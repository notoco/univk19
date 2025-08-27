
from urllib.parse import urljoin
from time import monotonic
# from dataclasses import dataclass
from datetime import datetime, timedelta, date as dt_date
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from itertools import chain
from threading import Lock
from typing import Optional, Union, Any, Tuple, List, Dict, Sequence, Mapping, Iterable, Iterator, Callable, TypeVar
from typing import ClassVar, NamedTuple, TYPE_CHECKING
from typing_extensions import Literal, TypeAlias, get_args as get_typing_args, TypedDict, Unpack, NotRequired, cast
from attrs import define, frozen, field, fields
from wrapt.wrappers import ObjectProxy
import requests

from . import ALL_PAGES
from ..ff.kotools import xsleep
from ..ff.tricks import dict_diff_new, join_items
from ..ff.log_utils import fflog, log
from ..ff.item import FFItem
from ..ff.calendar import fromisoformat
from ..ff.control import max_thread_workers
from ..ff.types import JsonData, JsonResult, KwArgs
from ..defs import MediaType, MainMediaType, MainMediaTypeList, MediaRef, VideoIds, ItemList, RefType, FFRef, MediaProgress, MediaProgressItem
from ..defs import IdsDict as Ids
from const import const

if TYPE_CHECKING:
    from request.structures import CaseInsensitiveDict


T = TypeVar('T')

DialogId: TypeAlias = Any
#: Trakt.tv objects to watch.
MainContentType: TypeAlias = Literal['movies', 'shows']
#: Any trakt.tv Standard Media Object.
AnyContentType: TypeAlias = Literal['movies', 'shows', 'seasons', 'episodes', 'persons', 'users', 'lists', 'comments']
#: Any trakt.tv Standard Media Object.
HistoryContentType: TypeAlias = Literal['movies', 'shows', 'seasons', 'episodes']
#: Trakt.tv objects to play.
PlayContentType: TypeAlias = Literal['movie', 'episode']
#: Trakt.tv objects to watch.
WatchContentType: TypeAlias = MainContentType
#: Scrobble action.
ScrobbleAction: TypeAlias = Literal['start', 'pause', 'stop']
#: Lookup ID services.
LookupService: TypeAlias = Literal['trakt', 'imdb', 'tmdb', 'tvdb']
#: Movie / tvshow list names.
ListName: TypeAlias = Literal['anticipated', 'collected', 'favorited', 'played', 'popular', 'trending', 'watched']
#: Movie / tvshow names of lists with period.
ListWithPeriod: TypeAlias = Literal['collected', 'favorited', 'played', 'watched']
#: User general list type.
UserListType: TypeAlias = Literal['likes', 'watchlist', 'favorites', 'history', 'watched']  # no: 'collection'
#: User general list type. List is writable, items can be added/removed.
UserListPostType: TypeAlias = Literal['watchlist', 'favorites', 'collection', 'history']  # no: 'ratings'
#: Users list, the most: UserListType, popular.
UserGeneralListType: TypeAlias = Literal['trending', 'popular']
#: Like type. "" means all types.
LikeType: TypeAlias = Literal['list', 'comment', '']
#: Extended response info.
ExtendedInfo: TypeAlias = Literal['full', 'metadata', 'noseasons', 'episodes', 'comments', 'guest_stars', 'vip', '']
#: Sort by, returned by trakt as 'X-sort-by' (user) and 'X-Applied-Sort-By' (response).
SortBy: TypeAlias = Literal['rank', 'added', 'title', 'released', 'runtime', 'popularity', 'percentage', 'votes',
                            'my_rating', 'random', 'watched', 'collected']
#: Sort type (by and how), returned by trakt as 'X-sort-by'.'X-Sort-How' (user) and 'X-Applied-Sort-By'.'X-Applied-Sort-How' (response).
SortType: TypeAlias = Literal[
    '',          # default sort (no sort)
    'trakt',     # trakt sort ('X-sort-by'.'X-Sort-How')
    'rank.asc', 'rank.desc',
    'added.asc', 'added.desc',
    'title.asc', 'title.desc',
    'released.asc', 'released.desc',
    'runtime.asc', 'runtime.desc',
    'popularity.asc', 'popularity.desc',
    'percentage.asc', 'percentage.desc',
    'votes.asc', 'votes.desc',
    'my_rating.asc', 'my_rating.desc',
    'random.asc', 'random.desc',
    'watched.asc', 'watched.desc',
    'collected.asc', 'collected.desc',
]


class TraktExcepiton(Exception):
    """All exception from trakt.tv."""
    def __init__(self, *args,
                 code: Optional[int] = None,
                 text: Optional[str] = None,
                 url: Optional[str] = None,
                 ) -> None:
        super().__init__(*args)
        #: HTTP status code.
        self.code: Optional[int] = code
        #: HTTP response text.
        self.text: Optional[str] = text
        #: URL.
        self.url: Optional[str] = url

    @classmethod
    def from_response(cls, response: requests.Response, msg: Optional[str] = None) -> 'TraktExcepiton':
        args = () if msg is None else (msg,)
        return cls(*args, code=response.status_code, text=response.text, url=response.request.url)


class TraktAuthError(TraktExcepiton):
    """Authentication exception."""


class TraktCredentials(NamedTuple):
    """Trakt.tv credentials."""

    #: Client ID
    client: str
    #: Client Secret
    secret: str
    #: Access token: settings.getString("trakt.token").
    access_token: Optional[str] = None
    #: Refresh token: settings.getString("trakt.refresh").
    refresh_token: Optional[str] = None

    def __bool__(self) -> bool:
        """Return True if creadentials are defined (trakt.tv can be used)."""
        return bool(self.refresh_token)


class TraktIds(TypedDict):
    """IDs of trakt item (media)."""

    trakt: int
    tmdb: NotRequired[int]
    imdb: NotRequired[str]
    tvdb: NotRequired[int]
    slug: NotRequired[str]


@frozen
class TraktUserProfile:
    """Trakt.tv user profile info."""

    #: User ID (slug).
    id: str
    #: User name (nick).
    username: str
    #: User full name.
    name: str
    #: True if profile is private.
    private: bool = False
    #: True if it's VIP profile.
    vip: bool = False
    #: Avatar URL.
    avatar: Optional[str] = None
    #: Location country code (ex. "PL").
    location: Optional[str] = None

    # rest: joined_at, about, gender, age


@frozen
class Pages:
    """Current Page info."""
    page: int
    page_size: int = field(default=0, kw_only=True)
    page_count: int = field(default=0, kw_only=True)
    item_count: int = field(default=0, kw_only=True)
    sort: SortType = field(default='', kw_only=True)
    response_sort: SortType = field(default='', kw_only=True)

    @classmethod
    def from_headers(cls, headers: Union[Dict[str, str], 'CaseInsensitiveDict[str]'], page: int = 0) -> 'Pages':
        page = int(headers.get('X-Pagination-Page', page))
        page_size = int(headers.get('X-Pagination-Limit', 0))
        page_count = int(headers.get('X-Pagination-Page-Count', 0))
        item_count = int(headers.get('X-Pagination-Item-Count', 0))
        sort: SortType = ''
        if (sort_by := headers.get('X-Sort-By')) and (sort_ord := headers.get('X-Sort-How')):
            sort = f'{sort_by}.{sort_ord}'  # type: ignore
        reps_sort: SortType = ''
        if (sort_by := headers.get('X-Applied-Sort-By')) and (sort_ord := headers.get('X-Applied-Sort-How')):
            reps_sort = f'{sort_by}.{sort_ord}'  # type: ignore
        return Pages(page, page_size=page_size, page_count=page_count, item_count=item_count, sort=sort, response_sort=reps_sort)

    @classmethod
    def empty(cls) -> 'Pages':
        return Pages(0)

    @classmethod
    def single(cls, item_count: int = 1) -> 'Pages':
        return Pages(1, page_count=1, item_count=item_count)

    def list(self, items: Iterable[T]) -> ItemList[T]:
        return ItemList(items, page=self.page, total_pages=self.page_count, total_results=self.item_count)


class MultiShowId(NamedTuple):
    """Lookup show ID result, part of MultiId."""
    #: TVshow ID for show/season/episode.
    vid: VideoIds
    #: TVshow title.
    title: Optional[str] = None


class MultiId(NamedTuple):
    """Lookup ID result."""

    #: Media type.
    type: str
    #: Media reference. If there is no TMDB data could be None.
    #: Ref is normalized (movie/show with season/episode numbers if needed).
    ref: Optional[MediaRef]
    #: Media IDs (eg. TMDB & IMDB episode ID).
    vid: VideoIds
    #: TVshow for show/season/episode.
    show: Optional[MultiShowId]
    #: Media title.
    title: Optional[str] = None
    #: Media / tvshow year.
    year: Optional[int] = None


class Activities(NamedTuple):
    """Trakt.tv activities."""

    #: Only changed activates.
    changed: JsonData
    #: All last activates.
    data: JsonData
    #: DB changes.
    db_changed: bool = False

    @property
    def playback(self) -> Optional[datetime]:
        movies = (self.changed or {}).get('movies', {})
        episodes = (self.changed or {}).get('episodes', {})
        return min((fromisoformat(d) for cntr in (movies, episodes) if (d := cntr.get('paused_at'))), default=None)

    @property
    def playback_movies(self) -> Optional[datetime]:
        movies = (self.changed or {}).get('movies', {})
        return fromisoformat(d) if (d := movies.get('paused_at')) else None

    @property
    def playback_shows(self) -> Optional[datetime]:
        episodes = (self.changed or {}).get('episodes', {})
        return fromisoformat(d) if (d := episodes.get('paused_at')) else None

    @property
    def watched_movies(self) -> Optional[datetime]:
        movies = (self.changed or {}).get('movies', {})
        return fromisoformat(d) if (d := movies.get('watched_at')) else None

    @property
    def watched_shows(self) -> Optional[datetime]:
        # shows = (self.changed or {}).get('shows', {})
        episodes = (self.changed or {}).get('episodes', {})
        return fromisoformat(d) if (d := episodes.get('watched_at')) else None

    @property
    def last(self) -> Optional[datetime]:
        """Last activity from supported ones."""
        return min((act for act in (self.playback, self.playback_movies, self.playback_shows, self.watched_movies, self.watched_shows) if act),
                   default=None)


class TraktRequestKwargs(TypedDict):
    params: NotRequired[Optional[KwArgs]]
    page: NotRequired[Optional[int]]
    limit: NotRequired[Optional[int]]
    extended: NotRequired[Optional[ExtendedInfo]]
    errors: NotRequired[str]
    login_required: NotRequired[bool]


class Response(ObjectProxy):
    """JSON data with some extra info."""

    def __init__(self, data: JsonData, resp: requests.Response) -> None:
        super().__init__(data)
        self.status_code = resp.status_code
        self.headers = resp.headers


@define
class TraktApiStats:
    request_count: int = 0


class TraktApi:
    """Trakt.tv API."""

    _main2type: Dict[MainMediaType, MainContentType] = {
        'movie': 'movies',
        'show': 'shows',
    }

    _ref2type: Dict[RefType, AnyContentType] = {
        'movie': 'movies',
        'show': 'shows',
        'season': 'seasons',
        'episode': 'episodes',
        'list': 'lists',
        'person': 'persons',
    }

    _ref2item: Dict[RefType, str] = {
        'movie': 'movie',
        'show': 'show',
        'season': 'season',
        'episode': 'episode',
        'list': 'list',
    }

    _def_list_media: Dict[UserListType, RefType] = {
        'likes': 'list',
        'collection': '',
        'watchlist': '',
        'favorites': '',
        'history': '',
    }

    _DEBUG_STATS: ClassVar[TraktApiStats] = TraktApiStats()
    _FAKE: ClassVar[bool] = False

    def __init__(self) -> None:
        #: Trakt API url.
        self.base: str = 'https://api.trakt.tv'
        #: Connection session.
        self.sess: requests.Session = requests.Session()
        #: API token.
        self.token: str = None
        #: Connection timeout.
        self.timeout: float = const.trakt.connection.timeout
        #: Number of tries.
        self.try_count: int = const.trakt.connection.try_count
        #: Delays between tries.
        self.try_delay: float = const.trakt.connection.try_delay
        #: OAuth redirect URL - device.
        self.redirect_url: str = 'urn:ietf:wg:oauth:2.0:oob'
        #: Last activities to compare.
        self.activities: Activities = Activities({}, {})
        #: Locker
        self.auth_lock = Lock()
        #: Locker
        self.sync_lock = Lock()

    @contextmanager
    def depagination(self, *, scan_limit: int = const.trakt.scan.page.limit) -> Iterator['DePagination']:
        """Return single page. Handle Takt pages, read all pages at once and return it as one big page."""
        yield DePagination(self, scan_limit=scan_limit)

    def request(self,
                method: str,
                url: str,
                *,
                data: Optional[JsonData] = None,
                params: Optional[KwArgs] = None,
                page: Optional[int] = None,
                limit: Optional[int] = None,  # works only with `page`
                extended: Optional[ExtendedInfo] = None,
                errors: str = 'ignore',
                login_required: bool = True,
                ) -> Optional[requests.Response]:
        """Send request to trakt.tv and return JSON."""
        if self._FAKE:
            return None
        cred = self.credentials()
        # if not cred:
        #     return None
        url = urljoin(self.base, url)
        headers = {
            # "Content-Type": "application/json",
            'trakt-api-version': '2',
        }
        if login_required:
            headers['trakt-api-key'] = cred.client
        # Default params.
        params = dict(params or ())
        if page is not None:
            if params.get('page') is None:
                params['page'] = page
            if params.get('limit') is None:
                if limit is None:
                    params['limit'] = const.trakt.page.limit
                else:
                    params['limit'] = limit
        if extended:
            if params.get('extended') is None:
                params['extended'] = extended
        # For status codes see: https://trakt.docs.apiary.io/#introduction/status-codes
        status_code: int = 0
        resp = None
        # fflog(f'[TRAKT] {url=}, {params=}')
        for i in range(self.try_count):
            # get newest credentials (after token refresh too)
            cred = self.credentials()
            if login_required and cred:
                headers['Authorization'] = f'bearer {cred.access_token}'
            # make the request
            resp_headers = {}
            try:
                resp = self.sess.request(method, url, json=data, params=params, headers=headers, timeout=self.timeout)
                status_code = resp.status_code
                resp_headers = {k: v for k, v in resp.headers.items() if 'sort-' in k.lower()}
            except requests.ConnectionError:
                status_code = 0
            except requests.RequestException:
                if errors == 'ignore':
                    status_code = 0
                else:
                    raise
            finally:
                # fflog(f'[TRAKT] {method} {url} ? {params} < {data!r}  (try: {i+1}) → {status_code}\n  {cred}')
                fflog(f'[TRAKT] {method} {url} ? {params} < {data!r}  (try: {i+1}) → {status_code}, cred:{bool(cred)}')
                fflog(f'[TRAKT]  …  {headers=}')
                fflog(f'[TRAKT]  …  {resp_headers=}')
            # analyze response
            try_delay = 0
            with self.auth_lock:
                if status_code == 401:  # Unauthorized - OAuth must be provided
                    # Handle other codes like 401 here (Token Refresh Logic)
                    self.refresh()
                elif status_code == 403:  # Forbidden - invalid API key or unapproved app
                    if const.trakt.auth.auto and cred:
                        self.auth()
                    else:
                        return None
                elif status_code in (0, 429):  # Connection Error | Rate Limit Exceeded
                    # See: https://trakt.docs.apiary.io/#introduction/rate-limiting
                    fflog(f'[TRAKT] Rate limit exceeded {status_code}')
                    try_delay = self.try_delay
                    # TODO, handle response headers
                    # X-Ratelimit: {"name":"UNAUTHED_API_GET_LIMIT","period":300,"limit":1000,"remaining":0,
                    #               "until":"2020-10-10T00:24:00Z"}
                    # Retry-After: 10
                elif status_code == 420:  # If the user's list item limit is exceeded, a 420 HTTP error code is returned
                    log('Trakt list limit exceeded')
                    break
                elif status_code == 502:  # Gateway Error - trakt.tv is not avaliable
                    try_delay = 3 * self.try_delay
                else:
                    # rest: success or error, stop repeating
                    break
            if try_delay:
                xsleep(try_delay)

        if resp is None:
            return None

        # 200: Success
        # 201: Success - new resource created (POST)
        # 204: Success - no content to return (DELETE)
        if 200 <= status_code <= 299:
            return resp

        if status_code >= 500:  # temporary
            fflog(f'[TRAKT] Temporary error {resp.status_code}')
            return None
        if status_code >= 400:  # permanent
            fflog(f'[TRAKT] Error {resp.status_code}\n{resp.text}')
            return None

    def get(self, url: str, **kwargs: Unpack[TraktRequestKwargs]) -> Optional[JsonResult]:
        """Send GET request to trakt.tv and return JSON."""
        resp: Optional[requests.Response] = self.request('GET', url, data=None, **kwargs)
        if resp is None:
            return None
        return resp.json()

    def post(self, url: str, data: JsonData, **kwargs: Unpack[TraktRequestKwargs]) -> Optional[JsonData]:
        """Send POST request to trakt.tv and return JSON."""
        resp: Optional[requests.Response] = self.request('POST', url, data=data, **kwargs)
        if resp is None:
            return None
        return resp.json()

    def put(self, url: str, data: JsonData, **kwargs: Unpack[TraktRequestKwargs]) -> Optional[JsonData]:
        """Send PUT request to trakt.tv and return JSON."""
        resp: Optional[requests.Response] = self.request('PUT', url, data=data, **kwargs)
        if resp is None:
            return None
        return resp.json()

    def delete(self, url: str, **kwargs: Unpack[TraktRequestKwargs]) -> bool:
        """Send DELETE request to trakt.tv and return True if deleted."""
        resp: Optional[requests.Response] = self.request('DELETE', url, data=None, **kwargs)
        return resp.status_code == 204 if resp else False

    def get_with_pages(self, url: str, **kwargs: Unpack[TraktRequestKwargs]) -> Tuple[Optional[JsonResult], Pages]:
        """Send GET request to trakt.tv and return JSON and pages."""
        if kwargs.get('page') == ALL_PAGES:
            with self.depagination() as trakt:
                resp: Optional[requests.Response] = trakt.request('GET', url, data=None, **kwargs)
        else:
            resp: Optional[requests.Response] = self.request('GET', url, data=None, **kwargs)
        if resp is None:
            return None, Pages.empty()
        return resp.json(), Pages.from_headers(resp.headers)

    def auth(self) -> bool:
        """Device authentication."""
        # see: https://trakt.docs.apiary.io/#reference/authentication-devices/exchange-code-for-access_token
        fflog('[TRAKT] Going to authentication')
        cred = self.credentials()
        resp = self.sess.post(urljoin(self.base, '/oauth/device/code'), json={'client_id': cred.client},
                              timeout=self.timeout)
        if resp.status_code != 200:
            fflog(f'[TRAKT][AUTH] DEvice code failed {resp.status_code}: {resp.text}')
            raise TraktAuthError.from_response(resp, f'Can NOT get code for client {cred.client!r}')
        device_code_data: JsonData = resp.json()

        # How often we can ask about user auth.
        interval: int = device_code_data['interval']
        # When (in sec) auth process expires.
        expires_in: int = device_code_data['expires_in']
        # Timestamp of process start.
        start: float = monotonic()
        # Device code (used in oauth).
        device_code: str = device_code_data['device_code']

        # Create (progress-bar) dialog.
        dialog = self.dialog_create(user_code=device_code_data['user_code'],
                                    verification_url=device_code_data['verification_url'])
        # Continue as long as not expire or user authorized or user canceled.
        access: Optional[JsonData] = None
        try:
            while True:
                #: Current timestamp.
                now: float = monotonic()
                # check in expires...
                if start + expires_in < now:
                    break
                # check if dialog is canceled
                if self.dialog_is_canceled(dialog):
                    break
                # check if user authorized this device
                if access := self._get_access_token(device_code, cred):
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
        if access:
            self.set_access_token(access)
        return bool(access)

    def refresh(self) -> bool:
        """Exchange refresh_token for access_token."""
        cred = self.credentials()
        if not cred.refresh_token:
            return self.auth()
        fflog('[TRAKT] Refresh token')
        headers = {
            # "Content-Type": "application/json",
            'trakt-api-key': cred.client,
            'trakt-api-version': '2',
            # 'Authorization': f'bearer {cred.access_token}',
        }
        resp = self.sess.post(urljoin(self.base, '/oauth/token'), json={
            'refresh_token': cred.refresh_token,
            'client_id': cred.client,
            'client_secret': cred.secret,
            'redirect_uri': self.redirect_url,
            'grant_type': 'refresh_token',
        }, headers=headers, timeout=self.timeout)
        # 401: If the refresh_token is invalid, you'll get a 401 error.
        # 403:  # Forbidden - invalid API key or unapproved app
        if resp.status_code in (401, 403):
            return self.auth()
        if resp.status_code == 200:
            self.set_access_token(resp.json())
            return True
        fflog(f'[TRAKT][AUTH] Refresh token failed {resp.status_code}: {resp.text}')
        if resp.status_code == 400:
            fflog('[TRAKT][AUTH] Force authorize...')
            if self.auth():
                fflog('[TRAKT][AUTH] Authorized')
                return True
            fflog('[TRAKT][AUTH] Authorize FAILED')
            return False
        raise TraktAuthError.from_response(resp, 'Can not refresh access token')

    def _get_access_token(self, device_code: str, cred: TraktCredentials) -> Optional[JsonData]:
        """Poll for the access_token."""
        # see: https://trakt.docs.apiary.io/#reference/authentication-devices/get-token/poll-for-the-access_token
        resp = self.sess.post(urljoin(self.base, '/oauth/device/token'), json={
            'code': device_code,
            'client_id': cred.client,
            'client_secret': cred.secret,
        }, timeout=self.timeout)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 400:  # Pending - waiting for the user to authorize your app
            return None
        if resp.status_code == 429:  # Slow Down - your app is polling too quickly
            xsleep(5)
            return None
        # rest - errors
        fflog(f'[TRAKT][AUTH] Pull access token failed {resp.status_code}: {resp.text}')
        raise TraktAuthError.from_response(resp, 'Can not pull access token')

    def revoke_session(self) -> bool:
        """Revoke current sesion."""
        cred = self.credentials()
        if not cred:
            return True  # no session, nothing to do
        self.post('oauth/revoke', data={
            'token': cred.access_token,
            'client_id': cred.client,
            'client_secret': cred.secret,
        })
        self.remove_access_token()
        return True

    def get_video_ids(self, kwargs: KwArgs) -> Ids:
        """
        Get trakt.tv `ids` dict from arguments.

        Support for "trakt", "imdb", "tmdb", "slug" trakt.tv ID.
        Support for "ffid" video ID, VideoIds or int got from VideoIds.make_video_id.
        """
        ffid = kwargs.pop('ffid', None)
        if isinstance(ffid, int):
            ffid = VideoIds.from_ffid(ffid)
        if ffid:
            kwargs = {**ffid.ids(), **kwargs}
        return {k: v for k in ('trakt', 'imdb', 'tmdb', 'slug') for v in (kwargs.pop(k, None),) if v}

    def scrobble(self,
                 action: ScrobbleAction,
                 type: PlayContentType,
                 progress: float = 0.0,
                 *,
                 errors: str = 'ignore',
                 ids: Ids,
                 # **kwargs,
                 ) -> bool:
        """Scrobble what a user is watching in a media center. For ID in kwargs see get_video_ids()."""
        # ids = self.get_video_ids(kwargs)
        # if kwargs:
        #     raise TypeError(f'TraktApi.scrobble_*() got an unexpected keyword arguments: {",".join(kwargs)}')
        if action not in get_typing_args(ScrobbleAction):
            raise ValueError(f'TraktApi.scrobble_*() got incorrect action {action!r}')
        if type not in get_typing_args(PlayContentType):
            raise ValueError(f'TraktApi.scrobble_*() got incorrect type {type!r}')
        data = {
            'progress': float(progress),
            type: {'ids': ids},
            # 'app_version': ...
        }
        fflog(f'[TRAKT][SCROBBLE] post /scrobble/{action}, data={data}')
        data = self.post(f'scrobble/{action}', data=data, errors=errors)
        return bool(data)

    def scrobble_start(self, type: PlayContentType, progress: float = 0.0, **kwargs) -> bool:
        """Start watching in a media center. For ID in kwargs see get_video_ids()."""
        return self.scrobble('start', type=type, progress=progress, **kwargs)

    def scrobble_pause(self, type: PlayContentType, progress: float, **kwargs) -> bool:
        """Pause watching in a media center. For ID in kwargs see get_video_ids()."""
        return self.scrobble('pause', type=type, progress=progress, **kwargs)

    def scrobble_stop(self, type: PlayContentType, progress: float, **kwargs) -> bool:
        """Stop or finish watching in a media center. For ID in kwargs see get_video_ids()."""
        return self.scrobble('stop', type=type, progress=progress, **kwargs)

    def _scrobble_ref(self,
                      action: ScrobbleAction,
                      ref: MediaRef,
                      progress: float = 0.0,
                      *,
                      errors: str = 'ignore',
                      ) -> bool:
        """Scrobble what a user is watching in a media center."""
        if action not in get_typing_args(ScrobbleAction):
            raise ValueError(f'TraktApi.scrobble_*() got incorrect action {action!r}')
        ids = self.get_video_ids({'ffid': ref.ffid})
        if ref.type in get_typing_args(PlayContentType):
            data = {
                'progress': float(progress),
                ref.type: {'ids': ids},
            }
        elif ref.is_episode:
            data = {
                'progress': float(progress),
                'show': {'ids': ids},
                'episode': {'season': ref.season, 'number': ref.episode},
            }
        else:
            fflog.error(f'[TRAKT][SCROBBLE] ERROR, nut supported type {ref}')
            return False
        fflog(f'[TRAKT][SCROBBLE] post /scrobble/{action}, data={data}')
        return bool(self.post(f'scrobble/{action}', data=data, errors=errors))

    def scrobble_ref(self, action: ScrobbleAction, ref: MediaRef, progress: float = 0.0) -> bool:
        """Scrobble what a user is watching in a media center."""
        return self._scrobble_ref(action=action, ref=ref, progress=progress)

    def scrobble_pause_ref(self, ref: MediaRef, progress: float = 0.0) -> bool:
        """Pause watching in a media center."""
        return self._scrobble_ref('start', ref=ref, progress=progress)

    def scrobble_stop_ref(self, ref: MediaRef, progress: float = 0.0) -> bool:
        """Stop watching in a media center."""
        return self._scrobble_ref('start', ref=ref, progress=progress)

    def scrobble_start_ref(self, ref: MediaRef, progress: float = 0.0) -> bool:
        """Start watching in a media center."""
        return self._scrobble_ref('start', ref=ref, progress=progress)

    def get_watching(self, user: str = 'me') -> Optional[JsonData]:
        """Get what a user is currently watching."""
        resp = self.get(f'users/{user}/watching', errors='ignore')
        if isinstance(resp, Mapping):
            return resp
        return None

    def get_playblack_list(self, *, extended: ExtendedInfo = '', type: Optional[PlayContentType] = None, errors: str = 'ignore') -> Sequence[JsonData]:
        """Get playback progress."""
        if type is None or type in get_typing_args(PlayContentType):
            ctype = f'{type}s' if type else ''
            resp = self.get(f'sync/playback/{ctype}', errors=errors, extended=extended)
        else:
            raise ValueError(f'TraktApi.get_playblack_list() got incorrect type {type!r}')
        return resp if isinstance(resp, Sequence) else ()

    def remove_playback(self, playback_id: int, *, errors: str = 'ignore') -> bool:
        """Remove a playback item (progress) by trakt playback item ID."""
        return self.delete(f'sync/playback/{playback_id}', errors=errors)

    def get_watched_list(self, type: WatchContentType, *,
                         extended: ExtendedInfo = '', errors: str = 'ignore') -> Sequence[JsonData]:
        """Get watched list."""
        if type not in get_typing_args(WatchContentType):
            raise ValueError(f'TraktApi.get_watched_list() got incorrect type {type!r}')
        resp = self.get(f'sync/watched/{type}', errors=errors, extended=extended)
        return resp if isinstance(resp, Sequence) else ()

    def get_history_list(self, type: HistoryContentType, *, errors: str = 'ignore') -> Sequence[JsonData]:
        """Get history."""
        if type not in get_typing_args(HistoryContentType):
            raise ValueError(f'TraktApi.get_history_list() got incorrect type {type!r}')
        with self.depagination() as trakt:
            data = trakt.get(f'sync/history/{type}', errors=errors)
        if isinstance(data, Sequence):
            return data
        return []

    def _op_history_item(self, url: str, type: HistoryContentType, ids: Ids,
                         season: Optional[int] = None, episode: Optional[int] = None) -> Optional[JsonData]:
        """Operate (add/remove) history item, +/- watched play_count."""
        # TODO: add support for "watched_at"
        if type and not type.endswith('s'):
            type = cast(HistoryContentType, f'{type}s')
        if type not in get_typing_args(HistoryContentType):
            raise ValueError(f'TraktApi.*_history_item() got incorrect type {type!r}')
        if not ids:
            raise ValueError('TraktApi.*_history_item() no ids.')
        item: Dict[str, Any] = {'ids': {k: v for k, v in ids.items() if k and v}}
        if type in ('shows', 'seasons', 'episodes') and season is not None:
            item['seasons'] = [{'number': int(season)}]
            if type in ('shows', 'episodes') and episode is not None:
                item['seasons'][0]['episodes'] = [{'number': int(episode)}]
            type = 'shows'
        return self.post(url, data={type: [item]})

    def add_history_item(self, type: HistoryContentType, ids: Ids,
                         season: Optional[int] = None, episode: Optional[int] = None) -> Optional[JsonData]:
        """Add history item, increments watched play_count."""
        return self._op_history_item('sync/history/', type, ids, season=season, episode=episode)

    def remove_history_item(self, type: HistoryContentType, ids: Ids, *,
                            season: Optional[int] = None, episode: Optional[int] = None) -> Optional[JsonData]:
        """Remove history item, decrements watched play_count."""
        return self._op_history_item('sync/history/remove', type, ids, season=season, episode=episode)

    def add_history_ref(self, ref: MediaRef) -> bool:
        """Add history item, increments watched play_count."""
        mtype, ids = self._ref_to_trakt_hist(ref)
        if mtype:
            res = self._op_history_item('sync/history/', mtype, ids, season=ref.season, episode=ref.episode)
            if isinstance(res, Mapping):
                return any(v for v in (res.get('added') or {}).values())
        return False

    def remove_history_ref(self, ref: MediaRef) -> bool:
        """Remove history item, reset watched play_count."""
        mtype, ids = self._ref_to_trakt_hist(ref)
        if mtype:
            res = self._op_history_item('sync/history/remove', mtype, ids, season=ref.season, episode=ref.episode)
            if isinstance(res, Mapping):
                return any(v for v in (res.get('deleted') or {}).values())
        return False

    def _ref_to_trakt_hist(self, ref: MediaRef) -> Tuple[Optional[HistoryContentType], Ids]:
        ids = cast(Ids, ref.video_ids.ids())  # it's OK, the same keys
        if ref.type in ('movie', 'show'):  # also seasons and episodes
            mtype = f'{ref.real_type}s'  # hack
            assert mtype in ('movies', 'shows', 'seasons', 'episodes')
            return mtype, ids
        fflog(f'WARNING: wrong ref {ref!r}', stack_depth=2)
        return None, ids

    def get_last_activities(self, *, activities: Optional[Activities] = None, errors: str = 'ignore',
                            timestamp: Optional[Union[datetime, float]] = None) -> Activities:
        """Get last activity."""
        with self.sync_lock:
            old: Activities = self.activities if activities is None else activities
        new = self.get('sync/last_activities', errors=errors)
        if not isinstance(new, Mapping):
            return Activities({}, {})
        changed = Activities(dict_diff_new(old.data or {}, new), new)
        if activities is None:
            self.activities = changed
            with self.sync_lock:
                if self.activities.changed:
                    if self.activities_changed(self.activities, timestamp=timestamp):
                        changed = changed._replace(db_changed=True)
        return changed

    def sync_now(self) -> bool:
        """Sync all trakt.tv stuff. Returns True if DB is changed."""
        act = self.get_last_activities()
        return act.db_changed

    def id_lookup(self,
                  id: Union[str, int],
                  *,
                  service: LookupService,
                  type: Optional[MediaType] = None,
                  errors: str = 'ignore',
                  ) -> MultiId:
        if service not in get_typing_args(LookupService):
            raise ValueError(f'TraktApi.id_lookup() got incorrect service {service!r}')
        # if type == 'season':
        #     raise ValueError('Trakt.tv does not implement SEASON id lookup')
        params: Dict[str, str] = {}
        if type:
            params['type'] = type
        data = self.get(f'search/{service}/{id}', params=params, errors=errors)
        if not data or isinstance(data, Mapping):
            return MultiId(type='', ref=None, vid=VideoIds(), show=None)

        item: JsonData = data[0]
        mtype: str = item['type']
        itself = item[mtype]
        vid = VideoIds.from_ids(itself['ids'])
        title = itself.get('title')
        if mtype == 'movie':
            ref = MediaRef.movie(vid.ffid)
            return MultiId(type=mtype, ref=ref, vid=vid, show=None, title=title, year=itself.get('year'))
        show_item = item['show']
        if mtype == 'show':
            show_vid = vid
        else:
            show_vid = VideoIds.from_ids(show_item['ids'])
        ref = MediaRef.tvshow(show_vid.ffid, itself.get('season'), itself.get('number'))
        show = MultiShowId(vid=show_vid, title=show_item.get('title'))
        return MultiId(type=mtype, ref=ref, vid=vid, show=show, title=title, year=show_item.get('year'))

    def _get_ref(self, it: JsonData, ref_type: Optional[RefType] = None) -> Iterator[MediaRef]:
        if 'movie' in it:
            yield VideoIds.from_ids(it['movie']['ids']).ref('movie')
        elif 'episode' in it:
            vid = VideoIds.from_ids(it['show']['ids'])
            d = it['episode']
            yield MediaRef('show', vid.ffid, season=d['season'], episode=d['number'])
        elif 'season' in it:
            vid = VideoIds.from_ids(it['show']['ids'])
            d = it['season']
            yield MediaRef('show', vid.ffid, season=d['number'])
        elif 'show' in it:
            yield VideoIds.from_ids(it['show']['ids']).ref('show')
        elif 'person' in it:
            yield VideoIds.from_ids(it['person']['ids']).ref('person')
        elif 'list' in it:
            yield VideoIds.from_ids(it['list']['ids']).ref('list')
        elif ref_type is not None:
            iid = it.get('ids', {}).get('trakt')
            if iid:
                yield MediaRef(ref_type, iid)

    def list_refs(self, items: Iterable[JsonData]) -> List[MediaRef]:
        """Get refs from media item list."""
        return list(ref for it in items for ref in self._get_ref(it))

    def _item_list(self,
                   data: Optional[JsonResult],
                   *,
                   pages: Pages,
                   ref_type: Optional[RefType] = None,
                   sort: Optional[SortType] = None,  # sort by X-Sort-By and X-Sort-How, has no sense with real pagination
                   ) -> ItemList[FFItem]:
        """Return item list with pagination."""

        def get_ff(it: JsonData) -> Iterator[FFItem]:
            for ref in self._get_ref(it, ref_type=ref_type):  # only single ref or None
                ff = FFItem(ref)
                vtag = ff.vtag
                info = it.get(ref.real_type, {})
                ff.label = ff.title = info.get('title') or info.get('name') or it.get('name') or ''
                year = info.get('year')
                if year:
                    vtag.setYear(int(year))
                ids = info.get('ids', {})
                for key in ('imdb', 'trakt'):
                    val = ids.get(key)
                    if val:
                        ff.vtag.setUniqueID(str(val), key)
                ffid = VideoIds.from_ids(ids).ffid
                if ffid and ffid in VideoIds.KODI:
                    ff.vtag.setDbId(ffid)  # Kodi DBID
                vtag.setPlot(info.get('description') or it.get('description') or '')
                if last_watched_at := it.get('last_watched_at', it.get('watched_at')):
                    ff.temp.watched = date = fromisoformat(last_watched_at)
                    vtag.setLastPlayed(str(date.astimezone().replace(tzinfo=None)))
                else:
                    ff.temp.watched = None
                if ref.is_show and (seasons := it.get('seasons')):
                    try:
                        episodes = tuple(MediaProgressItem(MediaRef(ref.type, ref.ffid, sz['number'], ep['number']),
                                                           play_count=ep['plays'], last_watched_at=ep['last_watched_at'])
                                         for sz in seasons for ep in sz.get('episodes') or ())
                    except KeyError:
                        pass  # no progreass info, just skip it
                    else:
                        ff.progress = MediaProgress(ref, bar=episodes)
                # item_count = it.get('item_count')
                # if item_count:
                #     ff.children_count = item_count
                if ref.type == 'list':
                    user_info = it.get('list', {}).get('user', {})
                    ff.role = user_info.get('name') or ''
                    vtag.setUniqueID(info.get('ids', {}).get('slug') or '', 'trakt.list')
                    vtag.setUniqueID(user_info.get('ids', {}).get('slug') or '', 'trakt.user')
                ff.source_data = it
                yield ff

        # if type is not None and isinstance(data, Sequence):
        if data is None or isinstance(data, Mapping):
            return ItemList.empty()
        # sort by trakt user preferences (X-Sort-By and X-Sort-How)
        items: Sequence[JsonData] = self._sort_items_with_pages(data, sort=sort, pages=pages)
        # prase items and generate FFItems
        return pages.list(ff for it in items for ff in get_ff(it))

    def _sort_items_with_pages(self, items: Sequence[JsonData], *, sort: Optional[SortType], pages: Optional[Pages]) -> Sequence[JsonData]:
        """Item sorting using pages with X-Sort-By and X-Sort-How, ex. 'added.asc'."""
        if pages is None:
            return self._sort_items(items, sort=sort)
        return self._sort_items(items, sort=sort, trakt_sort=pages.sort, response_sort=pages.response_sort)

    def _sort_items(self,
                    # items to sort
                    items: Sequence[JsonData],
                    *,
                    # force sort (set by FF)
                    sort: Optional[SortType],
                    # trakt user list sort
                    trakt_sort: SortType = '',
                    # api reponse applied sort
                    response_sort: SortType = '',
                    ) -> Sequence[JsonData]:
        """Item sorting using X-Sort-By and X-Sort-How, ex. 'added.asc'."""
        # sort by trakt user preferences (X-Sort-By and X-Sort-How)
        if trakt_sort and sort in ('', 'trakt'):
            sort = trakt_sort
        # need to sort?
        if sort and sort != response_sort:
            from random import randint
            import re

            def define_exctract(default: Any, key: str, tv: Any = '', *, rx: Optional[re.Pattern] = None) -> Any:
                def extract(it: JsonData):
                    value = default
                    if obj := it.get('movie'):
                        value = obj.get(key, default)
                    tv_key = tv or key
                    for name in ('episode', 'show'):
                        if obj := it.get(name):
                            value = obj.get(tv_key, default)
                            break
                    if rx:
                        value = rx.sub('', value)
                    return value
                return extract

            remove_prefix = re.compile(r'^(?:A|An|The)\s+', flags=re.IGNORECASE)
            sorting: Dict[SortBy, Callable[[JsonData], Any]] = {
                'added':      lambda it: it.get('listed_at', ''),                                  # noqa: E272
                'collected':  lambda it: it.get('last_collected_at', it.get('collected_at', '')),  # noqa: E272
                'rank':       lambda it: it.get('rank', ''),                                       # noqa: E272
                'released':   define_exctract('', 'released', 'first_aired'),                      # noqa: E272
                'title':      define_exctract('', 'title', rx=remove_prefix),                      # noqa: E272
                'runtime':    define_exctract(0, 'runtime'),                                       # noqa: E272
                'votes':      define_exctract(0, 'votes'),                                         # noqa: E272
                'popularity': define_exctract(.0, 'rating'),                                       # noqa: E272   (it's not real popularity)
                'random':     lambda _: randint(1, 1_000_000),                                     # noqa: E272
                # rest are not supported now
            }

            by: SortBy
            by, _, order = sort.rpartition('.')  # type: ignore
            if key := sorting.get(cast(SortBy, by)):
                fflog(f'[TRAKT] sorting: {sort}')
                return sorted(items, key=key, reverse=(order == 'desc') ^ const.indexer.trakt.sort.reverse_order.get(by, False))

        return items

    def general_list(self,
                     type: MainMediaType,
                     list: ListName,
                     period: Union[None, int, Literal['weekly']] = None,
                     *,
                     page: int = 1,
                     ) -> ItemList:
        """Get general list like popular or trading."""
        if type not in get_typing_args(MainMediaType):
            raise ValueError(f'TraktApi.list() got incorrect content type {type!r}')
        if list not in get_typing_args(ListName):
            raise ValueError(f'TraktApi.list() got incorrect list name {list!r}')
        ctype = self._main2type[type]
        url = f'{ctype}/{list}'
        if period:
            if list not in get_typing_args(ListWithPeriod):
                raise ValueError(f'TraktApi.list(): list {list!r} could na be used period {period!r}')
            url = f'{url}/{period}'
        params = {'page': page, 'limit': const.trakt.page.limit}
        data, pages = self.get_with_pages(url, params=params)
        if isinstance(data, Sequence):
            if list == 'popular':  # Special case! Only "popular" has item directly (w/o type objects).
                data = [{type: it} for it in data]
            return self._item_list(data, pages=pages)
        return ItemList.empty()

    def box_office(self) -> ItemList[FFItem]:
        """Returns the top 10 grossing movies in the U.S. box office last weekend."""
        resp: Optional[requests.Response] = self.request('GET', 'movies/boxoffice', data=None)
        if resp is not None:
            data: JsonResult = resp.json()
            if isinstance(data, Sequence):
                return self._item_list(data, pages=Pages.single(len(data)))
        return ItemList.empty()

    def user_general_lists(self, list: UserGeneralListType, *, page: int = 1) -> ItemList[FFItem]:
        """Returns user lists."""
        data, pages = self.get_with_pages(f'lists/{list}', page=page)
        if isinstance(data, Sequence):
            return self._item_list(data, pages=pages, ref_type='list')
        return ItemList.empty()

    def user_profile(self, user: str = 'me') -> Optional[TraktUserProfile]:
        """Returns user profile."""
        data = self.get(f'users/{user}')
        if isinstance(data, Mapping):
            data['id'] = data['ids']['slug']
            if avatar := data.get('images', {}).get('avatar'):
                data['avatar'] = avatar
            args = {f.name for f in fields(TraktUserProfile)}
            return TraktUserProfile(**{k: v for k, v in data.items() if k in args})
        return None

    def user_lists(self, user: str = 'me') -> ItemList[FFItem]:
        """Returns user lists."""
        data = self.get(f'users/{user}/lists')
        if isinstance(data, Sequence):
            return self._item_list(data, pages=Pages.single(len(data)), ref_type='list')
        return ItemList.empty()

    def the_list(self,
                 list_id: Union[int, str],
                 *,
                 page: int = 1,
                 media_type: Optional[MainMediaType] = None,
                 ) -> ItemList[FFItem]:
        """Returns user lists by ID only."""
        ctype: str = self._ref2type.get(media_type, '')
        data, pages = self.get_with_pages(f'lists/{list_id}/items/{ctype}', page=page)
        if isinstance(data, Sequence):
            return self._item_list(data, pages=pages)
        return ItemList.empty()

    def user_list_items(self,
                        list_id: Union[int, str],
                        user: str = 'me',
                        *,
                        page: Optional[int] = None,
                        media_type: Optional[MainMediaType] = None,
                        sort: Optional[SortType] = None,  # sort by X-Sort-By and X-Sort-How, has no sense if `page` is used
                        ) -> ItemList[FFItem]:
        """Returns user (private too) lists."""
        ctype: str = self._ref2type.get(media_type, '')
        extended = 'full' if sort is not None else None  # more datails are needed for sorting
        data, pages = self.get_with_pages(f'users/{user}/lists/{list_id}/items/{ctype}', page=page, extended=extended)
        if isinstance(data, Sequence):
            return self._item_list(data, pages=pages, sort=sort)
        return ItemList.empty()

    def user_generic_list(self,
                          list_type: UserListType,
                          user: str = 'me',
                          *,
                          media_type: Optional[RefType] = None,
                          page: int = ALL_PAGES,
                          sort: Optional[SortType] = None,  # sort by X-Sort-By and X-Sort-How, has no sense if `page` is used
                          limit: Optional[int] = None,
                          noseasons: bool = False,
                          # Hide shows with 100%
                          hide_100: bool = False,
                          ) -> ItemList[FFItem]:
        """Returns generic user list items (likes, watchlist, favorites, history, watched)."""
        # Likes: Comments has no media attached, we have to use "https://api.trakt.tv/comments/{id}/item"
        if media_type is None:
            media_type = self._def_list_media.get(list_type, '')
        path = ['users', user, list_type]
        if mtype := self._ref2type.get(media_type, ''):
            path.append(mtype)
        params: Dict[str, Any] = {'page': page or 1, 'limit': limit or const.trakt.page.limit}
        extended = None
        if sort is not None or hide_100:
            extended = 'full'
        elif noseasons:
            extended = 'noseasons'
        if page == ALL_PAGES:
            with self.depagination() as trakt:
                data, pages = trakt.get_with_pages('/'.join(path), params=params, extended=extended)
        else:
            data, pages = self.get_with_pages('/'.join(path), params=params, extended=extended)
        if isinstance(data, Sequence):
            if media_type == 'show' and hide_100:
                def in_progress(it: JsonData) -> bool:
                    if count := it.get('show', {}).get('aired_episodes'):
                        return 0 < sum(1 for sz in it.get('seasons', []) for ep in sz.get('episodes', []) if ep.get('plays')) < count
                    return False
                data = [it for it in data if in_progress(it)]
            return self._item_list(data, pages=pages, sort=sort)
        return ItemList.empty()

    def _proc_list_items(self,
                         items: Iterable[FFRef],
                         *,
                         path: str,
                         remove: bool,
                         people_enabled: bool,
                         show_only: bool = False,  # only shows, no seasons or episodes
                         ) -> Tuple[bool, int]:
        """Proceed (add, remove) trakt user list items. Return True on success and number of proceeded items. Notes are not supported."""
        items = tuple(items)
        if not items:
            return True, 0
        movies = tuple({'ids': ref.video_ids.ids()} for item in items if (ref := item.ref).is_movie)
        if show_only:
            shows = tuple({'ids': ref.video_ids.ids()} for item in items if (ref := item.ref).is_show)
        else:
            shows = tuple(chain(
                ({'ids': ref.video_ids.ids()}
                 for item in items if (ref := item.ref).is_show),
                ({'ids': ref.video_ids.ids(), 'seasons': [{'number': ref.season}]}
                 for item in items if (ref := item.ref).is_season),
                ({'ids': ref.video_ids.ids(), 'seasons': [{'number': ref.season, 'episodes': [{'number': ref.episode}]}]}
                 for item in items if (ref := item.ref).is_episode),  # type: ignore[reportArgumentType]
            ))
        if people_enabled:
            people = tuple({'ids': ref.video_ids.ids()} for item in items if (ref := item.ref).type == 'person')
        else:
            people = ()
        if not movies and not shows and not people:
            return True, 0
        items_to_send = {
            'movies': movies,
            'shows': shows,
        }
        if people_enabled:
            items_to_send['people'] = people
        data = self.post(path, data=items_to_send)
        res_name = 'deleted' if remove else 'added'
        if isinstance(data, Mapping):
            added = sum(v for v in data.get(res_name, {}).values())
            # existing = sum(v for v in data.get('existing', {}).values())
            not_found = sum(len(v) for v in data.get('not_found', {}).values())
            return added > 0 and not_found == 0, added
        return False, 0

    def add_to_user_list(self,
                         list_id: Union[int, str],
                         items: Iterable[FFRef],
                         *,
                         user: str = 'me',
                         ) -> Tuple[bool, int]:
        """Add items to trakt user list. Return True on success and number of proceeded items. Notes are not supported."""
        return self._proc_list_items(items, path=f'users/{user}/lists/{list_id}/items', remove=False, people_enabled=True)

    def remove_from_user_list(self,
                              list_id: Union[int, str],
                              items: Iterable[FFRef],
                              *,
                              user: str = 'me',
                              ) -> Tuple[bool, int]:
        """Remove items from trakt user list. Return True on success and number of proceeded items."""
        return self._proc_list_items(items, path=f'users/{user}/lists/{list_id}/items/remove', remove=True, people_enabled=True)

    def add_to_generic_list(self,
                            list_type: UserListPostType,
                            items: Iterable[FFRef],
                            ) -> Tuple[bool, int]:
        """Add items to trakt generic list (favorites, watchlist, collection, ...). Return True on success and number of proceeded items."""
        return self._proc_list_items(items, path=f'sync/{list_type}', remove=False, people_enabled=False, show_only=list_type == 'favorites')

    def remove_from_generic_list(self,
                                 list_type: UserListPostType,
                                 items: Iterable[FFRef],
                                 ) -> Tuple[bool, int]:
        """Remove items from trakt generic list (favorites, watchlist, collection, ...). Return True on success and number of proceeded items."""
        return self._proc_list_items(items, path=f'sync/{list_type}/remove', remove=True, people_enabled=False, show_only=list_type == 'favorites')

    def create_user_list(self,
                         name: str,
                         *,
                         user: str = 'me',
                         display_numbers: bool = False,
                         allow_comments: bool = True,
                         privacy: Literal['private', 'link', 'friends', 'public'] = 'private',
                         description: str = '',
                         ) -> Optional[int]:
        """Create a new user list and return its ID."""
        data = self.post(f'users/{user}/lists', {
            'name': name,
            'description': description,
            'privacy': privacy,
            'display_numbers': display_numbers,
            'allow_comments': allow_comments,
        })
        return data['ids']['trakt'] if isinstance(data, Mapping) and 'ids' in data else None

    def delete_user_list(self,
                         list_id: Union[int, str],
                         *,
                         user: str = 'me',
                         ) -> bool:
        """Delete the new user list."""
        data = self.delete(f'users/{user}/lists/{list_id}' )
        return data is not False

    def _single_join(self,
                     call: Callable[..., Sequence[JsonData]],
                     args: Any,
                     *,
                     chunk: int = 0,
                     sort: Optional[SortType] = None,
                     ref_type: Optional[RefType] = None,
                     ) -> ItemList[FFItem]:
        if isinstance(args, str):
            args = args.split(',')
        if not args:
            return ItemList.empty()
        if len(args) == 1:
            items = call(args[0])
        else:
            with ThreadPoolExecutor(max_thread_workers()) as pool:
                datas = pool.map(call, args)
            items = tuple(join_items(*datas, zip_chunk=chunk))
        items = self._sort_items(items, sort=sort)
        items = self._item_list(items, pages=Pages.single(len(items)), ref_type=ref_type)
        return ItemList.single(items)

    def user_collection(self,
                        type: Union[MainMediaType, MainMediaTypeList, Sequence[MainMediaType]],
                        user: str = 'me',
                        *,
                        chunk: int = 0,
                        sort: Optional[SortType] = None,
                        ) -> ItemList[FFItem]:
        """Return user collection list items."""
        # def get(mtype: MainMediaType, limit: int = 0) -> List[FFItem]:
        def get(mtype: MainMediaType) -> Sequence[JsonData]:
            if mtype not in get_typing_args(MainMediaType):
                raise ValueError(f'TraktApi got incorrect content type {mtype!r}')
            ctype = self._main2type[mtype]
            data = self.get(f'users/{user}/collection/{ctype}')
            if isinstance(data, Sequence):
                return data
            return []

        return self._single_join(get, type, chunk=chunk, sort=sort)

    def recommendations(self,
                        type: Union[MainMediaType, MainMediaTypeList, Sequence[MainMediaType]],
                        *,
                        limit: Optional[int] = None,
                        chunk: int = 0,
                        ) -> ItemList[FFItem]:
        """Return social recommendations. No media means mix movies and shows."""
        def get(mtype: MainMediaType) -> List[JsonData]:
            if mtype not in get_typing_args(MainMediaType):
                raise ValueError(f'TraktApi got incorrect content type {mtype!r}')
            ctype = self._main2type[mtype]
            itype = self._ref2item[mtype]
            params = {}
            if limit:
                params['limit'] = limit
            data = self.get(f'recommendations/{ctype}', params=params)
            if isinstance(data, Sequence):
                return [{itype: it} for it in data]
                return self._item_list(data, pages=Pages.single(len(data)), ref_type=mtype)
            return []

        return self._single_join(get, type, chunk=chunk)

    def calendarium(self,
                    type: Union[MainMediaType, MainMediaTypeList, Sequence[MainMediaType]],
                    *,
                    # limit: Optional[int] = None,
                    chunk: int = 0,
                    ) -> ItemList[FFItem]:
        """Return callendar list items."""

        def get(mtype: MainMediaType) -> Sequence[JsonData]:
            if mtype not in get_typing_args(MainMediaType):
                raise ValueError(f'TraktApi got incorrect content type {mtype!r}')
            ctype = self._main2type[mtype]
            frm, to = const.indexer.tvshows.calendar_range
            start_date = dt_date.today() + timedelta(days=to)
            days = max(0, frm - to) + 1  # max(0) aby nie było odwróconych dni, +1 aby złapać start_date włącznie
            days = min(days, 33)  # API
            which = 'all' if ctype == 'movies' else 'my'
            data = self.get(f'calendars/{which}/{ctype}/{start_date}/{days}')
            if isinstance(data, Sequence):
                return tuple(reversed(data))
            return []

        return self._single_join(get, type, chunk=chunk)

    def aliases(self, mtype: MainMediaType, id: Union[int, str]) -> Sequence[JsonData]:
        """Get miedia aliases, `id` is trakt ID, trakt slug, or IMDB ID."""
        ctype = self._main2type[mtype]
        data = self.get(f'{ctype}/{id}/aliases', login_required=False)
        if isinstance(data, Sequence):
            return data
        return []

    # --- Following methods MUST be overrided ---

    def credentials(self) -> TraktCredentials:
        """Return current credencials."""
        raise NotImplementedError('api.trakt.TraktApi.credentials() is not implemented')

    def set_access_token(self, access: JsonData) -> TraktCredentials:
        """Save access token into settings and return new credentials."""
        raise NotImplementedError('api.trakt.TraktApi.set_access_token() is not implemented')

    def remove_access_token(self) -> None:
        """Remove access token from settings."""
        raise NotImplementedError('api.trakt.TraktApi.remove_access_token() is not implemented')

    def dialog_create(self, user_code: str, verification_url: str) -> DialogId:
        """Create GUI dialog."""
        print(f'Enter {user_code!r} on site {verification_url}')

    def dialog_close(self, dialog: DialogId) -> None:
        """Close GUI dialog."""
        print()

    def dialog_is_canceled(self, dialog: DialogId) -> bool:
        """Return True if GUI dialog is canceled."""
        return False

    def dialog_update_progress(self, dialog: DialogId, progress: float) -> None:
        """Update GUI dialog progress-bar."""
        print(f'\r {progress:5.1f}           ', end='')

    # --- Following methods COULD be overrided ---

    def activities_changed(self, activities, *, timestamp: Optional[Union[datetime, float]] = None) -> bool:
        """Called if activites cahnge is detected. NOTE: it's called under lock."""  # noqa: D401
        return False


if TYPE_CHECKING:
    class DePaginationBase(ObjectProxy, TraktApi):
        pass
    class DeResponseBase(ObjectProxy, requests.Response):
        pass
else:
    DePaginationBase = ObjectProxy
    DeResponseBase = ObjectProxy


class DeResponse(DeResponseBase):
    """Proxy to requests.Response, to override JSON."""

    def __init__(self, resp: requests.Response, *, json: JsonResult) -> None:
        super().__init__(resp)
        self._self_json = json

    def json(self, **kwargs) -> Any:
        return self._self_json


class DePagination(DePaginationBase):
    """Proxy to Traktapi using requests with depagination – all pages at once."""

    def __init__(self, api: TraktApi, *, scan_limit: int = const.trakt.page.limit) -> None:
        super().__init__(api)
        self._self_scan_limit: int = scan_limit

    def request(self,
                method: str,
                url: str,
                *,
                data: Optional[JsonData] = None,
                **kwargs: Unpack[TraktRequestKwargs],
                ) -> Optional[requests.Response]:
        """Send requests to trakt.tv for all pages and return all response lists as single reponse."""

        def req(page: int) -> Sequence[JsonData]:
            pp = dict(params)
            pp['page'] = page
            resp = self.__wrapped__.request(method, url, params=pp, data=data, **kwargs)
            return part if resp and isinstance((part := resp.json()), Sequence) else []

        # 'X-Pagination-Page', 'X-Pagination-Limit', 'X-Pagination-Page-Count', 'X-Pagination-Item-Count'
        the_resp: Optional[requests.Response] = None
        params = dict(kwargs.pop('params', None) or ())
        params.pop('page', None)
        kwargs.pop('page', None)
        limit: int = kwargs.pop('limit', params.pop('limit', 0)) or 0  # force limit for all items, NOT for single page scan
        page: int = 1
        params['limit'] = self._self_scan_limit
        # the fist page, get more info
        params['page'] = page
        the_resp = self.__wrapped__.request(method, url, params=params, data=data, **kwargs)
        if the_resp is None:
            return None
        page_count = int(the_resp.headers.get('X-Pagination-Page-Count', 1))
        part: JsonResult = the_resp.json()
        if page_count <= 1 or not isinstance(part, Sequence):
            # already single page or not sequence (we can not join pages)
            return the_resp
        page_size = int(the_resp.headers.get('X-Pagination-Limit', len(part)))
        result: List[JsonData] = [*part]
        # get rest of pages concurrent (in threads)
        with ThreadPoolExecutor(max_thread_workers()) as pool:
            if limit and page_size:
                # limit pages by item limit, it works good only if gages has the same number of items
                parts = pool.map(req, range(2, min(page_count, (limit + page_size - 1) // page_size) + 1))
            else:
                # all existing pages
                parts = pool.map(req, range(2, page_count + 1))
        result.extend(it for part in parts for it in part)
        # return all pageas as single response
        the_resp.headers['X-Pagination-Page'] = '1'
        the_resp.headers['X-Pagination-Limit'] = str(len(result))
        the_resp.headers['X-Pagination-Page-Count'] = '1'
        the_resp.headers['X-Pagination-Item-Count'] = str(len(result))
        return DeResponse(the_resp, json=result)


# --- DEBUG & TESTS ---

if __name__ == '__main__':
    from argparse import ArgumentParser
    from pathlib import Path
    import json
    from .tmdb import TmdbApi
    from .. import cmdline_argv

    class TerminalTrakt(TraktApi):

        def __init__(self, client: str, secret: str, tmdb_api_key: Optional[str] = None) -> None:
            super().__init__()
            self.client: str = client
            self.secret: str = secret
            self.tmdb_api_key: str = tmdb_api_key
            self.path: Path = Path('~/.cache/ff3/trakt-credentials.json').expanduser()
            with open(self.path, encoding='utf-8') as f:
                data = json.load(f)
            if not self.client:
                self.client = data.get('client')
            if not self.secret:
                self.secret = data.get('secret')
            if not self.tmdb_api_key:
                self.tmdb_api_key = data.get('tmdb_api_key')
            self.save_credentials(data)
            self.tmdb = TmdbApi(self.tmdb_api_key)

        def credentials(self) -> TraktCredentials:
            """Return current credencials."""
            try:
                with open(self.path, encoding='utf-8') as f:
                    data = json.load(f).get('token', {})
            except IOError as exc:
                # print(f'TerminalTrakt.credentials(): {exc}')
                data = {}
            return TraktCredentials(client=self.client, secret=self.secret,
                                    access_token=data.get('access_token'),
                                    refresh_token=data.get('refresh_token'))

        def set_access_token(self, access: JsonData) -> TraktCredentials:
            """Save access token into settings."""
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.save_credentials({'token': access})
            return self.credentials()

        def save_credentials(self, data: JsonData):
            data['client'] = self.client
            data['secret'] = self.secret
            data['tmdb_api_key'] = self.tmdb_api_key
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

    def id2ids(id: str) -> JsonData:
        if id[:1] == '@' and id[1:].isdigit():
            return {'trakt': int(id[1:])}
        if id.isdigit():
            return {'tmdb': int(id)}
        return {'imdb': id}

    def id2hist(type: str, id: str) -> JsonData:
        id, se, ep, *_ = id.split('/', 2) + [None, None]
        item = {'ids': id2ids(id)}
        if type != 'movies' and se:
            item['seasons'] = [{'number': int(se)}]
            if ep:
                item['seasons'][0]['episodes'] = [{'number': int(ep)}]
        return item

    def jprint(data: JsonResult) -> None:
        print(json.dumps(data, indent=2))

    # 'X-Pagination-Page', 'X-Pagination-Limit', 'X-Pagination-Page-Count', 'X-Pagination-Item-Count'

    p = ArgumentParser()
    p.add_argument('--client', help='Client ID / app ID')
    p.add_argument('--secret', help='Client secret')
    p.add_argument('--tmdb-api-key', help='TMDB API key, for get extra info')
    p.add_argument('-p', '--page', type=int, help='page number (starts from 1)')
    p.add_argument('-l', '--page-limit', type=int, help='page limit (size), default 10')
    pp = p.add_subparsers(title='command', dest='cmd')
    p_sc = pp.add_parser('scrobble')
    p_sc.add_argument('action', choices=get_typing_args(ScrobbleAction), help='scrobble action')
    p_sc.add_argument('type', choices=get_typing_args(PlayContentType), help='media type')
    p_sc.add_argument('id', type=id2ids, help='imdb/tmdb id')
    p_sc.add_argument('progress', nargs='?', type=float, help='scrobble action')
    p_pb = pp.add_parser('playback')
    p_wt = pp.add_parser('watched')
    p_wt.add_argument('type', choices=('movies', 'shows'))
    p_wt.add_argument('--full', action='store_true', help='return full data')
    p_hi = pp.add_parser('history')
    p_hi.add_argument('type', choices=get_typing_args(HistoryContentType))
    p_hi.add_argument('trakt_id', nargs='?', default='', help='track ID to show only one element')
    p_hi_x = p_hi.add_mutually_exclusive_group()
    p_hi_x.add_argument('-a', '--add', nargs='+', metavar='ID', help='add imdb or tmdb ID')
    p_hi_x.add_argument('-r', '--remove', nargs='+', metavar='ID', help='remove imdb or tmdb ID')
    p_hi_x.add_argument('-i', '--ids', nargs='+', metavar='ID', help='remove by history entry ID')
    p_hi.add_argument('--full', action='store_true', help='return full data')
    p_ac = pp.add_parser('activities')
    p_sy = pp.add_parser('sync')
    # p_tm = pp.add_parser('tmdb')
    # p_tm.add_argument('type', choices=('movie', 'tv'))
    # p_tm.add_argument('id', nargs='+', help='list of TMDB IDs')
    args = p.parse_args(cmdline_argv[1:])
    # print(args); exit()  # DEBUG

    trakt = TerminalTrakt(args.client, args.secret, tmdb_api_key=args.tmdb_api_key)
    # trakt.auth()
    # trakt.refresh()
    try:
        params = {}
        if args.page:
            params['page'] = args.page
        if args.page_limit:
            params['limit'] = args.page_limit

        if args.cmd == 'scrobble':
            progress = 50 if args.progress is None else args.progress
            jprint(trakt.scrobble(args.action, args.type, progress, ids=args.id))
        elif args.cmd == 'playback':
            jprint(trakt.get('sync/playback/'))
        elif args.cmd == 'watched':
            if args.full:
                params['extended'] = 'full'
            jprint(trakt.get(f'sync/watched/{args.type}'))
        elif args.cmd == 'history':
            if args.add:
                jprint({args.type: [id2hist(args.type, a) for a in args.add]})
                jprint(trakt.post('sync/history/', data={args.type: [id2hist(args.type, a) for a in args.add]}))
            elif args.ids:
                jprint(trakt.post('sync/history/remove', data={'ids': [int(a) for a in args.ids]}))
            elif args.remove:
                jprint({args.type: [id2hist(args.type, a) for a in args.remove]})
                jprint(trakt.post('sync/history/remove', data={args.type: [id2hist(args.type, a) for a in args.remove]}))
            else:
                if args.full:
                    params['extended'] = 'full'
                jprint(trakt.get(f'sync/history/{args.type}/{args.trakt_id}', params=params))
        elif args.cmd == 'activities':
            jprint(trakt.get_last_activities())
        elif args.cmd == 'sync':
            from pprint import pprint

            def playback_from_item(item: JsonData, type: str = None) -> TraktPlayback:
                """Create DB row from trakt item JSON data."""
                vtype = item.get('type', type)
                ids = item[vtype]['ids']
                imdb = ids.get('imdb')
                tmdb = ids.get('tmdb')
                ffid = VideoIds.make_video_id(imdb=imdb, tmdb=tmdb)
                values = {'ffid': ffid}
                values.update(trakt_id=ids.get('trakt_id'), imdb=imdb, tmdb=tmdb, slug=ids.get('slug'), type=vtype, playback_id=item.get('id'))
                for attr in ('progress', 'paused_at', 'play_count', 'last_watched_at'):
                    values[attr] = item.get(attr)
                if vtype == 'episode':
                    ep = item['episode']
                    ids = item['show']['ids']
                    values.update(episode=ep['number'], season=ep['season'], trakt_id=ids.get('trakt_id'),
                                  imdb=imdb, tmdb=tmdb, slug=ids.get('slug'))
                return TraktPlayback(**values)

            pb = [playback_from_item(item) for item in trakt.get_playblack_list()]
            wm = [playback_from_item(item, type='movie') for item in trakt.get_watched_list('movies')]
            # ws = [playback_from_item(item, type='episode') for item in trakt.get_watched_list('shows')]
            out = _playback_merge([], pb, wm)#, ws)
            pprint(out)
        elif args.cmd == 'tmdb':
            print(json.dumps(trakt.get_tmdb_info(args.type, args.id, tv_episodes=True), indent=2))

    except TraktExcepiton as exc:
        print(f'{exc.url}: {exc.code}: {exc.text}')
        raise

    # print(json.dumps(trakt.get('shows/173337/seasons?translations=pl'), indent=2))
    # print(json.dumps(trakt.get('shows/173337/seasons/0?translations=pl'), indent=2))
    # print(json.dumps(trakt.get('shows/173337/seasons/1?translations=pl'), indent=2))
