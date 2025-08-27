
from __future__ import annotations
from typing import Protocol, overload, TYPE_CHECKING
from threading import current_thread
from pathlib import Path
from functools import wraps
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from attrs import define
from wrapt.wrappers import ObjectProxy
import requests_cache
from requests import *  # noqa: F401, F403  # type: ignore
import requests as _requests
from .threads import ThreadCanceled, ThreadSingleLocal
from const import const, NetCache

if TYPE_CHECKING:
    from typing_extensions import Literal, Unpack, ParamSpec, TypeVar, Callable, Self, Iterator
    from requests import (adapters, api, auth, certs, check_compatibility, codes, compat, cookies, exceptions, hooks, models, packages,  # noqa: F401
                          sessions, status_codes, structures,)
    from requests_cache.models import AnyResponse
    from requests_cache.backends.filesystem import BaseCache
    from ._requests_types import (CacheArg, ExpirationTime, CacheSessionExArgs, RequestFunctionArgs, RequestMethodArgs,
                                  RequestMethodExArgs, RequestOrigArgsWithoutUrl)
    from ._requests_types import JsonResult, Data, Method
    P = ParamSpec('P')
    R = TypeVar('R')


# Keyword arguments for CachedSession (without cache_name and expire_after).
_sess_ex_args = {
    'backend',
    'serializer',
    'urls_expire_after',
    'cache_control',
    'allowable_codes',
    'allowable_methods',
    'always_revalidate',
    'ignored_parameters',
    'match_headers',
    'filter_fn',
    'key_fn',
    'stale_if_error',
}


@define
class CacheConfig:
    """Configuration for cache decorator."""
    cache: CacheArg = None
    expire_after: ExpirationTime = None

    def append_to_stack(self) -> list[CacheConfig]:
        """Append this configuration to the current thread's cache config stack."""
        loc = ThreadSingleLocal()
        cc: list[CacheConfig] = getattr(loc, 'netcache_config_stack', [])
        loc.netcache_config_stack = cc
        cc.append(self)
        return cc

    @contextmanager
    def context(self) -> Iterator[Self]:
        cc = self.append_to_stack()
        try:
            yield self
        finally:
            cc.pop()

    @classmethod
    def current(cls) -> CacheConfig:
        """Get the current cache configuration."""
        loc = ThreadSingleLocal()
        cc: list[CacheConfig] = getattr(loc, 'netcache_config_stack', [])
        if not cc:
            return CacheConfig()
        return cc[-1]


def cache_folder() -> Path:
    """Return the path to the netcache folder."""
    from .control import dataPath
    folder = Path(dataPath) / 'netcache'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def cache_params(cache: CacheArg, expire_after: ExpirationTime) -> tuple[NetCache | None, str | None, ExpirationTime, bool]:
    """Return the cache path based on the provided cache name."""
    # current cache
    folder = cache_folder()
    cc = CacheConfig.current()
    # from .log_utils import fflog
    # fflog.debug(f'cache_params for {current_thread().name}: {cache=}, {expire_after=}, {cc=}  ####################  {cache or cc.cache!r}')
    if cache is None:
        cache = cc.cache
    if cache is None or cache is False:
        # print(f'No cache for {current_thread().name}')
        return None, None, requests_cache.DO_NOT_CACHE, True
    # skip netcache write in widgets
    readonly = False
    if not const.core.netcache.widgets:
        from .control import is_plugin_folder
        if not is_plugin_folder():
            # it's not a folder, it could be a widget and we should do not write to the cache to avoid file lock
            readonly = True
    # determine cache db
    if cache is True:
        cache = 'other'
    netcache = const.core.netcache.cache.get(cache)
    if netcache is None:
        # print(f'cache for {current_thread().name}, using "other.db" with default expire')
        netcache = NetCache(60)
        path, expire = str(folder / 'other'), netcache.expire
    else:
        expire = netcache.expire
        if isinstance(expire, str):
            from .settings import settings
            expire = settings.eval(expire)
        if expire_after is not None:
            expire = expire_after
        # print(f'cache for {current_thread().name}, using "{cache}" with expire {expire}')
        path, expire = str(folder / f'{cache}'), expire
    return netcache, path, expire, readonly


def clear_netcache(cache: CacheArg | None = None) -> None:
    """
    Clear the netcache.

    Remove the cache folder if None.
    Delete all entries in the cache for `cache` is ''.
    Otherwise, delete all entries in the cache for `cache`.
    """
    if cache is None:
        from shutil import rmtree
        folder = cache_folder()
        rmtree(str(folder), ignore_errors=True)
    elif cache:
        _, _, _, _, backend = netcache_backend(cache, expire_after=None)
        if backend is not None:
            backend.clear()
    else:
        for cache in const.core.netcache.cache:
            if cache:
                _, _, _, _, backend = netcache_backend(cache, expire_after=None)
                if backend is not None:
                    backend.clear()


def cleanup_netcache() -> None:
    """Clean up the netcache from expired entries."""
    from datetime import timedelta
    from .log_utils import fflog
    from requests_cache import DO_NOT_CACHE, NEVER_EXPIRE
    fflog.debug('[#####] Cleaning up netcache...')
    for cache in const.core.netcache.cache:
        if cache:
            netcache, _, expire_after, _, backend = netcache_backend(cache, expire_after=None)
            if backend is not None and netcache is not None and netcache.cleanup:
                # from .log_utils import fflog
                # fflog(f'Cleaning up netcache {cache!r} with backend {backend!r}')
                older_than = 0
                if isinstance(expire_after, timedelta):
                    expire_after = expire_after.total_seconds()
                if isinstance(expire_after, int) and expire_after not in (DO_NOT_CACHE, NEVER_EXPIRE):
                    if const.core.netcache.cleanup.expire_factor:
                        older_than = max(1.0, const.core.netcache.cleanup.expire_factor) * expire_after
                    offset = const.core.netcache.cleanup.expire_offset
                    if isinstance(offset, timedelta):
                        older_than += offset.total_seconds()
                    else:
                        older_than += offset
                if older_than:
                    backend.delete(older_than=older_than)
                else:
                    backend.delete(expired=True)


if TYPE_CHECKING:
    _SessionBases = ObjectProxy, requests_cache.CachedSession, _requests.Session
else:
    _SessionBases = ObjectProxy,


def netcache_backend(cache: CacheArg = None, expire_after: ExpirationTime = None) -> tuple[NetCache | None, str | None, ExpirationTime, bool, BaseCache | None]:
    """Return the current netcache backend."""
    netcache, cache_name, expire_after, readonly = cache_params(cache, expire_after)
    if netcache is None or cache_name is None:
        return netcache, cache_name, expire_after, readonly, None
    if const.core.netcache.backend is False:
        return None, None, 0, True, None

    from requests_cache.serializers.pipeline import Stage, SerializerPipeline
    s1, s2 = const.core.netcache.serializer

    is_binary = True
    if s1 == 'pickle':
        import pickle
        from requests_cache.serializers.preconf import base_stage
        stages = [base_stage, Stage(pickle)]
    elif s1 == 'json':
        import json
        from requests_cache.serializers.preconf import json_preconf_stage
        stages = [json_preconf_stage, Stage(json)]
        if s2:
            from requests_cache.serializers.preconf import utf8_encoder
            stages.append(utf8_encoder)
        else:
            is_binary = False
    else:
        raise ValueError(f'Unknown serializer[1] {s1!r} for netcache')

    if s2 == '':
        pass
    elif s2 in ('zlib',):
        import zlib
        stages.append(Stage(dumps=zlib.compress, loads=zlib.decompress))
    elif s2 in ('gzip', 'gz'):
        import gzip
        stages.append(Stage(dumps=gzip.compress, loads=gzip.decompress))
    elif s2 in ('bzip2', 'bz2'):
        import bz2
        stages.append(Stage(dumps=bz2.compress, loads=bz2.decompress))
    elif s2 in ('lzma', 'xz'):
        import lzma
        stages.append(Stage(dumps=lzma.compress, loads=lzma.decompress))
    else:
        raise ValueError(f'Unknown serializer[2] {s2!r} for netcache')

    serializer = SerializerPipeline(stages, name='_'.join((s1, s2)), is_binary=is_binary)

    if const.core.netcache.backend == 'sqlite':
        from sqlite3 import OperationalError
        from requests_cache.backends.sqlite import SQLiteCache
        cache_name = f'{cache_name}.db'
        busy_timeout = int(netcache.busy_timeout * 1000) if netcache.busy_timeout else None
        try:
            backend = SQLiteCache(db_path=cache_name,
                                  busy_timeout=busy_timeout,
                                  wal=netcache.wal,
                                  serializer=serializer)
        except OperationalError as exc:
            # from .log_utils import fflog, fflog_exc                         # XXX
            # fflog(f'Can NOT create SQLiteCache for {cache_name!r}: {exc}')  # XXX
            # fflog_exc()                                                     # XXX
            import sys
            print(f'[FanFilm] Can NOT create SQLiteCache for {cache_name!r}: {exc}', file=sys.stderr)
            return None, None, 0, True, None
    elif const.core.netcache.backend == 'filesystem':
        from requests_cache.backends.filesystem import FileCache
        backend = FileCache(cache_name=cache_name, expire_after=expire_after, decode_content=False,
                            maximum_cache_bytes=netcache.size_limit_in_bytes(),
                            serializer=serializer, readonly=readonly)
    elif const.core.netcache.backend == 'redis':
        from requests_cache.backends.redis import RedisCache
        backend = RedisCache(namespace=cache_name, expire_after=expire_after,
                             host=const.core.netcache.redis.host,
                             port=const.core.netcache.redis.port,
                             ttl=const.core.netcache.redis.ttl,
                             ttl_offset=const.core.netcache.redis.ttl_offset,
                             serializer=serializer, readonly=readonly)
    elif const.core.netcache.backend == 'memory':
        from requests_cache.backends.filesystem import BaseCache
        backend = BaseCache(cache_name=cache_name, expire_after=expire_after,
                            serializer=serializer, readonly=readonly)
    else:
        raise ValueError(f'Unknown backend {const.core.netcache.backend!r} for netcache')

    return netcache, cache_name, expire_after, readonly, backend


class Session(*_SessionBases):
    """Proxy to requests.Session with cache and ThreadCanceled support."""

    if TYPE_CHECKING:
        __wrapped__: requests_cache.CachedSession

    def __init__(self,
                 cache: CacheArg = None,
                 expire_after: ExpirationTime = None,
                 **kwargs: Unpack[CacheSessionExArgs],
                 ) -> None:
        netcache, cache_name, expire_after, readonly, backend = netcache_backend(cache, expire_after)
        if netcache is None or cache_name is None:
            super().__init__(_requests.Session())
            return
        if 'backend' not in kwargs and backend is not None:
            kwargs['backend'] = backend
        super().__init__(requests_cache.CachedSession(cache_name=cache_name, expire_after=expire_after, readonly=readonly, **kwargs))

    def request(
        self,
        method: Method,
        url: str,
        **kwargs: Unpack[RequestOrigArgsWithoutUrl],
    ):
        if (event := getattr(current_thread(), '_stop_requested', None)) is not None and event.is_set():
            raise ThreadCanceled()
        # result = super().request(method=method, url=url, **kwargs)
        result = self.__wrapped__.request(method=method, url=url, **kwargs)
        if event is not None and event.is_set():
            raise ThreadCanceled()
        return result


def request(method: Method,
            url: str,
            *,
            cache: CacheArg = None,
            expire_after: ExpirationTime = None,
            **kwargs: Unpack[RequestFunctionArgs],
            ) -> AnyResponse:
    """Proxy to requests.request with cache and ThreadCanceled suport."""
    sess_args: CacheSessionExArgs = {k: v for k, v in kwargs.items() if k in _sess_ex_args}  # type: ignore[reportAssignmentType]
    if sess_args:
        kwargs = {k: v for k, v in kwargs.items() if k not in _sess_ex_args}  # type: ignore[reportAssignmentType]
    with Session(cache=cache, expire_after=expire_after, **sess_args) as session:
        # from .log_utils import fflog                                       # XXX
        # _cache = CacheConfig.current().cache if cache is None else cache   # XXX
        # fflog(f'[NETCACHE] Request {method} {url} with cache={_cache!r}')  # XXX
        return session.request(method=method, url=url, **kwargs)


def get(url: str,
        params: Data = None,
        *,
        cache: CacheArg = None,
        **kwargs: Unpack[RequestMethodExArgs],
        ) -> AnyResponse:
    """Proxy to requests.get with cache and ThreadCanceled suport."""
    return request("GET", url, params=params, cache=cache, **kwargs)


def options(url: str,
            params: Data = None,
            *,
            cache: CacheArg = None,
            **kwargs: Unpack[RequestMethodArgs],
            ) -> AnyResponse:
    """Proxy to requests.options with cache and ThreadCanceled suport."""
    return request("OPTIONS", url, params=params, cache=cache, **kwargs)


def head(url: str,
         params: Data = None,
         *,
         cache: CacheArg = None,
         **kwargs: Unpack[RequestMethodArgs],
         ) -> AnyResponse:
    """Proxy to requests.head with cache and ThreadCanceled suport."""
    kwargs.setdefault("allow_redirects", False)
    return request("HEAD", url, params=params, cache=cache, **kwargs)


def post(url: str,
         data: Data = None,
         json: JsonResult | None = None,
         *,
         params: Data = None,
         cache: CacheArg = None,
         **kwargs: Unpack[RequestMethodArgs],
         ) -> AnyResponse:
    """Proxy to requests.post with cache and ThreadCanceled suport."""
    return request("POST", url, params=params, data=data, json=json, cache=cache, **kwargs)


def put(url: str,
        data: Data = None,
        json: JsonResult | None = None,
        *,
        params: Data = None,
        cache: CacheArg = None,
        **kwargs: Unpack[RequestMethodArgs],
        ) -> AnyResponse:
    """Proxy to requests.put with cache and ThreadCanceled suport."""
    return request("PUT", url, params=params, data=data, json=json, cache=cache, **kwargs)


def patch(url: str,
          data: Data = None,
          json: JsonResult | None = None,
          *,
          params: Data = None,
          cache: CacheArg = None,
          **kwargs: Unpack[RequestMethodArgs],
          ) -> AnyResponse:
    """Proxy to requests.patch with cache and ThreadCanceled suport."""
    return request("PATCH", url, params=params, data=data, json=json, cache=cache, **kwargs)


def delete(url: str,
           *,
           cache: CacheArg = None,
           **kwargs: Unpack[RequestMethodArgs],
           ) -> AnyResponse:
    """Proxy to requests.delete with cache and ThreadCanceled suport."""
    return request("DELETE", url, cache=cache, **kwargs)


class CacheDecoProto(Protocol):
    """Protocol for cache decorator."""
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type, exc_value, traceback) -> None: ...
    def __call__(self, func: Callable[P, R], /) -> Callable[P, R]: ...


def netcache(cache: CacheArg,
             *,
             expire_after: ExpirationTime = None,
             ) -> CacheDecoProto:
    """
    Cache decorator for requests functions.

    Example:
    >>> @netcache('a')
    >>> class A:
    >>>
    >>>     def foo(self):
    >>>         requires.get('http://a-host/')      # This will use the cache 'a' (from the class decorator)
    >>>
    >>>     @netcache('b')
    >>>     def bar(self):
    >>>         requires.get('http://b-host/')      # This will use the cache 'b' (from the method decorator)
    >>>         with netcache('c'):
    >>>             requires.get('http://c-host/')  # This will use the cache 'c' (from the context manager)
    """

    class CacheDecorator:
        """Cache decorator class."""

        def __init__(self, config: CacheConfig) -> None:
            self.config = config

        def __call__(self, func_or_type: Callable[P, R], /) -> Callable[P, R]:
            """Decorate."""

            def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
                with self.config.context():
                    return func(*args, **kwargs)

            # try:
            #     setattr(func_or_type, '_ff_netcache', self.config)
            # except AttributeError:
            #     from .log_utils import fflog
            #     fflog(f'Cannot set _ff_netcache on {func_or_type!r}, classes with metaclass with __slot__ are not supported')

            if isinstance(func_or_type, type):
                def wrapper(func):
                    """Wrap class methods with cache."""
                    @wraps(func)
                    def wrapped(*args, **kwargs):
                        with self.config.context():
                            return func(*args, **kwargs)
                    return wrapped
                cls = func_or_type
                if cls_dict := getattr(cls, '__dict__', None):
                    for name, value in cls_dict.items():
                        if not name.startswith('_') and callable(value):
                            setattr(cls, name, wrapper(value))
                return cls

            func = func_or_type
            return wraps(func)(wrapped)

        def __enter__(self) -> Self:
            """Enter the context manager."""
            CacheConfig(cache=cache, expire_after=expire_after).append_to_stack()
            return self

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            """Exit the context manager."""
            loc = ThreadSingleLocal()
            cc: list[CacheConfig] = getattr(loc, 'netcache_config_stack', [])
            if cc:
                cc.pop()
            print(f'exit {loc=}, {cc=}, {self=}')
            if exc_type is not None:
                print(f'Exception in cache decorator: {exc_type}, {exc_value}')

    config = CacheConfig(cache=cache, expire_after=expire_after)
    return CacheDecorator(config)


@overload
def no_netcache(func: Callable[P, R], /) -> Callable[P, R]: ...


@overload
def no_netcache(none: Literal[None] = None, /) -> CacheDecoProto: ...


def no_netcache(func_on_none: Callable[P, R] | None = None, /) -> Callable[P, R] | CacheDecoProto:
    """
    Decorator to disable cache for a specific function.

    Example:
    >>> @netcache('a')
    >>> class A:
    >>>
    >>>     def foo(self):
    >>>         requires.get('http://a-host/')    # This will use the cache 'a' (from the class decorator)
    >>>         with no_netcache():
    >>>             requires.get('http://host/')  # This will NOT use any cache
    >>>
    >>>     @no_netcache
    >>>     def bar(self):
    >>>         requires.get('http://host/')      # This will NOT use any cache
    """
    if func_on_none is None:
        return netcache(False)
    return netcache(False)(func_on_none)


class RequestsPoolExecutor(ThreadPoolExecutor):
    """ThreadPoolExecutor with support for requests cache."""

    def __init__(self,
                 max_workers: int | None = None,
                 thread_name_prefix: str = 'requests-',
                 initializer: Callable[[], object] | None = None,
                 initargs: tuple[()] = (),
                 ) -> None:

        def init(config: CacheConfig, initializer: Callable[[], object] | None = None, initargs: tuple[()] = ()) -> None:
            """Netcache initializer for the thread pool."""
            loc = ThreadSingleLocal()
            loc.netcache_config_stack = [config]
            if initializer is not None:
                initializer(*initargs)

        config = CacheConfig.current()
        super().__init__(max_workers=max_workers, thread_name_prefix=thread_name_prefix,
                         initializer=init, initargs=(config, initializer, initargs))
        self._cache_config_stack: list[CacheConfig] = []


if __name__ == '__main__':
    from .threads import Thread

    @netcache('media')
    class A:
        @netcache('b', expire_after=5)
        def foo(self):
            resp = get('http://localhost:8000?b')
            print('foo', resp.text, resp.from_cache)
            with netcache('c'):
                resp = get('http://localhost:8000?c')
                print('foo.with', resp.text, resp.from_cache)
        # @no_netcache
        def bar(self):
            resp = get('http://localhost:8000?a')
            print('bar', resp.text, resp.from_cache)
        def call(self):
            self.bar()
            # self.foo()

    a = A()
    t = Thread(target=a.call)
    t.start()
    t.join()
