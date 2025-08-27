
from __future__ import annotations
from typing import cast, TYPE_CHECKING
from typing_extensions import Literal
from pathlib import Path
from attrs import frozen
from xbmcgui import ControlList, ListItem
from .base_window import BaseDialog, CANCEL_ACTIONS
from ..ff.item import FFItem
from ..ff.lists import AddToServices, AddToServiceDefs, LIST_POINTERS
from ..ff.tricks import pairwise
from ..ff.types import flag_names
from ..ff.control import art_path, notification
from ..ff.log_utils import fflog, fflog_exc
from ..kolang import L
from cdefs import ListType, ListTarget, ListPointer
from const import const
if TYPE_CHECKING:
    from typing import Any, Iterable, Sequence, Collection, ClassVar
    from xbmcgui import Action, Control
    from ..defs import RefType, FFRef
    from ..ff.lists import ServiceDescr
    from .new_list import NewListResult


HEADER_TYPES_LABEL = 104
HEADER_TYPES_BOX = 105
SERVICE_LIST = 222
LIST_LIST = 223
BUTTON_CANCEL = 31
BUTTON_NEW_LIST = 33
BUTTON_LIMIT_ITEMS = 34
BUTTON_DEBUG = 39

#: ...
AddToDialogMediaBarMode = Literal['hide', 'icons', 'labels', 'initial', 'notoco']


@frozen
class HeaderControl:
    inital: str  # single-letter type name initial
    type: RefType
    icon: int
    label: int
    title: str  # localized (translated)
    notoco: str  # trolling

    @property
    def list_type(self) -> ListType:
        return ListType.from_media_ref(self.type)


@frozen(kw_only=True)
class ListInfo:
    """Information about the list."""
    service: ServiceDescr
    name: str
    id: str
    type: ListType
    item: FFItem
    tab_label: str = ''  # label for the list, used in the dialog

    def add_items(self, items: Iterable[FFRef]) -> int | None:
        """Add items to the selected list."""
        target = ListTarget.from_ffitem(self.item)
        return self.service.add_items(target, items)


class AddToDialog(BaseDialog):
    """General add media (and other refs) to anything, like lists or library."""

    XML = 'AddTo.xml'
    CUSTIMZED_XML = True

    HEADER_CONTROLS: dict[RefType, HeaderControl] = {h.type: h for h in (
        HeaderControl('C', 'collection', 200, 201, L(30388, '{n} collection|||{n} collections'), '시리즈'),
        HeaderControl('M', 'movie',      202, 203, L(30888, '{n} movie|||{n} movies'), ' 영화'),
        HeaderControl('T', 'show',       204, 205, L(30389, '{n} show|||{n} shows'), '드라마'),  # '시리즈'
        HeaderControl('S', 'season',     206, 207, L(30390, '{n} season|||{n} seasons'), '시즌'),
        HeaderControl('E', 'episode',    208, 209, L(30391, '{n} episode|||{n} episodes'), '에피소드'),  # '화와'
        HeaderControl('P', 'person',     210, 211, L(30392, '{n} person|||{n} persons'), '인물'),
        HeaderControl('L', 'list',       212, 213, L(30393, '{n} list|||{n} lists'), '글자'),
    )}

    def __init__(self,
                 *args,
                 items: Iterable[FFRef],
                 services: AddToServices | AddToServiceDefs | None = None,
                 **kwargs,
                 ) -> None:
        """Instance initialization, there are no XML controls yet. See onInit()."""
        super().__init__(*args)
        # To handle shit-kodi-gui events.
        self.list_current_indexes: dict[int, int] = {
            SERVICE_LIST: -1,
            LIST_LIST: -1,
        }
        self.source_items: list[FFRef] = list(items)
        self.source_services: AddToServices | AddToServiceDefs | None = services
        self.items: list[FFRef] = []
        self.item_counts: dict[RefType, int] = {}
        self.existing_types = ListType.NONE
        self.services: AddToServices = {}
        self._reinit(len(self.source_items))

    def _reinit(self, max_length: int) -> None:
        self.items = self.source_items[:max_length]
        self.item_counts = {}
        for it in self.items:
            rtype = it.ref.real_type
            self.item_counts[rtype] = self.item_counts.get(rtype, 0) + 1
        for rtype in self.item_counts:
            self.existing_types |= ListType.from_media_ref(rtype)
        # build service tree
        services = self.source_services
        if services is None:
            services = const.dialog.add_to.lists.default
        self.services = {label: [LIST_POINTERS[cast(ListPointer, ptr)] if isinstance(ptr, str) else ptr for ptr in pointers]
                         for label, pointers in (services or const.dialog.add_to.lists.services).items()}
        # filter service tree
        self.services = {label: pointers for label, wanted_pointers in self.services.items()
                         if (pointers := [ptr for ptr in wanted_pointers if ptr.is_enabled()])}
        self.list_list: list[FFItem] = []
        self.setProperty('item_count', str(len(self.items)))
        self.setProperty('type_label', '')
        for typ in self.HEADER_CONTROLS:
            self.setProperty(f'type.{typ}.count', str(sum(it.ref.real_type == typ for it in self.items)))
        self.media_type_bar: AddToDialogMediaBarMode = const.dialog.add_to.media_type.bar_mode

    def on_init(self) -> None:
        """Kodi call it on window initialization, access to XML controls is allowed from now."""
        self.getControl(HEADER_TYPES_BOX).setVisible(False)
        self.getControl(HEADER_TYPES_LABEL).setVisible(False)
        width = 128
        y = 2
        show_types = self.existing_types | const.dialog.add_to.media_type.absent_visible
        header_controls = [hc for hc in self.HEADER_CONTROLS.values() if hc.list_type & show_types]
        x = (self.getControl(HEADER_TYPES_BOX).getWidth() - width * len(header_controls)) // 2
        for hc in header_controls:
            self.getControl(hc.icon).setPosition(x, y)
            self.getControl(hc.label).setPosition(x + 48, y)
            x += width
        for hc in self.HEADER_CONTROLS.values():
            self.getControl(hc.icon).setVisible(bool(hc.list_type & show_types))
            self.getControl(hc.label).setVisible(bool(hc.list_type & show_types))
        self.add_items(SERVICE_LIST, list(self.services))
        # self.add_items(SERVICE_LIST, [chr(65 + i)*3 for i in range(26)])  # DEBUG
        self.update_media_bar(ListType.MEDIA)
        self.setFocus(self.getControl(SERVICE_LIST))

    def on_close(self) -> None:
        """Kodi call it on window close, no access to XML controls is allowed from now."""
        self.source_items.clear()  # Remove FFItems to prevent memory leaks.
        self.items.clear()  # Remove FFItems to prevent memory leaks.

    def item_count(self, allowed: ListType | None = None) -> int:
        if allowed is None:
            allowed = self.current_list().type
        return sum(self.item_counts.get(hc.type, 0) for hc in self.HEADER_CONTROLS.values() if hc.list_type & allowed)

    def update_media_bar(self, allowed: ListType) -> None:
        """Update colors based on destination allowed media types."""
        def color(typ: RefType) -> str:
            ltype = ListType.from_media_ref(typ)
            if not ltype & self.existing_types:
                return const.dialog.add_to.media_type.absent_color
            if ltype & allowed:
                return const.dialog.add_to.media_type.exist_color
            return const.dialog.add_to.media_type.disallowed_color

        item_count = self.item_count(allowed)
        self.setProperty('window_title', L(30401, 'Add {matched} / {n} item|||Add {matched} / {n} items', n=len(self.items), matched=item_count))
        if self.media_type_bar == 'icons':
            for typ in self.HEADER_CONTROLS:
                self.setProperty(f'type.{typ}.color', color(typ))
        elif self.media_type_bar == 'labels':
            self.setProperty('type_label', ', '.join(f'[COLOR {color(hc.type)}]{L.get_text(hc.title, n=self.item_counts.get(hc.type, 0))}[/COLOR]'
                                                     for hc in self.HEADER_CONTROLS.values()))
        elif self.media_type_bar == 'initial':
            self.setProperty('type_label', ',     '.join(f'[COLOR {color(hc.type)}]{hc.inital}: {self.item_counts.get(hc.type, 0)}[/COLOR]'
                                                         for hc in self.HEADER_CONTROLS.values()))
        elif self.media_type_bar == 'notoco':
            self.setProperty('type_label', ', '.join(f'[COLOR {color(typ)}]{self.item_counts.get(typ, 0)} {hc.notoco}[/COLOR]'
                                                     for typ, hc in self.HEADER_CONTROLS.items()))
        self.getControl(HEADER_TYPES_BOX).setVisible(self.media_type_bar == 'icons')
        self.getControl(HEADER_TYPES_LABEL).setVisible(self.media_type_bar in ('labels', 'initial', 'notoco'))

    def update_list(self) -> None:
        """Update list of the lists for current selected service."""
        def xxx_new_item(label: str, level: int = 0) -> ListItem:
            level = int(label[-1])
            it = ListItem(label)
            it.setArt({'icon': str(path / 'userlists.png')})
            it.setProperty('item.indent', str(level))
            if level <= 1:
                it.setProperty('item.indent.label', '')
            elif level <= 3:
                it.setProperty('item.indent.label', '>' * level)
            else:
                it.setProperty('item.indent.label', f'{level}× >')
            return it

        def proc_item_list(it: FFItem) -> Iterable[FFItem]:
            exist_color = const.dialog.add_to.media_type.exist_color
            absent_color = const.dialog.add_to.media_type.absent_color
            types = ListType.new(it.getProperty('list_type'))
            for typ in ListType.iter_single_flags():
                name = (typ.name or '').lower()
                it.setProperty(f'type.{name}.color', exist_color if typ & types else absent_color)
            yield it

        path = Path(art_path)
        _, services = self.current_service()
        self.list_list = [it for srv in services for lst in srv.lists() for it in proc_item_list(lst)]
        for a, b in pairwise(self.list_list):
            if a.getProperty('group') != b.getProperty('group'):
                b.setProperty('separator.above', 'true')
        self.add_items(LIST_LIST, self.list_list)
        self.list_current_indexes[LIST_LIST] = -1
        self.check_events()
        self.update_new_list_button()
        self.update_limit_items_button()

    def update_new_list_button(self) -> None:
        """Update the "New List" button state."""
        _, services = self.current_service()
        button = self.getControl(BUTTON_NEW_LIST)
        button.setEnabled(any(srv.create_enabled() for srv in services))

    def update_limit_items_button(self) -> None:
        """Update the "Limit Items" button state."""
        button = self.getControl(BUTTON_LIMIT_ITEMS)
        count = self.item_count()
        button.setEnabled(count > 1)

    def current_service(self) -> tuple[str, Sequence[ServiceDescr]]:
        """Return currently selected service."""
        widget = cast(ControlList, self.getControl(SERVICE_LIST))
        label, services = tuple(self.services.items())[widget.getSelectedPosition()]
        return label, tuple(services)

    def current_list(self) -> ListInfo:
        """Return currently selected list (from central widget)."""
        widget = cast(ControlList, self.getControl(SERVICE_LIST))
        service_label = tuple(self.services.keys())[widget.getSelectedPosition()]
        widget = cast(ControlList, self.getControl(LIST_LIST))
        item = self.list_list[widget.getSelectedPosition()]
        pointer: ListPointer = item.getProperty('pointer')  # type: ignore[assignment]
        service = LIST_POINTERS[pointer]
        list_id = item.getProperty('list_id')
        name = item.getLabel()
        return ListInfo(service=service, name=name, id=list_id or name, type=ListType.new(item.getProperty('list_type')), item=item,
                        tab_label=service_label)

    def check_events(self) -> None:
        """Determine what could change in the GUI. Manually because GUI is fucked up."""
        for control_id, old_index in self.list_current_indexes.items():
            if widget := cast(ControlList, self.getControl(control_id)):
                if (index := widget.getSelectedPosition()) != old_index:
                    self.list_current_indexes[control_id] = index
                    self.on_event('current_index_changed', control_id, index)

    def on_click(self, control_id: int) -> None:
        """Kodi sent the control's click."""
        self.check_events()
        if control_id == BUTTON_CANCEL:
            self.close()
        elif control_id == BUTTON_NEW_LIST:
            from .new_list import NewWindowDialog
            label, cur_service = self.current_service()
            if service := next(iter(srv for srv in cur_service if srv.create_enabled()), None):
                def_types = service.new_types if service.new_types else ListType.MEDIA | ListType.COLLECTION
                new_opts = service.new_list_options or {}
                new: NewListResult | None = NewWindowDialog(types=def_types & service.types, enabled_types=service.edit_types & service.types,
                                                            new_list_options=new_opts).doModal()
                fflog(f'new list: {new=}')  # TODO: remove this log
                if new:
                    if service.create(new.name, type=new.types, public=new.public):
                        notification(L(30484, 'Create {service} list').format(service=label),
                                     L(30485, 'List {name} has been created').format(name=new.name), visible=True)
                        self.update_list()
                    else:
                        from xbmcgui import Dialog
                        fflog(f'Failed to create {label} list {new.name!r} with types {flag_names(new.types)}')
                        Dialog().ok(L(30394, 'Error'),
                                    L(30486, 'Failed to {service} create list {name}.').format(service=label, name=new.name))
        elif control_id == LIST_LIST:
            # List selected, add items to it.
            lst = self.current_list()
            # num = lst.service.add_items(lst.item, self.items)
            # notification(f'Add to {lst.service.name} list', f'Added {num} items to {lst.name}.', visible=True)
            self.close(lst)
        elif control_id == BUTTON_LIMIT_ITEMS:
            from xbmcgui import Dialog
            ShowAndGetNumber = 0
            total = self.item_count(ListType.ALL)
            heading = L(30491, 'Enter number of items (1..{total})').format(total=total)
            if snum := Dialog().numeric(ShowAndGetNumber, heading):
                if snum.isdecimal():
                    snum = int(snum)
                    self._reinit(max(1, min(snum, len(self.source_items))))
                    self.update_list()
                    lst = self.current_list()
                    self.update_media_bar(lst.type)
                    self.update_new_list_button()
                    self.update_limit_items_button()
        elif control_id == BUTTON_DEBUG:
            from xbmcgui import Dialog
            Dialog().ok('H', 'Mmm')

    def on_action(self, action: Action) -> None:
        """Kodi sent the action."""
        self.check_events()
        if self.default_action(action):
            return

    def on_control(self, control: Control) -> None:
        """The control's click events."""
        self.check_events()

    def on_focus(self, control_id: int) -> None:
        """Kodi sent the control's focus."""
        self.check_events()

    def on_event(self, event: str, control_id: int, value: Any = None) -> None:
        fflog(f' ######### event: {event = }, {control_id = }, {value = }')
        if event == 'current_index_changed':
            if control_id == SERVICE_LIST:
                self.update_list()
            elif control_id == LIST_LIST:
                lst = self.current_list()
                self.update_media_bar(lst.type)
                self.update_new_list_button()
                self.update_limit_items_button()
