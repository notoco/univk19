from typing import Union, List, Dict, Tuple, Optional, TYPE_CHECKING
from typing_extensions import Self
from dataclasses import dataclass
if TYPE_CHECKING:
    import xbmc

__fake_kodi__ = True

ACTION_ANALOG_FORWARD = 113
ACTION_ANALOG_MOVE = 49
ACTION_ANALOG_MOVE_X_LEFT = 601
ACTION_ANALOG_MOVE_X_RIGHT = 602
ACTION_ANALOG_MOVE_Y_DOWN = 604
ACTION_ANALOG_MOVE_Y_UP = 603
ACTION_ANALOG_REWIND = 114
ACTION_ANALOG_SEEK_BACK = 125
ACTION_ANALOG_SEEK_FORWARD = 124
ACTION_ASPECT_RATIO = 19
ACTION_AUDIO_DELAY = 161
ACTION_AUDIO_DELAY_MIN = 54
ACTION_AUDIO_DELAY_PLUS = 55
ACTION_AUDIO_NEXT_LANGUAGE = 56
ACTION_BACKSPACE = 110
ACTION_BIG_STEP_BACK = 23
ACTION_BIG_STEP_FORWARD = 22
ACTION_BROWSE_SUBTITLE = 247
ACTION_BUILT_IN_FUNCTION = 122
ACTION_CALIBRATE_RESET = 48
ACTION_CALIBRATE_SWAP_ARROWS = 47
ACTION_CHANGE_RESOLUTION = 57
ACTION_CHANNEL_DOWN = 185
ACTION_CHANNEL_NUMBER_SEP = 192
ACTION_CHANNEL_SWITCH = 183
ACTION_CHANNEL_UP = 184
ACTION_CHAPTER_OR_BIG_STEP_BACK = 98
ACTION_CHAPTER_OR_BIG_STEP_FORWARD = 97
ACTION_CONTEXT_MENU = 117
ACTION_COPY_ITEM = 81
ACTION_CREATE_BOOKMARK = 96
ACTION_CREATE_EPISODE_BOOKMARK = 95
ACTION_CURSOR_LEFT = 120
ACTION_CURSOR_RIGHT = 121
ACTION_CYCLE_SUBTITLE = 99
ACTION_CYCLE_TONEMAP_METHOD = 261
ACTION_DECREASE_PAR = 220
ACTION_DECREASE_RATING = 137
ACTION_DELETE_ITEM = 80
ACTION_ENTER = 135
ACTION_ERROR = 998
ACTION_FILTER = 233
ACTION_FILTER_CLEAR = 150
ACTION_FILTER_SMS2 = 151
ACTION_FILTER_SMS3 = 152
ACTION_FILTER_SMS4 = 153
ACTION_FILTER_SMS5 = 154
ACTION_FILTER_SMS6 = 155
ACTION_FILTER_SMS7 = 156
ACTION_FILTER_SMS8 = 157
ACTION_FILTER_SMS9 = 158
ACTION_FIRST_PAGE = 159
ACTION_FORWARD = 16
ACTION_GESTURE_ABORT = 505
ACTION_GESTURE_BEGIN = 501
ACTION_GESTURE_END = 599
ACTION_GESTURE_NOTIFY = 500
ACTION_GESTURE_PAN = 504
ACTION_GESTURE_ROTATE = 503
ACTION_GESTURE_SWIPE_DOWN = 541
ACTION_GESTURE_SWIPE_DOWN_TEN = 550
ACTION_GESTURE_SWIPE_LEFT = 511
ACTION_GESTURE_SWIPE_LEFT_TEN = 520
ACTION_GESTURE_SWIPE_RIGHT = 521
ACTION_GESTURE_SWIPE_RIGHT_TEN = 530
ACTION_GESTURE_SWIPE_UP = 531
ACTION_GESTURE_SWIPE_UP_TEN = 540
ACTION_GESTURE_ZOOM = 502
ACTION_GUIPROFILE_BEGIN = 204
ACTION_HDR_TOGGLE = 260
ACTION_HIGHLIGHT_ITEM = 8
ACTION_INCREASE_PAR = 219
ACTION_INCREASE_RATING = 136
ACTION_INPUT_TEXT = 244
ACTION_JUMP_SMS2 = 142
ACTION_JUMP_SMS3 = 143
ACTION_JUMP_SMS4 = 144
ACTION_JUMP_SMS5 = 145
ACTION_JUMP_SMS6 = 146
ACTION_JUMP_SMS7 = 147
ACTION_JUMP_SMS8 = 148
ACTION_JUMP_SMS9 = 149
ACTION_LAST_PAGE = 160
ACTION_MENU = 163
ACTION_MOUSE_DOUBLE_CLICK = 103
ACTION_MOUSE_DRAG = 106
ACTION_MOUSE_DRAG_END = 109
ACTION_MOUSE_END = 109
ACTION_MOUSE_LEFT_CLICK = 100
ACTION_MOUSE_LONG_CLICK = 108
ACTION_MOUSE_MIDDLE_CLICK = 102
ACTION_MOUSE_MOVE = 107
ACTION_MOUSE_RIGHT_CLICK = 101
ACTION_MOUSE_START = 100
ACTION_MOUSE_WHEEL_DOWN = 105
ACTION_MOUSE_WHEEL_UP = 104
ACTION_MOVE_DOWN = 4
ACTION_MOVE_ITEM = 82
ACTION_MOVE_ITEM_DOWN = 116
ACTION_MOVE_ITEM_UP = 115
ACTION_MOVE_LEFT = 1
ACTION_MOVE_RIGHT = 2
ACTION_MOVE_UP = 3
ACTION_MUTE = 91
ACTION_NAV_BACK = 92
ACTION_NEXT_CHANNELGROUP = 186
ACTION_NEXT_CONTROL = 181
ACTION_NEXT_ITEM = 14
ACTION_NEXT_LETTER = 140
ACTION_NEXT_PICTURE = 28
ACTION_NEXT_SCENE = 138
ACTION_NEXT_SUBTITLE = 26
ACTION_NONE = 0
ACTION_NOOP = 999
ACTION_PAGE_DOWN = 6
ACTION_PAGE_UP = 5
ACTION_PARENT_DIR = 9
ACTION_PASTE = 180
ACTION_PAUSE = 12
ACTION_PLAYER_DEBUG = 27
ACTION_PLAYER_DEBUG_VIDEO = 262
ACTION_PLAYER_FORWARD = 77
ACTION_PLAYER_PLAY = 79
ACTION_PLAYER_PLAYPAUSE = 229
ACTION_PLAYER_PROCESS_INFO = 69
ACTION_PLAYER_PROGRAM_SELECT = 70
ACTION_PLAYER_RESET = 248
ACTION_PLAYER_RESOLUTION_SELECT = 71
ACTION_PLAYER_REWIND = 78
ACTION_PREVIOUS_CHANNELGROUP = 187
ACTION_PREVIOUS_MENU = 10
ACTION_PREV_CONTROL = 182
ACTION_PREV_ITEM = 15
ACTION_PREV_LETTER = 141
ACTION_PREV_PICTURE = 29
ACTION_PREV_SCENE = 139
ACTION_PVR_ANNOUNCE_REMINDERS = 193
ACTION_PVR_PLAY = 188
ACTION_PVR_PLAY_RADIO = 190
ACTION_PVR_PLAY_TV = 189
ACTION_PVR_SHOW_TIMER_RULE = 191
ACTION_QUEUE_ITEM = 34
ACTION_QUEUE_ITEM_NEXT = 251
ACTION_RECORD = 170
ACTION_RELOAD_KEYMAPS = 203
ACTION_REMOVE_ITEM = 35
ACTION_RENAME_ITEM = 87
ACTION_REWIND = 17
ACTION_ROTATE_PICTURE_CCW = 51
ACTION_ROTATE_PICTURE_CW = 50
ACTION_SCAN_ITEM = 201
ACTION_SCROLL_DOWN = 112
ACTION_SCROLL_UP = 111
ACTION_SELECT_ITEM = 7
ACTION_SETTINGS_LEVEL_CHANGE = 242
ACTION_SETTINGS_RESET = 241
ACTION_SET_RATING = 164
ACTION_SHIFT = 118
ACTION_SHOW_FULLSCREEN = 36
ACTION_SHOW_GUI = 18
ACTION_SHOW_INFO = 11
ACTION_SHOW_OSD = 24
ACTION_SHOW_OSD_TIME = 123
ACTION_SHOW_PLAYLIST = 33
ACTION_SHOW_SUBTITLES = 25
ACTION_SHOW_VIDEOMENU = 134
ACTION_SMALL_STEP_BACK = 76
ACTION_STEP_BACK = 21
ACTION_STEP_FORWARD = 20
ACTION_STEREOMODE_NEXT = 235
ACTION_STEREOMODE_PREVIOUS = 236
ACTION_STEREOMODE_SELECT = 238
ACTION_STEREOMODE_SET = 240
ACTION_STEREOMODE_TOGGLE = 237
ACTION_STEREOMODE_TOMONO = 239
ACTION_STOP = 13
ACTION_SUBTITLE_ALIGN = 232
ACTION_SUBTITLE_DELAY = 162
ACTION_SUBTITLE_DELAY_MIN = 52
ACTION_SUBTITLE_DELAY_PLUS = 53
ACTION_SUBTITLE_VSHIFT_DOWN = 231
ACTION_SUBTITLE_VSHIFT_UP = 230
ACTION_SWITCH_PLAYER = 234
ACTION_SYMBOLS = 119
ACTION_TAKE_SCREENSHOT = 85
ACTION_TELETEXT_BLUE = 218
ACTION_TELETEXT_GREEN = 216
ACTION_TELETEXT_RED = 215
ACTION_TELETEXT_YELLOW = 217
ACTION_TOGGLE_COMMSKIP = 246
ACTION_TOGGLE_DIGITAL_ANALOG = 202
ACTION_TOGGLE_FONT = 249
ACTION_TOGGLE_FULLSCREEN = 199
ACTION_TOGGLE_SOURCE_DEST = 32
ACTION_TOGGLE_WATCHED = 200
ACTION_TOUCH_LONGPRESS = 411
ACTION_TOUCH_LONGPRESS_TEN = 420
ACTION_TOUCH_TAP = 401
ACTION_TOUCH_TAP_TEN = 410
ACTION_TRIGGER_OSD = 243
ACTION_VIDEO_NEXT_STREAM = 250
ACTION_VIS_PRESET_LOCK = 130
ACTION_VIS_PRESET_NEXT = 128
ACTION_VIS_PRESET_PREV = 129
ACTION_VIS_PRESET_RANDOM = 131
ACTION_VIS_PRESET_SHOW = 126
ACTION_VIS_RATE_PRESET_MINUS = 133
ACTION_VIS_RATE_PRESET_PLUS = 132
ACTION_VOICE_RECOGNIZE = 300
ACTION_VOLAMP = 90
ACTION_VOLAMP_DOWN = 94
ACTION_VOLAMP_UP = 93
ACTION_VOLUME_DOWN = 89
ACTION_VOLUME_SET = 245
ACTION_VOLUME_UP = 88
ACTION_VSHIFT_DOWN = 228
ACTION_VSHIFT_UP = 227
ACTION_ZOOM_IN = 31
ACTION_ZOOM_LEVEL_1 = 38
ACTION_ZOOM_LEVEL_2 = 39
ACTION_ZOOM_LEVEL_3 = 40
ACTION_ZOOM_LEVEL_4 = 41
ACTION_ZOOM_LEVEL_5 = 42
ACTION_ZOOM_LEVEL_6 = 43
ACTION_ZOOM_LEVEL_7 = 44
ACTION_ZOOM_LEVEL_8 = 45
ACTION_ZOOM_LEVEL_9 = 46
ACTION_ZOOM_LEVEL_NORMAL = 37
ACTION_ZOOM_OUT = 30
ALPHANUM_HIDE_INPUT = 2
CONTROL_TEXT_OFFSET_X = 10
CONTROL_TEXT_OFFSET_Y = 2
DLG_YESNO_CUSTOM_BTN = 12
DLG_YESNO_NO_BTN = 10
DLG_YESNO_YES_BTN = 11
HORIZONTAL = 0
ICON_OVERLAY_HD = 6
ICON_OVERLAY_LOCKED = 3
ICON_OVERLAY_NONE = 0
ICON_OVERLAY_RAR = 1
ICON_OVERLAY_UNWATCHED = 4
ICON_OVERLAY_WATCHED = 5
ICON_OVERLAY_ZIP = 2
ICON_TYPE_FILES = 106
ICON_TYPE_MUSIC = 103
ICON_TYPE_NONE = 101
ICON_TYPE_PICTURES = 104
ICON_TYPE_PROGRAMS = 102
ICON_TYPE_SETTINGS = 109
ICON_TYPE_VIDEOS = 105
ICON_TYPE_WEATHER = 107
INPUT_ALPHANUM = 0
INPUT_DATE = 2
INPUT_IPADDRESS = 4
INPUT_NUMERIC = 1
INPUT_PASSWORD = 5
INPUT_TIME = 3
INPUT_TYPE_DATE = 4
INPUT_TYPE_IPADDRESS = 5
INPUT_TYPE_NUMBER = 1
INPUT_TYPE_PASSWORD = 6
INPUT_TYPE_PASSWORD_MD5 = 7
INPUT_TYPE_PASSWORD_NUMBER_VERIFY_NEW = 10
INPUT_TYPE_SECONDS = 2
INPUT_TYPE_TEXT = 0
INPUT_TYPE_TIME = 3
KEY_APPCOMMAND = 53248
KEY_BUTTON_A = 256
KEY_BUTTON_B = 257
KEY_BUTTON_BACK = 275
KEY_BUTTON_BLACK = 260
KEY_BUTTON_DPAD_DOWN = 271
KEY_BUTTON_DPAD_LEFT = 272
KEY_BUTTON_DPAD_RIGHT = 273
KEY_BUTTON_DPAD_UP = 270
KEY_BUTTON_LEFT_ANALOG_TRIGGER = 278
KEY_BUTTON_LEFT_THUMB_BUTTON = 276
KEY_BUTTON_LEFT_THUMB_STICK = 264
KEY_BUTTON_LEFT_THUMB_STICK_DOWN = 281
KEY_BUTTON_LEFT_THUMB_STICK_LEFT = 282
KEY_BUTTON_LEFT_THUMB_STICK_RIGHT = 283
KEY_BUTTON_LEFT_THUMB_STICK_UP = 280
KEY_BUTTON_LEFT_TRIGGER = 262
KEY_BUTTON_RIGHT_ANALOG_TRIGGER = 279
KEY_BUTTON_RIGHT_THUMB_BUTTON = 277
KEY_BUTTON_RIGHT_THUMB_STICK = 265
KEY_BUTTON_RIGHT_THUMB_STICK_DOWN = 267
KEY_BUTTON_RIGHT_THUMB_STICK_LEFT = 268
KEY_BUTTON_RIGHT_THUMB_STICK_RIGHT = 269
KEY_BUTTON_RIGHT_THUMB_STICK_UP = 266
KEY_BUTTON_RIGHT_TRIGGER = 263
KEY_BUTTON_START = 274
KEY_BUTTON_WHITE = 261
KEY_BUTTON_X = 258
KEY_BUTTON_Y = 259
KEY_INVALID = 65535
KEY_MOUSE_CLICK = 57344
KEY_MOUSE_DOUBLE_CLICK = 57360
KEY_MOUSE_DRAG = 57604
KEY_MOUSE_DRAG_END = 57606
KEY_MOUSE_DRAG_START = 57605
KEY_MOUSE_END = 61439
KEY_MOUSE_LONG_CLICK = 57376
KEY_MOUSE_MIDDLECLICK = 57346
KEY_MOUSE_MOVE = 57603
KEY_MOUSE_NOOP = 61439
KEY_MOUSE_RDRAG = 57607
KEY_MOUSE_RDRAG_END = 57609
KEY_MOUSE_RDRAG_START = 57608
KEY_MOUSE_RIGHTCLICK = 57345
KEY_MOUSE_START = 57344
KEY_MOUSE_WHEEL_DOWN = 57602
KEY_MOUSE_WHEEL_UP = 57601
KEY_UNICODE = 61952
KEY_VKEY = 61440
KEY_VMOUSE = 61439
NOTIFICATION_ERROR = 'error'
NOTIFICATION_INFO = 'info'
NOTIFICATION_WARNING = 'warning'
PASSWORD_VERIFY = 1
REMOTE_0 = 58
REMOTE_1 = 59
REMOTE_2 = 60
REMOTE_3 = 61
REMOTE_4 = 62
REMOTE_5 = 63
REMOTE_6 = 64
REMOTE_7 = 65
REMOTE_8 = 66
REMOTE_9 = 67
VERTICAL = 1


class Control:

    def __init__(self) -> None:
        pass

    def getId(self) -> int:
        return 0

    def getX(self) -> int:
        return 0

    def getY(self) -> int:
        return 0

    def getHeight(self) -> int:
        return 0

    def getWidth(self) -> int:
        return 0

    def setEnabled(self, enabled: bool) -> None:
        pass

    def setVisible(self, visible: bool) -> None:
        pass

    def isVisible(self) -> bool:
        return True

    def setVisibleCondition(self, visible: str,
                            allowHiddenFocus: bool = False) -> None:
        pass

    def setEnableCondition(self, enable: str) -> None:
        pass

    def setAnimations(self, eventAttr: List[Tuple[str, str]]) -> None:
        pass

    def setPosition(self, x: int, y: int) -> None:
        pass

    def setWidth(self, width: int) -> None:
        pass

    def setHeight(self, height: int) -> None:
        pass

    def setNavigation(self, up: 'Control',
                      down: 'Control',
                      left: 'Control',
                      right: 'Control') -> None:
        pass

    def controlUp(self, up: 'Control') -> None:
        pass

    def controlDown(self, control: 'Control') -> None:
        pass

    def controlLeft(self, control: 'Control') -> None:
        pass

    def controlRight(self, control: 'Control') -> None:
        pass


class ControlSpin(Control):

    def __init__(self) -> None:
        pass

    def setTextures(self, up: str,
                    down: str,
                    upFocus: str,
                    downFocus: str,
                    upDisabled: str,
                    downDisabled: str) -> None:
        pass


class ControlLabel(Control):

    def __init__(self, x: int,
                 y: int,
                 width: int,
                 height: int,
                 label: str,
                 font: Optional[str] = None,
                 textColor: Optional[str] = None,
                 disabledColor: Optional[str] = None,
                 alignment: int = 0,
                 hasPath: bool = False,
                 angle: int = 0) -> None:
        pass

    def getLabel(self) -> str:
        return ""

    def setLabel(self, label: str = "",
                 font: Optional[str] = None,
                 textColor: Optional[str] = None,
                 disabledColor: Optional[str] = None,
                 shadowColor: Optional[str] = None,
                 focusedColor: Optional[str] = None,
                 label2: str = "") -> None:
        pass


class ControlEdit(Control):

    def __init__(self, x: int,
                 y: int,
                 width: int,
                 height: int,
                 label: str,
                 font: Optional[str] = None,
                 textColor: Optional[str] = None,
                 disabledColor: Optional[str] = None,
                 _alignment: int = 0,
                 focusTexture: Optional[str] = None,
                 noFocusTexture: Optional[str] = None) -> None:
        pass

    def setLabel(self, label: str = "",
                 font: Optional[str] = None,
                 textColor: Optional[str] = None,
                 disabledColor: Optional[str] = None,
                 shadowColor: Optional[str] = None,
                 focusedColor: Optional[str] = None,
                 label2: str = "") -> None:
        pass

    def getLabel(self) -> str:
        return ""

    def setText(self, text: str) -> None:
        pass

    def getText(self) -> str:
        return ""

    def setType(self, type: int, heading: str) -> None:
        pass


class ControlList(Control):

    def __init__(self, x: int,
                 y: int,
                 width: int,
                 height: int,
                 font: Optional[str] = None,
                 textColor: Optional[str] = None,
                 buttonTexture: Optional[str] = None,
                 buttonFocusTexture: Optional[str] = None,
                 selectedColor: Optional[str] = None,
                 _imageWidth: int = 10,
                 _imageHeight: int = 10,
                 _itemTextXOffset: int = 10,
                 _itemTextYOffset: int = 2,
                 _itemHeight: int = 27,
                 _space: int = 2,
                 _alignmentY: int = 4) -> None:
        pass

    def addItem(self, item: Union[str,  'ListItem'],
                sendMessage: bool = True) -> None:
        pass

    def addItems(self, items: List[Union[str,  'ListItem']]) -> None:
        pass

    def selectItem(self, item: int) -> None:
        pass

    def removeItem(self, index: int) -> None:
        pass

    def reset(self) -> None:
        pass

    def getSpinControl(self) -> Control:
        return Control()

    def getSelectedPosition(self) -> int:
        return 0

    def getSelectedItem(self) -> 'ListItem':
        return ListItem()

    def setImageDimensions(self, imageWidth: int, imageHeight: int) -> None:
        pass

    def setSpace(self, space: int) -> None:
        pass

    def setPageControlVisible(self, visible: bool) -> None:
        pass

    def size(self) -> int:
        return 0

    def getItemHeight(self) -> int:
        return 0

    def getSpace(self) -> int:
        return 0

    def getListItem(self, index: int) -> 'ListItem':
        return ListItem()

    def setStaticContent(self, items: List['ListItem']) -> None:
        pass


class ControlFadeLabel(Control):

    def __init__(self, x: int,
                 y: int,
                 width: int,
                 height: int,
                 font: Optional[str] = None,
                 textColor: Optional[str] = None,
                 _alignment: int = 0) -> None:
        pass

    def addLabel(self, label: str) -> None:
        pass

    def setScrolling(self, scroll: bool) -> None:
        pass


class ControlTextBox(Control):

    def __init__(self, x: int,
                 y: int,
                 width: int,
                 height: int,
                 font: Optional[str] = None,
                 textColor: Optional[str] = None) -> None:
        pass

    def setText(self, text: str) -> None:
        pass

    def getText(self) -> str:
        return ""

    def reset(self) -> None:
        pass

    def scroll(self, id: int) -> None:
        pass

    def autoScroll(self, delay: int, time: int, repeat: int) -> None:
        pass


class ControlImage(Control):

    def __init__(self, x: int,
                 y: int,
                 width: int,
                 height: int,
                 filename: str,
                 aspectRatio: int = 0,
                 colorDiffuse: Optional[str] = None) -> None:
        pass

    def setImage(self, imageFilename: str, useCache: bool = True) -> None:
        pass

    def setColorDiffuse(self, hexString: str) -> None:
        pass


class ControlProgress(Control):

    def __init__(self, x: int,
                 y: int,
                 width: int,
                 height: int,
                 texturebg: Optional[str] = None,
                 textureleft: Optional[str] = None,
                 texturemid: Optional[str] = None,
                 textureright: Optional[str] = None,
                 textureoverlay: Optional[str] = None) -> None:
        pass

    def setPercent(self, pct: float) -> None:
        pass

    def getPercent(self) -> float:
        return 0.0


class ControlButton(Control):

    def __init__(self, x: int,
                 y: int,
                 width: int,
                 height: int,
                 label: str,
                 focusTexture: Optional[str] = None,
                 noFocusTexture: Optional[str] = None,
                 textOffsetX: int = 10,
                 textOffsetY: int = 2,
                 alignment: int = (0|4),
                 font: Optional[str] = None,
                 textColor: Optional[str] = None,
                 disabledColor: Optional[str] = None,
                 angle: int = 0,
                 shadowColor: Optional[str] = None,
                 focusedColor: Optional[str] = None) -> None:
        pass

    def setLabel(self, label: str = "",
                 font: Optional[str] = None,
                 textColor: Optional[str] = None,
                 disabledColor: Optional[str] = None,
                 shadowColor: Optional[str] = None,
                 focusedColor: Optional[str] = None,
                 label2: str = "") -> None:
        pass

    def setDisabledColor(self, color: str) -> None:
        pass

    def getLabel(self) -> str:
        return ""

    def getLabel2(self) -> str:
        return ""


class ControlGroup(Control):

    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        pass


class ControlRadioButton(Control):

    def __init__(self, x: int,
                 y: int,
                 width: int,
                 height: int,
                 label: str,
                 focusOnTexture: Optional[str] = None,
                 noFocusOnTexture: Optional[str] = None,
                 focusOffTexture: Optional[str] = None,
                 noFocusOffTexture: Optional[str] = None,
                 focusTexture: Optional[str] = None,
                 noFocusTexture: Optional[str] = None,
                 textOffsetX: int = 10,
                 textOffsetY: int = 2,
                 _alignment: int = (0|4),
                 font: Optional[str] = None,
                 textColor: Optional[str] = None,
                 disabledColor: Optional[str] = None,
                 angle: int = 0,
                 shadowColor: Optional[str] = None,
                 focusedColor: Optional[str] = None,
                 disabledOnTexture: Optional[str] = None,
                 disabledOffTexture: Optional[str] = None) -> None:
        pass

    def setSelected(self, selected: bool) -> None:
        pass

    def isSelected(self) -> bool:
        return True

    def setLabel(self, label: str = "",
                 font: Optional[str] = None,
                 textColor: Optional[str] = None,
                 disabledColor: Optional[str] = None,
                 shadowColor: Optional[str] = None,
                 focusedColor: Optional[str] = None,
                 label2: str = "") -> None:
        pass

    def setRadioDimension(self, x: int,
                          y: int,
                          width: int,
                          height: int) -> None:
        pass


class ControlSlider(Control):

    def __init__(self, x: int,
                 y: int,
                 width: int,
                 height: int,
                 textureback: Optional[str] = None,
                 texture: Optional[str] = None,
                 texturefocus: Optional[str] = None,
                 orientation: int = 1) -> None:
        pass

    def getPercent(self) -> float:
        return 0.0

    def setPercent(self, pct: float) -> None:
        pass

    def getInt(self) -> int:
        return 0

    def setInt(self, value: int, min: int, delta: int, max: int) -> None:
        pass

    def getFloat(self) -> float:
        return 0.0

    def setFloat(self, value: float,
                 min: float,
                 delta: float,
                 max: float) -> None:
        pass


def _is_yes(val: str) -> bool:
    """Check if a string is a positive answer."""
    return val.lower() in ('y', 'yes', '1', 'true', 'ok', 'ja', 'j', 'yea', 'yeah', 't', 'tak')


class Dialog:

    def __init__(self) -> None:
        pass

    def yesno(self, heading: str,
              message: str,
              nolabel: str = "",
              yeslabel: str = "",
              autoclose: int = 0,
              defaultbutton: int = DLG_YESNO_NO_BTN) -> bool:
        print(f'== {heading} ==\n{message}\n{yeslabel or "YES"} (Y) / {nolabel or "NO"} (N)')
        default = 'y' if defaultbutton == DLG_YESNO_YES_BTN else 'n'
        val = input(f'Y/N [{default}]: ').strip().lower() or default
        return _is_yes(val)

    def yesnocustom(self, heading: str,
                    message: str,
                    customlabel: str,
                    nolabel: str = "",
                    yeslabel: str = "",
                    autoclose: int = 0,
                    defaultbutton: int = DLG_YESNO_NO_BTN) -> int:
        default = 'x' if defaultbutton == DLG_YESNO_CUSTOM_BTN else 'y' if defaultbutton == DLG_YESNO_YES_BTN else 'n'
        print(f'== {heading} ==\n{message}\n{yeslabel or "YES"} (Y) / {nolabel or "NO"} (N) / {customlabel} (X)')
        val = input(f'Y/N/X [{default}]: ').strip().lower() or default
        # -1: cancelled
        return 2 if val == 'x' else int(_is_yes(val))

    def info(self, item: 'ListItem') -> bool:
        print(item)
        return True

    def select(self, heading: str,
               list: List[Union[str,  'ListItem']],
               autoclose: int = 0,
               preselect: int = -1,
               useDetails: bool = False) -> int:
        return 0

    def contextmenu(self, list: List[str]) -> int:
        return 0

    def multiselect(self, heading: str,
                    options: List[Union[str,  'ListItem']],
                    autoclose: int = 0,
                    preselect: Optional[List[int]] = None,
                    useDetails: bool = False) -> List[int]:
        return [0]

    def ok(self, heading: str, message: str) -> bool:
        return True

    def textviewer(self, heading: str,
                   text: str,
                   usemono: bool = False) -> None:
        pass

    def browse(self, type: int,
               heading: str,
               shares: str,
               mask: str = "",
               useThumbs: bool = False,
               treatAsFolder: bool = False,
               defaultt: str = "",
               enableMultiple: bool = False) -> Union[str,  List[str]]:
        return ""

    def browseSingle(self, type: int,
                     heading: str,
                     shares: str,
                     mask: str = "",
                     useThumbs: bool = False,
                     treatAsFolder: bool = False,
                     defaultt: str = "") -> str:
        return ""

    def browseMultiple(self, type: int,
                       heading: str,
                       shares: str,
                       mask: str = "",
                       useThumbs: bool = False,
                       treatAsFolder: bool = False,
                       defaultt: str = "") -> List[str]:
        return [""]

    def numeric(self, type: int,
                heading: str,
                defaultt: str = "",
                bHiddenInput: bool = False) -> str:
        print(f'{heading} [{defaultt}]:NUM: ', end='')
        return ''.join(c for c in input() or defaultt if c.isdecimal())

    def notification(self, heading: str,
                     message: str,
                     icon: str = "",
                     time: int = 0,
                     sound: bool = True) -> None:
        print(f'Notification: {heading}: {message}')

    def input(self, heading: str,
              defaultt: str = "",
              type: int = INPUT_ALPHANUM,
              option: int = 0,
              autoclose: int = 0) -> str:
        print(f'{heading} [{defaultt}]: ', end='')
        return input() or defaultt

    def colorpicker(self, heading: str,
                    selectedcolor: str = "",
                    colorfile: str = "",
                    colorlist: List['ListItem'] = ()) -> str:
        return ""


@dataclass
class _DialogProgress:
    _heading: str = ''
    _message: str = ''
    _percent: int = 0
    _closed: bool = False

    def __init__(self) -> None:
        self._heading = ''
        self._message = ''
        self._percent = 0
        self._closed = False

    def _update(self, percent: int) -> None:
        from lib.fake.fake_term import formatting, ef, rs
        self._percent = percent
        msg = formatting(self._message).replace('\n', f'{ef.dim}[CR]{rs.dim_bold}')
        print(f'\r\033[A\033[2KDialogProgress[{self._heading}]: {self._percent:3d}% – {msg}   ')

    def create(self, heading: str, message: str = "") -> None:
        self._heading = heading
        self._message = message
        print()

    def close(self) -> None:
        self._closed = True


class DialogProgress(_DialogProgress):

    def __init__(self) -> None:
        super().__init__()

    def update(self, percent: int, message: str = "") -> None:
        if message:
            self._message = message
        self._update(percent)

    def iscanceled(self) -> bool:
        return self._closed


class DialogProgressBG(_DialogProgress):

    def __init__(self) -> None:
        super().__init__()

    def deallocating(self) -> None:
        pass

    def update(self, percent: int = 0,
               heading: str = "",
               message: str = "") -> None:
        if heading:
            self._heading = heading
        if message:
            self._message = message
        self._update(percent)

    def isFinished(self) -> bool:
        return self._closed


class ListItem:

    def __new__(cls,
                label: Optional[str] = None,
                label2: Optional[str] = None,
                path: Optional[str] = None,
                offscreen: bool = True,
                ) -> 'ListItem':
        obj = object.__new__(cls)
        obj.__init__(label, label2, path, offscreen)
        return obj

    def __init__(self, label: str = "",
                 label2: str = "",
                 path: str = "",
                 offscreen: bool = False) -> None:
        self.__label: str = label
        self.__label2: str = label2
        self.__path: str = path
        self.__offscreen: bool = offscreen
        self.__folder: bool = True
        self.__art: Dict[str, str] = {}
        self.__info: Dict[str, str] = {}
        self.__prop: Dict[str, str] = {}
        self.__menu: List[Tuple[str, str]] = []
        self.__date: str = ""
        self.__seasons: List[Tuple[int, str]] = []
        self.__selected: bool = False

    def getLabel(self) -> str:
        return self.__label or ""

    def getLabel2(self) -> str:
        return self.__label2 or ""

    def setLabel(self, label: str) -> None:
        self.__label = label

    def setLabel2(self, label: str) -> None:
        self.__label2 = label

    def getDateTime(self) -> str:
        return self.__date or ""

    def setDateTime(self, dateTime: str) -> None:
        self.__date = dateTime or ""

    def setArt(self, dictionary: Dict[str, str]) -> None:
        self.__art = dict(dictionary)

    def setIsFolder(self, isFolder: bool) -> None:
        self.__folder = bool(isFolder)

    def setUniqueIDs(self, dictionary: Dict[str, str], defaultrating: str = "") -> None:
        self.getVideoInfoTag().setUniqueIDs(dictionary, defaultrating)

    def setRating(self, type: str,
                  rating: float,
                  votes: int = 0,
                  defaultt: bool = False) -> None:
        pass

    def addSeason(self, number: int, name: str = "") -> None:
        self.__seasons.append((number, name))

    def getArt(self, key: str) -> str:
        return self.__art.get(key, "")

    def isFolder(self) -> bool:
        return self.__folder

    def getUniqueID(self, key: str) -> str:
        return self.getVideoInfoTag().getUniqueID(key)

    def getRating(self, key: str) -> float:
        vtag = self.getVideoInfoTag()
        return vtag._ratings.get(vtag._rating_default, vtag.Rating()).rating

    def getVotes(self, key: str) -> int:
        vtag = self.getVideoInfoTag()
        return vtag._ratings.get(vtag._rating_default, vtag.Rating()).votes

    def select(self, selected: bool) -> None:
        self.__selected = selected

    def isSelected(self) -> bool:
        return self.__selected

    def setInfo(self, type: str, infoLabels: Dict[str, str]) -> None:
        self.__type = type
        self.__info = dict(infoLabels)

    def setCast(self, actors: List[Dict[str, str]]) -> None:
        from xbmc import Actor
        self.getVideoInfoTag().setCast([Actor(**actor) for actor in actors])

    def setAvailableFanart(self, images: List[Dict[str, str]]) -> None:
        pass

    def addAvailableArtwork(self, url: str,
                            art_type: str = "",
                            preview: str = "",
                            referrer: str = "",
                            cache: str = "",
                            post: bool = False,
                            isgz: bool = False,
                            season: int = -1) -> None:
        pass

    def addStreamInfo(self, cType: str, dictionary: Dict[str, str]) -> None:
        pass

    def addContextMenuItems(self, items: List[Tuple[str, str]]) -> None:
        self.__menu.extend(items)

    def setProperty(self, key: str, value: str) -> None:
        self.__prop[key.lower()] = value

    def setProperties(self, dictionary: Dict[str, str]) -> None:
        self.__prop = {k.lower(): v for k, v in dictionary.items()}

    def getProperty(self, key: str) -> str:
        return self.__prop.get(key.lower(), "")

    def setPath(self, path: str) -> None:
        self.__path = path

    def setMimeType(self, mimetype: str) -> None:
        pass

    def setContentLookup(self, enable: bool) -> None:
        pass

    def setSubtitles(self, subtitleFiles: List[str]) -> None:
        pass

    def getPath(self) -> str:
        return self.__path or ""

    def getVideoInfoTag(self) -> 'xbmc.InfoTagVideo':
        from xbmc import InfoTagVideo
        return InfoTagVideo()

    def getMusicInfoTag(self) -> 'xbmc.InfoTagMusic':
        from xbmc import InfoTagMusic
        return InfoTagMusic()

    def getPictureInfoTag(self) -> 'xbmc.InfoTagPicture':
        from xbmc import InfoTagPicture
        return InfoTagPicture()

    def getGameInfoTag(self) -> 'xbmc.InfoTagGame':
        from xbmc import InfoTagGame
        return InfoTagGame()

    def _get_context_menu(self) -> List[Tuple[str, str]]:
        return list(self.__menu)


class Action:

    def __init__(self) -> None:
        pass

    def getId(self) -> int:
        return 0

    def getButtonCode(self) -> int:
        return 0

    def getAmount1(self) -> float:
        return 0.0

    def getAmount2(self) -> float:
        return 0.0


class Window:

    def __init__(self, existingWindowId: int = -1) -> None:
        pass

    def show(self) -> None:
        pass

    def setFocus(self, pControl: Control) -> None:
        pass

    def setFocusId(self, iControlId: int) -> None:
        pass

    def getFocus(self) -> Control:
        return Control()

    def getFocusId(self) -> int:
        return 0

    def removeControl(self, pControl: Control) -> None:
        pass

    def removeControls(self, pControls: List[Control]) -> None:
        pass

    def getHeight(self) -> int:
        return 0

    def getWidth(self) -> int:
        return 0

    def setProperty(self, key: str, value: str) -> None:
        pass

    def getProperty(self, key: str) -> str:
        return ""

    def clearProperty(self, key: str) -> None:
        pass

    def clearProperties(self) -> None:
        pass

    def close(self) -> None:
        pass

    def doModal(self) -> None:
        pass

    def addControl(self, pControl: Control) -> None:
        pass

    def addControls(self, pControls: List[Control]) -> None:
        pass

    def getControl(self, iControlId: int) -> Control:
        return Control()

    def onAction(self, action: Action) -> None:
        pass

    def onControl(self, control: Control) -> None:
        pass

    def onClick(self, controlId: int) -> None:
        pass

    def onDoubleClick(self, controlId: int) -> None:
        pass

    def onFocus(self, controlId: int) -> None:
        pass

    def onInit(self) -> None:
        pass


class WindowDialog(Window):

    def __init__(self) -> None:
        pass


class WindowXML(Window):

    def __new__(cls,
                xmlFilename: str,
                scriptPath: str,
                defaultSkin: str = "Default",
                defaultRes: str = "720p",
                isMedia: bool = False) -> Self:
        obj = object.__new__(cls)
        return obj

    def __init__(self, xmlFilename: str,
                 scriptPath: str,
                 defaultSkin: str = "Default",
                 defaultRes: str = "720p",
                 isMedia: bool = False) -> None:
        pass

    def addItem(self, item: Union[str,  ListItem],
                position: int = 2147483647) -> None:
        pass

    def addItems(self, items: List[Union[str,  ListItem]]) -> None:
        pass

    def removeItem(self, position: int) -> None:
        pass

    def getCurrentListPosition(self) -> int:
        return 0

    def setCurrentListPosition(self, position: int) -> None:
        pass

    def getListItem(self, position: int) -> ListItem:
        return ListItem()

    def getListSize(self) -> int:
        return 0

    def clearList(self) -> None:
        pass

    def setContainerProperty(self, strProperty: str, strValue: str) -> None:
        pass

    def setContent(self, strValue: str) -> None:
        pass

    def getCurrentContainerId(self) -> int:
        return 0


class WindowXMLDialog(WindowXML):

    def __init__(self, xmlFilename: str,
                 scriptPath: str,
                 defaultSkin: str = "Default",
                 defaultRes: str = "720p") -> None:
        pass


def getCurrentWindowId() -> int:
    return 0


def getCurrentWindowDialogId() -> int:
    return 0


def getScreenHeight() -> int:
    return 0


def getScreenWidth() -> int:
    return 0
