
import sys  # for sys.exit
from typing import Optional

from xbmcgui import Dialog
from ..ff.routing import route, subobject, url_for, RouteObject
from ..ff.menu import directory
from ..ff.tmdb import tmdb
from ..ff.trakt import trakt
from ..api.imdb import ImdbScraper
from ..ff.control import refresh, infoDialog, yesnoDialog, busy_section, addonName, notification
from ..ff.settings import settings
from ..ff.db import state
from ..indexers.lists import ListsInfo
from ..service.client import service_client

# from ..ff.log_utils import fflog
from ..kolang import L
from .navigator import nav
from const import const


def yes_no(name: Optional[str] = None) -> bool:
    lines = [L(32056, 'Are you sure?')]
    if name is not None:
        lines.insert(0, name)
    return yesnoDialog(*lines)


class Cache(RouteObject):
    """Podmenu: /narzędzia/cache."""

    CLEAR_SOURCES_LABEL = L(30252, 'Clear cached source list')
    CLEAR_SEARCH_LABEL = L(30253, 'Clear search history')
    CLEAR_NETCACHE_LABEL = L(30474, 'Clear netcache')

    @route('/')
    def cache(self):
        with directory(view=const.indexer.tools.view, thumb='common/cache.png') as kdir:
            # kdir.action(32807, "clearCacheBookmarks")
            kdir.action(self.CLEAR_NETCACHE_LABEL, self.clear_netcache)
            # kdir.action(32639, "clearCacheMeta")
            kdir.action(self.CLEAR_SOURCES_LABEL, self.clear_sources)  # sources, clearCacheProviders
            kdir.action(self.CLEAR_SEARCH_LABEL, self.clear_search)       # clearCacheSearch
            # kdir.action(32794, "clearCacheAll")

    @route('/sources')
    def clear_sources(self) -> None:
        from ..ff import cache
        if yes_no(self.CLEAR_SOURCES_LABEL):
            with busy_section(complete_notif=True):
                cache.cache_clear_sources()
                cache.cache_clear_providers()

    @route('/search')
    def clear_search(self) -> None:
        from ..ff.db.db import db_manager
        if yes_no(self.CLEAR_SEARCH_LABEL):
            with busy_section(complete_notif=True):
                db_manager.remove_db('search')

    @route('/netcache')
    def clear_netcache(self) -> None:
        """Clear network cache."""
        if yes_no(self.CLEAR_NETCACHE_LABEL):
            with busy_section(complete_notif=True):
                from ..ff.requests import clear_netcache
                clear_netcache()


class Views(RouteObject):
    """Podmenu: /narzędzia/Widoki."""
    CLEAR_VIEW_LABEL = L(32640, 'Clear views...')
    VIEW_ITEMS = [
        (L(32001, 'Movies'), 'movies'),
        (L(32002, 'TV Shows'), 'tvshows'),
        (L(30302, 'Seasons'), 'seasons'),
        (L(30303, 'Episodes'), 'episodes'),
        (L(32032, 'Collection'), 'sets'),
        (L(30133, 'Actors'), 'actors'),
        (L(30304, 'Mixed lists'), 'videos'),
        (L(32011, 'Genres'), 'genres'),
        (L(30305, 'Menu'), 'addons'),
    ]

    @route('/')
    def views(self):
        """Menu wyboru widoków."""
        with directory(view=const.indexer.tools.view, thumb='common/views.png') as kdir:
            for label_id, view_type in self.VIEW_ITEMS:
                kdir.folder(label_id, url_for(self.set_views, type=view_type))
            kdir.action(self.CLEAR_VIEW_LABEL, self.clear_views)

    @route('/set_views/')
    def set_views(self, type: str) -> None:
        # TODO: use type: ContentView ???
        with directory(view=type) as kdir:
            kdir.action(L(32059, 'CLICK HERE TO SAVE VIEW'), url_for(self.addCustomView, type=type))

    @route('/addCustomView/')
    def addCustomView(self, type: str) -> None:
        from ..ff.views import view_manager
        view_manager.add_custom_view(type)

    @route
    def clear_views(self) -> None:
        from ..ff import cache
        if yes_no(self.CLEAR_VIEW_LABEL):
            with busy_section(complete_notif=True):
                cache.cache_clear_view()


class LibraryTools(RouteObject):
    """Podmenu: /narzędzia/library."""

    movie_library = settings.getString("library.movie")
    tv_library = settings.getString("library.tv")
    lists_info = ListsInfo()

    @route
    def sync_trakt_lib(self):
        for content_type, name in [('movie', 'auto trakt movies'), ('show', 'auto trakt tvshow')]:
            if items := trakt.user_collection(type=content_type):
                service_client.library_add(items, name=name)

    @route
    def sync_tmdb_lib(self):
        for content_type, name in [('movie', 'auto tmdb movies'), ('show', 'auto tmdb tvshow')]:
            if items := tmdb.user_general_lists(list_type='favorite', type=content_type):
                service_client.library_add(items, name=name)

    @route
    def sync_imdb_lib(self):
        imdb = ImdbScraper()
        user = settings.getString('imdb.user')
        for content_type, name in [('movie', 'auto imdb movies'), ('show', 'auto imdb tvshow')]:
            if items := imdb.watch_list(user, media_type=content_type):
                service_client.library_add(items, name=name)


    @route('/')
    def library(self):
        self.lists_info = ListsInfo()
        with directory(view=const.indexer.tools.view, thumb='common/library.png') as kdir:
            kdir.folder(L(32543, 'Movies'), self.movie_library, thumb='movies/main.png')
            kdir.folder(L(32544, 'TV Shows'), self.tv_library, thumb='tvshows/main.png')
            if self.lists_info.trakt_enabled():
                kdir.action(L(30314, 'Update Trakt collection'), self.sync_trakt_lib, thumb='services/trakt/update.png')
            if self.lists_info.tmdb_enabled():
                kdir.action(L(30315, 'Update TMDB collection'), self.sync_tmdb_lib, thumb='services/tmdb/update.png')
            if self.lists_info.imdb_enabled():
                kdir.action(L(30350, 'Update IMdb collection'), self.sync_imdb_lib, thumb='services/imdb/update.png')


class Download(RouteObject):
    """Podmenu: /narzędzia/download."""

    CLEAR_DOWNLOADER_LABEL = L(30227, 'Clear downloader cache')

    movie_downloads = settings.getString("movie.download.path")
    tv_downloads = settings.getString("tv.download.path")

    @route('/')
    def download(self):
        with directory(view=const.indexer.tools.view, thumb='common/downloads.png') as kdir:
            kdir.folder(L(30319, 'Movies downloaded'), f'{self.movie_downloads}', thumb='movies/download.png')
            kdir.folder(L(30320, 'TV Shows downloaded'), f'{self.tv_downloads}', thumb='tvshows/download.png')
            kdir.action(L(32807, 'Download manager'), self.download_manager, thumb='common/downloads.png')
            kdir.action(self.CLEAR_DOWNLOADER_LABEL, self.download_clear_cache)

    @route
    def download_manager(self) -> None:
        from lib.ff.downloader import downloadManager
        downloadManager()

    @route
    def download_clear_cache(self) -> None:
        from ..ff import cache
        if yes_no(self.CLEAR_DOWNLOADER_LABEL):
            with busy_section(complete_notif=True):
                cache.cache_clear_downloader()


class Tools(RouteObject):
    """Głowne menu FanFilm."""

    @route('/')
    def home(self) -> None:
        """Create root / main menu."""
        with directory(view=const.indexer.tools.view) as kdir:
            kdir.action(L(32806, 'Settings'), nav.settings, thumb='common/tools.png')
            kdir.folder(L(30368, 'Manage settings'), self.settings, thumb='common/tools.png')
            if tmdb.credentials():
                kdir.action(L(30183, 'TMDB: Revoke authorization'), self.tmdb_revoke, thumb='services/tmdb/main.png')
            else:
                kdir.action(L(30184, 'TMDB: Authorize'), self.tmdb_auth, thumb='services/tmdb/main.png')
            if trakt.credentials():
                kdir.action(L(30185, 'TRAKT: Revoke authorization'), self.trakt_revoke, thumb='services/trakt/main.png')
                if const.indexer.trakt.show_sync_entry:
                    kdir.action(L(30186, 'TRAKT: Synchronize'), self.trakt_sync, thumb='services/trakt/update.png')
            else:
                kdir.action(L(30187, 'TRAKT: Authorize'), self.trakt_auth, thumb='services/trakt/main.png')
            kdir.folder(L(32049, 'Viewtypes'), self.views, thumb='common/views.png')
            if settings.getBool('enable_library'):
                kdir.folder(L(32541, 'Library'), self.librarytools, thumb='common/library.png')
            if settings.getBool('downloads'):
                kdir.folder(L(30306, 'Downloaded'), self.download, thumb='common/downloads.png')
            kdir.folder(L(30254, 'Cache'), self.cache, thumb='common/cache.png')
            if const.tune.service.web_server.port:
                kdir.action(L(30373, 'FanFilm web server'), self.web_server, thumb='common/tools.png')

    @route('/tmdb/auth')
    def tmdb_auth(self) -> None:
        if tmdb.auth():
            infoDialog(L(30188, 'Authorization successful'), L(30189, '[FanFilm] TMDB authorization'), 'default')
        else:
            infoDialog(L(30190, 'Authorization FAILED'), L(30189, '[FanFilm] TMDB authorization'), 'ERROR')
        refresh()

    @route('/tmdb/revoke')
    def tmdb_revoke(self) -> None:
        if not tmdb.credentials or not yesnoDialog(L(32056, 'Are you sure?'), heading=L(30183, 'TMDB: Revoke authorization')):
            return
        if tmdb.unauth():
            infoDialog(L(30191, 'Revoke authorization successful'), L(30192, '[FanFilm] TMDB revoke authorization'), 'default')
        else:
            infoDialog(L(30193, 'Revoke authorization FAILED'), L(30192, '[FanFilm] TMDB revoke authorization'), 'ERROR')
        refresh()

    @route('/trakt/auth')
    def trakt_auth(self) -> None:
        if trakt.auth():
            infoDialog(L(30188, 'Authorization successful'), L(30194, '[FanFilm] Trakt.tv authorization'), 'default')
            state.add_job('service', 'trakt.sync', sender='plugin')
            refresh()
        else:
            infoDialog(L(30190, 'Authorization FAILED'), L(30194, '[FanFilm] Trakt.tv authorization'), 'ERROR')

    @route('/trakt/revoke')
    def trakt_revoke(self) -> None:
        if not trakt.credentials or not yesnoDialog(L(32056, 'Are you sure?'), heading=L(30185, 'TRAKT: Revoke authorization')):
            return
        if trakt.unauth():
            infoDialog(L(30191, 'Revoke authorization successful'), L(30195, '[FanFilm] Trakt.tv revoke authorization'), 'default')
        else:
            infoDialog(L(30193, 'Revoke authorization FAILED'), L(30195, '[FanFilm] Trakt.tv revoke authorization'), 'ERROR')
        refresh()

    @route('/trakt/sync')
    def trakt_sync(self) -> None:
        if not trakt.credentials:
            return
        status = trakt.sync()
        if status is not None:
            # TODO: notify about changed (True)?
            infoDialog(L(30196, 'Synchronize successful'), L(30197, '[FanFilm] Trakt.tv synchronize'), 'default')
        else:
            infoDialog(L(30198, 'Synchronize FAILED'), L(30197, '[FanFilm] Trakt.tv synchronize'), 'ERROR')

    @route('/colorpicker/open/{service}')
    def colorpicker(self, service: str, default: Optional[str] = None) -> None:
        from lib.ff.colorpicker import ColorPicker
        colorpicker = ColorPicker(default_color=default)
        colorpicker.run(service)
        sys.exit()

    @route('/colorpicker/save/{service}/{color}')
    def colorpicker_save(self, service: str, color: str) -> None:
        from lib.ff.colorpicker import ColorPicker
        colorpicker = ColorPicker('ColorPicker.xml')
        colorpicker.save_color(service, color)
        sys.exit()

    @route('/pairekino')
    def pairekino(self) -> None:
        from ..sources.pl.ekinotv import _source
        _source().pair_scraper()

    @subobject
    def cache(self) -> Cache:
        """Cache submenu."""
        return Cache()

    @subobject
    def views(self) -> Views:
        """Views submenu."""
        return Views()

    @subobject
    def download(self) -> Download:
        """Download submenu."""
        return Download()

    @subobject
    def librarytools(self) -> LibraryTools:
        """Library submenu."""
        return LibraryTools()

    @route
    def settings(self) -> None:
        with directory(view=const.indexer.tools.view) as kdir:
            kdir.action(L(30369, 'Clean settings'), self.clean_settings, thumb='common/tools.png')
            kdir.action(L(30370, 'Restore settings'), self.restore_settings, thumb='common/tools.png')
            kdir.action(L(30371, 'Backup settings'), self.backup_settings, thumb='common/tools.png')
            kdir.action(L(30497, 'Factory settings reset'), self.factory_settings_reset, thumb='common/tools.png')

    @route('/settings/factory_reset')
    def factory_settings_reset(self) -> None:
        addon = addonName()
        if Dialog().yesno(heading=L(30498, 'Reset {addon} settings').format(addon=addon),
                          message=L(30499, 'Reset settings to the factory defaults?\nThis will overwrite current settings!')):
            if settings.factory_reset():
                notification(addon, L(30500, 'Factory reset is done')).show()
            else:
                notification(addon, L(30501, 'Factory reset FAILED'), icon='ERROR').show()

    @route('/settings/clean')
    def clean_settings(self) -> None:
        addon = addonName()
        answer = 0
        changes = settings.clear_undefined(override_defaults=True, dry_run=True)
        # nothing to clear
        if changes is settings.Changes.NONE:
            Dialog().ok(addonName(), L(30502, 'Settings already cleared'))
            return
        # if there are changes with defaults update, ask for confirmation (yes/no/update_default)
        # elif changes is settings.Changes.DEFAULTS:
        if False:  # force to ask for confirmation
            answer = Dialog().yesnocustom(heading=L(30372, 'Clear {addon} settings').format(addon=addon),
                                          message=L(30373, ('Clear the setting?\nThis will remove undefined user settings.\n'
                                                            'You can override default values with the addon ones.')),
                                          customlabel=L(30495, 'Update defaults too'))
        # if there are changes without defaults update, ask for confirmation (yes/no)
        # elif changes is settings.Changes.CHANGED:
        if True:  # force to ask for confirmation
            answer = Dialog().yesno(heading=L(30372, 'Clear {addon} settings').format(addon=addon),
                                    message=L(30503, 'Clear the setting?\nThis will remove undefined user settings.'))
        if answer:
            override = answer == 2
            if settings.clear_undefined(override_defaults=override):
                notification(addon, L(30375, 'Settings cleared.')).show()
            else:
                notification(addon, L(30376, 'Clear settings FAILED.'), icon='ERROR').show()

    @route('/settings/backup')
    def backup_settings(self) -> None:
        addon = addonName()
        if Dialog().yesno(heading=L(30377, 'Backup {addon} settings').format(addon=addon),
                          message=L(30378, 'Create new setting\'s backup?')):
            if settings.make_backup():
                notification(addon, L(30379, 'Backup created.')).show()
            else:
                notification(addon, L(30380, 'Create backup FAILED.'), icon='ERROR').show()

    @route('/settings/restore')
    def restore_settings(self) -> None:
        addon = addonName()
        backups = settings.backup_files()
        if not backups:
            Dialog().ok(heading=L(30381, '{addon} Settings').format(addon=addon), message=L(30382, 'No backups available.'))
            return
        index = Dialog().select(heading=L(30383, 'Select a backup to restore'), list=[p.stem for p in backups])
        if index == -1:
            return
        backup = backups[index]
        if Dialog().yesno(heading=L(30384, 'Restore {addon} settings').format(addon=addon),
                          message=L(30385, 'Restore backup: {backup}?\nThis will overwrite current settings!').format(backup=backup.name)):
            if settings.restore_backup(backup):
                notification(addon, L(30386, 'Backup restored. Restart the plugin.')).show()
            else:
                notification(addon, L(30387, 'Restore backup FAILED.'), icon='ERROR').show()

    @route
    def web_server(self) -> None:
        from ..windows.site_auth import SiteAuthWindow
        from xbmc import getIPAddress
        url = f'http://{getIPAddress()}:{const.tune.service.web_server.port}'
        SiteAuthWindow(code='', qrcode=url, url=url, progress=False, title=L(30373, 'FanFilm web server')).doModal()
