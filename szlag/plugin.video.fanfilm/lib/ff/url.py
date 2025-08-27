"""
Simple routing based on libka, without annotations.
"""

import re
import json
from urllib.parse import SplitResult, urlsplit, urlunsplit, parse_qsl, quote, quote_plus
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import (
    Optional, Union, Any,
    Tuple, Dict,
    Mapping,
    Callable, Type, TypeVar,
    TYPE_CHECKING,
)
from typing_extensions import (
    ParamSpec, get_args, get_origin, Self, Literal,
    SupportsIndex, Protocol, TypeAlias, Annotated,
)

from . import log_utils as logger
from .tricks import get_method_class, MISSING
from .types import is_optional, remove_optional
from ..defs import MediaRef

# type aliases
Args = Tuple[Any]
KwArgs = Dict[str, Any]
# Params = Dict[Union[str, int], Any]
Params = Dict[str, Any]
ArgType = Union[Type, Callable]

R = re.compile


T = TypeVar('T')


@dataclass
class RouteCalling:
    method: Optional[Callable[..., None]] = None
    kwargs: KwArgs = field(default_factory=dict)

    def set(self, method: Callable[..., None], kwargs: KwArgs) -> None:
        self.method = method
        self.kwargs = kwargs

    def clear(self):
        self.method = None
        self.kwargs = {}


_ff_route_calling = RouteCalling()


# def ann_subtype(cls, ann, default=str):
#     """Remove Optional and returns subtype from PathArg (or `str` if none)."""
#     ann = remove_optional(ann)
#     origin = getattr(ann, '__origin__', ann)
#     try:
#         if origin is cls or issubclass(origin, cls):
#             return getattr(ann, '__args__', (default,))[0]
#     except TypeError:
#         pass
#     return None


def ann_type(ann: Annotated, cls: Optional[Type] = None) -> Tuple[Type, Tuple[Any, ...]]:
    """Check and return type and annotated details (meta)."""
    ann = remove_optional(ann)
    origin = get_origin(ann)
    if origin is not Annotated:
        return ann, ()
    args = get_args(ann)
    typ, meta = args[0], args[1:]
    if cls is None or cls in meta:
        return typ, meta
    return typ, ()


class _PathArg:
    """Path argument pseudo-type for annotations."""


class _Unsigned:
    """Unsigned[int] argument pseudo-type for annotations."""


class _Positive:
    """Positive[int] argument pseudo-type for annotations."""


PathArg: TypeAlias = Annotated[T, _PathArg]
Unsigned: TypeAlias = Annotated[T, _Unsigned]
Positive: TypeAlias = Annotated[T, _Positive]
# RegEx: TypeAlias = Annotated[T, _Positive]


# Author: rysson
def item_iter(obj):
    """
    Return item (key, value) iterator from dict or pair sequence.
    Empty seqence for None.
    """
    if obj is None:
        return ()
    if isinstance(obj, Mapping):
        return obj.items()
    return obj


def prepare_query_params(params: Optional[KwArgs] = None, *, raw: Optional[KwArgs] = None) -> Dict[str, Any]:
    """
    Helper. Make dict ready to query. Can be used with URL.

    Path is appended (if exists).
    All data from `params` are prepared (ex. using JSON).
    All data from `raw` are picked (+gzip +b64).

    Note: `raw` is not used.
    """
    def prepare(s):
        if s is True:
            # Non-standard behavior !
            return 'true'
        if s is False:
            # Non-standard behavior !
            return 'false'
        if isinstance(s, (dict, list)):
            # Non-standard behavior !
            s = json.dumps(s)
        elif not isinstance(s, str):
            s = str(s)
        return s

    result = {}
    result.update((k, prepare(v)) for k, v in item_iter(params))
    # result.update((k, encode_data(v)) for k, v in item_iter(raw))
    return result


def xquote(s: Any, safe: str = '/') -> str:
    """prepare_query_params.prepare + urllib.parse.quote for the single value."""
    if s is True:
        # Non-standard behavior !
        return 'true'
    if s is False:
        # Non-standard behavior !
        return 'false'
    if isinstance(s, (set, frozenset)):
        # Non-standard behavior !
        s = tuple(s)
    if isinstance(s, (dict, list, tuple)):
        # Non-standard behavior !
        s = json.dumps(s)
    elif not isinstance(s, str):
        s = str(s)
    return quote_plus(s, safe=safe)


# class Query(str):
#
#     __slots__ = ('_url',)
#
#     def __new__(cls, value: str, *, url: 'URL'):
#         obj = str.__new__(cls, value)
#         obj._url = url
#         return obj
#
#     def __repr__(self) -> str:
#         return f'query({super().__repr__()})'
#
#     def __str__(self) -> str:
#         return super().__str__()
#
#     def __getitem__(self, key: str) -> str:
#         return self._url.params.get(key)


class URL(SplitResult):
    """Parsed URL."""

    _args: Optional[Params]
    _safe: str

    def __new__(cls,
                url: Union[str, 'URL'],
                netloc: Optional[str] = None,
                path: Optional[str] = None,
                query: Optional[str] = None,
                fragment: Optional[str] = None,
                *,
                safe: str = "?/:@",
                allow_fragments: bool = False,
                ) -> 'URL':
        if isinstance(url, SplitResult):
            scheme, netloc, path, query, fragment = url
        elif netloc is None or path is None:
            scheme, netloc, path, query, fragment = urlsplit(url, allow_fragments=allow_fragments)
        else:
            scheme = url
        obj: URL = SplitResult.__new__(cls, scheme, netloc, path, query or '', fragment or '')
        obj._args = None
        obj._safe = safe
        # obj._args: Optional[Params] = None
        # obj._safe: str = safe
        return obj

    if TYPE_CHECKING:
        def __init__(self, url: Union[str, 'URL'], netloc: Optional[str] = None, path: Optional[str] = None,
                     params: Optional[str] = None, query: Optional[str] = None, fragment: Optional[str] = None,
                     *, safe: str = "?/:@") -> None:  ...

    def __str__(self) -> str:
        return urlunsplit(self)

    # @property
    # def query(self) -> Query:
    #     return Query(self[4], url=self)

    @property
    def args(self) -> Params:
        if self._args is None:
            self._args = dict(parse_qsl(self.query))
        return self._args

    query_dict = args

    def __getitem__(self, key: Union[SupportsIndex, slice, str]) -> Any:
        if isinstance(key, str):
            return self.args.get(key)
        return super().__getitem__[key]

    def __mod__(self, params: Params) -> 'URL':
        query: str
        if isinstance(params, Mapping):
            params = {**self.args, **params}
            query = '&'.join(f'{quote(k, safe=self._safe)}={xquote(v, safe=self._safe)}'
                             for k, v in params.items() if v is not None)
        else:
            raise TypeError(f'Unsported query type {type(params)} in URL % QUERY')
        return URL(self.scheme, self.netloc, self.path, self.params, query, self.fragment)

    def update_query(self, params: Union[None, Params, str] = None, **kwargs) -> 'URL':
        query: str
        if params is None:
            if not kwargs:
                raise TypeError('Use URL.update_query() with positional arguemnt or keyword arguments, not both')
            params = kwargs
        elif kwargs:
            raise TypeError('URL.update_query() missing arguemnt')
        if isinstance(params, str):
            params = dict(parse_qsl(params))
        if isinstance(params, Mapping):
            params = {**self.args, **params}
            query = '&'.join(f'{quote(k)}={xquote(v)}' for k, v in params.items() if v is not None)
        else:
            raise TypeError(f'Unsported query type {type(params)} in with_query()')
        return URL(self.scheme, self.netloc, self.path, self.params, query, self.fragment, safe=self._safe)

    def with_query(self, _params: Union[None, Params, str] = None, /, **kwargs) -> 'URL':
        query: str
        if _params is None:
            if not kwargs:
                raise TypeError('URL.with_query() missing argument')
            params = kwargs
        elif kwargs:
            raise TypeError('Use URL.with_query() with positional arguemnt or keyword arguments, not both')
        else:
            params = _params
        if isinstance(params, str):
            query = params
        elif isinstance(params, Mapping):
            query = '&'.join(f'{quote(k)}={xquote(v)}' for k, v in params.items() if v is not None)
        else:
            raise TypeError(f'Unsported query type {type(params)} in with_query()')
        return URL(self.scheme, self.netloc, self.path, query, self.fragment, safe=self._safe)

    def without_remote(self) -> 'URL':
        """Return URL without remote data (scheme, netloc)."""
        return URL(*self._replace(scheme='', netloc=''))

    def replace(self, **kwargs) -> 'URL':
        """Return URL with replaced fields."""
        return URL(*self._replace(**kwargs))

    @contextmanager
    def safe(self, safe: str):
        old_safe: str = self._safe
        self._safe += safe
        try:
            yield
        finally:
            self._safe = old_safe

    def replace_safe(self, safe: str):
        old_safe: str = self._safe
        self._safe = safe
        try:
            yield
        finally:
            self._safe = old_safe
