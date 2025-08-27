"""Service / reload exception definitions."""

from typing import Optional, Sequence
from types import ModuleType
from pathlib import Path


class ExitBaseExcepion(BaseException):
    """Exit exceptions are based on BaseException to pass thru `except Exception`."""


class KodiExit(ExitBaseExcepion):
    """Kodi is going to close."""


class ReloadExit(ExitBaseExcepion):
    """Force to reload modules."""

    def __init__(self, *args,
                 files: Sequence[Path] = (),
                 changed: Sequence[Path] = (),
                 modules: Optional[Sequence[ModuleType]] = None,
                 ) -> None:
        super().__init__(*args)
        #: List of all watcheed files.
        self.files: Sequence[Path] = files
        #:  List of changed files.
        self.changed: Sequence[Path] = changed
        #:  Set of changed modules.
        self.modules: Sequence[ModuleType] = modules or ()
