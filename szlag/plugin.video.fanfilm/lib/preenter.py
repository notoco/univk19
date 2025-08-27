"""Some stuff to do berfore main() is called."""

import atexit
from pathlib import Path
from const import const


if const.debug.autoreload:
    from .service.reload import ReloadMonitor
    ffpath: Path = Path(__file__).parent
    reload_monitor = ReloadMonitor([
        ffpath / '*.py',
        ffpath / 'ff/**',
        ffpath / 'api',
        ffpath / 'indexers',
        ffpath / 'sources',
        ffpath / 'windows',
    ])
else:
    reload_monitor = None


def cleanup():
    import xbmc
    from lib.ff import settings as settings_module
    from lib.kolang import _label_getters
    from lib.ff.menu import KodiDirectory
    xbmc.log('------- FF3: cleanup()', xbmc.LOGDEBUG)
    KodiDirectory.set_current_info(None, None)  # force clean
    if settings_module.settings:
        settings_module.settings._addon = None
    settings_module.settings = None
    for lab in _label_getters.values():
        lab.addon = None


def preinit():
    """Run on begeining, before run count."""
    atexit.register(cleanup)
    if reload_monitor:
        reload_monitor.check()


def premain():
    """Run just before main."""
