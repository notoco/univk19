"""Common types."""

from __future__ import annotations
from sys import version_info, maxsize
from weakref import ReferenceType
from typing import Optional, Union, Any, Tuple, List, Dict, Sequence, Iterator, TypeVar, Type, overload, TYPE_CHECKING
from typing import Sized, Collection, Reversible, Callable
from typing import _SpecialForm, _GenericAlias
from typing_extensions import Literal, Annotated, Protocol, TypeForm, Self, TypeIs, TypeAlias, get_origin, get_args, runtime_checkable
import re
from functools import reduce
from operator import or_
from enum import Enum, IntEnum, Flag, IntFlag
from pathlib import Path, PurePosixPath as UPath
from urllib.parse import SplitResult, urlsplit, urlunsplit
from attrs import frozen, field
if version_info >= (3, 10):
    from types import UnionType
    _UnionType = UnionType
else:
    _UnionType = _GenericAlias  # pyright hack
    UnionType = Union
if TYPE_CHECKING:
    from datetime import timezone, tzinfo, date as dt_date, time as dt_time
    from .url import URL

SpecialType = Union[_SpecialForm, _GenericAlias, _UnionType]


#: Any JSON data object.
JsonData = Dict[str, Any]
#: Any JSON data.
JsonResult = Union[JsonData, Sequence[JsonData]]

#: Keyword arguements.
Args = Tuple[Any, ...]
#: Keyword arguements.
KwArgs = Dict[str, Any]

#: Any parameters.
Params = Dict[str, Any]
#: Web headers.
Headers = Dict[str, str]

if version_info >= (3, 10):
    from types import UnionType, EllipsisType, NoneType
else:
    UnionType = Union
    if TYPE_CHECKING:
        from types import EllipsisType, NoneType
    else:
        EllipsisType = type(...)
        NoneType = type(None)

T = TypeVar('T')
I = TypeVar('I', covariant=True)
C = TypeVar('C', bound=Type)
E = TypeVar('E', bound=Enum)
ArgType = Union[Type[Any], Callable[[Any], Any]]
AnnMeta = Sequence[Any]

TRUE_VALUES = {'true', 'on', '1', 'hi', 'high', 'up', 'enable', 'enabled'}
FALSE_VALUES = {'false', 'off', '0', 'lo', 'low', 'down', 'disable', 'disabled'}


def is_union(ann: TypeForm) -> bool:
    """Return True if type is Union."""
    origin = get_origin(ann)
    return origin is Union or origin is UnionType


def is_optional(ann: TypeForm) -> bool:
    """Return True if `ann` is optional. Optional[X] is equivalent to Union[X, None]."""
    args = get_args(ann)
    return is_union(ann) and len(args) == 2 and args[1] is type(None)


def remove_optional(ann: TypeForm[T]) -> TypeForm[T]:
    """Remove Optional[X] (if exists) and returns X."""
    args = get_args(ann)
    if is_union(ann) and len(args) == 2 and args[1] is type(None):
        return args[0]
    return ann


def is_union_none(ann: TypeForm) -> bool:
    """Return True if `ann` could be None. Union[None, ...] or Optional[X]."""
    args = get_args(ann)
    return get_origin(ann) is UnionType and any(a is type(None) or a is None for a in args)

if version_info >= (3, 10):
    from inspect import get_annotations
else:
    import sys
    import types
    import functools

    def get_annotations(obj: Any, *, globals: Optional[Params] = None, locals: Optional[Params] = None, eval_str: bool = False) -> Params:
        """Compute the annotations dict for an object. See inspect.get_annotations() from py 3.13."""

        if isinstance(obj, type):
            # class
            obj_dict = getattr(obj, '__dict__', None)
            if obj_dict and hasattr(obj_dict, 'get'):
                ann = obj_dict.get('__annotations__', None)
                if isinstance(ann, types.GetSetDescriptorType):
                    ann = None
            else:
                ann = None

            obj_globals = None
            module_name = getattr(obj, '__module__', None)
            if module_name:
                module = sys.modules.get(module_name, None)
                if module:
                    obj_globals = getattr(module, '__dict__', None)
            obj_locals = dict(vars(obj))
            unwrap = obj
        elif isinstance(obj, types.ModuleType):
            # module
            ann = getattr(obj, '__annotations__', None)
            obj_globals = getattr(obj, '__dict__')
            obj_locals = None
            unwrap = None
        elif callable(obj):
            # this includes types.Function, types.BuiltinFunctionType,
            # types.BuiltinMethodType, functools.partial, functools.singledispatch,
            # "class funclike" from Lib/test/test_inspect... on and on it goes.
            ann = getattr(obj, '__annotations__', None)
            obj_globals = getattr(obj, '__globals__', None)
            obj_locals = None
            unwrap = obj
        else:
            raise TypeError(f"{obj!r} is not a module, class, or callable.")

        if ann is None:
            return {}

        if not isinstance(ann, dict):
            raise ValueError(f"{obj!r}.__annotations__ is neither a dict nor None")

        if not ann:
            return {}

        if not eval_str:
            return dict(ann)

        if unwrap is not None:
            while True:
                if hasattr(unwrap, '__wrapped__'):
                    unwrap = unwrap.__wrapped__
                    continue
                if isinstance(unwrap, functools.partial):
                    unwrap = unwrap.func
                    continue
                break
            if hasattr(unwrap, "__globals__"):
                obj_globals = unwrap.__globals__

        if globals is None:
            globals = obj_globals
        if locals is None:
            locals = obj_locals or {}

        # "Inject" type parameters into the local namespace
        # (unless they are shadowed by assignments *in* the local namespace),
        # as a way of emulating annotation scopes when calling `eval()`
        if type_params := getattr(obj, "__type_params__", ()):
            locals = {param.__name__: param for param in type_params} | locals

        return_value = {key:
            value if not isinstance(value, str) else eval(value, globals, locals)
            for key, value in ann.items() }
        return return_value


if version_info < (3, 9):
    class ReferenceType(ReferenceType):
        def __class_getitem__(cls, typ):
            return Annotated[typ, ReferenceType]


def is_literal(obj: object, cls: Type[T]) -> TypeIs[T]:
    """Return True if `obj` in in Literal type `cls`."""
    return obj in get_args(cls)


@runtime_checkable
class DateTime(Protocol):
    """Simplifed py datetime class."""

    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int
    microsecond: int

    @classmethod
    def today(cls) -> Self: ...

    @classmethod
    def now(cls, tz: timezone | None = None) -> Self: ...

    @classmethod
    def fromtimestamp(cls, timestamp: float, tz: tzinfo | None = None) -> Self: ...

    @classmethod
    def combine(cls, date: 'dt_date', time: 'dt_time', tzinfo: tzinfo | None = None) -> Self: ...

    def isoformat(self) -> str: ...

    def date(self) -> dt_date: ...

    def time(self) -> dt_time: ...


class PagedItemList(Reversible, Collection[T], Protocol):
    """Item list with pagination info."""

    @overload
    def __getitem__(self, index: int, /) -> T: ...

    @overload
    def __getitem__(self, index: slice, /) -> Sequence[T]: ...

    def index(self, value: T, start=0, stop=maxsize, /) -> int: ...

    def count(self, value: T, /) -> int: ...

    @property
    def page(self) -> int: ...

    @property
    def page_size(self) -> int: ...

    @property
    def total_pages(self) -> int: ...

    @property
    def total_results(self) -> int: ...

    def next_page(self) -> Optional[int]: ...


if version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum
    class StrEnum(str, Enum):
        """Enum where members are also (and must be) strings."""

        def __new__(cls, *values):
            "values must already be of type `str`"
            if len(values) > 3:
                raise TypeError('too many arguments for str(): %r' % (values, ))
            if len(values) == 1:
                # it must be a string
                if not isinstance(values[0], str):
                    raise TypeError('%r is not a string' % (values[0], ))
            if len(values) >= 2:
                # check that encoding argument is a string
                if not isinstance(values[1], str):
                    raise TypeError('encoding must be a string, not %r' % (values[1], ))
            if len(values) == 3:
                # check that errors argument is a string
                if not isinstance(values[2], str):
                    raise TypeError('errors must be a string, not %r' % (values[2]))
            value = str(*values)
            member = str.__new__(cls, value)
            member._value_ = value
            return member

        @staticmethod
        def _generate_next_value_(name, start, count, last_values):
            """Return the lower-cased version of the member name."""
            return name.lower()


# --- argument descriptions ---


def ann_type(ann: Annotated, cls: TypeForm[T] = None) -> Tuple[TypeForm[T], AnnMeta]:
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


class _Unsigned:
    """Unsigned[int] argument pseudo-type for annotations."""


class _Positive:
    """Positive[int] argument pseudo-type for annotations."""


Unsigned: TypeAlias = Annotated[T, _Unsigned]
Positive: TypeAlias = Annotated[T, _Positive]


def mk_none(v: str) -> None:
    """Make bool."""
    if v:
        raise ValueError(f'Non-empty none {v!r}')
    return None


def mk_bool(v: str) -> bool:
    """Make bool."""
    if isinstance(v, str):
        v = v.lower()
        if v in TRUE_VALUES:
            return True
        if v in FALSE_VALUES:
            return False
        raise ValueError(f'Unknown bool format {v!r}')
    return bool(v)


def uint(v: str) -> int:
    """Make unsigned int."""
    val = int(v)
    if val < 0:
        raise ValueError(f'Negative uint {v!r}')
    return val


def pint(v: str) -> int:
    """Make positive int."""
    val = int(v)
    if val <= 0:
        raise ValueError(f'Non-positive int {v!r}')
    return val


def ufloat(v: str) -> float:
    """Make unsigned float."""
    val = float(v)
    if val < 0:
        raise ValueError(f'Negative ufloat {v!r}')
    return val


def mk_path(v: str) -> Path:
    """Make Path()."""
    if v.startswith('./'):
        return Path(v[2:])
    if not v.startswith('/'):
        v = f'/{v}'
    return Path(v)


def mk_upath(v: str) -> UPath:
    """Make Path()."""
    if v.startswith('./'):
        return UPath(v[2:])
    if not v.startswith('/'):
        v = f'/{v}'
    return UPath(v)


def mk_url(v: str) -> 'URL':
    """Make simple URL."""
    from .url import URL
    if not v.startswith('/'):
        v = f'/{v}'
    return URL(v)


@frozen
class EnumDumper:
    transform: Callable[[Any], Any] = str
    attr: Literal['enum', 'fullname', 'name', 'value'] = 'name'  # name or value

    def __repr__(self) -> str:
        return f'EnumDumper({self.transform.__qualname__}, {self.attr!r})'


# EnumFullName: TypeAlias = Annotated[E, EnumDumper(lambda e: str(e).lower(), 'enum')]
EnumEnum: TypeAlias = Annotated[E, EnumDumper(str, 'enum')]
EnumFullName: TypeAlias = Annotated[E, EnumDumper(str, 'fullname')]
EnumName: TypeAlias = Annotated[E, EnumDumper(str.lower)]
EnumValue: TypeAlias = Annotated[E, EnumDumper(str, 'value')]


@frozen
class ArgDescr:
    """Type conversion  description."""
    #: Argument type.
    type: ArgType = str
    #: Regex pattern to argument parse.
    pattern: Union[str, Callable[[TypeForm[Any], AnnMeta], str]] = r'.*'
    #: If True, regex is passed to `type`. If False, the string value.  TODO: check if is used.
    rx: bool = field(default=False, kw_only=True)
    #: Dump value to url argument.
    dumper: Optional[Callable[[Any, AnnMeta], str]] = field(default=None, kw_only=True)
    #: Load value from url argument.
    loader: Optional[Callable[[str, TypeForm[Any], AnnMeta], Any]] = field(default=None, kw_only=True)

    def pat(self, cls: TypeForm[Any], meta: AnnMeta = ()) -> str:
        if callable(self.pattern):
            return self.pattern(cls, meta)
        return self.pattern

    def dump(self, val: Any, cls: TypeForm, meta: AnnMeta = ()) -> str:
        if self.dumper:
            return self.dumper(val, meta)
        if val is None:
            return ''
        if isinstance(val, bool):
            return 'true' if val else 'false'
        if isinstance(val, (Path, UPath)):
            from .tricks import str_removeprefix
            return str_removeprefix(str(val), '/')
        if isinstance(val, SplitResult):
            from .tricks import str_removeprefix
            return str_removeprefix(urlunsplit(val), '/')
        # if isinstance(val, SafeUrl):
        #     return quote_plus(val)
        # if isinstance(val, tuple):
        #     return ','.join(self.dump(v) for v in val)
        return f'{val}'

    @staticmethod
    def _prepare(typ: TypeForm[T], meta: Optional[AnnMeta]) -> Tuple[TypeForm[T], AnnMeta]:
        typ = remove_optional(typ)
        if meta is None:
            meta = ()
        if get_origin(typ) is Annotated:
            args = get_args(typ)
            typ = remove_optional(args[0])
            meta = (*args[1:], *meta)
        return typ, meta

    def load(self, val: str, cls: TypeForm, meta: Optional[AnnMeta] = None) -> Any:
        cls, meta = self._prepare(cls, meta)
        if self.loader:
            return self.loader(val, cls, meta)
        if cls is None or cls is NoneType:
            return mk_none(val)
        if callable(self.type):
            return self.type(val)
        return str(val)


@frozen
class LiteralArg(ArgDescr):

    def pat(self, cls: TypeForm[Any], meta: AnnMeta = ()) -> str:
        """Return regex pattern for literal."""
        def literal_to_rx(val) -> str:
            if val is None:
                return ''  # TODO: Add Literal[None] support
            if val is True:
                return 'true|1'
            if val is False:
                return 'false|0'
            typ = type(val)
            if typ is int or typ is float:
                val = str(val)
            if issubclass(typ, Enum):
                at, _ = find_arg_descr(typ)
                if at:
                    return at.pat(typ, meta)
            return re.escape(str(val))
        cls, meta = self._prepare(cls, meta)
        type_args = get_args(cls)
        if type_args:
            apat = '|'.join(literal_to_rx(a) for a in type_args)
            return f'(?:{apat})'
        return ANN_TYPES[str].pat(cls, meta)

    def dump(self, val: Any, cls: TypeForm, meta: AnnMeta = ()) -> str:
        if isinstance(val, Enum):
            at, _ = find_arg_descr(type(val))
            if at:
                return at.dump(val, cls, meta)
        return super().dump(val, cls, meta)

    def load(self, val: str, cls: TypeForm, meta: Optional[AnnMeta] = None) -> Any:
        cls, meta = self._prepare(cls, meta)
        if get_origin(cls) is Literal:
            aargs = get_args(cls)
            # TODO: Add Literal[Enum] support
            for a in aargs:
                if a is None and val == '':
                    return None
                if a is True and val in ('true', '1'):  # simplified values
                    return True
                if a is False and val in ('false', '0'):  # simplified values
                    return False
                if isinstance(a, Enum):
                    at, _ = find_arg_descr(type(a))
                    if at:
                        return at.load(val, type(a), meta)
                if val == str(a):
                    return type(a)(val)
        raise ValueError(f'Value {val!r} does NOT match to literal {cls}')


@frozen
class EnumArg(ArgDescr):

    default: EnumDumper = field(kw_only=True)

    def _get_ed(self, meta: AnnMeta) -> EnumDumper:
        return next(iter(mt for mt in meta if isinstance(mt, EnumDumper)), self.default)

    def pat(self, cls: TypeForm[Enum], meta: AnnMeta = ()) -> str:
        cls, meta = self._prepare(cls, meta)
        if not isinstance(cls, type):
            return super().pat(cls, meta)
        ed = self._get_ed(meta)
        if issubclass(cls, IntFlag) and ed.attr == 'value':
            return r'\d+'
        if ed.attr in ('enum', 'fullname'):
            pat = ''
        else:
            pat = '|'.join(ed.transform(str(v)) for e in cls.__members__.values() if (v := getattr(e, ed.attr)) is not None)
        if issubclass(cls, Flag):
            # class name and Flag names and values are save, omit re.escape()
            av = '|'.join(e.name for e in cls.__members__.values() if e.name)
            epat = fr'{cls.__name__}\.(?:{av})(?:\|(?:{av}))*'
            if issubclass(cls, IntFlag):
                pat = fr'{pat}|\d+' if pat else r'\d+'
            if pat:
                pat = fr'(?:{pat})(?:,(?:{pat}))*|{epat}'
            else:
                pat = epat
            if ed.attr == 'value':
                pat = fr'{pat}|\d+'
        return f'(?:{pat})'

    def dump(self, val: Any, cls: TypeForm, meta: AnnMeta = ()) -> str:
        def bits(val: Flag) -> Sequence[str]:
            if version_info >= (3, 10):
                flags = sorted(type(val).__members__.values(), key=lambda e: e.value.bit_count(), reverse=True)
            else:
                flags = sorted(type(val).__members__.values(), key=lambda e: bin(e.value).count('1'), reverse=True)
            mask = val.value
            hit = []
            for e in flags:
                v = e.value
                if v & mask == v:
                    hit.append(e)
                    mask &= ~v
                if not mask:
                    break
            names = sorted(str(ed.transform(e.name)) for e in hit)
            if isinstance(val, IntFlag) and mask:
                names.append(str(mask))
            return names

        if not isinstance(val, Enum):
            # raise TypeError(type(val))
            return super().dump(val, cls, meta)
        ed = self._get_ed(meta)
        if ed.attr == 'fullname':
            if isinstance(val, Flag):
                vals = '|'.join(bits(val))
                return f'{val.__class__.__name__}.{vals}'
            return f'{val.__class__.__name__}.{ed.transform(val.name)}'
        if ed.attr == 'enum':
            return str(ed.transform(val))
        if (x := getattr(val, ed.attr)) is not None and (ed.attr != 'name' or '|' not in x):
            return str(ed.transform(x))
        if ed.attr == 'name' and isinstance(val, Flag):
            return ','.join(bits(val))
        return super().dump(val, cls, meta)

    def load(self, val: str, cls: TypeForm, meta: Optional[AnnMeta] = None) -> Any:
        cls, meta = self._prepare(cls, meta)
        ed = self._get_ed(meta)
        if isinstance(cls, type) and issubclass(cls, Enum):
            # Flags with `|` or `,` has more flags, there is no sense to compare with defined value
            if ('|' not in val and ',' not in val) or not issubclass(cls, Flag):
                for e in cls.__members__.values():
                    if ed.attr == 'enum':
                        if val == str(ed.transform(e)):
                            return e
                    elif ed.attr == 'fullname':
                        if val == f'{cls.__name__}.{ed.transform(e.name)}':
                            return e
                    elif val == str(ed.transform(getattr(e, ed.attr))):
                        return e
                for e in cls.__members__.values():
                    if val == str(e.value):
                        return e
            if issubclass(cls, Flag):
                def flag_to_int(val: str, flg: str) -> int:
                    if val.isdecimal():
                        return int(val)
                    for e in cls.__members__.values():
                        if ed.attr == 'enum':
                            tr = e
                        elif ed.attr == 'fullname':
                            tr = f'{cls.__name__}.{e.name}'
                        else:
                            tr = getattr(e, ed.attr)
                        if str(ed.transform(tr)) == flg:
                            return e.value
                    return 0
                if val.isdecimal():
                    return cls(int(val))
                # int_flag = issubclass(cls, IntFlag):
                if ',' in val:
                    return cls(reduce(or_, (flag_to_int(s, s) for s in val.split(','))))
                elif '|' in val and '.' in val and ed.attr in ('enum', 'fullname'):
                # elif '.' in val and ed.attr == 'enum':
                    return cls(reduce(or_, (flag_to_int(s, f'{cls.__name__}.{s}') for s in val.partition('.')[2].split('|'))))

        raise ValueError(f'Value {val!r} does NOT match to enum/flag {cls}')


none_arg = ArgDescr(mk_none, r'(?:)')

#: Annotated typed, used on path (see _RE_PATH_ARG) and with PathArg[...].
ANN_TYPES: Dict[TypeForm[Any], ArgDescr] = {
    Literal:             LiteralArg(),
    Enum:                EnumArg(Enum,            default=EnumDumper(str.lower, 'name')),
    IntEnum:             EnumArg(IntEnum,         default=EnumDumper(str, 'value')),
    StrEnum:             EnumArg(StrEnum,         default=EnumDumper(str, 'value')),
    Flag:                EnumArg(Flag,            default=EnumDumper(str.lower, 'name')),
    IntFlag:             EnumArg(IntFlag,         default=EnumDumper(str, 'value')),
    str:                 ArgDescr(str,            r'[^/]+'),
    UPath:               ArgDescr(mk_upath,       r'.+'),
    Path:                ArgDescr(mk_path,        r'.+'),
    SplitResult:         ArgDescr(mk_url,         r'.+'),
    # SafeUrl:             ArgDescr(mk_safe_url,    r'[^/]+'),
    int:                 ArgDescr(int,            r'[+-]?\d+'),
    Unsigned[int]:       ArgDescr(uint,           r'\d+'),
    Positive[int]:       ArgDescr(pint,           r'[1-9]\d*'),
    Positive:            ArgDescr(pint,           r'[1-9]\d*'),
    float:               ArgDescr(float,          r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(:?[eE][+-]?\d+)?'),
    Unsigned[float]:     ArgDescr(float,          r'(?:\d+(?:\.\d*)?|\.\d+)(:?[eE][+-]?\d+)?'),
    bool:                ArgDescr(mk_bool,        r'true|false|0|1'),
    # None:                none_arg,
    Any:                 ArgDescr(),
}


def find_arg_descr(ann: TypeForm,
                   *,
                   meta: AnnMeta = (),
                   annotations: Dict[TypeForm[Any], ArgDescr] = ANN_TYPES,
                   quiet: bool = False,
                   ) -> Tuple[Optional[ArgDescr], AnnMeta]:
    """Find description type."""
    typ = remove_optional(ann)
    if at := annotations.get(ann):
        return at, meta
    otype = get_origin(ann)
    if otype is Annotated:
        typ, *meta = get_args(ann)
        typ = remove_optional(typ)
        if at := annotations.get(typ):
            return at, meta
        otype = get_origin(typ)
    else:
        typ = ann
    if at := annotations.get(otype):  # type: ignore[reportArgumentType]
        return at, meta
    for base_type in getattr(typ, '__mro__', (typ,)):
        if at := annotations.get(base_type):
            return at, meta
    from .log_utils import fflog
    if not quiet:
        fflog.error(f'Unsupported argument type: {ann!r}')
    return None, meta
    # return ArgDescr(), meta


def flag_names(flag: Flag) -> str:
    """"Dump flag to comma-separated list of flag names."""
    return ANN_TYPES[Flag].dump(flag, Flag)
