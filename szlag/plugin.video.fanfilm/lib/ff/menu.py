"""Menu and Kodi list directory support."""

from typing import Optional, Any, Union, Tuple, List, Dict, Set, Sequence, Iterable, Iterator, Callable, ClassVar
from typing_extensions import Literal, Self, TypedDict, Unpack, NotRequired, TypeAlias
from contextlib import contextmanager
from itertools import chain
from pathlib import Path
import re
from attrs import define

from xbmcplugin import addDirectoryItems, endOfDirectory, setContent as setContentView, setPluginCategory
from xbmc import getSkinDir

from .log_utils import fflog_exc
from .routing import URL, url_for, url_proxy, subobject, route, RouteObject, EndpointInfo, find_dispatched_call, unwrap
from .item import FFItem, FMode, SortPosition
from .kotools import xsleep
from .db.state import save_directory
from .info import ffinfo
from .views import view_manager
from . import control
from .types import PagedItemList
from ..service.client import service_client
from ..service.misc import PluginRequestInfo
from ..kolang import L
from .control import addonFanart, update as folder_update
from .settings import settings
from const import const, MediaWatchedMode
from cdefs import ListTarget


Target: TypeAlias = Union[None, str, URL, Callable[..., None], RouteObject, subobject, EndpointInfo]
ContextMenuItem: TypeAlias = Tuple[str, Target]
ContextMenu: TypeAlias = Iterable[ContextMenuItem]

#: Folder content view type.
ContentView: TypeAlias = Literal[
    # - from xbmcplugin.setContent():
    #   albums, artists, episodes, files, games, images, movies, musicvideos, songs, tvshows, videos,
    'albums', 'artists', 'episodes', 'files', 'games', 'images', 'movies', 'musicvideos', 'songs', 'tvshows', 'videos',
    # - from Container.Content():
    #   actors, albums, artists, directors, episodes, files, genres, movies, musicvideos, playlists, plugins,
    #   seasons, sets, songs, studios, tags, tvshows, years,
    'actors', 'directors', 'genres', 'playlists', 'plugins', 'seasons', 'sets', 'studios', 'tags', 'years',
    # - extra well known types:
    'addons',
    # - strange types (not supported): unknown, events, mixed
]

Sort = Literal['label', 'title', 'year']

art_path: Path = Path(control.art_path)


@route
def _no_operation() -> None:
    """No operation (separator)."""


class MenuCondition:
    def __call__(self) -> bool:
        return True


@define
class IfSetting(MenuCondition):
    #: Settings name
    name: str

    def __call__(self) -> bool:
        return settings.getBool(self.name)


@define
# class IfHasLibrary(MenuCondition):
class if_has_library(MenuCondition):
    #: Settings name
    val: int

    def __call__(self) -> bool:
        return self.val >= 5


class CMenu(ContextMenuItem):
    """Single context-menu item with some extra stuff."""

    _visible: Union[bool, str, MenuCondition]
    _order: int

    def __new__(cls, label: str, target: Target, *, visible: Union[bool, str, MenuCondition] = True, order: int = 0) -> Self:
        obj = super().__new__(cls, (label, target))
        obj._visible = visible
        obj._order = order
        return obj

    @property
    def visible(self) -> bool:
        """Check if item is visible in context menu."""
        if self._visible is True:
            return True
        if not self._visible:  # False, None, ''
            return False
        if isinstance(self._visible, str):
            return settings.eval(self._visible)
        return self._visible()

    @property
    def order(self) -> int:
        """Order of item in context menu."""
        return self._order


class AutoContextMenu:
    """Generator (creator) for context menu items."""

    def generate(self,
                 item: FFItem,
                 *,
                 target: Optional[Target] = None,
                 menu: Sequence[ContextMenuItem] = (),
                 kdir: 'Optional[KodiDirectory]' = None,
                 ) -> Iterator[ContextMenuItem]:
        if False:
            yield


class KodiDirectoryKwArgs(TypedDict):
    """Arguments for KodiDirectory() for better typing."""
    # Content view type.
    view: NotRequired[Optional[ContentView]]
    #: Update the listing (updateListing=True).
    update: NotRequired[bool]
    #: Art: thumb.
    thumb: NotRequired[Optional[str]]
    #: Art: icon.
    icon: NotRequired[Optional[str]]
    #: Art: poster.
    poster: NotRequired[Optional[str]]
    #: Art: landscape.
    landscape: NotRequired[Optional[str]]
    #: Art: banner.
    banner: NotRequired[Optional[str]]
    #: Art: fanart.
    fanart: NotRequired[Optional[str]]
    #: Auto-format (ex. unaired).
    autoformat: NotRequired[bool]
    #: Style format.
    style: NotRequired[Optional[str]]
    #: Context menu (append on top).
    menu_top: NotRequired[Optional[Iterable[Tuple[str, Target]]]]
    #: Context menu (append on bottom).
    menu_bottom: NotRequired[Optional[Iterable[Tuple[str, Target]]]]
    #: Auto context menu creators.
    auto_menu: NotRequired[Optional[Iterable[AutoContextMenu]]]
    #: Auto ceate "no content do display" if directory is empty. True or message to show.
    no_content_message: NotRequired[Union[str, bool, None]]
    #: Plugin category, to show as super-title.
    category: NotRequired[Union[str, int, None]]
    #: User list target (add to, remove from...).
    list_target: NotRequired[Optional[ListTarget]]


class KodiDirectoryAddArgs(TypedDict):
    """Arguments for KodiDirectory() create items functions."""
    thumb: NotRequired[Optional[str]]
    icon: NotRequired[Optional[str]]
    poster: NotRequired[Optional[str]]
    landscape: NotRequired[Optional[str]]
    banner: NotRequired[Optional[str]]
    fanart: NotRequired[Optional[str]]
    style: NotRequired[Optional[str]]
    descr: NotRequired[str]
    position: NotRequired[SortPosition]
    menu_top: NotRequired[Optional[Iterable[Tuple[str, Target]]]]
    menu: NotRequired[Optional[Iterable[Tuple[str, Target]]]]
    menu_bottom: NotRequired[Optional[Iterable[Tuple[str, Target]]]]
    role: NotRequired[Optional[str]]
    auto_menu: NotRequired[Union[bool, Iterable[AutoContextMenu]]]


class KodiDirectory:
    """Kodi list directory used in with statement."""

    #: Current folder URL.
    THIS_URL: ClassVar[Optional[URL]] = None
    #: Current folder info (url, refreshing, history...).
    INFO: ClassVar[PluginRequestInfo] = PluginRequestInfo()
    #: True if folder is refreshed (the same URL is used).
    REFRESH_DONE: ClassVar[bool] = False
    #: True if folder is created (KodiDirectory is used).
    CREATED: ClassVar[bool] = False
    #: Index of focused item.
    FOCUS_INDEX: ClassVar[int] = -1
    #: Last folder contnet (KodiDirectory is used).
    CONTENT: ClassVar[Sequence[FFItem]] = ()

    #: Format for future item (unaired, non-premiered).
    FUTURE_FORMAT: ClassVar[Optional[str]] = const.folder.style.future
    #: Format for item with role.
    ROLE_FORMAT: ClassVar[Optional[str]] = const.folder.style.role
    #: Format for broken items (eg. not found in TMDB). Eg. '{} [COLOR red]![/COLOR]'
    BROKEN_FORMAT: ClassVar[Optional[str]] = const.folder.style.broken

    NEXT_PAGE_LABEL = L(32053, '[I]Next page[/I]')
    PREV_PAGE_LABEL = L(30239, '[I]Previous page[/I]')
    #: Names to exclude from folder path.
    FOLDER_PATH_EXCLUDE_NAMES = {NEXT_PAGE_LABEL, PREV_PAGE_LABEL}

    _DEBUG_PRINT_LIST: ClassVar[bool] = False

    _rx_menu_target = re.compile(r'[^(]*://')

    def __init__(self,
                 *,
                 view: Optional[ContentView] = 'addons',
                 # prefix: str = '',
                 update: bool = False,
                 thumb: Optional[str] = None,
                 icon: Optional[str] = None,
                 poster: Optional[str] = None,
                 landscape: Optional[str] = None,
                 banner: Optional[str] = None,
                 fanart: Optional[str] = None,
                 autoformat: bool = True,
                 style: Optional[str] = None,
                 menu_top: Optional[Iterable[ContextMenuItem]] = None,
                 menu_bottom: Optional[Iterable[ContextMenuItem]] = None,
                 auto_menu: Optional[Iterable[AutoContextMenu]] = None,
                 no_content_message: Union[str, bool, None] = None,
                 category: Union[str, int, None] = None,
                 list_target: Optional[ListTarget] = None,
                 ) -> None:
        import sys  # XXX
        #: Directory view type.
        self.view: Optional[ContentView] = view
        ##: URL prefix for all added actions.
        #self.prefix: str = prefix
        #: Update the listing (updateListing=True).
        self.update: bool = update
        #: Plugin handle.
        self.handle: int = int(sys.argv[1])  # 0  XXX
        #: Added items.
        self.items: List[FFItem] = []
        #: Auto-format (ex. unaired).
        self.autoformat = bool(autoformat)
        #: Style format.
        self.style: Optional[str] = style
        #: Context menu (append on top).
        self.menu_top: List[ContextMenuItem] = list(menu_top or ())
        #: Context menu (append on bottom).
        self.menu_bottom: List[ContextMenuItem] = list(menu_bottom or ())
        #: Focused item.
        self._focused_item: Optional[FFItem] = None
        #: Menu of last item.
        self._last_item_menu: Optional[ContextMenu] = None
        #: Set of handled items to avoid format duplications, key: id(FFItem).
        self._handled_items: Set[int] = set()
        #: Auto context menu creators.
        self.auto_menu: Iterable[AutoContextMenu] = () if auto_menu is None else tuple(auto_menu)
        #: Auto ceate "no content do display" if directory is empty. True or message to show.
        if no_content_message is None:
            no_content_message = const.indexer.empty_folder_message
        self.no_content_message: str = L(32834, 'No content to display') if no_content_message is True else no_content_message or ''
        #: Plugin category, to show as super-title.
        self.category: Union[str, int, None] = category
        #: User list target (add to, remove from...).
        self.list_target: Optional[ListTarget] = list_target
        # --- default settings ---
        if fanart is None:
            fanart = addonFanart()
        #: Art images.
        self.images: Dict[str, Optional[str]] = {
            'thumb': thumb,
            'icon': icon,
            'poster': poster,
            'landscape': landscape,
            'banner': banner,
            'fanart': fanart,
        }

    @classmethod
    def ready_for_data(cls) -> bool:
        """
        Checks service if everyfing is ready.

        Only trakt sync on refreshing is supported now.
        """
        if cls.REFRESH_DONE:
            return True
        from .log_utils import fflog  # XXX
        fflog(f'[MENU] ready? {cls.INFO.refresh=}, {cls.INFO.locked=}')
        if cls.INFO.locked:
            ok = service_client.folder_ready()
            fflog(f'[MENU] folder ready: {ok=}')
        cls.REFRESH_DONE = True
        # if cls.INFO.refresh and const.folder.refresh_delay:
        #     fflog('sleep before refresh')
        #     xsleep(const.folder.refresh_delay)
        # if cls.INFO.refresh and not cls.REFRESH_DONE:
        #     fflog('wait for refresh')
        #     ok = service_client.foler_ready()
        #     fflog(f'folder ready: {ok=}')
        #     cls.REFRESH_DONE = True
        return True

    @classmethod
    def set_current_info(cls, url: Union[URL, str], info: 'PluginRequestInfo') -> None:
        cls.THIS_URL = URL(url)
        cls.INFO = info
        cls.REFRESH_DONE = False
        cls.CREATED = False
        cls.FOCUS_INDEX = -1
        cls.CONTENT = ()

    def close(self) -> None:
        """Close the directory (endDirectory)."""
        if self.no_content_message and not self.items:
            self.no_content(empty_message=self.no_content_message)
        if self.view:
            setContentView(self.handle, self.view)
        category = self.category
        if category is None:
            skin_id = getSkinDir()
            category = const.folder.category_by_skin.get(skin_id, const.folder.category)
        if category and isinstance(category, int):
            parent_path = [p for p in self.INFO.parent_path if p.label not in KodiDirectory.FOLDER_PATH_EXCLUDE_NAMES]
            if parent_path:
                category = ' / '.join(parent.label for parent in parent_path[-category:])
            else:
                category = False
        if isinstance(category, str):
            setPluginCategory(self.handle, category)  # visible as Container.PluginCategory in a skin
        if self.items:
            if self._DEBUG_PRINT_LIST:
                print('\n'.join(f'  {it.url:50s} {it}' for it in self.items))
            items = [(item.url or '', item, item.isFolder()) for item in self.items]
            if self._focused_item:
                try:
                    self.__class__.FOCUS_INDEX = self.items.index(self._focused_item) + 1  # +1 for ".."
                except ValueError:
                    self.__class__.FOCUS_INDEX = -1
            if const.core.media_watched_mode is MediaWatchedMode.WATCH_LISTITEM:
                ffinfo.update_item_kodi_data(self.items)
            addDirectoryItems(self.handle, items, len(self.items))
        endOfDirectory(self.handle, updateListing=self.update, cacheToDisc=const.folder.cache_to_disc)
        if 1:  # XXX
            from .log_utils import fflog
            from ..info import exec_id
            fflog(f'[MENU] endOfDirectory [{exec_id()}]: {self.handle=}, {self.update=}, {self._focused_item=}')
        view_manager.set_custom_view(self.view)
        self.__class__.CONTENT = tuple(self.items)
        self.__class__.CREATED = True
        # save folder to DB
        if const.folder.db_save:
            save_directory(str(self.INFO.url), self.items)

    def _make_url(self, target: Target) -> str:
        """Make URL string from URL or target method."""
        if target is not None:
            if isinstance(target, str):
                return target
            if isinstance(target, URL):
                if ',' in target.path:  # fix comma in url
                    target = target._replace(path=target.path.replace(',', '%2C'))
                return str(target)
            if isinstance(target, EndpointInfo):
                return str(target.url)
            # if isinstance(target, subobject) and self.prefix:
            #     target = url_for(self.prefix, target)
            target = url_for(target)
        if target is None:
            return self.no_op_url
        return str(target)

    def _menu_target(self, target: Target) -> str:
        url = self._make_url(target)
        if self._rx_menu_target.match(url):
            url = f'RunPlugin({url})'
        return url

    def add(self, item: FFItem, *, url: Optional[Target] = None, **kwargs: Unpack[KodiDirectoryAddArgs]) -> None:
        """Add new item (folder / action)."""
        if url is None:
            url = item.target
        if url is not None:
            item.url = self._make_url(url)
        self._set_item(item, target=url, **kwargs)
        self.items.append(item)

    def _set_item(self,
                  ffitem: FFItem,
                  enable_art: bool = True,
                  enable_format: bool = True,
                  target: Optional[Target] = None,
                  **kwargs: Unpack[KodiDirectoryAddArgs],
                  ) -> None:
        """Fill item with extra arguments."""
        if enable_art:
            mn_art, it_art = {}, ffitem.getArt()
            if fallback := const.folder.fanart_fallback:
                if ffitem.ref.type == 'show' and 'tvshow.fanart' not in it_art:
                    for key in (f'tvshow.{fallback}', fallback):
                        if img := it_art.get(key):
                            it_art.setdefault('tvshow.fanart', img)
                            break
                if 'fanart' not in it_art:
                    for key in ('tvshow.fanart', f'tvshow.{fallback}', 'tvshow.landscape', fallback):
                        if img := it_art.get(key):
                            it_art.setdefault('fanart', img)
                            break
            for nm, img in self.images.items():
                if img := kwargs.get(nm, it_art.get(nm) or img):
                    if '://' not in img:
                        path = art_path / img
                        if path.exists():
                            img = str(path)
                    mn_art[nm] = img
            ffitem.setArt({**mn_art, **it_art})
        if role := kwargs.get('role'):
            ffitem.role = role
        if id(ffitem) not in self._handled_items:  # only first time
            if enable_format and self.autoformat:
                if ffitem.unaired and self.FUTURE_FORMAT:
                    ffitem.label = self.FUTURE_FORMAT.format(ffitem.label, item=ffitem)
                if ffitem.role and self.ROLE_FORMAT:
                    ffitem.label = self.ROLE_FORMAT.format(ffitem.label, item=ffitem)
                if ffitem.broken and self.BROKEN_FORMAT:
                    ffitem.label = self.BROKEN_FORMAT.format(ffitem.label, item=ffitem)
            if style := kwargs.get('style', self.style):
                ffitem.label = style.format(ffitem.label, item=ffitem)
            if descr := kwargs.get('descr'):
                ffitem.vtag.setPlot(descr)
            if ffitem.descr_style:
                ffitem.vtag.setPlot(ffitem.descr_style.format(ffitem.vtag.getPlot(), item=ffitem))
        menu: Optional[ContextMenu] = kwargs.get('menu')
        menu = menu or ()
        if ffitem.cm_menu:
            menu = (*menu, *ffitem.cm_menu)
        top_menu = (*self.menu_top, *(kwargs.get('menu_top') or ()))
        if const.debug.crash_menu:
            from ..main import crash
            menu = (('CRASH', url_for(crash)), *menu)
        # create context-menu
        auto_menu = kwargs.get('auto_menu', True)
        if auto_menu is False:
            pass
        else:
            if auto_menu is None or auto_menu is True:
                auto_menu = ()
            menu = tuple(menu)
            # list(self.auto_menu[0].generate(ffitem, target=target, menu=menu, kdir=self))
            menu = (*menu, *(new for am in chain(auto_menu, self.auto_menu)
                             for new in am.generate(ffitem, target=target, menu=menu, kdir=self)))
        bottom_menu = (*(kwargs.get('menu_bottom') or ()), *self.menu_bottom)
        menu = (*top_menu, *sorted(menu, key=lambda m: getattr(m, 'order', 0)), *bottom_menu)
        if menu:
            # filter out context-menu items with visible == False
            menu = tuple(m for m in menu if getattr(m, 'visible', True))
        if menu:
            self._last_item_menu = tuple(menu)
            ffitem.addContextMenuItems([(label, self._menu_target(target)) for label, target in menu])
        if const.core.media_watched_mode is MediaWatchedMode.FAKE_DBID and ffitem.ffid:
            ffitem.vtag.setDbId(ffitem.ffid)
        if ffitem.mode == FMode.Playable and ffitem.url and not ffitem.getPath():
            ffitem.setPath(ffitem.url)
        if ffitem.ffid:
            ffitem.vtag.setUniqueID(str(ffitem.ffid), 'ffid')
        if (ref := ffitem.ref).ffid:
            ffitem.vtag.setUniqueID(f'{ref:a}', 'ffref')
        if pos := kwargs.get('position'):
            ffitem.position = pos
        self._handled_items.add(id(ffitem))

    def folder(self, label: str, target: Optional[Target], **kwargs: Unpack[KodiDirectoryAddArgs]) -> FFItem:
        """Add new folder menu."""
        item = FFItem(label, mode=FMode.Folder)
        self.add(item, url=target, **kwargs)
        return item

    def action(self, label: str, action: Union[str, Target], **kwargs: Unpack[KodiDirectoryAddArgs]) -> FFItem:
        """Add new folder menu."""
        if isinstance(action, str):
            url = self.no_op_url
        else:
            url = self._make_url(action)
        item = FFItem(label, mode=FMode.Command, url=url, info_type=None)
        self.add(item, **kwargs)
        return item

    def play(self, label: str, target: Optional[Target], **kwargs: Unpack[KodiDirectoryAddArgs]) -> FFItem:
        """Add new folder menu."""
        item = FFItem(label, mode=FMode.Playable)
        self.add(item, url=target, **kwargs)
        return item

    def separator(self, label: str = '———————', **kwargs: Unpack[KodiDirectoryAddArgs]) -> FFItem:
        """Add new seaparator / label menu. No any operation."""
        item = FFItem(label, mode=FMode.Separator, url=str(url_for(_no_operation)))
        self.add(item, **kwargs)
        return item

    def focus_item(self, item: Optional[FFItem]) -> None:
        """Set item and try to focus it (by service)."""
        self._focused_item = item

    @contextmanager
    def item_mutate(self) -> Iterator['KodiDirectoryMutate']:
        """With context for mutate (modify) added items."""
        yield KodiDirectoryMutate(self, len(self.items))

    def no_content(self, content_view: Optional[ContentView] = None, *, target: Target = None, empty_message: Optional[str] = None) -> None:
        """Empty folder."""
        if not empty_message:
            empty_message = L(32834, 'No content to display')
        if const.indexer.no_content.show_item:
            self.folder(empty_message, target, icon='common/error.png')
        if const.indexer.no_content.notification:
            control.infoDialog(empty_message)

    no_op = staticmethod(_no_operation)

    no_op_url = str(url_for(_no_operation))


@define
class KodiDirectoryMutate:
    """With context for mutate (modify) added items."""

    kdir: KodiDirectory
    index: int = 0

    @property
    def items(self) -> Sequence[FFItem]:
        """Return new added items."""
        return self.kdir.items[self.index:]

    @property
    def item(self) -> Optional[FFItem]:
        """Return last new added item."""
        assert self.index >= 0
        if len(self.kdir.items) > self.index:
            return self.kdir.items[-1]
        return None

    @property
    def menu(self) -> Optional[List[ContextMenuItem]]:
        """Menu of last new added item."""
        assert self.index >= 0
        if len(self.kdir.items) > self.index:
            return list(self.kdir._last_item_menu or ())
        return None

    @menu.setter
    def menu(self, menu: ContextMenu) -> None:
        if not (item := self.item):
            raise IndexError('No item to mutate')
        self.kdir._set_item(item, enable_art=False, enable_format=False, menu=menu)

    def isort(self, sort: Sort, *, reverse: bool = False) -> None:
        """Sort items by Sort object in place."""
        def key(item: FFItem):
            if sort == 'label':
                return item.label.lower()
            if sort == 'title':
                return item.vtag.getTitle().lower()
            if sort == 'year':
                return item.vtag.getYear() or 0
            raise ValueError(f'Unknown sort: {sort}')
        if self.index:
            self.kdir.items[self.index:] = sorted(self.kdir.items[self.index:], key=key, reverse=reverse)
        else:
            self.kdir.items.sort(key=key, reverse=reverse)


@contextmanager
def directory(items: Optional[PagedItemList] = None,  # optional items get pagination
              *,
              # Extra arguments for "next page" routing, next page url_for().
              route_args: Optional[Dict[str, Any]] = None,
              # All KodiDirectoryKwArgs arguments.
              **kwargs: Unpack[KodiDirectoryKwArgs]) -> Iterator[KodiDirectory]:
    kdir = KodiDirectory(**kwargs)
    if kdir.handle == -1 and const.folder.script_autorefresh:  # called as script
        import sys
        folder_update(str(url_for()))
        sys.exit()
    kdir.ready_for_data()
    if route_args is None:
        route_args = {}
    try:
        def show_page_item(*, go_next: bool) -> None:
            if not items or not hasattr(items, 'page') or not (page := items.page):
                return  # no page api
            if go_next:
                next_page = items.next_page() if hasattr(items, 'next_page') else page + 1
                icon = 'common/poster_next.jpg'
                landscape = 'common/landscape.jpg'
                label = KodiDirectory.NEXT_PAGE_LABEL
            else:
                if const.folder.previous_page == 'never':
                    return
                next_page = page - 1
                icon = 'common/poster_prev.jpg'
                landscape = 'common/landscape_prev.jpg'
                label = KodiDirectory.PREV_PAGE_LABEL
            if not next_page:  # out of range
                return
            if hasattr(items, 'total_pages'):
                total_pages = min(items.total_pages, const.folder.max_page_jump or 10*9)
                descr = L(30125, 'Go to page {page} / {total_pages}').format(page=next_page, total_pages=total_pages)
                if go_next is False and const.folder.previous_page == 'on_last_page' and page + 1 < total_pages:
                    return
            else:
                total_pages = 0
                descr = L(30240, 'Go to page {page}').format(page=next_page)
            kdir.folder(label, url_for(page=next_page, **route_args), icon=icon,
                        thumb=icon, banner=icon, poster=icon, landscape=landscape, descr=descr, menu=[
                            CMenu(L(30241, 'First page'), url_for(page=1, **route_args), visible=page > 1),
                            CMenu(L(30332, 'Previous page'), url_for(page=page-1, **route_args), visible=page > 2),
                            CMenu(L(30242, 'Jump to page...'), url_proxy(jump_to_page, page=page, total_pages=total_pages), visible=total_pages > 3),
                            CMenu(L(30243, 'Last page'), url_for(page=total_pages, **route_args), visible=page + 1 < total_pages),
                        ])

        show_page_item(go_next=False)
        yield kdir
        show_page_item(go_next=True)
    except Exception:
        fflog_exc()
    finally:
        kdir.close()


# @route('/jumping_to_page/{page}/{total_pages}/{url}')
@route('{url}/jumping_to_page/{page}/{total_pages}')
def jump_to_page(url: URL, page: int, total_pages: int, **kwargs) -> None:
    """Proxy to jump to page with page number dialog."""

    from xbmcgui import Dialog
    ShowAndGetNumber = 0

    if call := find_dispatched_call(url.with_query(kwargs)):
        total_pages = min(total_pages, const.folder.max_page_jump or 9999)
        heading = L(30244, 'Enter page number (1..{total_pages})').format(page=page, total_pages=total_pages)
        if snum := Dialog().numeric(ShowAndGetNumber, heading):
            if snum.isdecimal():
                page = int(snum)
                if page < 1:
                    page = 1
                elif total_pages and page > total_pages:
                    page = total_pages
                meth = call.bind()
                target = url_for(meth, page=page, **{**call.kwargs, **kwargs})
                if target:
                    folder_update(str(target))


if __name__ == '__main__':
    from ..defs import ItemList

    with directory(view='addons') as kdir:
        kdir.folder('ala ma kaca', '/')
        kdir.folder(12345, '/')  # test nieporawnego argumentu

    items = ItemList(page=1, total_pages=5, total_results=10)
    with directory(items, view='addons') as kdir:
        kdir.folder('ala ma kaca', '/')
        kdir.folder(12345, '/')  # test nieporawnego argumentu
