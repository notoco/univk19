"""
Simple base info module.

Keep it simple, no global imports, no dependencies.
"""

from __future__ import annotations


#: Number of plugin calls
run_count: int = 0


def new_run() -> int:
    """Report new call. Return current call count."""
    # zliczaj liczbę wywołań FF
    global run_count
    # if not run_count:
    #     from .ff.control import pretty_log_info
    #     pretty_log_info()
    if run_count is not False:
        run_count += 1
    return run_count


def exec_id(*, highlight: str = '') -> str:
    """Return execute id."""
    import sys
    import os
    import threading
    iid = id(sys.implementation)
    iid = ((iid >> 48) ^ (iid >> 32) ^ (iid >> 16) ^ iid) & 0xffff
    pid = os.getpid()
    tid = threading.get_ident()
    if run_count is None or run_count is False:
        return f'{iid:04x}:{pid}:{tid}'
    off = '\033[0m' if highlight else ''
    return f'{iid:04x}:{pid}:{tid}:{highlight}{run_count}{off}'
