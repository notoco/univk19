"""Simple Kodi tools."""

from __future__ import annotations
from time import monotonic
from threading import Event, Thread, Lock, enumerate as threading_enumerate, main_thread
from queue import Empty, Queue
from contextlib import contextmanager
from pathlib import Path
import atexit
import json
from types import TracebackType
from typing import Optional, Union, Mapping, Type, TypeVar, Callable, ClassVar, Generic, TYPE_CHECKING
from typing_extensions import TypedDict, Unpack, NotRequired, Self, Literal, Protocol, TypeAlias
from attrs import define, field, Attribute
from .threads import WeakThread, xsleep
from .threads import xsleep_until_exit  # noqa: F401
from .log_utils import fflog, fflog_exc
from ..info import exec_id
if TYPE_CHECKING:
    from datetime import datetime
    from typing import Any, List, Dict, Sequence, Iterator
    from .types import JsonData, JsonResult, Params


from xbmc import Monitor as XmbcMonitor, Player as XbmcPlayer, PlayList as XbmcPlayList, PLAYLIST_VIDEO
from xbmc import executeJSONRPC
import xbmcaddon
import xbmcgui

from const import const
from ..service.exc import KodiExit, ReloadExit, ExitBaseExcepion


T = TypeVar('T')
KodiLibraryType = Literal['video', 'music']
KodiRpcAction = Literal['notify', 'request', 'response']

#: System platform.
_platform: Optional[str] = None
#: Kodi startup timestemp
_startup: 'Optional[datetime]' = None


#: Monitor.onNotification callback type.
OnNotification: TypeAlias = Callable[[str, str, str], None]


class MonitorProtocol(Protocol):
    """Protocol for objects that can receive Kodi notifications."""

    def onNotification(self, sender: str, method: str, data: str) -> None:
        """Notification, called by Kodi."""


class Monitor:
    """Pseudo Kodi monitor base class. Used in KodiMonitor.add_monitor()."""

    def add(self) -> None:
        """Add monitor to KodiMonitor."""
        if xmonitor := KodiMonitor.instance():
            xmonitor.add_monitor(self)
        else:
            fflog.warning(f'[KOTOOLS]  KodiMonitor instance is not created [{exec_id()}]')

    def remove(self) -> None:
        """Remove monitor from KodiMonitor."""
        if xmonitor := KodiMonitor.instance():
            xmonitor.remove_monitor(self)

    def __enter__(self) -> Self:
        """Context manager to add monitor to KodiMonitor."""
        if xmonitor := KodiMonitor.instance():
            xmonitor.add_monitor(self)
        else:
            fflog.warning(f'[KOTOOLS]  KodiMonitor instance is not created [{exec_id()}]')
        return self

    def __exit__(self, exc_type: Type[BaseException], exc_inst: Optional[BaseException], exc_tb: Optional[TracebackType]) -> None:
        """Context manager to remove monitor from KodiMonitor."""
        if xmonitor := KodiMonitor.instance():
            xmonitor.remove_monitor(self)

    def onNotification(self, sender: str, method: str, data: str) -> None:
        """Notification, called by Kodi."""


@define(kw_only=True, order=True)
class XTimer:
    """Timer for Kodi. Use it to run code after some time."""

    #: monotonic() value when timer expires.
    expires: float
    #: interval in seconds.
    interval: float = field(default=0, eq=False)
    #: Event to set when timer expires.
    event: Event = field(factory=Event, repr=False, eq=False)
    #: True if timer is expired, False is aborted.
    expired: bool = field(default=False, init=False, repr=False, eq=False)


class KodiMonitor(XmbcMonitor):
    """Kodi monitor for safe sleep and exit."""

    #: Global Kodi monitor instance.
    _instance: ClassVar[KodiMonitor | None] = None
    #: Event for create singleton instance.
    _instance_lock: ClassVar[Lock] = Lock()

    def __init__(self) -> None:
        from .threads import PriorityQueue
        super().__init__()
        self._loop_event = Event()
        self._timers: PriorityQueue[XTimer] = PriorityQueue()
        self._exiting: bool = False
        self._aborting: bool = False
        self._sleep_thread: Thread | None = None
        self._monitor_thread: Thread | None = None
        self._monitors: list[MonitorProtocol] = []
        self._watchers: set[OnNotification] = set()
        self._lock = Lock()  # Lock for thread safety, if needed

    @classmethod
    def instance(cls, *, start: bool = True) -> KodiMonitor:
        """Create new Kodi monitor instance."""
        def new(caller: str):
            iid = exec_id()
            fflog(f'[KOTOOLS]  KodiMonitor  CREATE [{iid}] from [{caller}]')
            aborting = exiting = None
            try:
                instance = cls()
                created.put_nowait(instance)
                while not instance.aborting and not instance._aborting and not instance.abortRequested():
                    if instance.waitForAbort(const.tune.sleep_step):
                        break
                aborting, exiting = instance._aborting, instance._exiting
            except Exception:
                fflog_exc()
            finally:
                cls._instance = None
                fflog(f'[KOTOOLS]  KodiMonitor  thread EXIT [{iid}] (instance {aborting=}, {exiting=})')

        with KodiMonitor._instance_lock:
            if cls._instance is None:
                created = Queue()
                th = WeakThread(target=new, name='KodiMonitor.monitor', kwargs={'caller': exec_id()})
                th.start()
                cls._instance = created.get()
                assert cls._instance is not None, 'KodiMonitor instance is not created!'
                cls._instance._monitor_thread = th
                if start:
                    cls._instance.start()
            return cls._instance

    @classmethod
    def destroy(cls) -> None:
        """Destroy Kodi monitor instance."""
        fflog(f'[KOTOOLS]  KodiMonitor  goiing to destroy  {cls._instance!r} [{exec_id()}]')
        with KodiMonitor._instance_lock:
            if cls._instance is not None:
                fflog('[KOTOOLS]  KodiMonitor  destroying')
                cls._instance.stop()
                # cls._instance = None
                fflog('[KOTOOLS]  KodiMonitor  DESTROYED')

    @property
    def aborting(self) -> bool:
        """Return True if Kodi is quiting (abort has been requested)."""
        return self._aborting

    def _clear_timers(self) -> None:
        """Clear all timers."""
        while not self._timers.empty():
            try:
                timer = self._timers.get_nowait()
            except Empty:
                break
            timer.event.set()

    def onNotification(self, sender: str, method: str, data: str) -> None:
        """Notification, called by Kodi."""
        fflog(f'[KOTOOLS]  Kodi x-monitor received notification: {sender=}, {method=}, {data=}  |M|={len(self._monitors)},'  # XXX
              f' |W|={len(self._watchers)}, |T|={self._timers.qsize()}, abort={self.abortRequested()} [{exec_id()}]')             # XXX
        from .control import plugin_id
        for monitor in self._monitors:
            try:
                monitor.onNotification(sender, method, data)
            except Exception as exc:
                fflog(f'[KOTOOLS]  Error in observer {monitor!r} on notification({sender=}, {method=}): {exc}')
                fflog_exc()
        for watcher in self._watchers:
            try:
                watcher(sender, method, data)
            except Exception as exc:
                fflog(f'[KOTOOLS]  Error in watcher {watcher!r} on notification({sender=}, {method=}): {exc}')
                fflog_exc()
        if sender == 'xbmc' and method == 'System.OnQuit':
            # Kodi is exiting, cancel all timers and set abort event.
            act_threads = ', '.join(str(th) for th in threading_enumerate())  # LOG
            fflog(f'[KOTOOLS]  System.OnQuit: {act_threads}')
            self._aborting = True
            self._exiting = True
            self._clear_timers()
            self._loop_event.set()
            kodi_abort_event.set()
        elif sender == plugin_id and method == 'ServiceUpdate':
            from ..service.client import service_client
            try:
                msg = json.loads(data)
            except Exception as exc:
                fflog.error(f'JSONRPC message failed: {exc}, {sender=}, {method=}\n  {data!r}')
            else:
                fflog(f'Service updated: {msg}')
                if isinstance(msg, dict) and (url := msg.get('url')):
                    service_client._url = url

    def add_monitor(self, monitor: MonitorProtocol) -> None:
        """Add monitor for Kodi notifications."""
        fflog(f'[KOTOOLS]  Add monitor {monitor!r}')
        with self._lock:
            for m in self._monitors:
                if m is monitor:
                    return
            self._monitors.append(monitor)

    def remove_monitor(self, monitor: MonitorProtocol) -> None:
        """Remove monitor for Kodi notifications."""
        fflog(f'[KOTOOLS]  Remove monitor {monitor!r}')
        with self._lock:
            for i, m in enumerate(self._monitors):
                if m is monitor:
                    del self._monitors[i]
                    return

    @contextmanager
    def with_monitor(self, monitor: MonitorProtocol) -> Iterator[Self]:
        """Context manager to add monitor for Kodi notifications."""
        self.add_monitor(monitor)
        try:
            yield self
        finally:
            self.remove_monitor(monitor)

    def add_watcher(self, watcher: OnNotification) -> None:
        """Add notification watcher."""
        with self._lock:
            self._watchers.add(watcher)

    def remove_watcher(self, watcher: OnNotification) -> None:
        """Remove notification watcher."""
        with self._lock:
            self._watchers.discard(watcher)

    @contextmanager
    def with_watcher(self, watcher: OnNotification) -> Iterator[Self]:
        """Context manager to add watcher for Kodi notifications."""
        self.add_watcher(watcher)
        try:
            yield self
        finally:
            self.remove_watcher(watcher)

    @contextmanager
    def abort_context(self,
                      on_abort: Callable[[], Any] | None,
                      args: Sequence[Any] | None = None,
                      kwargs: Mapping[str, Any] | None = None,
                      *,
                      event: Event | None = None
                      ) -> Iterator[Event]:
        """
        Context manager to work with aborting.

        Example (3 in 1):
        >>> def on_abort_function():
        >>>     print("Kodi is aborting, do something here...")
        >>> with KodiMonitor.instance().abort_context(on_abort=on_abort_function) as event:
        >>>     if event.wait(timeout=10):
        >>>          print("Kodi is aborting, do something here...")
        >>>     if event.is_set():
        >>>          print("Kodi is aborting, do something here...")
        """

        def look_for_abort(sender: str, method: str, data: str) -> None:
            if sender == 'xmbc' and method == 'System.OnQuit':
                assert event is not None
                event.set()
                if on_abort:
                    aa = () if args is None else args
                    kw = {} if kwargs is None else kwargs
                    on_abort(*aa, **kw)

        if event is None:
            event = Event()
        with self.with_watcher(look_for_abort):
            yield event

    def reload(self) -> None:
        """Set reload event and cancel all timers."""
        self._clear_timers()
        fflog(f'[KOTOOLS]  Kodi monitor received reload, exiting... {self._loop_event.is_set()}')
        self._loop_event.set()
        reload_event.set()

    def new_timer(self, interval: float, *, event: Optional[Event] = None) -> XTimer:
        """Create new timer."""
        expires = monotonic() + interval
        timer = XTimer(expires=expires, interval=interval, event=event or Event())
        self._timers.put(timer)
        self._loop_event.set()  # wake up monitor if waiting
        return timer

    def remove_timer(self, timer: XTimer) -> bool:
        """Remove timer."""
        if self._timers.remove(timer):
            self._loop_event.set()
            return True
        return False

    def wait(self, timer: XTimer) -> bool:
        """Wait for timer to expire. Return True if timer expired, False if cancelled."""
        timer.event.wait()
        if timer.expired:
            assert timer not in self._timers.queue, f'Timer {timer} is expired but still in queue!'
            return True
        else:
            self.remove_timer(timer)
            return False

    def start(self) -> None:
        """Start Kodi monitor in a separate thread."""
        fflog(f'[KOTOOLS]  KodiMonitor  START LOOP [{exec_id()}]')
        self._aborting = False
        self._sleep_thread = WeakThread(target=self.run, name='KodiMonitor.loop')
        self._sleep_thread.start()

    def stop(self) -> None:
        """Stop Kodi monitor."""
        fflog(f'[KOTOOLS]  KodiMonitor  STOP  sleep={self._sleep_thread}, monitor={self._monitor_thread}')
        if self._sleep_thread:
            self._sleep_thread, thread = None, self._sleep_thread
            self.exit(force=True)
            thread.join()
        if self._monitor_thread:
            self._aborting = True
            self._exiting = True
            self._monitor_thread, thread = None, self._monitor_thread
            thread.join()

    def exit(self, *, force: bool = False) -> None:
        """Exit monitor."""
        self._exiting = True
        if force:
            self._clear_timers()
        self._loop_event.set()

    def run(self) -> None:
        """Run monitor loop."""
        iid = exec_id()
        fflog(f'[KOTOOLS]  KodiMonitor [{iid}] RUN')
        while not self._aborting and not self.abortRequested():
            timer = self._timers.peek()
            self._loop_event.clear()
            if timer is None:
                if self._exiting:
                    break
                # Wait for next timer or Kodi exit.
                self._loop_event.wait()
            else:
                now = monotonic()
                if now >= timer.expires:
                    # Timer expired, remove it and set event.
                    tmr = self._timers.get()
                    if tmr is timer:
                        # was_expired = timer.expired
                        if not timer.event.is_set():
                            timer.expired = True
                            timer.event.set()
                            timer.event.clear()  # clear event if already expired
                        self._timers.task_done()
                    else:
                        fflog.warning(f'[{iid}] Unexpected expired timer: {tmr!r} != {timer!r}')
                        self._timers.put(tmr)  # put back if not the same
                else:
                    # Wait until timer expires or next timer or Kodi exit.
                    timer.expired = not self._loop_event.wait(timer.expires - now)
        aborting, exiting = self._aborting, self._exiting
        self._aborting = True  # force to abort creator thread
        fflog(f'[KOTOOLS]  KodiMonitor [{iid}] exiting...  (instance {aborting=}, {exiting=})')


destroy_xmonitor = KodiMonitor.destroy
"""Destroy the monitor."""


def active_threads() -> List[Thread]:
    """Get list of active threads."""
    try:
        from threading import _DummyThread  # type: ignore[reportAssignmentType]  # confict with fallback class
    except ImportError:
        class _DummyThread:
            pass
    return [th for th in threading_enumerate()
            if isinstance(th, Thread) and type(th) not in (_DummyThread, type(main_thread()), WeakThread)]


def xmonitor_script_finish() -> None:
    """Check the monitor on end of stript."""
    from ..info import exec_id  # XXX
    xmonitor = KodiMonitor._instance
    fflog(f'[KOTOOLS]  KodiMonitor  SCRIPT finishing [{exec_id()}], {xmonitor=}')  # XXX
    if xmonitor is not None:
        threads = active_threads()
        fflog(f'[KOTOOLS]  KodiMonitor  SCRIPT FINISH [{exec_id()}], {len(threads)} threads: {threads}, aborting={xmonitor.aborting}')  # XXX
        if not threads or xmonitor.aborting or xmonitor.abortRequested() or kodi_abort_event.is_set():
            # if threads:
            #     for th in threads:
            #         fflog(f'[KOTOOLS]  KodiMonitor  THREAD {th.name} still running, exiting...')
            #         th.join(timeout=5)
            destroy_xmonitor()


def xmonitor_exit(*, force: bool = False) -> None:
    """Exit Kodi monitor."""
    xmonitor = KodiMonitor.instance()
    if xmonitor is not None:
        xmonitor.exit(force=force)


#: Event for Kodi exit.
kodi_abort_event = Event()
#: Event for module reload.
reload_event = Event()

# Start Kodi monitor in a separate thread.
atexit.register(destroy_xmonitor)


FF_ICON: str = xbmcaddon.Addon().getAddonInfo('icon')

ICONS: Dict[Optional[str], str] = {
    None: FF_ICON,
    '': FF_ICON,
    'INFO': xbmcgui.NOTIFICATION_INFO,
    'WARNING': xbmcgui.NOTIFICATION_WARNING,
    'ERROR': xbmcgui.NOTIFICATION_ERROR,
}


class NotificationOpenArgs(TypedDict):
    interval: NotRequired[Optional[float]]
    delay: NotRequired[Optional[float]]


@define
class Notification:
    """
    Forced GUI notifications.

    Like xbmcgui.Dialog().notification() but keeps visible event another notification occur.
    Differences:
    - `interval` in SECONDS (not milliseconds)
    - it starts hidden, must be opened or shown, you can use `with` statement
    - `heading`, `message` and `icon` could be changed in any time
    - you could add startup `delay`

    `open()` and `show()` are very similar and don't differ on first usage at all.
    Opening rests all settings and shows, then delay works again.

    When `with` statement is used `interval` interval means visible time AFTER statement exit.

    >>> Notification('Header', 'My text').show()
    >>>
    >>> with Notification('Header', 'Progress: 0%', delay=1) as notif:
    >>>    for i, job in enumerate(jobs):
    >>>        notif.message = f'Progress: {100 * i / len(jobs)}%'
    """

    # Dialog heading (title).
    heading: str
    # heading: str = field()
    # Dialog message.
    message: str
    # message: str = field()
    # Icon to use. Default is FanFilm icon.
    icon: Optional[str] = None
    # Time in SECONDS (sic!). Default 5, None or -1 means forever.
    interval: Optional[float] = 5
    # Play notification sound, default True.
    sound: bool = True
    # True if the notification is visible, if not, you must use show().
    visible: bool = False
    # Startup show delay in seconds.
    delay: float = -1  # -1 means auto (zero or almost zero)
    # Show works if True otherwise hidden notification (show is not enabled).
    enabled: bool = True

    # -- private attributes --
    _visible: bool = field(default=False, init=False, repr=False)
    _sound: bool = field(default=False, init=False, repr=False)
    _delay: float = field(default=0, init=False, repr=False)
    _thread: Optional[Thread] = field(default=None, init=False, repr=False)
    # _changed: Event = field(factory=Event, init=False, repr=False)
    _exit: Event = field(factory=Event, init=False, repr=False)
    _finished: Event = field(factory=Event, init=False, repr=False)
    _stack: ClassVar[List[Notification]] = []

    def __attrs_post_init__(self):
        self.icon = ICONS.get(self.icon, FF_ICON)
        self._delay = self.delay
        # self._changed.clear()
        if self.visible:
            if self.delay < 0:
                self.delay = 0.01
            self.show()
        elif self.delay < 0:
            self.delay = 0

    # @heading.validator
    # def _change_heading(self, attr: Attribute, value: str) -> None:
    #     self._changed.set()

    # @message.validator
    # def _change_message(self, attr: Attribute, value: str) -> None:
    #     self._changed.set()

    def _show_loop(self, **kwargs: Unpack[NotificationOpenArgs]) -> None:
        assert self.icon is not None
        self._finished.clear()
        interval = kwargs.get('interval', self.interval)
        delay = kwargs.get('delay', self._delay)
        if delay and delay > 0:
            xsleep(delay, cancel_event=self._exit)
            # self._changed.clear()
            self._delay = 0
        if interval is None or interval < 0:
            end = 2**63  # a lot of interval
        else:
            end = monotonic() + (interval or 5)
        try:
            self._stack.append(self)
            fflog(f'Start {self.heading=}, {interval=}, {delay=}, {self._visible=}')
            while self._visible and (now := monotonic()) < end:
                if self._stack and self._stack[-1] is self:
                    sleep_interval = min(1, end - now)
                    sound, self._sound = self._sound, False
                    # self._changed.clear()
                    # fflog.debug(f'notif {self.heading=}, {interval=}, {delay=}, {sleep_interval=}')
                    xbmcgui.Dialog().notification(self.heading, self.message, self.icon, int(1000 * sleep_interval + 10), sound)
                    self._sound = False
                    xsleep(sleep_interval, cancel_event=self._exit)
                    # xsleep(sleep_interval, cancel_event=self._changed)
                else:  # not on top
                    fflog(f'hidden {self.heading=}, {interval=}, {delay=}')
                    xsleep(min(.2, end - now))
        finally:
            fflog(f'finish {self.heading=}, {interval=}, {delay=}')
            self.visible = False
            self._thread = None
            self._stack.remove(self)
            self._finished.set()

    def show(self, **kwargs: Unpack[NotificationOpenArgs]) -> Self:
        """Shows notification. No delay again."""
        if self.enabled and not self._visible:
            self._exit.clear()
            self._visible = True
            self._sound = self.sound
            self._thread = Thread(target=self._show_loop, kwargs=kwargs)
            self._thread.start()
        return self

    def hide(self) -> Self:
        """Hide notification."""
        if self._visible:
            self._visible = False
            self._exit.set()
            # self._changed.set()
        return self

    def open(self, **kwargs: Unpack[NotificationOpenArgs]) -> Self:
        """Opens notification again: resets settings and shows."""
        if not self.visible:
            self._sound = self.sound
            self._delay = self.delay
            self.show(**kwargs)
        return self

    def close(self) -> Self:
        """Closes notification."""
        self.hide()
        return self

    # def __del__(self) -> None:
    #     self.hide()

    def __enter__(self) -> Notification:
        if self._visible:
            self.hide()
            xsleep(1.1, cancel_event=self._finished)
        self.open(interval=None)
        return self

    def __exit__(self, exc_type: Type[BaseException], exc_inst: Optional[BaseException], exc_tb: Optional[TracebackType]) -> None:
        self.close()


def get_player_item() -> xbmcgui.ListItem | None:
    """Returns current playing Kodi ListItem or current ListItme from playlist."""
    try:
        player = XbmcPlayer()
        if player.isPlaying():
            return player.getPlayingItem()
    except Exception:
        fflog_exc()

    pls = XbmcPlayList(PLAYLIST_VIDEO)
    if (size := pls.size()) > 0 and 0 <= (index := pls.getposition()) < size:
        try:
            return pls[index]
        except Exception:
            fflog_exc()
    # if (size := pls.size()) > 0:
    #     index = pls.getposition()
    #     try:
    #         return pls[index if 0 <= index < size else 0]
    #     except Exception:
    #         fflog_exc()
    return None


def stop_playing() -> None:
    """Stop playing anything."""
    from .control import close_busy_dialog
    XbmcPlayer().stop()
    XbmcPlayList(PLAYLIST_VIDEO).clear()
    close_busy_dialog()


def get_platform() -> str:
    """Get current platform."""
    global _platform
    if _platform is None:
        import platform
        import sys
        _platform = platform.system().lower()
        if _platform == 'linux' and hasattr(sys, 'getandroidapilevel'):
            _platform = 'android'
    return _platform


def kodi_startup_timestamp() -> 'datetime':
    """Return datetime timestamp of kodi launch (in UTC)."""
    import re
    from datetime import datetime, timezone, timedelta
    global _startup
    if _startup is None:
        from xbmcvfs import translatePath
        log_path = Path(translatePath('special://logpath')) / 'kodi.log'
        from xbmc import getInfoLabel
        if log_path.exists():
            from codecs import BOM_UTF8
            from .calendar import fromisoformat
            try:
                with open(log_path, 'rb') as f:
                    data = f.read(128)
                    if data.startswith(BOM_UTF8):
                        data = data[len(BOM_UTF8):]
                    if mch := re.match(rb'[-\d]+[ T][:.\d]+', data):
                        # parse first log timestamp and convert it to UTC.
                        _startup = fromisoformat(mch[0].decode('ascii')).astimezone(timezone.utc)
                        return _startup
            except (OSError, ValueError):
                fflog_exc()
                pass
        fflog(f'Missing kodi.log {log_path=}')
        # fallback to kodi api, it is fucked, can return "busy"
        from xbmc import getInfoLabel
        now = datetime.now(timezone.utc)
        up = getInfoLabel("System.Uptime")
        nums = list(map(int, re.findall(r'\d+', getInfoLabel("System.Uptime"))))
        if nums:
            # could be, in translations (sic!):
            # - "1 day 2 hours 3 minutes"
            # - "1 hour 2 minutes"
            # - "1 minute"  (not checked)
            d, h, m = [0, 0, *nums][-3:]
            _startup = now - timedelta(days=d, hours=h, minutes=m)
        else:
            fflog(f'Incorrect System.Uptime: {up!r}')
            # WTF???
            # Kodi can NOT return human readable time data, even if system is 4 hours up`.
            # It could return "Busy" (PL: "Zajęty")
            return datetime(1971, 1, 1, tzinfo=timezone.utc)
    return _startup


class KodiRpc:
    """Kodi JSONRPC client."""

    MESSAGE_ID_NAME: ClassVar[str] = '_id_'
    ACTION_NAME: ClassVar[str] = '_action_'
    BROADCAST: ClassVar[int] = 0

    def __init__(self) -> None:
        #: JSON-RPC message id.
        self._jsonrpc_id = 1
        #: Notification message id for match NotifyAll response.
        self._notify_message_id = int(monotonic() * 1000) % 1000 * 1000 + 1

    def rpc(self, method: str, *, params: Optional[Params] = None, fields: Sequence[str] = ()) -> JsonResult:
        """Call remote procedure (JSONRPC)."""
        msg_id, self._jsonrpc_id = self._jsonrpc_id, self._jsonrpc_id + 1
        params = dict(params or {})
        req = {
            'jsonrpc': '2.0',
            'method': method,
            'params': params,
            'id': msg_id,
        }
        # TODO: sort
        # TODO: filter
        # TODO: limits
        if fields:
            params['properties'] = tuple(fields)
        result = None
        try:
            result = executeJSONRPC(json.dumps(req, default=tuple, ensure_ascii=False))
            data = json.loads(result)
        except Exception as exc:
            fflog.error(f'JSONRPC call failed: {exc}, {req!r}\n  {result!r}')
            raise
        fflog.debug(f'................  {data}')
        return data

    def rpc_list(self, method: str, *, params: Optional[Params] = None, fields: Sequence[str] = (), return_type: Optional[str] = None) -> list[JsonData]:
        """Call remote procedure (JSONRPC)."""
        data = self.rpc(method=method, params=params, fields=fields)
        if isinstance(data, Mapping) and isinstance((result := data.get('result')), Mapping):
            if return_type is None:
                return_type = next(iter(result.keys() - {'limits'}), None)
                if return_type is None:
                    return []
            # if limits := result.get('limits'):
            #     end, start, total = limits['end'], limits['start'], limits['total']
            return result[return_type]
        return []

    def rpc_object(self, method: str, *, params: Optional[Params] = None, fields: Sequence[str] = (), return_type: Optional[str] = None) -> JsonData:
        """Call remote procedure (JSONRPC)."""
        data = self.rpc(method=method, params=params, fields=fields)
        if isinstance(data, Mapping) and isinstance((result := data.get('result')), Mapping):
            if return_type is None:
                return_type = next(iter(result.keys() - {'limits'}), None)
                if return_type is None:
                    return {}
            return result[return_type]
        return {}

    def notify(self, method: str, data: JsonData | None = None, *, id: int | None = None, action: KodiRpcAction = 'notify') -> int:
        """Emit JSON-RPC notification. Returns message id."""
        from .control import plugin_id
        data = dict(data or ())
        if isinstance(id, int):
            mid = id  # could be zero on service notification broadcast
        else:
            mid, self._notify_message_id = self._notify_message_id, self._notify_message_id + 1
        data[self.MESSAGE_ID_NAME] = mid
        data[self.ACTION_NAME] = action
        params = {
            'sender': plugin_id,
            'message': method,
            'data': data or {},
        }
        self.rpc(method='JSONRPC.NotifyAll', params=params)
        return mid

    def service_call(self, method: str, data: JsonData | None = None, *, timeout: float | None = None) -> JsonData | None:
        """Call JSON-RPC using notifications and return response."""

        class ServiceWaiter(Monitor):

            def __init__(self) -> None:
                super().__init__()
                self.last_id: int | None = None
                self.last_msg: JsonData | None = None
                self.msg: JsonData | None = None

            def onNotification(self, sender: str, method: str, data: str) -> None:
                """Notification, called by Kodi."""
                # fflog(f'[KOTOOLS][RPC]  ServiceWaiter received notification: {sender=}, {method=}, {data=}')
                if sender == plugin_id and data and (msg := json.loads(data)) and msg.get(ACTION_NAME) == 'response':
                    self.last_msg = msg
                    self.last_id = msg.get(MESSAGE_ID_NAME)
                    if self.last_id == mid:
                        self.msg = msg
                        event.set()

        from .control import plugin_id
        MESSAGE_ID_NAME = self.MESSAGE_ID_NAME
        ACTION_NAME = self.ACTION_NAME
        if timeout is None:
            timeout = const.tune.service.rpc_call_timeout
        mid = 0
        event = Event()
        with ServiceWaiter() as waiter:
            mid = self.notify(method, data, action='request')
            if waiter.last_id == mid:
                # already received
                return waiter.last_msg
            xsleep(timeout, cancel_event=event)
            # waiter.waitForAbort(0.001)
            # waiter.waitForAbort(timeout)
            if not event.is_set():
                return None
            return waiter.msg

    def wait_for_service(self, *, timeout: float | None = None) -> bool:
        """Wait for Kodi service to be ready. Returns True if service is ready, False on timeout."""

        def service_up(sender: str, method: str, data: str) -> None:
            """Notification, called by Kodi."""
            # fflog(f'======================================================== {sender=}, {method=}, {data=}')
            if sender == plugin_id and method in ('Other.ServicePong', 'Other.ServiceUp'):
                event.set()

        from .control import plugin_id
        xmonitor = KodiMonitor.instance()
        if xmonitor is None:
            return False
        if timeout is None:
            timeout = const.tune.service.startup_timeout
        event = Event()
        with xmonitor.with_watcher(service_up):
            step = 1.5
            while timeout > 0 and not event.is_set():
                self.notify('ServicePing')
                # wait for service ping
                xsleep(min(timeout, step), cancel_event=event)
                timeout -= step
            return event.is_set()
