"""
Our wrapper for threading.Thread.

Adds result value, on_finished callbacks (rx. to clean DB connection).
"""

from __future__ import annotations
from sys import version_info as PY
from time import monotonic
from threading import Thread as _Thread, local as _local, Event as _Event
from threading import Lock, RLock, Condition, current_thread   # noqa: F401  (simulate threading import)
import queue
from weakref import WeakKeyDictionary
from typing import Optional, Any, Set, Iterable, Mapping, Callable, TypeVar, TYPE_CHECKING
from typing_extensions import Self, TypeAlias, Generic

from xbmc import Monitor
from const import const

if TYPE_CHECKING:
    from typing_extensions import ClassVar, Type
    from .kotools import ExitBaseExcepion

T = TypeVar('T')

ThreadOnFinished: TypeAlias = Callable[[], None]

# Safe future timestamp (signed 32-bit minus more then one day).
MAX_TIMESTAMP = 2**31 - 100000


class ThreadCanceled(BaseException):
    """Thread method should be canceled. BaseException to avoid `except Exception:` everywhere."""


class local(_local):
    """threading.local wrapper."""


class ThreadSingleLocal(local):
    """Thread wide threading.local data, singleton per thread."""

    _instances: ClassVar[WeakKeyDictionary[_Thread, ThreadSingleLocal]] = WeakKeyDictionary()
    _lock: ClassVar[Lock] = Lock()

    def __new__(cls: type[Self]) -> ThreadSingleLocal:
        """Create a new instance of ThreadLocal, singleton per thread."""
        with ThreadSingleLocal._lock:
            th = current_thread()
            data = cls._instances.get(th)
            if data is None:
                data = super().__new__(cls)
                cls._instances[th] = data
        return data


class Event(_Event):
    """threading.Event wrapper. Honore Kodi exit."""

    def wait(self, timeout: Optional[float] = None, *, monitor: Optional[Monitor] = None) -> bool:
        """Block until the internal flag is true. See: threading.Event."""
        if monitor is None:
            monitor = Monitor()
        end = MAX_TIMESTAMP if timeout is None else monotonic() + timeout
        while (delta := end - monotonic()) > 0 and not monitor.abortRequested():
            if super().wait(min(delta, const.tune.event_step)):
                return True
        return False
        # while not self.is_set() and (delta := end - monotonic()) > 0:
        #     xsleep(delta, cancel_event=self)
        # return self.is_set()


class PriorityQueue(queue.PriorityQueue, Generic[T]):
    """threading.PriorityQueue wrapper, allows preview first item (peek)."""

    def peek(self) -> T | None:
        """Return the first item in the queue without removing it."""
        with self.mutex:
            if self.queue:
                return self.queue[0]

    def remove(self, item: T, /) -> bool:
        """Remove item."""
        with self.mutex:
            try:
                self.queue.remove(item)
            except ValueError:
                return False
        self.task_done()
        return True

    def __contains__(self, item: T, /) -> bool:
        """Return True if item in the queue."""
        with self.mutex:
            return item in self.queue


class Thread(_Thread, Generic[T]):
    """threading.Thread wrapper. Keeps result."""

    if TYPE_CHECKING:
        _target: Callable[..., T] | None
        _args: tuple[Any, ...]
        _kwargs: dict[str, Any]

    def __init_subclass__(cls, /, **kwargs) -> None:
        """Override __init_subclass__ to ensure that run() is overridden."""
        # force override run() to catch return value
        def run(self: Self) -> None:
            try:
                self.result = cls_run(self)
            except Exception:
                from .log_utils import log_exc
                log_exc()
            for cb in self.on_finished:
                cb()

        super().__init_subclass__(**kwargs)
        cls_run = cls.run
        cls.run = run  # type: ignore[method-assign]

    def __init__(self,
                 group: None = None,
                 target: Optional[Callable[..., Any]] = None,
                 name: Optional[str] = None,
                 args: Iterable[Any] = (),
                 kwargs: Optional[Mapping[str, Any]] = None,
                 *,
                 daemon: Optional[bool] = None,
                 on_finished: Optional[ThreadOnFinished] = None,
                 ) -> None:
        super().__init__(group=group, target=target, name=name, args=args, kwargs=kwargs, daemon=daemon)
        if PY < (3, 10):
            if name is None and callable(target):
                self._name = f'{self._name} ({target.__name__})'
        self._local: Optional[local] = None
        self.result: T | None = None
        self.exception: BaseException | None = None
        self.on_finished: Set[ThreadOnFinished] = set()
        if on_finished is not None:
            self.on_finished.add(on_finished)

    # taken from PY (3.8-3.12)
    def run(self) -> T:  # type: ignore[override]
        """
        Method representing the thread's activity.

        You may override this method in a subclass. The standard run() method
        invokes the callable object passed to the object's constructor as the
        target argument, if any, with sequential and keyword arguments taken
        from the args and kwargs arguments, respectively.
        """
        try:
            if self._target is not None:
                return self._target(*self._args, **self._kwargs)
        except ThreadCanceled:
            from .log_utils import fflog
            fflog(f'Thread {self.name} graceful canceled')
        except Exception as exc:
            from .log_utils import fflog, fflog_exc
            fflog(f'Thread {self.name} raises an exception: {exc}')
            self.exception = exc
            if const.debug.log_exception:
                fflog_exc()
            raise
        finally:
            # Avoid a refcycle if the thread is running a function with
            # an argument that has a member that points to the thread.
            del self._target, self._args, self._kwargs

    @property
    def local(self) -> local:
        """Returns threading.local() varaibles as class local instance."""
        if self._local is None:
            self._local = local()
        return self._local


class WeakThread(Thread):
    """Helper thread, abort on script exit, do not count in standard threads."""


if TYPE_CHECKING:
    class Queue(queue.Queue[T], Generic[T]):  # type: ignore  (Subscript for class "Queue" will generate runtime exception)
        """A custom queue subclass that provides a :meth:`clear` method."""
        def clear(self) -> None:
            """Clears all items from the queue."""
else:
    # See: https://stackoverflow.com/a/31892187/9935708
    class Queue(queue.Queue):
        """A custom queue subclass that provides a :meth:`clear` method."""

        def clear(self):
            """Clears all items from the queue."""
            with self.mutex:
                unfinished = self.unfinished_tasks - len(self.queue)
                if unfinished <= 0:
                    if unfinished < 0:
                        raise ValueError('task_done() called too many times')
                    self.all_tasks_done.notify_all()
                self.unfinished_tasks = unfinished
                self.queue.clear()
                self.not_full.notify_all()


def xsleep(interval: float,
           *,
           cancel_event: _Event | None = None,
           ) -> bool:
    """Sleep in safe mode. Exit on Kodi exit or module reload. Return True if timer expired, False if cancelled."""
    from .kotools import KodiMonitor, KodiExit, ReloadExit
    from .log_utils import fflog  # XXX
    xmonitor = KodiMonitor.instance()
    # if xmonitor is None:
    #     return  # Monitor is destroying.
    if cancel_event is not None and cancel_event.is_set():
        # cancel_event.clear()  # clear event if set
        return False
    timer = xmonitor.new_timer(interval, event=cancel_event)
    T = monotonic()
    expired = xmonitor.wait(timer)
    if const.debug.log_xsleep_jitter and (jitter := abs((dt := monotonic() - T) - interval)) >= const.debug.log_xsleep_jitter:
        fflog(f'[KOTOOLS]  xsleep({interval}) {jitter:.3f} mismatch, finished after {dt:.3f} seconds, {timer=} (ev={timer.event.is_set()}),'
              f' {cancel_event=} / {cancel_event and cancel_event.is_set()=}')
    # timer.event.clear()  # clear event after wait
    if xmonitor and (xmonitor.aborting or xmonitor.abortRequested()):
        raise KodiExit()
    if const.debug.autoreload:
        from ..service.reload import ReloadMonitor
        if ReloadMonitor.reloading:
            raise ReloadExit()
    return expired


def xsleep_until_exit(interval: float) -> Optional[Type[ExitBaseExcepion]]:
    try:
        xsleep(interval)
    except ExitBaseExcepion as exc:
        return type(exc)
    return None


class Timer(Thread, Generic[T]):
    """
    Call a function after a specified number of seconds:

    >>> t = Timer(30.0, f, args=None, kwargs=None)
    >>> t.start()
    >>> t.cancel()     # stop the timer's action if it's still waiting

    Modified Python's version. Keep function result.
    """

    def __init__(self, interval: float, function: Callable[..., T], args=None, kwargs=None) -> None:
        super().__init__()
        self.interval = interval
        self.function = function
        self.args = args if args is not None else []
        self.kwargs = kwargs if kwargs is not None else {}
        self.finished = Event()
        self.result: Optional[T] = None

    def cancel(self) -> None:
        """Stop the timer if it hasn't finished yet."""
        self.finished.set()

    def run(self) -> None:
        xsleep(self.interval, cancel_event=self.finished)
        if not self.finished.is_set():
            self.result = self.function(*self.args, **self.kwargs)
        self.finished.set()


if __name__ == '__main__':
    class MT(Thread):
        def run(self):
            loc.__dict__.setdefault('a', 42)
            print(42, id(loc), loc.__dict__)
            return 42

    class A:
        def print44(self, a=1, b=2):
            loc.__dict__.setdefault('a', 44)
            print(f'44: {a=}, {b=}', id(loc), loc.__dict__)
            return 44

    loc = _local()
    t1 = MT()
    t2 = Thread(target=A().print44, args=(1, 2))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    print(t1.name, t2.name)
    print(t1.result, t2.result)
