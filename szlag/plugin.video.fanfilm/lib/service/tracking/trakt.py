"""Trakt service task."""

from __future__ import annotations
from time import monotonic
from typing import Optional
from threading import Lock
from attrs import frozen

from ...ff.threads import Thread, Event, Queue
from ...ff.trakt import trakt
from ...ff.kotools import xsleep
from ...ff.calendar import utc_timestamp
from ...ff.control import notification
from ...ff.log_utils import fflog
from ..exc import ExitBaseExcepion
from ...kolang import L
from . import TrackingAction
from ...ff.settings import settings
from const import const


@frozen
class TraktSyncStatus:
    timestamp: Optional[float] = None
    changed: bool = False


class TraktSync(Thread):
    """Trakt to FF3 sync service task."""

    def __init__(self) -> None:
        self.active: bool = False
        self.interval: int = const.trakt.sync.interval
        self.startup_interval: int = const.trakt.sync.startup_interval
        self.need_sync: Event = Event()
        self.synced: Event = Event()
        self._lock: Lock = Lock()
        self._syncing: bool = False
        self._status: TraktSyncStatus = TraktSyncStatus()
        #: UTC timestamp when cooldown end and sync could starts again.
        self._cooldown_timestamp: float = 0
        super().__init__()
        self.name = f'{self.name}: TraktSync'

    @property
    def is_syncing(self) -> bool:
        with self._lock:
            return self._syncing

    @property
    def status(self) -> TraktSyncStatus:
        with self._lock:
            return self._status

    @property
    def timestamp(self) -> Optional[float]:
        with self._lock:
            return self._status.timestamp

    @property
    def changed(self) -> float:
        with self._lock:
            return self._status.changed

    def stop(self) -> None:
        """Stop trakty sync thread."""
        self.active = False

    def run(self):
        """Main activity."""
        # startup
        self.active = True
        try:
            xsleep(self.startup_interval)
        except (ExitBaseExcepion, SystemExit):
            return

        # working
        while self.active:
            try:
                now = utc_timestamp()
                if self._cooldown_timestamp and self._cooldown_timestamp > now:
                    xsleep(self._cooldown_timestamp - now)
                self._sync()
                if not self.need_sync.is_set():
                    xsleep(self.interval, cancel_event=self.need_sync)
                    self.need_sync.clear()
            except (ExitBaseExcepion, SystemExit):
                # abort
                self._status = TraktSyncStatus()
                self._syncing = False
                self.synced.set()
                self.active = False
                raise

    def _sync(self) -> bool:
        if not trakt.credentials():
            with self._lock:
                self._status = TraktSyncStatus()
            return False
        with self._lock:
            self._syncing = True
            self.synced.clear()
        fflog('[SERVICE][TRAKT] sync START')
        with notification('[FanFilm] Trakt', L(30200, 'sync in progress'),
                          delay=const.trakt.sync.notification_delay,
                          enabled=settings.getBool('trakt.sync_notification')):
            timestamp = utc_timestamp()
            changed = trakt.sync_now(timestamp=timestamp)
            cooldown_timestamp = utc_timestamp() + const.trakt.sync.cooldown
        fflog('[SERVICE][TRAKT] sync DONE')
        with self._lock:
            self._status = TraktSyncStatus(timestamp=timestamp, changed=changed)
            self._cooldown_timestamp = cooldown_timestamp
            self._syncing = False
            self.synced.set()
        return True

    def sync_start(self) -> None:
        """Force sync start (if not syncing already)."""
        self.synced.clear()
        self.need_sync.set()

    def sync(self, timeout: Optional[float] = None) -> Optional[TraktSyncStatus]:
        """
        Synces trakt and returns new timestamp.

        It starts syncing and wait for finish.
        Waits max `timeout` if not None.
        Returns new trakt sync timestamp or None if timeout expires.
        """
        # check if syncing is in progress
        start_time = monotonic()
        prev_timestamp = 0
        with self._lock:
            if self._syncing:
                prev_timestamp = self._status.timestamp
        # syncing is in progress, we have to wait for current syncing ends to start sync again
        if prev_timestamp:
            if not self.synced.wait(timeout):
                return None  # timeout expires
        # start syncing
        self._cooldown_timestamp = 0  # force sync now
        self.sync_start()
        # wait for synced (minus time spend on waiting for previous syncing)
        if timeout is not None and timeout > 0:
            timeout = max(0, start_time + timeout - monotonic())
        return self.wait_for_sync(timeout=timeout)

    def wait_for_sync(self, timeout: Optional[float] = None) -> Optional[TraktSyncStatus]:
        if self.synced.wait(timeout):
            with self._lock:
                return self._status
        return None  # timeout expires


class TraktSender(Thread):
    """Sending FF3 events to trakt service task."""

    def __init__(self) -> None:
        self.queue: Queue[Optional[TrackingAction]] = Queue()
        self._lock: Lock = Lock()
        super().__init__()
        self.name = f'{self.name}: TraktSender'

    @property
    def active(self) -> bool:
        return self.is_alive()

    def action(self, action: TrackingAction) -> None:
        """Send tracking action to trakt service."""
        self.queue.put(action)

    def run(self):
        fflog('[TraktSender] started')
        """Main activity."""
        while True:
            action = self.queue.get()
            if action is None:  # immediate stop
                break
            fflog(f'[TraktSender] {action=} ...  {trakt.credentials()=}')
            with self._lock:
                try:
                    db_save = False
                    if trakt.credentials():
                        fflog(f'[TraktSender] {action=}')
                        if action.action == 'watched':
                            if action.progress:
                                trakt.scrobble_ref('stop', action.ref, db_save=db_save)
                            else:
                                trakt.add_history_ref(action.ref, db_save=db_save)
                        elif action.action == 'unwatched':
                            trakt.remove_playback_ref(action.ref, db_save=db_save)
                            trakt.remove_history_ref(action.ref, db_save=db_save)
                        elif action.action == 'reset_progress':
                            trakt.remove_playback_ref(action.ref, db_save=db_save)
                finally:
                    self.queue.task_done()
        fflog('[TraktSender] stopping')

    def stop(self) -> None:
        """Stop trakt sync thread."""
        self.queue.clear()
        self.queue.put(None)
