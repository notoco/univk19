"""Tiny TheMovieDB.org API wrapper."""

from __future__ import annotations
import re
from datetime import datetime, date as dt_date, timedelta
from threading import Lock, Semaphore
from urllib.parse import urljoin
from enum import Enum, Flag, auto as auto_enum
from time import monotonic
from typing import Optional, Union, Any, Tuple, List, Dict, Set, Sequence, Iterable, Iterator, Mapping, Callable
from typing import Generic, Generator, ClassVar, Type, TypeVar, NamedTuple, TYPE_CHECKING
from typing_extensions import Literal, get_args as get_typing_args, TypedDict, Unpack, NotRequired, TypeAlias, Self, Pattern, cast
# from typing_extensions import Annotated
from attrs import define, frozen, evolve

from ..defs import VideoIds, MediaRef
from ..defs import RefType, MainMediaType, MainMediaTypeList, ItemList, SearchType, FFRef
from ..ff.db.playback import MediaPlayInfoDict
from ..ff.item import FFItem, EpisodeType
from ..ff.types import JsonData, JsonResult, KwArgs, Params, Headers
from ..ff.calendar import fromisoformat
from ..ff.tricks import join_items, batched, jwt_decode
from ..ff.kotools import xsleep
from ..ff.log_utils import fflog
from ..ff.control import max_thread_workers
from ..ff.requests import RequestsPoolExecutor, clear_netcache
from ..ff import requests
from const import const

if TYPE_CHECKING:
    from ..ff.requests import CacheArg, Method


T = TypeVar('T')

DialogId: TypeAlias = Any
ApiVer: TypeAlias = Literal[3, 4, None]

TmdbId: TypeAlias = int
MovieId: TypeAlias = TmdbId
ShowId: TypeAlias = TmdbId
SeasonId: TypeAlias = TmdbId
EpisodeId: TypeAlias = TmdbId
SeasonNumber: TypeAlias = int
EpisodeNumber: TypeAlias = int
# TmdbTvIdKey = Tuple[ShowId, Optional[SeasonId], Optional[EpisodeId]]
# TmdbTvIds = Dict[TmdbTvIdKey, TmdbId]

#: TMDB get info content type.
TmdbContentType: TypeAlias = Literal['movie', 'tv']
TmdbContentPluarType: TypeAlias = Literal['movies', 'tv']
#: TMDB get info content type.
TmdbListType: TypeAlias = Literal[
    'top_rated',    # ?include_adult=false&include_video=false&language=en-US&page=1&sort_by=vote_average.desc&without_genres=99,10755&vote_count.gte=200
    'popular',      # ?include_adult=false&include_video=false&language=en-US&page=1&sort_by=popularity.desc
    'now_playing',  # ?include_adult=false&include_video=false&language=en-US&page=1&sort_by=popularity.desc&with_release_type=2|3&release_date.gte={min_date}&release_date.lte={max_date}
    'upcoming',     # ?include_adult=false&include_video=false&language=en-US&page=1&sort_by=popularity.desc&with_release_type=2|3&release_date.gte={min_date}&release_date.lte={max_date}
]

TimeWindow: TypeAlias = Literal['week', 'day']

TmdbConfName: TypeAlias = Literal['countries', 'jobs', 'languages', 'primary_translations', 'timezones']

ExternalIdType: TypeAlias = Literal['imdb']

TmdbSearchType: TypeAlias = Literal['collection', 'company', 'keyword', 'movie', 'multi', 'person', 'tv']

PersonDataType: TypeAlias = Literal['combined_credits', 'movie_credits', 'tv_credits']

DetailsAllowed: TypeAlias = Literal['movie', 'show', 'person', 'collection']

MediaResource: TypeAlias = Literal['recommendations', 'similar']

AccountId: TypeAlias = Union[int, Literal['me']]

#: Users general list.
UserGeneralListType: TypeAlias = Literal['favorite', 'watchlist']
#: TMDB JSON item data.
TmdbItemJson: TypeAlias = Dict[str, Any]
#: Media JSON data.
TmdbMediaDataDict: TypeAlias = Dict[MediaRef, TmdbItemJson]
#: TMDB sort_by values (movie).
TmdbMovieSortBy: TypeAlias = Literal['original_title.asc', 'original_title.desc',
                                     'popularity.asc', 'popularity.desc',
                                     'revenue.asc', 'revenue.desc',
                                     'primary_release_date.asc', 'primary_release_date.desc',
                                     'title.asc', 'title.desc',
                                     'vote_average.asc', 'vote_average.desc',
                                     'vote_count.asc', 'vote_count.desc',
                                     ]
#: TMDB sort_by values (tv).
TmdbTvSortBy: TypeAlias = Literal['first_air_date.asc', 'first_air_date.desc',
                                  'name.asc', 'name.desc',
                                  'original_name.asc', 'original_name.desc',
                                  'popularity.asc', 'popularity.desc',
                                  'vote_average.asc', 'vote_average.desc',
                                  'vote_count.asc', 'vote_count.desc',
                                  ]
#: TMDB sort_by values.
TmdbSortBy: TypeAlias = Literal['original_title.asc', 'original_title.desc',              # movie only
                                'revenue.asc', 'revenue.desc',                            # movie only
                                'primary_release_date.asc', 'primary_release_date.desc',  # movie only
                                'title.asc', 'title.desc',                                # movie only
                                'first_air_date.asc', 'first_air_date.desc',              # tv-show only
                                'name.asc', 'name.desc',                                  # tv-show only
                                'original_name.asc', 'original_name.desc',                # tv-show only
                                'popularity.asc', 'popularity.desc',
                                'vote_average.asc', 'vote_average.desc',
                                'vote_count.asc', 'vote_count.desc',
                                ]


@frozen
class TmdbCredentials:
    """TMDB credentials."""

    #: Optional TMDB api-key for get more tv-show info.
    api_key: Optional[str] = None
    #: Optional TMDB v4 api bearer JWT token.
    bearer: Optional[str] = None
    #: User name.
    user: Optional[str] = None
    #: User password.
    password: Optional[str] = None
    #: User session.
    session_id: Optional[str] = None
    #: Access token (v4).
    access_token: Optional[str] = None

    def __bool__(self) -> bool:
        """Return True if credentials are defined (user is logged)."""
        return bool(self.session_id) or bool(self.access_token)

    @property
    def v3(self) -> bool:
        """Return True if credentials are defined (user is logged) in v3 API."""
        return bool(self.session_id)

    @property
    def v4(self) -> bool:
        """Return True if credentials are defined (user is logged) in v4 API."""
        return bool(self.access_token)

    @property
    def account_id(self) -> str:
        """Return account_id from v4 access_token."""
        if self.access_token:
            return jwt_decode(self.access_token).get('sub', '')
        return ''


class GetImageMode(Enum):
    """Mode of image getting."""
    #: append  - use `append_to_response=images` with fixed `include_image_language`, no poster at all often
    APPEND = 'append'
    #: append  - use `append_to_response=images` with fixed `include_image_language=en.
    APPEND_EN = 'append_en'
    #: append  - use `append_to_response=images` with fixed `include_image_language={lang}.
    APPEND_LANG = 'append_lang'
    #: pull    - like `append` but gen images in next request if fails (no images)
    PULL = 'pull'
    #: full    - always make two requests, support all services (it is forced for non-tmdb services, e.g. fanart.tv)
    FULL = 'full'
    #: all     - use /images to get all images in concurrent request
    ALL = 'all'


class PersonCredits(NamedTuple):
    """Person credits result."""

    cast: Tuple[FFItem, ...] = ()
    crew: Tuple[FFItem, ...] = ()


class Condition(Generic[T]):
    """TMDB discovery conditions."""

    RX_EXPR: ClassVar[Pattern[str]] = re.compile(r'^\s*(\w+)\s*([<>=]=?)\s*(.*\S)\s*$')

    def __init__(self, type: Type[T], *, cond: Optional[List[Tuple[str, str]]] = None) -> None:
        self.type: Type[T] = type
        self.cond: List[Tuple[str, str]] = [] if cond is None else cond

    def range(self, min: T, max: T) -> 'Condition':
        return Condition(self.type, cond=[('gte', str(min)), ('lte', str(max))])

    def _add(self, val: T, a: int) -> T:
        if isinstance(val, dt_date):
            return val + timedelta(days=a)
        if isinstance(val, int):
            return val + a
        if isinstance(float, int):
            return val + .001 * a
        return val

    def __repr__(self) -> str:
        return f'Conditional(type={self.type}, cond={self.cond})'

    def __str__(self) -> str:
        s = ' & '.join(f'{k}={v}' for k, v in self.cond)
        return f'Conditional({s})'

    def __le__(self, other: T) -> 'Condition':
        if type(other) is not self.type:
            try:
                other = self.type(other)
            except Exception:
                return Condition(self.type)
        return Condition(self.type, cond=[('lte', str(other))])

    def __ge__(self, other: T) -> 'Condition':
        if type(other) is not self.type:
            try:
                other = self.type(other)
            except Exception:
                return Condition(self.type)
        return Condition(self.type, cond=[('gte', str(other))])

    def __lt__(self, other: T) -> 'Condition':
        if type(other) is not self.type:
            try:
                other = self.type(other)
            except Exception:
                return Condition(self.type)
        return Condition(self.type, cond=[('lte', str(self._add(other, -1)))])

    def __gt__(self, other: T) -> 'Condition':
        if type(other) is not self.type:
            try:
                other = self.type(other)
            except Exception:
                return Condition(self.type)
        return Condition(self.type, cond=[('gte', str(self._add(other, 1)))])

    def __and__(self, other: 'Condition[T]') -> 'Condition':
        if isinstance(other, Condition):
            return Condition(self.type, cond=[*self.cond, *other.cond])
        return NotImplemented

    @classmethod
    def filter_from_str_expr(cls, expr: str) -> Tuple[str, Union[str, Self, None]]:
        """Return condition from expr. Try use numbers."""
        if mch := cls.RX_EXPR.fullmatch(expr):
            a, o, b = mch.groups()
            if o in ('=', '=='):
                return a, b
            if o == '<':
                return a, cls(str) < b  # type: ignore [reportOperatorIssue]
            if o == '<=':
                return a, cls(str) <= b  # type: ignore [reportOperatorIssue]
            if o == '>':
                return a, cls(str) > b  # type: ignore [reportOperatorIssue]
            if o == '>=':
                return a, cls(str) >= b  # type: ignore [reportOperatorIssue]
        return expr, None

    @classmethod
    def filters_from_str_expr_list(cls, expresions: Iterable[str]) -> 'DiscoveryFilters':
        allowed = TmdbApi.DISCOVER_FILTERS
        filters = {k: v for val in expresions
                   for k, v in (cls.filter_from_str_expr(val),) if k in allowed and v is not None}
        return cast('DiscoveryFilters', filters)


# RangeCondition: TypeAlias = Annotated[T, Condition]


class DiscoveryFilters(TypedDict):
    """Filter arguments for TMDB discovery."""

    air_date: NotRequired[Condition[dt_date]]
    first_air_date: NotRequired[Condition[dt_date]]
    first_air_year: NotRequired[int]
    include_null_first_air_dates: NotRequired[bool]
    screened_theatrically: NotRequired[bool]
    timezone: NotRequired[str]
    with_networks: NotRequired[int]
    with_status: NotRequired[Union[str, Literal[0, 1, 2, 3, 4, 5]]]  # Returning Series: 0 Planned: 1 In Production: 2 Ended: 3 Cancelled: 4 Pilot: 5
    with_type: NotRequired[Union[str, Literal[0, 1, 2, 3, 4, 5, 6]]]

    certification: NotRequired[Union[str, Condition[str]]]
    certification_country: NotRequired[str]
    include_adult: NotRequired[bool]
    include_video: NotRequired[bool]
    language: NotRequired[str]
    primary_release_year: NotRequired[int]
    primary_release_date: NotRequired[Condition[dt_date]]
    region: NotRequired[str]
    release_date: NotRequired[Condition[dt_date]]
    sort_by: NotRequired[TmdbSortBy]
    vote_average: NotRequired[Condition[float]]
    vote_count: NotRequired[Condition[int]]
    watch_region: NotRequired[str]
    with_cast: NotRequired[str]
    with_companies: NotRequired[str]
    with_crew: NotRequired[str]
    with_genres: NotRequired[str]
    with_keywords: NotRequired[str]
    with_origin_country: NotRequired[str]
    with_original_language: NotRequired[str]
    with_people: NotRequired[str]
    with_release_type: NotRequired[Union[str, Literal[1, 2, 3, 4, 5, 6]]]
    with_runtime: NotRequired[Condition[int]]
    with_watch_monetization_types: NotRequired[Union[str, Literal['flatrate', 'free', 'ads', 'rent', 'buy']]]
    with_watch_providers: NotRequired[str]
    without_companies: NotRequired[str]
    without_genres: NotRequired[str]
    without_keywords: NotRequired[Union[str, int, Sequence[int]]]
    without_watch_providers: NotRequired[str]
    year: NotRequired[int]


class SearchFilters(TypedDict):
    """Filter arguments for TMDB search."""

    include_adult: NotRequired[bool]
    primary_release_year: NotRequired[int]
    year: NotRequired[int]
    first_air_date_year: NotRequired[int]
    region: NotRequired[str]


class TmdbRequestKwargs(TypedDict):
    credentials: NotRequired[Optional[TmdbCredentials]]
    api_version: NotRequired[Literal[3, 4]]
    params: NotRequired[Optional[KwArgs]]
    append_to_response: NotRequired[Tuple[str, ...]]
    lang: NotRequired[Optional[str]]
    expected_errors: NotRequired[Sequence[int]]
    cache: NotRequired[Optional[str]]


@define
class TmdbApiStats:
    request_count: int = 0
    extra_seasons_count: int = 0
    multi_seasons_count: int = 0


@define
class TmdbProvider:
    id: int
    name: str
    logo: Optional[str] = None
    display_priority: int = 0


@frozen (kw_only=True)
class MediaVideo:
    lang: str
    name: str
    key: str
    site: str
    type: str
    official: bool
    published_at: datetime

    # @property
    # def locale(self) -> str:
    #     return f'{self.lang}-{self.country}'


class SkelOptions(Flag):
    """TMDB skeleton options."""

    NONE = 0
    #: Get translate info.
    #: Not need to set, ffinfo.get_en_skel_items() sets is if `locale` is used.
    TRANSLATIONS = auto_enum()
    #: Get info for first few seasons.
    #: It is useful only if show has up to 18 seasons but it do not any extra request.
    SHOW_FIRST_SEASONS = auto_enum()
    #: Get info for last few seasons.
    #: Seasons details depend on number of seasons. Skel try to get a few first seasons (more then 18) with main show request.
    #: If there is more seasons skel request a few last seasons (more then 18), because now skel knows number of seasons.
    SHOW_LAST_SEASONS = auto_enum()
    #: Get info for all seasons.
    #: Skel try to get a few first seasons (more then 18) with main show request then requests next season group one by one.
    SHOW_ALL_SEASONS = auto_enum()
    #: Approximate the episode air date as season air date.
    #: It is used only if there is no the season's details.
    SHOW_EPISODE_DATE_FIRST = auto_enum()
    #: Approximate the episode air date as last emitted episode or day before next season air date.
    #: It is used only if there is no the season's details.
    SHOW_EPISODE_DATE_LAST = auto_enum()
    #: Approximate the episode air date as linear date between SHOW_EPISODE_DATE_FIRST and SHOW_EPISODE_DATE_LAST.
    #: It is used only if there is no the season's details.
    SHOW_EPISODE_DATE_APPROXIMATE = auto_enum()


class TmdbApi:
    """Base TBDB API."""

    # 2015:
    #   Movies - alternative_titles, changes, credits, images, keywords, lists, releases, reviews, similar, translations, videos
    #   TV - alternative_titles, changes, content_ratings, credits, external_ids, images, keywords, similar, translations, videos
    #   People - changes, combined_credits, external_ids, images, movie_credits, tagged_images, tv_credits
    # + (2015):
    #   genre_ids, original_language and overview

    DISCOVER_FILTERS = {
        'air_date.gte': dt_date,
        'air_date.lte': dt_date,
        'first_air_year': int,
        'first_air_date.gte': dt_date,
        'first_air_date.lte': dt_date,
        'include_null_first_air_dates': bool,
        'screened_theatrically': bool,
        'timezone': str,
        'with_networks': int,
        'with_status': Union[str, Literal[0, 1, 2, 3, 4, 5]],  # can be a comma (AND) or pipe (OR) separated query, can be used in conjunction with region
        'with_type': Union[str, Literal[0, 1, 2, 3, 4, 5, 6]],  # can be a comma (AND) or pipe (OR) separated query, can be used in conjunction with region

        'certification': str,
        'certification.gte': str,
        'certification.lte': str,
        'certification_country': str,
        'include_adult': bool,
        'include_video': bool,
        'language': str,
        'primary_release_year': int,
        'primary_release_date.gte': dt_date,
        'primary_release_date.lte': dt_date,
        'region': str,
        'release_date.gte': dt_date,
        'release_date.lte': dt_date,
        'sort_by': TmdbSortBy,
        'vote_average.gte': float,
        'vote_average.lte': float,
        'vote_count.gte': float,
        'vote_count.lte': float,
        'watch_region': str,
        'with_cast': str,  # can be a comma (AND) or pipe (OR) separated query
        'with_companies': str,  # can be a comma (AND) or pipe (OR) separated query
        'with_crew': str,  # can be a comma (AND) or pipe (OR) separated query
        'with_genres': str,  # can be a comma (AND) or pipe (OR) separated query
        'with_keywords': str,   # can be a comma (AND) or pipe (OR) separated query
        'with_origin_country': str,
        'with_original_language': str,
        'with_people': str,  # can be a comma (AND) or pipe (OR) separated query
        'with_release_type': Union[str, Literal[1, 2, 3, 4, 5, 6]],  # can be a comma (AND) or pipe (OR) separated query, can be used in conjunction with region
        'with_runtime.gte': int,
        'with_runtime.lte': int,
        'with_watch_monetization_types': Union[str, Literal['flatrate', 'free', 'ads', 'rent', 'buy']],  # use in conjunction with watch_region, can be a comma (AND) or pipe (OR) separated query
        'with_watch_providers': str,  # use in conjunction with watch_region, can be a comma (AND) or pipe (OR) separated query
        'without_companies': str,
        'without_genres': str,
        'without_keywords': Union[str, int, Sequence[int]],
        'without_watch_providers': str,
        'year': int,
        # --- conditional keywords ---
        'air_date': dt_date,
        'first_air_date': dt_date,
        'primary_release_date': Condition[str],
        'release_date': Condition[dt_date],
        'vote_average': Condition[float],
        'vote_count': Condition[float],
        'with_runtime': Condition[int],
    }

    # --- some dicovery conditions ---

    Date = Condition(dt_date)
    Int = Condition(int)
    Float = Condition(float)
    VoteCount = Int
    VoteAverage = Float
    Vote = VoteAverage
    Today = dt_date.today()
    Now = Today
    WeekAgo = Today - timedelta(days=7)

    # --- others ---

    EPISODE_TYPE_TO_FF: ClassVar[Dict[Optional[str], EpisodeType]] = {
        'finale': 'season_finale',  # of 'series_finale' for some tvshow statuses, see get_episode_type()
        'mid_season': 'mid_season_finale',
    }

    # --- internal ---

    _main2tmdb_type: Dict[MainMediaType, TmdbContentType] = {
        'movie': 'movie',
        'show': 'tv',
    }

    _main2tmdb_type2: Dict[MainMediaType, TmdbContentPluarType] = {
        'movie': 'movies',
        'show': 'tv',
    }

    _ext_id_results: Dict[RefType, str] = {
        'movie': 'movie_results',
        'show': 'tv_results',
        'season': 'tv_season_results',
        'episode': 'tv_episode_results',
        'person': 'person_results',
    }

    _search2tmdb: Dict[SearchType, Optional[TmdbSearchType]] = {
        'all': 'multi',
        'multi': 'multi',
        'movie': 'movie',
        'show': 'tv',
        'person': 'person',
        'collection': 'collection',
        'company': 'company',
        'keyword': 'keyword',
    }

    _person2ref: Dict[PersonDataType, RefType] = {
        'combined_credits': '',
        'movie_credits': 'movie',
        'tv_credits': 'show',
    }

    # NOT USED yet, got from https://developer.themoviedb.org/reference/movie-now-playing-list
    predef_lists = {
        'now_playing': 'include_adult=false&include_video=false&sort_by=popularity.desc&with_release_type=2|3&release_date.gte={min_date}&release_date.lte={max_date}',
        'popular': 'include_adult=false&include_video=false&sort_by=popularity.desc',
        'top_rated': 'include_adult=false&include_video=false&sort_by=vote_average.desc&without_genres=99,10755&vote_count.gte=200',
        'upcoming': 'include_adult=false&include_video=false&sort_by=popularity.desc&with_release_type=2|3&release_date.gte={min_date}&release_date.lte={max_date}',
    }

    Skel = SkelOptions

    _DEBUG_STATS: ClassVar[TmdbApiStats] = TmdbApiStats()
    _FAKE: ClassVar[bool] = False

    def __init__(self, api_key: Optional[str] = None, lang: Optional[str] = None, *,
                 auth_api_version: ApiVer = const.tmdb.auth.api, bearer: Optional[str] = None) -> None:
        #: TMDB base URL.
        self.base: str = 'https://api.themoviedb.org/'
        #: Base API version.
        self.auth_api_version: ApiVer = auth_api_version
        #: TMDB base URL for v3.
        self.base3: str = f'{self.base}3'
        #: TMDB base URL for v4.
        self.base4: str = f'{self.base}4'
        #: URL to image profile image.
        self.art_image_url: str = 'https://image.tmdb.org/t/p/w780'
        #: URL to image profile image.
        self.art_landscape_url: str = 'https://image.tmdb.org/t/p/w1280'
        #: URL to art image with formating.
        self.art_image_url_fmt: str = 'https://image.tmdb.org/t/p/{width}{path}'
        #: URL to person profile image.
        self.person_image_url: str = 'https://image.tmdb.org/t/p/w300_and_h450_bestv2'
        #: TMDB API key for direct use. If None, credentials() must be overloaded.
        self.api_key: Optional[str] = api_key
        #: TMDB API v4 auth bearer for direct use. If None, credentials() must be overloaded.
        self.bearer: Optional[str] = bearer
        #: TMDB response language.
        self.lang: Optional[str] = lang  # or 'pl-PL'
        #: Timestamp to hold requests until rate is enabled.
        self.hold_until: float = 0
        #: Internal lock to protect common data (like `hold_until`).
        self.lock = Lock()
        #: Semaphore to limit connections number.
        self.conn_semaphore = Semaphore(const.tmdb.connection.max or 1_000_000)
        #: HTTP sessions.
        self._sessions: dict[str, requests.Session] = {}

    def _update_lang(self, lang: Optional[str] = None) -> str:
        """Update language (from settings)."""
        if lang is None:
            if self.lang is None:
                from ..ff.control import apiLanguage
                self.lang = apiLanguage().get('tmdb', 'pl-PL')
            lang = self.lang
        return lang

    def _prepare_credentials(self, *, params: Optional[Params] = None, credentials: Optional[TmdbCredentials] = None) -> Tuple[Params, Headers]:
        """Helper. Prepare creadentials, params and headers."""
        if credentials is None:
            credentials = self.credentials()
        if params is None:
            params = {}
        headers = {
            'Accept': 'application/json',
        }
        if v4_bearer := credentials.bearer or self.bearer or const.dev.tmdb.v4.bearer or apis.tmdb_bearer:
            headers['Authorization'] = f'Bearer {v4_bearer}'
            if credentials.v4:
                headers['Authorization'] = f'Bearer {credentials.access_token}'
        if api_key := credentials.api_key or self.api_key or apis.tmdb_API:
            params.setdefault('api_key', api_key)
            if credentials.v3:
                params.setdefault('session_id', credentials.session_id)
        return params, headers

    def _honorate_rate_limit(self) -> None:
        """Honorate TMDB max rate limit. Sleep if limit is exceeded."""
        with self.lock:
            now = monotonic()
            delay = max(0, self.hold_until - now)
        if delay:
            xsleep(delay)

    def _process_status_code(self, status_code: int) -> bool:
        """Process REST status code and return True if got response, False if should repeat."""
        if status_code == 0:
            xsleep(const.trakt.connection.try_delay)
            return False
        # Connection Error | Rate Limit Exceeded
        elif status_code == 429:
            # See: https://developer.themoviedb.org/docs/rate-limiting
            fflog(f'[TMDB] Rate limit exceeded {status_code}')
            with self.lock:
                if not self.hold_until:
                    self.hold_until = monotonic() + const.trakt.connection.try_delay
            return False
        # Gateway Error - site is not avaliable
        elif status_code == 502:
            xsleep(5 * const.trakt.connection.try_delay)
            return False
        with self.lock:
            self.hold_until = 0
        return True

    def session(self, cache: CacheArg = None) -> requests.Session:
        if not const.tmdb.connection.common_session:
            return requests.Session(cache)
        if cache is False:
            cache_name = ''
        else:
            _, cache_name, _, _ = requests.cache_params(cache, None)
        try:
            return self._sessions[cache_name or '']
        except KeyError:
            pass
        self._sessions[cache_name or ''] = sess = requests.Session(cache)
        sess.mount(self.base, requests._requests.adapters.HTTPAdapter(pool_maxsize=100))
        return sess

    # @logtime
    def request(self,
                method: Method,
                url: str,
                *,
                credentials: Optional[TmdbCredentials] = None,
                api_version: Literal[3, 4] = 3,
                data: Optional[JsonData] = None,
                params: Optional[KwArgs] = None,
                append_to_response: Sequence[str] = (),
                lang: Optional[str] = None,
                errors: Literal['strict', 'ignore'] = 'ignore',
                expected_errors: Sequence[int] = (),
                cache: CacheArg = None,
                ) -> Optional[requests.Response]:
        """Request to API."""

        def cond_params(params: KwArgs) -> Generator[Tuple[str, Any], None, None]:
            for k, v in params.items():
                if isinstance(v, Condition):
                    for cmp, val in v.cond:
                        # if val is True:
                        #     val = 'true'
                        # elif val is False:
                        #     val = 'false'
                        yield f'{k}.{cmp}', val
                else:
                    # if v is True:
                    #     v = 'true'
                    # elif v is False:
                    #     v = 'false'
                    yield k, v

        if self._FAKE:
            return None
        url = urljoin(f'{self.base}/{api_version}/', url)
        # headers = {
        #     'Accept': 'application/json',
        # }
        # if credentials is None:
        #     credentials = self.credentials()

        # append_to_response = ['external_ids', 'release_dates', 'translations']  # 'images', 'original_language'
        params = dict(cond_params(params or {}))
        # if v4_bearer := credentials.bearer or self.bearer or const.dev.tmdb.v4.bearer or apis.tmdb_bearer:
        #     headers['Authorization'] = f'Bearer {v4_bearer}'
        #     if credentials.v4:
        #         headers['Authorization'] = f'Bearer {credentials.access_token}'
        # if api_key := credentials.api_key or self.api_key or apis.tmdb_API:
        #     params.setdefault('api_key', api_key)
        #     if credentials.v3:
        #         params.setdefault('session_id', credentials.session_id)
        params, headers = self._prepare_credentials(credentials=credentials, params=params)
        if params.get('page') == 0:
            params['page'] = 1
        if append_to_response:
            params.setdefault('append_to_response', ','.join(append_to_response))
        lang = self._update_lang(lang)
        if lang:
            params['language'] = lang
        fflog(f'[FF][TMDB] {url=}, {params=}')

        resp = None
        status_code: int = 0
        for _ in range(const.trakt.connection.try_count or 1):
            self._DEBUG_STATS.request_count += 1
            self._honorate_rate_limit()
            try:
                # resp = requests.request(method, url, json=data, params=params, headers=headers,
                #                         timeout=const.tmdb.connection.timeout, cache=cache)
                with self.conn_semaphore:
                    resp = self.session(cache).request(method, url, json=data, params=params, headers=headers, timeout=const.tmdb.connection.timeout)
                status_code = resp.status_code
            except requests.ConnectionError:
                status_code = 0
            except requests.RequestException:
                if errors != 'ignore':
                    raise
                status_code = 0
            if self._process_status_code(status_code):
                break

        if resp is None:
            return None

        # Success
        if 100 <= status_code <= 299:
            return resp

        if status_code >= 500:  # temporary
            if status_code not in expected_errors:
                fflog(f'[TMDB] Temporary error {status_code}')
            return None
        if status_code >= 400:  # permanent
            if status_code not in expected_errors:
                fflog(f'[TMDB] Error {status_code}\n{resp.text}')
            if status_code == 401:  # Authentication failed
                self.auth_failed()
            return None

    def get(self, url: str, **kwargs: Unpack[TmdbRequestKwargs]) -> Optional[JsonResult]:
        """Send GET request to tbdb.org and return JSON."""
        resp: Optional[requests.Response] = self.request('GET', url, data=None, **kwargs)
        if resp is None:
            return None
        return resp.json()

    def post(self, url: str, data: JsonData | None, **kwargs: Unpack[TmdbRequestKwargs]) -> Optional[JsonData]:
        """Send POST request to tbdb.org and return JSON."""
        resp: Optional[requests.Response] = self.request('POST', url, data=data, **kwargs)
        if resp is None:
            return None
        return resp.json()

    def delete(self, url: str, data: JsonData | None, **kwargs: Unpack[TmdbRequestKwargs]) -> Optional[JsonData]:
        """Send POST request to tbdb.org and return JSON."""
        resp: Optional[requests.Response] = self.request('DELETE', url, data=data, **kwargs)
        if resp is None:
            return None
        return resp.json()

    def auth(self, *, credentials: Optional[TmdbCredentials] = None, force: bool = False) -> bool:
        """Authorize user and create new session / token."""
        if self.auth_api_version == 3:
            return self.auth_v3(credentials=credentials, force=force)
        return self.auth_v4(credentials=credentials, force=force)

    def auth_v3(self, *, credentials: Optional[TmdbCredentials] = None, force: bool = False) -> bool:
        """Authorize user and create new v3 session."""
        if credentials is None:
            credentials = self.credentials()
        if not force and credentials:
            return True  # already authorized
        credentials = evolve(credentials, session_id=None)
        if not credentials.user or not credentials.password:
            return False
        data = self.get('authentication/token/new', credentials=credentials)
        if not isinstance(data, Mapping):
            return False
        token = data.get('request_token')
        if not token:
            return False
        data = self.post('authentication/token/validate_with_login', credentials=credentials, data={
            'username': credentials.user,
            'password': credentials.password,
            'request_token': token,
        })
        if not data:
            return False
        data = self.post('authentication/session/new', credentials=credentials, data={'request_token': token})
        if not isinstance(data, Mapping) or not data.get('success'):
            return False
        self.save_session(session_id=data['session_id'])
        return True

    def auth_v4(self, *, credentials: Optional[TmdbCredentials] = None, force: bool = False) -> bool:
        """Authorize user and create new v4 access token and v3 session."""
        if credentials is None:
            credentials = self.credentials()
        if not force and credentials.v3 and credentials.v4:
            return True  # already authorized
        if force:
            credentials = evolve(credentials, access_token=None, session_id=None)

        if not credentials.v4:
            start = monotonic()
            data = self.post('auth/request_token', data={}, api_version=4, credentials=credentials)
            if not isinstance(data, Mapping) or not data.get('success') or not (request_token := data.get('request_token')):
                fflog.info(f'TMDB auth (v4) FAILED: no request token')
                return False
            # Create (progress-bar) dialog.
            # print(f'https://www.themoviedb.org/auth/access?request_token={request_token}')
            expires_in = const.tmdb.auth.dialog_expire  # max 15 min
            interval = const.tmdb.auth.dialog_interval
            dialog = self.dialog_create(request_token=request_token, verification_url=f'https://www.themoviedb.org/auth/access?request_token={request_token}')
            # Continue as long as not expire or user authorized or user canceled.
            access_token: str = ''
            try:
                while True:
                    #: Current timestamp.
                    now: float = monotonic()
                    # check in expires...
                    if start + expires_in < now:
                        fflog.info(f'TMDB auth (v4) FAILED: no access token in {expires_in} seconds')
                        return False
                    # check if dialog is canceled
                    if self.dialog_is_canceled(dialog):
                        return False
                    if access_token := self._get_access_token(request_token, credentials=credentials):
                        break
                    # update progress-bar
                    self.dialog_update_progress(dialog, 100 * (now - start) / expires_in)
                    # sleep given interval
                    xsleep(interval)
            except KeyboardInterrupt:
                print('''\nCancelled. Enter '0'.\n''')
            finally:
                # finish - close dialog
                self.dialog_close(dialog)
            if not access_token:
                return False
            credentials = evolve(credentials, access_token=access_token)

        if not credentials.v3:
            data = self.post('authentication/session/convert/4', data={'access_token': credentials.access_token}, credentials=credentials)
            if not isinstance(data, Mapping) or not data.get('success') or not (session_id := data.get('session_id')):
                fflog.info(f'TMDB auth (v4) FAILED: no v3 session id')
                return False
            credentials = evolve(credentials, session_id=session_id)

        self.save_session(access_token=credentials.access_token, session_id=credentials.session_id)
        return True

    def _get_access_token(self, request_token: str, *, credentials: Optional[TmdbCredentials] = None) -> str:
        """Retrive access_token if request_token is accepted by user (on web site)."""
        data = self.post('auth/access_token', data={}, params={'request_token': request_token}, api_version=4,
                         credentials=credentials, expected_errors=[422])
        # access_token, account_id (can be obtain from access_token)
        if isinstance(data, Mapping) and data.get('success') and (access_token := data.get('access_token')):
            return access_token
        return ''

    def revoke_session(self, *, credentials: Optional[TmdbCredentials] = None) -> bool:
        """Revoke the session (logout user)."""
        if credentials is None:
            credentials = self.credentials()
        if not credentials:
            return True  # no session, already done
        success = True
        if credentials.v4:
            data = self.delete('auth/access_token', data={'access_token': credentials.access_token}, api_version=4)
            if not isinstance(data, Mapping) or not data.get('success'):
                success = False
        if credentials.v3:
            data = self.delete('authentication/session', credentials=credentials, data={'session_id': credentials.session_id})
            if not isinstance(data, Mapping) or not data.get('success'):
                success = False
        self.save_session(session_id=None, access_token=None)  # forgot session_id (v3) and access_token (v4)
        return success

    unauth = revoke_session

    def _ref_id_to_tmdb(self, ref_id: T, /) -> T:
        if isinstance(ref_id, int) and ref_id in VideoIds.TMDB:
            ref_id = VideoIds.TMDB.index(ref_id)
        return ref_id

    def _parse_art(self, *, item: JsonData, translate_order: Sequence[str], skip_fanart: bool) -> Dict[str, str]:
        """Pre-parse art images. Much simpler verison of Art.parse_art()."""
        from ..ff.art import TmbdArtService
        images = item.get('images') or {}
        art_langs = (*dict.fromkeys(loc.partition('-')[0] for loc in translate_order), *(None,))
        no_langs = ('00', 'xx', 'null', None)
        art: Dict[str, str] = {}
        for aname, artdef in TmbdArtService.art_names.items():
            for src in artdef.sources:
                ilist = images.get(src.key)
                if ilist:
                    for lng in artdef.langs(yes=art_langs, no=no_langs, skip_fanart=skip_fanart):
                        for ielem in ilist:
                            if ielem.get('iso_639_1') == lng and (path := ielem['file_path']):
                                art[aname] = f'{self.art_image_url}{path}'
                                break
                        else:
                            continue
                        break
                    else:
                        continue
                    break
        return art

    @requests.netcache('media')
    def get_media_by_ref(self, ref: FFRef, *, tv_episodes: bool = False,
                         seasons: Optional[Iterable[int]] = None,
                         credentials: Optional[TmdbCredentials] = None) -> TmdbItemJson:
        """Get single media by reference."""
        # @requests.netcache('media')
        def get(path: str, par: Optional[Dict[str, Any]] = None):
            if par is None:
                par = params
            fflog(f'[FF][TMDB] {path=}, params={par!r}')
            self._DEBUG_STATS.request_count += 1
            self._honorate_rate_limit()
            if TYPE_CHECKING:
                status_code, resp = 0, requests.Response()
            for _ in range(const.trakt.connection.try_count or 1):
                try:
                    resp = requests.get(f'{self.base3}/{path}', params=par, headers=headers, timeout=const.tmdb.connection.timeout)
                    status_code = resp.status_code
                except (requests.ConnectionError, requests.RequestException):
                    status_code = 0
                except Exception as exc:
                    fflog(f'TMDB get failed: {exc}, url={self.base3}/{path}, params={params}')
                    raise
                if self._process_status_code(status_code):
                    break
            if status_code >= 400:
                fflog(f'[FF][TMDB] ERROR {status_code} for {path}')
            return resp.json()

        tv_seasons = tuple(seasons or ())
        ref = ref.ref
        rtype = ref.real_type
        cred_params, headers = self._prepare_credentials(credentials=credentials)
        params = dict(cred_params)
        imode = GetImageMode(const.tmdb.get_image_mode)
        respapp = ['external_ids', 'release_dates', 'translations', 'videos', 'keywords']
        if imode in (GetImageMode.APPEND, GetImageMode.APPEND_EN, GetImageMode.APPEND_LANG, GetImageMode.PULL):
            respapp.append('images')
        if ref.real_type in ('show', 'season'):
            respapp.append('aggregate_credits')
        elif ref.real_type in ('movie', 'episode'):
            respapp.append('credits')
        # append a few seasons with episodes to single request (sic!)
        scount: int = 0
        if tv_episodes and rtype == 'show':  # append a few existing seasons with episodes to single request (sic!)
            # see: https://www.themoviedb.org/talk/63ee22b4699fb7009e3e5102
            respapp.extend(f'season/{i+1}' for i in range(const.tmdb.append_seasons_count))
        if tv_seasons and rtype == 'show':  # append a few requestet seasons to single request (sic!)
            scount = const.tmdb.append_seasons_count
            respapp.extend(f'season/{i}' for i in tv_seasons[:scount])
            tv_seasons = tv_seasons[scount:]
        params['append_to_response'] = ','.join(respapp)
        lang = self._update_lang()
        if self.lang:
            params['language'] = self.lang
        if 'images' in respapp:
            lang = self.lang.partition('-')[0] if self.lang else 'en'
            if imode is GetImageMode.APPEND_EN:
                params['include_image_language'] = 'en'
            elif imode is GetImageMode.APPEND_LANG:
                params['include_image_language'] = lang
            else:
                params['include_image_language'] = ','.join(dict.fromkeys((lang, 'en', 'null')))
        if 'videos' in respapp:
            lang = self.lang.partition('-')[0] if self.lang else 'en'
            params['include_video_language'] = ','.join(dict.fromkeys((lang, 'en', 'null')))
        if ref.type == 'movie':
            path = f'movie/{ref.tmdb_id}'
        elif ref.type == 'show':
            path = '/'.join(f'{k}{v}' for k, v in zip(['tv/', 'season/', 'episode/'], ref.tmdb_tv_tuple))
        elif ref.type in ('person', 'collection'):
            path = f'{ref.type}/{ref.tmdb_id}'
        else:
            # non DetailsAllowed type
            raise ValueError(f'Unsupported TMDB media type {ref.type}, can NOT use season or episode ID or else')

        # receive tmdb data with images
        if imode is GetImageMode.ALL:
            with RequestsPoolExecutor(max_thread_workers()) as ex:
                obj = ex.submit(get, path)
                img = ex.submit(get, f'{path}/images', cred_params)
            data = obj.result()
            data['images'] = img.result()

        else:
            data: JsonData = get(path)
            if imode is GetImageMode.PULL:
                orig_lang: str = data.get('original_language', 'en')
                trans_order = tuple(dict.fromkeys((self._update_lang(), lang, 'en-US', 'en-GB', 'en',
                                                   *(f'{orig_lang}-{c}' for c in data.get('origin_country', ())), orig_lang)))
                art = self._parse_art(item=data, translate_order=trans_order, skip_fanart=ref.is_episode)
                if not all(art.get(a) for a in ('fanart', 'landscape', 'poster', 'clearlogo')):
                    data['images'] = get(f'{path}/images', {'api_key': credentials.api_key})

        # fix up extra seasons and theirs episodes
        if (tv_episodes or tv_seasons) and rtype == 'show':
            # get missing seasons (if more then const.tmdb.append_seasons_count)
            if tv_episodes:
                seasons_need = {sz['season_number'] for sz in data.get('seasons', ())}
            else:
                seasons_need = set(tv_seasons)
            seasons_got = {int(sznum) for asz in data if asz.startswith('season/') if (sznum := asz.partition('/')[2]).isdigit()}
            missing_seasons = seasons_need - seasons_got
            if missing_seasons:
                data2: JsonData
                self._DEBUG_STATS.extra_seasons_count += 1
                scount = const.tmdb.append_seasons_max_count
                if len(missing_seasons) > scount:
                    def get_seasons(nums):
                        sz_params = {**params, 'append_to_response': ','.join(f'season/{sz}' for sz in nums)}
                        return get(path, sz_params)

                    self._DEBUG_STATS.multi_seasons_count += 1
                    with RequestsPoolExecutor(max_thread_workers()) as ex:
                        for data2 in ex.map(get_seasons, batched(missing_seasons, scount)):
                            if isinstance(data2, Mapping) and data2.get('success', True):
                                data.update(data2)
                else:
                    # get extra info about missing show seasons
                    params['append_to_response'] = ','.join(f'season/{sz}' for sz in missing_seasons)
                    data2 = get(path)
                    if isinstance(data2, Mapping) and data2.get('success', True):
                        data.update(data2)

        # udpate main season list
        if rtype == 'show':
            for sz in data.get('seasons') or ():
                num: int = sz['season_number']
                sz['_ref'] = ref.with_season(num)
                sz['_type'] = 'season'
                if ex := data.get(f'season/{num}'):
                    sz.update(ex)

        data['_ref'] = ref
        data['_type'] = rtype
        if rtype == 'episode':
            if tv_vid := VideoIds.from_ffid(ref.ffid):
                data.setdefault('show_id', tv_vid.tmdb)
        return data

    # @logtime
    def get_media_list_by_ref(self, refs: Sequence[MediaRef], *, tv_episodes: bool = False,
                              credentials: Optional[TmdbCredentials] = None) -> List[TmdbItemJson]:
        """Get list of media by theris references."""
        def get(ref):
            return self.get_media_by_ref(ref, tv_episodes=tv_episodes, credentials=credentials)

        if credentials is None:
            credentials = self.credentials()
        with RequestsPoolExecutor(max_thread_workers()) as ex:
            jobs = ex.map(get, refs)
        return list(jobs)

    # @logtime
    def get_media_dict_by_ref(self, refs: Sequence[MediaRef], *, tv_episodes: bool = False, optimize: bool = False,
                              credentials: Optional[TmdbCredentials] = None) -> Dict[MediaRef, TmdbItemJson]:
        """Get dict of media by theris references."""
        def get(ref):
            if optimize and ref.is_show:
                seasons = show_seasons.get(ref)
            else:
                seasons = None
            return self.get_media_by_ref(ref, tv_episodes=tv_episodes, credentials=credentials, seasons=seasons)

        # optimize requests, to get seasons inside shows
        if optimize:
            show_seasons: Dict[MediaRef, Set[int]] = {ref: set() for ref in refs if ref.is_show}
            for ref in refs:
                if ref.is_season and (show_ref := ref.show_ref) and (nums := show_seasons.get(show_ref)) is not None:
                    assert ref.season is not None
                    nums.add(ref.season)
            refs = [ref for ref in refs if not ref.is_season or ref.show_ref not in show_seasons]
        # get items
        if credentials is None:
            credentials = self.credentials()
        if len(refs) == 1:
            jobs = [get(refs[0])]
        else:
            with RequestsPoolExecutor(max_thread_workers()) as ex:
                jobs = ex.map(get, refs)
        if optimize:
            def scan_items(item: JsonData) -> Iterator[JsonData]:
                yield item
                for sz in item.get('seasons', ()):
                    num = sz['season_number']
                    if item.get(f'season/{num}'):
                        yield sz
            return {it['_ref']: it for item in jobs for it in scan_items(item)}
        else:
            return {it['_ref']: it for it in jobs}

    def list_refs(self, type: RefType, items: Sequence[Union[JsonData, FFItem]]) -> List[MediaRef]:
        """Get refs from media item list."""
        if items:
            elem = items[0]
            if isinstance(elem, (FFItem, MediaRef)):
                return [it.ref for it in cast(Sequence[FFItem], items)]
            if isinstance(elem, Mapping):
                return [MediaRef.from_tmdb(type, it.get('id', 0), season=None, episode=None) for it in items]
        return []

    def get_skel_en_media(self,
                          refs: Sequence[MediaRef],
                          *,
                          options: SkelOptions = SkelOptions.SHOW_LAST_SEASONS,
                          credentials: Optional[TmdbCredentials] = None,
                          ) -> Dict[MediaRef, TmdbItemJson]:
        """Load skeleton media info."""

        def req(path: str, *, params: Params, append: Sequence[str] = ()):
            params = {**params, 'append_to_response': ','.join(append)}
            fflog(f'[FF][TMDB] {path=}, params={params!r}')
            self._DEBUG_STATS.request_count += 1
            if TYPE_CHECKING:
                status_code, resp = 0, requests.Response()
            for _ in range(const.trakt.connection.try_count or 1):
                self._honorate_rate_limit()
                try:
                    resp = requests.get(f'{self.base3}/{path}', params=params, headers=headers, timeout=const.tmdb.connection.timeout)
                    status_code = resp.status_code
                except (requests.ConnectionError, requests.RequestException):
                    status_code = 0
                if self._process_status_code(status_code):
                    break
            if resp.status_code >= 400:
                fflog(f'[FF][TMDB] ERROR {resp.status_code} for {path}')
            return resp.json()

        def get(ref: MediaRef, par: Optional[Dict[str, Any]] = None) -> TmdbItemJson:
            if par is None:
                par = params
            rtype = ref.real_type
            r_append = list(append_to_response)

            append_season_number = 0
            if ref.type == 'movie':
                path = f'movie/{ref.tmdb_id}'
            elif ref.type == 'show':
                # path = '/'.join(f'{k}{v}' for k, v in zip(['tv/', 'season/', 'episode/'], ref.tmdb_tv_tuple))
                path = f'tv/{ref.tmdb_id}'
                if ref.season:  # season and episode
                    r_append.append(f'season/{ref.season}')
                elif options & APPEND_SEASONS:
                    # try to match first 10 seasons, hope that it will be all seasons (then the last too)
                    if len(r_append) < const.tmdb.append_seasons_max_count:
                        append_season_number = const.tmdb.append_seasons_max_count - len(r_append)
                        r_append.extend(f'season/{i}' for i in range(1, append_season_number + 1))
            elif ref.type in ('person', 'collection'):
                path = f'{ref.type}/{ref.tmdb_id}'
            else:
                # non DetailsAllowed type
                raise ValueError(f'Unsupported TMDB media type {ref.type}, can NOT use season or episode ID or else')
            data = req(path, params=par, append=r_append)
            data['_ref'] = ref
            data['_type'] = rtype
            last_season_number = max(z['season_number'] for z in data.get('seasons', ())) if ref.is_show else 0
            # obtain all seasons
            if last_season_number and options & SkelOptions.SHOW_ALL_SEASONS:
                for s_nums in batched(range(append_season_number, last_season_number), const.tmdb.append_seasons_max_count):
                    r_append = [f'season/{i+1}' for i in s_nums]
                    s_data = req(path, params=par, append=r_append)
                    for key in r_append:
                        data[key] = s_data[key]
            # obtain a last few seasons (if not received already)
            elif last_season_number and options & SkelOptions.SHOW_LAST_SEASONS and last_season_number > append_season_number:
                r_append = [f'season/{i+1}'
                            for i in range(max(append_season_number, last_season_number - const.tmdb.append_seasons_max_count), last_season_number)]
                s_data = req(path, params=par, append=r_append)
                for key in r_append:
                    data[key] = s_data[key]
            if rtype == 'episode':
                if tv_vid := VideoIds.from_ffid(ref.ffid):
                    data.setdefault('show_id', tv_vid.tmdb)
            return data

        APPEND_SEASONS = SkelOptions.SHOW_FIRST_SEASONS | SkelOptions.SHOW_LAST_SEASONS | SkelOptions.SHOW_ALL_SEASONS;
        if credentials is None:
            credentials = self.credentials()
        cred_params, headers = self._prepare_credentials(credentials=credentials)
        append_to_response = ['external_ids']
        params = {
            **cred_params,
            # 'language': 'en-US',
        }
        if options & SkelOptions.TRANSLATIONS:
            append_to_response.append('translations')

        if not refs:
            return {}
        if len(refs) == 1:
            ref = refs[0]
            return {ref: get(ref)}
        with RequestsPoolExecutor(min(max_thread_workers(), const.tmdb.skel_max_threads)) as ex:
            jobs = ex.map(get, refs)
        return {ref: item for ref, item in zip(refs, jobs)}

    def parse_episode_type(self, item: JsonData, *, tvshow_status: str = '') -> EpisodeType:
        """Determine episode type."""
        if etype := item.get('episode_type'):
            if etype == 'finale':  # season or tvshow
                if tvshow_status.lower() in ('ended', 'canceled', 'canceled'):
                    return 'series_finale'
        return self.EPISODE_TYPE_TO_FF.get(etype, '')

    def _item_list(self, type: Union[RefType, SearchType], data: Optional[JsonResult], *,
                   key: str = 'results', out_type: Optional[RefType] = None) -> ItemList[FFItem]:
        """Return item list with pagination."""

        def parse(it: JsonData) -> FFItem:
            def set_if(setter: Callable, key: Union[str, Sequence[str]]) -> None:
                if isinstance(key, str):
                    key = (key,)
                for k in key:
                    val = it.get(k)
                    if val is not None and val != '':
                        setter(val)
                        return

            mtype: RefType = it.get('media_type', out_type)
            if mtype == 'tv':
                mtype = 'show'
            if out_type == 'movie' and 'media_type' not in it and 'genre_ids' not in it and 'popularity' not in it:
                mtype = 'collection'  # hack, searching movies returns collections
            ref = MediaRef.from_tmdb(mtype, it.get('id') or 0)
            it['_ref'] = ref
            ff = FFItem(ref)
            ff.source_data = it
            vtag = ff.vtag
            ff.label = ff.title = it.get('title', it.get('name')) or ''
            set_if(vtag.setOriginalTitle, 'original_name')
            set_if(vtag.setPlot, 'description')
            set_if(vtag.setPlot, 'overview')
            set_if(vtag.setPremiered, ('release_date', 'created_at'))
            set_if(vtag.setFirstAired, 'first_air_date')
            if date := ff.date:
                vtag.setYear(date.year)
            # set_if(vtag.set..., 'popularity')
            vtag.setRatings({'tmdb': (it.get('vote_average', 0.0), it.get('vote_count', 0))}, 'tmdb')
            if ref.is_show:
                set_if(vtag.setSeriesStatus, 'status')
            if episode_type := self.parse_episode_type(it):
                vtag.setEpisodeType(episode_type)
            ff.role = it.get('character', it.get('job', ''))
            art = {}
            if poster := it.get('poster_path', it.get('logo_path')):
                art['poster'] = f'{self.person_image_url}/{poster}'
            if fanart := it.get('backdrop_path'):
                fanart = f'{self.art_landscape_url}{fanart}'
                art['fanart'] = fanart
                art.setdefault('landscape', fanart)
            if not art.get('thumb') and (thumb := art.get('landscape' if ref.is_episode else 'poster')):
                art['thumb'] = thumb
            if art:
                ff.setArt(art)
            if count := it.get('number_of_items'):
                ff._children_count = count
            if (val := it.get('public')) is not None:
                ff.temp.public = val
            return ff

        if out_type is None:
            out_type = type

        if isinstance(data, Mapping):
            return ItemList([parse(it) for it in data.get(key, ())], page=data.get('page', 0),
                            total_pages=data.get('total_pages', 0), total_results=data.get('total_results', 0))

        if isinstance(data, Sequence) and not isinstance(data, str):
            return ItemList([parse(it) for it in data], page=1, total_pages=1, total_results=len(data))

        return ItemList.empty()

    def get_videos(self, ref: MediaRef) -> ...:
        if ref.type == 'movie':
            path = f'movie/{ref.tmdb_id}'
        elif ref.type == 'show':
            path = '/'.join(f'{k}{v}' for k, v in zip(['tv/', 'season/', 'episode/'], ref.tmdb_tv_tuple))
        else:
            raise ValueError(f'Unsupported TMDB media type {ref.type}, can NOT use season or episode ID or else')
        lang = self._update_lang()
        trailers_lang_priority = {lang.partition('-')[0]: 0, 'en': 1}
        result = self.get(f'{path}', append_to_response=('videos',), params={'include_video_language': f'{lang},en-US,en-GB'})
        items = sorted(
            result['videos']['results'],
            key=lambda t: (not t.get('official', False), t['type'] != 'Trailer', trailers_lang_priority.get(t['iso_639_1']), t.get('published_at', ''))
        )
        return [MediaVideo(lang=it['iso_639_1'], name=it['name'], key=it['key'], site=it['site'], type=it['type'], official=it['official'], published_at=fromisoformat(it['published_at'])) for it in items]


    # --- General API ---

    @requests.netcache('discover')
    def discover(self,
                 type: MainMediaType,
                 *,
                 page: int = 1,
                 # all filter paramaters from https://developer.themoviedb.org/reference/discover-movie
                 **kwargs: Unpack[DiscoveryFilters],
                 ) -> ItemList[FFItem]:
        """Discover media."""
        if type not in get_typing_args(MainMediaType):
            raise ValueError(f'TmdbApi.discover() got incorrect type {type!r}')
        try:
            ctype = self._main2tmdb_type[type]
        except KeyError:
            return ItemList.empty()

        allowed = set(self.DISCOVER_FILTERS)
        if kwargs.keys() - allowed:
            wrong = ', '.join(kwargs.keys() - allowed)
            raise TypeError(f'TmdbApi.discover() unknown filter params: {wrong}')

        params = {}
        if const.tmdb.avoid_keywords:
            kwargs.setdefault('without_keywords', const.tmdb.avoid_keywords)
        for k, v in kwargs.items():
            if v is not None:
                if not isinstance(v, str) and isinstance(v, Sequence):
                    v = '|'.join(map(str, v))
                params[k] = v
        params['page'] = page
        # data: Optional[JsonData] = cast(Optional[JsonData], self.get(type, params=params))
        return self._item_list(type, self.get(f'discover/{ctype}', params=params))

    @requests.netcache('discover')
    def discover_list(self,
                      type: MainMediaType,
                      list: TmdbListType,
                      *,
                      page: int = 1,
                      region: Optional[str] = None,
                      ) -> ItemList:
        """Discover media list (tweaked discover)."""
        if type not in get_typing_args(MainMediaType):
            raise ValueError(f'TmdbApi.discover() got incorrect type {type!r}')
        if list not in get_typing_args(TmdbListType):
            raise ValueError(f'TmdbApi.discover() got incorrect list {list!r}')
        try:
            ctype = self._main2tmdb_type[type]
        except KeyError:
            return ItemList.empty()

        params: Dict[str, Any] = {'page': page}
        if region:
            params['region'] = region
        return self._item_list(type, self.get(f'{ctype}/{list}', params=params))

    @requests.netcache('discover')
    def trending(self,
                 type: MainMediaType,
                 time: TimeWindow = 'week',
                 *,
                 page: int = 1,
                 ) -> ItemList:
        if type not in get_typing_args(MainMediaType):
            raise ValueError(f'TmdbApi.trending() got incorrect type {type!r}')
        if time not in get_typing_args(TimeWindow):
            raise ValueError(f'TmdbApi.trending() got incorrect time window {time!r}')
        ctype = self._main2tmdb_type[type]

        params: Dict[str, Any] = {'page': page}
        return self._item_list(type, self.get(f'trending/{ctype}/{time}', params=params))
        # Daily Trending
        # https://api.themoviedb.org/3/trending/movie/day?api_key=###
        # https://api.themoviedb.org/3/trending/tv/day?api_key=###
        # https://api.themoviedb.org/3/trending/person/day?api_key=###
        # https://api.themoviedb.org/3/trending/all/day?api_key=###
        # Weekly Trending
        # https://api.themoviedb.org/3/trending/movie/week?api_key=###
        # https://api.themoviedb.org/3/trending/tv/week?api_key=###
        # https://api.themoviedb.org/3/trending/person/week?api_key=###
        # https://api.themoviedb.org/3/trending/all/weekly?api_key=###

    @requests.netcache('art')
    def configuration(self, name: TmdbConfName) -> Sequence[JsonData]:
        """Get configuration lists like countries, languages etc."""
        data = self.get(f'configuration/{name}')
        if isinstance(data, Sequence):
            return data
        return []

    @requests.netcache('art')
    def genres(self, type: MainMediaType) -> List[JsonData]:
        """Get genres lists."""
        if type not in get_typing_args(MainMediaType):
            raise ValueError(f'TmdbApi.genres() got incorrect type {type!r}')
        ctype = self._main2tmdb_type[type]

        data = self.get(f'genre/{ctype}/list')
        if isinstance(data, Mapping):
            return data['genres']
        return []

    def find_id(self, source: ExternalIdType, id: Union[int, str]) -> Optional[MediaRef]:
        """Find external id."""
        data = self.get(f'find/{id}', params={'external_source': f'{source}_id'})
        if not isinstance(data, Mapping):
            return None
        for mtype, key in self._ext_id_results.items():
            if data.get(key):
                data = data[key][0]
                return MediaRef.from_tmdb(mtype, data['id'], data.get('season_number'), data.get('episode_number'))

    def find_ids(self, source: ExternalIdType, ids: Iterable[Union[int, str]]) -> Sequence[Optional[MediaRef]]:
        """Find list of external id."""
        def get(id: Union[int, str]) -> Optional[MediaRef]:
            return self.find_id(source, id)

        with RequestsPoolExecutor(max_thread_workers()) as ex:
            jobs = ex.map(get, ids)
        return list(jobs)

    def find_mixed_ids(self, ids: Iterable[Tuple[ExternalIdType, Union[int, str]]]) -> Sequence[Optional[MediaRef]]:
        """Find list of external id as list of (source, id)."""
        def get(args: Tuple[ExternalIdType, Union[int, str]]) -> Optional[MediaRef]:
            src, id = args
            return self.find_id(src, id)

        with RequestsPoolExecutor(max_thread_workers()) as ex:
            jobs = ex.map(get, ids)
        return list(jobs)

    @requests.netcache('search')
    def search(self,
               type: SearchType,
               query: str,
               *,
               page: int = 1,
               **kwargs: Unpack[SearchFilters],
               ) -> ItemList[FFItem]:
        """Search items."""
        stype = self._search2tmdb.get(type)
        if not stype:
            return ItemList.empty()
        params = {'page': page, 'query': query, **kwargs}
        return self._item_list(type, self.get(f'search/{stype}', params=params))

    def person_credits(self, person_id: int, type: PersonDataType) -> PersonCredits:
        """Get person credits."""
        mtype = self._person2ref[type]
        person_id = self._ref_id_to_tmdb(person_id)
        data = self.get(f'person/{person_id}/{type}')
        if isinstance(data, Mapping):
            return PersonCredits(cast=tuple(self._item_list(mtype, data.get('cast', ()))),
                                 crew=tuple(self._item_list(mtype, data.get('crew', ()))))
        return PersonCredits()

    def collection_items(self, collection_id: int) -> Sequence[FFItem]:
        """Get collection's items."""

        def parse(it: JsonData) -> FFItem:
            mtype = it.get('media_type', 'movie')
            if mtype == 'tv':
                mtype = 'show'
            ref = MediaRef.from_tmdb(mtype, it['id'])
            ff = FFItem(ref)
            ff.title = it.get('title') or ''
            ff.vtag.setOriginalTitle(it.get('original_title') or '')
            if poster := it.get('poster_path'):
                ff.setArt({'poster': f'{self.art_image_url}{poster}'})
            return ff

        collection_id = self._ref_id_to_tmdb(collection_id)
        data = self.get(f'collection/{collection_id}')
        if isinstance(data, Mapping):
            return [parse(it) for it in data.get('parts', ())]
        return []

    def media_resource(self, ref: MediaRef, resource: MediaResource, *, page: int = 1) -> List[FFItem]:
        """Get media (movie, show) resource."""
        if ref.type not in get_typing_args(MainMediaType):
            raise ValueError(f'TmdbApi.media_resource() got incorrect type {ref.type!r}')
        if resource not in get_typing_args(MediaResource):
            raise ValueError(f'TmdbApi.media_resource() got incorrect resource {resource!r}')
        try:
            mtype = cast(MainMediaType, ref.type)
            ctype = self._main2tmdb_type[mtype]
        except KeyError:
            return ItemList.empty()

        params = {'page': page}
        return self._item_list(mtype, self.get(f'{ctype}/{ref.tmdb_id}/{resource}', params=params))

    def media_keywords(self, ref: MediaRef) -> List[FFItem]:
        """Get media (movie, show) resource."""
        if ref.type not in get_typing_args(MainMediaType):
            raise ValueError(f'TmdbApi.media_resource() got incorrect type {ref.type!r}')
        try:
            mtype = cast(MainMediaType, ref.type)
            ctype = self._main2tmdb_type[mtype]
        except KeyError:
            return ItemList.empty()

        return self._item_list(mtype, self.get(f'{ctype}/{ref.tmdb_id}/keywords'), key='keywords', out_type='keyword')

    @requests.netcache('lists')
    def user_lists(self, account_id: AccountId = 'me', *, page: int = 1, api: ApiVer = None) -> List[FFItem]:
        """Get user lists."""
        account_id = self._ref_id_to_tmdb(account_id)
        if (credentials := self.credentials()).v4 and api != 3 and account_id == 'me':
            data = self.get(f'account/{credentials.account_id}/lists', params={'page': page}, api_version=4)
        elif credentials.v3 and api != 4:
            data = self.get(f'account/{account_id}/lists', params={'page': page})
        else:
            return ItemList.empty()
        return self._item_list('list', data)

    @requests.netcache('lists')
    def user_list_items(self, list_id: int, *, page: int = 1, api: ApiVer = None) -> ItemList[FFItem]:
        """Get user lists."""
        list_id = self._ref_id_to_tmdb(list_id)
        if (credentials := self.credentials()).v4 and api != 3:
            data = self.get(f'list/{list_id}', params={'page': page}, api_version=4)
            return self._item_list('', data)
        if credentials.v3 and api != 4:
            data = self.get(f'list/{list_id}', params={'page': page})
            return self._item_list('', data, key='items')
        return ItemList.empty()

    def _user_list_items_param(self, items: Iterable[FFRef]) -> list[dict[str, str | int]]:
        """Prepare items for user list API."""
        m2t = {
            **self._main2tmdb_type,
            # 'season': 'tv',   # add season's show
            # 'episode': 'tv',  # add epsiode's show
        }
        param = [{
            'media_type': media,
            'media_id': tmdb_id,
        } for it in items if (tmdb_id := (ref := it.ref).tmdb_id) and (media := m2t.get(ref.real_type))]
        return param

    def add_to_user_list(self, list_id: int, items: Iterable[FFRef]) -> int:
        """Add items to the list and return number of added items. Support only v4."""
        list_id = self._ref_id_to_tmdb(list_id)
        if not isinstance(items, Sequence):
            items = tuple(items)
        if not items:
            return True
        to_add = self._user_list_items_param(items)
        if not to_add:
            return False
        data = self.post(f'list/{list_id}/items', data={'items': to_add}, api_version=4)
        if not isinstance(data, Mapping) or not data.get('success'):
            return False
        clear_netcache('lists')
        return sum(res['success'] for res in data['results'])

    def remove_from_user_list(self, list_id: int, items: Iterable[FFRef]) -> int:
        """Remove items tfrom the list and return number of removed items. Support only v4."""
        list_id = self._ref_id_to_tmdb(list_id)
        if not isinstance(items, Sequence):
            items = tuple(items)
        if not items:
            return True
        to_remove = self._user_list_items_param(items)
        if not to_remove:
            return False
        data = self.delete(f'list/{list_id}/items', data={'items': to_remove}, api_version=4)
        if not isinstance(data, Mapping) or not data.get('success'):
            return False
        clear_netcache('lists')
        return sum(res['success'] for res in data['results'])

    def create_user_list(self, name: str, *, descr: str = '', public: bool = True, locale: Optional[str] = None, api: ApiVer = None) -> Optional[int]:
        """Create user list and return its ID."""
        # XXX XXX XXX   ----   TMDB (v4) ignores "public": false !!!!  ----   XXX XXX XXX
        if not name:
            raise ValueError('TmdbApi.create_user_list() requires name')
        if locale is None:
            locale = self.lang or 'pl-PL'
        country, _, lang = locale.partition('-')
        if (credentials := self.credentials()).v4 and api != 3:
            d = {'name': name, 'description': descr, 'public': public, 'iso_3166_1': country, 'iso_639_1': lang}
            fflog(f'new list data: {d}')
            data = self.post('list', data={'name': name, 'description': descr, 'public': public,
                                           'iso_3166_1': country, 'iso_639_1': lang}, api_version=4)
        elif credentials.v3 and api != 4:
            data = self.post('list', data={'name': name, 'description': descr, 'language': lang}, api_version=3)
        else:
            return None
        if isinstance(data, Mapping) and data.get('success'):
            clear_netcache('lists')
            return data.get('id')
        fflog(f'[FF][TMDB] Failed to create list {name!r}, data={data!r}')
        return None

    def delete_user_list(self, list_id: int) -> bool:
        """Delete the list (and its content). Return true on success. Support only v4."""
        list_id = self._ref_id_to_tmdb(list_id)
        data = self.delete(f'list/{list_id}', data=None, api_version=4)
        if not isinstance(data, Mapping) or not data.get('success'):
            return False
        clear_netcache('lists')
        return True

    @requests.netcache('lists')
    def user_general_lists(self,
                           list_type: UserGeneralListType,
                           type: Union[MainMediaType, MainMediaTypeList],
                           account_id: AccountId = 'me',
                           *,
                           page: int = 1,
                           chunk: int = 0,
                           sort: str = 'created_at.desc',
                           ) -> ItemList[FFItem]:
        """Get user lists."""
        def get(mtype: MainMediaType) -> ItemList[FFItem]:
            if mtype not in get_typing_args(MainMediaType):
                raise ValueError(f'TmdbApi got incorrect type {mtype!r}')
            ctype = self._main2tmdb_type2[mtype]
            data = self.get(f'account/{account_id}/{list_type}/{ctype}', params={'page': page, 'sort_by': sort})
            return self._item_list(mtype, data)

        if isinstance(type, str):
            type = cast(MainMediaType, type.split(','))
        if not type:
            return ItemList.empty()
        if len(type) == 1:
            return get(type[0])
        with RequestsPoolExecutor(max_thread_workers()) as pool:
            datas: Iterable[ItemList[FFItem]] = pool.map(get, type)
        return ItemList(join_items(*datas, zip_chunk=chunk), page=page, total_pages=max((d.total_pages for d in datas), default=1))

    def _set_general_list_items(self,
                                list_type: UserGeneralListType,
                                items: Iterable[FFRef],
                                *,
                                add: bool,
                                account: AccountId = 'me',
                                ) -> int:
        """Add or remove items to/from the general list (favorites, watchlist) and return number of proceeded items. Support only v3."""
        def update(it: JsonData) -> bool:
            data = self.post(f'account/{account}/{list_type}', data=it, api_version=3)
            return bool(isinstance(data, Mapping) and data.get('success'))

        if not isinstance(items, Sequence):
            items = tuple(items)
        if not items:
            return 0
        m2t = {**self._main2tmdb_type}
        to_update = [{
            'media_type': media,
            'media_id': tmdb_id,
            list_type: add,  # add to the list type
        } for it in items if (tmdb_id := (ref := it.ref).tmdb_id) and (media := m2t.get(ref.real_type))]
        if not to_update:
            return 0
        with RequestsPoolExecutor(max_thread_workers()) as ex:
            results = ex.map(update, to_update)
        clear_netcache('lists')
        return sum(results)

    def add_items_to_general_list(self,
                                  list_type: UserGeneralListType,
                                  items: Iterable[FFRef],
                                  *,
                                  account: AccountId = 'me',
                                  ) -> int:
        return self._set_general_list_items(list_type, items, add=True, account=account)

    def remove_items_from_general_list(self,
                                       list_type: UserGeneralListType,
                                       items: Iterable[FFRef],
                                       *,
                                       account: AccountId = 'me',
                                       ) -> int:
        return self._set_general_list_items(list_type, items, add=False, account=account)

    def web_url(self, ref: MediaRef) -> str:
        """Return link to media for humans."""
        if not ref.tmdb_id:
            return ''
        if ref.type == 'show':
            path = '/'.join(f'{k}{v}' for k, v in zip(['tv/', 'season/', 'episode/'], ref.tmdb_tv_tuple))
        elif ref.type in ('movie', 'person', 'collection'):
            path = f'{ref.type}/{ref.tmdb_id}'
        else:
            return ''  # unspotted media type
        return f'https://www.themoviedb.org/{path}'

    @requests.netcache('art')
    def providers(self, type: MainMediaType, region: str) -> Sequence[TmdbProvider]:
        """Return list of providers."""

        def parse(it: JsonData) -> TmdbProvider:
            if logo_path := it['logo_path']:
                logo = f'{self.art_image_url}{logo_path}'
            else:
                logo = None
            return TmdbProvider(id=it['provider_id'], name=it['provider_name'], logo=logo, display_priority=it['display_priority'])

        ctype = self._main2tmdb_type[type]  # konersja typu FF na TMDB
        result = self.get(f'watch/providers/{ctype}', params={'watch_region': region})
        if isinstance(result, Mapping):
            return [parse(it) for it in result.get('results', ())]
        return ()

    @requests.netcache('discover')
    def popular_people(self, *, page: int = 1) -> Sequence[FFItem]:
        """Return popular people."""
        return self._item_list('person', self.get('person/popular', params={'page': page}))

    # --- Following methods MUST be overridden ---

    def credentials(self) -> TmdbCredentials:
        """Return current credentials."""
        if self.api_key is not None:
            return TmdbCredentials(api_key=self.api_key)
        raise NotImplementedError('api.tmdb.TmdbApi.credentials() is not implemented')

    def save_session(self, *, session_id: Optional[str], access_token: Optional[str] = None) -> None:
        """Set session ID. Override this method and remember session ID or remove if None."""
        print(session_id, access_token)

    # --- Following methods COULD be overridden ---

    def dialog_create(self, request_token: str, verification_url: str) -> DialogId:
        """Create GUI dialog."""
        print(f'Confirm {request_token!r}, visit site {verification_url}')

    def dialog_close(self, dialog: DialogId) -> None:
        """Close GUI dialog."""
        print()

    def dialog_is_canceled(self, dialog: DialogId) -> bool:
        """Return True if GUI dialog is canceled."""
        return False

    def dialog_update_progress(self, dialog: DialogId, progress: float) -> None:
        """Update GUI dialog progress-bar."""
        print(f'\r {progress:5.1f}           ', end='')

    def auth_failed(self) -> None:
        """401 - auth error, should inform user or force auth again."""
        pass


# --- DEBUG & TESTS ---


if __name__ == '__main__':
    import json
    import sty
    # from pprint import pprint
    from ..ff.cmdline import DebugArgumentParser, parse_ref
    from ..ff import apis
    from ..ff.settings import settings
    # from ..ff.settings import settings
    code_color: str = f'{sty.fg.red}{sty.ef.bold}'

    class TerminalTmdb(TmdbApi):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.canceled = False

        def credentials(self):
            user: str = settings.getString('tmdb.username')
            password: str = settings.getString('tmdb.password')
            session_id: str = settings.getString('tmdb.sessionid')
            access_token = settings.getString('tmdb.access_token')
            return TmdbCredentials(user=user, password=password, session_id=session_id, access_token=access_token)

        def save_session(self, *, session_id: Optional[str], access_token: Optional[str] = None) -> None:
            """Set session ID. Save session ID or remove if None."""
            settings.setString('tmdb.sessionid', session_id or '')
            settings.setString('tmdb.access_token', access_token or '')

        def dialog_create(self, request_token: str, verification_url: str) -> DialogId:
            """Create GUI dialog."""
            import segno
            import sys
            print(f'[TMDB] Auth: visit {sty.ef.bold}{verification_url}{sty.rs.all}')
            qrcode = segno.make(verification_url)
            qrcode.terminal(out=sys.stderr, compact=True)
            self.canceled = False
            return 1

        def dialog_close(self, dialog: DialogId) -> None:
            """Close GUI dialog."""

        def dialog_cancel(self, dialog: DialogId = None) -> None:
            """Cancel GUI dialog. Debug only."""
            self.canceled = True

        def dialog_is_canceled(self, dialog: DialogId) -> bool:
            """Return True if GUI dialog is canceled."""
            return self.canceled

        def dialog_update_progress(self, dialog: DialogId, progress: float) -> None:
            """Update GUI dialog progress-bar."""
            print(f'[TMDB] auth : {progress:5.1f}')


    def jprint(data: JsonData) -> None:
        print(json.dumps(data, indent=2))

    def mprint(info: MediaPlayInfoDict) -> None:
        print('{')
        for k, v in info.items():
            # x = str(v).replace(', item_count', ',\n                  item_count')
            x = str(v).replace(', duration', ',\n                  duration')
            print(f'  {k}:\n    {x},')
        print('}')

    p = DebugArgumentParser(dest='cmd')
    p.add_argument('--tmdb-api-key', help='TMDB API key, for get extra info')
    with p.with_subparser('movie') as pp:
        pp.add_argument('id', type=int, help='tmdb movie id')
    with p.with_subparser('tv') as pp:
        pp.add_argument('id', type=int, help='tmdb tv-show id')
        pp.add_argument('season', type=int, nargs='?', help='optional season number')
        pp.add_argument('episode', type=int, nargs='?', help='optional episode number')
        pp.add_argument('-e', '--tv-episodes', action='store_true', help='episodes data for tv-show (gets seasons)')
    with p.with_subparser('info') as pp:
        pp.add_argument('ids', type=parse_ref, nargs='+', help='tmdb refs (m123, s123, s123/4, s123/4/5)')
        pp.add_argument('-e', '--tv-episodes', action='store_true', help='episodes data for tv-show (gets seasons)')
    with p.with_subparser('videos') as pp:
        pp.add_argument('ids', type=parse_ref, nargs='+', help='tmdb refs (m123, s123, s123/4, s123/4/5)')
    with p.with_subparser('discover') as pp:
        pp.add_argument('type', choices=('movie', 'tv', 'show'), help='media type')
        pp.add_argument('filter', nargs='*', help='filter (from DiscoveryFilters, ex: with_runtime<=90)')
        pp.add_argument('-p', '--page', type=int, default=1, help='page number (1..500)')
    with p.with_subparser('list') as pp:
        pp.add_argument('list', nargs='?', help='list ID')
        pp.add_argument('-A', '--api', choices=(3, 4), type=int, help='API version')
        pp.add_argument('-p', '--page', type=int, help='page number')
        pp.add_argument('-a', '--add', action='append', type=parse_ref, help='add media to the list')
    with p.with_subparser('auth') as pp:
        pp.add_argument('-A', '--api', choices=(3, 4), type=int, default=3, help='API version')
        pp.add_argument('-U', '--user', help='username (v3)')
        pp.add_argument('-P', '--pass', dest='password', help='password (v3)')
        pp.add_argument('-R', '--revoke', '--deauth', action='store_true', help='revoke authorization')
        pp.add_argument('-f', '--force', action='store_true', help='force auth')
    with p.with_subparser('skel') as pp:
        pp.add_argument('ids', type=parse_ref, nargs='+', help='tmdb refs (m123, s123, s123/4, s123/4/5)')
        pp.add_argument('-s', '--show', choices=('last', 'all', 'none'), default='last', help='show seasons options')
        pp.add_argument('-t', '--translations', action='store_true', help='append translations')
    with p.with_subparser('xxx') as pp:
        pass
    args = p.parse_args()
    # print(args); exit()  # DEBUG

    tmdb = TerminalTmdb(api_key=const.dev.tmdb.api_key or apis.tmdb_API)

    if args.cmd == 'xxx':
        def get(ref: FFRef):
            tmdb.get_media_by_ref(ref.ref)
        # tmdb.get_media_by_ref(MediaRef('movie', 100950387))
        # exit()
        from . import depaginate
        with depaginate(tmdb, limit=1000) as api:
            items = api.trending('movie')
        print(len(items))
        print(items[0])
        with RequestsPoolExecutor(max_workers=1000) as pool:
            full = list(pool.map(get, items))
        print(len(items), len(full))

    if args.cmd == 'movie':
        jprint(tmdb.get_media_by_ref(MediaRef('movie', args.id)))
    elif args.cmd == 'tv':
        jprint(tmdb.get_media_by_ref(MediaRef('show', args.id, args.season, args.episode),
                                     tv_episodes=args.tv_episodes))
    elif args.cmd == 'info':
        # pprint(list(tmdb.x_media_play_dict(args.ids, tv_episodes=args.tv_episodes).keys()))
        mprint(tmdb.x_media_play_dict(args.ids, tv_episodes=args.tv_episodes))
    elif args.cmd == 'videos':
        # pprint(list(tmdb.x_media_play_dict(args.ids, tv_episodes=args.tv_episodes).keys()))
        for ref in args.ids:
            # TODO: merge with master
            jprint(tmdb.get_videos(ref))
    elif args.cmd == 'discover':
        if args.type == 'tv':
            args.type = 'show'
        for it in tmdb.discover(args.type, page=args.page, **Condition.filters_from_str_expr_list(args.filter)):
            print(f'{it.ref:a} :  {it}')
    elif args.cmd == 'list':
        if args.list:
            if args.add:
                tmdb.add_to_user_list(args.list, args.add)
                items = args.add
            else:
                items = tmdb.user_list_items(args.list, page=args.page, api=args.api)
        else:
            items = tmdb.user_lists(page=args.page, api=args.api)
        print(f'{len(items)} item(s)')
        print(items)
    elif args.cmd == 'auth':
        if args.revoke:
            tmdb.revoke_session()
        elif args.user and args.password:
            tmdb.auth_v3(force=args.force)
        else:
            tmdb.auth_v4(force=args.force)
    elif args.cmd == 'skel':
        opts = {
            'none': SkelOptions.NONE,
            'first': SkelOptions.SHOW_LAST_SEASONS,
            'last': SkelOptions.SHOW_LAST_SEASONS,
            'all': SkelOptions.SHOW_ALL_SEASONS,
        }
        opt = opts[args.show]
        if args.translations:
            opt |= SkelOptions.TRANSLATIONS
        tmdb.get_skel_en_media(args.ids, options=opt)
