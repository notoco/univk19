
from typing import Optional, Union, Any, List, Sequence, Iterable, Iterator, TYPE_CHECKING
from typing_extensions import Self, TypeAlias
from collections import UserList
from enum import Enum
from pathlib import Path
from attrs import define, field
from .base_window import BaseDialog
from ..ff.log_utils import fflog, fflog_exc
from ..kolang import KodiLabels
from const import const


class KnownButton(Enum):
    CANCEL = 222
    OK = 186
    NO = 106
    YES = 107
    CLOSE = 15067
    DONE = 20177
    SAVE = 190
    CLEAR = 192
    SEARCH = 137
    SCAN = 193
    NEXT = 209
    PREVIOUS = 210
    DISABLE = 24021
    ENABLE = 24022


@define
class Button:
    name: str
    value: Optional[int] = None
    width: int = field(default=0, kw_only=True)
    control_id: int = field(default=0, init=False)
    known: Optional[KnownButton] = field(default=None, kw_only=True)


ButtonBoxType: TypeAlias = Optional[Iterable[Union[Button, KnownButton]]]


class ButtonBox(UserList):
    OK = (KnownButton.OK,)
    OK_CANCEL = (KnownButton.OK, KnownButton.CANCEL)
    YES_NO = (KnownButton.YES, KnownButton.NO)

    def __init__(self,
                 initlist: ButtonBoxType = None,
                 *,
                 button_width: int = 200,
                 button_space: int = 100,
                 ) -> None:
        super().__init__(initlist)
        self.button_width = button_width
        self.button_space = button_space


class FLayout(str):  # później się tym zajmę (rysson)
    pass


class SimpleDialog(BaseDialog):
    """Base dialog with some extenstions like image."""

    XML = 'SimpleDialog.xml'

    BUTTON_BOX_ID = 18

    def __new__(cls,
                layout: Union[None, FLayout, str] = None,
                *args,
                modal: bool = True,
                **kwargs,
                ) -> 'SimpleDialog':
        fflog(f'SimpleDialog.__new__({cls=}, {layout=}, {args=}, {modal=}, {kwargs=})')
        obj = super().__new__(cls, None, None, None, None, *args, modal=modal, _call_init=False)
        return obj

    def __init__(self,
                 layout: Union[None, FLayout, str] = None,
                 *args,
                 heading: Optional[str] = None,
                 label: Union[None, str, Sequence[Optional[str]]] = None,
                 text: Optional[str] = None,
                 # code: Optional[str] = None,
                 buttons: ButtonBoxType = ButtonBox.OK,
                 image: Optional[str] = None,
                 image_size: Optional[int] = None,
                 **kwargs) -> None:
        super().__init__(self, *args, **kwargs)
        if buttons is None:
            buttons = ButtonBox.OK
        self.layout: FLayout
        # self.code: str = code or ''
        self._is_canceled: bool = False
        self._cancel_button_id: Optional[int] = None
        self.buttons: List[Button] = [btn if isinstance(btn, Button) else Button('', known=btn) for btn in buttons]
        self._button_space = getattr(buttons, 'button_space', 100)
        self.heading = heading
        if label is None:
            self.labels = []
        elif isinstance(label, str):
            self.labels = [label]
        else:
            self.labels = [lb for lb in label if lb is not None]
        self.text = text
        self.image = image
        self.image_size = image_size
        if layout is None:
            self.layout = FLayout()
        elif isinstance(layout, str):
            # self.layout = FLayout.from_str(layout)
            self.layout = self._create_layout(layout)
        else:
            self.layout = layout

        if self.heading:
            self.setProperty('heading.name', self.heading)

        for i, label in enumerate(self.labels, 1):
            self.setProperty(f'label.{i}.name', label)

        if self.text:
            self.setProperty('textbox.1.name', 'aaa')
            self.setProperty('textbox.1.text', self.text)

        LL = KodiLabels()
        button_width = getattr(buttons, 'button_width', 200)
        if i_btn := next(iter((i, btn)
                              for close_button in (KnownButton.CANCEL, KnownButton.CLOSE, KnownButton.NO)
                              for i, btn in enumerate(self.buttons, 1)
                              if btn.known is close_button and btn.value is None), None):
            i_btn[1].value = 0
            self._cancel_button_id = 30 + i_btn[0]
        for i, btn in enumerate(self.buttons, 1):
            btn.control_id = 30 + i
            if btn.known is not None and not btn.name:
                btn.name = LL(btn.known.value)
            if not btn.width:
                btn.width = button_width
            if btn.value is None:
                btn.value = i
            self.setProperty(f'button.{i}.name', btn.name)

        if self.image:
            # self.setProperty('image.1.name', 'Dupa')
            self.setProperty('image.1.url', self.image)

    def onInit(self) -> None:
        fflog('SimpleDialog.onInit()')
        # --- button-box ---
        W = self.getControl(self.BUTTON_BOX_ID).getWidth()
        bw = sum(btn.width for btn in self.buttons)
        sp = (W - bw) // max(1, len(self.buttons) - 1)
        sp = min(sp, self._button_space)
        x = (W - (len(self.buttons) - 1) * sp - bw) // 2
        for btn in self.buttons:
            control = self.getControl(btn.control_id)
            control.setWidth(btn.width)
            control.setPosition(x, 10)
            control.setVisibleCondition('true')
            x += btn.width + sp
        cbuttons = [self.getControl(btn.control_id) for btn in self.buttons]
        for i in range(len(cbuttons)):
            cbuttons[i].controlRight(cbuttons[(i + 1) % len(cbuttons)])
            cbuttons[(i + 1) % len(cbuttons)].controlLeft(cbuttons[i])
        # --- layout ---
        column = -1
        icolumn = 300
        if 'image|' in self.layout and self.image:
            column, icolumn = 550, 0
        elif '|image' in self.layout and self.image:
            column, icolumn = 0, 550
        if 'image' in self.layout and self.image:
            size = min(500, self.image_size or 500)
            off = (500 - size) // 2
            image = self.getControl(91)
            image.setWidth(size)
            image.setHeight(size)
            image.setPosition(icolumn + off, 50 + off)
            image.setVisibleCondition('true')
        if 'text' in self.layout:
            text = self.getControl(51)
            if column >= 0:
                text.setPosition(column, 50)
            text.setVisibleCondition('true')
        if 'label' in self.layout:
            for i, label in enumerate(self.labels, 1):
                if i <= 5:
                    label = self.getControl(40 + i)
                    if column >= 0:
                        label.setWidth(500)
                        label.setPosition(column, 50 + 114 * (i-1))
                    label.setVisibleCondition('true')
        # --- focus ---
        self.setFocusId(30 + len(self.buttons))  # button on the right

    def onClick(self, controlId: int) -> None:
        fflog(f'SimpleDialog.onClick({controlId!r})')
        if controlId == self._cancel_button_id:
            self._is_canceled = True
        if 30 < controlId < 40:
            index = controlId - 31
            if 0 <= index < len(self.buttons):
                self._result = self.buttons[index].value
            self.close()

    def dialog_is_canceled(self) -> bool:
        return self._is_canceled

    def _create_layout(self, layout: str) -> FLayout:
        return FLayout(layout)  # XXX return fake layput

    if TYPE_CHECKING:
        def doModal(self) -> Optional[int]: ...


class ImageDialog(SimpleDialog):

    def __init__(self,
                 heading: str,
                 image: Union[str, Path],
                 *,
                 label: Optional[str] = None,
                 text: Optional[str] = None,
                 size: Optional[int] = None,
                 buttons: ButtonBoxType = ButtonBox.OK,
                 layout: Optional[FLayout] = None,
                 ) -> None:
        if layout is None:
            if label is not None:
                layout = FLayout('image|label')
            elif text is not None:
                layout = FLayout('image|text')
            else:
                layout = FLayout('image')
        super().__init__(layout=layout, heading=heading, image=str(image), image_size=size,
                         label=label, text=text, buttons=buttons)


class QRCodeDialog(ImageDialog):

    def __init__(self,
                 heading: str,
                 qrcode: str,
                 *,
                 label: Optional[str] = None,
                 text: Optional[str] = None,
                 size: Optional[int] = None,
                 scale: Optional[int] = None,
                 buttons: ButtonBoxType = ButtonBox.OK,
                 layout: Optional[FLayout] = None,
                 ) -> None:
        from sys import version_info
        from tempfile import NamedTemporaryFile
        import segno
        from ..ff.control import dataPath as DATA_PATH

        if scale is None:
            scale = const.tune.misc.qrcode.size
        # if size is None:
        #     size = 400  # default for QR-Code
        image_dir = Path(DATA_PATH) / 'tmp'
        image_dir.parent.mkdir(parents=True, exist_ok=True)
        if TYPE_CHECKING or version_info < (3, 12):
            tmp_kwargs = {}
        else:
            tmp_kwargs = {'delete_on_close': False}
        with NamedTemporaryFile('w+b', prefix='qrcode-', suffix='.png', dir=image_dir, delete=False, **tmp_kwargs) as f:
            qrcode_image = segno.make(qrcode)
            qrcode_image.save(f, scale=scale)
            self.image_path = Path(f.name)
        super().__init__(layout=layout, heading=heading, image=self.image_path, size=size,
                         label=label, text=text, buttons=buttons)

    def on_close(self):
        super().on_close()
        try:
            self.image_path.unlink()
        except IOError:
            fflog_exc()
