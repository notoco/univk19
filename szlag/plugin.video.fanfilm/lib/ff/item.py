"""FanFilm ListItem wrapper taken from libka."""

from __future__ import annotations
import re
from enum import Enum
from copy import deepcopy
from datetime import datetime, date as dt_date, time as dt_time
from typing import Optional, Union, Any, Tuple, List, Dict, Sequence, Mapping, Iterable, Iterator, Callable, ClassVar, Generic, TYPE_CHECKING
from typing import TypeVar, Type, NamedTuple, overload
from typing_extensions import Literal, TypeAlias, Protocol, Self
from wrapt.wrappers import ObjectProxy
from attrs import define, frozen, has as has_attrs, asdict
from .types import JsonData

# try:
#     from lib.kover.k20 import xbmcgui_ListItem as XbmcListItem
# except ImportError:
#     from xbmcgui import ListItem as XbmcListItem
from xbmcgui import ListItem as XbmcListItem
from xbmc import Actor, InfoTagVideo

from ..defs import RefType, MediaRef, VideoIds, MediaProgress, IdsDict
from .log_utils import fflog
from .tricks import dump_obj_gets, str_removeprefix, super_get_attr, super_set_attr, MISSING, MissingType
from .calendar import fromisoformat, timestamp as dt_timestmap, DateTime
from ..kolang import L
from const import const

if TYPE_CHECKING:
    from .kodidb import KodiVideoInfo
    from .menu import Target, ContextMenuItem, ContextMenu
    InfoTagVideoProxyType = InfoTagVideo
else:
    InfoTagVideoProxyType = ObjectProxy


# FFItem dict.
FFItemDict: TypeAlias = Dict[MediaRef, 'FFItem']
#: Kodi listitem's infoLabels type.
LabelInfoType: TypeAlias = Literal['video', 'music', 'pictures', 'game']
#: Info type value dict.
LabelInfoValues: TypeAlias = Dict[str, Any]
#: Popreries dict.
LabelPoperties: TypeAlias = Dict[str, str]
#: Popreries dict.
ArtValues: TypeAlias = Dict[str, str]
#: Kodi video media type.
LabelMediaType: TypeAlias = Literal['video', 'set', 'musicvideo', 'movie', 'tvshow', 'season', 'episode']
#: Special sort position.
SortPosition: TypeAlias = Literal['top', 'normal', 'bottom']
#: Episode type (or empty in not  applicable.
EpisodeType: TypeAlias = Literal['', 'standard',
                                 'series_premiere', 'season_premiere',
                                 'mid_season_finale', 'mid_season_premiere',
                                 'season_finale', 'series_finale']


T = TypeVar('T')


class VarApi(NamedTuple, Generic[T]):
    """Object variable (atribute) getter and setter."""
    name: Optional[str] = None
    getter: Union[str, Callable[[], T], None] = None
    setter: Union[str, Callable[[T], None], Callable[[str], Callable[[T], None]], None] = None
    default: Union[T, MissingType] = MISSING
    property: bool = False
    type: Optional[Callable[[Any], Any]] = None


#: Type of ...
ellipsis = type(...)
#: Class auto-vvariables description.
Vars: TypeAlias = Dict[str, Union[VarApi, Any]]


class JsonApiProto(Protocol):
    VARS: Vars
    def __to_json__(self) -> JsonData: ...
    def __set_json__(self, data: JsonData) -> None: ...
    @classmethod
    def __from_json__(cls: Type[Self], data: JsonData) -> Self: ...  # XXX HACK
    # def __from_json__(cls: Type[Self], data: JsonData) -> 'FFItem': ...  # XXX HACK


# def json_vars_deco(cls: Type[T]) -> Type[Union[JsonApiProto[T], T]]:
def json_vars_deco(cls: Type[T]) -> Type[T]:
    """Decorator for handle JSON methods and VARS definition."""
    def proc(k: str, v: Union[VarApi, Any]) -> VarApi:
        name = f'{k[:1].upper()}{k[1:]}'
        if v is ...:
            return VarApi(k, f'get{name}', f'set{name}')
        if not isinstance(v, VarApi):
            return VarApi(k, f'get{name}', f'set{name}', default=v)
        if not v.name:
            v = v._replace(name=k)
        if v.getter is True:
            v = v._replace(getter=f'get{name}')
        if v.setter is True:
            v = v._replace(setter=f'set{name}')
        return v

    def __to_json__(self) -> JsonData:
        """Dump object to JSON data."""
        def serialize(var):
            getter: Callable[[], Any] = var.getter
            if isinstance(getter, str):
                getter = super_get_attr(self, getter)
            if callable(getter):
                val = getter()
            elif var.property:
                val = super_get_attr(self, var.name)
            else:
                val = getter
            if val == var.default:
                return MISSING
            if val_to_json := getattr(val, '__to_json__', None):
                return val_to_json()
            if has_attrs(type(val)):
                return asdict(val, recurse=True)
            if isinstance(val, Sequence) and val and has_attrs(type(val[0])):
                return [asdict(v, recurse=True) for v in val]
            if isinstance(val, (datetime, dt_date, dt_time)):
                return str(val)
            return val

        return {var.name: val
                for var in self.VARS.values() if var.getter or var.property
                for val in (serialize(var),) if val is not MISSING}

    def __set_json__(self, data: JsonData) -> None:
        """Set JSON in existing object."""
        for key, val in data.items():
            var: VarApi = self.VARS.get(key)
            if var is None:
                fflog(f'ERROR, missing variable {key!r} in {self.__class__.__name__}')
                return
            if callable(var.type):
                val = var.type(val)
            if var.setter is not None:
                setter = var.setter
                if isinstance(setter, str):
                    setter = super_get_attr(self, setter)
                if callable(setter):
                    setter(val)
                else:
                    super_set_attr(self, var.setter, val)
            elif var.property and var.name:
                super_set_attr(self, var.name, val)
            else:
                fflog(f'ERROR, variable {key!r} is not settable {self.__class__.__name__}')

    @classmethod
    def __from_json__(cls, data: JsonData) -> T:
        """Load (create) object from JSON data."""
        obj = cls()
        obj.__set_json__(data)
        return obj

    cls.VARS = {k: proc(k, v) for k, v in getattr(cls, 'VARS', {}).items()}
    if not hasattr(cls, '__to_json__'):
        cls.__to_json__ = __to_json__
    if not hasattr(cls, '__from_json__'):
        cls.__from_json__ = __from_json__
    if not hasattr(cls, '__set_json__'):
        cls.__set_json__ = __set_json__
    return cls


class Temp:
    """Temporary custom attributes. Values are not stored."""


# @define(kw_only=True)
# class KodiItemData:
#     """Raw Kodi item data (from VideoDB)."""

#     # File ID ('idFile' from 'files')
#     file_id: Optional[int] = None
#     # Bookmark ID ('idBookmark' from 'bookmark')
#     bookmark_id: Optional[int] = None
#     # File/link name('strFilename' from 'files').
#     filename: str = ''
#     # Play count ('playCount' from 'files').
#     play_count: Optional[int] = None
#     # Played time (sec).
#     duration: Optional[float] = None
#     # Video duration (sec).
#     total_time: Optional[float] = None

#     @property
#     def prostgress(self) -> Optional[float]:
#         """Percent progress."""
#         if self.duration is None or self.total_time is None:
#             return None
#         if self.total_time > 0:
#             return 100 * self.duration / self.total_time
#         return 0.0


class FMode(Enum):
    """FFItem mode."""

    # Folder item (isFolder=True, isPalayble=False).
    Folder = 'folder'
    # Video item (isFolder=False, isPalayble=True).
    Playable = 'playable'
    # Command / passive item (isFolder=False, isPalayble=False).
    Command = 'command'
    # Kind od command.
    Separator = 'separator'


# class Role(Enum):
#     """Person main role."""
#     #: Actor
#     Actor = 'actor'
#     Director = 'director'
#     Writer = 'writer'
#     Crew = 'crew'


@frozen
class FFTitleAlias:
    title: str
    country: str = ''


@define
class Person:
    id: int
    name: str
    department: Optional[str] = None
    job: Optional[str] = None
    character: Optional[str] = None
    thumbnail: Optional[str] = None
    gender: int = 0
    order: int = -1

    @property
    def is_actor(self) -> bool:
        """True if actor"""
        return self.job == 'Actor'

    def actor(self) -> Optional[Actor]:
        """Return actor object."""
        if self.job == 'Actor':
            return Actor(self.name, self.character or '', self.order, self.thumbnail or '')
        return None


class _FFMetaClass(type):
    """FFItem meta-class to modify ListItem__init__ arguments."""

    def __call__(self, *args, **kwargs):
        return self.__new__(self, *args, **kwargs)
        # return super().__call__(*args, **kwargs).__wrapped__


class FFActor(Actor, metaclass=_FFMetaClass):
    """Extended actor/person."""

    def __new__(cls,
                name: str = '',
                role: str = '',
                order: int = -1,
                thumbnail: str = '',
                *,
                ffid: int = 0,
                ) -> 'FFActor':
        obj = super().__new__(cls, name, role, order, thumbnail)
        obj.__init__(name, role, order, thumbnail, ffid=ffid)
        return obj

    def __init__(self,
                 name: str = '',
                 role: str = '',
                 order: int = -1,
                 thumbnail: str = '',
                 *,
                 ffid: int = 0,
                 ) -> None:
        super().__init__(name, role, order, thumbnail)
        self.ffid = ffid

    def __hash__(self) -> int:
        """Return hash of item."""
        return hash(id(self))


@json_vars_deco
class FFVTag(InfoTagVideoProxyType):
    """Wrapper for InfoTagVideo, implements sam extra Famfilm stuff."""

    _rx_mpaa_split: ClassVar[re.Pattern] = re.compile(r'\s*,\s*')

    NO_DATE: ClassVar[str] = XbmcListItem().getVideoInfoTag().getPremieredAsW3C()

    VARS: Vars = {
        'actors':        VarApi(None, '_get_actors_json', '_set_actors_json', []),
        'countries':     [],
        'dbId':          -1,
        'directors':     [],
        'duration':      0,
        'episode':       -1,
        'firstAired':    VarApi(None, 'getFirstAiredAsW3C', 'setFirstAired', None),
        'genres':        [],
        'IMDBNumber':    '',
        'mediaType':     '',
        'mpaaList':      [],
        'originalTitle': '',
        'plot':          '',
        'plotBase':      '',  # external plot without modification and styling (e.g. w/o progress)
        'plotOutline':   '',
        'premiered':     VarApi(None, 'getPremieredAsW3C', 'setPremiered', None),
        'ratings':       {},
        'season':        -1,
        'studios':       [],
        'TvShowTitle':   '',
        'tagLine':       '',
        'title':         '',
        'trailer':       '',
        'uniqueIDs':     {},
        'userRating':    0,
        'writers':       [],
        'year':          0,
        # 'lastPlayed':    VarApi('lastPlayed', 'getLastPlayedAsW3C', 'setLastPlayed', None),
        # 'playcount'
        # 'resumeTime'
        # 'resumeTimeTotal'
        # 'file'
        # 'filenameAndPath'
        # 'path'
        # -- music --
        # 'album':         ...,
        # 'artists':       ...,
        # 'track':         ...,
        # -- FF specific --
        'englishTitle':       '',
        'englishTvShowTitle': '',
        'episodeType':        '',
        'seriesStatus':       '',
    }

    class Rating(NamedTuple):
        rating: float = 0
        votes: int = 0

    def __init__(self, vtag: InfoTagVideo) -> None:
        super().__init__(vtag)
        #: Unique Ids.
        self._self_unique_ids: Dict[str, str] = {}
        #: Unique Ids.
        self._self_unique_ids_default: str = ''
        #: MPAA ratings.
        self._self_mpaa: List[str] = []
        #: List of countries.
        self._self_countries: List[str] = []
        #: List of studios.
        self._self_studios: List[str] = []
        #: Ratings (keep copy to implement getRatings).
        self._self_ratings: Dict[str, FFVTag.Rating] = {}
        #: Default Rating name (keep copy to implement getRatingDefault).
        self._self_rating_default: str = 'default'
        #: Actor list (keep copy to implement getImDb).
        self._self_actors: List[FFActor] = []
        #: Crew - person list.
        self._self_crew: List[FFActor] = []
        #: Original / external plot without modification and styling (e.g. w/o progress).
        self._self_plot_base: str = ''
        #: The title in English.
        self._self_english_title: str = ''
        #: The tv-show title in English.
        self._self_english_tvshow_title: str = ''
        #: First aired date.
        self._self_first_aired: Optional[dt_date] = None
        #: Premiered date.
        self._self_premiered: Optional[dt_date] = None
        # #: Last played date-time.
        # self._self_last_played: Optional[datetime] = None
        #: Episode type.
        self._self_episode_type: EpisodeType = ''
        #: Tv-show status.
        self._self_series_status: str = ''


    def __repr__(self) -> str:
        return f'FFVTag({self.__wrapped__!r})'

    def dumps(self, *, indent: int = 2, margin: int = 0) -> str:
        def dump(vv: Any, margin: int) -> str:
            if isinstance(vv, tuple):
                br = '()'
            elif isinstance(vv, list):
                br = '[]'
            elif isinstance(vv, set):
                br = '{}'
            else:
                return repr(vv)
            if len(vv) <= 1:
                return repr(vv)
            out = '\n'.join(f'{"":{margin+indent}}{v!r}' for v in vv)
            return f'{br[0]}\n{out}\n{"":{margin}}{br[1]}'

        if not indent:
            return repr(self)
        vals = {str_removeprefix(k, 'InfoTagVideo.get'): v for k, v in dump_obj_gets(self)}
        if hasattr(self.__wrapped__, '__attributes__'):
            vals.update({a: v for a in self.__wrapped__.__attributes__ if (v := getattr(self, f'_{a}')) or True})
        out = '\n'.join(f'{"":{margin+indent}}{n:28} = {dump(v, margin=margin+indent)}' for n, v in vals.items())
        return f'FFVTag(\n{out}\n{"":{margin}})'

    def getUniqueIDs(self) -> Dict[str, str]:
        """Get all unique IDs."""
        return dict(self._self_unique_ids)

    def setUniqueIDs(self, values: Dict[str, str], defaultuniqueid: Optional[str] = None) -> None:
        """Set all unique IDs."""
        self._self_unique_ids = dict(values)
        if defaultuniqueid:
            self._self_unique_ids_default = defaultuniqueid
        self.__wrapped__.setUniqueIDs(values, defaultuniqueid)

    def setUniqueID(self, uniqueid: str, type: str = '', isdefault: bool = False) -> None:
        """Set one unique ID."""
        if not type:
            type = self._self_unique_ids_default
        if isdefault:
            self._self_unique_ids_default = type
        self._self_unique_ids[type] = uniqueid
        self.__wrapped__.setUniqueID(uniqueid, type, isdefault)

    def getAdult(self) -> bool:
        """Return True if it's adult video (X rated)."""
        return 'X' in self._self_mpaa

    def setAdult(self, adult: bool) -> None:
        """Set adult video flag (X rated)."""
        adult = bool(adult)
        was = 'X' in self._self_mpaa
        if was != adult:
            if adult:
                self._self_mpaa.append('X')
            else:
                self._self_mpaa.remove('X')
            self._set_mpaa()

    def getMpaaList(self) -> List[str]:
        """Get the MPAA rating of the video."""
        return list(self._self_mpaa)

    def setMpaaList(self, mpaa: List[str]) -> None:
        """Set the MPAA rating of the video."""
        self._self_mpaa = list(v for v in dict.fromkeys(mpaa) if v)
        self._set_mpaa()

    def getMpaa(self) -> str:
        """Get the MPAA rating of the video."""
        return ', '.join(self._self_mpaa)

    def setMpaa(self, mpaa: str) -> None:
        """Set the MPAA rating of the video."""
        self.setMpaaList(self._rx_mpaa_split.split(mpaa))

    def addMpaa(self, mpaa: str) -> None:
        """Add the MPAA rating of the video."""
        if mpaa and mpaa not in self._self_mpaa:
            self._self_mpaa.append(mpaa)
            self._set_mpaa()

    def _set_mpaa(self) -> None:
        """Set MPAA in kodi InfoTagVideo."""
        self.__wrapped__.setMpaa(', '.join(self._self_mpaa))

    def setCountries(self, countries: List[str]) -> None:
        """Set list of countries."""
        self._self_countries = list(countries)
        self.__wrapped__.setCountries(countries)

    def getCountries(self) -> List[str]:
        """Get list of countries (missing in kodi)."""
        return list(self._self_countries)

    def setStudios(self, studios: List[str]) -> None:
        """Set list of studios."""
        self._self_studios = list(studios)
        self.__wrapped__.setStudios(studios)

    def getStudios(self) -> List[str]:
        """Get list of studios (missing in kodi)."""
        return list(self._self_studios)

    def setRating(self, rating: float, votes: int = 0, type: str = "", isdefault: bool = False) -> None:
        """Set rating."""
        if not type:
            type = self._self_rating_default
        if isdefault:
            self._self_rating_default = type
        self._self_ratings[type] = FFVTag.Rating(rating=rating, votes=votes)
        self.__wrapped__.setRating(rating, votes, type, isdefault)

    def setRatings(self, ratings: Dict[str, Tuple[float, int]], defaultrating: str = "") -> None:
        """Set ratings."""
        if defaultrating:
            self._self_rating_default = defaultrating
        else:
            defaultrating = self._self_rating_default
        self._self_ratings = {k: FFVTag.Rating(*v) for k, v in ratings.items()}
        self.__wrapped__.setRatings(ratings, defaultrating)

    def getRatingDefault(self) -> str:
        """Get rating default name."""
        return self._self_rating_default

    def getRatings(self) -> Dict[str, Tuple[float, int]]:
        """Get ratings."""
        return dict(self._self_ratings)

    def _get_actors_json(self) -> List[JsonData]:
        """Get list of actors as JSON."""
        return [{'name': a.getName(), 'role': a.getRole(), 'order': a.getOrder(), 'thumbnail': a.getThumbnail(),
                 'ffid': a.ffid}
                for a in self._self_actors]

    def _set_actors_json(self, data: List[JsonData]) -> None:
        """Set list of actors from JSON data."""
        self._self_actors = [FFActor(**act) for act in data]
        self.__wrapped__.setCast(self._self_actors)

    def getTvShowTitle(self) -> str:
        """Get the video TV show title."""
        return self.getTVShowTitle()

    def getActors(self) -> List[FFActor]:
        """Get cast (actor list)."""
        return list(self._self_actors)

    def setActors(self, actors: Iterable[FFActor]) -> None:
        """Set cast (actor list)."""
        def act(a: Union[FFActor, Actor, Tuple]) -> FFActor:
            if isinstance(a, FFActor):
                return FFActor(a.getName(), a.getRole(), a.getOrder(), a.getThumbnail(), ffid=a.ffid)
            if isinstance(a, Actor):
                return FFActor(a.getName(), a.getRole(), a.getOrder(), a.getThumbnail())
            return FFActor(*a)

        self._self_actors = [act(a) for a in actors]
        self.__wrapped__.setCast(self._self_actors)

    def getCrew(self) -> List[FFActor]:
        """Get crew (director, producer, writer, ... list)."""
        return list(self._self_crew)

    def setCrew(self, persons: Iterable[FFActor]) -> None:
        """Set crew (director, producer, writer, ... list)."""
        def act(a: Union[FFActor, Actor, Tuple]) -> FFActor:
            if isinstance(a, FFActor):
                return FFActor(a.getName(), a.getRole(), a.getOrder(), a.getThumbnail(), ffid=a.ffid)
            if isinstance(a, Actor):
                return FFActor(a.getName(), a.getRole(), a.getOrder(), a.getThumbnail())
            return FFActor(*a)

        self._self_crew = [act(a) for a in persons]

    setCast = setActors

    def getPlotBase(self) -> str:
        """Returtns original / external plot without modification and styling (e.g. w/o progress)."""
        return self._self_plot_base

    def setPlotBase(self, plot: str) -> None:
        """Sets original / external plot without modification and styling (e.g. w/o progress). Overrides plot."""
        self._self_plot_base = str(plot or '')
        self.setPlot(self._self_plot_base)

    def getEnglishTitle(self) -> str:
        """Return the title in English."""
        return self._self_english_title

    def setEnglishTitle(self, title: str) -> None:
        """Set the title in English."""
        self._self_english_title = title

    def getEnglishTvShowTitle(self) -> str:
        """Return the tv-show title in English."""
        return self._self_english_tvshow_title

    def setEnglishTvShowTitle(self, title: str) -> None:
        """Set the tv-show title in English."""
        self._self_english_tvshow_title = title

    def getEpisodeType(self) -> EpisodeType:
        """Return the episode type."""
        return self._self_episode_type

    def setEpisodeType(self, value: EpisodeType) -> None:
        """Set the episode type."""
        self._self_episode_type = value

    def getSeriesStatus(self) -> str:
        """Return the episode type."""
        return self._self_series_status

    def setSeriesStatus(self, value: str) -> None:
        """Set the episode type."""
        self._self_series_status = value

    def getFirstAiredDate(self) -> Optional[dt_date]:
        """Get first aired date."""
        return self._self_first_aired

    def getFirstAiredAsW3C(self) -> str:
        """Get first aired date."""
        if self._self_first_aired is None:
            return self.NO_DATE
        return self._self_first_aired.isoformat()

    def setFirstAired(self, firstaired: Union[None, str, dt_date, datetime]) -> None:
        """Set first aired date."""
        date = firstaired
        if isinstance(date, str):
            date = fromisoformat(date)
        if isinstance(date, DateTime):
            date = date.date()
        self._self_first_aired = date
        self.__wrapped__.setFirstAired(self.NO_DATE if date is None else str(date))

    def getPremieredDate(self) -> Optional[dt_date]:
        """Get premiered date."""
        return self._self_premiered

    def getPremieredAsW3C(self) -> str:
        """Get premiered date."""
        if self._self_premiered is None:
            return self.NO_DATE
        return self._self_premiered.isoformat()

    def setPremiered(self, premiered: Union[None, str, dt_date, datetime]) -> None:
        """Set premiered date."""
        date = premiered
        if isinstance(date, str):
            date = fromisoformat(date)
        if isinstance(date, DateTime):
            date = date.date()
        self._self_premiered = date
        self.__wrapped__.setPremiered(self.NO_DATE if date is None else str(date))

    # def getLastPlayedDateTime(self) -> Optional[datetime]:
    #     """Get last played date."""
    #     return self._self_last_played

    # def getLastPlayedAsW3C(self) -> str:
    #     """Get last played date."""
    #     if self._self_last_played is None:
    #         return self.NO_DATE
    #     return self._self_last_played.isoformat(sep='T')

    # def setLastPlayed(self, lastplayed: Union[None, str, dt_date, datetime]) -> None:
    #     """Set last played date."""
    #     date = lastplayed
    #     if isinstance(date, str):
    #         date = fromisoformat(date)
    #     if isinstance(date, dt_date) and not isinstance(date, DateTime):
    #         date = datetime.combine(date, dt_time(12))
    #     self._self_last_played = date
    #     self.__wrapped__.setLastPlayed(self.NO_DATE if date is None else str(date))

    if TYPE_CHECKING:
        @classmethod
        def __from_json__(cls, data: JsonData) -> Self: ...
        def __to_json__(self) -> JsonData: ...
        def __set_json__(self, data: JsonData) -> None: ...


@json_vars_deco
class FFItem(XbmcListItem, metaclass=_FFMetaClass):
    """
    FanFilm xbmcgui.ListItem wrapper to keep URL and is_folder flag.

    >>> FFItem('label', 'label 2', '/path', offscreen=True)
    >>> FFItem('movie', 12345)
    >>> FFItem('movie', VideoIds(...))
    >>> FFItem(MediaRef(...))
    """

    DEFAULT_INFO_TYPE: LabelInfoType = 'video'

    VARS: Vars = {
        'type':                  VarApi(default=None, property=True),
        'ffid':                  VarApi(default=None, property=True),
        'tv_ffid':               VarApi(default=None, property=True),
        'url':                   VarApi(default=None, property=True),
        #
        'art':                   {},
        'dateTime':              ...,
        'label':                 '',
        'label2':                '',
        'path':                  '',
        'properties':            {},
        'availableFanart':       [],
        'folder':                VarApi('folder', 'isFolder', 'setIsFolder', False),
        'vtag':                  VarApi('vtag', 'getVideoInfoTag', 'vtag.__set_json__'),
        '_children_count':       VarApi(default=None, property=True),
        'episodes_count':        VarApi(default=None, property=True),
        'last_episode_to_air':   VarApi(default=None, property=True),
        'next_episode_to_air':   VarApi(default=None, property=True),
        'aliases_info':          VarApi(default=[], property=True, type=lambda vv: tuple(FFTitleAlias(*v) for v in vv)),
        'progress':              VarApi(default=None, property=True, type=lambda v: MediaProgress.__from_json__(v)),
        'keywords':              VarApi(default={}, property=True)
    }

    Mode: Type[FMode] = FMode
    ArtLabels: Tuple[str, ...] = ('thumb', 'poster', 'banner', 'fanart', 'clearart', 'clearlogo', 'landscape', 'icon')

    def __new__(cls,
                #: Kodi LiteItem label.
                label: Optional[Union[str, MediaRef]] = None,
                #: Kodi LiteItem label2.
                label2: Optional[str] = None,
                #: Kodi ListItem path.
                path: Optional[str] = None,
                # Kodi LiteItem offscreen flag (faster render).
                offscreen: bool = True,
                **kwargs):
        # Translate label.
        if isinstance(label, int):
            label = L(label)
        # determine arguments (see doc above)
        if isinstance(label, MediaRef):
            ref: MediaRef = label
            kwargs.setdefault('type', ref.real_type)
            if ref.season is None:
                kwargs.setdefault('ffid', ref.ffid)  # only for "movie" and "show"
            if ref.type == 'show':
                kwargs.setdefault('tv_ffid', ref.ffid)
                kwargs.setdefault('season', ref.season)
                kwargs.setdefault('episode', ref.episode)
            if kwargs['type'] in ('movie', 'episode'):
                kwargs.setdefault('mode', FMode.Playable)
            else:
                kwargs.setdefault('mode', FMode.Folder)
            label = label2 = ''
        elif isinstance(label, str) and isinstance(label2, int):
            kwargs.setdefault('type', label)
            kwargs.setdefault('ffid', label2)  # only for "movie" and "show"
            label = label2 = None
        elif isinstance(label, str) and isinstance(label2, VideoIds):
            kwargs.setdefault('type', label)
            kwargs.setdefault('ffid', label2.ffid)  # only for "movie" and "show"
            label = label2 = ''
        else:
            ...
        # if path:
        #     kwargs.setdefault('url', path)

        # xbmcgui.ListItem.__new__ positional arguments only
        if label is not None and not isinstance(label, str):
            fflog(f'ERROR: incorrect type: FFItem({label!r})')
        obj = super().__new__(cls, label, label2, path, offscreen)
        # obj.__init__(label, label2, path, offscreen)
        # # ffitem keyword argument only
        # obj.__ff_init__(**kwargs)
        obj.__init__(label, label2, path, offscreen, **kwargs)
        return obj

    def __init__(self,
                 # --- Kodi ListItem arguments. ---
                 # Kodi LiteItem label.
                 label: Optional[Union[str, MediaRef]] = None,
                 # Kodi LiteItem label2.
                 label2: str = '',
                 # Kodi ListItem path.
                 path: str = '',
                 # Kodi LiteItem offscreen flag (faster render).
                 offscreen: bool = True,
                 # --- Real FFItem keyword arguments. ---
                 *,
                 # Real media type (video type), one of: movie, show, season, episode.
                 type: Optional[RefType] = None,
                 # Media DB ID.
                 ffid: Optional[int] = None,
                 # Item mode (folder, playable, etc.).
                 mode: FMode = FMode.Command,
                 # Item URL, passed to kodi directory.
                 url: Optional[str] = None,
                 # Kodi list item info type (video, music, ...).
                 info_type: Optional[LabelInfoType] = 'video',
                 # Item target (URL or callback), passed to kodi directory. Will override url on kdir.add().
                 target: Optional['Target'] = None,
                 # TV show DB ID..
                 tv_ffid: Optional[int] = None,
                 # TV show season.
                 season: Optional[int] = None,
                 # TV show episode.
                 episode: Optional[int] = None,
                 # Tv-show FFItem (for seasons and episodes).
                 tvshow_item: Optional['FFItem'] = None,
                 # Season FFItem (for episodes).
                 season_item: Optional['FFItem'] = None,
                 # sort_key=None,
                 # custom=None,
                 # Set special sort postion (top, bottom).
                 position: Optional[SortPosition] = None,
                 # UTC timestamp, When item is created / updated.
                 meta_updated_at: int = 0,
                 # Properties to set.
                 properties: Optional[LabelPoperties] = None,
                 # Art values to set.
                 art: Optional[ArtValues] = None,
                 ) -> None:
        """FanFilm specfic initialize."""
        xbmc_label = label if isinstance(label, str) else ''
        super().__init__(xbmc_label, label2, path, offscreen)
        #: Media type.
        self.type: Optional[RefType] = type
        #: Media DB ID.
        self.tv_ffid: Optional[int] = tv_ffid
        #: Media DB ID.
        self._ffid: Optional[int] = ffid
        # True if folder. Passed to kodi directory.
        self._item_folder: bool = mode == FMode.Folder
        #: Item mode.
        self._mode: FMode = mode
        #: Kodi listitem's infoLabels type.
        self.info_type: Optional[LabelInfoType] = info_type
        #: Info labels copy.
        self._info: LabelInfoValues = {}
        #: Poperties copy.
        self._props: LabelPoperties = {}
        #: Art values copy.
        self._art: ArtValues = {}
        #: Art values copy.
        self._available_fanart: List[ArtValues] = []
        # self.sort_key = sort_key  # TODO: get more from libka
        # self.custom = custom  # TODO: get more from libka
        #: Custom context-menu items. Item are NOT added to ListItem. Use `addContextMenuItem` or `KodiDirectory.` to add items to ListItem.
        self.cm_menu: list[ContextMenuItem] = []
        #: Wrapper of Kodi InfoTagVideo.
        self._vtag: Optional[FFVTag] = None
        #: Tv-show ff-item, for show (itself), season, episode objects.
        self.show_item: Optional[FFItem] = tvshow_item
        #: Season ff-item, for episode object.
        self.season_item: Optional[FFItem] = season_item
        #: List of children: tv-show seasons or season episodes.
        self.children_items: Optional[List[FFItem]] = None
        #: Declaration of children count. Used in degraded items (eg. seasons got form show details).
        self._children_count: Optional[int] = None
        #: The number of all episodes count. Used in deep degraded show (without full seasons info).
        self.episodes_count: Optional[int] = None
        #: Declaration of aired episodes count. Used in deep degraded items (number of episodes in the show).
        self._aired_episodes_count: Optional[int] = None
        #: Last episode to air.
        self.last_episode_to_air: Optional[FFItem] = None
        #: Next episode to air.
        self.next_episode_to_air: Optional[FFItem] = None
        #: UI Language (eg. to obtain title language).
        self.ui_lang: Optional[str] = None
        #: Item URL (for kodi directory).
        self.target: Target | None = target
        #: Item URL (for kodi directory).
        self.url: Optional[str] = url
        #: Cutsom source data, eg. JSON object.
        self.source_data: Optional[Any] = None
        #: Cutsom role / label (eg. playing character, person job, etc.).
        self.role: str = ''
        #: Something is not OK, eg. not TMDB info found.
        self.broken: bool = False
        #: Optional style for fromat or modify description.
        self.descr_style: Optional[str] = None
        #: Temporary custom attributes.
        self.temp = Temp()
        #: Progress info.
        self.progress: Optional[MediaProgress] = None
        #: UTC timestamp, When item is created / updated.
        self.meta_updated_at: int = int(meta_updated_at.timestamp() if isinstance(meta_updated_at, DateTime) else meta_updated_at or 0)
        #: Title aliases.
        self.aliases_info: Sequence[FFTitleAlias] = ()
        #: Raw Kodi progress and play-count.
        self.kodi_data: Optional['KodiVideoInfo'] = None  # XXX ???
        #: Item keywords (from TMDB).
        self.keywords: Mapping[str, int] = {}

        if self.info_type is not None:
            self.setInfo(self.info_type, self._info)
        if self.url is None and self._mode == FMode.Separator:
            self.url = ''  # no operation
        # use property setters
        self.mode = mode
        if ffid is not None:
            self.ffid = ffid
        if season is not None:
            self.season = season
        if episode is not None:
            self.episode = episode
        if self.type:
            mtype = 'tvshow' if self.type == 'show' else self.type
            self.vtag.setMediaType(mtype)
        if position is not None:
            self.position = position
        if self._ffid:
            self.vtag.setUniqueID(str(self._ffid), 'ffid')
            self.vtag.setUniqueID(f'{self.ref:a}', 'ffref')
        if properties is not None:
            self.setProperties(properties)
        if art is not None:
            self.setArt(art)

    def __repr__(self):
        extra = ''
        if self.season:
            extra = f', season={self.season!r}'
            if self.episode:
                extra = f'{extra}, episode={self.episode!r}'
        # return (f'FFItem({super().__repr__()}, type={self.type!r}, ffid={self.ffid!r}{extra},'
        #         f' title={self.title!r}, year={self.year})')
        return (f'FFItem({self.ref:a}, type={self.type!r}, ffid={self.ffid!r}{extra},'
                f' title={self.title!r}, year={self.year})')

    def __hash__(self) -> int:
        """Return hash of item."""
        return hash(id(self))

    def dumps(self, *, indent: int = 2, margin: int = 0) -> str:
        if not indent:
            out = ', '.join(f'{n}={v!r}' for n, v in dump_obj_gets(self))
            return f'FFItem({out})'
            indent = 2
        # return '\n'.join(f'{indent}{n:28} = {v!r}' for n, v in dump_obj_gets(self))
        out = '\n'.join(f'{"":{indent}}{n:28} = {x}' for n, v in dump_obj_gets(self)
                        for x in (v.dumps(indent=indent, margin=margin+indent) if hasattr(v, 'dumps') else repr(v),))
        return f'FFItem(\n{out}\n{"":{margin}})'

    @property
    def vtag(self) -> FFVTag:
        if self._vtag is not None:
            return self._vtag
        return self.getVideoInfoTag()

    # def __getattr__(self, key):
    #     return getattr(self._xbmc_item, key)

    def __iter__(self) -> Iterator['FFItem']:
        """Iterate over children (seasons or episodes)."""
        return iter(self.children_items if self.children_items else ())

    def __call__(self) -> XbmcListItem:
        """Execute item, apply all virtual settings into Kodi ListItem."""
        # if self._menu is not None:
        #     self.addContextMenuItems(self._menu)
        return self

    # def __reduce_ex__(self, proto) -> Tuple[Type, Tuple[Any, ...], Any]:
    #     """Return pickle dump (type, args, state)."""

    # def __cache_dump__(self) -> JsonData:
    #     """Dump object to JSON data."""

    # @classmethod
    # def __cache_load__(self, data: JsonData) -> 'FFItem':
    #     """Load (create) object from JSON data."""

    # def __to_json__(self) -> JsonData:
    #     """Dump object to JSON data."""

    # @classmethod
    # def __from_json__(self, data: JsonData) -> 'FFItem':
    #     """Load (create) object from JSON data."""

    @classmethod
    def from_actor(cls, actor: FFActor) -> 'FFItem':
        """Create FFItem from FFActor."""
        it = FFItem(MediaRef.person(actor.ffid), mode=FFItem.Mode.Folder)
        it.label = it.title = actor.getName()
        img = actor.getThumbnail()
        if img:
            it.setArt({'thumb': img})
        it.role = actor.getRole()
        return it

    def get_season_item(self, season: int) -> Optional['FFItem']:
        """Get child season item, if exists."""
        for sz in self.season_iter():
            if sz.season == season:
                return sz
        return None

    # def get_episode_item(self) -> Optional['FFItem']:
    #     """Iterate over season episodes."""
    #     return iter(self.children_items if self.type == 'season' and self.children_items else ())

    def season_iter(self) -> Iterator['FFItem']:
        """Iterate over tv-show seasons."""
        return iter(self.children_items if self.type == 'show' and self.children_items else ())

    def episode_iter(self) -> Iterator['FFItem']:
        """Iterate over season episodes (for season) and over all non-special episodes (for show)."""
        if self.type == 'show' and self.season is None and self.episode is None:
            return iter((ep for sz in self.season_iter() if sz.season for ep in sz.episode_iter()))
        return iter(self.children_items if self.type == 'season' and self.children_items else ())

    def linear_episode_ref(self, number: int) -> Optional[MediaRef]:
        """Get episode ref by linear episode number in the show (1..N)."""
        ref = self.ref
        if ref.is_show:
            if not self.children_items:
                return None
            for sz in self.season_iter():
                if sz.season:  # skip specials
                    if 0 < number <= sz.children_count:
                        return ref.with_season(sz.season or 0).with_episode(number)
                    number -= sz.children_count
        elif ref.type == 'show':
            if show := self.show_item:
                return show.linear_episode_ref(number)
        return None

    def linear_episode_number(self) -> Optional[int]:
        """Get the episode linear number in the show (1..N)."""
        ref = self.ref
        if not ref.is_episode:
            return None
        if show := self.show_item:
            number = 0
            for sz in show.season_iter():
                if sz.season and sz.season == ref.season:  # skip specials
                    for ep in sz.episode_iter():
                        number += 1
                        if ep.episode == ref.episode:
                            return number
                    return None
                number += sz.children_count
        return None

    def item_tree_iter(self, *, itself: bool = False) -> Iterator['FFItem']:
        """Iterate over all sub-items."""
        if itself:
            return self
        for it in self.children_items or ():
            yield it
            yield from it.item_tree_iter()

    def item_dict(self) -> FFItemDict:
        """Return it self and all sub-items dict."""
        return {it.ref: it for it in self.item_tree_iter(itself=True)}

    def getVideoInfoTag(self):
        """Returns the VideoInfoTag for this item."""
        if self._vtag is None:
            if self.mode in (FMode.Command, FMode.Separator):
                self._vtag = FFVTag(InfoTagVideo())
            else:
                self._vtag = FFVTag(super().getVideoInfoTag())
        return self._vtag

    @property
    def mode(self) -> FMode:
        """Item mode (folder, playable...)."""
        return self._mode

    @mode.setter
    def mode(self, mode: FMode) -> None:
        playable = mode in (mode.Playable, 'play', 'playable')
        folder = mode in (mode.Folder, 'folder', 'menu')
        self.setProperty('IsPlayable', 'true' if playable else 'false')
        self.setIsFolder(folder)
        self._item_folder = folder

    @property
    def ffid(self) -> Optional[int]:
        """Media DB ID."""
        return self._ffid

    @ffid.setter
    def ffid(self, value: int) -> None:
        """Media DB ID."""
        self._ffid = value
        vtag = self.getVideoInfoTag()
        vtag.setUniqueID(str(self._ffid), 'ffid')
        vtag.setUniqueID(f'{self.ref:a}', 'ffref')
        vid = VideoIds.from_ffid(self._ffid)
        if vid is not None:
            if (default := vid.service()) and not vtag.getUniqueID(default):
                vtag.setUniqueID(vid.kodi_ids()[default], default, True)
            # vtag.setUniqueIDs(vid.kodi_ids(), vid.service())
            if self._ffid in VideoIds.KODI:
                try:
                    vtag.setDbId(self._ffid)  # Kodi DBID
                except OverflowError:
                    from .log_utils import fflog_exc
                    fflog_exc()
                    fflog(f'FFID overflow: ffid={self._ffid}, {vid=}')

    @property
    def label(self) -> str:
        """Current item label."""
        return self.getLabel()

    @label.setter
    def label(self, label: str) -> None:
        self.setLabel(label)

    @property
    def info(self) -> LabelInfoValues:
        return self._info

    def get(self, info: str) -> Any:
        """Get single info value or another value or None if not exists."""
        if info == 'label':
            return self.getLabel()
        return self._info.get(info)

    def get_info(self, info: str) -> Any:
        """Get single info value or None if not exists."""
        return self._info.get(info)

    def set_info(self, info: Union[str, LabelInfoValues], value: Optional[Any] = None):
        """
        Set info value or info dict.

        set_info(name, value)
        set_info({'name': 'value', ...})
        """
        if isinstance(info, Mapping):
            if value is not None:
                raise TypeError('Usage: set_info(name, value) or set_info(dict)')
            self._info.update(info)
        else:
            self._info[info] = value
        info_type = self.info_type
        if info_type is None:
            info_type = 'video'
        self.setInfo(info_type, self._info)

    def setInfo(self, info_type: str, infoLabels: LabelInfoValues) -> None:
        """See Kodi ListItem.setInfo()."""
        if self.info_type is None:
            self.info_type = info_type
        if info_type != self.info_type:
            raise ValueError(f'Info label type mismatch {self.info_type!r} != {info_type!r}')
        if self.info_type is None:
            raise TypeError('setInfo: type is None')
        self._info.update(infoLabels)
        super().setInfo(self.info_type, self._info)

    @property
    def title(self) -> str:
        """Item media title."""
        return self.vtag.getTitle()

    @title.setter
    def title(self, title: str) -> None:
        return self.vtag.setTitle(title)

    @property
    def year(self) -> Optional[int]:
        """Returns media year."""
        return self.vtag.getYear()

    @property
    def duration(self) -> Optional[int]:
        """Returns video duration or None."""
        return self.vtag.getDuration() or None

    @property
    def date(self) -> Optional[dt_date]:
        vtag = self.vtag
        ds = vtag.getFirstAiredDate()
        if not ds:
            ds = vtag.getPremieredDate()
        if not ds and (year := vtag.getYear()):
            rtype = self.ref.real_type
            if rtype == 'movie' and const.indexer.movies.date_from_year:
                return dt_date(year, 1, 1)
            elif rtype == 'episode' and const.indexer.episodes.date_from_year:
                return dt_date(year, 1, 1)
        return ds

    @property
    def date_timestamp(self) -> Optional[int]:
        d = self.date
        if d:
            try:
                return int(dt_timestmap(d))
            except OSError:
                # On Windows platform, C time range can sometimes be restricted.
                # See ff.callendar.utc_timestamp().
                return 0
        return None

    def aired_before(self, date: Optional[Union[dt_date, datetime]] = None) -> bool:
        """True, if episode is aired/premiered before date (or now) inclusive."""
        aired = self.date
        if aired is None:
            rtype = self.ref.real_type
            if rtype == 'movie':
                return not const.indexer.movies.future_if_no_date
            elif rtype == 'episode':
                return not const.indexer.episodes.future_if_no_date
            elif rtype == 'season':
                return not const.indexer.seasons.future_if_no_date
            elif rtype == 'show':
                return not const.indexer.tvshows.future_if_no_date
            return True  # we don't know
        if date is None:
            date = dt_date.today()
        elif isinstance(date, DateTime):
            date = date.date()
        return aired <= date

    @property
    def unaired(self) -> bool:
        """True, if episode is not aired."""
        return not self.aired_before()

    def setProperties(self, values: LabelPoperties) -> None:
        """See Kodi ListItem.setProperties()."""
        values = {k.lower(): v for k, v in values.items()}
        self._props.update(values)
        super().setProperties(values)

    def getProperties(self) -> LabelPoperties:
        """Get all properties."""
        return dict(self._props)

    def setProperty(self, key: str, value: str) -> None:
        """See Kodi ListItem.setProperty()."""
        key = key.lower()
        self._props[key] = value
        super().setProperty(key, '' if value is None else str(value))

    @overload
    def getArt(self, key: str) -> str: ...

    @overload
    def getArt(self) -> ArtValues: ...

    def getArt(self, key: Optional[str] = None) -> Union[str, ArtValues]:
        """Get the listitem's art by key or all art values if key is None."""
        if key is None:
            return dict(self._art)
        return super().getArt(key)

    def setArt(self, values: ArtValues) -> None:
        """Set the listitem's art."""
        self._art = dict(values)
        super().setArt(values)

    def getAvailableFanart(self) -> List[ArtValues]:
        """Get available images (needed for video scrapers)."""
        return deepcopy(self._available_fanart)

    def setAvailableFanart(self, images: List[ArtValues]) -> None:
        """Set available images (needed for video scrapers)."""
        self._available_fanart = [dict(im) for im in images]
        super().setAvailableFanart(images)

    @property
    def season(self) -> Optional[int]:
        """Season number or None."""
        value = self.getVideoInfoTag().getSeason()
        return None if value < 0 else value

    @season.setter
    def season(self, season: Optional[int]) -> None:
        vtag = self.getVideoInfoTag()
        if season is None:
            vtag.setSeason(-1)
        else:
            vtag.setSeason(int(season))
        vtag.setUniqueID(f'{self.ref:a}', 'ffref')

    @property
    def episode(self) -> Optional[int]:
        """Season number or None."""
        value = self.getVideoInfoTag().getEpisode()
        return None if value < 0 else value

    @episode.setter
    def episode(self, episode: Optional[int]) -> None:
        vtag = self.getVideoInfoTag()
        if episode is None:
            vtag.setEpisode(-1)
        else:
            vtag.setEpisode(int(episode))
        vtag.setUniqueID(f'{self.ref:a}', 'ffref')

    @property
    def show_ref(self) -> Optional[MediaRef]:
        """Return show ref for show, season and episode."""
        return self.ref.show_ref

    @property
    def season_ref(self) -> Optional[MediaRef]:
        """Return season ref for season and episode."""
        return self.ref.season_ref

    # def season_item(self) -> Optional['FFItem']:
    #     """Return season item (for episodes)."""
    #     return self._season_item

    # def show_item(self) -> Optional['FFItem']:
    #     """Return tv-show item (for seasons and episodes)."""
    #     return self._show_item

    @property
    def children_count(self) -> int:
        """Declaration of children count. Used in degraded items (e.g. seasons got form show details)."""
        if self.children_items is not None:
            return len(self.children_items)
        return self._children_count or 0

    @property
    def aired_episodes_count(self) -> int:
        """Declaration of episodes count. Used in deep degraded items (number of episodes in the show)."""
        if self._aired_episodes_count is None:
            ref = self.ref
            next_episode_to_air = self.next_episode_to_air
            if next_episode_to_air is None and self.show_item:
                next_episode_to_air = self.show_item.next_episode_to_air
            if ref.type != 'show':
                self._aired_episodes_count = 0
            elif ref.is_episode:
                self._aired_episodes_count = 1
            elif next_episode_to_air is None:  # no info about next episode...
                # we try use all episode count (it's good enough)
                if self.episodes_count is not None:
                    self._aired_episodes_count = self.episodes_count
                else:
                    # we count all episodes
                    seasons = (self,) if ref.is_season else self.children_items or ()
                    self._aired_episodes_count = sum(sz.children_count for sz in seasons)
            else:
                nxt = next_episode_to_air.ref
                assert nxt.season is not None
                assert nxt.episode is not None
                if ref.is_season:
                    # one season
                    assert ref.season is not None
                    if ref.season < nxt.season:
                        self._aired_episodes_count = self.children_count  # this season is before airing season, then is aired
                    elif ref.season > nxt.season:
                        self._aired_episodes_count = 0                    # this season is after airing season, then is not aired
                    else:
                        # the same season, check episodes (continuous episode counting, starting from one)
                        self._aired_episodes_count = nxt.episode - 1
                else:
                    # the show
                    self._aired_episodes_count = (sum(sz.children_count                          # episodes in all old seasons
                                                      for sz in self.season_iter()
                                                      if 0 < (sz.ref.season or 0) < nxt.season)
                                                  + nxt.episode - 1)                             # + old episodes in airing season
        return self._aired_episodes_count

    @aired_episodes_count.deleter
    def aired_episodes_count(self) -> None:
        self._aired_episodes_count = None

    def get_episode_type(self) -> EpisodeType:
        """Get (guess) episode type. See #180."""
        ref = self.ref
        if not ref.is_episode:
            return ''
        assert ref.season is not None
        assert ref.episode is not None
        # Case 1. Known episode type.
        if episode_type := self.vtag.getEpisodeType():
            return episode_type
        if show := self.show_item:
            # Case 2. Last aired.
            if (last := show.last_episode_to_air) and last.ref == ref:
                return last.vtag.getEpisodeType() or 'standard'
            # Case 3. Next to air.
            if (ep := show.next_episode_to_air) and ep.ref == ref:
                return ep.vtag.getEpisodeType() or 'standard'
        if ref.episode == 1:
            # Case 4. First episode of first season.
            if ref.season == 1:
                return 'series_premiere'
            # Case 5. First episode of non-first season.
            return 'season_premiere'
        if show := self.show_item:
            # last episode ...
            if (sz := show.get_season_item(ref.season)) and sz.children_count == ref.episode:
                # Case 6. Last episode of non-last season.
                if show.get_season_item(ref.season + 1):
                    return 'season_finale'
        # Case 7. All others.
        return 'standard'

    def copy_art_from(self, *items: Optional['FFItem'], all: bool = False) -> None:
        """Copy main (or all) art images from given items."""
        if all:
            ...
        is_episode = self.ref.is_episode
        art = self.getArt()  # no key, get all art images (FFItem extension)
        for key in self.ArtLabels:
            if not art.get(key):
                for it in items:
                    if it and (img := it.getArt(key)):
                        if key == 'thumb' and is_episode != it.ref.is_episode:
                            continue
                        art[key] = img
                        break
        # support for tvshow.poster and tvshow.fanart
        tvshow_art_labels = ('poster', 'landscape', 'fanart')
        for key in tvshow_art_labels:
            tvkey = f'tvshow.{key}'
            if not art.get(tvkey):
                for it in items:
                    if it and it.ref.is_show and (img := it.getArt(key)):
                        art[tvkey] = img
                        break
        if not art.get('thumb') and (thumb := art.get('landscape' if is_episode else 'poster')):
            art['thumb'] = thumb
        if art:
            self.setArt(art)

    def copy_from(self, *items: Optional['FFItem']) -> None:
        """Copy data (art, description etc.) from given items."""
        vtag = self.vtag
        what_to_copy = [
            ('getPlotBase', vtag.setPlotBase),
            ('getGenres', vtag.setGenres),
            ('getMpaa', vtag.setMpaa),
            ('getActors', vtag.setActors),
            ('getStudios', vtag.setStudios),
            ('getCountries', vtag.setCountries),
            ('getDirectors', vtag.setDirectors),
            ('getTrailer', vtag.setTrailer),
        ]
        if const.core.info.copy_year:
            what_to_copy.append(('getYear', vtag.setYear))
        if not self.ref.is_episode:
            what_to_copy.append(('getTagLine', vtag.setTagLine))
        for getter_name, setter in what_to_copy:
            if not getattr(vtag, getter_name)():
                for it in items:
                    if it:
                        val = getattr(it.vtag, getter_name)()
                        if val:
                            setter(val)
                            break

        self.copy_art_from(*items)

    @property
    def position(self) -> SortPosition:
        """Get special sort position."""
        pos = self.getProperty('SpecialSort')
        return pos if pos in ('top', 'bottom') else 'normal'

    @position.setter
    def position(self, pos: SortPosition) -> None:
        """Get special sort position."""
        self.setProperty('SpecialSort', pos if pos in ('top', 'bottom') else '')

    @property
    def ref(self) -> MediaRef:
        """Return media reference."""
        if self.type in ('season', 'episode'):
            return MediaRef(type='show', ffid=self.tv_ffid or 0, season=self.season, episode=self.episode)
        return MediaRef(type=self.type or '', ffid=self.ffid or 0)

    @property
    def video_ids(self) -> VideoIds:
        """Return VideoIds()."""
        return self.ref.video_ids

    @property
    def ids(self) -> IdsDict:
        """Returns know IDs."""
        ids = self.vtag.getUniqueIDs()
        return {k: int(v) if v.isdigit() else v
                for k in ('tmdb', 'imdb', 'trakt', 'tvdb', 'slug')
                if (v := ids.get(k))}  # type: ignore  -- number are converted to int

    @property
    def aliases(self) -> Sequence[str]:
        """Returns all title aliases (from all countries)."""
        return tuple(a.title for a in self.aliases_info)

    def clone(self) -> 'FFItem':
        """Clone FFItem."""
        data = self.__to_json__()
        item = FFItem(self.ref)
        item.__set_json__(data)
        item.progress = self.progress
        return item

    def __eq__(self, other: Any) -> bool:
        try:
            to_json = other.__to_json__
        except AttributeError:
            pass
        else:
            return self.__to_json__() == to_json()
        return False

    if TYPE_CHECKING:
        @classmethod
        def __from_json__(cls, data: JsonData) -> Self: ...
        def __to_json__(self) -> JsonData: ...
        def __set_json__(self, data: JsonData) -> None: ...


class FFFolder(FFItem):
    """Folder list item."""

    def __init__(self, name: str, *, mode: Optional[FMode] = None, **kwargs) -> None:
        assert mode is None or mode == FMode.Folder
        super().__init__(name, mode=FMode.Folder)


class FFPlayable(FFItem):
    """Playable list item."""

    def __init__(self, name: str, *, mode: Optional[FMode] = None, **kwargs) -> None:
        assert mode is None or mode == FMode.Playable
        super().__init__(name, mode=FMode.Playable)
