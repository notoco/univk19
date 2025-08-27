"""Some useful tricks."""

from sys import version_info
from functools import wraps, partial
from itertools import chain, zip_longest
from collections import namedtuple
from inspect import signature, Signature, Parameter
from inspect import ismethod, isfunction, isbuiltin, getmro, getmodule, currentframe
from dataclasses import Field, is_dataclass
import dataclasses as dc
from functools import reduce
from operator import or_
import threading
from enum import Flag
from datetime import datetime, date as dt_date, time as dt_time
from typing import Optional, Union, Any, Tuple, List, Dict, Mapping, Iterator, Iterable, Type, TypeVar, Callable, NoReturn, NamedTuple, TYPE_CHECKING
from types import ModuleType, TracebackType
from typing_extensions import Concatenate, ParamSpec, TypeGuard, cast, get_type_hints, Protocol, overload
import attrs
from attrs import Attribute

from .log_utils import fflog_exc, fflog
from ..exc import DeprecatedError
from ..service.exc import KodiExit


if version_info >= (3, 9):
    str_removeprefix = str.removeprefix
else:
    def str_removeprefix(s: str, __prefix: str):
        """
        If the string starts with the prefix string, return string[len(prefix):].
        Otherwise, return a copy of the original string.
        """
        if s.startswith(__prefix):
            return s[len(__prefix):]
        return s

if version_info >= (3, 10):
    from itertools import pairwise
else:
    from itertools import tee

    def pairwise(iterable):
        """
        Return successive overlapping pairs taken from the input iterable.
        pairwise('ABCDE') --> AB BC CD DE.
        """
        a, b = tee(iterable)
        next(b, None)
        return zip(a, b)

if version_info >= (3, 12):
    from itertools import batched
else:
    from itertools import islice

    def batched(iterable, n):
        """
        Batch data from the iterable into tuples of length n. The last batch may be shorter than n.
        batched('ABCDEFG', 3) --> ABC DEF G
        """
        if n < 1:
            raise ValueError('n must be at least one')
        it = iter(iterable)
        while batch := tuple(islice(it, n)):
            yield batch


if TYPE_CHECKING:
    from dataclasses import _DataclassParams


P = ParamSpec('P')
K = ParamSpec('K')
T = TypeVar('T')
C = TypeVar('C')
F = TypeVar('F', bound=Flag)
RET = TypeVar('RET')
N = TypeVar('N')
# NC = Callable[Concatenate[N, P], T]
NC = Concatenate[N, P]


class DataClass(Protocol):
    __dict__: Dict[str, Any]
    __doc__: Optional[str]
    # if using `@dataclass(slots=True)`
    __slots__: Union[str, Iterable[str]]
    __annotations__: Dict[str, Union[str, type]]
    __dataclass_fields__: Dict[str, Field]
    # the actual class definition is marked as private, and here I define
    # it as a forward reference, as I don't want to encourage
    # importing private or "unexported" members.
    # __dataclass_params__: '_DataclassParams'
    # __post_init__: Optional[Callable]


def singleton(orig_cls: Type[T]) -> Type[T]:
    """Singleton class decorator. Only one instance of the class is created."""
    orig_new: Callable = orig_cls.__new__
    instance: Any = None

    @wraps(orig_cls.__new__)
    def __new__(cls, *args, **kwargs):
        nonlocal instance
        if instance is None:
            # object.__new__ takes only one argument
            if orig_new is object.__new__:
                instance = object.__new__(cls)
            else:
                instance = orig_new(cls, *args, **kwargs)
            if cls.__singleton_init__:
                cls.__singleton_init__(instance, *args, **kwargs)
        return instance

    # override __new__
    orig_cls.__new__ = __new__
    # remove __init__ to keep call it once
    orig_cls.__singleton_init__ = getattr(orig_cls, '__init__', None)
    if orig_cls.__singleton_init__ is not None and orig_cls.__singleton_init__ is not object.__init__:
        if not any(orig_cls.__init__ is c.__init__ for c in orig_cls.mro()[1:]):
            del orig_cls.__init__
    return orig_cls


@singleton
class MissingType:
    """General type of singleton MISSING."""

    def __repr__(self) -> str:
        return 'MISSING'


#: General missing singleton object.
MISSING = MissingType()


class suppress:
    """
    Decorator and context manager that suppresses any of the specified exceptions.

    Examples.
    >>> with suppress(FileNotFoundError):
    >>>     os.remove('somefile.tmp')
    >>>
    >>> @suppress(FileNotFoundError)
    >>> def foo():
    >>>     os.remove('somefile.tmp')
    """

    def __init__(self, *exceptions, return_on_exception: Any = None,
                 errors_arg: bool = False, log_traceback: bool = False) -> None:
        #: List of suppressed exceptions.
        self._exceptions: Tuple[BaseException, ...] = exceptions
        #: Value to return by decorated function if suppressed exception occurs.
        self._return_on_exception: Any = return_on_exception
        #: Look into `errors` function argument in decorator.
        self._errors_arg: bool = errors_arg
        #: Log traceback on exception.
        self._log_traceback: bool = log_traceback
        # # is it @suppress without arguments?
        # if len(exceptions) == 1 and callable(exceptions[0]) and not issubclass(exceptions[0], BaseException):
        #     self._exceptions = (Exception,)

    def __call__(self, func: Callable[P, RET]) -> Callable[P, RET]:
        if self._errors_arg:
            @wraps(func)
            def wrapped(*args, errors: str = 'ignore', **kwargs):
                try:
                    return func(*args, **kwargs)
                except BaseException as exc:
                    if errors == 'ignore' and self._check_if_suppressed(exc.__class__, exc):
                        return self._return_on_exception
                    if self._log_traceback:
                        fflog_exc()
                    raise
        else:
            @wraps(func)
            def wrapped(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except BaseException as exc:
                    if self._check_if_suppressed(exc.__class__, exc):
                        return self._return_on_exception
                    if self._log_traceback:
                        fflog_exc()
                    raise

        return wrapped

    def __enter__(self) -> None:
        pass

    def __exit__(self, exc_type, exc_inst, exc_tb):
        # return exc_type is not None and issubclass(exc_type, self._exceptions)
        return self._check_if_suppressed(exc_type, exc_inst)
        if exc_type is None:
            return
        if issubclass(exc_type, self._exceptions):
            return True
        # Python 3.12 adds support for Py3.11 ExceptionGroup
        if version_info >= (3, 11) and issubclass(exc_type, ExceptionGroup):
            match, rest = exc_inst.split(self._exceptions)
            if rest is None:
                return True
            raise rest
        if self._log_traceback:
            fflog_exc()
        return False

    def _check_if_suppressed(self, exc_type, exc_inst) -> bool:
        if exc_type is None:
            return False
        if issubclass(exc_type, self._exceptions):
            return True
        # Python 3.12 adds support for Py3.11 ExceptionGroup
        if version_info >= (3, 11) and issubclass(exc_type, ExceptionGroup):
            match, rest = exc_inst.split(self._exceptions)
            if rest is None:
                return True
            raise rest
        return False


def is_namedtuple(obj: object) -> TypeGuard[Tuple]:
    """Retrun true if object is a namedtuple (NamedTuple)."""
    return isinstance(obj, tuple) and hasattr(type(obj), '_fields')


def is_namedtuple_class(cls: Any) -> TypeGuard[Type[Tuple]]:
    """Retrun true if class inheris from namedtuple (NamedTuple)."""
    return isinstance(cls, type) and issubclass(cls, tuple) and hasattr(cls, '_fields')


def namedtuple_attrs(cls: Type[Tuple]) -> Tuple[Attribute, ...]:
    """Return attrs.fields for namedtuple."""
    def make_field(name: str) -> Attribute:
        if name in defaults:
            default = defaults[name]
        else:
            default = attrs.NOTHING
        return Attribute(name=name, default=default, validator=None, repr=True, cmp=False, hash=None, init=True,
                         inherited=False, type=ann[name])  # type: ignore

    if not is_namedtuple(cls) and not is_namedtuple_class(cls):
        raise TypeError('must be called with a namedtuple type or instance') from None

    defaults: Dict[str, Any] = cls._field_defaults
    ann = get_type_hints(cls)
    return tuple(make_field(f) for f in cls._fields)


def namedtuple_fields(cls: Type[Tuple]) -> Tuple[Field, ...]:
    """Return dataclasses.fields from namedtuple."""
    def make_field(name: str) -> Field:
        f = dc.field()
        f.name = name
        f.type = ann[name]
        if name in defaults:
            f.default = defaults[name]
        return f

    if not is_namedtuple(cls) and not is_namedtuple_class(cls):
        raise TypeError('must be called with a namedtuple type or instance') from None

    defaults: Dict[str, Any] = cls._field_defaults
    ann = get_type_hints(cls)
    return tuple(make_field(f) for f in cls._fields)


def namedtuple_base(base: Type[NamedTuple]) -> Callable[[Type[NamedTuple]], Type[NamedTuple]]:
    """
    Decorator for NamedTuple derivation.

    The class is not derived from base class (isinstance fails), only fields are taken.
    If base class uses defaults all fields must use defaults.

    >>> class Point2d(NamedTuple):
    >>>     x: int
    >>>     y: int
    >>>
    >>> @namedtuple_base(Point2d)
    >>> class Point3d(NamedTuple):
    >>>     z: int
    >>>
    >>> Point3d(1, 2, 3)
    """

    def create_namedtuple(kls: Type) -> Type[NamedTuple]:
        def rev_defaults():
            defaults = {**base._field_defaults, **kls._field_defaults}
            for f in reversed(fields):
                if f not in defaults:
                    break
                yield defaults[f]

        if base._field_defaults and len(kls._field_defaults) < len(kls._fields):
            raise ValueError(f'Subclass {kls.__name__} have to set defaults for all fields')
        fields = base._fields + kls._fields
        nm_tpl = namedtuple(kls.__name__, fields, defaults=list(reversed(list(rev_defaults()))), module=kls.__module__)
        nm_tpl.__annotations__ = nm_tpl.__new__.__annotations__ = {**base.__annotations__, **kls.__annotations__}
        return nm_tpl

    return create_namedtuple


def is_attrs_class(obj) -> TypeGuard[Union[Type[attrs.AttrsInstance], attrs.AttrsInstance]]:
    cls = obj if isinstance(obj, type) else type(obj)
    return attrs.has(cls)


def dataclass_attrs(cls: Type[DataClass]) -> Tuple[Attribute, ...]:
    """Return attrs.fields from dataclass."""

    def make_field(f: Field) -> Attribute:
        if f.default is dc.MISSING:
            default = attrs.NOTHING
        elif f.default_factory is not dc.MISSING:
            default = attrs.Factory(f.default_factory)
        else:
            default = f.default
        return Attribute(name=f.name, default=default, validator=None, repr=f.repr, cmp=f.compare, hash=f.hash, init=f.init,
                         inherited=False, type=f.type)  # type: ignore

    if not is_dataclass(cls):
        raise TypeError('must be called with a dataclass type or instance') from None

    # ann = get_type_hints(cls)
    return tuple(make_field(f) for f in dc.fields(cls))


def dict_diff_new(a: Mapping, b: Mapping, *, recursion: bool = True) -> Dict:
    """Return dict new and differented values (b over a)."""
    # same = a.keys() & b.keys()
    # new = b.keys() - a.keys()
    if recursion:
        return {k: dict_diff_new(a[k], v) if k in a and isinstance(v, Mapping) else v
                for k, v in b.items() if k not in a or a[k] != v}
    else:
        return {k: v for k, v in b.items() if k not in a or a[k] != v}


def dump_obj_gets(obj: Any, pattern: str = 'get', def_str_key: str = 'tmdb') -> Iterator[Tuple[str, Any]]:
    """Dump obj.get*()."""
    attrs: List[str] = dir(obj)
    if hasattr(obj, '__wrapped__') and hasattr(type(obj), '__dict__'):
        attrs.extend(type(obj).__dict__)  # access to wrapper methods
    for attr in attrs:
        if attr.startswith(pattern):
            getter = getattr(obj, attr, None)
            # ismethod(getter) - it works ONLY with class wirtent in Python
            if callable(getter) and getattr(getter, '__self__', None) is not None:
                sig: Signature = signature(getter)
                try:
                    name = getter.__qualname__
                except AttributeError:
                    name = f'{obj.__class__.__name__}.{attr}'
                try:
                    val = getter()
                except (TypeError, DeprecatedError):
                    def def_val(p: Parameter) -> Any:
                        if p.annotation is str and def_str:  # noqa: B023  (`def_str` is shared list)
                            return def_str.pop(0)            # noqa: B023
                        if p.annotation in (str, bool, int, float):
                            return p.annotation()
                        return ''

                    def_str: List[str] = [def_str_key]
                    try:
                        params = sig.parameters.values()
                        args = [def_val(p) for p in params if p.default is p.empty and p.kind is p.POSITIONAL_ONLY]
                        kwargs = {p.name: def_val(p)
                                  for p in params if p.default is p.empty and p.kind is not p.POSITIONAL_ONLY}
                        val = getter(*args, **kwargs)
                    except DeprecatedError as exc:
                        yield name, exc
                        continue
                    except Exception:  # as exc:
                        # yield f'{obj.__class__.__name__}.{attr}() = ???  # {exc}'
                        yield name, NoReturn
                        continue
                # yield f'{obj.__class__.__name__}.{attr}() = {val!r}'
                yield name, val


@overload
def super_get_attr(obj: Any, key: str, /) -> Any: ...


@overload
def super_get_attr(obj: Any, key: str, default: T, /) -> Union[Any, T]: ...


def super_get_attr(obj: Any, key: str, /, *default) -> Any:
    """Like getattr() with sub.obj.support."""
    if '.' not in key:
        return getattr(obj, key, *default)
    for k in key.split('.'):
        obj = getattr(obj, k, *default)
    return obj


def super_set_attr(obj: Any, key: str, value: Any) -> None:
    """Like setattr() with sub.obj.support."""
    keys = key.split('.')
    for k in keys[:-1]:
        obj = getattr(obj, k)
    setattr(obj, keys[-1], value)


def super_has_attr(obj: Any, key: str) -> Any:
    """Like hasattr() with sub.obj.support."""
    try:
        super_get_attr(obj, key)
    except AttributeError:
        return False
    return True


# See: https://stackoverflow.com/a/71968448/9935708
def with_function_typing(_: Callable[P, Any]) -> Callable[[Callable[..., T]], Callable[P, T]]:
    """Decorator does nothing but returning the casted original function."""

    def return_func(func: Callable[..., T]) -> Callable[P, T]:
        return cast(Callable[P, T], func)

    return return_func


def with_method_typing(_: Callable[Concatenate[C, P], Any]) -> Callable[[Callable[..., T]], Callable[P, T]]:
    """Decorator does nothing but returning the casted original method (ignore self/cls)."""

    def return_func(func: Callable[..., T]) -> Callable[P, T]:
        return cast(Callable[P, T], func)

    return return_func


# See: https://stackoverflow.com/a/25959545/9935708
def get_method_class(meth):
    """Get class of method `meth`, bound or not."""

    if isinstance(meth, partial):
        return get_method_class(meth.func)
    if (ismethod(meth) or (isbuiltin(meth) and getattr(meth, '__self__', None) is not None
                           and getattr(meth.__self__, '__class__', None))):
        for cls in getmro(meth.__self__.__class__):
            if meth.__name__ in cls.__dict__:
                return cls
        meth = getattr(meth, '__func__', meth)  # fallback to __qualname__ parsing
    if isfunction(meth):
        cls = getattr(getmodule(meth),
                      meth.__qualname__.split('.<locals>', 1)[0].rsplit('.', 1)[0],
                      None)
        if isinstance(cls, type):
            return cls
    return getattr(meth, '__objclass__', None)  # handle special descriptor objects


def join_items(*items: Iterable[T], zip_chunk: int = 0) -> Iterable[T]:
    """
    Join list it items by `zip_chunk`.


    >>> join_items('abc', '123', zip_chunk=0)  # abc123
    >>> join_items('abc', '123', zip_chunk=1)  # a1b2c3
    >>> join_items('abc', '123', zip_chunk=2)  # ab12c3
    """
    if not items:
        pass

    elif len(items) == 1:
        yield from iter(items[0])

    elif zip_chunk <= 0:
        yield from chain(*items)

    elif zip_chunk == 1:
        for row in zip_longest(*items, fillvalue=MISSING):
            for it in row:
                if it is not MISSING:
                    yield it

    else:
        iters: List[Optional[Iterator[T]]] = [iter(ii) for ii in items]
        running = True
        while running:
            running = False
            for i, it in enumerate(iters):
                if it is not None:
                    for j in range(zip_chunk):
                        try:
                            yield next(it)
                            running = True
                        except StopIteration:
                            iters[i] = None
                            break


# Modiled Gareth Rees method.
# See: https://codereview.stackexchange.com/a/86067
def cyclic(*graphs: Union[Dict[T, Iterable[T]], Dict[T, Dict[T, Any]]]) -> bool:
    """
    Return True if the directed graph has a cycle.
    The graph must be represented as a dictionary mapping vertices to
    iterables of neighbouring vertices. For example:

    >>> cyclic({1: (2,), 2: (3,), 3: (1,)})
    True
    >>> cyclic({1: (2,), 2: (3,), 3: (4,)})
    False
    """
    visited = set()
    path = [object()]
    path_set = set(path)
    stack = [set(chain(*graphs))]
    while stack:
        for v in stack[-1]:
            if v in path_set:
                return True
            elif v not in visited:
                visited.add(v)
                path.append(v)
                path_set.add(v)
                stack.append({x for g in graphs for x in g.get(v, ())})
                break
        else:
            path_set.remove(path.pop())
            stack.pop()
    return False


class adict(dict):
    """Just dict() with attribute access."""

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None


class FormatObjectGetter:
    """Wrapper for ovject to auto call attributes. Useful for str format."""

    TYPES = {int, float, str, bytes, datetime, dt_date, dt_time}

    def __init__(self, obj: Any) -> None:
        self.__wrapped__ = obj

    def __getattr__(self, key: str):
        try:
            value = getattr(self.__wrapped__, key)
        except AttributeError as exc:
            try:
                value = getattr(self.__wrapped__, f'get{key}')
            except AttributeError:
                raise exc
            pass
        if callable(value):
            value = value()
        if type(value) in self.TYPES:
            return value
        return FormatObjectGetter(value)


class AlwaysFalse:
    """Fake false object."""

    def __bool__(self) -> bool:
        return False


class ThreadExceptHookArgsType(Protocol):
    exc_type: Type[BaseException]
    exc_value: Optional[BaseException]
    exc_traceback: TracebackType
    thread: Optional[threading.Thread]


def thread_excepthook(args: ThreadExceptHookArgsType) -> None:
    """Hook exception in thread."""
    if args.exc_value and args.exc_type not in (KodiExit, SystemExit, KeyboardInterrupt):
        fflog(f'EXCEPTION in thread: {args.thread}')
        fflog_exc(args.exc_value)
    else:
        fflog(f'Force exiting ({args.exc_type}) thread: {args.thread}')


# Override exception hook.
threading.excepthook = thread_excepthook


def current_line_number(depth: int = 1) -> int:
    """Return caller file line number."""
    cf = currentframe()
    for _ in range(depth):
        if not cf:
            break
        cf = cf.f_back
    return cf.f_lineno if cf else 0


def jwt_decode(token: str) -> Dict[str, Any]:
    """Simple JWT (JSON-Web-Token) decode."""
    from base64 import b64decode
    import json
    _, payload, *_ = token.split('.')
    if pad := len(payload) % 4:
        payload += '=' * (4 - pad)
    return json.loads(b64decode(payload).decode())


if version_info >= (3, 11):
    def iter_flags(cls_or_flag: Union[F, Type[F]], /) -> Iterator[F]:  # type: ignore[reportRedeclaration]
        """Iterate over separate flags (default since py 3.11)."""
        yield from iter(cls_or_flag)
else:
    def iter_flags(cls_or_flag: Union[F, Type[F]], /) -> Iterator[F]:
        """Iterate over separate flags (default since py 3.11)."""
        if isinstance(cls_or_flag, type):
            flag, cls = None, cls_or_flag
        else:
            flag, cls = cls_or_flag, type(cls_or_flag)
        flags2: Optional[Tuple[F, ...]]
        if (flags2 := getattr(cls, '_flags2', None)) is None:
            flags2 = tuple(sorted((f for f in cls if (v := f.value) and not (v & (v-1))), key=lambda f: f.value))
            setattr(cls, '_flags2', flags2)
        if flag is None:
            yield from flags2
        else:
            for f in flags2:
                if f & flag:
                    yield from f


def or_reduce(seq: Iterable[T]) -> T:
    """Reduce sequence with `or` operator."""
    return reduce(or_, seq)


# --- DEBUG & TESTS ---


if __name__ == '__main__':
    print(list(dump_obj_gets({'xxx': 123})))
    from contextlib import contextmanager
    from typing import get_args

    @contextmanager
    def assert_raises(*exceptions):
        try:
            yield
        except BaseException as exc:
            if version_info >= (3, 11):
                if issubclass(exc.__class__, BaseExceptionGroup):
                    exceptions = tuple(s for e in exceptions for s in (get_args(e) or (e,)))
                    match, rest = exc.split(lambda e: issubclass(e.__class__, exceptions))
                    if match:
                        return
            # exceptions = tuple(s for e in exceptions for s in (get_args(e) or (e,)))
            if issubclass(exc.__class__, exceptions):
                return
        raise AssertionError(f'Expected exception: {", ".join(e.__name__ for e in exceptions)}') from None

    @suppress(KeyError)
    def foo(exc):
        raise exc('a')

    foo(KeyError)
    with assert_raises(ValueError):
        foo(ValueError)
    with suppress(KeyError):
        raise KeyError('a')
    with assert_raises(ValueError):
        with suppress(KeyError):
            raise ValueError('a')
    if version_info >= (3, 11):
        with suppress(KeyError):
            raise ExceptionGroup('x', [KeyError('a')])
        with suppress(KeyError, ValueError):
            raise ExceptionGroup('x', [KeyError('a'), ValueError('a')])
        with assert_raises(ExceptionGroup[ValueError]):
            with suppress(KeyError):
                raise ExceptionGroup('x', [KeyError('a'), ValueError('a')])
        with suppress(ExceptionGroup):
            raise ExceptionGroup('x', [KeyError('a')])

    assert dict_diff_new({1: 2, 3: 4, 5: 6}, {1: 2, 8: 9, 5: 7}) == {8: 9, 5: 7}
    assert dict_diff_new({0: {1: 2, 3: 4, 5: 6}}, {0: {1: 2, 8: 9, 5: 7}}) == {0: {8: 9, 5: 7}}
    assert dict_diff_new({0: {1: 2, 3: 4, 5: 6}}, {0: {1: 2, 8: 9, 5: 7}}, recursion=False) == {0: {1: 2, 8: 9, 5: 7}}
