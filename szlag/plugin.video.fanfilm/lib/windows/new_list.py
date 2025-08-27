
from __future__ import annotations
from typing import cast, TYPE_CHECKING
from attrs import frozen
from xbmcgui import ControlEdit, ControlButton, ControlImage, INPUT_TYPE_TEXT
from .base_window import BaseDialog, CANCEL_ACTIONS, EDIT_ACTIONS
from ..ff.log_utils import fflog
from ..kolang import L
from cdefs import ListType
if TYPE_CHECKING:
    from xbmcgui import Action, Control
    from ..defs import RefType
    from ..ff.lists import AddToListCreateOptions
    from .gui import SwitchState


BUTTON_CANCEL = 31
BUTTON_OK = 32
NAME_EDIT = 201
PUBLIC_CHECKBOX = 350


@frozen
class TypeControl:
    """Type control definition."""

    inital: str  # single-letter type name initial
    name: RefType
    control: int
    type: ListType


@frozen(kw_only=True)
class NewListResult:
    """Result of the new list dialog."""

    name: str
    types: ListType
    public: bool = False  # public list by default?


class NewWindowDialog(BaseDialog):
    """Create new list for "add to" dialog."""

    XML = 'NewList.xml'
    CUSTIMZED_XML = True

    TYPES: dict[RefType, TypeControl] = {tc.name: tc for tc in (
        TypeControl('C', 'collection', 301, ListType.COLLECTION),
        TypeControl('M', 'movie',      302, ListType.MOVIE),
        TypeControl('T', 'show',       303, ListType.SHOW),
        TypeControl('S', 'season',     304, ListType.SEASON),
        TypeControl('E', 'episode',    305, ListType.EPISODE),
        TypeControl('P', 'person',     306, ListType.PERSON),
        TypeControl('L', 'list',       307, ListType.LIST),
    )}

    def __init__(self,
                 *args,
                 types: ListType = ListType.MEDIA,
                 enabled_types: ListType = ListType.MIXED,
                 visible_types: ListType = ListType.MIXED,
                 new_list_options: AddToListCreateOptions | None = None,
                 **kwargs,
                 ) -> None:
        """Instance initialization, there are no XML controls yet. See onInit()."""
        super().__init__(*args)
        self.types = types
        self.enabled_types = enabled_types
        self.visible_types = visible_types
        self.new_list_options: AddToListCreateOptions = new_list_options or {}
        for tc in self.TYPES.values():
            # self.setProperty(f'type.{tc.name}.enabled', 'true' if self.enabled_types & tc.type else 'false')
            self.setProperty(f'type.{tc.name}.visible', 'true' if self.visible_types & tc.type else 'false')
        self.setProperty('type.collection.checked', 'true')
        self.setProperty('type.person.texture', 'dialogs/bird.checked.focused.64.png')

    def on_init(self) -> None:
        """Kodi call it on window initialization, access to XML controls is allowed from now."""
        for tc in self.TYPES.values():
            if self.types & tc.type:
                self.set_switch_state(tc.control, 'on')
            self.set_control_enabled(tc.control, bool(self.enabled_types & tc.type))
        edit = cast(ControlEdit, self.getControl(NAME_EDIT))
        edit.setType(INPUT_TYPE_TEXT, L(30395, 'New list name'))
        self.update_edit_line()
        # new list options
        if val := self.new_list_options.get('public'):
            self.set_switch_state(PUBLIC_CHECKBOX, 'on')
        self.set_control_enabled(PUBLIC_CHECKBOX, val is not None)
        # focus
        self.setFocus(self.getControl(NAME_EDIT))
        self._set_ok_enabled()

    def list_name(self) -> str:
        """Return the name of the new list."""
        edit = cast(ControlEdit, self.getControl(NAME_EDIT))
        return edit.getText().strip()

    def list_type(self) -> ListType:
        """Return the selected types of the new list."""
        types = ListType.NONE
        for tc in self.TYPES.values():
            if (sw := self.get_switch_state(tc.control)) and sw.value:
                types |= tc.type
        return types

    def on_click(self, control_id: int) -> None:
        """Kodi sent the control click."""
        if control_id == BUTTON_CANCEL:
            self.close()
        elif control_id == BUTTON_OK and (name := self.list_name()) and (types := self.list_type()):
            pub_sw = self.get_switch_state(PUBLIC_CHECKBOX)
            self.close(NewListResult(name=name, types=types, public=bool(pub_sw and pub_sw.value)))
        elif control_id == NAME_EDIT:
            self._set_ok_enabled()

    def on_action(self, action: Action) -> None:
        """Kodi sent the action."""
        if self.default_action(action):
            return
        action_id = action.getId()
        if action_id in EDIT_ACTIONS:  # and focused_id == NAME_EDIT:
            self.update_edit_line()

    def on_focus(self, control_id: int) -> None:
        """Kodi sent the control's focus."""
        self.update_edit_line()

    def _set_ok_enabled(self) -> None:
        """Set OK button enabled state."""
        self.getControl(BUTTON_OK).setEnabled(bool(self.list_name().strip() and self.list_type() is not ListType.NONE))

    def update_edit_line(self) -> None:
        """Update GUI properties for edit line control."""
        edit = cast(ControlEdit, self.getControl(NAME_EDIT))
        if edit.getText() or self.focused_id() == NAME_EDIT:
            self.setProperty('edit_control.textcolor', 'BFFFFFFF')
        else:
            self.setProperty('edit_control.textcolor', '99999999')
        self._set_ok_enabled()

    def on_switch_changed(self, control_id: int, state: SwitchState) -> None:
        """GUI sent the switch state change."""
        self._set_ok_enabled()
