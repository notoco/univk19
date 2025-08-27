"""
Direct access to Kodi MyVideo*.db.

Use carefully.
"""

from __future__ import annotations
import re
from pathlib import Path
from contextlib import contextmanager
from sqlite3 import connect as db_connect, Connection, Cursor, OperationalError
from time import sleep
from datetime import datetime
from urllib.parse import parse_qsl
import json
from typing import Optional, Union, Any, Tuple, List, Dict, Iterator, Iterable, Mapping, Sequence, TYPE_CHECKING
from typing_extensions import Literal, TypedDict, cast
from attrs import frozen, fields
from ..defs import MediaRef, RefType, VideoIds
from .types import JsonResult, JsonData, Params
from .kotools import KodiRpc
from .item import FFItem
from .db import Lock, sql_dump
from ..indexers.defs import VideoSequenceMixin
from .settings import settings, advanced_settings
from .calendar import fromisoformat
from .log_utils import fflog
from .control import plugin_url, ff2_plugin_url, ff3a_plugin_url
from const import const
if TYPE_CHECKING:
    from mysql.connector import MySQLConnection, PooledMySQLConnection

from xbmcvfs import translatePath, File
from ..kodi import version as kodi_ver


QueryParams = Dict[str, str]
# fid, bid, fname, play_count, lastPlayed, time_s, total_s
InfoRow = Tuple[int, Optional[int], str, Optional[int], Optional[str], Optional[float], Optional[float]]

_rx_ff3_show_link_prefix = re.compile(r'play/(?:tv)?show/')


def int_on_none(value: Any) -> Optional[int]:
    """Returns int or None."""
    if value is None:
        return None
    return int(value)


@frozen(kw_only=True)
class KodiVideoInfo:
    """Played/playing video DB row."""

    #: Media reference.
    ref: MediaRef
    #: files.fileId
    fid: Optional[int] = None
    #: bookmark.bookmarkId
    bid: Optional[int] = None
    #: files.strFilename
    fname: str = ''
    #: files.playCount
    play_count: int = 0
    #: Last played at (files.lastPlayed).
    played_at: Optional[int] = None
    #: bookmark.timeInSeconds
    time_s: float = 0
    #: bookmark.totalTimeInSeconds
    total_s: float = 0
    #: TMDB of movie or tv-show if any
    tmdb: Optional[int] = None
    #: IMDB of movie or tv-show if any
    imdb: Optional[str] = None
    #: Video is in library
    library: Optional[bool] = None
    #: Media label.
    label: Optional[str] = None

    @property
    def percent(self) -> Optional[float]:
        """Progress in percent (0..100)."""
        if self.total_s:
            return 100 * self.time_s / self.total_s
        return None

    @property
    def has_progress(self) -> bool:
        """File has progress (is playing)."""
        return bool(self.total_s)

    @property
    def fake(self) -> bool:
        """True if info is fake."""
        return self.fid is None

    def ffitem(self, *, role: str | None = None) -> FFItem:
        """Return FFItem from this video info."""
        # ref = self.ref
        # ff = FFItem(self.label, type=ref.type, ffid=ref.ffid, season=ref.season, episode=ref.episode)
        ff = FFItem(self.ref)
        if self.label:
            ff.label = self.label
        if self.tmdb:
            ff.vtag.setUniqueID(str(self.tmdb), 'tmdb', True)
        if self.imdb:
            ff.vtag.setUniqueID(self.imdb, 'imdb')
        if role is not None:
            played_at = datetime.min if self.played_at is None else datetime.fromtimestamp(self.played_at)
            ff.role = role.format(self, pb=self, info=self, percent=self.percent or '', play_count=self.play_count,
                                  played_at=played_at, played_at_timestamp=played_at)
        ff.kodi_data = self
        return ff


class VideoInfoList(VideoSequenceMixin[KodiVideoInfo], list):
    pass


#: Kodi Video Database version, see: https://kodi.wiki/view/Databases#Database_Versions
vdb_ver: str = {
    19: '119',
    20: '121',
    21: '131',
    22: '137',
}.get(kodi_ver, '131')


class MySqlCredentials(TypedDict):
    """Credentials for mysql connector."""
    database: str
    host: str
    port: int
    user: str
    password: str


@frozen(kw_only=True)
class VideoDbConf:
    """
    Koid VideoDb configuration taken from advancedsettings.xml
    and keep in FF3 settings toavoid XML parse each time.
    """
    type: Literal['sqlite3', 'mysql'] = 'sqlite3'
    host: str = '127.0.0.1'
    port: int = 3306
    user: str = 'kodi'
    password: str = ''
    database: str = f'MyVideos{vdb_ver}'

    def mysql_credentials(self) -> MySqlCredentials:
        """Return credentials for mysql connector."""
        return {
            'host': self.host,
            'port': self.port,
            'user': self.user,
            'password': self.password,
            'database': self.database,
        }


def _in_lib_query(cur: Cursor, table: str, file_id: int) -> bool:
    """Returns True if video is in kodi library."""
    try:
        cur.execute(f'SELECT 1 FROM {table} WHERE idFile = {file_id}')
        return bool(cur.fetchall())
    except OperationalError as exc:
        fflog(f'Query library for {table}:{file_id} failed: {exc}')
        return False


def parse_datetime(val: Optional[str]) -> Optional[int]:
    """Parse datetime and convert to timestamp."""
    if not val:
        return None
    return int(fromisoformat(val).timestamp())


def _make_info(row: InfoRow) -> Iterator[KodiVideoInfo]:
    """Create KodiVideoInfo from VideosDB SELECT, see KodiVideoDB.get_plays()."""
    fid, bid, fname, play_count, played_at, time_s, total_s = row  # NOTE: in SEELCT order.
    path: str = ''
    if ff3_plugin := fname.startswith(plugin_url):
        path = fname[len(plugin_url):]
    elif fname.startswith(ff3a_plugin_url):
        ff3_plugin = True  # support for FF3-alfa
        path = fname[len(ff3a_plugin_url):]
    if ff2_plugin := fname.startswith(ff2_plugin_url):
        path = fname[len(ff2_plugin_url):]
    tmdb: Optional[int] = None
    imdb: Optional[str] = None
    if ff3_plugin and path.startswith('play/movie/'):
        # fflog(f'[KodiDb] movie {fname = }, {fname.split("/")}, {play_count=}, {time_s=}')
        ref = MediaRef.movie(int(path.partition('?')[0].split('/')[2]))
        vid = ref.video_ids
        tmdb, imdb = vid.tmdb, vid.imdb
    elif ff3_plugin and _rx_ff3_show_link_prefix.match(path):
        # fflog(f'[KodiDb] show {fname = }, {fname.split("/")}, {play_count=}, {time_s=}')
        ref = MediaRef.tvshow(*map(int, path.partition('?')[0].split('/')[2:5]))
        vid = ref.video_ids
        tmdb, imdb = vid.tmdb, vid.imdb
    elif ff2_plugin:
        # FanFilm2 (old play URL)
        params = dict(parse_qsl(fname.partition('?')[2]))
        if not ({'tmdb', 'season', 'episode'} - params.keys()):  # not set-keys means all keys exists
            ref = MediaRef.tvshow(int(params['tmdb']), int(params['season']), int(params['episode']))
        elif 'tmdb' in params:
            ref = MediaRef.movie(int(params['tmdb']))
        else:
            return None
        tmdb = int(params['tmdb'])
        imdb = params.get('imdb')
    else:
        return None
    # detect if video is in library (False – NOT NOW, it seems to be useless)
    in_lib: Optional[bool] = None
    # if (real_type := ref.real_type) in ('movie', 'episode'):
    #     in_lib = _in_lib_query(cur, real_type, fid)
    yield KodiVideoInfo(ref=ref, fid=fid, bid=bid, fname=fname, play_count=play_count or 0, played_at=parse_datetime(played_at),
                        time_s=time_s or 0, total_s=total_s or 0, tmdb=tmdb, imdb=imdb, library=in_lib)


class KodiVideoDB(KodiRpc):
    """Kodi MyVideo*.db."""

    VTYPES: Dict[str, RefType] = {
        'tvshow': 'show',
    }
    KTYPES: Dict[str, RefType] = {
        'movie': 'movie',
        'show': 'tvshow',     # type: ignore  (out of RefType)
        'tvshow': 'tvshow',   # type: ignore  (out of RefType)
        'season': 'season',
        'episode': 'episode',
    }
    RPC_LIST_METHODS = {
        'movie': 'VideoLibrary.GetMovies',
        'show': 'VideoLibrary.GetTVShows',
        'tvshow': 'VideoLibrary.GetTVShows',
        'season': 'VideoLibrary.GetSeasons',
        'episode': 'VideoLibrary.GetEpisodes',
    }

    _plugin = plugin_url.rstrip('/')
    _old_plugin = 'plugin://plugin.video.fanfilm'
    _old_plugin_pattern = _old_plugin if _old_plugin == _plugin else fr'(?:{_plugin}|{_old_plugin})'
    _rx_movie_link = re.compile(fr'{_plugin}/play\d*/movie/(?P<ffid>\d+)\b(?:\?.*)?'
                                fr'|{_old_plugin_pattern}?.*\btmdb=(?P<tmdb>\d+).*')
    _rx_episode_link = re.compile(fr'{_plugin}/play\d*/(?:tv)?show/(?P<ffid>\d+)/(?P<season>\d+)/(?P<episode>\d+)(?:\?.*)?'
                                  fr'|{_old_plugin_pattern}?.*\btmdb=(?P<old_tmdb>\d+)?&season=(?P<old_season>\d+)&episode=(?P<old_episode>\d+).*')
    _rx_url_link = re.compile(r'[^:]*://[^/]*/play\d*?/(?P<type>[^/]+)/(?P<id>\d+)(?:/(?P<season>\d+)/(?P<episode>\d+))?.*')

    def __init__(self, *, path: Optional[Path] = None, echo: Optional[bool] = None) -> None:
        super().__init__()
        echo = const.dev.db.echo if echo is None else bool(echo)
        #: Path to video DB.
        self.path: Path = Path(translatePath('special://database')) / f'MyVideos{vdb_ver}.db' if path is None else path
        #: Connection to video DB.
        self._conn: Union[Connection, 'MySQLConnection', 'PooledMySQLConnection', None] = None
        #: Lock for multithread access.
        self.lock = Lock()
        #: Debug echo queries.
        self._echo: bool = not echo  # Force change echo detection.
        # Set echo proprery (change forced).
        self.echo = echo

    def video_db_conf(self) -> VideoDbConf:
        """Return video db configurtion."""
        if const.core.kodidb.advanced_settings:
            if cred := advanced_settings.get('videodatabase'):
                cred['password'] = cred.pop('pass', '')  # replace key "pass" → "password"
                allowed = {f.name for f in fields(VideoDbConf)}
                return VideoDbConf(**{k: v for k, v in cred.items() if k in allowed})
        return VideoDbConf()

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        """Open connection to he DB or use existing one."""
        new_conn: bool = not self._conn
        if self._conn is None:
            sets = self.video_db_conf()
            if sets.type == 'mysql':
                import mysql.connector
                try:
                    self._conn = mysql.connector.connect(**sets.mysql_credentials(),
                                                         autocommit=True, charset='utf8', use_unicode=True)
                except mysql.connector.Error as exc:
                    fflog.error(f'mysql connection failed {exc} with {sets.mysql_credentials()}')
                    raise
                if TYPE_CHECKING:
                    assert self._conn is not None
            else:
                self._conn = db_connect(f'file:{self.path}?mode=ro', uri=True, check_same_thread=False, timeout=10)
                self._update_echo()
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
                        conn.commit()
                    finally:
                        cur.close()

    @property
    def echo(self) -> bool:
        """Echo queries (debug)."""
        return self._echo

    @echo.setter
    def echo(self, echo: bool) -> None:
        """Echo queries (debug)."""
        echo = bool(echo)
        if self._echo != echo:
            self._echo = echo
            self._update_echo()

    def _update_echo(self) -> None:
        """Echo queries (debug)."""
        if self._conn is not None and hasattr(self._conn, 'set_trace_callback'):
            if self._echo:
                self._conn.set_trace_callback(self._log_statement)
            else:
                self._conn.set_trace_callback(None)

    def _log_statement(self, stmt: str):
        """Echo SQL statement."""
        fflog(f'(DB:{self.path.stem}) \033[38;5;244m {stmt!r} \033[0m', stack_depth=2)

    def get_plays(self, *, tries: int = 3) -> List[KodiVideoInfo]:
        """Return list of played or playing videos."""

        last_exc: Optional[Exception] = None
        for cnt in range(tries):
            try:
                with self.cursor() as cur:
                    where = ' OR '.join(f"strFilename LIKE '{p}%'" for p in {plugin_url, ff2_plugin_url, ff3a_plugin_url})
                    cur.execute('SELECT'
                                ' f.idFile, b.idBookmark, strFilename, playCount, lastPlayed, timeInSeconds, totalTimeInSeconds'
                                ' FROM files AS f LEFT JOIN bookmark AS b ON b.idFile = f.idFile'
                                f" WHERE {where}")
                    # row[2] - in order in SELECT above, it's `strFilename`
                    return VideoInfoList(info for row in cur.fetchall() for info in _make_info(row))
            except OperationalError as exc:
                last_exc = exc
                if cnt + 1 < tries:
                    sleep(.1)
        fflog(f'Access to kodi DB failed: {last_exc}')
        return VideoInfoList()

    def get_play(self, ref: MediaRef, *, tries: int = 3, old_fanfilm: bool = True) -> Optional[KodiVideoInfo]:
        """Return played or playing video by ref."""

        plugin = plugin_url.rstrip('/')
        if ref.is_movie:
            link = f'{plugin}/play/movie/{ref.ffid}'
            where = f"strFilename = '{link}' OR strFilename LIKE '{link}?%'"
        elif ref.is_episode:
            link = f'{plugin}/play/show/{ref.ffid}/{ref.season}/{ref.episode}'
            where = f"strFilename = '{link}' OR strFilename LIKE '{link}?%'"
            if True:  # URL for FF3-alfa tests only. TODO: Remove before release.
                link = f'{plugin}/play/tvshow/{ref.ffid}/{ref.season}/{ref.episode}'
                where = f"{where} OR strFilename = '{link}'"
        else:
            return None

        select = ('SELECT f.idFile, b.idBookmark, strFilename, playCount, lastPlayed, timeInSeconds, totalTimeInSeconds'
                  ' FROM files AS f LEFT JOIN bookmark AS b ON b.idFile = f.idFile')

        row: Optional[InfoRow] = None
        for cnt in range(tries):
            try:
                with self.cursor() as cur:
                    cur.execute(f'{select} WHERE {where}')
                    row = cur.fetchone()
                    fflog(f'[KodiDB] new {where!r}, {row=}')
                    if row is None and old_fanfilm:
                        vids = VideoIds.from_ffid(ref.ffid)
                        if vids and vids.tmdb:
                            if ref.is_movie:
                                where = f"strFilename LIKE '{plugin}/?action=play%&tmdb={vids.tmdb}'"
                            elif ref.is_episode:
                                where = f"strFilename LIKE '{plugin}/?action=play%&tmdb={vids.tmdb}&season={ref.season}&episode={ref.episode}'"
                            cur.execute(f'{select} WHERE {where}')
                            row = cur.fetchone()
                            fflog(f'[KodiDB] old {where!r}, {row=}')
                break
            except OperationalError:
                if cnt + 1 < tries:
                    sleep(.1)
        if row:
            fid, bid, fname, play_count, played_at, time_s, total_s = row
            if 'tmdb=' in fname:
                # FF2
                params = dict(parse_qsl(fname.partition('?')[2]))
                tmdb = int(params['tmdb'])
                imdb = params.get('imdb')
            else:
                # FF3
                vid = ref.video_ids
                tmdb, imdb = vid.tmdb, vid.imdb
            return KodiVideoInfo(ref=ref, fid=fid, bid=bid, fname=fname, tmdb=tmdb, imdb=imdb,
                                 play_count=play_count or 0, played_at=parse_datetime(played_at),
                                 time_s=time_s or 0, total_s=total_s or 0)
        return None

    def get_play_by_url(self, url: Union[str, Sequence[str]], *, tries: int = 3) -> Optional[KodiVideoInfo]:
        """"Return played or playing video by its URL (plugin://...)."""

        select = ('SELECT f.idFile, b.idBookmark, strFilename, playCount, lastPlayed, timeInSeconds, totalTimeInSeconds'
                  ' FROM files AS f LEFT JOIN bookmark AS b ON b.idFile = f.idFile WHERE ')
        if isinstance(url, str):
            select += f' strFilename = {sql_dump(url)}'
        else:
            values = ','.join(sql_dump(u) for u in url)
            select += f' strFilename IN ({values})'

        row: Optional[InfoRow] = None
        for cnt in range(tries):
            try:
                with self.cursor() as cur:
                    cur.execute(select)
                    row = cur.fetchone()
                    fflog(f'[KodiDB] found url: {row=}')
                break
            except OperationalError:
                if cnt + 1 < tries:
                    sleep(.1)
        fflog(f'[KodiDB] {select=}, {row=}')
        if row:
            fid, bid, fname, play_count, played_at, time_s, total_s = row
            if 'tmdb=' in fname:
                # FF2
                params = dict(parse_qsl(fname.partition('?')[2]))
                tmdb = int(params['tmdb'])
                imdb = params.get('imdb')
                if (season := params.get('season')) and (episode := params.get('episode')):
                    ref = MediaRef('show', VideoIds(tmdb=tmdb).ffid, int(season), int(episode))
                else:
                    ref = MediaRef('movie', VideoIds(tmdb=tmdb).ffid)
            else:
                # FF3
                if mch := self._rx_url_link.fullmatch(fname):
                    if (season := mch['season']) and (episode := mch['episode']):
                        ref = MediaRef('show', int(mch['id']), int(season), int(episode))
                    else:
                        ref = MediaRef('movie', int(mch['id']))
                    vid = ref.video_ids
                    tmdb, imdb = vid.tmdb, vid.imdb
                else:
                    ref = MediaRef('', 0)
                    tmdb = imdb = None
            return KodiVideoInfo(ref=ref, fid=fid, bid=bid, fname=fname, tmdb=tmdb, imdb=imdb,
                                 play_count=play_count or 0, played_at=parse_datetime(played_at), time_s=time_s or 0, total_s=total_s or 0)
        return None

    def get_kodi_dbid(self, ref: MediaRef, *, tries: int = 3) -> int:
        """Return kodi dbid for given `ref` or zero if not found."""
        rtype = ref.real_type
        vtype = self.KTYPES.get(rtype, rtype)  # kodi media type
        if vtype not in ('movie', 'episode', 'tvshow'):  # season is not in `uniqueid` table of kodi DB
            return 0
        if vtype == 'episode':
            vtype = 'tvshow'  # search for tvshow for episode first

        for cnt in range(tries):
            try:
                with self.cursor() as cur:
                    vid = ref.video_ids
                    # XX # first try to find in `files` (FF3 only)
                    # XX plugin = plugin_url.rstrip('/')
                    # XX cur.execute(f'''SELECT media_id FROM uniqueid WHERE strFilename = '{plugin}/play/{vtype}/{"/".join(ref.id_tuple)}' ''')
                    # XX row = cur.fetchone()
                    # second, try to find in library (in `uniqueid`)
                    where = ' OR '.join(f'''(type = '{service}' AND value = {value!r})'''
                                        for service, value in (('tmdb', vid.tmdb), ('imdb', vid.imdb), ('tvdb', vid.tvdb))
                                        if value)
                    if not where:
                        return 0  # no any supported service (ID type)
                    cur.execute(f'SELECT media_id FROM uniqueid WHERE {where}')
                    row = cur.fetchone()
                    if row:
                        if rtype == 'episode':  # ok, we have tvshow id, next we have to find episode id
                            cur.execute(f'SELECT idEpisode FROM epsiodes WHERE idShow = {row[0]} AND c12 = {ref.season} AND c13 = {ref.episode}')
                            if not (row := cur.fetchone()):
                                return 0  # no matching episode
                        return int(row[0])
                break
            except OperationalError:
                if cnt + 1 < tries:
                    sleep(.1)
        return 0

    def get_plays_for(self, items: Sequence[Union[MediaRef, FFItem]], *, tries: int = 3) -> Iterator[KodiVideoInfo]:
        """Get KodiVideoInfo for given media."""
        if refs := {item.ref for item in items}:
            yield from (vi for vi in self.get_plays(tries=tries) if vi.ref in refs)
        # refs = {item.ref for item in items}
        # if 0 < len(refs) <= 25:
        #     # TODO: maybe optimizations?
        #     def make_path(ref: MediaRef) -> str:
        #         if ref.type == 'show':
        #             return f'{plugin_url}/play/tvshow/' + '/'.join(map(str, ref.tv_tuple))
        #         if ref.type == 'movie':
        #             return f'{plugin_url}/play/movie/{ref.ffid}'
        #         return ''
        #     paths = tuple(path for ref in refs if (path := make_path(ref)))
        #     yield from (vi for vi in self.get_play_by_url(paths, tries=tries) if vi.ref in refs)
        # elif refs:
        #     yield from (vi for vi in self.get_plays(tries=tries) if vi.ref in refs)

    def get_play_by_kodi_id(self, type: Literal['movie', 'tvshow', 'show', 'season', 'episode'], id: int, *,
                            tries: int = 3, read_strm: bool = False) -> Optional[KodiVideoInfo]:
        """Return played or playing video by kodi id. Accepts FF and kodi types."""
        return self.rpc_get_play_by_kodi_id(type=type, id=id, tries=tries, read_strm=read_strm)
        return self.direct_get_play_by_kodi_id(type=type, id=id, tries=tries, read_strm=read_strm)

    def direct_get_play_by_kodi_id(self, type: Literal['movie', 'tvshow', 'show', 'season', 'episode'], id: int, *,
                                   tries: int = 3, read_strm: bool = False) -> Optional[KodiVideoInfo]:
        """Return played or playing video by kodi id. Accepts FF and kodi types."""
        vtype = self.VTYPES.get(type, cast(RefType, type))
        for cnt in range(tries):
            try:
                with self.cursor() as cur:
                    ref: Optional[MediaRef] = None
                    service = uid = None
                    tv_service = tv_uid = None
                    season = episode = None
                    strm = None
                    fname = ''
                    play_count = time_s = total_s = 0
                    played_at = ''
                    bid = fid = 0
                    if vtype == 'movie':
                        query = ('SELECT'
                                 '  u.type AS service, u.value AS uid, c22 AS strm,'
                                 '  f.playCount, f.lastPlayed, b.timeInSeconds, b.totalTimeInSeconds,'
                                 '  f.idFile, b.idBookmark'
                                 ' FROM movie as m'
                                 ' LEFT JOIN uniqueid AS u ON m.idMovie = u.media_id AND u.media_type = \'movie\''
                                 ' LEFT JOIN files AS f ON m.idFile = f.idFile'
                                 ' LEFT JOIN bookmark as b ON b.idFile = f.idFile'
                                 ' WHERE idMovie = {id}')
                        cur.execute(query.format(id=id))
                        if row := cur.fetchone():
                            service, uid, strm, play_count, played_at, time_s, total_s, fid, bid = row
                    elif vtype == 'show':
                        query = ('SELECT'
                                 '  ut.type AS tv_service, ut.value AS tv_uid'
                                 ' FROM tvshow AS s'
                                 ' LEFT JOIN uniqueid AS ut ON s.idShow = ut.media_id AND ut.media_type = \'tvshow\''
                                 ' WHERE idShow = {id}')
                        cur.execute(query.format(id=id))
                        if row := cur.fetchone():
                            service, uid = row
                    elif vtype == 'season':
                        query = ('SELECT'
                                 '  ut.type AS tv_service, ut.value AS tv_uid, z.idSeason as season'
                                 ' FROM seasons AS z'
                                 ' LEFT JOIN tvshow AS s ON z.idShow = s.idShow'
                                 ' LEFT JOIN uniqueid AS ut ON s.idShow = ut.media_id AND ut.media_type = \'tvshow\''
                                 ' WHERE z.idSeason = {id}')
                        cur.execute(query.format(id=id))
                        if row := cur.fetchone():
                            tv_service, tv_uid, season = row
                    elif vtype == 'episode':
                        query = ('SELECT'
                                 '  u.type AS service, u.value AS uid, ut.type AS tv_service, ut.value AS tv_uid,'
                                 '  e.c12 AS season, e.c13 AS epsiode, e.c18 AS strm,'
                                 '  f.playCount, f.lastPlayed, b.timeInSeconds, b.totalTimeInSeconds,'
                                 '  f.idFile, b.idBookmark'
                                 ' FROM episode as e'
                                 ' LEFT JOIN uniqueid AS u ON e.c20 = u.uniqueid_id'
                                 ' LEFT JOIN tvshow AS s ON e.idShow = s.idShow'
                                 ' LEFT JOIN uniqueid AS ut ON s.c12 = ut.uniqueid_id AND ut.media_type = \'tvshow\''
                                 ' LEFT JOIN files AS f ON e.idFile = f.idFile'
                                 ' LEFT JOIN bookmark as b ON b.idFile = f.idFile'
                                 ' WHERE idEpisode = {id}')
                        cur.execute(query.format(id=id))
                        if row := cur.fetchone():
                            service, uid, tv_service, tv_uid, season, episode, strm, play_count, played_at, time_s, total_s, fid, bid = row
                            season, episode = int(season), int(episode)
                    else:
                        return None
                    if tv_service and tv_uid:
                        try:
                            vid = VideoIds(**{tv_service: tv_uid})
                            ref = MediaRef.tvshow(vid.ffid, season, episode)
                        except TypeError:
                            pass
                    if not ref and service and uid:
                        try:
                            vid = VideoIds(**{service: uid})
                            ref = MediaRef(vtype, vid.ffid)  # denormalized
                        except TypeError:
                            return None
                    if not ref and strm:
                        # fallback: read strm file to get play link
                        try:
                            fname = load_strm_file(strm)
                        except IOError:
                            return None  # no ref and no strm (no FF link)
                        if vtype == 'movie':
                            rx = self._rx_movie_link
                        elif vtype == 'episode':
                            rx = self._rx_episode_link
                        else:
                            return None  # should never catch, there is no strm fiel for season or show
                        try:
                            fname = load_strm_file(strm)
                            if mch := rx.fullmatch(fname):
                                mtype = 'movie' if vtype == 'movie' else 'show'
                                if mch['ffid']:
                                    ref = MediaRef(mtype, *map(int, mch.group('ffid', 'season', 'episode')))
                                else:  # old (stable2023, FF2)
                                    ref = MediaRef(mtype, VideoIds(tmdb=int(mch['old_tmdb'])).ffid, *map(int, mch.group('old_season', 'old_episode')))
                        except IOError:
                            pass
                    elif read_strm and strm:
                        try:
                            fname = load_strm_file(strm)
                        except IOError:
                            pass

                    if ref:
                        return KodiVideoInfo(ref=ref, fid=fid, bid=bid, fname=fname,
                                             play_count=play_count, played_at=played_at, time_s=time_s, total_s=total_s)
            except OperationalError:
                if cnt + 1 < tries:
                    sleep(.1)
        return None

    def rpc_get_play_by_kodi_id(self, type: Literal['movie', 'tvshow', 'show', 'season', 'episode'], id: int, *,
                                tries: int = 3, read_strm: bool = False) -> Optional[KodiVideoInfo]:
        """Return played or playing video by kodi id. Accepts FF and kodi types."""
        vtype = self.VTYPES.get(type, cast(RefType, type))
        # method = self.RPC_LIST_METHODS[type]
        if vtype == 'movie':
            data = video_db.rpc_object('VideoLibrary.GetMovieDetails', params={'movieid': id},
                                       fields=['uniqueid', 'playcount', 'lastplayed', 'resume', 'runtime', 'file'])
        elif vtype == 'show':
            data = video_db.rpc_object('VideoLibrary.GetTVShowDetails', params={'tvshowid': id},
                                       fields=['uniqueid', 'playcount'])
        elif vtype == 'season':
            data = video_db.rpc_object('VideoLibrary.GetSeasonDetails', params={'seasonid': id},
                                       fields=['playcount', 'season', 'tvshowid'])
            # NOTE: VideoLibrary.GetSeasonDetails() has no `uniqueid`
            #       `uniqueid` param raises RPC error: array element at index 0 does not match
            if data and 'error' not in data and 'uniqueid' not in data:
                data['uniqueid'] = {}
        elif vtype == 'episode':
            data = video_db.rpc_object('VideoLibrary.GetEpisodeDetails', params={'episodeid': id},
                                       fields=['uniqueid', 'playcount', 'lastplayed', 'resume', 'runtime', 'season', 'episode', 'tvshowid', 'file'])
        else:
            return None
        if 'uniqueid' not in data:
            return None

        uniqueid = data['uniqueid']
        vid = VideoIds.from_ids(uniqueid)
        if vtype in ('season', 'episode'):
            tvdata = video_db.rpc_object('VideoLibrary.GetTVShowDetails', params={'tvshowid': data['tvshowid']}, fields=['uniqueid'])
            tv_uniqueid = tvdata['uniqueid']
            tv_vid = VideoIds.from_ids(tv_uniqueid)
            ref = MediaRef.tvshow(tv_vid.ffid, data.get('season'), data.get('episode'))
            tmdb, imdb = int_on_none(tv_uniqueid.get('tmdb')), tv_uniqueid.get('imdb')
        else:
            ref = MediaRef(vtype, vid.ffid)
            tmdb, imdb = int_on_none(uniqueid.get('tmdb')), uniqueid.get('imdb')

        time_s = total_s = 0
        if resume := data.get('resume'):
            time_s = resume['position']
            total_s = resume['total']
        fflog(f'_____DB_____\n{data = }')
        return KodiVideoInfo(ref=ref, tmdb=tmdb, imdb=imdb, fname=data.get('file', ''),
                             play_count=data.get('playcount', 0), played_at=parse_datetime(data.get('lastplayed', '')),
                             time_s=time_s, total_s=total_s)

    # WTF !!!
    # Not a list, just an object and there is no ID !!!
    # {'id': 1, 'jsonrpc': '2.0', 'result': [{'name': 'VideoPlayer', 'playsaudio': True, 'playsvideo': True, 'type': 'video'}]}
    def get_players(self) -> Sequence[int]:
        """Return list of ID of available video players."""
        x = self.rpc_list('Player.GetActivePlayers', params={'media': 'video'})
        fflog(f'Player.GetActivePlayers: {json.dumps(x, indent=2)}')
        return ...

    def get_player_item(self) -> Sequence[int]:
        """Return current player item."""
        fields = []
        fields += ['uniqueid', 'playcount', 'lastplayed', 'resume', 'runtime', 'file']
        fields += ['uniqueid', 'playcount']
        fields += ['playcount', 'season', 'tvshowid']
        fields += ['uniqueid', 'playcount', 'lastplayed', 'resume', 'runtime', 'season', 'episode', 'tvshowid', 'file']
        x = self.rpc_list('Player.GetItem', params={'playerid': 1}, fields=list(set(fields)))
        fflog(f'Player.GetItem: {json.dumps(x, indent=2)}')
        return ...

    def get_library(self,
                    media_type: Optional[Literal['movie', 'show', 'season', 'episode']],
                    *,
                    remove_duplicates: bool = False,
                    deep: bool = False,
                    ) -> Iterable[KodiVideoInfo]:
        """Get Kodi library movies, ... (rpc)."""

        def parse(media: Literal['movie', 'show', 'season', 'episode'], it: JsonData) -> KodiVideoInfo:
            if media == 'movie':
                ffid = VideoIds.from_ids(it['uniqueid']).ffid
            elif media == 'show':
                ffid = VideoIds.from_ids(it['uniqueid']).ffid
                tvs[it['tvshowid']] = ffid
            else:  # season, episode
                ffid = tvs[it['tvshowid']]
                media = 'show'  # main type
            ref = MediaRef(media, ffid, season=it.get('season'), episode=it.get('episode'))
            uniqueid = it.get('uniqueid', {})
            resume = it.get('resume', {})
            return KodiVideoInfo(ref=ref,
                                 fname=it.get('file', ''),
                                 play_count=it.get('playcount', 0),
                                 played_at=parse_datetime(it.get('lastplayed', '')),
                                 time_s=resume.get('position', 0),
                                 total_s=resume.get('total', 0),
                                 tmdb=int_on_none(uniqueid.get('tmdb')),
                                 imdb=uniqueid.get('imdb', ''),
                                 label=it.get('label'),
                                 library=True,
                                 )

        from .debug import logtime
        with logtime(name='kodi db'):
            fields = {
                'movie': ('playcount', 'lastplayed', 'resume', 'uniqueid', 'file'),
                'show': ('playcount', 'lastplayed', 'uniqueid', 'file'),
                'season': ('tvshowid', 'season', 'playcount'),  # Kodi seasons reject "file"
                'episode': ('tvshowid', 'season', 'episode', 'playcount', 'lastplayed', 'resume', 'uniqueid', 'file'),
            }
            count = {}
            if not media_type:
                types = ('movie', 'show', 'season', 'episode')
            elif media_type in ('show', 'season', 'episode'):
                if deep:
                    types = ('show', 'season', 'episode')
                elif media_type == 'episode':
                    types = ('show', 'season', 'episode')
                elif media_type == 'season':
                    types = ('show', 'season')
                else:
                    types = ('show',)
            else:
                types = (media_type,)
            items: dict[MediaRef, JsonData] = {}
            tvs: dict[int, int] = {}  # tvshowid → ffid
            for media in types:
                with logtime(name=f' - {media}'):
                    data = self.rpc_list(self.RPC_LIST_METHODS[media], fields=fields[media])
                    count[media] = len(data)
                    # fflog(f'{self.RPC_LIST_METHODS[media]}: {json.dumps(data, indent=2)}')
                    if data:
                        fflog(f'{media}[0]: {json.dumps(data[0], indent=2)}')
                    for it in data:
                        yield parse(media, it)
            print(items.keys())

        fflog(f'Number of items {sum(count.values())}, {count}')
        return ()
        return [KodiVideoInfo(ref=MediaRef('movie', VideoIds.from_ids(ids).ffid),
                              fname=it['file'],
                              play_count=it['playcount'],
                              played_at=parse_datetime(it['lastplayed']),
                              time_s=it['resume']['position'],
                              total_s=it['resume']['total'],
                              tmdb=int(ids.get('tmdb') or 0),
                              imdb=ids.get('imdb', ''),
                              library=True,
                              ) for it in data if (ids := it['uniqueid'])]

    def get_library_dict(self,
                         media_type: Optional[Literal['movie', 'show', 'season', 'episode']],
                         *,
                         remove_duplicates: bool = False,
                         deep: bool = False,
                         ) -> dict[MediaRef, KodiVideoInfo]:
        """Get Kodi library media, ... (rpc) as dict."""
        return {it.ref: it for it in self.get_library(media_type=media_type,
                                                      remove_duplicates=remove_duplicates, deep=deep)}

    def get_library_ffitems(self,
                            media_type: Optional[Literal['movie', 'show', 'season', 'episode']],
                            *,
                            remove_duplicates: bool = False,
                            deep: bool = False,
                            strict: bool = True,
                            ) -> Sequence[FFItem]:
        """Get Kodi library media, ... (rpc) as ffitems."""
        items = {it.ref: it.ffitem() for it in self.get_library(media_type=media_type,
                                                                remove_duplicates=remove_duplicates, deep=deep)}
        for ref, ff in items.items():
            if ref.season is not None:
                ff.show_item = items.get(ref.show_ref)  # type: ignore[reportArgumentType]
                if ref.episode is not None:
                    ff.season_item = items.get(ref.season_ref)  # type: ignore[reportArgumentType]
        if strict and media_type:
            return tuple(ff for ref, ff in items.items() if ref.real_type == media_type)
        return tuple(items.values())


def load_strm_file(path: str) -> str:
    """Load STRM file."""
    with File(path) as f:
        content = f.read().strip()
    for line in content.splitlines():
        if line[:1] != '#':  # skip kodi property, see: https://kodi.wiki/view/Internet_video_and_audio_streams#Property_support:
            return line
    return ''


video_db = KodiVideoDB()


if __name__ == '__main__':
    def main_test():
        from pprint import pprint
        from ..ff.cmdline import DebugArgumentParser, parse_ref

        p = DebugArgumentParser(dest='cmd')
        p.add_argument('--dbpath', type=Path, default=Path('~/.kodi/userdata/Database').expanduser() / f'MyVideos{vdb_ver}.db',
                       help='path to Kodi MyVideos.db')
        # p.add_argument('--rpc-port', type=int, default=9090, help='Kodi JSON-RPC port')
        with p.with_subparser('ref') as pp:
            pp.add_argument('media', nargs='?', type=parse_ref, help='media: movie/ID or show/ID/SEASON/EPISODE')
        with p.with_subparser('id') as pp:
            pp.add_argument('type', choices=('movie', 'show', 'season', 'episode'), help='kodi media type')
            pp.add_argument('id', type=int, help='kodi dbid')
            pp.add_argument('--read-strm', action='store_true', help='force read strm file')
        with p.with_subparser('lib') as pp:
            pp.add_argument('type', nargs='?', choices=('movie', 'show', 'season', 'episode'), help='kodi media type')
            pp.add_argument('--remove-duplicates', action='store_true', help='remove duplicates from library')
        args = p.parse_args()

        kodidb = KodiVideoDB(path=args.dbpath)
        if args.cmd == 'ref':
            ref: MediaRef = args.media
            if ref:
                print(kodidb.get_play(ref))
            else:
                pprint(kodidb.get_plays())
        elif args.cmd == 'id':
            print(kodidb.get_play_by_kodi_id(args.type, args.id, read_strm=args.read_strm))
        elif args.cmd == 'lib':
            lib = tuple(kodidb.get_library(media_type=args.type, remove_duplicates=args.remove_duplicates))
            print(lib)
            # print([it for it in lib if it.time_s])
            # print([it for it in lib if it.play_count])

    main_test()
