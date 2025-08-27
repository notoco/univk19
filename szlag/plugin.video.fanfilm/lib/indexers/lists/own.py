from typing import Optional, Union, Tuple, Sequence, Iterable, ClassVar, TYPE_CHECKING
from typing_extensions import Unpack
from ..core import Indexer, no_content
from ...ff.routing import route, info_for, EnumName
from ...ff.menu import CMenu
from ...defs import FFRef, MediaRef
from ...ff.item import FFItem
from ...ff.ownlists import OwnList
from ..folder import item_folder_route, pagination, FolderRequest, list_directory, Target
from ...kolang import L
from ...ff.log_utils import fflog
from const import const
from cdefs import ListType, OwnListDef, WhenShowListName
if TYPE_CHECKING:
    from ...ff.menu import KodiDirectory, KodiDirectoryAddArgs


class OwnLists(Indexer):
    """
    Simple own lists. Just link to list with linsk to media.

    Supported list format:
      - CSV, columns: type, tmdb
      - JSON
      - m3u8 (not suppotetd yet)

    JSON format:
    >>> {
    >>>   "name": "LIST NAME",
    >>>   "type": "CONTENT_TYPE",
    >>>   "translations": {
    >>>     "pl": "PL NAME"
    >>>   },
    >>>   "items": [
    >>>     {
    >>>       "type": "MEDIA_TYPE(movie/show)",
    >>>       "tmdb": "TMDB_ID",
    >>>     },
    >>>     {
    >>>       "type": "list",
    >>>       "label": "Sub-list NAME",
    >>>       "url": "URL to the sub-list"
    >>>       "icon": "optional_icon_url",
    >>>     }, ...
    >>>   ]
    >>> }
    """

    CATEGORY: ClassVar[str] = L(30327, 'My Own Lists')

    def _generic_list(self, generic: str) -> Optional[OwnListDef]:
        """Get generic list definition by name."""
        for lst in const.indexer.own.generic:
            if lst.name == generic:
                return lst

    def _fav_entry(self, kdir: 'KodiDirectory', media: ListType, **kwargs: Unpack['KodiDirectoryAddArgs']) -> Optional[FFItem]:
        if media == ListType.PERSON:
            label, thumb = L(30329, 'Favorite Persons'), 'services/own/favorites_persons.png'
        elif media == ListType.COLLECTION:
            label, thumb = L(30330, 'Favorite Collections'), 'services/own/favorites_collections.png'
        elif media & ListType.MOVIE_LIKE and not (media & ~ListType.MOVIE_LIKE):
            label, thumb = L(30157, 'Favorite Movies'), 'services/own/favorites_movies.png'
        elif media & ListType.SHOW_LIKE and not (media & ~ListType.SHOW_LIKE):
            label, thumb = L(30158, 'Favorite TV Shows'), 'services/own/favorites_tvshows.png'
        else:
            label, thumb = L(30156, 'Mixed Favorites'), 'services/own/favorites_mixed.png'
        kwargs.setdefault('thumb', thumb)
        return kdir.folder(label, info_for(self.favorites, media=media or ListType.MIXED), **kwargs)

    def _any_entry(self, kdir: 'KodiDirectory', generic: str, media: ListType, **kwargs: Unpack['KodiDirectoryAddArgs']) -> Optional[FFItem]:
        if media == ListType.PERSON:
            label, thumb = L(30175, 'Persons'), 'services/own/persons.png'
        if media == ListType.COLLECTION:
            label, thumb = L(30145, 'Collections'), 'services/own/collection2.png'
        elif media & ListType.MOVIE_LIKE and not (media & ~ListType.MOVIE_LIKE):
            label, thumb = L(32001, 'Movies'), 'services/own/movies.png'
        elif media & ListType.SHOW_LIKE and not (media & ~ListType.SHOW_LIKE):
            label, thumb = L(32002, 'TV Shows'), 'services/own/tvshows.png'
        else:
            label, thumb = L(30398, 'Mixed Media'), 'services/own/mixed.png'
        kwargs.setdefault('thumb', thumb)
        return kdir.folder(label, info_for(self.generic, generic=generic, media=media or ListType.MIXED), **kwargs)

    @route('/')
    def home(self) -> None:
        """User own lists."""
        # imdb = ImdbScraper()
        with list_directory(view='sets', category=self.CATEGORY) as kdir:
            # kdir.folder(L(30146, 'Favorites'), self.favorites_folder, thumb='DefaultMovies.png')
            # kdir.folder(L(32033, 'Watchlist'), self.watchlist_folder, thumb='DefaultMovies.png')
            # for lst in const.indexer.own.generic:
            #     self._add_list_def(kdir, lst)
            self.add_generic_lists(kdir)
            if const.indexer.own.lists:
                if const.indexer.own.flat:
                    self.add_mine(kdir, flat=const.indexer.own.root.flat)
                else:
                    kdir.folder(L(30149, 'My Lists'), self.mine, thumb='services/own/lists.png')

    def add_generic_lists(self,
                          kdir: 'KodiDirectory',
                          media: Union[ListType, str, int, None] = None,
                          *,
                          icon: Optional[str] = None,
                          favorites: bool = True,
                          watchlist: bool = True,
                          collection: bool = True,
                          ) -> None:
        """Add generic lists to the given Kodi directory."""
        if media is not None:
            media = ListType.new(media)
        for lst in const.indexer.own.generic:
            if lst.name == ':favorites' and not favorites:
                continue
            if lst.name == ':watchlist' and not watchlist:
                continue
            if lst.name == ':collection' and not collection:
                continue
            if media is None:
                self._add_list_def(kdir, lst, media=media, icon='services/own/favorites.png' if lst.name == ':favorites' else icon)
                # self._any_entry(kdir, generic=lst.name, media=ListType.MIXED)
                # kdir.folder(label, info_for(self.generic, generic=generic, media=media or ListType.MIXED), **kwargs)
            else:
                self._add_list_def(kdir, lst, media=media, icon='services/own/main.png')

    # @route('favorites')
    def favorites_folder(self, *, mixed: bool = True) -> None:
        with list_directory(view='sets') as kdir:
            if mixed:
                self._fav_entry(kdir, ListType.MIXED)
            self._fav_entry(kdir, ListType.MOVIE)
            self._fav_entry(kdir, ListType.SHOW)
            self._fav_entry(kdir, ListType.PERSON)
            self._fav_entry(kdir, ListType.COLLECTION)
        # XXX DEBUG
        # print(info_for(self.favorites.endpoint('library'), media=OwnListType.MIXED))

    @route('mine/{__media}')
    def mine(self, *, media: EnumName[ListType] = ListType.MIXED, flat: Optional[bool] = None) -> None:
        if flat is None:
            flat = self._get_flat_for(media)
        with list_directory(view=const.indexer.own.mine.view) as kdir:
            self.add_mine(kdir, media=media or ListType.MIXED, flat=flat)

    @item_folder_route('favorites/{media}', list_spec='own:favorites')
    @pagination(const.indexer.own.page_size)
    def favorites(self, req: FolderRequest, /, *, media: EnumName[ListType], page: int = 1) -> Sequence[FFRef]:
        if lst := self._generic_list(':favorites'):
            return OwnList(type=media or ListType.MIXED, url=lst.url).load(media=media)
        return ()

    @item_folder_route('{generic}/{media}', list_spec='own:{generic}')
    @pagination(const.indexer.own.page_size)
    def generic(self, req: FolderRequest, /, *, generic: str, media: EnumName[ListType]) -> Sequence[FFRef]:
        if lst := self._generic_list(generic):
            return OwnList(type=media or ListType.MIXED, url=lst.url).load(media=media)
        return ()

    def _get_flat_for(self, media: Optional[ListType]) -> Optional[bool]:
        # const.indexer.movies.my_lists.root.flat
        # const.indexer.tvshows.my_lists.root.flat
        # const.indexer.persons.my_lists.root.flat
        if not media:
            return const.indexer.own.root.flat
        try:
            key = 'tvshows' if media == 'show' else f'{media}s'
            return getattr(const.indexer, key).my_lists.root.flat
        except AttributeError:
            return None

    def _menu(self, url: str) -> Optional[Iterable[Tuple[str, Target]]]:
        """Return menu for the own lists."""
        return []

    def add_mine(self,
                 kdir: 'KodiDirectory',
                 *,
                 media: ListType = ListType.MIXED,
                 favorites: bool = False,
                 watchlist: bool = False,
                 collection: bool = False,
                 flat: Optional[bool] = None,
                 ) -> None:
        if flat is None:
            flat = const.indexer.own.mine.flat_default
        if favorites:
            self._fav_entry(kdir, media)
        if watchlist and media != 'person':  # persons has no favorite at all
            self._any_entry(kdir, ':watchlist', media)
        if collection and media != 'person':  # persons has no favorite at all
            self._any_entry(kdir, ':collection', media)

        media |= ListType.LIST  # always show lists
        own_lists = [lst for lst in const.indexer.own.lists if lst.match(media)]
        if flat:
            when_show_rule = const.indexer.own.mine.show_list_name
            show_role = when_show_rule is WhenShowListName.ALWAYS or (when_show_rule is WhenShowListName.IF_MANY and len(own_lists) > 1)
            for lst in own_lists:
                role = lst.title if show_role else None
                if lst.type is ListType.LIST:
                    self._add_list_list(kdir, url=lst.url, media=media, role=role)
                elif lst.match(media):
                    if role is not None:
                        role = const.indexer.own.mine.root_direct_role.format(name=lst.title, type=lst.type)
                    self._add_list_def(kdir, lst, media=media, role=role)
        else:
            for lst in const.indexer.own.lists:
                if lst.match(media):
                    self._add_list_def(kdir, lst, media=media)

    @staticmethod
    def _default_icon(type: Union[ListType, str]) -> str:
        if type == 'list':
            return 'services/own/lists.png'
        if type == 'show':
            return 'services/own/tvshows.png'
        if type == 'person':
            return 'services/own/persons.png'
        return 'services/own/movies.png'

    def _add_list_def(self,
                      kdir: 'KodiDirectory',
                      lst: OwnListDef,
                      media: Optional[ListType] = None,
                      *,
                      role: Optional[str] = None,
                      icon: Optional[str] = None,
                      ) -> None:
        if lst.type is ListType.LIST:
            kdir.folder(lst.title, info_for(self.list_list, url=lst.url, media=media), thumb=lst.icon or self._default_icon(lst.type), role=role)
        elif OwnListDef.type_match(lst.type, media):
            menu = None  # self._menu()  XXX
            if lst.name.startswith(':'):
                if media is None:
                    kdir.folder(lst.title, info_for(self.generic_folder, generic=lst.name),
                                thumb=icon or lst.icon or self._default_icon(lst.type), role=role, menu=menu)
                elif media & lst.type:
                    kdir.folder(lst.title, info_for(self.generic, generic=lst.name, media=media or lst.type),
                                thumb=icon or lst.icon or self._default_icon(lst.type), role=role, menu=menu)
            else:
                kdir.folder(lst.title, info_for(self.item_list, url=lst.url, type=lst.type or ListType.MIXED, media=media),
                            thumb=icon or lst.icon or self._default_icon(lst.type), role=role, menu=menu)

    def _add_list_list(self,
                       kdir: 'KodiDirectory',
                       *,
                       type: ListType = ListType.LIST,
                       url: str,
                       media: Optional[EnumName[ListType]] = None,
                       role: Optional[str] = None,
                       ) -> None:
        for it in OwnList(type=type, url=url).load():
            if isinstance(it, FFItem):
                it_url = it.vtag.getUniqueID('list-url')
                it_type = ListType.new(it.vtag.getUniqueID('list-type'))
                if it_type == 'list':
                    kdir.add(it, url=info_for(self.list_list, type=it_type, url=it_url, media=media), role=role, thumb='services/own/lists.png')
                elif OwnListDef.type_match(it_type, media):
                    if media is ListType.ALL:
                        media = None
                    if it_url.startswith('db://own/'):
                        menu = self._menu(it_url)
                        name = it_url[9:]  # remove 'db://own/' prefix
                        kdir.add(it, url=info_for(self.own_items, name=name, media=media), role=role, thumb='services/own/lists.png', menu=menu)
                    else:
                        kdir.add(it, url=info_for(self.item_list, type=it_type, url=it_url, media=media), role=role, thumb='services/own/lists.png')

    @route('/list')
    def list_list(self,
                  *,
                  type: ListType = ListType.LIST,
                  url: str,
                  media: Optional[EnumName[ListType]] = None,
                  ) -> None:
        fflog(f'own list {media=}: {url=}')
        with list_directory(view=const.indexer.own.mine.view) as kdir:
            self._add_list_list(kdir, type=type, url=url, media=media)

    @item_folder_route('/list/{name}', list_spec='own:user:{name}')
    @pagination(const.indexer.own.page_size)
    def own_items(self,
                  req: FolderRequest,
                  /, *,
                  name: str,
                  media: Optional[EnumName[ListType]] = None,
                  page: int = 1,
                  ) -> Sequence[FFRef]:
        # def add_menu(it: FFRef) -> FFItem:
        #     """Add menu to the item."""
        #     if not isinstance(it, FFItem):
        #         it = FFItem(it)
        #     it.cm_menu.append(...)
        #     return it
        # return [add_menu(it) for it in OwnList(type=ListType.ALL, url=f'db://own/{name}').load(page=page, media=media)]
        fflog(f'own media {media=}: {name=}')
        return OwnList(type=ListType.ALL, url=f'db://own/{name}').load(page=page, media=media)

    @item_folder_route('/list/type/{type}')
    @pagination(const.indexer.own.page_size)
    def item_list(self,
                  req: FolderRequest,
                  /, *,
                  type: EnumName[ListType],
                  url: str,
                  media: Optional[EnumName[ListType]] = None,
                  page: int = 1,
                  ) -> Sequence[FFRef]:
        fflog(f'own media {type=}: {url=}')
        return OwnList(type=type or ListType.MIXED, url=url).load(page=page, media=media)

    @route('{generic}')
    def generic_folder(self, generic: str) -> None:
        if not (lst := self._generic_list(generic)):
            view = const.indexer.own.mine.view
            return no_content(view, empty_message=f'No such generic list: {generic}')
        if lst.name == ':favorites':
            return self.favorites_folder(mixed=lst.mixed)
        with list_directory(view='sets') as kdir:
            if lst.mixed:
                self._any_entry(kdir, generic=lst.name, media=ListType.MIXED)
            if lst.type & ListType.MOVIE:
                self._any_entry(kdir, generic=lst.name, media=ListType.MOVIE)
            if lst.type & ListType.SHOW_LIKE:
                self._any_entry(kdir, generic=lst.name, media=ListType.SHOW)
            if lst.type & ListType.PERSON:
                self._any_entry(kdir, generic=lst.name, media=ListType.PERSON)
            if lst.type & ListType.COLLECTION:
                self._any_entry(kdir, generic=lst.name, media=ListType.COLLECTION)

    @route('/remove/{name}/{ref}')
    def remove_item(self, name: str, ref: MediaRef) -> None:
        """Remove item from the own list."""
        from ...ff.lists import LIST_POINTERS
        sd = LIST_POINTERS.get('', None)
        fflog(f'remove item {name=}: {ref=}')
        # OwnList(type=ListType.ALL, url=f'db://own/{name}').remove(ref)
        # return no_content(const.indexer.own.mine.view, empty_message=f'Removed {ref} from {name} list')

    @route('/delete/{name}')
    def delete_list(self, name: str) -> None:
        """Delete own user list."""
        fflog(f'delete list {name=}')
        # OwnList(type=ListType.ALL, url=f'db://own/{name}').remove(ref)
        # return no_content(const.indexer.own.mine.view, empty_message=f'Removed {ref} from {name} list')


# if __name__ == '__main__':
#     OwnList(OwnListDef('a', 'mixed', 'info://profile/dupa')).load()
