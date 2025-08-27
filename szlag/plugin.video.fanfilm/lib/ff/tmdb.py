"""Tiny TheMovieDB.org API getter."""

from __future__ import annotations
from typing import Optional, TYPE_CHECKING
from pathlib import Path
from ..api.tmdb import TmdbApi, TmdbCredentials, DialogId
from . import apis
from .settings import settings
from .control import dataPath as DATA_PATH, notification, addonName
from .log_utils import fflog
from ..kolang import L
from const import const
if TYPE_CHECKING:
    from ..windows.site_auth import SiteAuthWindow


class Tmdb(TmdbApi):
    """API for themoviedb.org."""

    def __init__(self):
        #: TMDB auth progreass dialog.
        self.progress_dialog: Optional[SiteAuthWindow] = None
        #: Path to generated auth QR-Code.
        self.auth_qrcode_path: Optional[Path] = None

        api_key: str = const.dev.tmdb.api_key or apis.tmdb_API
        bearer: str = const.dev.tmdb.v4.bearer or apis.tmdb_bearer
        super().__init__(api_key=api_key, bearer=bearer)

    def credentials(self) -> TmdbCredentials:
        """Return current credencials."""
        user = settings.getString('tmdb.username')
        password = settings.getString('tmdb.password')
        session_id = settings.getString('tmdb.sessionid')
        access_token = settings.getString('tmdb.access_token')
        return TmdbCredentials(user=user, password=password, session_id=session_id, access_token=access_token)

    def save_session(self, *, session_id: Optional[str], access_token: Optional[str] = None) -> None:
        """Set session ID. Save session ID or remove if None."""
        settings.setString('tmdb.sessionid', session_id or '')
        settings.setString('tmdb.access_token', access_token or '')

    def dialog_create(self, request_token: str, verification_url: str) -> DialogId:
        """Create GUI dialog."""
        import segno
        from ..windows.site_auth import SiteAuthWindow

        code_hash = f'{hash(verification_url):08x}'
        icon = Path(DATA_PATH) / f'tmp/tmdb-auth-qrcode.{code_hash}.png'
        icon.parent.mkdir(parents=True, exist_ok=True)
        fflog(f'[TMDB] Auth: visit site {verification_url}')
        qrcode = segno.make(verification_url)
        qrcode.save(str(icon), scale=const.tmdb.auth.qrcode_size)
        self.auth_qrcode_path = icon
        self.progress_dialog = SiteAuthWindow(code='', url=verification_url, icon=icon, modal=False,
                                              title=L(30364, '[B]Authorize TMDB[/B]'))
        self.progress_dialog.doModal()  # this dialog is modeless (!)

    def dialog_close(self, dialog: DialogId) -> None:
        """Close GUI dialog."""
        if self.auth_qrcode_path is not None:
            self.auth_qrcode_path.unlink(missing_ok=True)
            self.auth_qrcode_path = None
        if self.progress_dialog is not None:
            self.progress_dialog.destroy()
            self.progress_dialog = None  # works like "del X"

    def dialog_cancel(self, dialog: DialogId) -> None:
        """Cancel GUI dialog. Debug only."""
        if self.progress_dialog is not None:
            self.progress_dialog.close()

    def dialog_is_canceled(self, dialog: DialogId) -> bool:
        """Return True if GUI dialog is canceled."""
        if self.progress_dialog is not None:
            return self.progress_dialog.dialog_is_canceled()
        return False

    def dialog_update_progress(self, dialog: DialogId, progress: float) -> None:
        """Update GUI dialog progress-bar."""
        fflog(f'[TMDB] auth {progress:5.1f}')
        if self.progress_dialog is not None:
            self.progress_dialog.update(int(progress))

    def auth_failed(self) -> None:
        """401 - auth error, should inform user or force auth again."""
        notification(f'{addonName()} – TMDB', L(30365, 'TMDB has no authorization')).show()


#: Global TMDB support.
tmdb = Tmdb()
