from __future__ import annotations
from typing import TYPE_CHECKING
from typing import Iterable, Callable
from typing_extensions import TypedDict, NotRequired, Literal
from datetime import datetime, timedelta
from requests_cache import SerializerType, ExpirationPattern
from requests_cache.backends import BaseCache
from future.backports.http.cookiejar import CookieJar
import requests
from .types import JsonResult
from cdefs import NetCacheName

CacheArg = NetCacheName | bool | None
ExpirationTime = int | float | str | datetime | timedelta | None
ExpirationPatterns = dict[ExpirationPattern, ExpirationTime]
FilterCallback = Callable[[requests.Response], bool]
KeyCallback = Callable[..., str]

Data = dict[str, str | int | float | None] | Iterable[tuple[str, str | int | float | None]] | str | bytes | None

Method = Literal['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']


class CacheSessionExArgs(TypedDict):
    """Arguments for the cached session."""
    # cache_name: NotRequired[str]
    # expire_after: NotRequired[ExpirationTime]
    backend: NotRequired[str | BaseCache]
    serializer: NotRequired[SerializerType | None]
    urls_expire_after: NotRequired[ExpirationPatterns | None]
    cache_control: NotRequired[bool]
    allowable_codes: NotRequired[Iterable[int]]
    allowable_methods: NotRequired[Iterable[str]]
    always_revalidate: NotRequired[bool]
    ignored_parameters: NotRequired[Iterable[str]]
    match_headers: NotRequired[Iterable[str] | bool]
    filter_fn: NotRequired[FilterCallback | None]
    key_fn: NotRequired[KeyCallback | None]
    stale_if_error: NotRequired[bool | int]


class CacheSessionArgs(CacheSessionExArgs):
    """Arguments for the cached session."""
    cache_name: NotRequired[str]
    expire_after: NotRequired[ExpirationTime]


class SomeRequestOrigArgs(TypedDict):
    # method: Literal['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']
    headers: NotRequired[dict[str, str] | None]
    cookies: NotRequired[dict[str, str] | CookieJar | None]
    files: NotRequired[dict[str, str | bytes] | Iterable[tuple[str, str | bytes]] | None]
    auth: NotRequired[tuple[str, str] | None]
    timeout: NotRequired[float | tuple[float, float] | None]
    allow_redirects: NotRequired[bool | None]
    proxies: NotRequired[dict[str, str] | None]
    hooks: NotRequired[dict[str, Callable[[requests.Response], None]] | None]
    stream: NotRequired[bool | None]
    verify: NotRequired[bool | str | None]
    cert: NotRequired[str | tuple[str, str] | None]


class RequestOrigArgsWithoutUrl(SomeRequestOrigArgs):
    params: NotRequired[Data]
    data: NotRequired[Data]
    json: NotRequired[JsonResult | None]


class RequestOrigArgs(RequestOrigArgsWithoutUrl):
    # method: Literal['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']
    url: str


class RequestCacheExArgs(TypedDict):
    only_if_cached: NotRequired[bool]
    refresh: NotRequired[bool]
    force_refresh: NotRequired[bool]


class RequestCacheArgs(RequestCacheExArgs):
    expire_after: NotRequired[ExpirationTime]


class RequestArgs(RequestCacheArgs, RequestOrigArgs):
    pass


class RequestMethodExArgs(RequestCacheExArgs, SomeRequestOrigArgs):
    pass


class RequestMethodArgs(RequestCacheArgs, SomeRequestOrigArgs):
    pass


class RequestFunctionArgs(CacheSessionExArgs, RequestOrigArgsWithoutUrl):
    pass
