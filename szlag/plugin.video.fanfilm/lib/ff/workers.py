# -*- coding: utf-8 -*-

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

from typing import Optional
import os
import threading

import xbmc
from .settings import settings
from .threads import ThreadCanceled
from .log_utils import fflog, fflog_exc
from const import const


class Thread(threading.Thread):
    # Statyczna lista przechowująca wszystkie instancje wątków
    threads = []

    # Ustalanie liczby dostępnych wątków
    threads_count = settings.getInt("threads.count")
    if threads_count > 0:
        available_threads = threads_count
    else:
        available_threads = os.cpu_count() or 8

    # Ustawienie semafora, który ogranicza liczbę równoczesnych wątków do dostępnej liczby rdzeni
    thread_limiter = threading.Semaphore(available_threads)

    def __init__(self, target, args=(), kwargs=None, *, name: Optional[str] = None):
        super().__init__(target=target, args=args, kwargs=kwargs if kwargs else {}, name=name)
        self._stop_requested = threading.Event()
        self.threads.append(self)

    def run(self):
        with self.thread_limiter:
            while not xbmc.Monitor().abortRequested() or self._stop_requested.is_set():
                if self._target:
                    try:
                        self._target(*self._args, **self._kwargs)
                        break
                    except ThreadCanceled:
                        fflog(f'Thread {self.name} graceful canceled')
                        return
                    except Exception as exc:
                        fflog(f'Thread {self.name} raises an exception: {exc}')
                        if const.dev.sources.log_exception:
                            fflog_exc()
                        raise
                if xbmc.Monitor().waitForAbort(1):
                    break

    def stop(self):
        self._stop_requested.set()

    @classmethod
    def stop_all(cls):
        for thread in cls.threads:
            thread.stop()
