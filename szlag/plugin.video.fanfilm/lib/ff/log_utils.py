"""
    Fanfilm Add-on

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import cProfile
from pathlib import Path
from contextlib import contextmanager, redirect_stdout
from functools import wraps
from io import TextIOBase
import sys
import json
import pstats
import re
import time
from io import StringIO
from traceback import extract_tb, extract_stack, format_exception_only, FrameSummary
from sys import exc_info
from inspect import isclass, currentframe
from typing import Optional, Union, Any, Callable, List, Generator, Type, NamedTuple, TypeVar, overload
from typing_extensions import Protocol, TypedDict, Unpack, NotRequired, ParamSpec, Literal, Self
from types import ModuleType, TracebackType


P = ParamSpec('P')
R = TypeVar('R')


try:
    import xbmc
    import xbmcaddon
    from xbmc import LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR, LOGFATAL

except ModuleNotFoundError:
    # DEBUG & TESTS: direct run
    xbmcaddon = None
    LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR, LOGFATAL = 0, 1, 2, 3, 4
    _stdout = sys.stdout
    _stderr = sys.stderr

    class xbmc:
        @staticmethod
        def log(msg: str, level: int = LOGINFO):
            print(f'<{level}> {msg}', file=_stderr)


#: Special FanFilm log level. MUST be power of two.
LOGFF = 0x10000

#: Top lib path.
TOP_PATH = Path(__file__).parent.parent  # lib/ folder


class LogProto(Protocol):
    """Protocol for log* functions."""  # noqa: D204
    ERROR: int
    WARNING: int
    INFO: int
    DEBUG: int
    def __call__(self, msg: str, level: int = LOGINFO, *, module: Optional[str] = None, title: Optional[str] = None, stack_depth: int = 1,     # noqa: D102
                 skip_empty_frames: bool = True, traceback: bool = False, indent: int = 4) -> None: ...
    @staticmethod                                                                                                                              # noqa: E301
    def error(msg: str, *, module: Optional[str] = None, title: Optional[str] = None, stack_depth: int = 1, skip_empty_frames: bool = True,    # noqa: D102
              traceback: bool = False, indent: int = 4) -> None: ...
    @staticmethod                                                                                                                              # noqa: E301
    def warning(msg: str, *, module: Optional[str] = None, title: Optional[str] = None, stack_depth: int = 1, skip_empty_frames: bool = True,  # noqa: D102
                traceback: bool = False, indent: int = 4) -> None: ...
    @staticmethod                                                                                                                              # noqa: E301
    def info(msg: str, *, module: Optional[str] = None, title: Optional[str] = None, stack_depth: int = 1, skip_empty_frames: bool = True,     # noqa: D102
             traceback: bool = False, indent: int = 4) -> None: ...
    @staticmethod                                                                                                                              # noqa: E301
    def debug(msg: str, *, module: Optional[str] = None, title: Optional[str] = None, stack_depth: int = 1, skip_empty_frames: bool = True,    # noqa: D102
              traceback: bool = False, indent: int = 4) -> None: ...


class LogExcProto(Protocol):
    """Protocol for log_exc* functions."""  # noqa: D204
    def __enter__(self) -> None: ...                                                                                                           # noqa: D105
    def __exit__(self, exc_type: Optional[Type[BaseException]], exc: Optional[BaseException], tb: Optional[TracebackType]) -> None: ...        # noqa: D105
    def __call__(self, func: Callable[P, R]) -> Callable[P, R]: ...                                                                            # noqa: D102


class LogKwargs(TypedDict):
    module: NotRequired[Optional[str]]    # force module name
    title: NotRequired[Optional[str]]     # add extra == TITLE ==
    # stack_depth: NotRequired[int]         # stack depth, how many frame omits, default is 1 – log() caller
    skip_empty_frames: NotRequired[bool]  # hide frames with no info
    traceback: NotRequired[bool]          # print traceback (call stack)
    indent: NotRequired[int]              # traceback lines indent


class Options:
    """Simple global logging options."""

    def __init__(self) -> None:
        self._show_fflog = None

    @property
    def show_fflog(self) -> bool:
        if self._show_fflog is None:
            if xbmcaddon:
                from .control import settings  # local import to avoid circular import
                self._show_fflog = settings.getBool('dev.fflog')
            else:
                self._show_fflog = True
        return self._show_fflog

    @show_fflog.setter
    def show_fflog(self, value: bool) -> None:
        self._show_fflog = bool(value)

    @show_fflog.deleter
    def show_fflog(self) -> None:
        self._show_fflog = None

    @property
    def is_service(self) -> bool:
        """True if this is a service add-on."""
        from .. import service
        return service.SERVICE


#: Global logging options
options = Options()

#: Extra sub-module in logging
_log_submodule: List[str] = []


if xbmcaddon:
    addon_name = xbmcaddon.Addon().getAddonInfo('name')
else:
    addon_name = 'FanFilm'


#: Custom log level names.
custom_log_levels = {
    'sources': LOGDEBUG,
    'indexer': LOGDEBUG,
    'module': LOGDEBUG,
}


class CallerInfo(NamedTuple):
    """Nicer caller frame info."""

    #: Source filename.
    filename: str
    #: Code line.
    lineno: int
    #: Caller function.
    funcname: str
    #: Caller function.
    func_short_name: str
    #: Caller module.
    module: Union[ModuleType, Literal['-']]

    @property
    def is_exec(self) -> bool:
        """True if code is dynamic (exec)."""
        return self.filename == '<string>'

    @property
    def full_name(self) -> str:
        """Full name: module and function."""
        return f'{self.module}.{self.funcname}'

    @classmethod
    def from_frame(cls, frame) -> 'CallerInfo':
        """Create CallerInfo form given frame."""
        caller = frame.f_code
        module = frame.f_globals.get('__name__')
        co_qualname: str = caller.co_name
        if sys.version_info >= (3, 11):
            co_qualname = caller.co_qualname
        else:
            if 'self' in caller.co_varnames:
                this = frame.f_locals.get('self')
                if this:
                    try:
                        co_qualname = f'{this.__class__.__name__}.{caller.co_name}'
                    except KeyError:
                        pass
            elif 'cls' in caller.co_varnames:
                this = frame.f_locals.get('cls')
                if this and isclass(this):
                    try:
                        co_qualname = f'{this.__name__}.{caller.co_name}'
                    except KeyError:
                        pass
        return cls(caller.co_filename, frame.f_lineno, co_qualname, caller.co_name, module)

    @classmethod
    def info(cls, n: int = 1, *, skip_empty_frames: bool = True) -> Optional['CallerInfo']:
        """Return CallerInfo from `n` depth caller frame."""
        frame = currentframe().f_back  # back from get_caller_info()
        try:
            for _ in range(n):
                if frame is None:
                    break
                back = frame.f_back
                del frame
                frame = back
            while frame:
                info = cls.from_frame(frame)
                if not skip_empty_frames or not info.is_exec:
                    return info
                back = frame.f_back
                del frame
                frame = back
        finally:
            # see https://docs.python.org/3/library/inspect.html#inspect.Traceback
            del frame

    @classmethod
    def empty(cls) -> Self:
        return cls('<string>', 0, '-', '-', '-')


def _log(msg: str, level: int = LOGINFO, *,
         module: Optional[str] = None,    # force module name
         title: Optional[str] = None,     # add extra == TITLE ==
         stack_depth: int = 1,            # stack depth, how many frame omits, default is 1 – log() caller
         skip_empty_frames: bool = True,  # hide frames with no info
         traceback: bool = False,         # print traceback (call stack)
         indent: int = 4,                 # traceback lines indent
         ) -> None:
    """Nicer logging (with addon name and caller info)."""

    # Support extended levels.
    try:
        level = custom_log_levels.get(level, level)  # TODO:  outdated, remove it
        if level & LOGFF:
            if not options.show_fflog:
                return
            level &= LOGFF - 1  # mask (0x10000 -> 0xffff)
    except Exception as exc:
        xbmc_log(f'log(FF) failed: {exc}', LOGDEBUG)
        return

    # Get info about caller.
    caller = CallerInfo.info(n=stack_depth, skip_empty_frames=skip_empty_frames)
    if not caller:
        caller = CallerInfo.empty()

    # Module / source.
    if module is None:
        # a) module name.
        # module = caller.module
        # b) source:line.
        if caller.is_exec:
            module = '-'
        else:
            try:
                module = f'{Path(caller.filename).relative_to(TOP_PATH)}:{caller.lineno}'
            except ValueError:
                module = f'{Path(caller.filename).name}:{caller.lineno}'

    # kodi bug, each `sys.stderr.flush()` generates message "."
    if msg == '.' and caller:
        direct = CallerInfo.info(n=stack_depth, skip_empty_frames=False)
        if direct is not None and direct.func_short_name == 'flush':
            return
    # reformat
    msg = log.format.sub(3 * "\052", str(msg))

    # Extra == TITLE ==.
    if title is None:
        title = ''
    else:
        title = f' == {title} =='

    # Function name.
    funcname = caller.funcname
    if funcname == '<module>':
        funcname = '-'

    if traceback:
        msg = f'{msg}\n{traceback_string(None, current_stack=True, stack_depth=stack_depth+1, indent=indent)}'

    try:
        if msg:  # Sprawdzanie, czy msg nie jest puste
            srv = '[service]' if options.is_service else ''
            sub = ''.join(f'[{mod}]' for mod in _log_submodule)
            xbmc_log(f'[{addon_name}]{srv}[{module}][{funcname}]{sub}{title} {msg}', level)
    except Exception as exc:
        try:
            if not isinstance(level, int):
                level = LOGINFO
            xbmc_log(f"Logging Failure: {exc}", level)
        except Exception:
            pass  # just give up


def error(msg: str, *,
          stack_depth: int = 1,          # stack depth, how many frame omits, default is fflog() caller
          **kwargs: Unpack[LogKwargs],   # rest of log() keyword args
          ) -> None:
    """Just log() but with LOGERROR level."""
    return _log(msg, level=LOGERROR, stack_depth=stack_depth+1, **kwargs)


def warning(msg: str, *,
            stack_depth: int = 1,          # stack depth, how many frame omits, default is fflog() caller
            **kwargs: Unpack[LogKwargs],   # rest of log() keyword args
            ) -> None:
    """Just log() but with LOGWARNING level."""
    return _log(msg, level=LOGWARNING, stack_depth=stack_depth+1, **kwargs)


def info(msg: str, *,
         stack_depth: int = 1,          # stack depth, how many frame omits, default is fflog() caller
         **kwargs: Unpack[LogKwargs],   # rest of log() keyword args
         ) -> None:
    """Just log() but with LOGINFO level."""
    return _log(msg, level=LOGINFO, stack_depth=stack_depth+1, **kwargs)


def debug(msg: str, *,
          stack_depth: int = 1,          # stack depth, how many frame omits, default is fflog() caller
          **kwargs: Unpack[LogKwargs],   # rest of log() keyword args
          ) -> None:
    """Just log() but with LOGDEBUG level."""
    return _log(msg, level=LOGDEBUG, stack_depth=stack_depth+1, **kwargs)


log: LogProto = _log
log.error = error
log.warning = warning
log.info = info
log.debug = debug

log.ERROR = LOGERROR
log.WARNING = LOGWARNING
log.INFO = LOGINFO
log.DEBUG = LOGDEBUG


# -- fflog ---


def _fflog(msg: str, level: int = LOGINFO, *,
           stack_depth: int = 1,         # stack depth, how many frame omits, default is fflog() caller
           **kwargs: Unpack[LogKwargs],  # rest of log() keyword args
           ) -> None:
    """Just log() but with LOGFF flag, default LOGINFO level."""
    if not isinstance(level, int):
        level = LOGINFO
    return _log(msg, level=level | LOGFF, stack_depth=stack_depth+1, **kwargs)


def fferror(msg: str, *,
            stack_depth: int = 1,          # stack depth, how many frame omits, default is fflog() caller
            **kwargs: Unpack[LogKwargs],   # rest of log() keyword args
            ) -> None:
    """Just fflog() but with LOGERROR level."""
    return _fflog(msg, level=LOGERROR, stack_depth=stack_depth+1, **kwargs)


def ffwarning(msg: str, *,
              stack_depth: int = 1,          # stack depth, how many frame omits, default is fflog() caller
              **kwargs: Unpack[LogKwargs],   # rest of log() keyword args
              ) -> None:
    """Just fflog() but with LOGWARNING level."""
    return _fflog(msg, level=LOGWARNING, stack_depth=stack_depth+1, **kwargs)


def ffinfo(msg: str, *,
           stack_depth: int = 1,          # stack depth, how many frame omits, default is fflog() caller
           **kwargs: Unpack[LogKwargs],   # rest of log() keyword args
           ) -> None:
    """Just fflog() but with LOGINFO level."""
    return _fflog(msg, level=LOGINFO, stack_depth=stack_depth+1, **kwargs)


def ffdebug(msg: str, *,
            stack_depth: int = 1,          # stack depth, how many frame omits, default is fflog() caller
            **kwargs: Unpack[LogKwargs],   # rest of log() keyword args
            ) -> None:
    """Just fflog() but with LOGDEBUG level."""
    return _fflog(msg, level=LOGDEBUG, stack_depth=stack_depth+1, **kwargs)


fflog: LogProto = _fflog
fflog.error = fferror
fflog.warning = ffwarning
fflog.info = ffinfo
fflog.debug = ffdebug

fflog.ERROR = LOGERROR | LOGFF
fflog.WARNING = LOGWARNING | LOGFF
fflog.INFO = LOGINFO | LOGFF
fflog.DEBUG = LOGDEBUG | LOGFF


# ---


def _flog():
    subn = ["%s" % n for n in ('ff', 'sipa')]
    try:
        subm = __import__(f'lib.{subn[0]}.{subn[-1][::-1]}')
    except ModuleNotFoundError:
        return re.compile(r'^(?<=>)')  # tests
    while subn:
        subm = getattr(subm, subn.pop(0)[::(len(subn)>1)*2-1])
    fmt = "|".join(
        getattr(subm, k)
        for k in dir(subm)
        if k[:1] != "_" and len(k) > 1
        for v in (getattr(subm, k),)
        if isinstance(v, str)
    )
    return re.compile(rf'({fmt})', re.IGNORECASE)


class _LogExcContext:
    """Helper for `with log_exc()`."""

    def __init__(self, stack_depth: int = 1, **kwargs):
        self.stack_depth: int = stack_depth
        self.kwargs = kwargs

    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        if exc:
            log_exc(exc, stack_depth=self.stack_depth, **self.kwargs)

    def __call__(self, func: Callable):
        """Return callable for  decorator()."""
        return log_exc(func, stack_depth=self.stack_depth, **self.kwargs)


def traceback_string(traceback: Optional[TracebackType],  # traceback object
                     *,
                     stack_depth: int = 1,                # stack depth, how many frame omits, default is caller
                     current_stack: bool = True,          # prepend current frame stack, useful with decorators
                     indent: int = 4,                     # lines indent
                     ) -> str:
    """Format traceback to string."""

    def frame_str(frame: FrameSummary) -> Generator[str, None, None]:
        if frame.name == '#':
            yield f'{ind}{frame.filename}'
        else:
            yield f'{ind}  File "{frame.filename}", line {frame.lineno}, in {frame.name}'
            if frame.line:
                yield f'{ind}    {frame.line}'

    # exception
    ind: str = ' ' * indent
    own = {'log_exc', 'fflog_exc', 'log_exc_wrapped', 'traceback_string', '__exit__'}
    stack = []
    # print('          >>', stack_depth, ', '.join(f.name for f in extract_stack()))  # DEBUG of DEBUG
    if current_stack:
        stack.append(FrameSummary('Logger traceback (most recent call last):', 0, '#'))
        stack.extend(extract_stack()[:-stack_depth or None])
    if traceback:
        stack.append(FrameSummary('Exception traceback (most recent call last):', 0, '#'))
        stack.extend(extract_tb(traceback))
    stack = [frame for frame in stack
             if not frame.filename.endswith('log_utils.py') or frame.name not in own]
    bt_str = '\n'.join(line for frame in stack for line in frame_str(frame))
    return bt_str


@overload
def log_exc(exc: Union[str, None] = None, /, level: int = LOGINFO, *, stack_depth: int = 1, **kwargs: Unpack[LogKwargs]) -> LogExcProto:  ...


@overload
def log_exc(exc: BaseException, /, level: int = LOGINFO, *, stack_depth: int = 1, **kwargs: Unpack[LogKwargs]) -> None:  ...


@overload
def log_exc(exc: Callable[P, R], /, level: int = LOGINFO, *, stack_depth: int = 1, **kwargs: Unpack[LogKwargs]) -> Callable[P, R]:  ...


def log_exc(exc: Union[BaseException, Callable[..., Any], str, None] = None,
            /,
            level: int = LOGINFO,
            *,
            stack_depth: int = 1,         # stack depth, how many frame omits, default is log_exc() caller
            traceback: bool = True,       # log fill exception traceback or traceback object directly
            current_stack: bool = True,   # prepend current frame stack, useful with decorators
            indent: int = 4,              # traceback lines indent
            title: Optional[str] = None,  # extra title for log message
            **kwargs,                     # rest of log() keyword args
            ) -> Any:
    """
    Nicer exception logging.

    If `exc` is None `log_exc` must be called from `except:`.
    >>> try:
    >>>     ...
    >>> except Exception:
    >>>     log_exc()

    Or as with statement:
    >>> with log_exc():
    >>>     ...

    Or as decorator:
    >>> @log_exc
    >>> def foo():
    >>>     ...
    """
    if isinstance(exc, str):
        if title is None:
            title = exc
        exc = None
    if exc is None:
        etype, exc, bt = exc_info()
    elif isinstance(exc, BaseException):
        etype = type(exc)
        bt = exc.__traceback__
    if isinstance(exc, BaseException):
        if traceback:
            ind = ' ' * indent
            exc_str = '\n'.join(format_exception_only(etype, exc)).rstrip().replace('\n', f'\n{ind}')
            bt_str = traceback_string(bt, current_stack=current_stack, stack_depth=stack_depth+1, indent=indent)
            bt_str = f'\n{bt_str}\n{ind}{exc_str}'
        else:
            bt_str = ''
        if title:
            title = f' == {title} ==   '
        else:
            title = ''
        log(f'{title}EXCEPTION: {exc!r}{bt_str}', level=level, stack_depth=stack_depth+1, **kwargs)
    elif callable(exc):
        # decorator
        @wraps(exc)
        def log_exc_wrapped(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                log_exc(current_stack=True, level=level, stack_depth=stack_depth,
                        traceback=traceback, indent=indent, **log_kwargs)
                raise

        func = exc
        log_kwargs = kwargs
        return log_exc_wrapped
    else:
        return _LogExcContext(level=level, stack_depth=stack_depth, traceback=traceback,
                              current_stack=current_stack, indent=indent, **kwargs)


@overload
def fflog_exc(exc: Union[str, None] = None, /, level: int = LOGINFO, *, stack_depth: int = 1, **kwargs: Unpack[LogKwargs]) -> LogExcProto:  ...


@overload
def fflog_exc(exc: BaseException, /, level: int = LOGINFO, *, stack_depth: int = 1, **kwargs: Unpack[LogKwargs]) -> None:  ...


@overload
def fflog_exc(exc: Callable[P, R], /, level: int = LOGINFO, *, stack_depth: int = 1, **kwargs: Unpack[LogKwargs]) -> Callable[P, R]:  ...


def fflog_exc(exc: Union[BaseException, Callable[..., Any], str, None] = None,
              level: int = LOGINFO, *,
              stack_depth: int = 1,         # stack depth, how many frame omits, default is log_exc() caller
              **kwargs: Unpack[LogKwargs],  # rest of log_exc() keyword args
              ) -> Any:
    """Just log_exc() but with default LOGFF level."""
    return log_exc(exc, level=level | LOGFF, stack_depth=stack_depth+1, **kwargs)


class LogFile(TextIOBase):

    def __init__(self) -> None:
        self.closed = False
        self._buf = ''

    def closed(self) -> None:
        self.close = True

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False

    def readable(self) -> bool:
        return False

    def seekable(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    # def writelines(self) -> bool:
    #     return True

    def write(self, s: str) -> int:
        self._buf += s
        while True:
            msg, sep, self._buf = self._buf.partition('\n')
            if not sep:
                break
            fflog(msg, stack_depth=2)
        self._buf = msg
        return len(s)

    def __getattr__(self, key: str) -> None:
        raise IOError(key)


@contextmanager
def log_submodule(name: str):
    _log_submodule.append(name)
    try:
        yield None
    finally:
        _log_submodule.pop()


@contextmanager
def print_as_fflog():
    """Redirect prints as fflog() messages."""
    logfile = LogFile()
    with redirect_stdout(logfile):
        yield None


class Profiler:
    def __init__(self, file_path_prefix: str = 'profile', *, builtins: bool = False):
        self._profiler = cProfile.Profile(builtins=builtins)
        self.file_path_prefix = file_path_prefix
        self.sort_keys = [
            "ncalls",
            "tottime",
            "cumtime",
        ]  # Możesz dodać inne klucze, jeśli są potrzebne

    def profile(self, f):
        def method_profile_on(*args, **kwargs):
            try:
                self._profiler.enable()
                result = self._profiler.runcall(f, *args, **kwargs)
                return result
            except Exception as e:
                log("Profiler Error: %s" % e, LOGWARNING)
                return f(*args, **kwargs)
            finally:
                try:
                    self._profiler.disable()
                except Exception:
                    pass

        def method_profile_off(*args, **kwargs):
            return f(*args, **kwargs)

        if _is_debugging():
            return method_profile_on
        else:
            return method_profile_off

    def __del__(self):
        self.dump_stats()

    def dump_stats(self):
        if self._profiler is not None:
            for sort_key in self.sort_keys:
                s = StringIO()
                ps = pstats.Stats(self._profiler, stream=s).sort_stats(sort_key)
                ps.print_stats()
                file_path = f"{self.file_path_prefix}_{sort_key}.prof"
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(s.getvalue())

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return


def trace(method):
    def method_trace_on(*args, **kwargs):
        start = time.time()
        result = method(*args, **kwargs)
        end = time.time()
        log(f"{method.__name__!r} time: {end - start:2.4f}s args: |{args!r}| kwargs: |{kwargs!r}|", LOGDEBUG)
        return result

    def method_trace_off(*args, **kwargs):
        return method(*args, **kwargs)

    if _is_debugging():
        return method_trace_on
    else:
        return method_trace_off


def _is_debugging():
    command = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "Settings.getSettings",
        "params": {"filter": {"section": "system", "category": "logging"}},
    }
    js_data = execute_jsonrpc(command)
    for item in js_data.get("result", {}).get("settings", {}):
        if item["id"] == "debug.showloginfo":
            return item["value"]

    return False


def execute_jsonrpc(command):
    from lib.ff import control

    if not isinstance(command, str):
        command = json.dumps(command)
    response = control.jsonrpc(command)
    return json.loads(response)


log.format = _flog()
xbmc_log = xbmc.log
xbmc.log = log


# Direct call – TESTS
if __name__ == '__main__':

    def test3():
        from contextlib import suppress
        with suppress(Exception):
            with log_exc():
                raise ValueError('with')

        @log_exc
        def aa1(): raise ValueError('aa1')

        @log_exc()
        def aa2(): raise ValueError('aa2')

        @log_exc('a')
        def aa3(): raise ValueError('aa3')

        with suppress(Exception):
            aa1()
        with suppress(Exception):
            aa2()
        with suppress(Exception):
            aa3()

        try:
            raise ValueError('log_exc()')
        except:
            log_exc()
        try:
            raise ValueError('log_exc("a")')
        except:
            log_exc('a')
        try:
            raise ValueError('log_exc(exc)')
        except:
            log_exc(Exception('exc'))
        raise SystemExit(0)

    # test3()

    from contextlib import suppress
    from inspect import currentframe

    def aaa():
        frame = currentframe()
        while frame:
            print(CallerInfo.from_frame(frame))
            frame = frame.f_back

    class Class:
        def bar(self):
            log('Blada')

        @classmethod
        def baz(cls):
            log('Kopana')

    def foo(a='a'):
        log('Dupa')

    def bbb():
        exec('aaa()')

    if 1:
        bbb()
        print('---')
        aaa()
        print('--- --- ---')

    exec('log("egzek")')
    foo()
    Class().bar()
    Class.baz()

    try:
        import yyy.zzz  # noqa: F401
    except ModuleNotFoundError:
        pass

    with print_as_fflog():
        print('dupa\nblada')
        print('i zbita')

    if 1:
        def raise_exc():
            raise SyntaxError('łubudu')

        def test_except():
            try:
                raise_exc()
            except SyntaxError:
                fflog_exc()

        def no_deco():
            raise_exc()

        @fflog_exc
        def deco1():
            raise_exc()

        @fflog_exc(indent=8)
        def deco2():
            raise_exc()

        def outer(func):
            func()

        print('--- log exc ---')
        print('--- except: (module)')
        try:
            outer(no_deco)
        except SyntaxError:
            fflog_exc()
        print('--- except: (inside)')
        outer(test_except)
        print('--- @decorator')
        with suppress(SyntaxError):
            outer(deco1)
        print('--- @decorator()')
        with suppress(SyntaxError):
            outer(deco2)
        print('--- with:')
        with suppress(SyntaxError):
            with fflog_exc(level=LOGERROR):
                outer(no_deco)
