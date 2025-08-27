"""
Simple HTTP Proxy for FanFilm Kodi addon
This module starts a simple HTTP proxy server that listens for incoming
HTTP requests and forwards them to an external server, modifying the headers as necessary.
"""

from typing import Optional, Union, Any, Tuple, List, Dict, Set, Iterable, Mapping
from typing import ClassVar, Type, Callable, TYPE_CHECKING
from typing_extensions import TypeAlias, ParamSpec
import sys
from enum import Enum
# from contextlib import closing
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from attrs import define, frozen, asdict
if sys.version_info >= (3, 9):
    from random import randbytes
else:
    from random import randint
    def randbytes(n: int) -> bytes:
        return b''.join(bytes((randint(0, 255),)) for _ in range(n))
if TYPE_CHECKING:
    from .tracking.trakt import TraktSync
    from .misc import VolatileFfid
    from .main import Works

import requests
import xbmcaddon

from .http_request import (
    RequestHandler, Route, request, Address,
    HTTPBadRequest, HTTPNotFound, HTTPUnprocessableContent, ExpectedJsonObjectError,
)
from .predefined import EMPTY_M3U, TT430
from ..ff.control import plugin_id, busy_dialog
from ..ff.settings import settings
from ..ff.log_utils import fflog, fflog_exc
from ..ff.routing import URL  # , Router
from ..ff.threads import Thread, Event, Lock
from ..ff.tricks import MISSING
from ..ff.types import JsonData, JsonResult
from ..ff.item import FFItem
from ..ff.db.db import Db, DbManager, DbMode, SqlConnection, SqlCursor
from ..ff.db import state
from ..ff.kotools import KodiRpc
from ..defs import MediaRef
from const import const, StateMode

PS = ParamSpec('PS')
RouteResultValue: TypeAlias = Union[JsonResult, str]
RouteResult: TypeAlias = Union[Tuple[int, RouteResultValue], RouteResultValue]

# Initialize addon
addon = xbmcaddon.Addon(id=plugin_id)

DbClientId: TypeAlias = str


# DEBUG (command line tests)
if __name__ == '__main__':
    from ..ff.cmdline import DebugArgumentParser
    p = DebugArgumentParser()
    p.add_argument('-p', '--port', type=int, default=8123, help='server port')
    p.add_argument('-t', '--threading', action='store_true', help='multithreading / concurent requests')
    args = p.parse_args()


class SqlMethod(Enum):
    EXECUTE = 'execute'
    EXECUTE_MANY = 'executemany'
    EXECUTE_SCRIPT = 'executescript'
    COMMIT = 'commit'
    ROLLBACK = 'rollback'


@define
class DbClient:
    """Represents single client connection."""
    id: DbClientId
    db: Db
    cursor: SqlCursor


if TYPE_CHECKING:
    class ServerBase(ThreadingHTTPServer):
        pass
elif __name__ == '__main__' and not args.threading:  # DEBUG only !!!
    class ServerBase(HTTPServer):
        pass
else:
    class ServerBase(ThreadingHTTPServer):
        pass


class Server(ServerBase):
    """FanFilm HTTP Server."""

    def __init__(self,
                 server_address: Address,
                 RequestHandlerClass: Type[BaseHTTPRequestHandler],
                 *,
                 works: Optional['Works'] = None,
                 ) -> None:
        super().__init__(server_address, RequestHandlerClass)
        host, port = self.server_address
        self.url = URL(f'http://{host}:{port}/')
        self.db_lock = Lock()
        self.db_conns: Dict[DbClientId, Db] = {}
        self.db_clients: Dict[DbClientId, DbClient] = {}
        self.works: Optional['Works'] = works
        self.events: Dict[str, Event] = {} if works is None else works.events  # no copy - shared events
        self.trakt_sync: Optional['TraktSync'] = works and works.trakt_sync
        self.volatile_ffid: Optional['VolatileFfid'] = works and works.volatile_ffid
        if self.trakt_sync:
            self.events.setdefault('trakt', self.trakt_sync.synced)

    def _get_db_under_lock(self, name: str):
        """Get DB connection. MUST be under self.lock."""
        try:
            return self.db_conns[name]
        except KeyError:
            pass
        # DB manager is used only for create connection. Do NOT use manage methods here.
        manager = DbManager()
        path = manager._path_for_name(name)
        db = manager._create_connection(name, path, mode=DbMode.SEPARATED)
        self.db_conns[name] = db
        return db

    def _get_db(self, name: str):
        with self.db_lock:
            return self._get_db_under_lock(name)

    def _get_client(self, cid: Optional[DbClientId], name: str) -> DbClient:
        with self.db_lock:
            if cid:
                try:
                    return self.db_clients[cid]
                except KeyError:
                    pass
            while True:
                cid = randbytes(8).hex()
                if cid not in self.db_clients:
                    break
            db = self._get_db_under_lock(name)
            self.db_clients[cid] = client = DbClient(cid, db, db._conn.cursor())
            return client

    @Route.get(r'/info?')
    def info(self) -> JsonResult:
        from ..ff.control import plugin_id
        return {
            'status': 'ok',
            'plugin': plugin_id,
        }

    @Route.post(r'/db/(?P<name>\w+)/?')
    def db_query(self, name: str) -> JsonResult:
        """Handle SQL query POST."""
        data = request.json
        if not isinstance(data, Mapping):
            raise ExpectedJsonObjectError()
        try:
            cid = data.get('cursor')
            method = SqlMethod(data.get('method', 'execute'))
            if method in (SqlMethod.COMMIT, ):
                query = ''
                params = ()
            else:
                query = data['query']
                if method == SqlMethod.EXECUTE_MANY:
                    params = data['params']
                else:
                    params = data.get('params', ())
        except (KeyError, ValueError):
            raise HTTPUnprocessableContent(message='innorect request')
        client = self._get_client(cid, name)
        with self.db_lock:
            if method is SqlMethod.EXECUTE:
                client.cursor.execute(query, params)
            elif method is SqlMethod.EXECUTE_MANY:
                client.cursor.executemany(query, params)
            elif method is SqlMethod.EXECUTE_SCRIPT:
                client.cursor.executescript(query)
            elif method is SqlMethod.COMMIT:
                client.cursor.connection.commit()
            elif method is SqlMethod.ROLLBACK:
                client.cursor.connection.rollback()
            return {
                'status': 'ok',
                'items': client.cursor.fetchall(),
                'lastrowid': client.cursor.lastrowid,
                'rowcount': client.cursor.rowcount,
            }

    @Route.post(r'/event/(?P<name>[a-zA-Z]\w*)(?:/(?P<action>\w+))?/?')
    def event_request(self, name: str, action: Optional[str] = None) -> JsonResult:
        """Remote service events support."""
        event = self.events.get(name)
        if event is None:
            raise HTTPNotFound(message=f'Event {name!s} not found')
        if not action:
            action = 'get'
        data = {'status': 'ok', 'event': name, 'action': action}
        if action == 'get':
            return data
        elif action == 'wait':
            result = event.wait()
            return {**data, 'state': result}
        elif action == 'set':
            event.set()
            return {**data, 'state': event.is_set()}
        elif action == 'clear':
            event.clear()
            return {**data, 'state': event.is_set()}
        else:
            raise HTTPUnprocessableContent(message=f'Unspotted event action {action!r}')

    @Route.post(r'/trakt/(?P<action>\w+)/?')
    def trakt(self, action: Optional[str] = None) -> JsonResult:
        """Remote service events support."""
        if self.trakt_sync is None:
            raise HTTPUnprocessableContent(message='Trakt not initialized')
        event = self.events.get('trakt')
        if event is None:
            raise HTTPNotFound(message='Event trakt not found')
        if not action:
            action = 'get'
        timeout = request.json.get('timeout') if isinstance(request.json, Mapping) else None
        data = {'status': 'ok', 'action': action}
        if action == 'get':
            return data
        elif action == 'sync':
            status = self.trakt_sync.sync(timeout=timeout)
            return {**data, 'timestamp': status and status.timestamp, 'changed': bool(status and status.changed)}
        elif action == 'wait':
            status = self.trakt_sync.wait_for_sync(timeout=timeout)
            return {**data, 'timestamp': status and status.timestamp, 'changed': bool(status and status.changed)}
        else:
            raise HTTPUnprocessableContent(message=f'Unspotted trakt action {action!r}')

    @Route.get(r'/plugin/request/info/?')
    @Route.get(r'/folder/info/?')
    def get_plugin_request_info(self) -> JsonResult:
        """Get folder info."""
        if not self.works:
            raise HTTPUnprocessableContent(message='Works are not initialized')
        return {
            'status': 'ok',
            'plugin_request': self.works.folder.__to_json__(),
        }

    @Route.post(r'/plugin/request/enter/?')
    @Route.post(r'/folder/enter/?')
    def plugin_request_enter(self) -> JsonResult:
        """Enter into new plugin folder."""
        if not self.works:
            raise HTTPUnprocessableContent(message='Works are not initialized')
        if not isinstance(request.json, Mapping):
            raise HTTPUnprocessableContent(message='innorect request, object requested')
        if not (url := request.json.get('url')):
            raise HTTPUnprocessableContent(message='"url" missing')
        enter_timestamp = request.json.get('timestamp')
        self.works.folder.enter(url, timestamp=enter_timestamp)
        if self.works.folder.locked:
            if event := self.events.get('folder'):
                fflog('[SERVICE] lock the folder')
                event.clear()  # folder is not ready if locked
        if const.tune.service.group_update_busy_dialog and self.works.folder.scan_started:
            busy_dialog(True)
        return {
            'status': 'ok',
            'plugin_request': self.works.folder.__to_json__(),
        }

    @Route.post(r'/plugin/request/exit/?')
    @Route.post(r'/folder/exit/?')
    def plugin_request_exit(self) -> JsonResult:
        """Exit from list new plugin folder."""
        if not self.works:
            raise HTTPUnprocessableContent(message='Works are not initialized')
        if const.tune.service.group_update_busy_dialog and self.works.folder.scan_finished:
            busy_dialog(False)
        if not isinstance(request.json, Mapping):
            raise HTTPUnprocessableContent(message='innorect request, object requested')
        if (folder_data := request.json.get('folder', MISSING)) is MISSING:
            raise HTTPUnprocessableContent(message='"folder" missing')
        if folder_data is None:
            folder = None
        else:
            folder = [FFItem.__from_json__(it) for it in folder_data]
        focus = request.json.get('focus', -1)
        exit_timestamp = request.json.get('timestamp')
        self.works.folder.exit(folder=folder, focus=focus, timestamp=exit_timestamp)
        return {
            'status': 'ok',
            'plugin_request': self.works.folder.__to_json__(),
        }

    # DEBUG only (!!!)
    @Route.post(r'/plugin/request/ready/force/?')
    @Route.post(r'/folder/ready/force/?')
    def folder_force_ready(self, action: str = 'ready') -> JsonResult:
        """Handle folder ready event - force ready only."""
        if (event := self.events.get('folder')) is None:
            raise HTTPNotFound(message='Event folder not found')
        state = True
        if isinstance(request.json, Mapping):
            state = bool(request.json.get('set', True))
        if state:
            event.set()
        else:
            event.clear()
        # done = event.clear()
        return {
            'status': 'ok',
            'ready': event.is_set(),
        }

    @Route.route(('POST', 'GET'), r'/(?:plugin/request|folder)/(?P<action>ready)/?')
    def folder_ready(self, action: str = 'ready') -> JsonResult:
        """Handle folder ready event."""
        if (event := self.events.get('folder')) is None:
            raise HTTPNotFound(message='Event folder not found')
        timeout = request.json.get('timeout') if isinstance(request.json, Mapping) else None
        verbose = not event.is_set()
        if verbose:
            fflog('[FOLDER] wait')
        done = event.wait(timeout=timeout)
        if verbose:
            fflog(f'[FOLDER] {done = }')
        return {
            'status': 'ok',
            'ready': done,
        }

    @Route.post(r'/folder/content/?')
    def set_folder_content(self) -> JsonResult:
        """Handle set folder content (list of items)."""
        if not self.works:
            raise HTTPUnprocessableContent(message='Works are not initialized')
        self.works.folder.content = ...

    @Route.get(r'/ffid/?')
    def list_ffid(self) -> JsonResult:
        """list all refs (filter by volatile ffid)."""
        if self.volatile_ffid is None:
            raise HTTPBadRequest(message='Volatile FFID is not supported')
        if 'ffid' in request.params:
            ffids = request.params.get('ffid', '')
            filters = {'ffid': ffids}
            refs = [{'ffid': ffid, 'ref': self.volatile_ffid.get(ffid)}
                    for ffid in map(int, ffids.split(','))]
        else:
            filters = {}
            refs = [{'ffid': ffid, 'ref': ref} for ffid, ref in self.volatile_ffid._refs.items()]
        return {
            'status': 'ok',
            'filters': filters,
            'refs': refs,
            }

    @Route.get(r'/ffid/(?P<ffid>\d+)/?')
    def get_ffid(self, ffid: int) -> JsonResult:
        """Get ref by volatile ffid."""
        if self.volatile_ffid is None:
            raise HTTPBadRequest(message='Volatile FFID is not supported')
        if ref := self.volatile_ffid.get(ffid):
            return {
                'status': 'ok',
                'ffid': ffid,
                'ref': ref.as_dict(),
            }
        raise HTTPNotFound(message=f'FFID {ffid} not found')

    @Route.post(r'/ffid/?')
    def create_ffid(self) -> JsonResult:
        """Create new volatile ffid for given ref."""
        if self.volatile_ffid is None:
            raise HTTPBadRequest(message='Volatile FFID is not supported')
        data = request.json
        if not isinstance(data, Mapping):
            raise ExpectedJsonObjectError()
        if refs := data.get('refs'):
            try:
                return {
                    'status': 'ok',
                    'refs': [{'ffid': self.volatile_ffid.register(ref), 'ref': ref.as_dict()}
                             for ref_json in refs if (ref := MediaRef(**ref_json))],
                }
            except TypeError as exc:
                raise HTTPUnprocessableContent(message=f'incorrect `refs` format: {exc}`') from None
        raise HTTPUnprocessableContent(message='`refs` missing')

    @Route.get(r'/state/(?P<module>[^/]+)(?:/(?P<key>[^/]+))?/?')
    def state_get(self, module: str, key: str = '') -> JsonResult:
        """Get variables from virtual DB state."""
        if not self.works:
            raise HTTPUnprocessableContent(message='Works are not initialized')
        if key:
            var = self.works.state.get(module=module, key=key)
            variables = [] if var is None else [var]
        else:
            variables = self.works.state.get_all(module=module)
        return {
            'status': 'ok',
            'variables': [asdict(var) for var in variables],
        }

    @Route.post(r'/state/?')
    def state_set(self) -> JsonResult:
        """Set variables in virtual DB state."""
        if not self.works:
            raise HTTPUnprocessableContent(message='Works are not initialized')
        data = request.json
        if not isinstance(data, Mapping):
            raise ExpectedJsonObjectError()
        if (variables := data.get('variables')) and isinstance(variables, list):
            self.works.state.multi_set(variables)
        else:
            raise HTTPUnprocessableContent(message='"variables" missing')
        return {
            'status': 'ok',
        }

    @Route.delete(r'/state/(?P<module>[^/]+)(?:/(?P<key>[^/]+))?/?')
    def state_delete(self, module: str, key: str = '') -> JsonResult:
        """Delete variable or whole module from virtual DB state."""
        if not self.works:
            raise HTTPUnprocessableContent(message='Works are not initialized')
        if key:
            var = self.works.state.delete(module=module, key=key)
            deleted = [] if var is None else [var]
        else:
            deleted = self.works.state.delete_all(module=module)
        return {
            'status': 'ok',
            'deleted': bool(deleted),
        }

    @Route.post(r'/state/wait/?')
    def state_wait(self) -> JsonResult:
        """Wait for variable value in virtual DB state."""
        if not self.works:
            raise HTTPUnprocessableContent(message='Works are not initialized')
        data = request.json
        if not isinstance(data, Mapping):
            raise ExpectedJsonObjectError()
        timeout: Optional[float] = data.get('timeout')
        if (var := data.get('wait_for')) and isinstance(var, Mapping) and (mod := var.get('module')) and (key := var.get('key')):
            res = self.works.state.wait_for(module=mod, key=key, value=var.get('value', True), timeout=timeout)
        else:
            raise HTTPUnprocessableContent(message='"wait_for" missing, or has no "module" and "key"')
        return {
            'status': 'ok',
            'result': res,
        }

    @Route.get(r'/media/tt430.mp4')
    def tt430(self) -> bytes:
        """Fake player (black) to avoid error on sources window cancel."""
        return TT430

    @Route.get(r'/media/(?:empty|stop).m3u8?')
    def stop_m3u(self) -> bytes:
        """Fake player (empty m38u playlist) to avoid error on sources window cancel."""
        return EMPTY_M3U

    @Route.post(r'.*drm(?:cda)?=(?P<url>.*)')
    def drm(self, url: str) -> bytes:
        """DRM woraround."""
        #     if "@" in url:
        #         url, header_str = url.split('@')
        link = '?'.join((url, request.url.query))
        fflog(f'[SERVICE][DRM] {link=}')
        headers = {k: v for k, v in request.headers.items() if k not in ('Host', 'Content-Type')}
        length = int(request.headers.get('Content-Length', 0))
        post_data = request.handler.rfile.read(length)
        fflog(f'[SERVICE][DRM] HTTP POST data {post_data!r}')
        resp = requests.post(url=url, headers=headers, data=post_data, params=request.params, verify=False)
        fflog(f'[SERVICE][DRM] HTTP Response {resp.status_code}, data {resp.content!r}')
        return resp.content

    @Route.get(r'/sleep/(?P<interval>\d+)')
    def sleep(self, interval: int) -> JsonData:
        """DEBUG. Sleep `interval` seconds."""
        from time import monotonic, sleep
        t = monotonic()
        if request.method != 'HEAD':
            sleep(interval)
        return {
            'slept': monotonic() - t,
        }

    @Route.get(r'/advanced_settings/?')
    def advanced_settings(self) -> JsonResult:
        from ..ff.settings import advanced_settings
        return advanced_settings.get()

    # @Route.get(r'/library/?')
    # def library_list(self) -> JsonResult:
    #     ...

    # @Route.get(r'/library/(?P<batch>\d+)/?')
    # def library_get(self, batch: int) -> JsonResult:
    #     ...

    @Route.post(r'/library/?')
    def library_add(self) -> JsonResult:
        if not self.works:
            raise HTTPUnprocessableContent(message='Works are not initialized')
        if not self.works.library:
            raise HTTPUnprocessableContent(message='Library is not enabled')
        data = request.json
        if not isinstance(data, Mapping):
            raise ExpectedJsonObjectError()
        name = data.get('name')
        force_sync = data.get('force_sync', False)
        quiet = data.get('quiet', False)
        if (items := data.get('items')) and isinstance(items, list):
            batch_id = self.works.library.add([MediaRef.__from_json__(it) for it in items], name=name, force_sync=force_sync, quiet=quiet)
        else:
            raise HTTPUnprocessableContent(message='"items" missing')
        return {
            'status': 'ok',
            'batch': {
                'id': batch_id,
            },
        }


class HttpProxy:
    """
    The main function that starts the HTTP Proxy server.
    """

    def __init__(self,
                 *,
                 works: Optional['Works'],
                 ) -> None:
        self._running: bool = False
        self._server: Optional[HTTPServer] = None
        self._httpd_thread: Optional[Thread] = None
        self.works: Optional['Works'] = works

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start proxy server (in new therad)."""
        if self._running:
            return

        address = '127.0.0.1'  # Localhost
        try:
            # create HTTP server and start serve in new therad
            self._server = Server((address, RequestHandler.DEFAULT_PORT), RequestHandler, works=self.works)
            self._server.allow_reuse_address = True
            self._httpd_thread = Thread(target=self._server.serve_forever)
            self._httpd_thread.start()
            self._running = True

            # get port number and set server URL in the settings
            # GET.url = POST.url = self._server.url
            url = str(self._server.url)
            state.set('url', url, module='service', mode=StateMode.DB)
            fflog(f'=== Http Server Started: {self._server.url} ===')
            rpc = KodiRpc()
            rpc.notify('ServiceUpdate', {'url': url})

        except Exception:
            # creating HTTP server failed, clear URL in the settings
            state.set('url', None, module='service', mode=StateMode.DB)
            self._running = False
            fflog_exc()
            raise

    def stop(self):
        """Stop proxy server."""
        if not self._running:
            return

        # shutdown and close the server
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server.socket.close()
            self._server = None
        if self._httpd_thread is not None:
            self._httpd_thread.join()
            self._httpd_thread = None
        self._running = False

        # clear URL in the settings
        state.set('url', None, module='service', mode=StateMode.DB)
        fflog('=== Http Server Stopped ===')


if __name__ == '__main__':
    from .misc import VolatileFfid
    from .main import Works
    address = '127.0.0.1'
    works = Works(
        events={
            'folder': Event(),
        },
        volatile_ffid=VolatileFfid()
    )
    works.events['folder'].set()
    server = Server((address, args.port), RequestHandler, works=works)
    server.allow_reuse_address = True
    server.serve_forever()
