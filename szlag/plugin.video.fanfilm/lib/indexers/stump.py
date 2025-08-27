"""
Any stump indexer is here.
"""

from typing import List, ClassVar
from typing_extensions import TypeAlias, Literal

from .core import Indexer
from .search import Search
from ..defs import VideoIds
from ..ff.routing import route, subobject, url_for, PathArg
from ..ff.menu import KodiDirectory, directory, ContextMenuItem
from ..ff.item import FFItem
from ..api.tmdb import DiscoveryFilters
from ..kolang import L
from const import const

StumpDiscoverFilter: TypeAlias = Literal['with_keywords', 'with_companies', 'with_networks']


class StumpIndexer(Indexer):

    DISCOVER_FILTER: ClassVar[StumpDiscoverFilter]

    @subobject
    def search(self) -> 'Search':
        """Search submodule."""
        return Search(indexer=self)

    @route('/{oid}/movie')
    def movie(self, oid: int, page: PathArg[int] = 1) -> None:
        from .navigator import nav
        oid = VideoIds.tmdb_id(oid)
        filters: DiscoveryFilters = {self.DISCOVER_FILTER: str(oid)}
        nav.movie.discover(page=page, votes=const.indexer.stump.votes, **filters)

    @route('/{oid}/show')
    def show(self, oid: int, page: PathArg[int] = 1) -> None:
        from .navigator import nav
        oid = VideoIds.tmdb_id(oid)
        filters: DiscoveryFilters = {self.DISCOVER_FILTER: str(oid)}
        nav.show.discover(page=page, votes=const.indexer.stump.votes, **filters)

    def do_show_item(self, kdir: KodiDirectory, it: FFItem, *, alone: bool, link: bool, menu: List[ContextMenuItem]) -> None:
        """Process stump search item. Called from search_items()."""
        # kdir.folder(name, url_for(self.item, oid=oid))
        it.mode = it.Mode.Folder
        it.url = str(url_for(self.item, oid=it.ffid))
        kdir.add(it, menu=menu)

    @route('/')
    def item(self, oid: PathArg[int]) -> None:
        with directory(view='addons') as kdir:
            kdir.folder(L(32001, 'Movies'), url_for(self.movie, oid=oid),
                        thumb='movies/main.png', icon='DefaultMovies.png')
            kdir.folder(L(32002, 'TV Shows'), url_for(self.show, oid=oid),
                        thumb='tvshows/main.png', icon='DefaultTVShows.png')


class Keywords(StumpIndexer):

    MODULE = 'keywords'
    DISCOVER_FILTER = 'with_keywords'
    VIEW = 'tags'
    TYPE = 'keyword'
    IMAGE = 'common/keywords.png'


class Companies(StumpIndexer):

    MODULE = 'company'
    DISCOVER_FILTER = 'with_companies'
    VIEW = 'studios'
    TYPE = 'company'
    IMAGE = 'common/companies.png'
