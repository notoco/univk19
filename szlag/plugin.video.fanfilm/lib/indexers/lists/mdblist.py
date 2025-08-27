
from typing import Optional, TYPE_CHECKING
from ...defs import MainMediaType, Pagina
from ..core import Indexer
from ...ff.routing import route, info_for
from ..folder import list_directory, item_folder_route
from ...api.mdblist import mdblist
from ...kolang import L
from const import const
if TYPE_CHECKING:
    from ...ff.menu import KodiDirectory


class MDBListIndexer(Indexer):
    """Indexer for MDBList service (user lists)."""

    @route('/')
    def home(self) -> None:
        """User MDBList lists."""
        with list_directory(view='sets') as kdir:
            # kdir.folder(L(30144, 'Likes'), info_for(self.likes), thumb='highly-rated.png')  # Not in API yet
            kdir.folder(L(32033, 'Watchlist'), info_for(self.watchlist), thumb='services/mdblist/watchlist.png')
            kdir.folder(L(30148, 'Popular Lists'), info_for(self.top_lists), thumb='services/mdblist/popular.png')
            if const.indexer.mdblist.root.flat:
                self._add_mine(kdir, page=0)
            else:
                kdir.folder(L(30149, 'My Lists'), self.mine, thumb='services/mdblist/my.png')

    @route('/mine/{__page}')
    def mine(self, *, page: int = 1, user: Optional[str] = None, media: Optional[MainMediaType] = None):
        """Show my lists and my likes."""
        with list_directory(view=const.indexer.mdblist.mine.view) as kdir:
            self._add_mine(kdir, page=page, user=user, media=media)

    @route('/mine/{__page}')
    def _add_mine(self, kdir: 'KodiDirectory', *, page: int = 1, user: Optional[str] = None, media: Optional[MainMediaType] = None):
        """Show my lists and my likes."""
        items = sorted(mdblist.user_lists(user=user, media=media), key=lambda x: x.title.lower())
        items = Pagina(items, page=page, limit=const.indexer.mdblist.page_size)
        for it in items:
            kdir.add(it, url=info_for(self.list_items, list_id=it.ffid, media=media), thumb='services/mdblist/lists.png')

    @item_folder_route('/watchlist', list_spec='mdblist:watchlist')
    def watchlist(self, *, media: Optional[MainMediaType] = None):
        """Show watchlist."""
        return mdblist.watchlist_items(media=media)

    @item_folder_route('/list/{list_id}', list_spec='mdblist:user:{list_id}')
    def list_items(self, list_id: int, *, page: int = 1, media: Optional[MainMediaType] = None):
        """Show items in a list."""
        return mdblist.list_items(list_id=list_id, page=page, media=media)

    @route('/top/{__page}')
    def top_lists(self, *, page: int = 1, media: Optional[MainMediaType] = None):
        """Show top lists."""
        # return mdblist.top_lists(media=media)
        with list_directory(view=const.indexer.mdblist.top.view) as kdir:
            items = mdblist.top_lists(media=media)
            items = Pagina(items, page=page, limit=const.indexer.mdblist.page_size)
            for it in items:
                kdir.add(it, url=info_for(self.list_items, list_id=it.ffid, media=media), thumb='services/mdblist/lists.png')
