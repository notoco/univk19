"""
Fanfilm Add-on

Indexers' core.
"""

from itertools import chain
from datetime import datetime, date as dt_date, timedelta
from enum import Flag
from typing import Optional, Union, Any, Tuple, List, Dict, Set, Sequence, Mapping, Iterable, Callable, ClassVar, TYPE_CHECKING
from typing_extensions import Literal, Unpack, TypeAlias, get_args as get_typing_args, cast, TypedDict, NotRequired

from ..kolang import L
from ..ff import control, locales
from ..ff.log_utils import fflog, fflog_exc
from ..ff.types import JsonData, PagedItemList
from ..ff.menu import directory, ContentView, KodiDirectory, Target, ContextMenu, ContextMenuItem, KodiDirectoryKwArgs, CMenu
from ..ff.routing import route, url_for, info_for, PathArg, RouteObject
from ..ff.db.media import get_ref_list, set_ref_list  # XXX HACK?
from ..ff.db.playback import set_track_watched_item, unset_track_watched_item
from ..ff.db import state
from ..ff.calendar import local_str_from_utc_timestamp, fromisoformat
from ..ff.item import FFItem
from ..ff.info import ffinfo, ItemInfoKwargs
from ..ff.tmdb import tmdb
from ..ff.trakt import trakt
from ..api.imdb import ImdbScraper, ImdbTitleType
from ..api.tmdb import DiscoveryFilters, SearchFilters, SearchType, MediaResource
from ..ff.settings import settings
from ..defs import RefType, ItemList, MediaRef, MediaRefWithNoType, MediaPlayType, Pagina
from .defs import CodeId, DirItemSource
from .folder import filter_kwargs, item_folder_route, pagination, list_directory, ApiPage, FolderRequest
from const import const
if TYPE_CHECKING:
    from .folder import AutoContextMenu


# Pozycja do dodania do katalogu (listy) kodi.
DirItemData = Dict[str, Any]

#: Crew job.
Job: TypeAlias = Literal['director', 'producer']

#: Service.
ServiceType: TypeAlias = Literal['tmdb', 'trakt', 'imdb']


class ItemProceed(Flag):
    """Flags for mark item proceeded steps."""
    NONE = 0
    PROGRESS = 1


class ItemProceedDict(dict):
    """Dict with flags."""
    def __missing__(self, key: MediaRef) -> ItemProceed:
        return ItemProceed.NONE


class ShowItemOnlyKwargs(TypedDict):
    # Standalone items (ex. episode without show), item label should show full info (ex. show and episode title).
    alone: NotRequired[bool]
    # Item URL to show an item if True, else execute the item. Ex. link to an episode: shows episodes else plays the episode.
    link: NotRequired[bool]
    # Extra context menu, not necessary in 99%. See Indexer.prepare_item().
    menu: NotRequired[Optional[ContextMenu]]
    # Show progress.
    show_progress: NotRequired[bool]


class ShowItemKwargs(ShowItemOnlyKwargs, KodiDirectoryKwArgs, ItemInfoKwargs):
    # Message to show in a notification, if item list is empty. Do not show any notification if None.
    empty_message: NotRequired[Optional[str]]
    # Extra format to set [ROLE].
    role_format: NotRequired[Union[str, Callable[[FFItem, int], str], None]]
    # Do not get info (already got).
    skip_ffinfo: NotRequired[bool]


class Indexer(RouteObject):
    """Base class for all indexers."""

    _jobs: Dict[Optional[Job], Set[str]] = {
        'director': {'Director'},
        # 'director': {'Director', 'Co-Director'},
        'producer': {'Producer'},
    }

    #: Module name / id.
    MODULE: ClassVar[str] = ''  # to read const settings
    #: Indexer type – main type (eg. movie, show).
    TYPE: ClassVar[RefType] = ''
    #: Indexer video type – real type (eg. movie, episode).
    VIDEO_TYPE: ClassVar[RefType] = ''
    TMBD_CONTENT: ClassVar[str] = ''
    TRAKT_CONTENT: ClassVar[str] = ''
    ADULT: ClassVar[bool] = False
    INCLUDE_VIDEO: ClassVar[bool] = False
    VOTE_COUNT_SETTING: ClassVar[str] = ''
    #: Kodi directory content view.
    VIEW: ClassVar[ContentView] = 'addons'

    #: Default image/icon.
    IMAGE: ClassVar[Optional[str]] = None

    #: New search icon.
    SEARCH_ICON: ClassVar[Optional[str]] = None
    #: Search item icon if None `IMAGE` is used.
    SEARCH_ITEM_ICON: ClassVar[Optional[str]] = None

    _flag_url: ClassVar[str] = 'https://raw.githubusercontent.com/hampusborgos/country-flags/ba2cf4101bf029d2ada26da2f95121de74581a4d/png250px/{lower}.png'

    def __init__(self, action: Optional[str] = None) -> None:
        #: Navigator action.
        self.action: str = control.sysaction if action is None else action
        #: Default sort type.
        self.video_sort: str = 'popularity.desc'
        #: Helper. Refs proceeded by item_progress().
        self._item_proceeded: Dict[MediaRef, ItemProceed] = ItemProceedDict()

    def no_content(self, view: Optional[ContentView] = None, *, target: Target = None, empty_message: Optional[str] = None) -> None:
        """Empty folder."""
        if not view:
            view = self.VIEW
        return no_content(view, target=target, empty_message=empty_message)

    def error_content(self, message: str, view: Optional[ContentView] = None) -> None:
        """Empty folder."""
        if not view:
            view = self.VIEW
        return err_content(message, view)

    # def store_base_info(self, items: List[MediaBaseInfo]) -> None:
    #     """Store current directory in state DB. It allows to recover all IDs."""
    #     set_media_base_info(items)

    def today(self) -> dt_date:
        """Fake today."""
        return (datetime.now() - timedelta(hours=5)).date()

    def not_so_today(self) -> dt_date:
        """Fake today, not so current day (eg. without cinema last N months))."""
        return self.today()

    def search_items(self,
                     query: str,
                     *,
                     page: int,
                     type: Optional[SearchType] = None,
                     **kwargs: Unpack[SearchFilters],
                     ) -> None:
        """Search TMDB and make directory. Must be called from @route endpoint."""
        from .navigator import nav
        if type is None:
            type = self.TYPE
        if type not in get_typing_args(SearchType):
            return self.error_content(L(30126, 'Inorrect {} type {!r}').format(SearchType.__class__.__name__, type))
        empty_message = L(30127, 'Nothing found')
        stype: SearchType = cast(SearchType, type)
        kwargs.setdefault('include_adult', self.ADULT)
        self.tune_search_filters(kwargs)
        items = tmdb.search(type=stype, query=query, page=page, **kwargs)
        if items:
            nav.show_items(items, empty_message=empty_message)
        else:
            self.no_content(target=getattr(self, 'search', None), empty_message=empty_message)

    def tune_search_filters(self, filters: SearchFilters) -> None:
        """Tune search filters."""
        pass

    def discover_items(self,
                       *,
                       page: int,
                       route_args: Optional[Dict[str, Any]] = None,
                       votes: Optional[int] = None,
                       **kwargs: Unpack[DiscoveryFilters],
                       ) -> ItemList[FFItem]:
        """Discover TMDB and make directory. Must be called from @route endpoint."""
        kwargs.setdefault('include_adult', self.ADULT)
        kwargs.setdefault('include_video', self.INCLUDE_VIDEO)
        vote_count: int = settings.getInt(self.VOTE_COUNT_SETTING)
        if votes is not None:
            vote_count = votes
        if not votes or votes >= 0:
            kwargs.setdefault('vote_count', tmdb.VoteCount >= vote_count)
        if self.TYPE == 'movie':
            sort_by_opt = settings.getInt('movies.sort')
            kwargs.setdefault('sort_by', const.indexer.movies.discover_sort_by[sort_by_opt])
        if self.TYPE == 'show':
            sort_by_opt = settings.getInt('tvshows.sort')
            kwargs.setdefault('sort_by', const.indexer.tvshows.discover_sort_by[sort_by_opt])
        self.tune_discovery_filters(kwargs)
        if self.TYPE in ('movie', 'show'):
            items = tmdb.discover(self.TYPE, page=page, **kwargs)
        else:
            fflog(f'Unsupported discovery media {self.TYPE!r}')
            items = tmdb.discover(self.TYPE, page=page, **kwargs)  # try it, it will fail
        return items

    def discover(self,
                 *,
                 page: int,
                 route_args: Optional[Dict[str, Any]] = None,
                 votes: Optional[int] = None,
                 **kwargs: Unpack[DiscoveryFilters],
                 ) -> None:
        """Discover TMDB and make directory. Must be called from @route endpoint."""
        items = self.discover_items(page=page, route_args=route_args, votes=votes, **kwargs)
        self.show_items(items, page=page)

    def tune_discovery_filters(self, filters: DiscoveryFilters) -> None:
        """Tune search filters."""
        pass

    def show_items(self,
                   # Sequence of references or FFItems or page (subset) of FFItems to show.
                   items: Union[Sequence[Union[FFItem, MediaRef]], Pagina[FFItem]],
                   *,
                   # Current page number (starts from one) or None for single/first page. Is ignored at this moment (PagedItemList.page is used).
                   page: Optional[int] = None,
                   # All directory (kdir), ffinfo.get_items and Indexer.show_item arguments.
                   **kwargs: 'Unpack[ShowItemKwargs]',
                   ) -> None:
        """
        Show refs/items in the directory.

        Function gets references find full info in TMDB, and process each item by show_item().

        `refs` could be:
        - sequence of:
            - MediaRef  – pure references,
            - FFItem    – item, its `ref` is used to get info, if there is no info, then whole item is taken;
        - or Pagina page of FFItems – only one page is used to get info and display.

        `alone` flag is used when items are not at typical place, example file of watching episodes – each episode
        is alone and show title should be used in episode label.

        `link` flag means the user rather wants to jump to a directory where the item instead of executing item.
        Example links in show progress folder jump to season view instead of start playing the episode.

        Item progress is always obtained to show Kodi indicator (until progress != Progress.NO).
        `show_progress` flag is used only for show progress bar in the description.

        There is no necessary to override this function. Look at prepare_item() and do_show_item().
        """
        self._item_proceeded.clear()
        if kwargs.get('view') is None:
            kwargs['view'] = self.VIEW
        pg_items = cast(PagedItemList, items)  # directory() check if refs/items object is PagedItemList type
        count = 0
        role_format = kwargs.get('role_format')
        dir_kwargs = filter_kwargs(KodiDirectoryKwArgs, kwargs)
        # dir_kwargs.setdefault('category', self.TYPE)  # XXX
        with directory(pg_items, **dir_kwargs) as kdir:
            self.pre_show_items(kdir)
            show_kwargs = filter_kwargs(ShowItemOnlyKwargs, kwargs)
            show_kwargs.setdefault('alone', True)
            get_kwargs = filter_kwargs(ItemInfoKwargs, kwargs)
            if not kwargs.get('skip_ffinfo'):
                items = ffinfo.get_items(items, **get_kwargs, duplicate=False, keep_missing=False)
            for it in items:
                count += 1
                if callable(role_format):
                    it.role = role_format(it, count)
                elif role_format is not None:
                    it.role = role_format.format(it=it, item=it, ref=it.ref, index=count, title=it.title, year=it.year)
                self.show_item(kdir, it, **show_kwargs)
            self.post_show_items(kdir)
            # save current directory info
            # state.set('refs', [item.ref for item in kdir.items], module='directory')
            if not count:
                kdir.no_content('sets', empty_message=kwargs.get('empty_message'))

    def show_item(self, kdir: KodiDirectory, it: FFItem, *, alone: bool = False, link: bool = False, show_progress: bool = True,
                  menu: Optional[ContextMenu] = None) -> None:
        """Show single item."""
        menu = list(menu or ())
        self.prepare_item(kdir, it, alone=alone, link=link, menu=menu)
        if show_progress:
            self.item_progress(it, menu=menu)
        self.item_properties(it)
        self.do_show_item(kdir, it, alone=alone, link=link, menu=menu)

    def prepare_item(self, kdir: KodiDirectory, it: FFItem, *, alone: bool = False, link: bool = False, menu: List[ContextMenuItem]) -> None:
        """Prepare item to show. Add common stuff like progress, menu. Called from discover(). Override it in your class."""

    def do_show_item(self, kdir: KodiDirectory, it: FFItem, *, alone: bool, link: bool, menu: List[ContextMenuItem]) -> None:
        """Show item. Called from Indexer.show_item(). Override it in your class."""
        it.label = f'!!! {it.title} !!!'
        it.url = f'/fatal/there/is/no/route/for/{it.ffid}'
        kdir.add(it)

    def item_auto_menu(self, item: FFItem, *, kdir: Optional[KodiDirectory]) -> 'List[AutoContextMenu]':
        from .folder import auto_add_to_menu, auto_library_menu, auto_log_list_menu, auto_remove_list_items_refmenu
        # auto menu for adding items
        auto_menu = [
            auto_add_to_menu(),
            auto_library_menu(),
            # auto_user_list_menu(),
            auto_log_list_menu(),
            *(auto_add_to_menu(enabled=cm.enabled, service=cm.service, list=cm.list, name=cm.name)
              for cm in const.indexer.context_menu.add_to),
        ]
        # other operations on items, based on item folder
        if kdir and kdir.list_target:
            from ..ff.routing import EndpointInfo, current_route, main_router
            rtcall = current_route()
            params = {**rtcall.kwargs, 'ref': item.ref}
            if TYPE_CHECKING:
                assert rtcall.method is not None
                assert rtcall.route is not None
            if url := url_for(rtcall.method, **rtcall.kwargs):
                for am in [auto_remove_list_items_refmenu()]:
                    if am.is_enabled() and (path := am.endpoint_path()):
                        path = path.format(url.path, **params)
                        target = EndpointInfo(url=url._replace(path=path), method=rtcall.method, params=params, main_router=main_router)
                        item.cm_menu.extend(am.generate(item, target=target, kdir=kdir))
            ...
        return auto_menu

    def pre_show_items(self, kdir: KodiDirectory):
        """Called before item list folder is created."""

    def post_show_items(self, kdir: KodiDirectory):
        """Called after item list folder is created."""

    def item_menu(self, dir_item: FFItem, src_item: FFItem, menu: List[ContextMenuItem]) -> None:
        """Called to add extra context menu entries."""

    def item_properties(self, it: FFItem) -> None:
        """Set extra properties (w/o progress ones)."""
        ref = it.ref
        if ref.is_episode:
            it.setProperty('episode_type', it.get_episode_type())

    def item_progress(self, it: FFItem, *, menu: Optional[List[ContextMenuItem]] = None) -> None:  # , *, kdir: KodiDirectory = None):
        """Update item progress in kodi."""
        ref = it.ref
        # if self._item_proceeded[ref] & ItemProceed.PROGRESS:  # already done
        #     return
        vtag = it.vtag

        cm_mark_as_watched = cm_mark_as_unwatched = False
        icount = None
        if 1 or trakt.credentials():
            pb = it.progress
            if pb is not None:
                if const.debug.tty:
                    import sty  # XXX DEBUG
                    fflog(f'{sty.bg.blue}>>>{sty.rs.all} {ref=}, {pb.play_count=}, {pb.progress=}')  # XXX
                else:
                    fflog(f'>>> {ref=}, {pb.play_count=}, {pb.progress=}')  # XXX
                if ref.is_container:  # show & season or collection
                    if 0 < pb.progress < 100:  # in progress only
                        vtag.setResumePoint(int(pb.progress) or 1, 0)  # fake resume point (partialy watched)
                        icount = pb.items_count()
                        it.setProperty('inprogress', str(icount.in_progress))
                        it.setProperty('watched', str(icount.watched))
                        it.setProperty('unwatched', str(icount.unwatched))
                        it.setProperty('total', str(icount.total))
                    if ref.is_show or ref.is_season:  # any progress (0, 100 or in-progress)
                        if icount is None:
                            icount = pb.items_count()
                        if icount.watched:
                            it.setProperty('WatchedEpisodes', str(icount.watched))
                        it.setProperty('UnWatchedEpisodes', str(icount.unwatched))
                        it.setProperty('TotalEpisodes', str(icount.total))
                        it.setProperty('WatchedEpisodePercent', str(int(pb.progress)))
                    cm_mark_as_watched = True
                    cm_mark_as_unwatched = True
                else:  # movie or episode or anything
                    duration = vtag.getDuration() or const.indexer.episodes.missing_duration
                    # if no progress in kodi or progress is not similar (omit if < 0.1%)
                    if duration:  # and (not kpb or not kpb.has_progress or abs(kpb.percent - percent) > 0.1):
                        vtag.setResumePoint(duration * pb.progress / 100, duration)
                it.setProperty('PercentPlayed', str(int(pb.progress)))
                cm_mark_as_watched = not pb.play_count
                cm_mark_as_unwatched = bool(pb.play_count) or pb.progress
                vtag.setPlaycount(pb.play_count)
                if pb.has_last_watched_at:
                    vtag.setLastPlayed(local_str_from_utc_timestamp(pb.last_watched_at))
            else:
                cm_mark_as_watched = True

        if icount is None:
            if (ref.is_show or ref.is_season) and (count := it.aired_episodes_count):
                total = str(count)
            else:
                total = '' if it.children_items is None else str(it.children_count)
                # it.setProperty('watched', '0')
                # it.setProperty('WatchedEpisodes', '0')
                if it.children_items is not None:
                    if ref.is_show:
                        total = str(sum(1 for sz in it.season_iter() for ep in sz.episode_iter() if not ep.unaired))
                    elif ref.is_season:
                        total = str(sum(1 for ep in it.episode_iter() if not ep.unaired))
            it.setProperty('unwatched', total)
            it.setProperty('UnWatchedEpisodes', total)
            it.setProperty('total', total)
            it.setProperty('TotalEpisodes', total)
        if it.progress:
            it.descr_style = ffinfo.progress_descr_style(it.progress)

        # use cm_mark_as_watched, cm_mark_as_unwatched to add menu
        if menu is not None and it.ref.real_type not in get_typing_args(MediaPlayType):
            if cm_mark_as_watched:
                menu.append(CMenu(L(30128, 'Mark as watched'), url_for(self.set_watched, ref=it.ref), order=50))
            if cm_mark_as_unwatched:
                menu.append(CMenu(L(30129, 'Mark as unwatched'), url_for(self.unset_watched, ref=it.ref), order=50))
        self._item_proceeded[ref] |= ItemProceed.PROGRESS

    @route('/watched/set/{ref}')
    def set_watched(self, ref: MediaRefWithNoType) -> None:
        """Mark media as watched."""
        fflog(f'custom set watched {ref!r}')
        media_ref = ref.with_forced_type(self.TYPE)
        if set_track_watched_item(media_ref):
            control.refresh()
        if trakt.credentials():
            trakt.add_history_ref(media_ref, db_save=False)
            # trakt.sync_start()

    @route('/watched/unset/{ref}')
    def unset_watched(self, ref: MediaRefWithNoType) -> None:
        """Mark media as unwatched."""
        media_ref = ref.with_forced_type(self.TYPE)
        fflog(f'custom set unwatched {ref!r}')
        if unset_track_watched_item(media_ref):
            control.refresh()
        if trakt.credentials():
            trakt.remove_history_ref(media_ref, db_save=False)
            # trakt.sync_start()

    @route('/discover')
    def media_discover(self, *, page: PathArg[int] = 1, votes: Optional[int] = None, **kwargs: Unpack[DiscoveryFilters]) -> None:
        """Simple discover."""
        self.discover(page=page, votes=votes, **kwargs)

    @route
    def resume(self, *, page: PathArg[int] = 1) -> None:
        """Resume video (movie, episode). Module must have self.VIDEO_TYPE defined."""
        if self.VIDEO_TYPE:
            from .navigator import nav
            items = trakt.media_in_progress(self.VIDEO_TYPE, page=page, sort=True)
            if fmt := self.const_for_real_type.resume.watched_date_format:
                for it in items:
                    if (val := it.vtag.getLastPlayedAsW3C()) and (date := fromisoformat(val)).year > 1970:
                        it.role = f'{date:{fmt}}'
            nav.show_items(items, alone=True)
        else:
            self.no_content()

    @property
    def const(self) -> Any:
        return getattr(const.indexer, self.MODULE, None)

    @property
    def const_for_real_type(self) -> Any:
        vtype = self.VIDEO_TYPE
        if vtype == 'show':
            vtype = 'tvshow'
        return getattr(const.indexer, f'{vtype}s')


class MainIndexer(Indexer):
    """Base class for main indexers (movie, tvshow)."""

    # --- Top lists ---

    @item_folder_route('/trending', limit=const.indexer.trending_scan_limit)
    def trending(self, page: PathArg[int] = 1):
        """Trending movies/tvshows."""
        # FF: /trending/movie/week?api_key=%s&language=%s&primary_release_date.lte=%s&vote_count.gte=100
        service = self.const.trending.service
        if service == 'trakt':
            items = trakt.general_list(self.TYPE, 'trending', page=page)
        else:
            # /trending nie obsługuje parametrów filtrowania !!!
            items = tmdb.trending(self.TYPE, page=page, time='week')
        return items  # already ItemList (with pages)

    # --- Gatunki ---
    @route
    def genre(self, value: PathArg[str] = '', page: PathArg[int] = 1) -> None:
        """Genre lists."""
        # default FF const settigns
        defs = getattr(const.indexer, self.MODULE).genre
        icons: Dict[CodeId, str] = const.indexer_group.genres.icons.get(const.indexer_group.genres.icons_set, {})

        all_genres = value == 'all'
        if value and not all_genres:
            vote_count: int = defs.votes
            filters = {}
            if self.TYPE == 'show':
                filters['first_air_date'] = tmdb.Date <= self.not_so_today()
            else:
                filters['primary_release_date'] = tmdb.Date <= self.not_so_today()
            return self.discover(page=page, votes=vote_count, with_genres=value, **filters)

        # poprawki tłumaczeń
        ui_lang = locales.kodi_locale()
        translations: Dict[CodeId, str] = const.indexer_group.genres.translations.get(ui_lang, {})
        # wszystkie gatunki z TMDB
        group_items = tmdb.genres(self.TYPE)
        genres = get_group_items(group_items, code_key='id', name_key='name', icon='common/genres.png')
        genres = [g._replace(name=translations.get(g.code, g.name), image=icons.get(g.code, g.image)) for g in genres]
        group_item_directory(genres, all_items=True, default_icon='common/languages.png', all_title=L(30101, 'All languages'),
                             view='genres')

    # --- Języki ---
    @route
    def language(self, value: PathArg[str] = '', page: PathArg[int] = 1) -> None:
        """Language lists."""
        # default FF const settigns
        defs = const.indexer_group.languages

        all_languages = value == 'all'
        if value and not all_languages:
            filters = {}
            if self.TYPE == 'show':
                filters['first_air_date'] = tmdb.Date <= self.not_so_today()
            else:
                filters['primary_release_date'] = tmdb.Date <= self.not_so_today()
            return self.discover(page=page, votes=defs.votes, with_original_language=value, **filters)

        # same settings
        ui_lang = locales.kodi_locale()
        api_lang = control.api_language('tmdb')
        # te na górze listy
        top = {*defs.top, ui_lang.partition('-')[0], api_lang.partition('-')[0]}
        # tłumaczenia nazw języków na ten używany przez kodi
        translations = cast(Dict[CodeId, str], locales.language_translations())

        # wszystkie języki z TMDB
        group_items = tmdb.configuration('languages')
        languages = get_group_items(group_items, code_key='iso_639_1', name_key=None, translations=translations,
                                    name_backup_key='english_name', icon='common/languages.png')
        group_item_directory(languages, all_items=all_languages, top=top, groups=defs.groups,
                             default=defs.default, default_icon='common/languages.png', all_title=L(30101, 'All languages'))
    # --- Dostawcy ---
    @route
    def provider_list(self, page: PathArg[int] = 1) -> None:
        """Providers list movies/tvshows."""
        with directory(view='studios') as kdir:
            for provider in tmdb.providers(self.TYPE, region=const.indexer.region):
                kdir.folder(provider.name, url_for(self.provider, pid=provider.id), icon=provider.logo)

    @route
    def provider(self, pid: int, *, page: PathArg[int] = 1) -> None:
        """Providers movies/tvshows."""
        filters: DiscoveryFilters = {
            'with_watch_providers': str(pid),
            'watch_region': const.indexer.tvshows.region,
            'with_watch_monetization_types': 'flatrate|free|ads|rent|buy',
        }
        if self.TYPE == 'show':
            filters['first_air_date'] = tmdb.Date <= self.not_so_today()
            filters['sort_by'] = 'first_air_date.desc'
        else:
            filters['primary_release_date'] = tmdb.Date <= self.not_so_today()
            filters['sort_by'] = 'primary_release_date.desc'
        self.discover(page=page, votes=0, **filters)
    # --- Kraje ---
    @route
    def country(self, value: PathArg[str] = '', page: PathArg[int] = 1) -> None:
        """Country lists."""
        # default FF const settigns
        defs = const.indexer_group.countries

        # determine call type (main, all, item)
        all_countries = value == 'all'
        if value and not all_countries:
            filters = {}
            if self.TYPE == 'show':
                filters['first_air_date'] = tmdb.Date <= self.not_so_today()
            else:
                filters['primary_release_date'] = tmdb.Date <= self.not_so_today()
            return self.discover(page=page, votes=defs.votes, with_origin_country=value, **filters)

        # same settings
        ui_lang = locales.kodi_locale()
        api_lang = control.api_language('tmdb')
        # te na górze listy
        top = {*defs.top, ui_lang.rpartition('-')[2], api_lang.rpartition('-')[2]}

        # wszystkie kraje z TMDB
        group_items = tmdb.configuration('countries')
        countries = get_group_items(group_items, code_key='iso_3166_1', name_key='native_name',
                                    icon='common/country.png')
        if True:  # add country flags
            countries = [c._replace(image=self._flag_url.format(code=c.code, lower=c.code.lower())) for c in countries]
        group_item_directory(countries, all_items=all_countries, top=top, groups=defs.groups,
                             default=defs.default, default_icon='common/country.png', all_title=L(30103, 'All countries'))

    # NOT USED
    def group_discover(self, page: int, **kwargs: Unpack[DiscoveryFilters]) -> None:
        """Discover TMDB for genre, country, language and make directory. Must be called from @route endpoint."""
        kwargs.setdefault('include_adult', self.ADULT)
        kwargs.setdefault('include_video', self.INCLUDE_VIDEO)
        kwargs.setdefault('vote_count', tmdb.VoteCount >= settings.getInt(self.VOTE_COUNT_SETTING))
        items = tmdb.discover(self.TYPE, page=page, **kwargs)
        with directory(items, view=self.VIEW) as kdir:
            for it in ffinfo.get_items(items):
                if it:
                    menu = []
                    self.show_item(kdir, it, menu=menu)

    # --- Lata i zakresy lat. ---
    @route('/year/-')
    @route('/year/{year}-{end}')
    def year_range(self, year: Optional[int] = None, end: Optional[int] = None, page: PathArg[int] = 1) -> None:
        """Media from given decade (range)."""
        if year and end and end >= year:
            return self.discover_year(year, end, page=page)

        with directory(view='years') as kdir:
            year = self.today().year
            for y in reversed(range(1900, year + 1, 10)):
                e = min(year, y+9)
                kdir.folder(f'{y}–{e}', url_for(self.year_range, year=y, end=e), icon='common/calendar.png')

    @route
    def year(self, year: Optional[PathArg[int]] = None, page: PathArg[int] = 1) -> None:
        """Media from given year."""
        if year:
            return self.discover_year(year, year, page=page)

        with directory(view='years') as kdir:
            kdir.folder(L(32630, 'Popular by decades'), url_for(self.year_range), icon='common/calendar.png')
            for y in reversed(range(1900, self.today().year + 1)):
                kdir.folder(str(y), url_for(self.year, year=y), icon='common/calendar.png')

    def discover_year(self, year: int, end: int, *, page: int = 1) -> None:
        """Discover media in year range. Override it for tune."""
        no_content(self.VIEW)

    @item_folder_route('/awards/{name}')
    @pagination(const.indexer.imdb.page_size, api=ApiPage(size=250))
    # def awards_media(self, req: FolderRequest, /, name: str, page: int = 1, *, title_type: Optional[ImdbTitleType] = None) -> List[MediaRef]:
    def awards_media(self, req: FolderRequest, /, name: str) -> List[MediaRef]:
        db_name = f'{self.TYPE}.awards.{name}'
        # refs = get_ref_list(db_name)
        # if not refs:
        imdb = ImdbScraper()
        title_type = imdb.TITLE_TYPES.get(self.TYPE)
        refs = imdb.last_oscars_refs(name, title_type=title_type)
            # refs = ffinfo.find_ids('imdb', refs)
            # refs = list(filter(None, refs))
            # set_ref_list(db_name, refs)
        return ItemList.single(refs)

    def show_media_info_item(self, kdir: KodiDirectory, it: FFItem):
        """Add media item in details view."""
        it.mode = it.Mode.Separator
        it.label = f'[B]{it.title}[/B]'
        kdir.add(it, url=kdir.no_op)

    @route('/{ref}/info')
    def media_info(self, ref: MediaRefWithNoType) -> None:
        """Show media (movie, tvshow) details."""
        from .navigator import nav
        media_ref = ref.with_forced_type(self.TYPE)
        if control.syshandle == -1:
            return control.update(str(url_for(ref=media_ref)))
        it = ffinfo.get_item(media_ref)
        if it is None:
            return self.no_content()
        collection = ffinfo.item_collection(it)
        with list_directory(view='sets') as kdir:
            self.pre_show_items(kdir=kdir)
            self.show_media_info_item(kdir, it)
            if collection:
                kdir.folder(L(30130, 'Movie Collection'), info_for(nav.collection.item, oid=collection.ref.ffid),
                            thumb='common/collections.png')
            kdir.folder(L(30131, 'Recommendations'), info_for(self.media_items, ref=it.ref, resource='recommendations'),
                        thumb='common/recommendations.png')
            if it.source_data and it.source_data['videos'].get('results'):
                kdir.folder(L(30293, 'Videos'), info_for(self.media_videos, ref=it.ref),
                            thumb='common/library.png')
            kdir.folder(L(30132, 'Similar'), info_for(self.media_items, ref=it.ref, resource='similar'), thumb='common/similar.png')
            kdir.folder(L(32011, 'Genres'), info_for(self.media_genres, ref=it.ref), thumb='common/genres.png')
            kdir.folder(L(30133, 'Actors'), info_for(self.media_cast, ref=it.ref), thumb='common/people.png')
            kdir.folder(L(30134, 'Directors'), info_for(self.media_crew, ref=it.ref, job='director'), thumb='common/people.png')
            kdir.folder(L(30135, 'Producers'), info_for(self.media_crew, ref=it.ref, job='producer'), thumb='common/people.png')
            kdir.folder(L(30136, 'Crew'), info_for(self.media_crew, ref=it.ref), thumb='common/people.png')
            kdir.folder(L(32014, 'Languages'), info_for(self.media_languages, ref=it.ref), thumb='common/languages.png')
            kdir.folder(L(30104, 'Countries'), info_for(self.media_countries, ref=it.ref), thumb='common/country.png')
            kdir.folder(L(30137, 'Keywords'), info_for(self.media_keywords, ref=it.ref), thumb='common/keywords.png')
            kdir.folder(L(30138, 'Companies'), info_for(self.media_companies, ref=it.ref), thumb='common/companies.png')
            if it.source_data and 'networks' in it.source_data:
                kdir.folder(L(32016, 'Networks'), info_for(self.media_networks, ref=it.ref), thumb='common/networks.png')
            if it.year:
                decade = round(it.year, -1)
                end = min(self.today().year, decade + 9)
                kdir.folder(L(30139, 'Year {year}').format(year=it.year),
                            info_for(self.year, year=it.year), thumb='common/calendar.png')
                kdir.folder(L(30140, 'Decade {start}–{end}').format(start=decade, end=end),
                            info_for(self.year_range, year=decade, end=end), thumb='common/calendar.png')
            # TODO:
            #   - tv networks

    # TODO: use folder endpoints
    @route('/{ref}/library/add')
    def add_to_library(self, ref: MediaRefWithNoType) -> None:
        # if item := ffinfo.get_item(ref.with_forced_type(self.TYPE), limit=1):
        from ..ff.libtools import library
        library.add(ref.with_forced_type(self.TYPE))

    @route('/library/multiadd')
    def add_to_library_multiple(self) -> None:
        refs = state.get('multilib_refs', module='library')
        media_refs = [MediaRef(*ref) for ref in refs]
        items = ffinfo.get_items(media_refs, crew_limit=None)
        if items:
            from ..ff.libtools import library
            library.add_multiple(items)

    def show_crew(self, items: Sequence[Union[MediaRef, FFItem]]) -> None:
        """Show crew."""
        from .navigator import nav
        nav.person.show_items(items)

    @item_folder_route('/{ref}/cast', limit=const.indexer.add_to_limit)
    @pagination(const.indexer.page_size)
    def media_cast(self, ref: MediaRefWithNoType):
        it = ffinfo.get_item(ref.with_forced_type(self.TYPE), crew_limit=False)
        if not it:
            return []
        return [FFItem.from_actor(a) for a in it.vtag.getActors()]

    @item_folder_route('/{ref}/crew')
    @pagination(const.indexer.page_size)
    def media_crew(self, ref: MediaRefWithNoType, job: Optional[PathArg[Job]] = None):
        it = ffinfo.get_item(ref.with_forced_type(self.TYPE), crew_limit=False)
        if not it:
            return []
        jobs = self._jobs.get(job, set())
        return [FFItem.from_actor(a) for a in it.vtag.getCrew()
                for role in (a.getRole(),) if ((role in jobs) if jobs else (role != 'Thanks'))]

    @route('/{ref}/{resource}')
    def media_items(self, ref: MediaRefWithNoType, resource: MediaResource, page: PathArg[int] = 1) -> None:
        """Show media resource (list of someting)."""
        items = tmdb.media_resource(ref.with_forced_type(self.TYPE), resource, page=page)
        self.show_items(items, page=page)

    @route('/{ref}/genres')
    def media_genres(self, ref: MediaRefWithNoType, job: Optional[PathArg[Job]] = None) -> None:
        it = ffinfo.get_item(ref.with_forced_type(self.TYPE), crew_limit=1)
        if not it or not isinstance(it.source_data, Mapping):
            return self.no_content()

        icons: Dict[CodeId, str] = const.indexer_group.genres.icons.get(const.indexer_group.genres.icons_set, {})
        ui_lang = locales.kodi_locale()
        translations: Dict[CodeId, str] = const.indexer_group.genres.translations.get(ui_lang, {})
        items = ffinfo.item_genres(it, translations=translations)
        with directory(view='genres', thumb='common/genres.png') as kdir:
            if len(items) > 1:
                kdir.folder(L(30141, 'All Genres'),
                            url_for(self.media_discover, with_genres=','.join(str(it.ffid) for it in items)),
                            descr='\n'.join(it.label for it in items),
                            thumb='common/genres.png')
            for it in items:
                gid = it.ref.ffid
                kdir.add(it, url=url_for(self.media_discover, with_genres=gid), thumb=icons.get(gid))

    @route('/{ref}/videos')
    def media_videos(self, ref: MediaRefWithNoType, page: PathArg[int] = 1) -> None:
        media_ref = ref.with_forced_type(self.TYPE)
        count = 0
        with directory(view=const.indexer.details.videos.view, thumb='common/library.png') as kdir:
            for it in tmdb.get_videos(media_ref):
                if it.site == 'YouTube':
                    count += 1
                    if it.official:
                        fmt = L(30295, '{trailer.type} {trailer.lang}: {trailer.name} | Official')
                    else:
                        fmt = L(30296, '{trailer.type} {trailer.lang}: {trailer.name}')
                    name = fmt.format(trailer=it)
                    kdir.play(name, f'plugin://plugin.video.youtube/play/?video_id={it.key}')
            if not count:
                return self.no_content(const.indexer.details.videos.view)

    # DirItemSource
    def _media_discover_list(self,
                             ref: MediaRef,
                             #: source data type
                             src_type: RefType,
                             #: source group key
                             #  - "id" (genre, company, etc.)
                             #  - "iso_639_1" (language)
                             #  - "iso_3166_1" (country)
                             code_key: str = 'id',
                             # nazwa klucza nazwy grupy
                             #  - "name" dla gatunków
                             #  - None dla języków (translacja)
                             #  - "native_name" dla krajów
                             name_key: str = 'name',
                             #: Translation [code] = name.
                             translations: Optional[Dict[CodeId, str]] = None,
                             # nazwa klucza ikony grupy, brana jest domyślna jeśli None
                             icon_key: Optional[str] = None,
                             #: (Default) icon or URL to external image for item "{code}". Eg. countries flags.
                             icon: Optional[str] = None,
                             # nazwy / URL-e ikon grup (np. gatunków, języków)
                             icons: Optional[Dict[str, str]] = None,
                             #: Label for multi-item, for all items (eg. all genres).
                             multi_label: Optional[str] = None,
                             #: The target, discover filter or target route.
                             target: Optional[Callable[..., None]] = None,
                             #: True if get more details.
                             info: bool = False,
                             ) -> None:
        """Show sub-list from details."""

        target_filtes: Dict[str, Tuple[str, str]] = {
            'language': ('spoken_languages', 'with_original_language'),
            'country': ('production_countries', 'with_origin_country'),
            'keyword': ('keywords', 'with_keywords'),  # ANDed
            'company': ('production_companies', 'with_companies'),   # ANDed
            'network': ('networks', 'with_networks'),
        }

        def target_url(code):
            if callable(target):
                return url_for(target, value=code)
            if not filter_key not in target_filtes:
                return KodiDirectory.no_op_url
            filters = {  # shuld be DiscoveryFilters but it failes
                # 'primary_release_date': tmdb.Date <= self.not_so_today(),
                filter_key: str(code),
            }
            return url_for(self.media_discover, votes=0, **filters)

        try:
            source_key, filter_key = target_filtes[src_type]
        except KeyError:
            return self.no_content()
        if not ref.type:
            ref = ref.with_forced_type(self.TYPE)
        it = ffinfo.get_item(ref, crew_limit=1)
        if not it or not isinstance(it.source_data, Mapping):
            return self.no_content()

        source = it.source_data.get(source_key, ())
        items = get_group_items(source, code_key=code_key, name_key=name_key, icon_key=icon_key,
                                translations=translations, icons=icons, icon=icon)
        if info:
            extra = ffinfo.get_items([MediaRef(src_type, int(it.code)) for it in items])
        with directory(view='sets') as kdir:
            if multi_label and len(items) > 1:
                codes = ','.join(str(it.code) for it in items)
                kdir.folder(multi_label, target_url(codes), icon=icon,
                            descr='\n'.join(it.name for it in items))
            if info and extra:
                for it, ex in zip(items, extra):
                    if ex:
                        kdir.add(ex, url=target_url(it.code))
                    else:
                        kdir.folder(it.name, target_url(it.code), icon=it.image or icon)
            else:
                for it in items:
                    kdir.folder(it.name, target_url(it.code), icon=it.image or icon)

    @route('/{ref}/languages')
    def media_languages(self, ref: MediaRefWithNoType) -> None:
        """Show media languages."""
        translations = cast(Dict[CodeId, str], locales.language_translations())
        return self._media_discover_list(ref.with_forced_type(self.TYPE), 'language', code_key='iso_639_1', name_key='',
                                         icon='common/languages.png', translations=translations)

    @route('/{ref}/countries')
    def media_countries(self, ref: MediaRefWithNoType) -> None:
        """Show media countries."""
        translations = cast(Dict[CodeId, str], locales.country_translations())
        return self._media_discover_list(ref.with_forced_type(self.TYPE), 'country', code_key='iso_3166_1', name_key='',
                                         icon=self._flag_url, translations=translations)

    @route('/{ref}/companies')
    def media_companies(self, ref: MediaRefWithNoType) -> None:
        """Show media companies."""
        return self._media_discover_list(ref.with_forced_type(self.TYPE), 'company', icon_key='logo_path', icon='common/companies.png')

    @route('/{ref}/networks')
    def media_networks(self, ref: MediaRefWithNoType) -> None:
        """Show media networks."""
        return self._media_discover_list(ref.with_forced_type(self.TYPE), 'network', icon_key='logo_path', icon='common/networks.png')

    @route('/{ref}/keywords')
    def media_keywords(self, ref: MediaRefWithNoType) -> None:
        """Show media keywords."""
        items = tmdb.media_keywords(ref.with_forced_type(self.TYPE))
        with directory(view='sets', thumb='common/keywords.png') as kdir:
            if len(items) > 1:
                kdir.folder(L(30142, 'All Keywords'),
                            url_for(self.media_discover, with_keywords=','.join(str(it.ffid) for it in items)),
                            descr='\n'.join(it.label for it in items))
            for it in items:
                kdir.add(it, url=url_for(self.media_discover, with_keywords=it.ref.tmdb_id))

    # ---  A tak dla jaj!  :-P  ---

    @route
    def joke(self, type: PathArg[Literal['movie', 'tv_series', 'person', 'collection',
                                         'tv_network', 'keyword', 'production_company']],
             jid: PathArg[int] = 0,
             page: PathArg[int] = 1,
             prefix: str = '') -> None:
        N = 3

        def strip_accents(s: str) -> str:
            return ''.join(c for c in normalize('NFD', s) if category(c) != 'Mn')

        def norm(s: str) -> str:
            def ch(c: str) -> str:
                c = strip_accents(c)[:1]
                if c.isdigit():
                    return '1'
                if c == 'Ł':
                    c = 'L'
                v = ord(c or ' ')
                if 'A' <= c <= 'Z':
                    return c
                if 0x300 <= v <= 0x3ff:
                    return 'Ω'
                if 0x400 <= v <= 0x52f:
                    return 'Я'
                if c and category(c) == 'Lu':
                    return '•'
                return '+'
            return ''.join(ch(c) for c in s.upper())

        from pathlib import Path
        from unicodedata import normalize, category
        from gzip import decompress
        import requests
        import re
        from ..ff.control import dataPath

        if jid:
            fname = {
                'keyword': 'with_keywords',
                'production_company': 'with_companies',
                'tv_network': 'with_networks',
            }
            if type not in fname:
                return no_content(self.VIEW)
            filters: DiscoveryFilters = {fname[type]: str(jid)}
            return self.discover(page=page, votes=0, **filters)
        path = Path(dataPath)
        rx = re.compile(r'\s*{\s*"id"\s*:\s*(\d+)\s*,\s*"name"\s*:\s*"((?:\\.|[^"])*)"')
        date = self.not_so_today() - timedelta(days=1)
        url = f'http://files.tmdb.org/p/exports/{type}_ids_{date:%m_%d_%Y}.json.gz'
        path = path / Path(url).name
        if path.exists():
            gz = path.read_bytes()
        else:
            gz = requests.get(url).content
            try:
                path.write_bytes(gz)
            except IOError:
                pass

        prefix_len = len(prefix)
        names = {m[2].replace('\\', '').replace('\u200e', '').strip(): int(m[1])
                 for ln in decompress(gz).decode().split('\n')
                 for m in (rx.match(ln),) if m}
        names = {k: v for k, v in names.items() if norm(k[:prefix_len]) == prefix}

        with directory() as kdir:
            if prefix_len < N:
                if prefix in names:
                    kdir.folder(prefix, url_for(type=type, jid=names[prefix]))
                letters = sorted(set(norm(n[prefix_len:prefix_len+1]) for n in names if len(n) > prefix_len))
                if letters:
                    for let in letters:
                        kdir.folder(f'[B]{prefix}{let}[/B]', url_for(type=type, prefix=f'{prefix}{let}'))
            else:
                for name in sorted(set(n for n in names if norm(n[:N]) == prefix)):
                    kdir.folder(name, url_for(type=type, jid=names[name]))


def get_group_items(items: Sequence[JsonData],
                    *,
                    # nazwa klucza kodu grupy
                    #  - "id" dla gatunków
                    #  - "iso_639_1" dla języków
                    #  - "iso_3166_1" dla krajów
                    code_key: str,
                    # nazwa klucza nazwy grupy
                    #  - "name" dla gatunków
                    #  - None dla języków (translacja)
                    #  - "native_name" dla krajów
                    name_key: Optional[str] = 'name',
                    # nazwa klucza gdy nie ma tłumaczenia
                    #  - "english_name" dla języków (translacja)
                    name_backup_key: Optional[str] = None,
                    # tłumaczenia nazw kodów (np. języków) na ten używany przez kodi/GUI
                    translations: Optional[Dict[CodeId, str]] = None,
                    # nazwa klucza ikony grupy, brana jest domyślna jeśli None
                    icon_key: Optional[str] = None,
                    # nazwy / URL-e ikon grup (np. gatunków, języków)
                    icons: Optional[Dict[str, str]] = None,
                    # domyślna nazwa / URL ikony
                    icon: Optional[str] = None,
                    ) -> List[DirItemSource]:
    """Get list of all items (genres, languages, countries)."""

    def new(it: JsonData) -> DirItemSource:
        code = it[code_key]
        if name_key:
            name = it[name_key]
        elif name_backup_key:
            name = translations.get(code, it[name_backup_key])
        else:
            name = translations.get(code, f'[{code}]')
        img = None
        if icon_key:
            img = it[icon_key]
            if img and img.startswith('/'):  # TMDB path
                img = f'{tmdb.art_image_url}{img}'
        if not img:
            if icon:
                img = icons.get(code, icon.format(code=code, lower=str(code).lower()))
            else:
                img = icon
        return DirItemSource(code=code, name=name, image=img)

    if translations is None:
        translations = {}
    if icons is None:
        icons = {}
    return [new(it) for it in items]


# lista wszyskich elemntów grupy(genres, languages, countries) pobrana z TBDB
def group_item_directory(items: Iterable[DirItemSource],  # lista...
                         *,
                         # pozycje na głównej stronie gdy all_items=False (grupy zawsze wchodzą)
                         default: Optional[Set[CodeId]] = None,
                         # pozycje na górze listy, gdy domyślne (all_items=False)
                         top: Optional[Set[CodeId]] = None,
                         # grupy, zawsze na głównej stronie: kod AND (,) lub OR(|) : nazwa
                         groups: Optional[Sequence[DirItemSource]] = None,
                         # True,  jeśli wszystkie elementy mają być widoczne
                         # False, jeśli tyle domeyślne `default`
                         all_items: bool = False,
                         # nazwa pola „wszystkie (gatunki, języki, kraje...)”
                         all_title: str = 'All',
                         # domyślna nazwa / URL ikony
                         default_icon: Optional[str] = None,
                         # funcja do operacji na nazwie przy sortowanieu (np. str.lower)
                         sort_name_op: Optional[Callable[[str], str]] = str.lower,
                         # typ widoku zawartości
                         view: ContentView = 'addons',
                         ) -> None:
    """
    Generate group directory (genres, languages, countries etc.).
    Must be called from @route endpoint.
    """

    # te na górze listy
    if all_items:
        top = set()
    else:
        top = set(top or ())

    # wszystkie elementy z TMDB
    if groups:
        items = chain(items, groups)
    if sort_name_op:
        items = sorted(items, key=lambda it: (it.code not in top, sort_name_op(it.name)))
    else:
        items = sorted(items, key=lambda it: (it.code not in top, it.name))

    # fitrowanie, po wybranych
    if not all_items:
        default = {*(default or ()), *(g.code for g in (groups or ()))}
        items = filter(lambda it: it.code in default, items)

    # katalog
    with directory(view=view) as kdir:
        for it in items:
            kdir.folder(it.name, url_for(value=it.code), icon=it.image or default_icon or '')
        if not all_items:
            kdir.folder(f'[B]{all_title}[/B]', url_for(value='all'), icon=default_icon or '')


def no_content(content_view: ContentView, *, target: Target = None, empty_message: Optional[str] = None) -> None:
    """Empty folder."""
    if not empty_message:
        empty_message = L(32834, 'No content to display')
    with directory(view=content_view) as kdir:
        if const.indexer.no_content.show_item:
            kdir.folder(empty_message, target, icon='common/error.png')
    if const.indexer.no_content.notification:
        control.infoDialog(empty_message)


def err_content(message: str, content_view: ContentView) -> None:
    """Empty folder."""
    with directory(view=content_view) as kdir:
        ...
    ln1 = L(30143, 'Error: {}').format(message or '')
    ln2 = L(32834, 'No content to display')
    control.infoDialog(f'{ln1}[CR]{ln2}')
