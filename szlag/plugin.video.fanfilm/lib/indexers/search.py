
from typing import Optional, Tuple, TYPE_CHECKING
import json
import re

from xbmcgui import Dialog, INPUT_ALPHANUM, INPUT_NUMERIC

from ..ff.routing import RouteObject, route, url_for, route_redirect, PathArg
from ..ff.menu import directory, CMenu
from ..ff.db.search import get_search_history, get_search_item, set_search_item, touch_search_item, SearchEntry
from ..ff.db.search import remove_search_item, remove_search_history
from ..ff.control import refresh, update, busy_dialog, close_busy_dialog, busy_section, Finally
from ..ff.log_utils import fflog
from ..defs import SearchType
from ..kolang import L
from .core import Indexer, no_content
from const import const
if TYPE_CHECKING:
    from ..api.tmdb import SearchFilters


class Search(RouteObject):
    """General media searching."""

    def __init__(self, indexer: Indexer, *, type: Optional[SearchType] = None) -> None:
        #: Serach for this indexer.
        self.indexer: Indexer = indexer
        #: Typr of search items.
        self.type: SearchType = type if type else indexer.TYPE if indexer else 'multi'

    @route('/')
    def home(self) -> None:
        """Search main menu."""
        if not self.indexer:
            return no_content('addons')
        item_icon = getattr(self.indexer, 'SEARCH_ITEM_ICON', None)
        search_icon = getattr(self.indexer, 'SEARCH_ICON', item_icon)
        if item_icon is None:
            item_icon = getattr(self.indexer, 'IMAGE', None)
        if search_icon is None:
            search_icon = 'common/search.png'
        history = get_search_history(self.type)
        with directory(view=const.indexer.search.view, thumb=item_icon) as kdir:
            year_dialog = const.indexer.search.year_dialog
            if not getattr(self.indexer.const, 'search', None):
                year_dialog = 'never'
            always_year = year_dialog == 'always'
            new = kdir.action(L(32603, 'New search...'), url_for(self.new, year=always_year), style='[B]{}[/B]', thumb=search_icon, menu=[
                CMenu(L(30411, 'New search with year...'), url_for(self.new, year=True), visible=(year_dialog == 'context-menu')),
            ])
            new.position = 'top'
            if year_dialog == 'entry':
                new = kdir.action(L(30411, 'New search with year...'), url_for(self.new, year=True), style='[B]{}[/B]', thumb=search_icon)
                new.position = 'top'
            for it in history:
                query, _ = self._query_options(it, colorize=True)
                kdir.folder(query, url_for(self.entry, id=it.id), menu=(
                    (L(30180, 'Remove item'), url_for(self.remove, id=it.id)),
                    (L(30181, 'Delete history'), self.clear),
                    (L(30182, 'Edit item'), url_for(self.edit, id=it.id)),
                ))

    @route
    def new(self, query: Optional[str] = None, *, year: bool = False) -> None:
        """Create new search."""
        if not self.indexer:
            return no_content('addons')
        busy_dialog()
        if not query:
            # xbmc.Keyboard(text, title)  ...doModal()
            query = Dialog().input(L(32010, 'Search'), type=INPUT_ALPHANUM)
        query = re.sub(r'\s+', ' ', query).strip()
        if query:
            options = {}
            if year and (value := Dialog().input(L(30412, 'Year (optional)'), type=INPUT_NUMERIC)) and value.isdecimal():
                options['year'] = int(value)
            else:
                xquery, xopt = self._query_options(SearchEntry(search_type=self.type, query=query, updated_at=0))
                if xyear := xopt.get('year'):
                    query = xquery
                    options['year'] = xyear
            sid = set_search_item(type=self.type, query=query, options=options)
            route_redirect(self.entry, id=sid)
            update(str(url_for(self.entry, id=sid) or ''))
        else:
            close_busy_dialog()
            update(str(url_for(self.home) or ''))

    @route
    def epg(self, query: str) -> None:
        """Search EPG."""
        if not self.indexer:
            return no_content('addons')
        with busy_section():
            sid = set_search_item(type=self.type, query=query)
            self.search(sid)

    @route
    def edit(self, id: PathArg[int]) -> None:
        """Edit search item."""
        sit = get_search_item(id)
        if not self.indexer or not sit:
            return no_content('addons')
        # xbmc.Keyboard(text, title)  ...doModal()
        query = Dialog().input(L(32010, 'Search'), sit.query, type=INPUT_ALPHANUM)
        query = query.strip()
        if query:
            sid = set_search_item(type=sit.search_type, query=query, id=id)
            # route_redirect(self.entry, id=sid)
            # self.search(sid)
            update(str(url_for(self.entry, id=sid) or ''))
        else:
            return self.home()

    @route('/')
    def entry(self, id: PathArg[int], *, page: PathArg[int] = 1) -> None:
        """Search entry point."""
        if not self.indexer:
            return no_content('addons')
        self.search(id, page=page)
        Finally.call(close_busy_dialog)

    def search(self, id: int, *, page: int = 1) -> None:
        """Search for items."""
        sit = get_search_item(id, type=self.type)
        if not self.indexer or not sit:
            return no_content('addons')
        touch_search_item(id)
        query, filters = self._query_options(sit)
        return self.indexer.search_items(query, page=page, type=self.type, **filters, sort_by='popularity.desc')

    def _query_options(self, sit: 'SearchEntry', *, colorize: bool = False) -> 'Tuple[str, SearchFilters]':
        """Get query and options for search item."""
        query = sit.query.strip()
        filters: 'SearchFilters' = {}
        try:
            cs = self.indexer.const.search
        except AttributeError:
            pass
        else:
            if cs.year_pattern and (mch := re.search(cs.year_pattern, sit.query)):
                filters['year'] = int(next(iter(v for v in mch.groups() if v)))
                hit = mch.group(0)
                if colorize:
                    query = query.replace(hit, const.indexer.search.query_option_format.format(hit, option=hit))
                else:
                    query = query.replace(hit, '').strip()
        if options := sit.options:
            options = json.loads(options)
            if year := options.get('year'):
                filters['year'] = year
                if colorize:
                    opt = f'({year})'
                    opt = const.indexer.search.query_option_format.format(opt, option=opt, year=year)
                    query = f'{query} {opt}'
        return query, filters

    @route
    def remove(self, id: PathArg[int]) -> None:
        """Remove history item."""
        remove_search_item(id=id)
        route_redirect(self.home)
        # self.home()
        # refresh()
        update(str(url_for(self.home) or ''))

    @route
    def clear(self) -> None:
        """Clear history (delete all items)."""
        if not const.indexer.search.clear_if_sure or Dialog().yesno(L(30181, 'Delete history'), L(32056, 'Are you sure?')):
            remove_search_history(type=self.type)
        route_redirect(self.home)
        update(str(url_for(self.home) or ''))
