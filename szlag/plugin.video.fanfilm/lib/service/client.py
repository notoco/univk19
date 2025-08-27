"""
Simple FF Service client to use it in FF plugin.
"""

from __future__ import annotations
from typing import Optional, Union, Any, Dict, Iterable, Mapping, Sequence, Iterator, ClassVar, overload, TYPE_CHECKING
from typing_extensions import Literal
from contextlib import contextmanager
from time import time as cur_time
import json
import requests
from attrs import asdict, evolve

from ..ff.log_utils import fflog, fflog_exc
from ..ff.url import URL
from ..ff.kotools import xsleep
from ..ff.db import state
from ..defs import MediaRef
from .misc import PluginRequestInfo, JsonEncoder, StateVar
from ..kolang import L
if TYPE_CHECKING:
    from ..ff.item import FFItem
    from .misc import VolatileFfid
from const import const, StateMode


class IncorrectResponse(ValueError):
    @property
    def data(self):
        return self.args[0] if self.args else None


class ServiceClient:
    """Simple FF Service client."""

    LOG_EXCEPTION: ClassVar[bool] = True
    FAKE: ClassVar[bool] = False

    def __init__(self, *, port: Optional[int] = const.tune.service.http_server.port) -> None:
        self._url: str | None = None
        self._volatile_ffid: VolatileFfid | None = None
        if port:
            self._url = f'http://127.0.0.1:{port}/'

    @overload
    def make_url(self, *, connect: Literal[True] = True) -> str: ...

    @overload
    def make_url(self, *, connect: Literal[False]) -> str | None: ...

    def make_url(self, *, connect: bool = True) -> str | None:
        """Service HTTP server URL."""
        if self._url is None:
            for i in range(const.tune.service.http_server.try_count or 1):
                url: Optional[str] = state.get('url', module='service', mode=StateMode.DB, from_boot=True)
                # from ..info import exec_id
                # fflog(f'[{exec_id()}] get url from db: {url!r}', traceback=True)
                if url:
                    self._url = url
                    break
                if not connect:
                    return None
                if self.FAKE:
                    self._url = 'http://127.0.0.1:8123/'
                    break
                if self._wait_for_service():
                    continue
                if not i:
                    fflog('No FF service URL, wait a little')
                xsleep(const.tune.service.http_server.wait_for_url or .01)
            else:
                fflog('ERROR: No FF service URL')
                return 'http://127.0.0.1:8123/'  # invalid URL (invalid port)
        return self._url

    @property
    def url(self) -> str:
        """Service HTTP server URL."""
        return self.make_url()

    @contextmanager
    def log_conn(self) -> Iterator[None]:
        try:
            yield None
        except requests.ConnectionError as exc:
            fflog(f'Connection to service {self.url} failed: {exc}')

    def _wait_for_service(self, *, timeout: Optional[float] = None) -> bool:
        """Wait for service to be available."""
        from ..ff.kotools import KodiRpc, Notification
        from ..ff.control import is_plugin_folder
        if is_plugin_folder():
            with Notification('FanFilm', L(30475, 'Waiting for service...')):
                return KodiRpc().wait_for_service(timeout=timeout)
        else:
            return KodiRpc().wait_for_service(timeout=timeout)

    def folder_ready(self, *, timeout: Optional[float] = None) -> bool:
        """Wait for folder ready (watching progress update)."""
        if timeout is None:
            timeout = const.folder.lock_wait_timeout
        try:
            data = requests.post(f'{self.url}folder/ready', timeout=timeout + 0.5, json={'timeout': timeout}).json()
            return data.get('ready', False)
        except Exception:
            if self.LOG_EXCEPTION:
                fflog_exc()
            return False

    def plugin_request_info(self) -> PluginRequestInfo:
        """Get folder info."""
        timeout = 3.0
        try:
            data = requests.get(f'{self.url}plugin/request/info', timeout=timeout + 0.5).json()
            if not isinstance(data, Mapping) or 'plugin_request' not in data:
                raise IncorrectResponse(data)
            return PluginRequestInfo.__from_json__(data['plugin_request'])
        except IncorrectResponse as exc:
            fflog.warning(f'Incorrect response: {exc.data!r}')
        except Exception:
            if self.LOG_EXCEPTION:
                fflog_exc()
        return PluginRequestInfo()

    def plugin_request_enter(self, url: Union[URL, str], *, timestamp: Optional[float] = None) -> PluginRequestInfo:
        """Notify server about FF plugin folder enter."""
        if not isinstance(url, str):
            url = str(url)
        timeout = 3.0
        try:
            data = None
            for _ in range(3):
                try:
                    data = requests.post(f'{self.url}plugin/request/enter', timeout=timeout + 0.5, json={
                        'url': url,
                        'timestamp': timestamp,
                    }).json()
                except requests.exceptions.ConnectionError:
                    self._url = None  # reset URL to force re-fetch
                    self._wait_for_service()
                else:
                    break
            if not isinstance(data, Mapping) or 'plugin_request' not in data:
                raise IncorrectResponse(data)
            info = PluginRequestInfo.__from_json__(data['plugin_request'])
            if const.debug.log_folders:
                fflog(f'[FOLDER] ENTER  >>>>>  {info}')
            else:
                fflog('[FOLDER] ENTER  >>>')
            return info
        except IncorrectResponse as exc:
            fflog.warning(f'Incorrect response: {exc.data!r}')
        except Exception:
            if self.LOG_EXCEPTION:
                fflog_exc()
        return PluginRequestInfo()

    def plugin_request_exit(self, *, folder: Optional[Sequence[FFItem]] = None, focus: int = -1, timestamp: Optional[float] = None) -> PluginRequestInfo:
        """Notify server about FF plugin generate folder exit."""
        from ..info import exec_id
        timeout = 3.0
        data = None
        iid = exec_id()
        try:
            to_sent = json.dumps({
                'folder': folder,
                'focus': focus,
                'timestamp': timestamp,
            }, cls=JsonEncoder)
            if const.debug.log_folders:
                fflog(f'[FOLDER] EXIT [{iid}]   >>>>>  {to_sent}')
            else:
                fflog(f'[FOLDER] EXIT [{iid}]   >>>')
            data = requests.post(f'{self.url}plugin/request/exit', timeout=timeout + 0.5, data=to_sent).json()
            if not isinstance(data, Mapping) or 'plugin_request' not in data:
                raise IncorrectResponse(data)
            return PluginRequestInfo.__from_json__(data['plugin_request'])
        except IncorrectResponse as exc:
            fflog.warning(f'Incorrect response: {exc.data!r}')
        except Exception:
            if self.LOG_EXCEPTION:
                fflog_exc()
        finally:
            fflog(f'[FOLDER] EXIT [{iid}]   done')
        return PluginRequestInfo()

    folder_info = plugin_request_info
    folder_enter = plugin_request_enter
    folder_exit = plugin_request_exit

    def _fake_volatile_ffid(self) -> VolatileFfid | None:
        """Check if it is a widget call on startup, service could not exists yet."""
        # already has FF HTTP server URL – no need to use fake FFID
        if self._url is not None:
            return None
        # it is folder (not widget) – we have to use real FF HTTP server
        from ..ff.control import is_plugin_folder
        if is_plugin_folder():
            return None
        # check if server is up and we could get the URL – if yes, don't use fake FFID
        url: Optional[str] = state.get('url', module='service', mode=StateMode.DB, from_boot=True)
        if url:
            self._url = url
            return None
        # fake FFID is not used yet – create one
        if self._volatile_ffid is None:
            from .misc import VolatileFfid
            self._volatile_ffid = VolatileFfid()
        return self._volatile_ffid

    def get_ffid_ref(self, ffid: int, *, timeout: Optional[float] = None) -> Optional[MediaRef]:
        """Get ref by volatile ffid."""
        req_timeout = None if timeout is None else timeout + .5
        if vffid := self._fake_volatile_ffid():
            return vffid.get(ffid)
        try:
            data = requests.get(f'{self.url}ffid/{ffid}', timeout=req_timeout).json()
            if not isinstance(data, Mapping) or 'ref' not in data:
                raise IncorrectResponse(data)
            if data.get('status') == 'ok':
                return MediaRef(**data['ref'])
            msg = data.get('message', '')
            fflog(f'Get volatile FFID failed: {msg}')
        except IncorrectResponse as exc:
            fflog.warning(f'Incorrect response: {exc.data!r}')
        except Exception:
            if self.LOG_EXCEPTION:
                fflog_exc()
        return None

    def get_ffid_ref_dict(self, ffid_list: Iterable[int], *, timeout: Optional[float] = None) -> Dict[int, MediaRef]:
        """Get refs by volatile ffid list, return dict[ffid] = ref."""
        req_timeout = None if timeout is None else timeout + .5
        if vffid := self._fake_volatile_ffid():
            return {ffid: ref for ffid in ffid_list if (ref := vffid.get(ffid)) is not None}
        try:
            data = requests.get(f'{self.url}ffid/', params={'ffid': ','.join(map(str, ffid_list))}, timeout=req_timeout).json()
            if not isinstance(data, Mapping) or 'refs' not in data:
                raise IncorrectResponse(data)
            if data.get('status') == 'ok':
                return {it['ffid']: MediaRef(**jref) for it in data['refs'] if it and (jref := it['ref'])}
            msg = data.get('message', '')
            fflog(f'Get volatile FFID failed: {msg}')
        except IncorrectResponse as exc:
            fflog.warning(f'Incorrect response: {exc.data!r}')
        except Exception:
            if self.LOG_EXCEPTION:
                fflog_exc()
        return {}

    def create_ffid(self, ref: MediaRef, *, timeout: Optional[float] = None) -> Optional[int]:
        """Create new volatile ffid for given ref."""
        req_timeout = None if timeout is None else timeout + .5
        if vffid := self._fake_volatile_ffid():
            return vffid.register(ref)
        try:
            data = requests.post(f'{self.url}ffid', timeout=req_timeout, json={'ref': ref.as_dict()}).json()
            if not isinstance(data, Mapping) or 'ffid' not in data:
                raise IncorrectResponse(data)
            if data.get('status') == 'ok':
                return data['ffid']
            msg = data.get('message', '')
            fflog(f'Create volatile FFID failed: {msg}')
        except IncorrectResponse as exc:
            fflog.warning(f'Incorrect response: {exc.data!r}')
        except Exception:
            if self.LOG_EXCEPTION:
                fflog_exc()
        return None

    def create_ffid_dict(self, refs: Iterable[MediaRef], *, timeout: Optional[float] = None) -> Dict[MediaRef, int]:
        """Create new volatile ffid for given ref."""
        req_timeout = None if timeout is None else timeout + .5
        if vffid := self._fake_volatile_ffid():
            return {ref: vffid.register(ref) for ref in refs}
        try:
            data = requests.post(f'{self.url}ffid', timeout=req_timeout, json={'refs': [ref.as_dict() for ref in refs]}).json()
            if not isinstance(data, Mapping) or 'refs' not in data:
                raise IncorrectResponse(data)
            if data.get('status') == 'ok':
                return {MediaRef(**jref): it['ffid'] for it in data['refs'] if it and (jref := it['ref'])}
            msg = data.get('message', '')
            fflog(f'Create volatile FFID failed: {msg}')
        except IncorrectResponse as exc:
            fflog.warning(f'Incorrect response: {exc.data!r}')
        except Exception:
            if self.LOG_EXCEPTION:
                fflog_exc()
        return {}

    def trakt_sync(self) -> Optional[bool]:
        """Synchronize trakt.tv."""
        try:
            resp = requests.post(f'{self.url}trakt/sync', json={'timeout': const.trakt.sync.wait_for_service_timeout}).json()
        except requests.ConnectionError as exc:
            fflog(f'Connection to service {self.url} failed: {exc}')
        else:
            try:
                return bool(resp.get('changed'))
            except Exception:
                if self.LOG_EXCEPTION:
                    fflog_exc()
        return None

    def state_get(self, module: str, key: str = '') -> Sequence[StateVar]:
        """Return service state variable."""
        url = f'{self.url}state/{module}'
        if key:
            url = f'{url}/{key}'
        try:
            resp = requests.get(url).json()
        except requests.ConnectionError as exc:
            fflog(f'Connection to service {self.url} failed: {exc}')
        else:
            try:
                return [StateVar(**it) for it in resp.get('variables', ())]
            except Exception:
                if self.LOG_EXCEPTION:
                    fflog_exc()
        return []

    def state_set(self, variables: Iterable[StateVar], *, connect: bool = True) -> Optional[bool]:
        """Set list of variables to service state."""
        url = self.make_url(connect=connect)
        if not url:
            fflog(f'No URL {connect=}')
            return None
        try:
            resp = requests.post(f'{url}state', json={'variables': tuple(asdict(var) for var in variables)}).json()
        except requests.ConnectionError as exc:
            fflog(f'Connection to service {url} failed: {exc}')
        else:
            try:
                return resp.get('status') == 'ok'
            except Exception:
                if self.LOG_EXCEPTION:
                    fflog_exc()
        return None

    def state_delete(self, module: str, key: str = '', *, connect: bool = True) -> Optional[bool]:
        """Delete service state variable."""
        url = self.make_url(connect=connect)
        if not url:
            fflog(f'No URL {connect=}')
            return None
        url = f'{url}state/{module}'
        if key:
            url = f'{url}/{key}'
        try:
            requests.delete(url)
        except requests.ConnectionError as exc:
            fflog(f'Connection to service {self.url} failed: {exc}')
        else:
            return True
        return None

    def state_wait(self, module: str, key: str, value: Any, *, timeout: Optional[float] = None) -> Optional[bool]:
        """Wait for service state variable change."""
        try:
            requests.post(f'{self.url}state/wait', json={'wait_for':
                                                         {'module': module, 'key': key, 'value': value},
                                                         'timeout': timeout,
                                                         }).json()
        except requests.ConnectionError as exc:
            fflog(f'Connection to service {self.url} failed: {exc}')
        else:
            return True
        return None

    @contextmanager
    def state_with(self, module: str, key: str) -> Iterator[None]:
        """Section with service state variable (set ti True in the statement, and False on exit)."""
        url = f'{self.url}state'
        var = StateVar(module=module, key=key, value=True, type='bool', updated_at=cur_time())
        try:
            requests.post(url, json={'variables': [asdict(var)]})
        except requests.ConnectionError as exc:
            fflog(f'Connection to service {self.url} failed: {exc}')
        try:
            yield None
        finally:
            var = evolve(var, value=False, updated_at=cur_time())
            try:
                requests.post(url, json={'variables': [asdict(var)]})
            except requests.ConnectionError as exc:
                fflog(f'Connection to service {self.url} failed: {exc}')

    def advanced_settings(self) -> Dict[str, Any]:
        """Return advancedsettings.xml as JSON structure."""
        with self.log_conn():
            return requests.get(f'{self.url}advanced_settings').json()
        return {}

    def library_add(self, items: Sequence[Union[MediaRef, FFItem]], *, name: Optional[str] = None,
                    force_sync: bool = False, quiet: bool = False) -> None:
        """Add to library items by theirs ref."""
        with self.log_conn():
            requests.post(f'{self.url}library', json={
                'name': name,
                'items': [it.ref for it in items],
                'force_sync': force_sync,
                'quiet': quiet,
            })


#: Default global service client.
service_client = ServiceClient()
