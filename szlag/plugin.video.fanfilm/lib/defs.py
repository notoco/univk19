"""
Some global object definitions.

Those classes are independent of rest of code.
Can be safety used in const.py.
"""

import re
from sys import maxsize
from datetime import datetime
from enum import Enum
from typing import Optional, Union, Any, Tuple, List, Dict, Mapping, Iterable, Iterator, TypeVar, NamedTuple, TYPE_CHECKING
from typing import overload, Sequence
# from collections.abc import Sequence
from typing_extensions import Self, Literal, TypeAlias, Protocol
from typing_extensions import TypedDict, NotRequired
from attrs import frozen, field
from .ff.types import JsonData
from .ff.calendar import make_datetime
# from .ff.calendar import utc_timestamp
# from .ff.tricks import namedtuple_base
if TYPE_CHECKING:
    from .ff.item import FFItem


T = TypeVar('T')

#: Main reference type.
RefType: TypeAlias = Literal['', 'movie', 'show', 'season', 'episode', 'person', 'collection',
                             'company', 'keyword', 'network',
                             # extra types (has no tmdb details)
                             'genre', 'language', 'country', 'list']
#: General media (item) content type.
MainMediaType: TypeAlias = Literal['movie', 'show']
MainMediaTypeList: TypeAlias = Literal['movie', 'show', 'movie,show']
#: General media (item) content type.
MediaType: TypeAlias = Literal['movie', 'show', 'season', 'episode']
#: Dict with media data
MediaDict: TypeAlias = Dict[str, Any]
#: Video objects to play.
MediaPlayType: TypeAlias = Literal['movie', 'episode']
#: Seatch type.
SearchType: TypeAlias = Literal['all', 'multi', 'movie', 'show', 'person', 'collection', 'company', 'keyword']
#: Generic reference.
FFRef = Union['MediaRef', 'FFItem']


#: Factor for denormalized season ffid.
SHOW_SEASON_COMBINE_FACTOR: int = 100


#: Dict with IDs (like in trakt.tv).
class IdsDict(TypedDict):
    tmdb: NotRequired[Optional[int]]
    imdb: NotRequired[Optional[str]]
    trakt: NotRequired[Optional[int]]
    tvdb: NotRequired[Optional[int]]
    slug: NotRequired[Optional[str]]


class VideoIds(NamedTuple):
    """
    Simple TMDB or IMDB or TRAKT IDs.

    This object can generate `vid` (video id). Typicaly it's just tmdb id.

    `vid` is used as FFID in Kodi API.
    """

    # The TMDB ID.
    tmdb: Optional[int] = None
    # The IMDB ID.
    imdb: Optional[str] = None
    # The Trakt ID.
    trakt: Optional[int] = None
    # The TVDB ID.
    tvdb: Optional[int] = None
    # The MDBList ID.
    mdblist: Optional[int] = None
    # Volatile (fake) ID, only for one FF session.
    volatile: Optional[int] = None
    # Kodi internal FFID.
    kodi_dbid: Optional[int] = None

    # --- NOTE: following class vars can NOT use hint type. ---
    #: Max Kodi DBID number.
    KODI_DBID_MAX = 98_999_999
    #: Valid Kodi DBID range (to check, zero is in number range KODI, but is not valid).
    KODI_DBID = range(1, KODI_DBID_MAX + 1)
    #: Kodi DB internal IDs.
    KODI = range(0, KODI_DBID_MAX + 1)
    #: Tmdb id range.
    TMDB = range(100_000_000, 999_000_000)
    #: Fake, temporary, dynamic ID, used for seasons only.
    VOLATILE = range(999_000_000, 1_000_000_000)
    #: Imdb id range.
    IMDB = range(1_000_000_000, 2_000_000_000)
    #: Trakt id range.
    TRAKT = range(2_000_000_000, 2_147_482_000)  # fit in 31 bit
    #: TvDB id range.
    TVDB = range(3_000_000_000, 4_000_000_000)  # not used
    #: dbList id range.
    MDBLIST = range(4_000_000_000, 5_000_000_000)

    def is_kodi(self) -> bool:
        """Return True if internal Kodi FFID."""
        return self.kodi_dbid is not None

    def is_tmdb(self) -> bool:
        """Return True if TMDB."""
        return self.tmdb is not None

    def is_imdb(self) -> bool:
        """Return True if IMDB."""
        return self.imdb is not None

    def is_trakt(self) -> bool:
        """Return True if Trakt."""
        return self.trakt is not None

    def is_tvdb(self) -> bool:
        """Return True if TvDB."""
        return self.tvdb is not None

    def is_mdblist(self) -> bool:
        """Return True if MDBList."""
        return self.mdblist is not None

    def is_volatile(self) -> bool:
        """Return True if FF volatile ID."""
        return self.volatile is not None

    def ff_id(self) -> int:
        """Generate video ID form VideoIds imdb / tmdb ID."""
        return self.make_ffid(imdb=self.imdb, tmdb=self.tmdb, trakt=self.trakt, tvdb=self.tvdb, mdblist=self.mdblist, volatile=self.volatile, kodi_dbid=self.kodi_dbid)

    @property
    def ffxid(self) -> int:
        """Generate video ID form VideoIds imdb / tmdb ID."""
        return self.make_ffid(imdb=self.imdb, tmdb=self.tmdb, trakt=self.trakt, tvdb=self.tvdb, mdblist=self.mdblist, volatile=self.volatile, kodi_dbid=self.kodi_dbid)

    @property
    def ffid(self) -> int:
        """Generate video ID form VideoIds imdb / tmdb ID."""
        return self.make_ffid(imdb=self.imdb, tmdb=self.tmdb, trakt=self.trakt, tvdb=self.tvdb, mdblist=self.mdblist, volatile=self.volatile, kodi_dbid=self.kodi_dbid)

    def ids(self) -> IdsDict:
        """Create dict with existing IDs."""
        ids: IdsDict = {}
        if self.trakt:
            ids['trakt'] = self.trakt
        if self.tmdb:
            ids['tmdb'] = self.tmdb
        if self.imdb:
            ids['imdb'] = self.imdb
        if self.tvdb:
            ids['tvdb'] = self.tvdb
        # if self.mdblist:
        #     ids['mdblist'] = self.tvdb
        return ids

    def kodi_ids(self) -> Mapping[str, str]:
        """Create dict with existing IDs in kodi setUniqueIDs() format."""
        ids = {'ffid': str(self.ffid)}
        if self.imdb:
            ids['imdb'] = str(self.imdb)
        if self.tmdb:
            ids['tmdb'] = str(self.tmdb)
        if self.trakt:
            ids['trakt'] = str(self.trakt)
        if self.tvdb:
            ids['tvdb'] = str(self.tvdb)
        if self.mdblist:
            ids['mdblist'] = str(self.mdblist)
        if self.volatile:
            ids['ff/volatile'] = str(self.tvdb)
        if self.kodi_dbid:
            ids['dbid'] = str(self.kodi_dbid)
        return ids

    def service(self) -> Optional[str]:
        """Return main service name (service with existing ID)."""
        if self.tmdb:
            return 'tmdb'
        if self.imdb:
            return 'imdb'
        if self.trakt:
            return 'trakt'
        if self.tvdb:
            return 'tvdb'
        if self.mdblist:
            return 'mdblist'
        if self.volatile:
            return 'ff/volatile'
        if self.kodi_dbid:
            return 'dbid'
        return None

    def ref(self, type: RefType) -> 'MediaRef':
        """Return media reference."""
        return MediaRef(type, self.ff_id())

    @property
    def value(self) -> Union[None, str, int]:
        """Return ID whathever it is."""
        if self.tmdb is not None:
            return self.tmdb
        if self.imdb is not None:
            return self.imdb
        if self.volatile is not None:
            return self.volatile + self.VOLATILE.start
        if self.kodi_dbid is not None:
            return self.kodi_dbid
        # Trakt is ignored, it does NOT differ to TMDB ID.
        return None

    def __str__(self) -> str:
        """ID as string (whathever ID is)."""
        return str(self.value or '')

    @classmethod
    def from_ids(cls, ids: JsonData) -> 'VideoIds':
        """Generate video IDs from ids dict."""
        return cls(tmdb=ids.get('tmdb'), imdb=ids.get('imdb'), trakt=ids.get('trakt'), tvdb=ids.get('tvdb'))

    @classmethod
    def from_tmdb(cls, item: JsonData) -> 'VideoIds':
        """Generate video IDs from TMDB item (`id` and `external_ids`)."""
        ids = item.get('external_ids') or {}
        return cls(tmdb=item['id'], imdb=ids.get('imdb_id'), tvdb=ids.get('tvdb_id'))

    @classmethod
    def ffid_from_tmdb(cls, item: JsonData) -> int:
        """Generate ffid from TMDB item (`id` and `external_ids`)."""
        ids = item.get('external_ids') or {}
        return cls.make_ffid(tmdb=item['id'], imdb=ids.get('imdb_id'), tvdb=ids.get('tvdb_id'))

    @classmethod
    def ffid_from_tmdb_id(cls, value: int) -> int:
        """Generate ffid from TMDB ID."""
        return cls.make_ffid(tmdb=value)

    @classmethod
    def from_kodi_dbid(cls, value: Union[int, str]) -> 'VideoIds':
        """Generate video IDs from Kodi DBID value."""
        value = int(value or '0')
        if value > 0:
            return cls(kodi_dbid=value)
        return cls()

    @classmethod
    def ffid_from_kodi_dbid(cls, value: Union[int, str]) -> int:
        """Generate ffid from Kodi DBID value."""
        value = int(value or '0')
        if value > 0:
            return cls.KODI.start + value
        return 0

    @classmethod
    def make_ffid(cls, *,
                  tmdb: Optional[int] = None,
                  imdb: Optional[str] = None,
                  trakt: Optional[int] = None,
                  tvdb: Optional[int] = None,
                  mdblist: Optional[int] = None,
                  volatile: Optional[int] = None,
                  kodi_dbid: Optional[int] = None,
                  ) -> int:
        """Generate video ID form imdb / tmdb ID."""
        if tmdb:
            return cls.TMDB.start + int(tmdb)
        elif imdb:
            factor = len(cls.IMDB)
            tt = int(f'9{imdb[2:]}')
            if tt >= 99 * factor // 10:
                from .ff.log_utils import error
                error(f'IMDB ID {imdb!r} is out of range')
                return 0
            return cls.IMDB.start + tt % factor
        elif trakt:
            return cls.TRAKT.start + int(trakt)
        elif tvdb:
            return cls.TVDB.start + int(tvdb)
        elif mdblist:
            return cls.MDBLIST.start + int(mdblist)
        elif volatile:
            return cls.VOLATILE.start + int(volatile)
        elif kodi_dbid:
            return cls.KODI.start + int(kodi_dbid)
        return 0

    @classmethod
    def from_ffid(cls, ffid: int) -> Optional['VideoIds']:
        """Recover imdb / tmdb ID from video ID."""
        if ffid is None or not isinstance(ffid, int):
            return None
        if ffid in cls.TMDB:
            return cls(tmdb=cls.TMDB.index(ffid))
        if ffid in cls.IMDB:
            value_digit_length = len(str(len(cls.IMDB) - 1))  # Number of digits for value part.
            tt = str(cls.IMDB.index(ffid))
            if len(tt) == value_digit_length and tt[0] != '9':
                return cls(imdb=f'tt{tt}')
            if tt[0] == '9':
                return cls(imdb=f'tt{tt[1:]}')
            return cls(imdb=f'tt{tt:0>{value_digit_length}}')
        if ffid in cls.VOLATILE:
            return cls(volatile=cls.VOLATILE.index(ffid))
        if ffid in cls.TRAKT:
            return cls(trakt=cls.TRAKT.index(ffid))
        if ffid in cls.TVDB:
            return cls(tvdb=cls.TVDB.index(ffid))
        if ffid in cls.MDBLIST:
            return cls(mdblist=cls.MDBLIST.index(ffid))
        if ffid in cls.KODI:
            return cls(kodi_dbid=cls.KODI.index(ffid))
        return None

    @classmethod
    def tmdb_id(cls, ffid: int) -> int:
        """Return TMDB id, 0 if ffid is not TMDB."""
        return cls.TMDB.index(ffid) if ffid in cls.TMDB else 0


_rx_mediaref_format: re.Pattern = re.compile(r'(?P<align>[<>^])?(?P<width>\d+)?(?P<code>\w)?')


class MediaRef(NamedTuple):
    """
    Reference to media (video).

    Movies:
        - type="movie" and `ffid`.
    Tv-show:
        - type="show" and `ffid`.
    Season:
        - type="show", tvshow in `ffid` and `season`.
        - type="season" and season `ffid` (denormalized, should not be used).
    Episode:
        - type="show", tvshow in `ffid`, `season` and `episode`.
        - type="episode" and episode `ffid` (denormalized, should be avoided, used in kodi monitor).

    Examples:
        - ('movie', MOVIE_ID, None, None)
        - ('show', SHOW_ID, None, None)
        - ('show', SHOW_ID, SEASON_NUM, None)
        - ('show', SHOW_ID, SEASON_NUM, EPISODE_NUM)

    Denormalized examples, should be avoided:
        - ('season', SEASON_ID, None, None)
        - ('episode', EPISODE_ID, None, None)
    """

    #: Media type.
    type: RefType
    #: Media ID (ffid).
    ffid: int
    #: Season number if season or episode is pointed by tvshow in `ffid` with `type` == 'show'.
    season: Optional[int] = None
    #: Episode number if episode is pointed by tvshow in `ffid` with `type` == 'show'.
    episode: Optional[int] = None

    def as_dict(self) -> Dict[str, Any]:
        """Return media ref as dict."""
        return self._asdict()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MediaRef':
        """New ref from dict data."""
        return cls(**data)

    def __to_json__(self) -> Dict[str, Any]:
        """Return media ref as json (simple dict)."""
        if self.episode is not None:
            return self._asdict()
        if self.season is not None:
            return {'type': self.type, 'ffid': self.ffid, 'season': self.season}
        return {'type': self.type, 'ffid': self.ffid}

    @classmethod
    def __from_json__(cls, data: Dict[str, Any]) -> 'MediaRef':
        """New ref from json dict."""
        try:
            return cls(**data)
        except TypeError:
            return cls(*data)  # type: ignore  -- falback, create from (named) tuple

    @property
    def is_normalized(self) -> bool:
        """Return True if ref is normalized, used movie or tvshow only."""
        return self.type not in ('season', 'episode')

    @property
    def real_type(self) -> RefType:
        """Return media type based on IDs and numbers."""
        if self.type == 'show':
            if self.episode is not None:
                return 'episode'
            if self.season is not None:
                return 'season'
        return self.type or ''

    @classmethod
    def from_tmdb(cls, type: RefType, tmdb: int, season: Optional[int] = None, episode: Optional[int] = None) -> 'MediaRef':
        """Create MediaRef from TMDB id."""
        return cls(type, tmdb + VideoIds.TMDB.start, season, episode)

    @property
    def main_type(self) -> str:
        """Return main type based on IDs: "movie" or "show" (for tv, season, episode)."""
        return self.type or ''

    @property
    def is_movie(self) -> bool:
        """Return True is ref is a movie."""
        return self.type == 'movie'

    @property
    def is_show(self) -> bool:
        """Return True is ref is a show."""
        return self.type == 'show' and self.season is None and self.episode is None

    @property
    def is_season(self) -> bool:
        """Return True is ref is a season (only normalized)."""
        return self.type == 'show' and self.season is not None and self.episode is None

    @property
    def is_episode(self) -> bool:
        """Return True is ref is an episode (only normalized)."""
        return self.type == 'show' and self.season is not None and self.episode is not None

    @property
    def is_volatile(self) -> bool:
        """Return True is ref's FFIDs is volatile."""
        return bool(self.ffid) and self.ffid in VideoIds.VOLATILE

    @property
    def is_container(self) -> bool:
        """Return True is ref is container type (could have children) like show and season."""
        return (self.type == 'show' and self.episode is None) or self.type == 'collection'

    def denormalize(self) -> Optional['MediaRef']:
        """Denormalize, it's possible only for seasons and only for TMDB."""
        return None  # Kodi has not enough bits for FFID to handle denormalized season FFID.

    def normalize(self) -> Optional['MediaRef']:
        """Normalize, it's possible only for seasons and only for TMDB."""
        if self.is_normalized:
            return self
        if self.type == 'season' and self.season is None and self.episode is None and self.ffid and self.ffid < 0:
            show, season = divmod(self.ffid, SHOW_SEASON_COMBINE_FACTOR)
            return MediaRef('show', show, season)
        return None

    def try_normalize(self) -> 'MediaRef':
        """Try to normalize, it's possible only for seasons and only for TMDB."""
        return self.normalize() or self

    @property
    def id_tuple(self) -> Tuple[int, ...]:
        """Return variable-length tuple for [media] or [show[,season[,episode]]]."""
        if self.type == 'show':
            if self.season is not None:
                if self.episode is not None:
                    return (self.ffid, self.season, self.episode)
                return (self.ffid, self.season)
            return (self.ffid,)
        return (self.ffid,)

    @property
    def tv_tuple(self) -> Tuple[int, ...]:
        """Return variable-length tuple for tvshow, season or episode: [show[,season[,episode]]]."""
        if self.type == 'show':
            if self.season is not None:
                if self.episode is not None:
                    return (self.ffid, self.season, self.episode)
                return (self.ffid, self.season)
            return (self.ffid,)
        return ()

    @property
    def tmdb_tv_tuple(self) -> Tuple[int, ...]:
        """Return variable-length tuple for tvshow, season or episode: [show[,season[,episode]]] with TMDB id."""
        if self.type == 'show':
            if self.season is not None:
                if self.episode is not None:
                    return (self.tmdb_id, self.season, self.episode)
                return (self.tmdb_id, self.season)
            return (self.tmdb_id,)
        return ()

    @property
    def tv_ffid(self) -> Optional[int]:
        """Return tv-show ffid for shows, season, episode."""
        if self.type == 'show':
            return self.ffid
        return None

    @property
    def tmdb_tv_ffid(self) -> Optional[int]:
        """Return tv-show ffid for shows, season, episode with TMDB id."""
        if self.type == 'show':
            return self.tmdb_id
        return None

    @property
    def video_ids(self) -> VideoIds:
        """Return VideoIds()."""
        vid = VideoIds.from_ffid(self.ffid)
        if vid is None:
            return VideoIds()
        return vid

    @property
    def ref(self) -> 'MediaRef':
        """Return ref (just itself). Same property as FFItem.ref."""
        return self

    @property
    def tmdb_id(self) -> int:
        """Return TMDB id, 0 if ffid is not TMDB."""
        return VideoIds.TMDB.index(self.ffid) if self.ffid in VideoIds.TMDB else 0

    @property
    def role(self) -> str:
        """Return empty role. Same property as FFItem.role."""
        return ''

    def to_sql_ref(self) -> 'XMediaRef':
        """Return media ref for SQL, without None (ffid = 0, season and episode = -1)."""
        return XMediaRef(self.type or '', self.ffid or 0, self.sql_season, self.sql_episode)

    @property
    def sql_ref(self) -> 'XMediaRef':
        """Return media ref for SQL, without None (ffid = 0, season and episode = -1)."""
        return XMediaRef(self.type or '', self.ffid or 0, self.sql_season, self.sql_episode)

    @property
    def xref(self) -> 'XMediaRef':
        """Return media ref for SQL, without None (ffid = 0, season and episode = -1)."""
        return XMediaRef(self.type or '', self.ffid or 0, self.sql_season, self.sql_episode)

    @property
    def sql_ffid(self) -> int:
        """Return media FFID for SQL. 0 if missing (for season and episode)."""
        if self.season is None and self.episode is None:
            return self.ffid or 0
        return 0

    @property
    def sql_main_ffid(self) -> int:
        """Return parent FFID (movie itself or tvshow for rest) for SQL."""
        if self.type in ('movie', 'show'):
            return self.ffid or 0
        return 0

    @property
    def sql_tv_ffid(self) -> int:
        """Return tvshow FFID for SQL (show, season and episode). 0 if missing (for movie)."""
        if self.type == 'show':
            return self.ffid or 0
        return 0

    @property
    def sql_season(self) -> int:
        """Return season number for SQL, -1 if None."""
        return -1 if self.season is None else self.season

    @property
    def sql_episode(self) -> int:
        """Return episode number for SQL, -1 if None."""
        return -1 if self.episode is None else self.episode

    @classmethod
    def from_sql_ref(cls, ref: 'MediaRef') -> Self:
        """Return media ref for SQL, without None (ffid = 0, season and episode = -1)."""
        season = None if ref.season == -1 else ref.season
        episode = None if ref.episode == -1 else ref.episode
        return cls(ref.type, ref.ffid, season, episode)

    @classmethod
    def movie(cls, ffid: int) -> 'MediaRef':
        """Create movie ref."""
        return cls('movie', ffid)

    @classmethod
    def tvshow(cls, ffid: int, season: Optional[int] = None, episode: Optional[int] = None) -> 'MediaRef':
        """Create tvshow ref."""
        return cls('show', ffid, season, episode)

    @classmethod
    def person(cls, ffid: int) -> 'MediaRef':
        """Create person ref."""
        return cls('person', ffid)

    def ref_list(self) -> Tuple['MediaRef', ...]:
        """Create media ref list. Ex. tvshow ref for season or episode."""
        if self.season is not None:
            if self.episode is not None:
                return (self, MediaRef('show', self.ffid, self.season), MediaRef('show', self.ffid))
            return (self, MediaRef('show', self.ffid))
        return (self,)

    @property
    def main_ref(self) -> 'MediaRef':
        """Return main ref (show ref for show, season and episode)."""
        return MediaRef(self.type, self.ffid)

    @property
    def show_ref(self) -> Optional['MediaRef']:
        """Return show ref for show, season and episode."""
        if self.type == 'show':
            return MediaRef(self.type, self.ffid)
        return None

    @property
    def season_ref(self) -> Optional['MediaRef']:
        """Return seasons ref for season and episode."""
        if self.type == 'show' and self.season is not None:
            return MediaRef(self.type, self.ffid, self.season)
        return None

    def parents(self) -> Iterator['MediaRef']:
        """Return all parent refs, ex. show and season ref for episode."""
        if self.type == 'show':
            if self.episode is not None:
                yield MediaRef(self.type, self.ffid, self.season)
            if self.season is not None:
                yield MediaRef(self.type, self.ffid)

    def with_forced_type(self, type: RefType) -> 'MediaRef':
        """Return copy with new type replaced."""
        return MediaRef(type, self.ffid, self.season, self.episode)

    def with_season(self, season: int) -> 'MediaRef':
        """Return copy with season replaced."""
        return MediaRef(self.type, self.ffid, season=season, episode=None)

    def with_episode(self, episode: int) -> 'MediaRef':
        """Return copy with episode replaced."""
        return MediaRef(self.type, self.ffid, season=self.season, episode=episode)

    @classmethod
    def from_slash_string(cls, string: str) -> Optional['MediaRef']:
        """Return media ref from string "type/ffid/..."."""
        if string and '/' in string:
            typ, *ids = string.split('/')
            vtype: RefType = typ   # type: ignore
            try:
                return cls(vtype, *map(int, ids[:3]))
            except ValueError:
                pass
        return None

    def __format__(self, fmt: str, *, default: str = 'a') -> str:
        """Return ref IDs as URL path."""
        mch = _rx_mediaref_format.fullmatch(fmt)
        assert mch
        align = mch['align'] or '<'
        width = int(mch['width'] or -1)
        code = mch['code'] or ''
        if not code:
            code = default
        if code == 'a':
            out = '/'.join(map(str, (self.type, *(self.tv_tuple or (self.ffid,)))))
        elif code == 'i':
            if (tt := self.tv_tuple):
                out = '/'.join(map(str, tt))
            else:
                out = str(self.ffid)
        else:
            raise ValueError(f'Unsupported MediaRef format {fmt!r}')
        if width > len(out):
            out = f'{out:{align}{width}}'
        return out


class XMediaRef(MediaRef):
    """Helper. Media reference for SQL (without None), ORM hacking."""
    __slots__ = ()
    _field_defaults = {'season': -1, 'episode': -1}
    __annotations__ = {**MediaRef.__annotations__, **{'season': int, 'episode': int}}


class MediaRefWithNoType(MediaRef):
    """Just MediaRef but with not type defined. Used in indexers' routing (no type, only numbers)."""

    def __format__(self, fmt: str, *, default: str = 'i') -> str:
        return super().__format__(fmt, default=default)


class ItemList(List[T]):
    """TMDB item list with pagination info. Initialize with page-only items."""

    def __init__(self, *args, page: int, page_size: int = 0, total_pages: int, total_results: int = 0) -> None:
        super().__init__(*args)
        #: Current page number.
        self.page: int = page
        #: Page size.
        self.page_size: int = page_size
        #: Total number of pages.
        self.total_pages: int = total_pages
        #: Total number of items.
        self.total_results: int = total_results

    def next_page(self) -> Optional[int]:
        """Return next page number or None."""
        if self.page and self.total_pages and self.page < self.total_pages:
            return self.page + 1
        return None

    def set_item_count(self, count, page_size: int = 25):
        """Set number of items and pages."""
        self.page_size = page_size
        self.total_results = count
        self.total_pages = (count + page_size - 1) // page_size

    @classmethod
    def empty(cls) -> Self:
        """Return new empty item list."""
        return cls(page=0, page_size=0, total_pages=0, total_results=0)

    @classmethod
    def single(cls, items: Iterable[T]) -> Self:
        """Return new single page item list."""
        lst = cls(items, page=1, total_pages=1, total_results=0)
        lst.page_size = lst.total_results = len(lst)
        return lst

    @classmethod
    def from_list(cls, items: 'Union[Iterable[T], Pagina, ItemList]', pages: 'Union[Pagina, ItemList, None]' = None) -> Self:
        """Return new item list from another list. Keep pages info."""
        if pages is None:
            if TYPE_CHECKING:
                assert isinstance(items, (Pagina, ItemList))
            pages = items
        return cls(items, page=pages.page, page_size=pages.page_size,
                   total_pages=pages.total_pages, total_results=pages.total_results)

    def with_content(self, items: Iterable[T]) -> 'ItemList':
        """Create new list with content changed (with the same pages)."""
        lst = self.__class__(items, page=self.page, total_pages=self.total_pages)
        lst.page_size = lst.total_results = len(lst)
        return lst


class Pagina(Sequence[T]):
    """Pagination object to split item list into pages. Initialize with full item list. Pages count from one."""

    def __init__(self, items: Iterable[T], *, page: int = 1, limit: int = 20):
        if not isinstance(items, Sequence):
            items = tuple(items)
        #: Full item  list.
        self.items: Sequence[T] = items
        #: Current page number.
        self.page: int = max(page, 1)
        #: Page size.
        self._limit: int = limit

    @property
    def limit(self) -> int:
        """Size of page."""
        return self._limit

    @property
    def page_size(self) -> int:
        """Size of page."""
        return self._limit

    @property
    def total_pages(self) -> int:
        """Total number of pages."""
        return (len(self.items) + self._limit - 1) // self._limit

    @property
    def total_results(self) -> int:
        """Total number of items."""
        return len(self.items)

    def next_page(self) -> Optional[int]:
        """Return next page number or None."""
        total_pages = self.total_pages
        if self.page and total_pages and self.page < total_pages:
            return self.page + 1
        return None

    def start(self) -> int:
        """Return begin of the view (view first index in items space)."""
        if self.page < 1:
            return 0
        # Pages count from one.
        return min((self.page - 1) * self._limit, len(self.items))

    def end(self) -> int:
        """Return end of the view (view last index + 1 in items space)."""
        if self.page < 1:
            return 0
        # Pages count from one.
        return min((self.page + 0) * self._limit, len(self.items))

    def next(self) -> 'Pagina[T]':
        """Get next page."""
        return Pagina(self.items, page=self.page+1, limit=self._limit)

    def __repr__(self) -> str:
        items = ', '.join(map(repr, iter(self)))
        return f'Pagina(page={self.page}, [{items}])'

    @classmethod
    def empty(cls) -> 'Pagina[T]':
        return cls([], page=0)

    @classmethod
    def single(cls, items: Iterable[T]) -> 'Pagina[T]':
        """Return new single page item list."""
        if not isinstance(items, Sequence):
            items = tuple(items)
        return cls(items, limit=len(items))

    # --- Sequence protocol ---

    @overload
    def __getitem__(self, index: int) -> T:  ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[T]: ...

    def __getitem__(self, index: Union[int, slice]) -> Union[T, Sequence[T]]:
        start, end = self.start(), self.end()
        if isinstance(index, int):
            if index < 0:
                index += end
            else:
                index += start
            if start <= index < end:
                return self.items[index]
            raise IndexError('Pagina index out of range')
        return self.items[start:end][index]

    def __len__(self) -> int:
        return self.end() - self.start()

    def __contains__(self, item: object, /) -> bool:
        for i in range(self.start(), self.end()):
            if self.items[i] == item:
                return True
        return False

    def __iter__(self) -> Iterator[T]:
        if self.page <= 1 and len(self.items) <= self._limit:
            return iter(self.items)
        return iter(self.items[self.start():self.end()])

    def __reversed__(self) -> Iterator[T]:
        return reversed(self.items[self.start():self.end()])

    def index(self, value: T, start: int = 0, stop: int = maxsize) -> int:
        # TODO user start and stop
        start = self.start()
        end = self.end()
        for i in range(start, end):
            if self.items[i] == value:
                return i - start
        raise ValueError(f'{value!r} is not in page')

    def count(self, value: T) -> int:
        return self.items[self.start():self.end()].count(value)


class NextWatchPolicy(Enum):
    """How to calculate last and next episode in show progress."""
    # Episode are calculated using the last aired episode the user has watched.
    LAST = 'last'
    # Episode are calculated using last watched episode (last activity).
    CONTINUED = 'continued'
    # Episode are calculated using first unwatched episode.
    FIRST = 'first'
    # Episode are calculated using the last aired episode at all.
    NEWEST = 'newest'


@frozen
class MediaProgressItem:
    """Video (movie or episode) progress."""
    #: Media reference.
    ref: MediaRef
    #: The video watching progress percent (0..100).
    progress: float = 0.0
    #: The number of played.
    play_count: int = 0
    #: The last watch time or minimum date (1y).
    last_watched_at: datetime = field(default=datetime.min, converter=make_datetime)

    def __bool__(self) -> bool:
        """If item is watched or waching."""
        return self.play_count > 0 or self.progress > 0

    @property
    def total_progress(self) -> float:
        return 100.0 if self.play_count else self.progress

    @property
    def has_last_watched_at(self) -> bool:
        return self.last_watched_at and self.last_watched_at.year > 1


@frozen
class MediaProgressCount:
    """Number of watched, total etc. sub-items (e.g. episodes)."""
    unwatched: int = 0
    in_progress: int = 0
    watched: int = 0
    total: int = 0


@frozen
class MediaProgress:
    """Media progress (all types)."""

    #: Media reference.
    ref: MediaRef
    #: The video watching progress percent (0..100).
    progress: float = 0.0
    #: The number of played.
    play_count: int = 0
    #: The ast watch time or minimum date (1y).
    last_watched_at: datetime = field(default=datetime.min, converter=make_datetime)

    #: Flat bar of sub-items.
    bar: Sequence[MediaProgressItem] = ()
    #: The next episode the user should watch.
    next_episode: Optional['FFItem'] = None
    #: The last episode the user watched.
    last_episode: Optional['FFItem'] = None

    def __bool__(self) -> bool:
        """If item is watched or waching."""
        return self.play_count > 0 or self.progress > 0

    @property
    def total_progress(self) -> float:
        """Maximized progress (skip second watching)."""
        return 100.0 if self.play_count else self.progress

    @property
    def has_last_watched_at(self) -> bool:
        return self.last_watched_at and self.last_watched_at.year > 1

    def items_count(self) -> MediaProgressCount:
        """Get  umber of watched, total etc. counters."""
        watched = in_progress = 0
        for it in self.bar:
            if it.play_count:
                watched += 1
            if 0 < it.progress < 100:
                in_progress += 1
        total = len(self.bar)
        return MediaProgressCount(unwatched=total - watched, in_progress=in_progress, watched=watched, total=total)

    @overload
    @classmethod
    def __from_json__(cls, data: JsonData) -> Self: ...

    @overload
    @classmethod
    def __from_json__(cls, data: None) -> None: ...

    @classmethod
    def __from_json__(cls, data: Optional[JsonData]) -> Optional[Self]:
        """Return new MediaProgress object."""
        if data is None:
            return None
        ref_data = data['ref']
        if isinstance(ref_data, Mapping):
            ref = MediaRef(**ref_data)
        else:
            ref = MediaRef(*ref_data)
        return cls(**{**data, 'ref': ref})
