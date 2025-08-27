
from typing import Optional, Sequence
from typing_extensions import Literal
from time import monotonic
from ..ff.routing import route, RouteObject, url_for, info_for
from ..ff.menu import directory
from ..ff.log_utils import fflog
from ..ff.kotools import Notification, xsleep
from ..ff.info import ffinfo
from ..defs import MediaRef
from .folder import list_directory, item_folder_route, pagination, Folder
from ..kolang import L
from const import const


def print_settings(name: str):
    from ..ff.settings import settings
    for getter in (settings.getBool, settings.getInt, settings.getNumber, settings.getString,
                   settings.getBoolList, settings.getIntList, settings.getNumberList, settings.getStringList):
        try:
            value = getter(name)
        except Exception as exc:
            fflog(f'{name=}: {exc}')
        else:
            fflog(f'{name=}: {getter.__name__}({value!r})')


class DevMenu(RouteObject):
    """Głowne menu FanFilm."""

    @route('/')
    def home(self) -> None:
        """Create root / main menu."""
        with directory(view='sets') as kdir:
            kdir.action('Videos', self.videos)
            kdir.action('Notification', self.notification)
            kdir.action('Send notif', self.send_notif)
            kdir.action('Video DB info', self.video_db)
            kdir.action('Simple dialog', self.simple_dialog)
            kdir.action('Auth dialog', self.auth_dialog)
            kdir.folder('Add-to stuff', self.add_to)
            kdir.action('Test GUI', self.test_gui)
            kdir.folder('Library', self.library)
            kdir.action('Empty folder', self.empty)
            kdir.action('Test settings engine', self.test_settings)
            kdir.action('Exit', self.exit)  # The Last One

    @route
    def exit(self) -> None:
        """The iterpreter exit. Reload sources in next plugin call."""
        import sys
        sys.exit()

    @route
    def empty(self) -> None:
        """Folder with no items."""
        with directory(view='sets'):
            pass

    @route
    def videos(self) -> None:
        from ..main import fake_play_movie
        with directory(view='videos') as kdir:
            # kdir.play('Fake video', url_for(fake_play_movie, ref=MediaRef('movie', 909_000_001)))
            kdir.play('Fake video', url_for(fake_play_movie, ffid=100_000_646))
            ffitem = ffinfo.find_item(MediaRef('movie', 100_000_646))
            if ffitem:
                ffitem.label = 'Fake video'
                ffitem.url = str(url_for(fake_play_movie, ffid=ffitem.ref.ffid))
                kdir.add(ffitem)

    @route
    def notification(self) -> None:
        from ..ff.kotools import Notification, xsleep
        # xsleep(1.025)
        with Notification('FF dev', 'This is a test notification') as notif:
            fflog('[DEV] Notification start')
            xsleep(5)
            fflog('[DEV] Notification stop')

    @route
    def simple_dialog(self) -> None:
        from ..windows.dialogs import SimpleDialog, ButtonBox
        win = SimpleDialog('label|text', label='Bla bla bla', text="...", buttons=ButtonBox.YES_NO)
        result = win.doModal()
        fflog(f'[DEV] Dialog result: {result!r}')
        Notification('FF dev', f'Dialog result: {result!r}').show()

    @route('/auth/{__what}')
    def auth_dialog(self, what: Literal['tmdb', 'trakt'] = 'trakt') -> None:
        from ..windows.site_auth import SiteAuthWindow
        from ..ff.control import dataPath as DATA_PATH
        from pathlib import Path
        import segno
        if what == 'tmdb':  # TMDB
            token = ('eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiI5MDgwNjQ3ZmYxNjQ3ZiIsIm5iZiI6mYwMmI3NDc4ZGI5MDBmMTIzYMTc0MzU5Mjc2MS44MTkzLCJqdGkiOiI2N2VkMW'
                     'QzOTM0YzZjOTQxMDhkMGJmZmUiLCJzY29wZXMiOlsRva2VuIl0sInZlcnNpb24icGVuZGluZ19yZXF1ZXN0X3iOjIsImV4cCI6MTc0MzU5MzY2MX0.U8Tq8eLlC3e0Tb5O1P2lOYPyKdsTvgEufWG4tQGWnOk')
            verification_url = f'https://www.themoviedb.org/auth/access?request_token={token}'

            code_hash = f'{hash(verification_url):08x}'
            icon = Path(DATA_PATH) / f'tmp/dev-auth-qrcode.{code_hash}.png'
            icon.parent.mkdir(parents=True, exist_ok=True)
            qrcode = segno.make(verification_url)
            qrcode.save(str(icon), scale=const.tmdb.auth.qrcode_size)
        else:  # Trakt
            token = '12345678'
            verification_url = f'https://trakt.tv/activate/{token}'
            code_hash = f'{hash(verification_url):08x}'
            icon = Path(DATA_PATH) / f'tmp/dev-auth-qrcode.{code_hash}.png'
            icon.parent.mkdir(parents=True, exist_ok=True)
            qrcode = segno.make(verification_url)
            qrcode.save(str(icon), scale=const.trakt.auth.qrcode.size)
        modal = False
        win = SiteAuthWindow(code=token, url=verification_url, icon=icon, modal=modal)
        if modal:
            win.update(100)
            result = win.doModal()
        else:
            win.doModal()  # this dialog is modeless (!)
            try:
                for progress in range(0, 101, 5):
                    #: Current timestamp.
                    now: float = monotonic()
                    # check if dialog is canceled
                    if win.dialog_is_canceled():
                        break
                    # check if user authorized this device
                    # if access := self._get_access_token(device_code, cred):
                    #     break
                    # update progress-bar
                    win.update(int(progress))
                    # sleep given interval
                    xsleep(0.5)
            except KeyboardInterrupt:
                print('''\nCancelled. Enter '0'.\n''')
            finally:
                # finish - close dialog
                result = win.result()
                win.destroy()
                del win
        icon.unlink()
        fflog(f'[DEV] Dialog result: {result!r}')
        Notification('FF dev', f'Dialog result: {result!r}').show()

    @route
    def add_to(self) -> None:
        with list_directory(view='sets') as kdir:
            kdir.action('Add-to dialog', self.add_to_dialog)
            kdir.action('New-list dialog', self.new_list_dialog)
            kdir.folder('Example items', info_for(self.item_examples))

    def _item_examples(self) -> Sequence[MediaRef]:
        from ..defs import VideoIds
        tmdb = VideoIds.ffid_from_tmdb_id
        items = [
            MediaRef('movie', tmdb(78)),
            MediaRef('show', tmdb(119051)),
            MediaRef('show', tmdb(1434), 2),
            MediaRef('show', tmdb(2734), 3, 4),
            MediaRef('person', tmdb(190)),
            MediaRef('collection', tmdb(726871)),
            MediaRef('genre', tmdb(12)),
            # MediaRef('list', 123),  # not-supported
        ]
        return items

    @item_folder_route
    def item_examples(self) -> Sequence[MediaRef]:
        return self._item_examples()

    @route
    def add_to_dialog(self) -> None:
        from ..windows.add_to import AddToDialog, ListInfo
        from ..ff.control import notification
        items = self._item_examples()
        win = AddToDialog(items=items)
        lst: Optional[ListInfo] = win.doModal()
        fflog(f'Add-to dialog {lst=}')
        if lst:
            num = lst.add_items(items=items)
            notification(L(30476, 'Add to {pointer} list').format(pointer=lst.service.pointer),
                         L(30478, 'Added {n} item to {name}|||Added {n} items to {name}', n=num, name=lst.name), visible=True)

    @route
    def new_list_dialog(self) -> None:
        from ..windows.new_list import NewWindowDialog
        win = NewWindowDialog()
        result = win.doModal()
        fflog(f'New-list dialog {result=}')

    @route
    def video_db(self) -> None:
        import sys
        from ..ff.kodidb import video_db
        # video_db.get_players()
        # video_db.get_player_item()
        x = tuple(video_db.get_library('movie'))
        fflog(f'ITEMS count {len(x)}')
        if x:
            fflog(f'First item {x[0]}')
        sys.exit(0)

    @route
    def send_notif(self) -> None:
        # import json
        # import xbmc
        # req = json.dumps({
        #     'id': 123,
        #     'jsonrpc': '2.0',
        #     'method': 'JSONRPC.NotifyAll',
        #     'params': {
        #         'sender': 'Dupa',
        #         'message': 'Blada',
        #         'data': {'a': 42},
        #     },
        # })
        # fflog(f'RPC {req = }')
        # resp = xbmc.executeJSONRPC(req)
        # fflog(f'RPC {resp = }')
        from ..ff.kotools import KodiRpc
        req  = {'dupa': 'blada'}
        fflog(f'RPC {req  = }')
        T = monotonic()
        resp = KodiRpc().service_call('ServicePing', req, timeout=3)
        T = monotonic() - T
        fflog(f'RPC {resp = }  [{T:.3f}s]')

    @route
    def test_gui(self) -> None:
        from ..windows.base_window import BaseDialog

        class Test(BaseDialog):
            XML = 'Test.xml'

        Test().doModal()

    @route
    def library(self) -> None:
        from ..ff.kodidb import video_db
        video_db.get_library('movie')
        with list_directory(view='sets') as kdir:
            kdir.folder('Mixed', info_for(self.library_items))
            for media in ('movie', 'show', 'season', 'episode'):
                kdir.folder(media.capitalize(), info_for(self.library_items, media=media))

    @item_folder_route('/library/media/{__media}')
    @pagination(20)
    def library_items(self, media: Optional[Literal['movie', 'show', 'season', 'episode']] = None):
        from ..ff.kodidb import video_db
        return Folder(video_db.get_library_ffitems(media), alone=True)
        # items = video_db.get_library_dict(media)
        # return Folder([it.ffitem() for ref, it in items.items() if not media or media == ref.real_type], alone=True)

    @route
    def test_settings(self) -> None:
        from ..ff.settings import settings
        for name in (
            # 'library.service.update',
            # 'library.days_delay',
            'movie.download.path',
        ):
            print_settings(name)
            fflog(f'DEF: {settings.definitions[name]}')
            val = settings.eval(f'0 or {name}')
            # val = settings.eval(f'0 or {{{name}}}')
            fflog(f'VAL: {val}')
        print(settings.eval('{schedCleanMetaCache}'))
