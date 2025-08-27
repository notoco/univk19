"""
Library service, adding in background.
"""

from __future__ import annotations
from typing import Optional, Sequence, TYPE_CHECKING
from attrs import define
from xbmc import executebuiltin
from ..ff.threads import Thread, Event, Queue
from ..ff.libtools import LibTools
from ..ff.calendar import make_datetime, timestamp
from ..ff.log_utils import fflog
from ..ff.settings import settings
from ..ff.control import infoDialog
from ..kolang import L

from const import const
if TYPE_CHECKING:
    from ..defs import FFRef


@define(kw_only=True)
class Batch:
    id: int
    name: str
    items: Sequence[FFRef]
    force_sync: bool = False
    quiet: bool = False


class Library(Thread):
    """Library service, adding in background."""

    def __init__(self) -> None:
        super().__init__(name='Library Service')
        self.library = LibTools()
        self.queue: Queue[Batch] = Queue()
        self.current: Optional[Batch] = None
        self._next_batch_id: int = int(timestamp())
        self.active: bool = False

    def stop(self) -> None:
        """Stop service gracefully."""
        self.active = False
        self.queue.put_nowait(Batch(id=0, name='', items=()))

    def add(self, items: Sequence[FFRef], *, name: Optional[str] = None, force_sync: bool = False, quiet: bool = False) -> int:
        """Add set of items to library. Return new set/batch id."""
        bid = self._next_batch_id
        self._next_batch_id += 1
        if not name:
            name = str(make_datetime(None))
        batch = Batch(id=bid, name=name, items=items, force_sync=force_sync, quiet=quiet)
        self.queue.put_nowait(batch)
        return batch.id

    def reload_library(self) -> int:
        """Async reload - send UpdateLibrary(video) request."""
        return self.add((), force_sync=True, quiet=True)

    def run(self) -> None:
        """Main activity, read batches and process items to libtool."""
        self.active = True
        while self.active:
            batch = self.queue.get()
            if not self.active:
                break
            fflog(f'[LIB] Start batch {batch.id} ({batch.name}): {len(batch.items)} element(s)')
            if not settings.getBool('library.service.notification'):
                batch.quiet = True  # force quiet if notifications are not allowd
            self.batch_started(batch)
            self.library.add(batch.items, reload=False)
            update = settings.getBool('library.update')
            empty = self.queue.empty()
            if (empty or const.library.service.sync_every_batch or batch.force_sync) and update:
                executebuiltin('UpdateLibrary(video)', const.library.service.sync_wait)
            self.batch_finished(batch)
            fflog(f'[LIB] Batch {batch.id} ({batch.name}) finished')
            self.queue.task_done()

    def batch_started(self, batch: Batch) -> None:
        """Start batch notification."""
        self.current = batch  # for info/notification only
        if not batch.quiet:
            infoDialog(L(30322, 'Started'), L(30321, 'Adding to library...'), icon="")

    def batch_finished(self, batch: Batch) -> None:
        """Finish batch notification."""
        self.current = None  # for info/notification only
        if not batch.quiet:
            infoDialog(L(30323, 'Finished'), L(30321, 'Adding to library...'), icon="")
