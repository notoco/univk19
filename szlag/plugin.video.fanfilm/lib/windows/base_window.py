from __future__ import annotations
from typing import Optional, Union, Any, Tuple, Dict, Sequence, Callable, Type, NamedTuple, ClassVar, cast, TYPE_CHECKING
from typing_extensions import Self, TypeVar, Generic, Literal
from threading import Thread, Condition
from pathlib import Path
from datetime import datetime, timezone
from attrs import define, frozen, field
from xbmcgui import WindowXML, WindowXMLDialog, ControlList, ControlImage
from xbmcgui import (
    ACTION_PARENT_DIR, ACTION_PREVIOUS_MENU, ACTION_STOP, ACTION_NAV_BACK,
    ACTION_MOUSE_RIGHT_CLICK, ACTION_MOUSE_LONG_CLICK, ACTION_CONTEXT_MENU,
)
from ..ff import control
from ..ff.tricks import MISSING
from ..ff.threads import Queue
from ..ff.log_utils import fflog, fflog_exc
# from ..ff.debug import logtime
from const import const
if TYPE_CHECKING:
    from xbmcgui import ListItem, Action, Control
    from .gui import CustomXmlData, SwitchState


T = TypeVar('T')
B = TypeVar('B', 'BaseWindow', 'BaseDialog')
Args = Tuple[Type[T], ...]
KwArgs = Dict[str, Any]

Errors = Literal['strict', 'ignore']

#: Type letter in edit-control (on Linux).
ACTION_EDIT_TYPING = 61952
ACTION_EDIT_BACKSPACE = 61448
ACTION_EDIT_DELETE = 61575
EDIT_ACTIONS = {
    ACTION_EDIT_TYPING,
    ACTION_EDIT_BACKSPACE,
    ACTION_EDIT_DELETE,
}

#: Actions (keys) to close / cancel / escape.
CANCEL_ACTIONS = {
    ACTION_PARENT_DIR,
    ACTION_PREVIOUS_MENU,
    # ACTION_PAUSE,
    ACTION_STOP,
    ACTION_NAV_BACK,
}

#: Actions (keys) for context-menu.
MENU_ACTIONS = {
    ACTION_MOUSE_RIGHT_CLICK,
    ACTION_MOUSE_LONG_CLICK,
    ACTION_CONTEXT_MENU,
}


class WindowCommand(NamedTuple):
    method: Callable
    args: Args
    kwargs: KwArgs


class WindowThread(Thread, Generic[B]):
    """Thread to call window's doModal() in thread (non blocking)."""

    def __init__(self,
                 win_class: Type[B],
                 name: Optional[str] = None,
                 args: Args = (),
                 kwargs: KwArgs = {},  # noqa: B006
                 ) -> None:
        super().__init__(name=name)
        #: Window class to create the window.
        self.win_class = win_class
        #: Arguments for window create.
        self.args: Args = args
        #: Keyword arguments for window create.
        self.kwargs: KwArgs = kwargs
        #: The window.
        self.win: B | None = None
        #: Thread condition variable for window creation.
        self.win_ready = Condition()
        #: Window commands (doModal) queue.
        self.win_commands: Queue[WindowCommand | None] = Queue()

    def run(self) -> None:
        """Do job. Main thread proc."""
        fflog.debug(f'••• [TH] create win {self.win_class}, {self.args}, {self.kwargs}')
        self.win = self.win_class(*self.args, **self.kwargs)
        try:
            fflog.debug('••• [TH] notify')
            with self.win_ready:
                self.win_ready.notify()
            while True:
                fflog.debug('••• [TH] wait for command')
                cmd = self.win_commands.get()
                fflog.debug(f'••• [TH] {cmd=}')
                if not cmd:
                    break
                cmd.method(*cmd.args, **cmd.kwargs)
                self.win_commands.task_done()
        finally:
            fflog.debug('••• [TH] close')
            self.win.close()
        fflog.debug('••• [TH] finished')

    def command(self, method: Callable, *args, **kwargs) -> None:
        """Postpone window method call."""
        self.win_commands.put(WindowCommand(method, args, kwargs))

    def stop(self) -> None:
        """Stop the window thread."""
        self.win_commands.put(None)


class _WindowMetaClass(type):
    """Base Window meta-class to modify __init__ arguments."""

    def __call__(self, *args, **kwargs):
        return super().__call__(*args, **kwargs).__wrapped__


@frozen
class XmlWindowsArgs:
    xml_filename: str
    script_path: str
    default_skin: str
    default_res: str
    xml_source: Path
    xml_path: Path
    customized_xml: bool
    custom_data: CustomXmlData


class AbstractWindow:

    XML: ClassVar[str] = ''
    CUSTIMZED_XML: ClassVar[bool] = False

    if TYPE_CHECKING:
        _customised_xml: bool
        _customised_data: CustomXmlData

        def getControl(self, iControlId: int) -> Control: ...

    @classmethod
    def _resolve_args(cls,
                      xmlFilename: Optional[str] = None,
                      scriptPath: Optional[str] = None,
                      defaultSkin: Optional[str] = None,
                      defaultRes: Optional[str] = None,
                      *args,
                      **kwargs,
                      ) -> XmlWindowsArgs:
        if xmlFilename is None:
            xmlFilename = cls.XML
        if scriptPath is None:
            scriptPath = control.addonPath
        if defaultSkin is None:
            defaultSkin = 'Default'
        if defaultRes is None:
            defaultRes = '1080i'  # kodi default: 720p
        xml_source = Path(scriptPath) / 'resources' / 'skins' / defaultSkin / defaultRes / xmlFilename

        if customized_xml := kwargs.pop('customized_xml', cls.CUSTIMZED_XML):
            now = datetime.now(timezone.utc)
            xmlFilename = const.tune.gui.xml_output_filename.format(xml_source.name, name=xml_source.name, stem=xml_source.stem,
                                                                    suffix=xml_source.suffix, suffixes=xml_source.suffixes,
                                                                    path=xml_source, parent=xml_source.parent, folder=xml_source.parent,
                                                                    now=now, date=now.date(), time=now.time(), timestamp=int(now.timestamp()))
            xml_path = Path(scriptPath) / 'resources' / 'skins' / defaultSkin / defaultRes / xmlFilename
            custom_data = _customize_xml(xml_source, xml_path)
        else:
            from .gui import CustomXmlData
            xml_path = xml_source
            custom_data = CustomXmlData()
        return XmlWindowsArgs(xmlFilename, scriptPath, defaultSkin, defaultRes, xml_source, xml_path, customized_xml, custom_data)

    def on_closing(self) -> None:
        """Custom function called when window goint to close."""

    def on_close(self) -> None:
        """Custom function called on window close."""

    def on_init(self) -> None:
        """Kodi call it on window initialization, access to XML controls is allowed from now. Custom callback."""

    def default_action(self, action: Action) -> bool:
        """Handle default action."""
        action_id = action.getId()
        if action_id in CANCEL_ACTIONS:
            self.close()
            return True
        return False

    def on_action(self, action: Action) -> None:
        """Kodi sent the action. Custom callback."""
        self.default_action(action)

    def on_click(self, control_id: int) -> None:
        """Kodi sent the control's click. Custom callback."""

    def on_focus(self, control_id: int) -> None:
        """Kodi sent the control's focus. Custom callback."""

    def on_control(self, control: Control) -> None:
        """Kodi sent all click events on owned and selected controls when the control itself doesn't handle the message. Custom callback."""

    def on_switch_changed(self, control_id: int, state: SwitchState) -> None:
        """FanFilm sent the switch's state change."""

    def close(self) -> None:
        self.on_closing()
        super().close()  # type: ignore[reportAttributeAccessIssue]
        self.on_close()

    def onInit(self) -> None:
        """Kodi call it on window initialization, access to XML controls is allowed from now."""
        fflog(' +++++++++ onInit:')
        self.on_init()

    def onAction(self, action: Action) -> None:
        """Kodi sent the action."""
        fflog(f' +++++++++ onAction: id = {action.getId()!r}, amount = {action.getAmount1()!r}, {action.getAmount2()!r}, button = {action.getButtonCode()!r}')
        self.on_action(action)

    def onClick(self, controlId: int) -> None:
        """Kodi sent the control's click."""
        fflog(f' +++++++++ onClick: {controlId = }')
        if switch := self._customised_data.switches.get(controlId):
            state = switch.state
            switch.click()
            self._handle_switch(controlId)
            if switch.state is not state:
                self.on_switch_changed(controlId, switch.state)
        self.on_click(controlId)

    def onFocus(self, controlId: int) -> None:
        """Kodi sent the control's focus."""
        fflog(f' +++++++++ onFocus: {controlId = }')
        self._handle_switch(controlId, check_focus=True)
        self.on_focus(controlId)

    def onControl(self, control: Control) -> None:
        """Kodi sent all click events on owned and selected controls when the control itself doesn't handle the message."""
        fflog(f' +++++++++ onControl: {control = }')
        self.on_control(control)

    def _handle_switch(self, control_id: int, *, check_focus: bool = False) -> None:
        if check_focus:
            focused_id = self.focused_id()
            for control_id, switch in self._customised_data.switches.items():
                switch.control_state = switch.control_state.with_flag(switch.FOCUSED, control_id == focused_id)

        for control_id, switch in self._customised_data.switches.items():
            for subcontrol_name in switch.style.subcontrols:
                try:
                    subcontrol = cast(ControlImage, self.getControl(switch.subcontrols_id[subcontrol_name]))
                    subcontrol_def = switch.state.subcontrols[subcontrol_name]
                    old_subcontrol = switch.applied.state and switch.applied.state.subcontrols[subcontrol_name]
                except (RuntimeError, KeyError):
                    pass
                    # fflog_exc(title=f' +++++++++ _handle_switch: {control_id = }, {switch = }, {subcontrol_name = }')
                else:
                    if not switch.is_applied():
                        texture = subcontrol_def.texture(switch.control_state)
                        texture_path = texture.format_path(switch.control_state, switch_state=switch.state)
                        old_control_state = switch.applied.control_state
                        if (old_subcontrol is None or switch.applied.state is None
                                or old_subcontrol.texture_path(old_control_state, switch_state=switch.applied.state) != texture_path):
                            subcontrol.setImage('' if texture_path == '-' else texture_path)
                        if old_subcontrol is None or old_subcontrol.texture(old_control_state).color_diffuse != texture.color_diffuse:
                            subcontrol.setColorDiffuse(texture.color_diffuse)
            if not switch.is_applied():
                switch.set_applied()

    def focused_id(self) -> int:
        """Return ID of focused control or zero if no focus."""
        try:
            return self.getFocusId()  # type: ignore[reportAttributeAccessIssue]
        except RuntimeError:  # from kodi docs: raises RuntimeError if no control has focus
            return 0

    def set_control_enabled(self, control_id: int, enabled: bool, *, errors: Errors = 'ignore') -> None:
        """Enable or disable control by ID."""
        try:
            control = self.getControl(control_id)
        except RuntimeError:
            if errors == 'strict':
                msg = f'No control {control_id!r} in {self.__class__.__name__}'
                fflog(msg)
                raise KeyError(msg)
            return
        control.setEnabled(bool(enabled))
        if switch := self._customised_data.switches.get(control_id):
            new_control_state = switch.control_state.with_flag(switch.ENABLED, enabled)
            if switch.control_state != new_control_state:
                switch.control_state = new_control_state
                self._handle_switch(control_id)

    def set_switch_state(self, control_id: int, state: str, *, errors: Errors = 'ignore') -> None:
        """Set switch state by control ID."""
        if switch := self._customised_data.switches.get(control_id):
            if state != switch.state.name:
                switch.set(state)
                self._handle_switch(control_id)
                self.on_switch_changed(control_id, switch.state)
        elif errors == 'strict':
            msg = f'No switch for control {control_id!r} in {self.__class__.__name__}'
            fflog(msg)
            raise KeyError(msg)

    def switch_state(self, control_id: int) -> SwitchState:
        """Get switch state by control ID."""
        if switch := self._customised_data.switches.get(control_id):
            return switch.state
        msg = f'No switch for control {control_id!r} in {self.__class__.__name__}'
        fflog(msg)
        raise KeyError(msg)

    def get_switch_state(self, control_id: int) -> SwitchState | None:
        """Get switch state by control ID."""
        if switch := self._customised_data.switches.get(control_id):
            return switch.state
        return None


class BaseWindow(AbstractWindow, WindowXML):

    def __new__(cls,
                xmlFilename: Optional[str] = None,
                scriptPath: str = control.addonPath,
                defaultSkin: str = 'Default',
                defaultRes: str = '1080i',  # '720p',
                *args,
                **kwargs) -> Self:
        obj: BaseWindow
        xml_args = cls._resolve_args(xmlFilename, scriptPath, defaultSkin, defaultRes, *args, **kwargs)
        obj = super().__new__(cls, xml_args.xml_filename, xml_args.script_path, xml_args.default_skin, xml_args.default_res, *args)
        obj.__init__(xml_args.xml_filename, xml_args.script_path, xml_args.default_skin, xml_args.default_res, *args, **kwargs)
        obj._customised_xml = xml_args.customized_xml
        obj._customised_data = xml_args.custom_data
        return obj

    def add_items(self, control_id: int, items: Sequence[Union[str, ListItem]]) -> None:
        control = self.getControl(control_id)
        if isinstance(control, ControlList):
            control.reset()
            control.addItems(items)  # type: ignore - ControlList.addItems() accepts Sequence[]


class BaseDialog(AbstractWindow, WindowXMLDialog):

    if TYPE_CHECKING:
        _result: Any
        _exception: Optional[BaseException]
        _closed: bool
        _thread: WindowThread | None

    def __new__(cls,
                xmlFilename: Optional[str] = None,
                scriptPath: Optional[str] = None,
                defaultSkin: Optional[str] = None,
                defaultRes: Optional[str] = None,
                *args,
                modal: bool = True,
                _call_init: bool = True,
                **kwargs) -> Self:
        obj: Self
        fflog.debug(f'BaseDialog.__new__({cls=}, {xmlFilename=}, {scriptPath=}, {defaultSkin=}, {defaultRes=}, {args=}, {modal=}, {_call_init=}, ...)')
        # fflog.debug(f'BaseDialog.__new__({cls=}, {xmlFilename=}, {scriptPath=}, {defaultSkin=}, {defaultRes=}, {args=}, {modal=}, {_call_init=}, {kwargs=})')
        xml_args = cls._resolve_args(xmlFilename, scriptPath, defaultSkin, defaultRes, *args, **kwargs)
        if modal:
            obj = super().__new__(cls, xml_args.xml_filename, xml_args.script_path, xml_args.default_skin, xml_args.default_res)
            obj._thread = None
        else:
            # for non-blocking dialogs, window is created in thread
            th = WindowThread[Self](super().__new__, name=f'WindowThread.{xml_args.xml_filename}',
                                    args=(cls, xml_args.xml_filename, xml_args.script_path, xml_args.default_skin, xml_args.default_res, *args))
            fflog.debug(f'••• start thread {th}')
            th.start()
            with th.win_ready:
                if not th.win:
                    fflog.debug('••• wait for window')
                    th.win_ready.wait()
            obj = th.win
            obj._thread = th
        obj._closed = False
        obj._result = None
        obj._exception = None
        obj._customised_xml = xml_args.customized_xml
        obj._customised_data = xml_args.custom_data
        if _call_init:
            fflog.debug('••• init')
            obj.__init__(xml_args.xml_filename, xml_args.script_path, xml_args.default_skin, xml_args.default_res, *args, **kwargs)
        fflog.debug('••• created')
        return obj
        # return ObjectProxy(obj)  # to avoid __init__ call, _WindowMetaClass will remove ObjectProxy

    def __init__(self, *args, **kwargs) -> None:
        """Useless, because WindowXMLDialog uses __new__ only."""
        pass

    def raise_exception(self, exception: BaseException) -> None:
        """Set exception to raise from doModal()."""
        self._exception = exception

    def result(self) -> Any:
        """Get result of dialog."""
        if self._closed:
            return self._result
        raise RuntimeError('Dialog is not closed yet, call doModal() or close() first.')

    def set_result(self, result: Any) -> None:
        """Explicit set the result. Useful with doModal()."""
        self._result = result

    def close(self, result: Any = MISSING) -> None:
        self._closed = True
        if result is not MISSING:
            self._result = result
        self.on_closing()
        if self._thread:
            fflog.debug('••• postpone exit')
            self._thread.stop()
        fflog.debug('••• close')
        super().close()
        fflog.debug('••• on_close')
        self.on_close()
        fflog.debug('••• finished')

    def doModal(self) -> Any:
        """Ececute the window. Call doModal direct (modal) or in thread (modeless)."""
        if self._thread:
            from ..ff.kotools import KodiMonitor
            self.show()
            fflog.debug(f'••• postopne {self.doModal}')
            xmonitor = KodiMonitor.instance()
            if xmonitor is None:
                self._thread.command(super().doModal)
            else:
                # Abort window thread on Kodi exit
                with xmonitor.abort_context(self._thread.stop):
                    self._thread.command(super().doModal)
            fflog.debug(f'••• sent {self.doModal}')
        else:
            super().doModal()
        if not self._closed:
            self._closed = True
            self.on_close()
        if self._exception:
            raise self._exception
        return self._result

    def is_modal(self) -> bool:
        """Return True if dialog is modal."""
        return not self._thread

    def destroy(self) -> None:
        """Close and clean up."""
        self.close()
        if self._thread:
            self._thread.join()

    def add_items(self, control_id: int, items: Sequence[Union[str, ListItem]]) -> None:
        """Add items to control list `control_id`."""
        control = self.getControl(control_id)
        if isinstance(control, ControlList):
            control.reset()
            control.addItems(items)  # type: ignore[reportArgumentType] - ControlList.addItems() accepts Sequence[]


def _customize_xml(xml_source: Path, xml_path: Path) -> CustomXmlData:
    """Fix window/dialog source XML to handle what kodi can not."""
    from .gui import custom_xml
    return custom_xml(xml_source, xml_path)
