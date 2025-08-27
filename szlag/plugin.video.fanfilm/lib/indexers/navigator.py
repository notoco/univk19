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

from typing import Optional, Union, Dict, Sequence, Callable, TYPE_CHECKING
from typing_extensions import Literal, cast
from inspect import unwrap
from attrs import asdict

from ..ff import control
from ..ff.log_utils import fflog
from ..ff.menu import directory, ContentView, KodiDirectoryKwArgs, KodiDirectory
from ..ff.routing import route, subobject, MainRouteObject, PathArg
from ..ff.tricks import singleton
from ..ff.info import ffinfo, ItemInfoKwargs
from ..ff.item import FFItem
from ..ff.types import PagedItemList
from ..defs import MediaRef, VideoIds
from ..kolang import L
from .folder import filter_kwargs, mediaref_endpoint
from .core import ShowItemKwargs, ShowItemOnlyKwargs, Indexer
from .lists import ListsInfo
from const import const
if TYPE_CHECKING:
    from typing_extensions import Unpack
    from .search import Search
    from .movies import Movies
    from .tvshows import TVShows
    from .persons import Persons
    from .stump import Keywords
    from .stump import Companies
    from .collections import Collections
    from .lists.trakt import TraktLists
    from .lists.tmdb import TmdbLists
    from .lists.imdb import ImdbLists
    from .lists.mdblist import MDBListIndexer
    from .lists.own import OwnLists
    from .history import History
    from .tools import Tools
    from .dev_tests import DevMenu


def reset() -> None:
    """Reset navigator stuff for reuse code (re-run in the same Python interpreter)."""
    ...


reset()


# -- Global routes, MUST be on top of the Navigator. --


@mediaref_endpoint
@route('/play/{ref}')
def play(ref: MediaRef, *, edit: bool = False) -> None:
    """Play any video (movie, episode)."""
    from ..ff.sources import sources
    print(f'play({ref}) ...')
    if ref.ffid in VideoIds.KODI:
        ref = ref._replace(ffid=ref.ffid + VideoIds.TMDB.start)
    if ref.type in ('movie', 'show'):
        sources().play(ref.type, ref.ffid, ref.season, ref.episode, edit_search=edit)


# URL for FF3-alfa tests only. TODO: Remove before release.
@mediaref_endpoint(param_ref_ffid='tv_ffid')
@route('/play/tvshow')
def play_tvshow(tv_ffid: PathArg[int], season: PathArg[int], episode: PathArg[int], *, edit: bool = False) -> None:
    """Play tv-show episode video. Only for support FF3 alpha links."""
    from ..ff.sources import sources
    print(f'play.tvshow({tv_ffid=}, {season=}, {episode=}) ...')
    sources().play('show', tv_ffid, season, episode, edit_search=edit)


# Example for FF2 library links. Keep it for compatibility.
#  plugin://plugin.video.fanfilm/?action=play&name=Rebel+Moon+-+Part+One%3A+A+Child+of+Fire+%282023%29&title=Rebel+Moon+-+Part+One%3A+A+Child+of+Fire&localtitle=Rebel+Moon+%E2%80%93+cz%C4%99%C5%9B%C4%87+1%3A+Dziecko+Ognia&year=2023&imdb=tt14998742&tmdb=848326
#  plugin://plugin.video.fanfilm/?action=play&title=What+If...+Strange+Supreme+Intervened%3F&year=2021&imdb=tt10168312&tmdb=91363&season=2&episode=9&tvshowtitle=What+If...%3F&date=2023-12-30


# Kolejność ma znaczenie, old_play_tvshow() musi być nad old_play_movie(),
# bo inaczej filmy zjedzą seriale (mają podzbiór argumentów, więc trafią).
@route('/')
def old_play_tvshow(action: Literal['play'], tmdb: int, season: int, episode: int, **kwargs) -> None:
    """Play movie video in old API (up to FanFilm 2023)."""
    ffid = VideoIds(tmdb=tmdb, imdb=kwargs.get('imdb')).ffid
    if ffid:
        fflog(f'old play.tvshow({tmdb=}, {season=}, {episode=}):  {ffid=} ...')
        play(MediaRef('show', ffid, season, episode))
    else:
        fflog(f'old play.tvshow({tmdb=}, {season=}, {episode=}):  {ffid=} FAILED')


# Musi być po serialach, patrz komentarz wyżej.
@route('/')
def old_play_movie(action: Literal['play'], tmdb: int, **kwargs) -> None:
    """Play movie video in old API (up to FanFilm 2023)."""
    ffid = VideoIds(tmdb=tmdb, imdb=kwargs.get('imdb')).ffid
    if ffid:
        fflog(f'old play.movie({tmdb=}):  {ffid=} ...')
        play(MediaRef('movie', ffid))
    else:
        fflog(f'old play.movie({tmdb=}):  {ffid=} FAILED')


# --- Heler: Multi-search indexer. ---

class MultiSearch(Indexer):
    """Indexer used for multi search."""

    @subobject
    def search(self) -> 'Search':
        """Multi search submodule."""
        from .search import Search
        return Search(indexer=self, type='multi')


# -- The Navigator. --

@singleton
class Navigator(MainRouteObject):
    """Głowne menu FanFilm."""

    @route('/')
    def home(self) -> None:
        """Create root / main menu."""
        # UWAGA: W tym miejscu zostały użyte nietypowe odwołania sięgające przez klasę (np. Navigator.movie)
        #        a nie przez właściwość (np. self.movie). Jest to użyte WYŁĄCZNIE w celach optymalizacji,
        #        nie trzeba wtedy ładować wszystkich modułów na start. Link wskazuje na cały moduł, nie może
        #        tak wskazać na metodę modułu.
        #        Niezbędnym warunkiem działania są:
        #          - @subobject na wskazanym miejscu (np. w def movie),
        #          - @route('/') w klasie pod-obiektu (np. w Movies).
        # To działa TYLKO w Navigatorze (głównym obiekcie). NIE używać w innych klasach.
        with directory() as kdir:
            if const.debug.dev_menu:
                kdir.folder('« DEV »', Navigator.dev, thumb='featured.png')
            kdir.folder(L(32001, 'Movies'), Navigator.movie, thumb='movies/main.png', icon='DefaultMovies.png')
            kdir.folder(L(32002, 'TV Shows'), Navigator.show, thumb='tvshows/main.png', icon='DefaultTVShows.png')
            if const.indexer.persons.enabled:
                kdir.folder(L(30175, 'Persons'), Navigator.person, thumb='persons/main.png', icon='DefaultActor.png')
            if const.indexer.navigator.lists_folder:
                # add "my lists" to fake directory to check if any exists
                fake = KodiDirectory()
                self.add_my_lists_entries(fake)
                if fake.items:
                    kdir.folder(L(30471, 'Lists'), self.lists, thumb='services/own/main.png')
            else:
                self.add_my_lists_entries(kdir)
            kdir.folder(L(32036, 'History'), Navigator.history, thumb='common/history.png')
            kdir.folder(L(32008, 'Tools'), Navigator.tools, thumb='common/tools.png')
            kdir.folder(L(32010, 'Search'), self.search, thumb='common/search.png')  # self.search jest lokalnie

    @route
    def search(self) -> None:
        """Main search menu."""
        with directory(thumb='search.png') as kdir:
            kdir.folder(L(32001, 'Movies'), self.movie.search, thumb='movies/search.png', icon='DefaultMovies.png')
            kdir.folder(L(32002, 'TV Shows'), self.show.search, thumb='tvshows/search.png', icon='DefaultTVShows.png')
            kdir.folder(L(30175, 'Persons'), self.person.search, thumb='persons/search.png', icon='people-search.png')
            kdir.folder(L(30137, 'Keywords'), self.keyword.search, thumb='common/search_keywords.png')
            kdir.folder(L(30138, 'Companies'), self.company.search, thumb='common/search_companies.png')
            kdir.folder(L(30151, 'Movies Collection'), self.collection.search, thumb='common/search_collection.png')
            if const.indexer.search.multi_search:
                kdir.folder(L(30472, 'Multi search'), self.multi.search, thumb='common/search.png')

    @subobject
    def multi(self) -> MultiSearch:
        """Multi search submodule."""
        return MultiSearch()

    @route
    def settings(self) -> None:
        """Open the settings."""
        control.openSettings()
        # control.execute("Dialog.Close(busydialognocancel)")

    def add_my_lists_entries(self, kdir: KodiDirectory):
        """Add user lists folder entries (for all services)."""
        linfo = ListsInfo()
        if linfo.trakt_enabled():
            kdir.folder(L(30164, 'My Trakt Lists'), Navigator.trakt, thumb='services/trakt/lists.png')
            # kdir.folder(L(30176, 'Trakt'), Navigator.trakt, thumb='trakt.png')
        if linfo.tmdb_enabled():
            kdir.folder(L(30165, 'My TMDB Lists'), Navigator.tmdb, thumb='services/tmdb/lists.png')
            # kdir.folder(L(32775, 'TMDB'), Navigator.tmdb, thumb='tmdb.png')
        if linfo.imdb_enabled():
            kdir.folder(L(30349, 'My IMDB Lists'), Navigator.imdb, thumb='services/imdb/lists.png')
            # kdir.folder(L(30177, 'IMDB'), Navigator.imdb, thumb='imdb.png')
        if linfo.mdblist_enabled():
            kdir.folder(L(30367, 'My MDBList Lists'), Navigator.mdblist, thumb='services/mdblist/lists.png')
        if linfo.own_enabled():
            kdir.folder(L(30327, 'My Own Lists'), Navigator.own, thumb='services/own/lists.png')

    @route('/list')
    def lists(self) -> None:
        """User lists (for all services)."""
        with directory(view='sets') as kdir:
            self.add_my_lists_entries(kdir)

    @route
    def noop(self) -> None:
        ...

    def show_items(self,
                   items: Sequence[Union[FFItem, MediaRef]],
                   *,
                   # Current page number (starts from one) or None for single/first page. Is ignored at this moment (PagedItemList.page is used).
                   page: Optional[int] = None,
                   # All directory (kdir), ffinfo.get_items and Indexer.show_item arguments.
                   **kwargs: 'Unpack[ShowItemKwargs]',
                   ) -> None:
        """Show items in directory, select movie, tvshow or else."""
        # find all used types
        types = {it.ref.real_type for it in items if it}
        # only one type, view could be selected
        if len(types) == 1:
            mtype = next(iter(types))
            if mtype == 'movie':
                return self.movie.show_items(items, **kwargs)
            if mtype == 'show':
                return self.show.show_items(items, **kwargs)
            if mtype == 'season':
                return self.show.show_items(items, **{'view': 'seasons', **kwargs})
            if mtype == 'episode':
                return self.show.show_items(items, **{'view': 'episodes', **kwargs})
            if mtype in ('person', 'collection', 'keyword', 'company'):
                return getattr(self, mtype).show_items(items, **kwargs)
        # no so good known type or mixed types
        pg_items = cast(PagedItemList, items)  # directory() check if items object is PagedItemList type
        count = 0
        if kwargs.get('view') is None:
            kwargs['view'] = 'videos'  # default view for mixed items
        role_format = kwargs.get('role_format')
        dir_kwargs = filter_kwargs(KodiDirectoryKwArgs, kwargs)
        with directory(pg_items, **dir_kwargs) as kdir:
            show_kwargs = filter_kwargs(ShowItemOnlyKwargs, kwargs)
            show_kwargs.setdefault('alone', True)
            get_kwargs = filter_kwargs(ItemInfoKwargs, kwargs)
            if not kwargs.get('skip_ffinfo'):
                items = ffinfo.get_items(items, **get_kwargs, duplicate=False, keep_missing=False)
            for it in items:
                count += 1
                mtype = it.ref.type
                if callable(role_format):
                    it.role = role_format(it, count)
                elif role_format is not None:
                    it.role = role_format.format(it=it, item=it, ref=it.ref, index=count, title=it.title, year=it.year)
                if mtype == 'movie':
                    self.movie.show_item(kdir, it, **show_kwargs)
                elif mtype in ('show', 'season', 'episode'):
                    self.show.show_item(kdir, it, **show_kwargs)
                elif mtype in ('person', 'collection', 'keyword', 'company'):
                    getattr(self, mtype).show_item(kdir, it, **show_kwargs)
                else:
                    it.mode = it.Mode.Separator
                    kdir.add(it, url=kdir.no_op)
            if not count:
                kdir.no_content('sets', empty_message=kwargs.get('empty_message'))

    @subobject
    def movie(self) -> 'Movies':
        """Menu /movie."""
        from .movies import Movies
        return Movies()

    @subobject
    @subobject('/tvshow')  # URL for FF3-alfa tests only. TODO: Remove before release.
    def show(self) -> 'TVShows':
        """Menu /show."""
        from .tvshows import TVShows
        return TVShows()

    @subobject
    def person(self) -> 'Persons':
        """Menu /person."""
        from .persons import Persons
        return Persons()

    @subobject
    def keyword(self) -> 'Keywords':
        """Menu /keyword."""
        from .stump import Keywords
        return Keywords()

    @subobject
    def company(self) -> 'Companies':
        """Menu /keyword."""
        from .stump import Companies
        return Companies()

    @subobject
    def collection(self) -> 'Collections':
        """Menu /collection (TMDB collections)."""
        from .collections import Collections
        return Collections()

    @subobject
    def trakt(self) -> 'TraktLists':
        """Menu /trakt (trakt lists)."""
        from .lists.trakt import TraktLists
        return TraktLists()

    @subobject
    def tmdb(self) -> 'TmdbLists':
        """Menu /tmdb (tmdb lists)."""
        from .lists.tmdb import TmdbLists
        return TmdbLists()

    @subobject
    def imdb(self) -> 'ImdbLists':
        """Menu /imdb (imdb lists)."""
        from .lists.imdb import ImdbLists
        return ImdbLists()

    @subobject
    def mdblist(self) -> 'MDBListIndexer':
        """Menu /mdblist (mdblist lists)."""
        from .lists.mdblist import MDBListIndexer
        return MDBListIndexer()

    @subobject
    def own(self) -> 'OwnLists':
        """Menu /own (user own lists, like favorites or custom)."""
        from .lists.own import OwnLists
        return OwnLists()

    @subobject
    def history(self) -> 'History':
        """Menu /history."""
        from .history import History
        return History()

    @subobject
    def tools(self) -> 'Tools':
        """Menu /tools."""
        from .tools import Tools
        return Tools()

    @subobject
    def dev(self) -> 'DevMenu':
        """Developer menu."""
        from .dev_tests import DevMenu
        return DevMenu()


# singleton
nav = Navigator()
