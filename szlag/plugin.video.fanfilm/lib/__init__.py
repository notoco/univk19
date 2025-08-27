import sys
from pathlib import Path
from typing import List


def is_subinterpreter() -> bool:
    """Detect if module is called in subinterpreter (Kodi) or not (command line)."""
    from traceback import format_stack
    st = format_stack()
    return bool(st and 'fanfilm' in st[0] and '/_dev_' not in st[0])


SUBINTERPRETER: bool = is_subinterpreter()
cmdline_argv: List[str] = []
FAKE: bool = not SUBINTERPRETER

# Path to the top-level fanfilm folder.
top_ff_path = Path(__file__).parent
# Add paths to 3rd-party libs.
sys.path.insert(0, str(top_ff_path / '3rd'))
# Add fake xmbc modules (DEBUG & TESTS).
if FAKE:
    sys.path.insert(0, str(top_ff_path / 'fake'))
    # from .fake import xbmc, xbmcgui
    # sys.modules['xbmc'] = xbmc
    # sys.modules['xbmcgui'] = xbmcgui
    # Fake sys.argv for DEBUG & TESTS from command line
    cmdline_argv, sys.argv = sys.argv, ['plugin://fanfilm/', '0', '']
    from lib.fake.fake_api import auto
    auto(cmdline_argv)
    del auto


# Monkey-patching datetime.strptime
# see: https://forum.kodi.tv/showthread.php?tid=112916&pid=2953239
# see: https://bugs.python.org/issue27400
import datetime as datetime_module            # noqa: E402
from datetime import datetime as _datetime    # noqa: E402


if not getattr(datetime_module, '_datetime_is_patched', False):

    class datetime(_datetime):

        @classmethod
        def strptime(cls, date_string: str, format: str) -> _datetime:
            try:
                return _dt_strptime(date_string, format)
            except TypeError:
                import time
                return datetime(*(time.strptime(date_string, format)[0:6]))

    _dt_strptime = _datetime.strptime
    datetime_module.datetime = datetime
    datetime_module._datetime = _datetime
    datetime_module._datetime_is_patched = True
