
from pathlib import Path
from sqlite3 import connect as db_connect, Connection, Cursor, OperationalError
from contextlib import contextmanager
from threading import Lock
import json
from typing import Optional, Union, Any, Tuple, List, Dict, Sequence, Mapping, Iterator
# from .kodidb import KodiVideoDB, KodiVideoInfo, video_db
from xbmc import executeJSONRPC, getInfoLabel, getCondVisibility

#: Any JSON data object.
JsonData = Dict[str, Any]
#: Any JSON data.
JsonResult = Union[JsonData, List[JsonData]]

#: Keyword arguements.
Args = Tuple[Any, ...]
#: Keyword arguements.
KwArgs = Dict[str, Any]

#: Any patameters.
Params = Dict[str, Any]


class ServiceSpy:

    VIDEO_DB_PATH = Path('~/.kodi/userdata/Database/MyVideos131.db').expanduser()

    def __init__(self):
        self.lock = Lock()
        self._conn: Optional[Connection] = None
        self._jsonrpc_id = 1
        self.url = 'http://127.0.0.1:8000/'  # notif logger

    def send(self) -> None:
        ...

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        """Open connection to he DB or use existing one."""
        new_conn: bool = not self._conn
        if not self._conn:
            self._conn = db_connect(f'file:{self.VIDEO_DB_PATH}?mode=ro', uri=True, check_same_thread=False, timeout=10)
        try:
            yield self._conn
        finally:
            try:
                if new_conn:
                    self._conn.close()
            finally:
                if new_conn:
                    self._conn = None

    @contextmanager
    def cursor(self) -> Iterator[Cursor]:
        """Create DB cursor."""
        with self.lock:
            with self.connection() as conn:
                cur = conn.cursor()
                try:
                    yield cur
                finally:
                    try:
                        cur.connection.commit()
                    finally:
                        cur.close()

    def get_plays(self):
        # where = f" WHERE strFilename LIKE 'plugin://plugin.video.fanfilm/%'"
        where = ''
        cols = ('idFile', 'idBookmark', 'strFilename', 'playCount', 'timeInSeconds', 'totalTimeInSeconds')
        with self.cursor() as cur:
            cur.execute('SELECT'
                        ' f.idFile, b.idBookmark, strFilename, playCount, timeInSeconds, totalTimeInSeconds'
                        ' FROM files AS f LEFT JOIN bookmark AS b ON b.idFile == f.idFile'
                        f' {where}')
            return [{col: val for col, val in zip(cols, row)} for row in cur.fetchall()]

    def rpc(self, method: str, *, params: Optional[Params] = None, fields: Sequence[str] = ()) -> JsonResult:
        """Call remote procedure (JSONRPC)."""
        msg_id, self._jsonrpc_id = self._jsonrpc_id, self._jsonrpc_id + 1
        params = dict(params or {})
        req = {
            'jsonrpc': '2.0',
            'method': method,
            'params': params,
            'id': msg_id,
        }
        if fields:
            params['properties'] = tuple(fields)
        data = json.loads(executeJSONRPC(json.dumps(req)))
        return data

    def rpc_list(self, method: str, *, params: Optional[Params] = None, fields: Sequence[str] = (), return_type: Optional[str] = None) -> Sequence[JsonData]:
        """Call remote procedure (JSONRPC)."""
        data = self.rpc(method=method, params=params, fields=fields)
        if isinstance(data, Mapping) and isinstance((result := data.get('result')), Mapping):
            if return_type is None:
                return_type = next(iter(result.keys() - {'limits'}), None)
                if return_type is None:
                    return []
            return result[return_type]
        return []

    def rpc_object(self, method: str, *, params: Optional[Params] = None, fields: Sequence[str] = (), return_type: Optional[str] = None) -> JsonData:
        """Call remote procedure (JSONRPC)."""
        data = self.rpc(method=method, params=params, fields=fields)
        if isinstance(data, Mapping) and isinstance((result := data.get('result')), Mapping):
            if return_type is None:
                return_type = next(iter(result.keys() - {'limits'}), None)
                if return_type is None:
                    return {}
            return result[return_type]
        return {}

    def get_players(self) -> Sequence[JsonData]:
        return self.rpc_list('Player.GetPlayers')

    def get_info(self) -> JsonData:
        return {
            'ListItem': {
                'u.ffid': getInfoLabel('ListItem.UniqueID(ffid)'),
                'u.ffref': getInfoLabel('ListItem.UniqueID(ffref)'),
                'u.tmdb': getInfoLabel('ListItem.UniqueID(tmdb)'),
                'u.imdb': getInfoLabel('ListItem.UniqueID(imdb)'),
                'u.dbid': getInfoLabel('ListItem.UniqueID(dbid)'),
                'imdb': getInfoLabel('ListItem.IMDBNumber'),
                'dbid': getInfoLabel('ListItem.DBID'),
                'path': getInfoLabel('ListItem.FilenameAndPath'),
                'resume': getCondVisibility('ListItem.IsResumable'),
                'progress': getInfoLabel('ListItem.PercentPlayed'),
                'index': getInfoLabel('ListItem.CurrentItem'),
                'title': getInfoLabel('ListItem.Title'),
                'label': getInfoLabel('ListItem.Label'),
            },
            'Player': {
                'path': getInfoLabel('Player.FilenameAndPath'),
                'fname': getInfoLabel('Player.Filename'),
                'playing': getCondVisibility('Player.Playing'),
                'progress': getInfoLabel('Player.Progress'),
            },
            'VideoPlayer': {
                'u.ffid': getInfoLabel('VideoPlayer.UniqueID(ffid)'),
                'u.ffref': getInfoLabel('VideoPlayer.UniqueID(ffref)'),
                'u.tmdb': getInfoLabel('VideoPlayer.UniqueID(tmdb)'),
                'u.imdb': getInfoLabel('VideoPlayer.UniqueID(imdb)'),
                'u.dbid': getInfoLabel('VideoPlayer.UniqueID(dbid)'),
                'imdb': getInfoLabel('VideoPlayer.IMDBNumber'),
                'dbid': getInfoLabel('VideoPlayer.DBID'),
                'progress': getInfoLabel('Player.Progress'),
                'title': getInfoLabel('Player.Title'),
            },
        }

    def onNotification(self, sender: str, method: str, data: str) -> None:
        from ..ff.log_utils import fflog
        from ..ff.kodidb import video_db
        fflog('--------------------------------------')
        fflog(f'SENDER: {sender!r}, METHOD: {method!r}, DATA: {"null" if data is None else json.dumps(json.loads(data), indent=2)}')
        fflog(f'PLAYERS: {json.dumps(self.get_players(), indent=2)}')
        fflog(f'INFO: {json.dumps(self.get_info(), indent=2)}')
        # video_db.get_players()
        # video_db.get_player_item()


spy = ServiceSpy()


if __name__ == '__main__':
    from itertools import chain

    # def print_table(rows, *, sep=' | '):
    def print_table(rows, *, sep='\033[38;5;238m|\033[0m'):
        if not rows:
            return
        first = rows[0]
        if isinstance(first, dict):
            cols = tuple(first)
            rows = tuple(row.values() for row in rows)
        else:
            cols = tuple(f'[{i}]' for i in range(len(first)))
        lens = [max(len(str(c)) for c in cc) for cc in zip(*chain(rows, (cols,)))]
        print(sep.join(f'{v:^{w}}' for v, w in zip(cols, lens)))
        for row in rows:
            print(sep.join(f'{str(v):{w}}' for v, w in zip(row, lens)))

    print_table(spy.get_plays())
    # print_table((('asdasasdasd', 'bb', 1), ('aa', 'bbbbbbb', 22)))
    # print_table(({'a': 'asdasasdasd', 'b': 'bb', 'ccc': 1}, {'a': 'aa', 'b': 'bbbbbbb', 'ccc': 22}))
