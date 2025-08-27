
from typing import Optional, List

from .core import Indexer
from .folder import mediaref_endpoint, item_folder_route, add_to, AddToService
from .search import Search
from ..ff.routing import route, subobject, info_for
from ..ff.item import FFItem
from ..ff.menu import KodiDirectory, directory, ContextMenuItem
from ..ff.tmdb import tmdb
from ..defs import MediaRef
from ..kolang import L


class Collections(Indexer):
    """
    Collections navigation (a little bit degraded).

    The collection is both:
      - item to add
      - folder with movies to add.
    """

    MODULE = 'collections'
    TYPE = 'collection'
    VIEW = 'sets'
    IMAGE = 'movies/collection.png'

    @subobject
    def search(self) -> 'Search':
        """Search submodule."""
        return Search(indexer=self, type='collection')

    def do_show_item(self, kdir: KodiDirectory, it: FFItem, *, alone: bool, link: bool, menu: List[ContextMenuItem]) -> None:
        """Process stump search item. Called from search_items()."""
        # kdir.folder(name, url_for(self.item, oid=oid))
        it.mode = it.Mode.Folder
        url = info_for(self.item, oid=it.ffid)
        bottom = []
        if it.ffid:
            # Call dialog: add collection's movies to...
            bottom.append((L(30366, 'Add movies to...'), info_for(self.add_movies_to, oid=it.ffid)))
        kdir.add(it, url=url, auto_menu=self.item_auto_menu(it, kdir=kdir), menu=menu, menu_bottom=bottom, thumb='movies/collection.png')

    # @mediaref_endpoint(param_ref_ffid='oid')
    @item_folder_route('/{oid}')
    def item(self, oid: int):
        return tmdb.collection_items(oid)

    @route('/{oid}/add/movies/to/{__service_name}/{__list_name}')
    def add_movies_to(self,
                      oid: int,
                      service_name: Optional[AddToService] = None,
                      list_name: Optional[str] = None,
                      ):
        """Add collection's movies to..."""
        add_to(service=service_name, list_id=list_name, items=tmdb.collection_items(oid))
