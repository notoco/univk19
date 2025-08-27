from __future__ import annotations
import re
from datetime import datetime, timedelta
from html import unescape
from threading import Thread
from urllib.parse import unquote
from copy import deepcopy
from functools import partial
from typing import Optional, Union, Any, List, Dict, Iterable, TYPE_CHECKING

from xbmcgui import ListItem, Window
from xbmcgui import (
    ACTION_MOVE_LEFT, ACTION_MOVE_RIGHT, ACTION_MOVE_UP, ACTION_MOVE_DOWN,
)

from ..ff.control import addonPath, run_plugin, settings, busy_dialog, close_busy_dialog
from ..ff.locales import kodi_locale
from ..ff.log_utils import fflog, fflog_exc
from ..ff.types import is_literal
from ..ff import control
from ..sources import Source
if TYPE_CHECKING:
    from xbmcgui import ControlList
    from ..ff.menu import ContextMenu
    from ..ff.item import FFItem
    from ..ff.sources import sources as SourceFactory, SourceSearchQuery

from ..kolang import L
from .base_window import BaseDialog, CANCEL_ACTIONS, MENU_ACTIONS
from .context import ContextMenuDialog
from cdefs import PlayMode, is_play_mode
from const import const

ITEM_LIST = 5000
NO_ITEMS_LABEL = 5001
RESCAN = 5005
EDIT_SEARCH = 5006


class RescanSources(Exception):
    """Force rescan sources again."""

    def __init__(self, *, query: Optional['SourceSearchQuery']) -> None:
        super().__init__()
        self.query: Optional['SourceSearchQuery'] = query


def endtime(minutes: Union[int, str]) -> str:
    if not minutes:
        return '–'
    end = datetime.now() + timedelta(minutes=int(minutes))
    return end.strftime("%H:%M")


def clear_source(source):
    return source.rsplit(".", 1)[0]


def format_info(label):
    try:
        return re.sub(r"(\d+(?:[.,]\d+)?\s*[GMK]B)", r"[COLOR ffffffff]\1[/COLOR]", label)
    except Exception:
        return label


class Panel(BaseDialog):

    XML = 'SourcesPanel.xml'

    def onAction(self, action):
        action_id = action.getId()
        fflog(f' ######### {action_id = }, {action = }')
        if action_id in CANCEL_ACTIONS:
            self.close()


class EditDialog(BaseDialog):

    XML = 'SourcesEdit.xml'
    CUSTIMZED_XML = True

    #: Edit controls (101..110):
    EDIT_CONTROLS = {
        101: 'localtitle',
        102: 'title',
        103: 'originalname',
        104: 'year',
        105: 'premiered',
        106: 'imdb',
        107: 'tmdb',
        108: 'tvshowtitle',
        109: 'season',
        110: 'episode',
    }

    SCAN_BUTTON = 31

    def __init__(self, *args, query: Dict[str, str], raise_rescan: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.raise_rescan = raise_rescan
        self.query = query
        if query.get('episode'):
            mtype = 'episode'
        else:
            mtype = 'movie'
        fflog(f' ... {mtype = }, {query = }')
        self.setProperty('search.media_type', mtype)

    def get_query(self) -> 'SourceSearchQuery':
        def value(ctl_id: int, key: str) -> Any:
            ctl = self.getControl(ctl_id)
            val = ctl.getText(ctl_id)
            if key in ('season', 'episode'):
                return int(val) if val else None
            if key in ('year',):
                return int(val or 0)
            return val

        return {key: value(ctl_id, key) for ctl_id, key in self.EDIT_CONTROLS.items()}

    def onInit(self) -> None:
        # ctl = self.getControl(5099)
        # ctl.setLabel('Dupa blada', 'font_tiny', '0xFF00FFFF')
        for ctl_id, key in self.EDIT_CONTROLS.items():
            ctl = self.getControl(ctl_id)
            ctl.setText(str(self.query.get(key) or ''))
        self.setFocus(self.getControl(self.SCAN_BUTTON))

    def onAction(self, action):
        action_id = action.getId()
        fflog(f' ######### {action_id = }, {action = }')
        if action_id in CANCEL_ACTIONS:
            self.close()

    def onClick(self, controlId: int) -> None:
        control_id = controlId
        if control_id == 31:  # Scan button.
            query = self.get_query()
            if self.raise_rescan:
                self.raise_exception(RescanSources(query=query))
            self.close(query)
        elif control_id == 32:  # Cancel button.
            self.close()


class SourceDialog(BaseDialog):

    XML = 'SourcesDialog.xml'
    CUSTIMZED_XML = True

    rx_provider_rename: re.Pattern = re.compile(r'(?P<suffix>\.\d)')
    provider_suffixes = {
        '.1': '¹',
        '.2': '²',
        '.3': '³',
    }

    def __init__(self,
                 *args,
                 sources: SourceFactory,
                 item: FFItem,
                 items: List[Source],
                 query: SourceSearchQuery,
                 edit_search: bool = False,
                 **kwargs,
                 ) -> None:
        items = [*(Source.from_meta(ffitem=item, meta=it) for it in const.dev.sources.prepend_fake_items),
                 *items,
                 *(Source.from_meta(ffitem=item, meta=it) for it in const.dev.sources.append_fake_items)]
        super().__init__(*args)
        self.source_factory: SourceFactory = sources
        self.item: FFItem = item
        self.ui_lang = kodi_locale()
        self.sources: List[Source] = items
        self.lists = self.list_items(self.sources)
        self.resolved: Optional[Source] = None
        self.focused_constrol_id: int = 0
        if TYPE_CHECKING:
            from copy import copy
            self.query = copy(query)
        else:
            self.query = dict(query)
        self._call_edit_search: bool = edit_search

    def doModal(self) -> Optional[Source]:
        super().doModal()
        return self.resolved

    def apply_source(self, source: Source, url: str, *, play: Optional[PlayMode] = None) -> None:
        """Apply selected source, return to the sources manager and player."""
        self.resolved = Source(url=url, provider=source.provider, hosting=source.hosting, ffitem=source.ffitem, attr=source.attr,
                               meta=dict(source.meta), resolved=True)
        if play:
            self.resolved.set_play_mode(play)
        self.close()

    def onInit(self) -> None:
        default_color = settings.getString('default.color.identify2')
        duration_in_mins = int(self.item.vtag.getDuration() / 60)
        duration_str = str(duration_in_mins) if duration_in_mins else '–'

        self.setProperty('item.title', str(self.item.title))
        self.setProperty('item.tvshowtitle', self.item.vtag.getTvShowTitle())
        self.setProperty('item.year', str(self.item.year))
        self.setProperty('item.season', str(self.item.season))
        self.setProperty('item.episode', str(self.item.episode))
        self.setProperty('item.duration', L(30111, 'Duration: [B]{duration}[/B] minute|||Duration: [B]{duration}[/B] minutes', n=duration_in_mins, duration=duration_str))
        self.setProperty('item.art.poster', self.item.getArt('poster'))
        self.setProperty('item.art.fanart', self.item.getArt('fanart'))
        self.setProperty('item.endtime', endtime(duration_in_mins))
        self.setProperty('item.colored.default', default_color)
        self.setProperty('sources.edit_button', 'true' if const.sources_dialog.edit_search.in_dialog else 'false')
        self.setProperty('panel.visible', 'false')
        # colors MUST be set in known window, HOME is very know :-D
        home = Window(10000)
        home.setProperty('fanfilm.sources_dialog.info.index.color', const.sources_dialog.index_color)
        # items
        self.add_items(ITEM_LIST, self.lists)
        if self.lists:
            self.setProperty('noitem', 'false')
            self.getControl(NO_ITEMS_LABEL).setVisible(False)
            self.setFocus(self.getControl(ITEM_LIST))
        else:
            self.setProperty('noitem', 'true')
            self.setFocus(self.getControl(RESCAN))
        if self._call_edit_search:
            if not self.edit_search():
                self.close()  # force close on "back"

    def list_items(self, items: Iterable[Source]) -> List[ListItem]:
        return [self.create_list_item(item) for item in items]

    def handle_source(self, *, play_mode: Optional[PlayMode] = None):
        """Try to resolve source. If success keep busy dialog active."""
        try:
            busy_dialog()

            position = self.item_list_widget.getSelectedPosition()
            auto_select = settings.getBool('auto.select.next.item.to.play')
            play_mode = play_mode

            if auto_select:
                for i in range(position, len(self.sources)):
                    if resolved := self.source_factory.resolve_source(src := self.sources[i]):
                        fflog(f'[WIN] auto select: {position=}, {i=}, {resolved=}')
                        self.apply_source(src, resolved, play=play_mode)
                        break
                    play_mode = None
                else:
                    fflog(f'[WIN] auto select: not resolved ({position=}, len={len(self.sources)})')
                    close_busy_dialog()
            else:
                if resolved := self.source_factory.resolve_source(src := self.sources[position]):
                    fflog(f'[WIN] select: {position=}, {resolved=}')
                    self.apply_source(src, resolved, play=play_mode)
                else:
                    fflog(f'[WIN] select: not resolved ({position=})')
                    close_busy_dialog()
        except Exception:
            fflog_exc()
            close_busy_dialog()

    def handle_rescan(self):
        self.raise_exception(RescanSources(query=self.query))
        self.close()
        # url = f"{control.plugin_urresolve_source.item.ffid}"
        # run_plugin(url)

    def handle_download(self):
        position = self.item_list_widget.getSelectedPosition()
        if resolved := self.source_factory.resolve_source(self.sources[position]):
            if settings.getBool('download.downinfo'):
                downitem = self.sources[position]
                info_content = downitem.get('info', '').strip()
                daudio_type = next((t for t in ['Lektor', 'Dubbing', 'Napisy'] if t in info_content), '')
                dlanguage = downitem.get('language', '').upper()
                dquality = downitem.get('quality', '')
                dinfo2 = downitem.get('info2', '')
                downinfo = f'{daudio_type} | {dlanguage} | {dquality} |{dinfo2}'
            else:
                downinfo = ''
            year = self.item.year
            if settings.getBool('download.downlocaltitle'):
                if self.item.episode:
                    dname = f"{self.item.vtag.getTvShowTitle()}.S{self.item.season:02d}E{self.item.episode:02d}"
                    self.show_item = self.item if self.item.ref.is_show else self.item.show_item
                    year = int(self.show_item.vtag.getYear())
                else:
                    dname = self.item.title
            else:
                if self.item.episode:
                    dname = f"{self.item.vtag.getEnglishTvShowTitle()}.S{self.item.season:02d}E{self.item.episode:02d}"
                    self.show_item = self.item if self.item.ref.is_show else self.item.show_item
                    year = int(self.show_item.vtag.getYear())
                else:
                    dname = self.item.vtag.getOriginalTitle()
            from lib.ff.downloader import download
            thread = Thread(
                target=download,
                args=(
                    dname,
                    year,
                    self.getProperty('item.art.poster'),
                    downinfo,
                    resolved,
                ),
            )
            thread.start()

    @property
    def item_list_widget(self) -> ControlList:
        return self.getControl(ITEM_LIST)  # type: ignore[reportReturnType]

    def handle_rebuy(self):
        position = self.item_list_widget.getSelectedPosition()
        src = self.sources[position]
        if resolved := self.source_factory.resolve_source(src, for_resolve={"buy_anyway": True}):
            self.apply_source(src, resolved)

    def edit_search(self) -> bool:
        if query := EditDialog(query=self.query, raise_rescan=False).doModal():
            self.raise_exception(RescanSources(query=query))
            self.close()
            return True
        return False

    def onClick(self, controlId: int) -> None:
        control_id = controlId
        if control_id == ITEM_LIST:
            self.handle_source()
        elif control_id == RESCAN:
            if const.sources_dialog.rescan_edit:
                self.edit_search()
            else:
                self.handle_rescan()
        elif control_id == EDIT_SEARCH:
            self.edit_search()

    def onAction(self, action):
        action_id = action.getId()
        if action_id in CANCEL_ACTIONS:
            self.close()
        elif action_id in MENU_ACTIONS:
            context_menu_items: ContextMenu = []
            if settings.getBool("downloads"):
                context_menu_items.append((control.lang(30115), self.handle_download))
            position = self.item_list_widget.getSelectedPosition()
            src = self.sources[position]
            for action in src.menu_actions():
                label = src.action_label(action)
                if action == 'buy':
                    context_menu_items.append((label, self.handle_rebuy))
                elif is_play_mode(action):
                    context_menu_items.append((label, partial(self.handle_source, play_mode=action)))
            if len(context_menu_items) >= 1:
                ContextMenuDialog(menu=context_menu_items).doModal()
        # elif self.focused_constrol_id == ITEM_LIST and action_id == ACTION_MOVE_LEFT:
        #     Panel().doModal()

    def onFocus(self, controlId: int) -> None:
        control_id = controlId
        self.focused_constrol_id = control_id
        # fflog(f' ######### {control_id = }')
        if control_id == 5011:
            # self.setProperty('panel.visible', 'true')
            Panel().doModal()
            self.setFocusId(ITEM_LIST)

    def create_list_item(self, item: Source) -> ListItem:
        from ..ff.sources import sources
        provider_translations: Dict[str, str] = const.sources.translations.providers.get(self.ui_lang, {})
        hosting_translations: Dict[str, str] = const.sources.translations.hostings.get(self.ui_lang, {})
        hosting = item.hosting
        if not hosting.startswith('plugin.video.'):
            hosting = clear_source(item.hosting)
        info = " ".join(
                    sorted(
                        format_info(item.get("info") or "").strip().lower().split(),
                        key=lambda p: sources.language_type_priority.get(p, 999)
                    )
                )
        fflog(f'[WINDOWS]:  {item=}')
        try:
            label = item['label']
        except KeyError:
            label = f'NONAME from {hosting}'
        li = ListItem(label=label)
        li.setProperty('item.info', info)
        li.setProperty('item.hosting', hosting_translations.get(hosting, hosting))
        li.setProperty('item.colored', item.get('color_identify') or '')
        li.setProperty('item.colored.default', settings.getString("default.color.identify2"))

        size = item.get('size')
        if size is not None:
            li.setProperty('item.size', str(size))

        if item.get('on_account'):
            li.setProperty('item.on_account_expires', item.get('on_account_expires') or 'konto')

        if item.get('no_transfer'):
            li.setProperty('item.no_transfer', str(item.get('no_transfer') or ''))

        for key in ['url', 'info2', 'language', 'quality']:
            if item.get(key) is None:
                fflog(f'[WINDOWS]: ERORR: No key {key!r} in item {item!r} !!!')
            li.setProperty(f'item.{key}', (item.get(key) or '').strip())
        # replace provider suffix
        provider = self.rx_provider_rename.sub(lambda mch: self.provider_suffixes.get(mch['suffix'], mch['suffix']), item.provider)
        li.setProperty('item.provider', provider_translations.get(provider, provider))

        if not li.getProperty('item.info2'):
            li.setProperty('item.info', li.getProperty('item.info').lstrip('| '))

        if settings.getBool('sources.filename_in_2nd_line'):
            filename = item.get('filename', '')
            if filename:
                filename = unescape(unquote(filename))
                if hosting:
                    filename = f': {filename}'
            li.setProperty('item.id', filename)

        if settings.getBool('icon.external') and (icon := item.get('icon')):
            li.setProperty('item.icon', icon)
        return li

# Fonts:
#   - title / heading: ~40, font40_title (Estuary), font38_title/font40 (Eestouchy), font_topbar (AH2R)
