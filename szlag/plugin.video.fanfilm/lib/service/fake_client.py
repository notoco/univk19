"""
Fake FF Service client for test.
"""

from __future__ import annotations
from typing import Optional, Union, Any, Dict, Iterable, Sequence, Iterator, ClassVar, TYPE_CHECKING
from contextlib import contextmanager
from time import time as cur_time
from attrs import evolve

from ..ff.log_utils import fflog
from .misc import PluginRequestInfo, StateVar, FFState, VolatileFfid
from .client import ServiceClient
if TYPE_CHECKING:
    from ..ff.url import URL
    from ..defs import MediaRef
    from ..ff.item import FFItem
from const import const


class FakeServiceClient(ServiceClient):
    """Simple FF Service client."""

    LOG_EXCEPTION: ClassVar[bool] = False
    FAKE: ClassVar[bool] = True

    def __init__(self, *, port: Optional[int] = const.tune.service.http_server.port) -> None:
        super().__init__(port=port)
        self._plugin_info = PluginRequestInfo()
        self._state = FFState()
        self._volatile_ffid = VolatileFfid()

    @property
    def url(self) -> str:
        """Service HTTP server URL."""
        if self._url is None:
            self._url = 'http://127.0.0.1:8123/'
        return self._url

    def folder_ready(self, *, timeout: Optional[float] = None) -> bool:
        """Wait for folder ready (watching progress update)."""
        fflog.debug('[FAKE] folder_ready()')
        return True

    def plugin_request_info(self) -> PluginRequestInfo:
        """Get folder info."""
        fflog.debug('[FAKE] plugin_request_info()')
        return self._plugin_info

    def plugin_request_enter(self, url: Union[URL, str], *, timestamp: Optional[float] = None) -> PluginRequestInfo:
        """Notify server about FF plugin folder enter."""
        fflog.debug(f'[FAKE] plugin_request_enter(url={str(url)!r})')
        self._plugin_info.enter(url, timestamp=timestamp)
        return self._plugin_info

    def plugin_request_exit(self, *, folder: Optional[Sequence[FFItem]] = None, focus: int = -1, timestamp: Optional[float] = None) -> PluginRequestInfo:
        """Notify server about FF plugin generate folder exit."""
        fflog.debug(f'[FAKE] plugin_request_exit({"-" if folder is None else len(folder)} items)')
        self._plugin_info.exit(folder=folder, focus=focus, timestamp=timestamp)
        return self._plugin_info

    def get_ffid_ref(self, ffid: int, *, timeout: Optional[float] = None) -> Optional[MediaRef]:
        """Get ref by volatile ffid."""
        return self._volatile_ffid.get(ffid)

    def get_ffid_ref_dict(self, ffid_list: Iterable[int], *, timeout: Optional[float] = None) -> Dict[int, MediaRef]:
        """Get refs by volatile ffid list, return dict[ffid] = ref."""
        return {ffid: ref for ffid in ffid_list if (ref := self._volatile_ffid.get(ffid)) is not None}

    def create_ffid(self, ref: MediaRef, *, timeout: Optional[float] = None) -> Optional[int]:
        """Create new volatile ffid for given ref."""
        return self._volatile_ffid.register(ref)

    def create_ffid_dict(self, refs: Iterable[MediaRef], *, timeout: Optional[float] = None) -> Dict[MediaRef, int]:
        """Create new volatile ffid for given ref."""
        return {ref: self._volatile_ffid.register(ref) for ref in refs}

    def trakt_sync(self) -> Optional[bool]:
        """Synchronize trakt.tv."""
        fflog.debug('[FAKE] trakt_sync()')
        return None

    def state_get(self, module: str, key: str = '') -> Sequence[StateVar]:
        """Return service state variable."""
        var = self._state.get(module=module, key=key)
        return () if var is None else (var,)

    def state_set(self, variables: Iterable[StateVar], *, connect: bool = True) -> Optional[bool]:
        """Set list of variables to service state."""
        return self._state.multi_set(variables)

    def state_delete(self, module: str, key: str = '', *, connect: bool = True) -> Optional[bool]:
        """Delete service state variable."""
        return bool(self._state.delete(module=module, key=key))

    def state_wait(self, module: str, key: str, value: Any, *, timeout: Optional[float] = None) -> Optional[bool]:
        """Wait for service state variable change."""
        return self._state.wait_for(module=module, key=key, value=value, timeout=timeout)

    @contextmanager
    def state_with(self, module: str, key: str) -> Iterator[None]:
        """Section with service state variable (set ti True in the statement, and False on exit)."""
        var = StateVar(module=module, key=key, value=True, type='bool', updated_at=cur_time())
        self._state.set(var)
        try:
            yield None
        finally:
            var = evolve(var, value=False, updated_at=cur_time())
            self._state.set(var)

    def advanced_settings(self) -> Dict[str, Any]:
        """Return advancedsettings.xml as JSON structure."""
        from ..ff.settings import advanced_settings
        return advanced_settings.get()

    def library_add(self, items: Sequence[Union[MediaRef, FFItem]], *, name: Optional[str] = None, force_sync: bool = False, quiet: bool = False) -> None:
        """Add to library items by theirs ref."""
        fflog.debug(f'[FAKE] library_add({len(items)} items, {name=}, {force_sync=}, {quiet=})')
