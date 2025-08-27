
from typing import Optional, List, Sequence
import re
from .core import Indexer, Job
from .search import Search
from .folder import list_directory, item_folder_route, pagination, ApiPage, FolderRequest, mediaref_endpoint
from .lists import ListsInfo
from ..ff.info import ffinfo
from ..ff.routing import route, subobject, url_for, info_for, PathArg
from ..ff.menu import KodiDirectory, directory, ContextMenuItem
from ..ff.item import FFItem
from ..ff.tmdb import tmdb
from ..defs import MediaRef, FFRef
from ..kolang import L
from const import const


class Persons(Indexer):
    """Persons navigation (a little bit degraded)."""

    MODULE = 'persons'
    TYPE = 'person'
    VIEW = 'actors'
    IMAGE = 'common/people.png'
    SEARCH_ICON = 'common/search.png'

    @route('/')
    def home(self) -> None:
        """Create root / main menu."""
        linfo = ListsInfo()
        with list_directory(view='addons', icon='persons/main.png') as kdir:
            kdir.folder(L(32010, 'Search'), self.search, thumb='persons/search.png')
            kdir.folder(L(32018, 'Most Popular'), info_for(self.popular), thumb='persons/featured.png')
            if linfo.own_enabled() and const.indexer.persons.my_lists.enabled:
                if const.indexer.persons.my_lists.flat:
                    from .navigator import nav
                    # nav.own.add_mine(kdir, favorites=True, media='person', flat=const.indexer.persons.my_lists.root.flat)
                    kdir.folder(L(30348, 'Own Favorites'), info_for(nav.own.favorites, media='person'), thumb='persons/favorites.png')
                    nav.own.add_generic_lists(kdir, media='person', favorites=False, icon='persons/main.png')
                    kdir.folder(L(30327, 'My Own Lists'), url_for(nav.own.mine, media='person'), thumb='persons/lists.png')
                else:
                    kdir.folder(L(30328, 'My Persons'), self.lists, thumb='persons/my.png', icon='DefaultVideoPlaylists.png')

    @subobject
    def search(self) -> 'Search':
        """Search submodule."""
        return Search(indexer=self, type='person')

    @route
    def lists(self) -> None:
        """My person lists."""
        from .navigator import nav
        linfo = ListsInfo()
        with list_directory(view='sets', icon='persons/main.png') as kdir:
            if linfo.own_enabled():
                kdir.folder(L(30348, 'Own Favorites'), url_for(nav.own.favorites, media='person'), thumb='services/own/favorites_persons.png')
                kdir.folder(L(30327, 'My Own Lists'), url_for(nav.own.mine, media='person'), thumb='userservices/own/lists.png')

    @item_folder_route('/popular', limit=const.indexer.persons.discovery_scan_limit)
    @pagination(api=ApiPage(size=20))
    def popular(self, req: FolderRequest, /, *, page: PathArg[int] = 1) -> Sequence[FFRef]:
        """Return poplular people (TMDB)."""
        return tmdb.popular_people(page=page)

    def do_show_item(self, kdir: KodiDirectory, it: FFItem, *, alone: bool, link: bool, menu: List[ContextMenuItem]) -> None:
        """Process discover item. Called from discover()."""
        it.label = f'{it.title}'
        it.mode = it.Mode.Folder
        url = info_for(self.person, person_id=it.ffid)
        kdir.add(it, url=url, auto_menu=self.item_auto_menu(it, kdir=kdir), menu=menu, thumb='common/peopleposter.png',)

    @mediaref_endpoint(param_ref_ffid='person_id')
    @route('/{person_id}')
    def person(self, person_id: int) -> None:
        """Show person."""
        ref = MediaRef.person(person_id)
        it = ffinfo.get_item(ref)
        if it is None:
            return self.no_content()
        it.mode = it.Mode.Separator
        it.label = f'[B]{it.title}[/B]'
        with list_directory(view='artists') as kdir:
            kdir.add(it, url=kdir.no_op)
            kdir.folder(L(32001, 'Movies'), info_for(self.movie, person_id=person_id),
                        thumb='movies/main.png', icon='movies/main.png')
            kdir.folder(L(32002, 'TV Shows'), info_for(self.show, person_id=person_id),
                        menu=[(L(30473, 'TV Appearances'), info_for(self.show, person_id=person_id, include_self=True))],
                        thumb='tvshows/main.png', icon='tvshows/main.png')
            kdir.folder(L(30178, 'Director'), info_for(self.crew, person_id=person_id, job='director'), thumb='persons/main.png')
            kdir.folder(L(30179, 'Producer'), info_for(self.crew, person_id=person_id, job='producer'), thumb='persons/main.png')

    @item_folder_route('/{person_id}/movie')
    @pagination
    def movie(self, person_id: int):
        credits = tmdb.person_credits(person_id, 'movie_credits')
        return credits.cast

    @item_folder_route('/{person_id}/show')
    @pagination
    def show(self, person_id: int, include_self: Optional[bool] = None):
        credits = tmdb.person_credits(person_id, 'tv_credits')
        if include_self is None:
            include_self = const.indexer.persons.show.include_self
        if not include_self:  # filter out self appearances
            r = re.compile(r'\b(?:Self|Herself|Himself)\b')
            return [it for it in credits.cast if not r.search(it.role)]
        return credits.cast

    @item_folder_route('/{person_id}/crew')
    @pagination
    def crew(self, person_id: int, job: Optional[PathArg[Job]] = None):
        credits = tmdb.person_credits(person_id, 'combined_credits')
        jobs = self._jobs.get(job, set())
        if jobs:
            crew = [c for c in credits.crew if c.role in jobs]
        else:
            crew = [c for c in credits.crew if c.role != 'Thanks']
        return crew
