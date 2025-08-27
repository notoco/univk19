"""Simple timing utilities."""

from __future__ import annotations
import sys
from time import monotonic
from functools import update_wrapper
from inspect import iscoroutinefunction
from typing import Optional, Any, TextIO, ContextManager, Callable, TypeVar
from typing_extensions import Literal, Self, ParamSpec, Protocol, overload
from ...ff.log_utils import fflog as _fflog

P = ParamSpec('P')
T = TypeVar('T')
R = TypeVar('R', covariant=True)


class WithDescrProtocol(Protocol[P, R]):

    @overload
    def __new__(cls, wrapped: Callable[P, R]) -> WithDescrProtocol[P, R]: ...
    @overload
    def __new__(cls, wrapped: Literal[None] = None) -> WithDescrProtocol: ...

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...

    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type, exc_value, traceback): ...

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, exc_type, exc_value, traceback): ...


@overload
def logtime(wrapped: Callable[P, R], /, *, name: Optional[str] = None, file: TextIO = sys.stdout, fflog: bool = True) -> Callable[P, R]: ...


@overload
def logtime(wrapped: Literal[None] = None, /, *, name: Optional[str] = None, file: TextIO = sys.stdout, fflog: bool = True) -> WithDescrProtocol: ...


def logtime(wrapped: Callable[P, R] | None = None, /, *, name: Optional[str] = None, file: TextIO = sys.stdout, fflog: bool = True) -> Any:
    """Print timing log."""

    class LogTiming:

        def __init__(self, *, name: str | None = None, file: TextIO = sys.stdout, fflog: bool = fflog):
            self.name: Optional[str] = name
            self.file: TextIO = file
            self.fflog: bool = fflog
            self.t: float = 0

        def __call__(self, wrapped):
            async def awrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                """Log async call time consumption."""
                t = monotonic()
                try:
                    result = await wrapped(*args, **kwargs)
                finally:
                    t = monotonic() - t
                    self.log(t, f'async call {wrapped.__qualname__}()')
                return result

            def swrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                """Log call time consumption."""
                t = monotonic()
                result = wrapped(*args, **kwargs)
                t = monotonic() - t
                self.log(t, f'call {wrapped.__qualname__}()')
                return result

            if iscoroutinefunction(wrapped):
                wrapper = awrapper
            else:
                wrapper = swrapper
            update_wrapper(wrapper, wrapped)
            return wrapper

        def __enter__(self):
            self.t = monotonic()
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            t = monotonic() - self.t
            self.log(t, 'with statement')

        async def __aenter__(self):
            self.t = monotonic()
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):
            t = monotonic() - self.t
            self.log(t, 'async with statement')

        def log(self, t, funcname):
            if self.name is not None:
                funcname = self.name
            if self.fflog:
                _fflog(f'Time of {funcname} is {t:.3f}')
            else:
                print(f'Time of {funcname} is {t:.3f}', file=self.file)

    obj = LogTiming(name=name, file=file)
    if wrapped is None:   # with statement or decorator with arguments
        return obj
    return obj(wrapped)   # decorator without arguments
