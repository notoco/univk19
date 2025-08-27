from typing import Optional
from typing_extensions import Literal
from ..core import Indexer
from ..folder import item_folder_route, pagination, ApiPage, FolderRequest, list_directory, Folder
from ...ff.routing import route, info_for, PathArg
from ...ff.menu import KodiDirectory
from ...ff.tmdb import tmdb
from ...defs import MainMediaType, MainMediaTypeList
from ...kolang import L
# from ...ff.log_utils import fflog
from const import const

Sort = Literal['name', 'created_at', 'updated_at', 'item_count']  # not used yet


class TmdbLists(Indexer):

    @route('/')
    def home(self) -> None:
        """User TMDB lists."""
        with list_directory(view='sets') as kdir:
            kdir.folder(L(30146, 'Favorites'), self.favorites, thumb='services/tmdb/favorites.png', position='top')
            kdir.folder(L(32033, 'Watchlist'), self.watchlists, thumb='services/tmdb/watchlist.png', position='top')
            if const.indexer.tmdb.root.flat:
                self._mine(kdir)
            else:
                kdir.folder(L(30149, 'My Lists'), self.mine, thumb='services/tmdb/my.png')

    @route
    def favorites(self) -> None:
        with list_directory(view='sets') as kdir:
            if const.indexer.tmdb.favorites.mixed:
                kdir.folder(L(30156, 'Mixed Favorites'), info_for(self.favorite), thumb='services/tmdb/favorites.png')
            kdir.folder(L(30157, 'Favorite Movies'), info_for(self.favorite, media='movie'), thumb='services/tmdb/favorites.png')
            kdir.folder(L(30158, 'Favorite TV Shows'), info_for(self.favorite, media='show'), thumb='services/tmdb/favorites.png')

    @route
    def watchlists(self) -> None:
        with list_directory(view='sets') as kdir:
            if const.indexer.tmdb.watchlist.mixed:
                kdir.folder(L(30159, 'Mixed Watchlist'), info_for(self.watchlist), thumb='services/tmdb/watchlist.png')
            kdir.folder(L(30160, 'Watchlist Movies'), info_for(self.watchlist, media='movie'), thumb='services/tmdb/watchlist.png')
            kdir.folder(L(30161, 'Watchlist TV Shows'), info_for(self.watchlist, media='show'), thumb='services/tmdb/watchlist.png')

    def _mine(self, kdir: KodiDirectory, *, page: PathArg[int] = 1, media: Optional[MainMediaType] = None, sort: Optional[Sort] = 'name') -> None:
        """User TMDB lists."""
        kwargs = {} if media is None else {'media': media}

        # with kdir.item_mutate() as mutate:
        #     for it in tmdb.user_lists(page=page):
        #         kdir.add(it, url=info_for(self.user_list, list_id=it.ffid, **kwargs), thumb='services/tmdb/lists.png',)
        #     # sort via mutate, to skip Favorites and Watchlist if root flat is True
        #     mutate.isort('label')

        for it in tmdb.user_lists(page=page):
            kdir.add(it, url=info_for(self.user_list, list_id=it.ffid, **kwargs), thumb='services/tmdb/lists.png',)

        # test sortowania
        from xbmcplugin import addSortMethod, SORT_METHOD_LABEL
        addSortMethod(kdir.handle, SORT_METHOD_LABEL, '%L')

    @route
    def mine(self, *, page: PathArg[int] = 1, media: Optional[MainMediaType] = None) -> None:
        """User TMDB lists."""
        with list_directory(view=const.indexer.tmdb.mine.view) as kdir:
            self._mine(kdir, page=page, media=media)

    @item_folder_route('/list/{list_id}', list_spec='tmdb:user:{list_id}')
    @pagination(api=ApiPage(size=20))
    def user_list(self, list_id: int, *, page: PathArg[int] = 1, media: Optional[MainMediaType] = None):
        """Show TMDB user list."""
        items = tmdb.user_list_items(list_id, page=page)
        if media:
            items = items.with_content([it for it in items if it.type == media])
        return items

    @item_folder_route('favorite/{media}', list_spec='tmdb:favorites')
    @pagination(api=ApiPage(size=20))
    def favorite(self, media: MainMediaTypeList = 'movie,show', *, page: PathArg[int] = 1):
        """Show TMDB user list."""
        return tmdb.user_general_lists('favorite', media, page=page, chunk=10)

    @item_folder_route('watchlist/{media}', list_spec='tmdb:watchlist')
    @pagination(api=ApiPage(size=20))
    def watchlist(self, media: MainMediaTypeList = 'movie,show', *, page: PathArg[int] = 1):
        """Show TMDB user list."""
        return tmdb.user_general_lists('watchlist', media, page=page, chunk=10)
