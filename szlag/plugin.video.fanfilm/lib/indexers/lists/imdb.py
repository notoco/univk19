from typing import Optional, Sequence
from typing_extensions import Literal
from ..core import Indexer
from ..folder import item_folder_route, pagination, ApiPage, FolderRequest, list_directory
from ...ff.routing import route, info_for, PathArg
from ...ff.menu import directory
from ...ff.settings import settings
from ...api.imdb import ImdbScraper
from ...defs import MainMediaType, Pagina, MediaRef
from ...kolang import L
# from ...ff.log_utils import fflog
from const import const


class ImdbLists(Indexer):

    @route('/')
    def home(self) -> None:
        """User IMDB lists."""
        # imdb = ImdbScraper()
        with directory(view='sets') as kdir:
            # kdir.folder(L(30146, 'Favorites'), self.favorites, thumb='DefaultMovies.png')
            kdir.folder(L(32033, 'Watchlist'), self.watchlists, thumb='services/imdb/watchlist.png')
            kdir.folder(L(30149, 'My Lists'), self.mine, thumb='services/imdb/my.png')

    @route
    def watchlists(self) -> None:
        with list_directory(view='sets') as kdir:
            if const.indexer.imdb.watchlist.mixed:
                kdir.folder(L(30159, 'Mixed Watchlist'), info_for(self.watchlist), thumb='services/imdb/watchlist.png')
            kdir.folder(L(30160, 'Watchlist Movies'), info_for(self.watchlist, media='movie'), thumb='services/imdb/watchlist.png')
            kdir.folder(L(30161, 'Watchlist TV Shows'), info_for(self.watchlist, media='show'), thumb='services/imdb/watchlist.png')

    @item_folder_route
    def watchlist(self,
                  req: FolderRequest,
                  /, *,
                  user: Optional[str] = None,
                  media: Optional[Literal['movie', 'show']] = None,
                  page: PathArg[int] = 1,
                  ) -> Sequence[MediaRef]:
        """Return IMDB watchlist items."""
        imdb = ImdbScraper()
        if not user:
            user = settings.getString('imdb.user')
        items = imdb.watch_list(user, media_type=media)
        if req.as_folder:
            items = Pagina(items, page=page, limit=const.indexer.imdb.page_size)
        return items

    @route
    def mine(self, media: Optional[MainMediaType] = None) -> None:
        """Show IMDB lists."""
        imdb = ImdbScraper()
        user = settings.getString('imdb.user')
        kwargs = {'media': media} if media else {}
        with list_directory(view=const.indexer.imdb.mine.view) as kdir:
            for it in imdb.user_lists(user):
                # it.mode = it.Mode.Folder
                kdir.add(it, url=info_for(self.user_list, list_id=it.vtag.getIMDBNumber(), **kwargs), thumb='services/imdb/lists.png')

    # page_size=const.indexer.imdb.page_size
    @item_folder_route('list/{list_id}')
    @pagination(api=ApiPage(size=250))
    def user_list(self,
                  req: FolderRequest, /, *,
                  list_id: str,
                  media: Optional[Literal['movie', 'show']] = None,
                  page: PathArg[int] = 1,
                  ) -> Sequence[MediaRef]:
        """Return the list items."""
        imdb = ImdbScraper()
        items = imdb.list(list_id, media_type=media, page=page)
        return items
