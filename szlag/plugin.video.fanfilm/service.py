"""
    FanFilm Add-on

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

from pathlib import Path
from time import monotonic
import sys
import atexit
from typing import Sequence
from types import ModuleType

# MUST be before any kodi or FF import
from lib import autoinstall  # noqa: F401, pylint: disable=W0611  # type: ignore
from lib import service
if True:
    # Mark this process as service.
    service.SERVICE = True

# Some consts.
# from const import const  # noqa: F401, pylint: disable=W0611

from lib.ff import log_utils
from lib.ff.log_utils import fflog, fflog_exc
from lib.ff.settings import settings
from const import const

ffpath = Path(__file__).parent / 'lib'
main_path = ffpath / 'service' / 'main.py'


def cleanup():
    """Cleanup on shutdown."""
    from lib.ff import settings as settings_module
    from lib.kolang import _label_getters
    if settings_module.settings:
        settings_module.settings._addon = None
    settings_module.settings = None
    for lab in _label_getters.values():
        lab.addon = None


atexit.register(cleanup)


if settings.getBool("ff.autostart"):
    from xbmc import executebuiltin
    from xbmcaddon import Addon
    plugin_id = Addon().getAddonInfo('id')
    fflog('Autoexec FF is enabled')
    executebuiltin(f"ActivateWindow(10025, plugin://{plugin_id}/, return)")

if const.debug.autoreload:
    # --- deveoping code ---
    force_reload = False
    while True:
        fflog('[FF] SERVICE start...')
        exit = None
        started_at = monotonic()
        try:
            from lib.service import reload, main
            reload_monitor = reload.ReloadMonitor([ffpath / '*.py', ffpath / 'ff**', ffpath / 'service', ffpath / 'api', ffpath / 'indexers'])
            try:
                if force_reload:
                    force_reload = False
                    started_at = 0
                    fflog('[FF] SERVICE force reload all modules')
                    reload_monitor.raise_reload()
                main.run(reload_monitor=reload_monitor)
            except main.KodiExit:
                fflog('[FF] SERVICE kodi is exiting')
                exit = 'kodi'
                main.stop()
                break
            except reload.ReloadExit as reloading:
                fflog('[FF][SERVICE] change detected...')
                mods: Sequence[ModuleType] = reload.modules_by_files(reloading.files)
                mod_count = len(mods)
                skip_mods = {sys.modules[__name__], main, reload, log_utils}
                reload.ReloadMonitor.reloading = True
                main.stop()
                if main.monitor.abortRequested() or main.monitor.waitForAbort(1.2):
                    fflog('[FF][SERVICE] kodi exit during reload')
                    break
                fflog(f'[FF][SERVICE] changed, reload {mod_count} modules...')
                reload.reload(reload)
                for mod in mods:
                    if mod not in skip_mods:
                        reload.reload(mod)
                reload.reload(main)
                del reload
                del main
                continue
        except Exception as exc:
            from lib.ff.kotools import xsleep_until_exit, KodiExit
            exit = str(exc)
            fflog_exc()
            if xsleep_until_exit(3) is KodiExit:
                break
            del xsleep_until_exit
            del KodiExit
        finally:
            fflog(f'[FF] SERVICE stop (exit {exit})')
            if (t := monotonic() - started_at < 5):
                from lib.ff.kotools import xsleep_until_exit, KodiExit
                fflog(f'[FF] SERVICE restarted too quick ({t:.1f} sec), sleep 15 sec')
                if xsleep_until_exit(15) is KodiExit:
                    break
                force_reload = True
                del xsleep_until_exit
                del KodiExit
else:
    # --- production code ---
    from lib.service import main
    from lib.service.exc import KodiExit
    from lib.info import exec_id, new_run

    # count run calls
    run_count: int = new_run()
    yellow = yellow_bold = off = iid = ''
    if const.debug.enabled:
        if const.debug.tty:
            yellow, yellow_bold, off = '\033[93m', '\033[93;1m', '\033[0m'
        iid = exec_id(highlight=yellow)
        fflog(f"{yellow_bold}[FF]{off} {yellow}service START{off} [{iid}] {sys.argv=}")

    try:
        main.run()
    except (KodiExit, SystemExit):
        pass
    finally:
        if const.debug.enabled:
            fflog(f"{yellow_bold}[FF]{off} {yellow}service FINISHED{off} [{iid}] {sys.argv=}")

if True:
    from lib.ff.kotools import destroy_xmonitor
    destroy_xmonitor()
