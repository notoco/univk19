"""
Simple routing based on libka, without annotations.
"""

from sys import version_info
import re
import json
from urllib.parse import quote_plus, unquote_plus
from itertools import chain
from inspect import signature as _signature, Signature, ismethod, isclass
from types import MethodType
from enum import Enum, IntEnum, Flag, IntFlag
from functools import wraps
from copy import copy
from typing import (
    Optional, Union, Any,
    Tuple, List, Dict,
    Sequence, Mapping,
    Iterable, Iterator,
    NamedTuple, Callable, Type, TypeVar, ClassVar,
    Generic, Generator,
    Pattern, Match,
    overload, cast,
    TYPE_CHECKING,
)
from typing_extensions import (
    ParamSpec, get_args, get_origin, get_type_hints, assert_type, Self, Literal,
    SupportsIndex, Protocol, TypeAlias, Annotated, TypeGuard, TypeForm,
    Unpack, NotRequired,
)
from attrs import define, frozen, field, evolve

from . import log_utils as logger
from .url import URL, item_iter
from .tricks import str_removeprefix, MISSING
from .types import (
    is_optional, remove_optional, mk_bool, EllipsisType, StrEnum,
    UPath, Path, Unsigned, Positive, EnumEnum, EnumFullName, EnumName, EnumValue,
    ArgDescr, LiteralArg, EnumArg, EnumDumper, AnnMeta,
    ann_type, find_arg_descr, mk_upath, mk_path, uint, pint, ufloat,
    ANN_TYPES as BASIC_ANN_TYPES
)
from ..defs import MediaRef, MediaRefWithNoType, RefType

# type aliases
Args = Tuple[Any]
KwArgs = Dict[str, Any]
# Params = Dict[Union[str, int], Any]
Params = Dict[str, Any]

R = re.compile

T = TypeVar('T')
P = ParamSpec('P')
RET = TypeVar('RET')
C = TypeVar('C', bound=Type[Any])
# D = TypeVar('D', bound=Union[Callable[P, None], Type[C]])
CLS = TypeVar('CLS', bound=Type[Any])
PARENT = TypeVar('PARENT', bound='RouteObject')
SUB = TypeVar('SUB', bound='RouteObject')
CALL_CLS = TypeVar('CALL_CLS')
CALL_PARENT = TypeVar('CALL_PARENT', bound='RouteObject')
CALL_SUB = TypeVar('CALL_SUB', bound='RouteObject')
# ROUTE_ARG = TypeVar('ROUTE_ARG', Callable[P, None], Type[SUB]])


_ATTR_TARGET_ROUTE_DEFS = '_ff_route_defs'
_ATTR_CLASS_ROUTERS = '_ff_routers'
_SUBOBJECT_PARENT = '_ff_subobject_parent'
# _SUBOBJECT_CHILDREN = '_ff_subobject_children'
# _SUBOBJECT_CHILDREN_BY_NAME = '_ff_subobject_children_by_name'
_RX_SPLIT_CAMEL_WORDS = re.compile(r'([A-Z]+[a-z0-9]*)')


# class SafeUrl(str):
#     pass


@define
class RouteCalling:
    method: Optional[Callable[..., None]] = None
    kwargs: KwArgs = field(factory=dict)
    route:  'Optional[RouteEntry]' = None

    def set(self, method: Callable[..., None], kwargs: KwArgs, *, route:  'Optional[RouteEntry]' = None) -> None:
        self.method = method
        self.kwargs = kwargs
        self.route = route

    def clear(self):
        self.method = None
        self.kwargs = {}
        self.route = None

    def __bool__(self) -> bool:
        """Check if route calling data is set."""
        return self.method is not None and self.route is not None


_ff_route_calling = RouteCalling()


def current_route() -> RouteCalling:
    """Get current route calling data."""
    return evolve(_ff_route_calling)


class _PathArg:
    """Path argument pseudo-type for annotations."""


class ArgFormat(str):
    """Format for endpoint argument, see EntryParam.value_format."""


RegEx = re.compile

PathArg: TypeAlias = Annotated[T, _PathArg]


def encode_params(params: Optional[KwArgs] = None, *, raw: Optional[KwArgs] = None) -> str:
    """
    Helper. Make query params with given data.

    Path is appended (if exists).
    All data from `params` are quoted.
    All data from `raw` are picked (+gzip +b64).
    """
    def quote_str_plus(s):
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
        return quote_plus(s)

    par_iter = item_iter(params)
    # raw_iter = item_iter(raw)
    return '&'.join(chain(
        ('%s=%s' % (quote_str_plus(k), quote_str_plus(v)) for k, v in par_iter),
        # ('%s=%s' % (quote_str_plus(k), encode_data(v)) for k, v in raw_iter).
    ))


RX_STR = r'[^/]+'


def mk_ref(v: str) -> MediaRef:
    """Make media reference with explicit type."""
    mtype, *args = v.split('/')
    if mtype not in get_args(RefType):
        raise ValueError(f'Incorrect media type {mtype!r}')
    return MediaRef(cast(RefType, mtype), *map(int, args[:3]))


def mk_ref_no_type(v: str) -> MediaRefWithNoType:
    """Make media reference. Type is unknown."""
    return MediaRefWithNoType('', *map(int, v.split('/')[:3]))


def mk_url(v: str) -> URL:
    """Make Path()."""
    if not v.startswith('/'):
        v = f'/{v}'
    return URL(v)


def mk_safe_url(v: str) -> str:
    """Make Path()."""
    return unquote_plus(v)


#: Annotated typed, used on path (see _RE_PATH_ARG) and with PathArg[...].
ANN_TYPES = {
    **BASIC_ANN_TYPES,
    MediaRefWithNoType:  ArgDescr(mk_ref_no_type,  r'(\d+)(?:/(\d+)(?:/(\d+))?)?',            dumper=lambda v, _: f'{v:i}'),  # NOTE: without ref.type (!!!)
    MediaRef:            ArgDescr(mk_ref,          r'([a-z]\w*)/(\d+)(?:/(\d+)(?:/(\d+))?)?', dumper=lambda v, _: f'{v:a}'),  # NOTE: with ref.type
}


class RouteType(Enum):
    """Type of RouteEntry."""  # Not used much yet.
    UNKNOWN = ''
    ENDPOINT = 'enpoint'
    OBJECT = 'object_descriptor'
    OBJECT_GET = 'object_getter'  # the only one is used with @subobject_route
    ROUTER = 'router'


@define
class EntryParam:
    """Single argument description to handle the argument type conversion."""
    #: Param name.
    name: str
    #: Param type / function to create.
    types: Sequence[Union[TypeForm[Any], Callable[[str], Any]]]
    #: True if optional.
    optional: bool = False
    #: Annotated meta.
    meta: AnnMeta = ()
    #: Ture, if param is used in the path.
    path_arg: bool = True
    #: Path arg is explicit in the path pattern.
    explicit: bool = False
    #: Default value.
    default: Any = MISSING
    #: Format for value.
    value_format: Optional[str] = None

    def format(self, value: Any) -> str:
        """Foramt value."""
        if self.value_format is None:
            return str(value)
        return self.value_format.format(value)


@define(kw_only=True)
class RouteEntry:
    """Route entry, describe endpoint or sub-router (subobject). Used to disptach and build URL."""
    #: Path regex.
    path: Pattern[str]
    #: Method class (set on class definition: in RouteObject.__init_subclass__).
    cls: Optional[Type[Any]] = None
    #: Method to call.
    method: Optional[Callable[..., None]] = None
    #: Sub-object
    subobject: Optional['subobject'] = None
    #: Sub-object
    subrouter: Optional['Router'] = None
    #: Params defined in route path as "{param}, type is in method annotation.".
    params: Dict[str, EntryParam] = field(factory=dict)
    #: Path for format in url_for().
    path_format: str = ''
    #: Label to show in folder, should be localized by L().
    label: str = ''
    #: Type of route entry.
    route_type: RouteType = RouteType.UNKNOWN  # TODO: implement it (now only OBJECT_GET is used)
    #: Method signature.
    signature: Optional[Signature] = None
    #: True it method has more route variants
    has_variants: bool = False

    @property
    def func(self) -> Optional[Callable[..., None]]:
        method = self.method
        if method is None:
            return None
        if (func := getattr(method, '__func__', None)) is not None:
            return func
        # if isinstance(method, (staticmethod, classmethod)):
        #     return method.__func__
        return method

    def embed(self, pattern: str) -> Self:
        """Embed route entry inside the pattern."""
        if self.signature is None:
            return self
        sig = self.signature
        pattern = pattern.strip('/')
        old_pat, old_fmt = self.path.pattern, self.path_format
        pre_fmt, _, post_fmt = pattern.partition('{}')
        pre_pat, pre_fmt = Router._parse_explicit_path_args(path=pre_fmt, params=self.params, sig=sig)
        post_pat, post_fmt = Router._parse_explicit_path_args(path=post_fmt, params=self.params, sig=sig)
        self.path_format = f'{pre_fmt}{old_fmt}{post_fmt}'
        self.path = re.compile(f'{pre_pat}{old_pat}{post_pat}')
        return self


@frozen(kw_only=True)
class RouteDef:
    """Info about the route added to the router."""
    #: The router for this entry.
    router: 'Router'
    #: The entry to add.
    route: RouteEntry


@frozen(kw_only=True)
class ClassRouterEntry:
    """Class (sub)router (with class routes). Each RouteObject has dict _ff_routers."""
    #: Main router – like separate namespace.
    main_router: 'Router'
    #: Class (sub)router (with class routes).
    class_router: 'Router'
    #: The class type.
    cls: Type['RouteObject']


@frozen(kw_only=True)
class ParentRouteObject:
    """Reference to parent route-object, used in sub-object _ff_subobject_parent."""
    #: Parent class with its router.
    parent: 'RouteObject'
    #: Sub-object route, points sub-object in the parent.
    route: RouteEntry
    #: Extra sub-object kwargs, used only with @subobject_route.
    params: Dict[str, Any] = field(factory=dict)


@frozen(kw_only=True)
class ChildRouteObject:
    """All sub-object instances, _ff_subobject_children cache handled by subobject() decorator."""
    #: Sub-object instance.
    child: 'RouteObject'
    #: Sub-object route.
    route: RouteEntry


class RouteObject:
    """Routing-object (class with @route methods)."""

    #: All routers by main router (_ATTR_CLASS_ROUTERS).
    _ff_routers: ClassVar[Dict['Router', ClassRouterEntry]]
    #: All routers by main router (_ATTR_TARGET_ROUTE_DEFS).
    _ff_route_defs: ClassVar[List[RouteDef]]
    #: Parent route-object (_SUBOBJECT_PARENT).
    _ff_subobject_parent: Optional[ParentRouteObject]
    #: Children route-object (_SUBOBJECT_CHILDREN).
    _ff_subobject_children: Dict['RouteObject', ChildRouteObject]
    #: Children route-object (_SUBOBJECT_CHILDREN_BY_NAME).
    _ff_subobject_children_by_name: Dict[str, ChildRouteObject]

    def __init_subclass__(cls, **kwargs):
        # print(f'RouteObject.__init_subclass__({cls=}, {kwargs=})')
        super().__init_subclass__(**kwargs)
        if cls.__module__ == __name__ and cls.__qualname__ == 'MainRouteObject':
            return
        routers: Dict[Router, ClassRouterEntry] = {}
        cls_route_defs: List[RouteDef] = []
        setattr(cls, _ATTR_CLASS_ROUTERS, routers)
        setattr(cls, _ATTR_TARGET_ROUTE_DEFS, cls_route_defs)
        cls_dir: Sequence[str]  # dir(cls) with order kept
        try:
            cls_dir_temp = {}
            for kls in reversed(cls.__mro__):
                if hasattr(kls, '__dict__'):
                    cls_dir_temp.update(kls.__dict__)
                elif hasattr(kls, '__slots__'):
                    cls_dir_temp.update((n, None) for n in kls.__slots__)
                else:
                    raise ModuleNotFoundError()  # failed, fallback to dir(cls)
            cls_dir = tuple(cls_dir_temp)
            del cls_dir_temp
        except ModuleNotFoundError:
            cls_dir = dir(cls)
        cls_names = set(cls_dir)
        for key in cls_dir:
            if not key.startswith('_'):
                val = unwrap(getattr(cls, key))
                defs: Sequence[RouteDef] = getattr(val, _ATTR_TARGET_ROUTE_DEFS, ())
                main_router: 'Router' = ...
                for rdef in defs:
                    main_router = rdef.router
                    route = rdef.route
                    cls_entry = cls._ff_get_cls_router(main_router)
                    # Remove from global routes and append to class routes.
                    try:
                        main_router.routes.remove(route)
                    except ValueError:
                        # route in base class, make copy for class cls
                        route = copy(route)  # route.params are reference not copy – it's OK
                    cls_entry.class_router.routes.append(route)
                    # Now we know the class.
                    route.cls = cls
                    # Hack. Add dynamic created function to the class as method.
                    if route.method and route.method.__name__ not in cls_names:
                        setattr(cls, route.method.__name__, route.method)
                # Auto-property for sub-classes (works only with single main_router)
                if defs and isclass(val) and issubclass(val, RouteObject):
                    prop = camel_to_snake(key)
                    # prop = camel_to_snake(val.__name__)
                    if not hasattr(cls, prop):
                        def get_getter(cls):
                            def _ff_get_subobject(self):
                                return cls()
                            return _ff_get_subobject
                        # typing hacks: main_router exists, _router= is hidden in subobject
                        for rdef in defs:
                            if rdef.router == main_router:
                                setattr(cls, prop, subobject(prop, name=prop, _router=main_router, _route=rdef.route)(get_getter(val)))  # type: ignore  # (hacks)
                                break
                        else:
                            setattr(cls, prop, subobject(prop, name=prop, _router=main_router)(get_getter(val)))  # type: ignore  # (hacks)

    @classmethod
    def _ff_get_cls_router(cls, main_router: 'Router') -> ClassRouterEntry:
        routers = cls._ff_routers
        try:
            cls_entry = routers[main_router]
        except KeyError:
            router_name = f'{cls.__module__}.{cls.__qualname__}'
            class_router = Router(name=router_name, main_router=main_router)
            cls_entry = ClassRouterEntry(main_router=main_router, class_router=class_router, cls=cls)
            class_router.class_entry = cls_entry
            routers[main_router] = cls_entry
        return cls_entry

    @classmethod
    def _ff_add_class_route(cls, *, path: str, main_router: 'Router') -> None:
        """Add class route to the main router (for each main router used)."""
        cls_entry = cls._ff_routers.get(main_router)
        if cls_entry is None:
            cls_entry = cls._ff_get_cls_router(main_router)
        path = path.strip('/')
        if '{}' not in path:
            path = f'{path}/{{}}' if path else '{}'
        pat = re.compile(path.replace('{}', Router._SUB_PATTERN))
        # Append class routers to main router (as sub-object).
        route = RouteEntry(path=pat, subrouter=cls_entry.class_router, path_format=path)
        main_router.routes.append(route)
        main_router.add_route_def(cls, route)

    def __new__(cls, *args, **kwargs) -> Self:
        obj = super().__new__(cls)
        obj._ff_subobject_parent = None  # _SUBOBJECT_PARENT
        obj._ff_subobject_children = {}  # _SUBOBJECT_CHILDREN
        obj._ff_subobject_children_by_name = {}  # _SUBOBJECT_CHILDREN_BY_NAME
        return obj


class MainRouteObject(RouteObject):
    """Routing-object (class with @route methods) bound to '/'."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Append class routers to main routers (as sub-object).
        pat = re.compile(Router._SUB_PATTERN)
        for main_router, cls_entry in cls._ff_routers.items():
            route = RouteEntry(path=pat, subrouter=cls_entry.class_router, path_format='{}')
            main_router.routes.append(route)
            # main_router.add_route_def(cls, route)


@frozen(kw_only=True)
class EndpointInfo:
    """Base info about endpoint (url and method)."""
    #: Endpoint URL
    url: URL
    #: Method to call.
    method: Callable[..., Any]
    #: Method parameters (keyword arguments).
    params: Params
    #: Main router to call.
    main_router: 'Router'


@frozen
class RouteCall:
    """Call method data (for routing)."""
    route: RouteEntry
    method: Callable[..., None]
    kwargs: KwArgs = field(factory=dict)
    instance: Optional[object] = None
    #: Subobject parital URL (not parsed).
    partial: Optional[str] = None

    def bind(self) -> Callable[..., None]:
        # if ismethod(self.method) or self.instance is None or (self.route.method_class and not self.route.method_class.is_method):
        if ismethod(self.method) or self.instance is None or isinstance(self.method, staticmethod):
            return self.method
        else:
            return MethodType(self.method, self.instance)


class RouteDecoratorProtocol(Protocol):
    @overload
    def __call__(self, func: Callable[P, None], /) -> Callable[P, None]: ...
    @overload
    def __call__(self, cls: Type[SUB], /) -> Type[SUB]: ...


class SubjectDecoratorProtocol(Protocol):
    @overload
    def __call__(self, func: Callable[[PARENT], SUB], /) -> 'subobject[PARENT, SUB]': ...
    @overload
    def __call__(self, subobject: 'subobject[PARENT, SUB]', /) -> 'subobject[PARENT, SUB]': ...


class Router:
    """
    URL router to manage methods and paths.

    >>> @entry(path='/Foo/{a}/{b}')
    >>> def foo(a, /, b: int, c=1, *, d: int, e=2):
    >>>     print(f'foo(a={a!r}, b={b!r}, c={c!r}, d={d!r}, e={e!r})')
    >>>
    >>> def bar(a: PathArg, /, b: PathArg[int], c=1, *, d: int, e=2):
    >>>     print(f'bar(a={a!r}, b={b!r}, c={c!r}, d={d!r}, e={e!r})')
    >>>
    >>> rt = Router('plugin://this')
    >>> rt.url_for(foo, 11, 12, 13, d=14)  # plugin://this/Foo/11/12?c=13&d=14
    >>> rt.url_for(bar, 11, 12, 13, d=14)  # plugin://this/bar/11/12?c=13&d=14
    >>>
    >>> rt.dispatch('plugin://this/Foo/11/12?c=13&d=14')  # foo(a='11', b=12, c='13', d=14, e=2)
    >>> rt.dispatch('plugin://this/bar/11/12?c=13&d=14')  # bar(a='11', b=12, c='13', d=14, e=2)
    """

    SAFE_CALL = False

    #: Regex for parse argument on the path: "/aa/{param}/cc".
    _RE_PATH_ARG = re.compile(r'(?P<pre>[-/.,:;])?\{(?P<opt>__)?(?P<name>[a-zA-Z]\w*)\}|(?P<subobj>\{\})')
    # _RE_PATH_ARG = re.compile(r'(?P<pre>[-/.,:;])?\{(?P<opt>__)?(?P<name>[a-zA-Z]\w*)\}')
    #: Pattern (not compiled) for replacing '{}' in the path.
    _SUB_PATTERN = r'(?P<_>.*)'
    #: Pattern (not compiled) for replacing '/{}' at the end of the path (note '/' in replace).
    _SUB_PATTERN_END = r'(?:/(?P<_>.*))?$'

    def __init__(self, url: Optional[Union[URL, str]] = None, obj: Optional[object] = None, *,
                 standalone: Optional[bool] = True, main_router: Optional['Router'] = None,
                 name: Optional[str] = None,
                 # addon: Optional['Addon'] = None,
                 ) -> None:
        if main_router is None:
            url = URL('plugin://plugin.video.fanfilm/') if url is None else URL(url)
        elif url is not None:
            logger.fflog.error(f'Sub-router {main_router}.Router({name=}) can NOT has own url ({url})')
            url = None
        #: Base URL of routing (plugin).
        self._url: Optional[URL] = url
        #: Root object to find subobjects / subroutes.
        self.obj: Optional[object] = obj
        #: Routes for decorators.
        self.routes: List[RouteEntry] = []
        #: Custom name.
        self.name: Optional[str] = name
        #: Main router
        self.main_router: Router = self if main_router is None else main_router
        #: Class entry for class router.
        self.class_entry: Optional[ClassRouterEntry] = None

        if standalone is False:
            self.routes = _main_router.routes  # link to routes (it's NOT a copy)

    def __repr__(self) -> str:
        x = id(self)
        return f'<Router {0xffff_ffff & (x ^ (x >> 32)):08x}: {self.name or ""}>'

    @property
    def url(self) -> URL:
        """Return main router URL."""
        if self._url is None:
            assert self.main_router is not self
            assert self.main_router._url is not None
            return self.main_router._url
        return self._url

    @url.setter
    def url(self, url: Union[URL, str]) -> None:
        if self.main_router is not self:
            raise AttributeError(f'Sub-router {self.main_router}.{self} can NOT has own url ({url})')
        self._url = URL('plugin://plugin.video.fanfilm/') if url is None else URL(url)

    def set_default_route_object(self, obj: object) -> None:
        """Set obj for subrounting."""
        self.obj = obj

    @overload  # @route  # (function)
    def route(self, func: Callable[P, None], /) -> Callable[P, None]: ...

    @overload  # @route(path, ...)  # (function and class)
    def route(self, path: str, /) -> RouteDecoratorProtocol:  ...

    @overload  # @route  # (class)
    def route(self, cls: Type[SUB], /) -> Type[SUB]: ...

    def route(self,
              func_or_cls_or_path,
              /, *,
              _type: RouteType = RouteType.UNKNOWN,
              ) -> Any:
        """
        @route decorator

        Use as simple endpoint entry decorator, with function name.
        >>> @route
        >>> def foo(a: PathArg[int], b: int) -> None: ...
        >>>
        >>> dispatch(URL('/foo/1?b=2'))
        >>> # foo(1, 2)

        Or decorator with arguemnts.
        >>> @route('/foo')
        >>> def bar(a: PathArg[int], b: int) -> None: ...
        >>>
        >>> @route('/foo/{a}')
        >>> def baz(a: int, b: int) -> None: ...
        >>>
        >>> dispatch(URL('/bar?a=1&b=2'))   #  bar(1, 2)
        >>> dispatch(URL('/bar/1?b=2'))     #  baz(1, 2)

        Could be used with subobject property.
        >>> class Root(MainRouteObject):
        >>>     @subobject
        >>>     def foo(self) -> 'Foo':
        >>>         return Foo(42)
        >>>
        >>> class Foo(RouteObject):
        >>>    def __init__(self, num: int) -> None:
        >>>        self.num = num
        >>>   @route
        >>>   def bar(self, PathArg[int], b: int) -> None: ...
        >>>
        >>> dispatch(URL('/foo/bar/1?b=2'))
        >>> # Foo(42).foo(1, 2)
        """

        def prepare_func(func: Callable[P, None]) -> Tuple[str, Callable[P, None], Callable[P, None]]:
            """Return (path, method_to_call, func_to_add_route)."""
            fn: Callable[P, None] = unwrap(func)
            fn_path: Optional[str] = path
            if fn_path is None:
                fn_path = fn.__name__
            if callable(fn):
                return fn_path, func, fn
            raise TypeError(f'Unsupported callable {func!r}')

        @overload
        def wrapper(func_or_cls: Callable[P, None]) -> Callable[P, None]: ...

        @overload
        def wrapper(func_or_cls: Type[SUB]) -> Type[SUB]: ...

        def wrapper(func_or_cls: Union[Callable[P, None], Type[SUB]]) -> Union[Callable[P, None], Type[SUB]]:
            if isclass(func_or_cls):
                klass = func_or_cls
                if not issubclass(klass, RouteObject):
                    raise TypeError(f'route() expected RouteObject class, got {func_or_cls.__name__}')
                if TYPE_CHECKING:
                    # only for type checking
                    def is_route_object_type(t) -> TypeGuard[Type[SUB]]:
                        return issubclass(t, RouteObject)
                    if not is_route_object_type(klass):
                        raise TypeError()
                klass._ff_add_class_route(path=camel_to_snake(klass.__name__) if path is None else path, main_router=self)
                return klass

            func: Callable[P, None] = func_or_cls
            fn_path, method, route_container = prepare_func(func)
            route = self.add_route(path=fn_path, method=method)
            route.route_type = _type
            self.add_route_def(route_container, route)
            return func

        if isclass(func_or_cls_or_path):
            path = None
            return wrapper(func_or_cls_or_path)

        if func_or_cls_or_path is not None and not isinstance(func_or_cls_or_path, str):
            path = None
            return wrapper(func_or_cls_or_path)

        path = cast(str, func_or_cls_or_path)
        return wrapper

    def function_route(self, *, path: Optional[str], method: Callable[P, None], signature: Optional[Signature] = None) -> RouteEntry:
        """Define and add route. Hepler for custom decorators."""
        if path is None:
            path = method.__name__
        func = unwrap(method)
        route = self.add_route(path=path, method=method, signature=signature)
        self.add_route_def(func, route)
        return route

    @overload  # @route  # (function)
    def subobject_route(self, func: Callable[P, SUB], /) -> Callable[P, SUB]: ...

    @overload  # @route(path, ...)  # (function and class)
    def subobject_route(self, path: str, /) -> Callable[[Callable[P, SUB]], Callable[P, SUB]]:  ...

    def subobject_route(self,
                        func_or_path,
                        /,
                        ) -> Any:
        """
        @subobject_route decorator - get subocject by route method (with args).

        It decorate method, it do NOT create subobject descriptor.

        >>> class Root(MainRouteObject):
        >>>     @subobject_route('/foo/{a}')
        >>>     def foo(self, a: int) -> 'Foo':
        >>>         return Foo(a)
        >>>
        >>> class Foo(RouteObject):
        >>>     def __init__(self, num: int) -> None:
        >>>         self.num = num
        >>>
        >>>    @route('/bar/{b}')
        >>>    def bar(self, b: int) -> None: ...
        >>>
        >>> dispatch(URL('/foo/1/bar/2'))  # Foo(1).foo(2)
        >>> url_for(Foo(3).bar, b=4)       # /foo/3/bar/4  - NOT SUPPORTED YET
        """
        # return self.route(func_or_path, _type=RouteType.OBJECT_GET)  # type: ignore[reportCallIssue]  # (_type is hidden)

        def prepare_func(func: Callable[P, SUB]) -> Tuple[str, Callable[P, SUB], Callable[P, SUB]]:
            """Return (path, method_to_call, func_to_add_route)."""
            fn: Callable[P, SUB] = unwrap(func)
            fn_path: Optional[str] = path
            if fn_path is None:
                fn_path = fn.__name__
            if callable(fn):
                return fn_path, func, fn
            raise TypeError(f'Unsupported callable {func!r}')

        def wrapper(func: Callable[P, SUB]) -> Callable[P, SUB]:
            @wraps(func)
            def wrapped(self: RouteObject, *args: P.args, **kwargs: P.kwargs) -> SUB:
                obj: SUB = func(self, *args, **kwargs)
                if args:
                    logger.fflog.warning(f'Positional arguemnts are NOT supported in @subobject_route in {func}')
                    # raise TypeError(f'Positional arguemnts are NOT supported in @subobject_route in {func}')
                    # -- experimental support for positional arguemnts --
                    sig = _signature(func) if route.signature is None else route.signature
                    sig_params = iter(sig.parameters.values())
                    if next(sig_params).name not in ('self', 'cls'):
                        raise TypeError(f'First positional arguemnt of {func} is not self or cls')
                    for a, p in zip(args, sig_params):
                        if p.kind is p.POSITIONAL_ONLY or p.kind is p.POSITIONAL_OR_KEYWORD:
                            kwargs[p.name] = a
                obj._ff_subobject_parent = ParentRouteObject(parent=self, route=route, params=kwargs)
                return obj

            fn_path, method, route_container = prepare_func(wrapped)
            route = self.add_route(path=fn_path, method=cast(Callable[P, None], method))
            route.route_type = RouteType.OBJECT_GET
            self.add_route_def(route_container, route)
            return method

        if func_or_path is not None and not isinstance(func_or_path, str):
            path = None
            return wrapper(func_or_path)

        path = cast(str, func_or_path)
        return wrapper

    @overload  # @subobject  # (function)
    def subobject(self, func: Callable[[PARENT], SUB], /) -> 'subobject[PARENT, SUB]': ...

    @overload  # @subobject  # (function)
    def subobject(self, subobject: 'subobject[PARENT, SUB]', /) -> 'subobject[PARENT, SUB]': ...

    @overload  # @subobject()  # (function)
    def subobject(self, /) -> 'Callable[[Callable[[PARENT], SUB] | subobject[PARENT, SUB]], subobject[PARENT, SUB]]':  ...
    # def subobject(self, /) -> Callable[[Callable[[PARENT], SUB]], 'subobject[PARENT, SUB]']:  ...

    @overload  # @subobject(path)  # (function)
    def subobject(self, path: str, /) -> SubjectDecoratorProtocol:  ...
    # def subobject(self, path: str, /) -> 'Callable[[Callable[P, SUB]], subobject[RouteObject, SUB]]':  ...

    # @overload  # @subobject  # (class)
    # def subobject(self, cls: Type[CLS], /) -> Type[CLS]: ...

    @overload  # prop = subobject(func)
    def subobject(self, func: Callable[[PARENT], SUB], path: str, /, *, name: Optional[str] = None): ...

    def subobject(self,
                  method_or_cls_or_path: 'Union[Type[CLS], Callable[[PARENT], SUB], subobject[PARENT, SUB] , str, None]' = None,
                  descr_path: Optional[str] = None,
                  /, *,
                  name: Optional[str] = None,
                  ) -> Any:
        """
        Subobject descriptor / porperty or decorator, used for subrouting.

        >>>
        """
        return subobject(method_or_cls_or_path, descr_path, name=name, _router=self)  # type: ignore[reportCallIssue]  # (_router is hidden)

    @classmethod
    def _arg_pat(cls, ann: TypeForm[Any], *, path: Optional[str] = None, method: Any = None) -> Tuple[Sequence[TypeForm[Any]], str, AnnMeta]:
        def type_pattern(typ: TypeForm[Any]):
            nonlocal the_meta
            # otype = get_origin(typ)
            typ, meta = ann_type(typ)
            if meta and isinstance(meta[0], re.Pattern):
                at = ArgDescr(typ, f'(?:{meta[0].pattern})')
                yield at.pat(typ, meta)
            else:
                at, meta = find_arg_descr(typ, meta=meta, annotations=ANN_TYPES)
                if at:
                    the_meta = (*the_meta, *meta)
                    yield at.pat(typ, the_meta)
                # elif otype is not Annotated or (at := ANN_TYPES.get(subtyp)) is None:
                else:
                    logger.error(f'Unsported argument type: typ={typ!r}')

        ann, the_meta = ann_type(ann)
        ann = remove_optional(ann)
        otype = get_origin(ann)
        if otype is Union:
            types = get_args(ann)
        else:
            types = (ann,)

        try:
            patterns = [pat for typ in types for pat in type_pattern(typ)]
        except ValueError:
            logger.fflog_exc()
            path = path or ''
            method = method or ''
            logger.fflog(f'ERRROR: can NOT create route for {path=}, {method=}, wrong {ann=}')
            return (), '--no-arg-pattern--', ()
        if len(patterns) == 1:
            at_pat = patterns[0]
        else:
            at_pat = '|'.join(f'(?:{p})' for p in patterns)
        return types, at_pat, the_meta

    @classmethod
    def _parse_explicit_path_args(cls, *, path: str, params: Dict[str, EntryParam], sig: Signature) -> Tuple[str, str]:
        def mkarg(m: Match[str]):
            nonlocal path_format, path_index
            if m['subobj']:
                path_format = f'{path_format}{m.string[path_index:m.start()]}{{}}'
                path_index = m.end()
                return '{}'
            pre = m['pre'] or ''
            val_pre, val_post = pre, ''
            opt = m['opt'] or ''
            name = m['name']
            value_format = f'{val_pre}{{}}' if val_pre else None  # only for optional
            start = m.start()
            try:
                par = sig.parameters[name]
            except KeyError:
                from .log_utils import fflog
                fflog.error(f'Missing parameter {name!r} in signature {sig} for path {path!r}')
                raise
            ann = remove_optional(par.annotation)
            subtype, meta = ann_type(ann)
            for mt in meta:
                if isinstance(mt, ArgFormat):
                    value_format = str(mt)
                    ann = subtype
                    start += len(pre)
                    fb, _, fe = value_format.partition('{}')
                    val_pre = re.escape(fb)
                    val_post = re.escape(fe)
                    break
            else:
                pre = ''
            path_format = f'{path_format}{m.string[path_index:start]}{{{opt}{name}}}'
            path_index = m.end()
            types, at_pat, meta = cls._arg_pat(ann)
            if name.isdigit():
                # positional arguments – partially supported – DO NO USE them
                params[int(name)] = entry = EntryParam(name, types, explicit=True, value_format=value_format, meta=meta)
                name = f'_{name}'
            else:
                params[name] = entry = EntryParam(name, types, optional=bool(opt), explicit=True, value_format=value_format, meta=meta)
            if par.default is not par.empty:
                entry.default = par.default
            if opt:
                return fr'{pre}(?:{val_pre}(?P<{name}>{at_pat}){val_post})?'
            return fr'{pre}{val_pre}(?P<{name}>{at_pat}){val_post}'

        def transform(path: str) -> Iterator[str]:
            index = 0
            for mch in cls._RE_PATH_ARG.finditer(path):
                yield re.escape(path[index:mch.start()])
                yield mkarg(mch)
                index = mch.end()
            yield re.escape(path[index:])

        path_format, path_index = '', 0
        # pattern = cls._RE_PATH_ARG.sub(mkarg, path)
        pattern = ''.join(transform(path))
        path_format = f'{path_format}{path[path_index:]}'
        return pattern, path_format

    def new_route(self, path: str, *, method: Callable, cls: Optional[Type] = None, signature: Optional[Signature] = None, **kwargs) -> RouteEntry:
        """Add route (ex. from @route)."""

        def add_path_args(pat: str, sig: Signature) -> str:
            nonlocal path_format
            for p in sig.parameters.values():
                ht = remove_optional(p.annotation)
                if ht is not p.empty:
                    typ, meta = ann_type(ht, _PathArg)
                    if meta:
                        types, at_pat, meta = self._arg_pat(typ)
                        if types:
                            if pat == '/':
                                pat = ''
                            if path_format == '/':
                                path_format = ''
                            params[p.name] = ep = EntryParam(p.name, tuple(types), meta=meta)
                            if p.default is not p.empty:
                                ep.default = p.default
                            sep = pat and '/'
                            if is_optional(p.annotation) or p.default is not p.empty:
                                ep.optional = True
                                pat = f'{pat}(?:{sep}(?P<{p.name}>{at_pat}))?'
                                path_format = f'{path_format}{{__{p.name}}}'
                            else:
                                pat = f'{pat}{sep}(?P<{p.name}>{at_pat})'
                                path_format = f'{path_format}/{{{p.name}}}'
                            path_format = path_format.strip('/')
            return pat

        def add_sig_args(sig: Signature) -> None:
            for i, p in enumerate(sig.parameters.values()):
                if not i and p.name in ('self', 'cls'):
                    continue
                if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY) and p.name not in params:
                    ht = remove_optional(p.annotation)
                    typ, meta = ann_type(ht, _PathArg)
                    if typ is None:
                        typ = str
                    opt = is_optional(p.annotation) or p.default is not p.empty
                    params[p.name] = ep = EntryParam(p.name, (typ,), optional=opt, path_arg=False, meta=meta)
                    if p.default is not p.empty:
                        ep.default = p.default

        assert path is not None
        func = unwrap(method)
        sig = _signature(func) if signature is None else signature
        path = path.strip('/')  # remove leading and tailing slashes
        path = getattr(path, 'path', path)  # EndpointEntry - duck typing (libka)
        params: Dict[str, EntryParam] = {}

        # path_format, path_index = '', 0
        # pattern = self._RE_PATH_ARG.sub(mkarg, path)
        # path_format = f'{path_format}{path[path_index:]}'
        pattern, path_format = self._parse_explicit_path_args(path=path, params=params, sig=sig)

        pattern = add_path_args(pattern, sig)
        add_sig_args(sig)
        if pattern.endswith('/{}'):  # special case: '/foo/{}' should be dispatched by '/foo' too (without last /).
            pattern = f'{pattern[:-3]}{self._SUB_PATTERN_END}'
        else:
            pattern = pattern.replace('{}', self._SUB_PATTERN)
        route = RouteEntry(path=re.compile(pattern), method=method, params=params, path_format=path_format, signature=sig, **kwargs)
        return route

    @overload
    def add_route(self, path: str, *, method: Callable[..., None], signature: Optional[Signature] = None, label: str = '') -> RouteEntry: ...

    @overload
    def add_route(self, path: str, *, router: Union['Router', RouteObject], label: str = '') -> RouteEntry: ...

    def add_route(self,
                  path: str,
                  *,
                  router: Optional[Union['Router', RouteObject]] = None,  # sub-router
                  method: Optional[Callable[..., None]] = None,
                  signature: Optional[Signature] = None,
                  label: str = '',
                  ) -> RouteEntry:
        """Add route (ex. from @entry)."""
        if method is not None:
            route = self.new_route(path, method=method, signature=signature, label=label)
        elif router is not None:
            if not isinstance(router, Router):
                router = router._ff_routers[self.main_router].class_router
            path = path.strip('/')
            if '{}' not in path:
                path = f'{path}/{{}}' if path else '{}'
            if path.endswith('/{}'):  # special case: '/foo/{}' should be dispatched by '/foo' too (without last /).
                pattern = f'{path[:-3]}{self._SUB_PATTERN_END}'
            else:
                pattern = path.replace('{}', self._SUB_PATTERN)
            route = RouteEntry(path=re.compile(pattern), subrouter=router, label=label, path_format=path)
        else:
            raise TypeError('Nothing to add in add_route, use `method` or `router`')
        self.routes.append(route)
        return route

    def add_route_def(self, target: object, route: RouteEntry) -> None:
        """Add route definition."""
        defs: List[RouteDef] = getattr(target, _ATTR_TARGET_ROUTE_DEFS, [])
        if defs:
            for rt in defs:
                if rt.route.method is route.method:
                    rt.route.has_variants = True
                    route.has_variants = True
        else:
            setattr(target, _ATTR_TARGET_ROUTE_DEFS, defs)
        defs.append(RouteDef(router=self, route=route))
        # self.routes.append(route)  -- already added by add_route()

    @overload
    def _url_for(self, first: bool, /, **kwargs) -> Optional[URL]: ...

    @overload
    def _url_for(self, first: bool, /, method: Callable[..., Any], **kwargs) -> Optional[URL]: ...

    @overload
    def _url_for(self, first: bool, /, target: RouteObject, **kwargs) -> Optional[URL]: ...

    def _url_for(self, _first: bool, /, *args, **kwargs) -> Optional[URL]:
        """
        Determinate URL for given method or None.

        url_for(method, **params)
        url_for(**params)
        """

        def dump_value(val: Any, types: Sequence[Any], *, meta: AnnMeta = ()) -> str:
            for typ in types:
                at, mt = find_arg_descr(typ, meta=meta, annotations=ANN_TYPES)
                if at:
                    return at.dump(val, typ, mt)
            return ANN_TYPES[Any].dump(val, Any)

        def arg_iter(route: RouteEntry, kwargs: Params) -> Iterator[Tuple[str, str]]:
            default_allowed = True
            # scan from the end, to detect optional path arguments
            for param in reversed(route.params.values()):
                val = kwargs.get(param.name, param.default)
                if is_default := default_allowed and (val == param.default):
                    # default path argument could be skipped (if is not explicit of course)
                    yield f'__{param.name}', ''  # __NAME is used for PathArg, it's not explicit
                elif param.path_arg:
                    # non-default path argument is used, all path arguments before must be added (remember about reversed)
                    default_allowed = False
                val = dump_value(val, param.types, meta=param.meta)
                if not is_default:
                    if param.optional and param.explicit:
                        yield f'__{param.name}', param.format(val)
                    else:
                        if param.value_format is None:
                            yield f'__{param.name}', f'/{val}'
                        else:
                            yield f'__{param.name}', param.value_format.format(val)
                # explicit argument, used in @route('{NAME}'}
                if param.value_format is None:
                    yield param.name, val
                else:
                    yield param.name, param.value_format.format(val)

        def make_url(route: RouteEntry) -> Optional[URL]:
            # those args are obligated
            needed = {p.name for i, p in enumerate(route.params.values())
                      if not p.optional and p.default is MISSING and (i or p.name not in ('self', 'cls'))}
            # if not all necessery arguments are present
            if not (needed - kwargs.keys()):
                # fill path with path-arguments
                path = route.path_format.format(**dict(arg_iter(route, kwargs)))
                # find forbidden args in query
                forbidden = {p.name for p in route.params.values() if p.path_arg}
                forbidden.update(('self', 'cls'))
                # build query
                q_params = {k: dump_value(v, (type(v),) if p is None else p.types)
                            for k, v in kwargs.items()
                            if k not in forbidden and ((p := route.params.get(k)) is None or p.default != v)}
                query = encode_params(q_params)
                # build url
                return URL(self.url.scheme, self.url.hostname, path, query)
            # Missing same arguments.
            return None

        def best_method_variant(func: Callable, routes: List[RouteEntry], start: int) -> Optional[URL]:
            def order(rt: RouteEntry) -> int:
                return sum(1 if kwargs.get(k, p.default) == p.default else -9 for k, p in rt.params.items() if p.path_arg)
            for route in sorted((rt for i in range(start, len(routes)) if (rt := routes[i]).func == func), key=order):
                url = make_url(route)
                if url is not None:
                    return url
                return None

        def find_method(method: Callable, routes: List[RouteEntry]) -> Optional[URL]:
            if ismethod(method):
                func = method.__func__
            else:
                func = method
            for i, route in enumerate(routes):
                if route.subrouter:
                    url = route.subrouter._url_for(False, *call_args, **call_kwargs)
                    if url is not None:
                        if not route.path_format:
                            breakpoint()
                        return url.replace(path=route.path_format.format(url.path))
                elif route.func == func:
                    if route.has_variants:
                        url = best_method_variant(func, routes, start=i)
                    else:
                        url = make_url(route)
                    if url is not None:
                        return url

        method: Callable
        call_args, call_kwargs = args, dict(kwargs)
        # if len(args) == 2:
        #     prefix, method = args
        if len(args) == 1:
            method, = args
        elif not args:
            # global name `_ff_route_calling` set by Router.call().
            if _ff_route_calling.method is None:
                raise RuntimeError('for_url() without method called outside @route')
            method = _ff_route_calling.method
            kwargs = {**_ff_route_calling.kwargs, **kwargs}
        else:
            raise TypeError(f'for_url() accepts max two positional arguments, got {len(args)}')

        # find in regular (ex. global) routes (endpoints)
        if callable(method):
            if url := find_method(method, self.routes):
                return url
            # seatch fir base clases
            if self.class_entry and self.class_entry.cls:
                for cls in self.class_entry.cls.__mro__:
                    if issubclass(cls, RouteObject):
                        if (cls_entry := getattr(cls, _ATTR_CLASS_ROUTERS, {}).get(self.main_router)) and cls_entry.class_router is not self:
                            if url := find_method(method, self.routes):
                                return url

        def get_subobject_path(instance: RouteObject, path: str = '') -> str:
            parent: Optional[ParentRouteObject]
            while (parent := getattr(instance, _SUBOBJECT_PARENT, None)) is not None:
                path = parent.route.path_format.format(path, **{k: p.format(v) for k, v in parent.params.items() if (p := parent.route.params[k])})
                instance = parent.parent
            return path

        if isinstance(method, RouteObject):
            path = get_subobject_path(method)
            return URL(self.url.scheme, self.url.hostname, path, '')

        instance: Optional[RouteObject] = None
        obj_type: Optional[Type[RouteObject]] = None
        function: Optional[Callable[..., None]] = None
        if callable(method):  # method, function or something
            if ismethod(method):  # method or classmethod
                if isclass(instance := method.__self__):
                    # classmethod
                    obj_type = instance
                    # kwargs.setdefault('cls', instance)
                    function = method.__func__
                else:
                    # regular method
                    obj_type = cast(Type[RouteObject], type(instance))
                    # kwargs.setdefault('self', instance)
                    function = method.__func__
            else:
                function = cast(Callable[..., None], method)
                ...
        else:
            breakpoint()
            ...

        # find URL in target method class, called on first _url_for only
        if _first:
            if obj_type is not None and instance is not None:
                # method.__self__.__class__._ff_routers[self].class_router._url_for(method, a=44)
                class_entry: Optional[ClassRouterEntry] = getattr(obj_type, _ATTR_CLASS_ROUTERS, {}).get(self.main_router)
                if class_entry and class_entry.class_router is not self:
                    if url := class_entry.class_router._url_for(False, method, **kwargs):
                        path = get_subobject_path(instance, url.path)
                        return url.replace(path=path)

            # subobject on class (not on instance)
            if isinstance(method, subobject):
                if method.route is not None:
                    class_entry: Optional[ClassRouterEntry] = getattr(method.route.cls, _ATTR_CLASS_ROUTERS, {}).get(self.main_router)
                    if (class_entry is None
                            or (class_entry.class_router is not self
                                and (class_entry.cls is None or not issubclass(class_entry.cls, MainRouteObject)))):
                        logger.fflog.warning(f'Unspecified subobject class mount point, url_for({method.method}) can return incorrect URL')
                    path = method.route.path_format.format('').rstrip('/')
                    return URL(self.url.scheme, self.url.hostname, path)

        if 0 and function is not None and (defs := getattr(function, _ATTR_TARGET_ROUTE_DEFS, None)):
            for d in defs:
                if d.route.method == function:
                    # if d.route.has_variants:
                    #     url = best_method_variant(func, routes, start=i)
                    # else:
                    url = make_url(d.route)
                    if url is not None:
                        return url
        return None

    @overload
    def url_for(self, **kwargs) -> Optional[URL]: ...

    @overload
    def url_for(self, method: Callable[..., Any], **kwargs) -> Optional[URL]: ...

    # @overload
    # def url_for(self, prefix: str, method: Callable[..., Any], **kwargs) -> Optional[URL]: ...

    @overload
    def url_for(self, target: RouteObject, **kwargs) -> Optional[URL]: ...

    def url_for(self, *args, **kwargs) -> Optional[URL]:
        """
        Determinate URL for given method or None.

        >>> url_for(method, **params)
        >>> url_for(**params)            # avaliable only from called endpoint
        """
        url = self._url_for(True, *args, **kwargs)
        if url is None:
            return None
        path = url.path.strip('/')
        return url.replace(path=f'/{path}')

    @overload
    def info_for(self, **kwargs) -> Optional[EndpointInfo]: ...

    @overload
    def info_for(self, method: Callable[..., Any], **kwargs) -> Optional[EndpointInfo]: ...

    @overload
    def info_for(self, target: RouteObject, **kwargs) -> Optional[EndpointInfo]: ...

    def info_for(self, *args, **kwargs) -> Optional[EndpointInfo]:
        """
        Determinate endpoint (with URL) for given method or None.

        >>> info_for(method, **params)
        >>> info_for(**params)            # avaliable only from called endpoint
        """
        url = self.url_for(*args, **kwargs)
        if url is None:
            return None
        if len(args) == 1:
            method, = args
        else:  # no args, checked in _url_for()
            assert not args
            assert _ff_route_calling.method is not None
            method = _ff_route_calling.method
            kwargs = {**_ff_route_calling.kwargs, **kwargs}
        return EndpointInfo(url=url, method=method, params=kwargs, main_router=self.main_router)

    def find_func_route(self, func: Callable[..., None]) -> Optional[RouteEntry]:
        """Return route matched to method for function definitions. [HELPER]"""
        method = unwrap(func)
        defs: Sequence[RouteDef] = getattr(func, _ATTR_TARGET_ROUTE_DEFS, ())
        for rdef in defs:
            if rdef.router is self.main_router and rdef.route.method == method:
                return rdef.route
        return None

    @overload
    def route_redirect(self, **kwargs) -> Optional[URL]: ...

    @overload
    def route_redirect(self, method: Callable, **kwargs) -> Optional[URL]: ...

    # @overload
    # def route_redirect(self, url: str) -> Optional[URL]: ...

    def route_redirect(self, *args, **kwargs) -> Optional[URL]:
        """
        Mark current route as method or URL. Useful for for_url().

        route_redirect(method, **params)
        route_redirect(**params)
        """
        method: Callable
        if len(args) == 1:
            method, = args
        elif not args:
            # global name `_ff_route_calling` set by Router.call().
            if _ff_route_calling.method is None:
                raise RuntimeError('route_redirect() without method called outside @route')
            method = _ff_route_calling.method
            kwargs = {**_ff_route_calling.kwargs, **kwargs}
        else:
            raise TypeError(f'route_redirect() accepts max two positional arguments, got {len(args)}')
        _ff_route_calling.set(method, kwargs)

    @overload
    def url_proxy(self, **kwargs) -> Optional[URL]: ...

    @overload
    def url_proxy(self, method: Callable[..., Any], **kwargs) -> Optional[URL]: ...

    @overload
    def url_proxy(self, target: RouteObject, **kwargs) -> Optional[URL]: ...

    def url_proxy(self, *args, **kwargs) -> Optional[URL]:
        """
        Like `url_for()` but use current route and put it in `url` arguemnt.

        Target must have `url` arguemnt (type of `Path`).
        """
        if _ff_route_calling.method is None:
            raise RuntimeError('url_proxy() without method called outside @route')
        method: Callable
        if len(args) == 1:
            method, = args
        elif not args:
            method = _ff_route_calling.method
        else:
            raise TypeError(f'url_proxy() accepts max two positional arguments, got {len(args)}')
        # URL for current route method (called method)
        url = url_for(_ff_route_calling.method, **_ff_route_calling.kwargs)
        if url:
            url = url.without_remote()
        # url for proxy
        # kwargs = {**_ff_route_calling.kwargs, **kwargs, 'url': url}
        kwargs = {**kwargs, 'url': url}
        return url_for(method, **kwargs)

    def find_call(self, url: URL, route: RouteEntry, params: Params, *, instance: Optional[object] = None) -> Optional[RouteCall]:
        """Find route method for call."""

        def set_arg(name: str, typ: TypeForm[Any], val: str) -> bool:
            at, meta = find_arg_descr(typ, annotations=ANN_TYPES)
            if at:
                try:
                    kwargs[name] = at.load(val, typ, meta)
                    return True
                except (TypeError, ValueError):
                    pass
            return False

        def proc_arg(p_name: str, p_annotation: TypeForm[T]) -> bool:
            if (val := kwargs.pop(p_name, None)) is not None:
                typ = remove_optional(p_annotation)
                if not set_arg(p_name, typ, val):
                    otype = get_origin(typ)
                    if otype is Union:
                        types = get_args(typ)
                    else:
                        types = (typ,)
                    for typ in types:
                        if set_arg(p_name, typ, val):
                            break  # found arg
                    else:
                        # raise ValueError(f'Can NOT convert argument {val!r} for {method.__qualname__}({p})')
                        logger.fflog.debug(f'Can NOT convert argument {val!r} for {method.__qualname__}({p_name}: {p_annotation})')
                        return False
            return True

        partial = params.pop('_', None)
        # params - argmuent for url args, url.args - url query args
        if route.subobject:
            kwargs = {**params}  # subobject can NOT consume query params, typicaly has no param at all
        else:
            kwargs = {**params, **url.args}
        method = route.method
        if isinstance(method, classmethod):
            method = method.__wrapped__
        if method is None:
            logger.fflog.warning('Missing method to call route {route}')
            return None
        sig = _signature(method) if route.signature is None else route.signature
        # filter-out method missing arguments
        if p_kwargs := next((p for p in sig.parameters.values() if p.kind is p.VAR_KEYWORD), None):
            # has **kwargs
            allowed = None
            o = get_origin(p_kwargs.annotation)
            if (o is Unpack and (a := get_args(p_kwargs.annotation))
                    and isclass(a[0]) and issubclass(a[0], dict) and (ann := get_type_hints(a[0]))):
                # **kwags with type annotation
                for a_name, a_ann in ann.items():
                    if get_origin(a_ann) is NotRequired:
                        a_ann = get_args(a_ann)[0]
                    proc_arg(a_name, a_ann)
        else:
            # no **kwargs
            allowed = {p.name for i, p in enumerate(sig.parameters.values())
                       if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY) and (i or p.name not in ('self', 'cls'))}
        if allowed is not None and kwargs.keys() - allowed:
            wrong = ', '.join(repr(k) for k in kwargs.keys() - allowed)
            logger.fflog.debug(f'method {method.__qualname__}() does not support argument(s): {wrong}')
            kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        # check is all obligatory arguments are present
        obligatory = {p.name for p in sig.parameters.values()
                      if (p.name not in ('self', 'cls') and p.default is p.empty and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY))}
        if obligatory - kwargs.keys():
            return None
        # apply types
        for p in sig.parameters.values():
            if not proc_arg(p.name, p.annotation):
                return None  # can NOT convert argument

        # Function - no instance
        if sig.parameters:
            p = next(iter(sig.parameters.values()))  # the first method argument
            if p.name not in ('self', 'cls'):
                return RouteCall(method=method, kwargs=kwargs, instance=None, route=route, partial=partial)

        if isinstance(instance, (list, tuple)):
            instance_list: Iterable[object] = instance
            for instance in instance_list:
                if route.cls is None or isinstance(instance, route.cls):
                    return RouteCall(method=method, kwargs=kwargs, instance=instance, route=route, partial=partial)
        elif route.cls is None or isinstance(instance, route.cls):
            return RouteCall(method=method, kwargs=kwargs, instance=instance, route=route, partial=partial)
        return None

    def call(self, call: RouteCall) -> Any:
        """Call found route method."""
        method, kwargs, instance = call.method, call.kwargs, call.instance
        func = getattr(method, '__func__', method)
        glob = func.__globals__
        ffunc = '__ff_route_function__'
        old = glob.get(ffunc, MISSING)
        glob[ffunc] = method
        try:
            # if ismethod(method) or instance is None or (route.method_class and not route.method_class.is_method):
            if ismethod(method) or instance is None or isinstance(method, staticmethod):
                _ff_route_calling.set(method, kwargs, route=call.route)
                result = method(**kwargs)
            else:
                _ff_route_calling.set(MethodType(method, instance), kwargs, route=call.route)
                result = method(instance, **kwargs)
        finally:
            _ff_route_calling.clear()
            if old is MISSING:
                del glob[ffunc]
            else:
                glob[ffunc] = old
        return result

    def find_dispatch(self, url: Union[URL, str], *, obj: Optional[object] = None) -> Optional[RouteCall]:
        """Find call for dispatched URL."""

        if isinstance(url, str):
            url = URL(url)
        if '%2C' in url.path:
            url = url.replace(path=url.path.replace('%2C', ','))
        # if '%' in url.path:
        #     url = url.replace(path=unquote_plus(url.path))
        if obj is None:
            obj = self.obj
        path = url.path.strip('/')
        for route in self.routes:
            if mch := route.path.fullmatch(path):
                params = mch.groupdict()
                sub = params.pop('_', '') or ''
                if route.subobject is not None:
                    main_router: Router = route.subobject.router
                    sub_obj = route.subobject.__get__(obj)  # get sub-object from subobject descriptor
                    sub_class_route_entry: Optional[ClassRouterEntry] = getattr(sub_obj, _ATTR_CLASS_ROUTERS, {}).get(main_router)
                    if sub_class_route_entry is None:
                        logger.fflog.error(f'Subobject {sub_obj!r} is not type RouteObject')
                        return None
                    if call := sub_class_route_entry.class_router.find_dispatch(url.replace(path=sub), obj=sub_obj):
                        return call
                elif route.subrouter:
                    if call := route.subrouter.find_dispatch(url.replace(path=sub), obj=obj):
                        return call
                elif call := self.find_call(url, route, params, instance=obj):
                    # @subobject_route
                    if route.route_type is RouteType.OBJECT_GET:
                        sub_obj = self.call(call)
                        if sub_obj is None:
                            logger.fflog.warning(f'Missing subobject for route {route}')
                        else:
                            sub_class_route_entry: Optional[ClassRouterEntry] = getattr(sub_obj, _ATTR_CLASS_ROUTERS, {}).get(self.main_router)
                            if sub_class_route_entry is None:
                                logger.fflog.error(f'Subobject {sub_obj!r} is not type RouteObject')
                                return None
                            if call := sub_class_route_entry.class_router.find_dispatch(url.replace(path=sub), obj=sub_obj):
                                return call
                    # endpoint
                    else:
                        return call

        # --- FAILED !!! ---
        return None

    def dispatch(self, url: Union[URL, str], *,
                 missing: Union[Callable[[URL], None], EllipsisType, None] = None,
                 obj: Optional[object] = None,
                 ) -> bool:
        """Dispatch given URL to registered routes."""
        if call := self.find_dispatch(url, obj=obj):
            self.call(call)
            return True
        if missing is ...:
            return False
        if missing:
            if isinstance(url, str):
                url = URL(url)
            missing(url)
            return True
        else:
            logger.fflog.warning(f'ERROR: Unhandled url {str(url)!r}')
        return False


class subobject(Generic[PARENT, SUB]):
    """
    Subobject descriptor / porperty or decorator, used for subrouting.

    >>>
    """

    @overload  # @subobject  # (class)
    def __init__(self, cls: Type[CLS], /) -> None: ...

    @overload  # @subobject  # (method)
    def __init__(self, func: Callable[[PARENT], SUB], /) -> None: ...

    @overload  # @subobject  # (method)
    def __init__(self, subobject: 'subobject[PARENT, SUB]', /) -> None: ...

    @overload  # @subobject()
    def __init__(self, /) -> None: ...

    @overload  # @subobject(path)
    def __init__(self, path: str, /) -> None: ...

    @overload  # prop = subobject(func, ...)
    def __init__(self, method: Callable[[PARENT], SUB], path: str, /, *, name: Optional[str] = None) -> None: ...

    def __init__(self,
                 method_or_cls_or_path: 'Union[Type[CLS], Callable[[PARENT], SUB], subobject[PARENT, SUB], str, None]' = None,
                 descr_path: Optional[str] = None,
                 /, *,
                 name: Optional[str] = None,
                 _router: Optional[Router] = None,     # hidden argument, used by Router.subobject()
                 _route: Optional[RouteEntry] = None,  # hidden argument, used by RouteObject.__init_subclass__()
                 ) -> None:
        if _router is None:
            _router = main_router

        path: Optional[str] = None
        cls: Optional[Type[CLS]] = None  # `cls` is not soported yet
        method: Optional[Callable[[PARENT], SUB]] = None
        if method_or_cls_or_path is None or isinstance(method_or_cls_or_path, str):
            if descr_path is not None:
                raise TypeError('subobject cannot use path argument twice')
            path = method_or_cls_or_path
        elif isclass(method_or_cls_or_path):
            cls = method_or_cls_or_path
            if name is not None:
                name = camel_to_snake(method_or_cls_or_path.__name__)
            # TODO: add class support
        elif isinstance(method_or_cls_or_path, subobject):
            method = method_or_cls_or_path.method
        elif callable(method_or_cls_or_path):
            method = method_or_cls_or_path
            if name is None:
                name = method.__name__
        else:
            raise TypeError(f'Unsported subobject argument {method_or_cls_or_path!r}')
        if path:
            path = path.strip('/')
            if not path:
                path = '{}'
            elif '{}' not in path:
                path += '/{}'

        #: subobject() method getter, if pattern is used, this method can take more argument then self
        self.method: Optional[Callable[[PARENT], SUB]] = method
        #: class of the method
        self.cls: Optional[Type[PARENT]] = None
        #: subocject name (by default descriptor name or method name)
        self.name: Optional[str] = name
        #: extra pattern, use `{}` to point where sub-pattern should be placed
        self.path: Optional[str] = path
        #: router where route is added if pattern is used
        self.router: Router = _router
        #: Created route.
        self.route: Optional[RouteEntry] = _route

        if self.method:
            self._add_route()

    @property
    def __wrapped__(self):
        return self.method

    def __repr__(self) -> str:
        path, method, name = self.path, self.method, self.name
        return f'subobject({path=}, {method=}, {name=})'

    @overload
    def __call__(self, cls: Type[CALL_CLS], /) -> 'subobject[Type[Any], CALL_CLS]': ...

    @overload
    def __call__(self, method: Callable[[CALL_PARENT], CALL_SUB], /) -> 'subobject[CALL_PARENT, CALL_SUB]': ...

    def __call__(self, method_or_cls: Union[Type[CALL_CLS], Callable[[CALL_PARENT], CALL_SUB]], /) -> Any:
        # "subobject" is used as @subobject(), decorator with arguments
        if isclass(method_or_cls):
            cls: CALL_CLS = method_or_cls
            if TYPE_CHECKING:
                self = cast(subobject[Type[Any], CALL_CLS], self)
            return self
        # ---
        method: Callable[[CALL_PARENT], CALL_SUB] = method_or_cls
        if self.method is not None:
            raise TypeError(f'Decorator already created for {self.method}')
        if isinstance(method, subobject):
            method = method.method
        if TYPE_CHECKING:
            self = cast(subobject[CALL_PARENT, CALL_SUB], self)
        self.method = method
        if self.name is None:
            self.__set_name__(None, method.__name__)
        self._add_route()
        return self

    @overload
    def __get__(self: Self, instance: None, objtype: Optional[Type[PARENT]] = None) -> Self: ...

    @overload
    def __get__(self: Self, instance: PARENT, objtype: Optional[Type[PARENT]] = None) -> SUB: ...

    def __get__(self: Self, instance: Optional[PARENT], objtype: Optional[Type[PARENT]] = None) -> Union[Self, SUB]:
        """Get descriptor value or instance."""
        if TYPE_CHECKING:
            assert self.name
        # grab instance class
        if self.cls is None:
            if instance is not None:
                self._update_cls(type(instance))
            elif objtype is not None:
                self._update_cls(objtype)
        # return descriptor
        if instance is None:
            return self
        # call and return subobject instance
        try:
            return instance._ff_subobject_children_by_name[self.name].child  # type: ignore[reportReturnType]  # (it's SUB)
        except KeyError:
            if self.method is not None:
                # create on demand
                value = self.method(instance)
                self.__set__(instance, value)
                return value
            raise AttributeError(f'{instance.__class__.__name__!r} object has no attribute {self.name!r}') from None

    def __set__(self, instance: PARENT, value: SUB) -> None:
        """Set descriptor value."""
        if TYPE_CHECKING:
            assert self.name
            assert self.route
        children = instance._ff_subobject_children
        by_name = instance._ff_subobject_children_by_name
        children[value] = by_name[self.name] = ChildRouteObject(child=value, route=self.route)
        value._ff_subobject_parent = ParentRouteObject(parent=instance, route=self.route)

    def __delete__(self, instance: PARENT) -> None:
        """Delete descriptor value."""
        if TYPE_CHECKING:
            assert self.name
        try:
            obj = instance._ff_subobject_children_by_name.pop(self.name)
            instance._ff_subobject_children.pop(obj.child)
        except KeyError:
            raise AttributeError(f'{instance.__class__.__name__!r} object has no attribute {self.name!r}') from None

    def __set_name__(self, owner: Type[PARENT], name: str) -> None:
        """Set descriptor value name."""
        self._update_cls(owner)
        self.name = name
        self._auto_path()
        if self.method is not None:
            if not self.router.routes or self.router.routes[-1].subobject != self.method:
                self._add_route()

    def _auto_path(self):
        if self.path is None and self.name is not None:
            path = self.name.strip('/')
            if '{}' not in path:
                if path:
                    path += '/{}'
                else:
                    path = '{}'
            self.path = path

    def _update_cls(self, cls: Type[PARENT]) -> None:
        if self.cls is None and cls is not None:
            self.cls = cls
            if self.route is not None:
                self.route.cls = cls

    def _add_route(self) -> None:
        if self.method:
            if self.route is None:
                if not self.path:
                    self._auto_path()
                if self.path:
                    route = self.router.add_route(self.path, method=self.method)
                    self.router.add_route_def(unwrap(self.method), route)
                    route.subobject = self
                    route.cls = self.cls
                    self.route = route
            else:
                self.route.subobject = self
                self.route.cls = self.cls


def unwrap(fn: T, /) -> T:
    """Retun unwrapped function."""
    while (wrapped := getattr(fn, '__wrapped__', None)) is not None:
        fn = wrapped
    return fn


def camel_to_snake(name: str) -> str:
    """Return snake_case from CamelCase, ex. TheBestAPI → the_best_api."""
    # return '_'.join(word.lower() for i, word in enumerate(_RX_SPLIT_CAMEL_WORDS.split(name)) if i % 2 or (not i and word.isalpha()))  # 'theBestAPI' works
    return '_'.join(word.lower() for word in _RX_SPLIT_CAMEL_WORDS.split(name)[1::2])


main_router = _main_router = Router(standalone=True, name='MAIN')

info_for = main_router.info_for
url_for = main_router.url_for
url_proxy = main_router.url_proxy
route_redirect = main_router.route_redirect
set_default_route_object = main_router.set_default_route_object
dispatch = main_router.dispatch
find_dispatched_call = main_router.find_dispatch
route = main_router.route
subobject_route = main_router.subobject_route
