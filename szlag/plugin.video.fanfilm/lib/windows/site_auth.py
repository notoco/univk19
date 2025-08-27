
from typing import Optional, Union
from pathlib import Path

# from xbmcvfs import translatePath

from .base_window import BaseDialog, CANCEL_ACTIONS
from ..kolang import L
from ..ff.log_utils import fflog
from const import const

CANCEL_BUTTON = 31
OPEN_BUTTON = 32


class SiteAuthWindow(BaseDialog):

    XML = 'SiteAuth.xml'
    CUSTIMZED_XML = True

    def __init__(self, *args,
                 code: str,
                 url: str = '',
                 progress: Union[int, bool] = 0,
                 icon: Optional[Union[Path, str]] = None,
                 title: Optional[str] = None,
                 qrcode: Optional[str] = None,
                 **kwargs) -> None:
        super().__init__(self, *args, **kwargs)
        self.progress_enabled: bool = progress is not False
        self.progress: int = progress or 0
        self.icon: str = str(icon or '')
        self.code: str = code
        self._remove_icon: bool = False
        self.url: str = url or ''
        self._is_inited: bool = False
        self._is_canceled: bool = False

        if not code:
            code = ''
        if icon is None and qrcode:
            self.icon = self.generate_qrcode(qrcode)
            self._remove_icon = True
        if const.dialog.auth.code_color:
            code = f'[COLOR {const.dialog.auth.code_color}]{code}[/COLOR]'
        if (link := self.url) and const.dialog.auth.link_color:
            link = f'[COLOR {const.dialog.auth.link_color}]{self.url}[/COLOR]'
        if title is None:
            title = L(30396, '[B]Authorize[/B]')
        self.setProperty('title', title)
        self.setProperty('code', str(code))
        self.setProperty('link', link)
        self.setProperty('link.open', L(30397, 'Open link') if link else '')
        self.setProperty('icon.path', str(self.icon or ''))
        self.setProperty('progress.enabled', 'enabled' if self.progress_enabled else '')

    def onInit(self) -> None:
        fflog('SiteAuthWindow.onInit()')
        self.setFocusId(OPEN_BUTTON)
        self._is_inited = True
        self.update(self.progress)

    def onAction(self, action) -> None:
        action_id = action.getId()
        fflog(f'SiteAuthWindow.onAction({action!r}): {action_id=}')
        if action_id in CANCEL_ACTIONS:
            self._is_canceled = True
            self.close()

    def onClick(self, controlId: int) -> None:
        fflog(f'SiteAuthWindow.onClick({controlId!r})')
        if controlId == CANCEL_BUTTON:
            self._is_canceled = True
            self.close()
        elif controlId == OPEN_BUTTON:
            from ..ff.kotools import get_platform
            if get_platform() == 'android':
                from subprocess import Popen
                Popen(['am', 'start', self.url])
            else:
                import webbrowser
                THE_SAME, NEW_WINDOW, NEW_TAB = 0, 1, 2  # noqa: F841
                webbrowser.open(self.url, new=NEW_TAB, autoraise=True)

    def generate_qrcode(self, code: str) -> str:
        """Generate QR code image and return its path."""
        import segno
        from ..ff.control import dataPath as DATA_PATH
        code_hash = f'{hash(code):08x}'
        icon = Path(DATA_PATH) / f'tmp/gui-qrcode.{code_hash}.png'
        icon.parent.mkdir(parents=True, exist_ok=True)
        qrcode = segno.make(code)
        qrcode.save(str(icon), scale=const.tmdb.auth.qrcode_size)
        return str(icon)

    def on_close(self) -> None:
        """Cleanup temp QR code image."""
        if self._remove_icon and self.icon:
            try:
                Path(self.icon).unlink(missing_ok=True)
            except Exception as exc:
                fflog.warning(f'Error removing QR code image {self.icon}: {exc}')
            self._remove_icon = False
            self.icon = ''

    def update(self, value: int) -> None:
        """Upate progress in percent (0..100)."""
        if not value or value < 0:
            value = 0
        elif value is True or value > 100:
            value = 100
        self.progress = value
        if self._is_inited:
            bg = self.getControl(21)
            fg = self.getControl(22)
            fg.setWidth(int(value * bg.getWidth() / 100))

    def dialog_is_canceled(self) -> bool:
        return self._is_canceled
