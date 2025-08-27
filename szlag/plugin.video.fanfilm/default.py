"""
    FanFilm Add-on
    Copyright (C) 2016 mrknow

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

import sys
from time import monotonic

# debug
_start_time: float = monotonic()

# MUST be before any kodi or FF import
from lib import autoinstall  # noqa: E402, F401, pylint: disable=W0611  # type: ignore
# Some consts.
from const import const                       # noqa: E402
from lib.preenter import preinit, premain     # noqa: E402
from lib.service.exc import ReloadExit        # noqa: E402

try:
    preinit()
except ReloadExit:
    # -- reload on source file chnged
    import xbmc
    import xbmcgui
    xbmc.log("[FanFilm][default.py][dev] change detected, force exit...", xbmc.LOGINFO)
    xbmcgui.Dialog().notification("[FanFilm][dev]", "FanFilm reload, force exit")
    sys.exit()

from lib.ff.log_utils import fflog     # noqa: E402
from lib.main import main, reset       # noqa: E402
from lib.info import exec_id, new_run  # noqa: E402

# count run calls
run_count: int = new_run()


# debug
yellow = yellow_bold = off = ''
if const.debug.enabled:
    from lib.ff.control import is_plugin_folder
    if const.debug.tty:
        yellow, yellow_bold, off = '\033[93m', '\033[93;1m', '\033[0m'
    T: float = monotonic() - _start_time
    fflog(f"{yellow} [FF] enter {off} [{exec_id(highlight=yellow)}] {sys.argv=}, folder={is_plugin_folder()} --- ({T:.3f}s)")
if const.debugger.enabled:
    from cdefs import run_debugger
    run_debugger()

# reset some stuff on script relaod
reset()


try:
    premain()
    main(sys.argv)
finally:
    from lib.ff.control import is_plugin_folder
    exit_every_nth = const.core.exit_every_nth if is_plugin_folder() else const.core.widgets_exit_every_nth
    gc_every_nth = const.core.gc_every_nth
    if const.debug.enabled:
        T: float = monotonic() - _start_time
        exit_mode = ''
        if exit_every_nth and run_count >= exit_every_nth:
            exit_mode = ' (sys)'
        fflog(f'{yellow} [FF] exit{exit_mode} {off} [{exec_id(highlight=yellow)}] --- ({T:.3f}s),'
              f' run={run_count}/{exit_every_nth}, gc={run_count}/{gc_every_nth}, folder={is_plugin_folder()}')
    # Cleanup on every plugin call
    from lib.ff.menu import KodiDirectory
    KodiDirectory.set_current_info(None, None)  # force clean  # type: ignore[reportArgumentType]
    from threading import enumerate as threading_enumerate
    from lib.ff.kotools import xmonitor_script_finish, destroy_xmonitor, active_threads
    fflog(f' [FF] finishing [{exec_id(highlight=yellow)}] threads: active={active_threads()}, all=({len(threading_enumerate())}){threading_enumerate()}')
    xmonitor_script_finish()
    fflog(f' [FF] finished [{exec_id(highlight=yellow)}] threads: active={active_threads()}, all=({len(threading_enumerate())}){threading_enumerate()}')
    # Script exit to force python interpreter reload
    if exit_every_nth and run_count >= exit_every_nth:
        import gc
        destroy_xmonitor()
        gc.collect()
        sys.exit()
    if gc_every_nth and run_count >= gc_every_nth:
        import gc
        gc.collect()
