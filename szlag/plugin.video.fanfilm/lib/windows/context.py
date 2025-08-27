from typing import List, TYPE_CHECKING
from ..windows.base_window import BaseDialog
from ..ff.menu import ContextMenuItem, ContextMenu
from ..ff.control import execute
from xbmcgui import ListItem

CONTEXT_MENU_ITEM_LIST = 9000
# CONTEXT_MENU_BOX = 9001
ITEM_HEIGHT = 75
MAX_ITEM_VISIBLE = 5


class ContextMenuDialog(BaseDialog):
    """Custom context-menu for custom XML windows."""

    XML = 'ContextMenu.xml'

    def __init__(self, *args, menu: ContextMenu) -> None:
        super().__init__(*args)
        self.items: List[ContextMenuItem] = list(menu)
        self._menu_items: List[ListItem] = []

    def onInit(self):
        self._prepare(self.items)
        self.add_items(CONTEXT_MENU_ITEM_LIST, self._menu_items)
        self.setFocus(self.getControl(CONTEXT_MENU_ITEM_LIST))
        height = ITEM_HEIGHT * max(1, min(MAX_ITEM_VISIBLE, len(self.items)))
        # self.getControl(CONTEXT_MENU_BOX).setHeight(height)
        self.getControl(CONTEXT_MENU_ITEM_LIST).setHeight(height)

    def onClick(self, controlId):
        if controlId == CONTEXT_MENU_ITEM_LIST:
            position: int = self.getControl(CONTEXT_MENU_ITEM_LIST).getSelectedPosition()
            action = self.items[position][1]

            if isinstance(action, str):
                execute(action)
            elif callable(action):
                if TYPE_CHECKING:
                    from ..ff.routing import subobject
                    assert not isinstance(action, subobject)
                action()

            self.close(position)

    def _prepare(self, items: ContextMenu) -> None:
        self.items = [menu for menu in self.items if getattr(menu, 'visible', True)]
        self._menu_items = [ListItem(menu[0]) for menu in self.items]
