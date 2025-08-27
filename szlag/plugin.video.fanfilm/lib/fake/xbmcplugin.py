from typing import List, Tuple, Optional, Callable, NamedTuple, TYPE_CHECKING
from attrs import define, field
from lib.fake.fake_term import print_item_list
if TYPE_CHECKING:
    import xbmcgui

SORT_METHOD_ALBUM = 14
SORT_METHOD_ALBUM_IGNORE_THE = 15
SORT_METHOD_ARTIST = 11
SORT_METHOD_ARTIST_IGNORE_THE = 13
SORT_METHOD_BITRATE = 43
SORT_METHOD_CHANNEL = 41
SORT_METHOD_COUNTRY = 17
SORT_METHOD_DATE = 3
SORT_METHOD_DATEADDED = 21
SORT_METHOD_DATE_TAKEN = 44
SORT_METHOD_DRIVE_TYPE = 6
SORT_METHOD_DURATION = 8
SORT_METHOD_EPISODE = 24
SORT_METHOD_FILE = 5
SORT_METHOD_FULLPATH = 35
SORT_METHOD_GENRE = 16
SORT_METHOD_LABEL = 1
SORT_METHOD_LABEL_IGNORE_FOLDERS = 36
SORT_METHOD_LABEL_IGNORE_THE = 2
SORT_METHOD_LASTPLAYED = 37
SORT_METHOD_LISTENERS = 39
SORT_METHOD_MPAA_RATING = 31
SORT_METHOD_NONE = 0
SORT_METHOD_PLAYCOUNT = 38
SORT_METHOD_PLAYLIST_ORDER = 23
SORT_METHOD_PRODUCTIONCODE = 28
SORT_METHOD_PROGRAM_COUNT = 22
SORT_METHOD_SIZE = 4
SORT_METHOD_SONG_RATING = 29
SORT_METHOD_SONG_USER_RATING = 30
SORT_METHOD_STUDIO = 33
SORT_METHOD_STUDIO_IGNORE_THE = 34
SORT_METHOD_TITLE = 9
SORT_METHOD_TITLE_IGNORE_THE = 10
SORT_METHOD_TRACKNUM = 7
SORT_METHOD_UNSORTED = 40
SORT_METHOD_VIDEO_ORIGINAL_TITLE = 49
SORT_METHOD_VIDEO_ORIGINAL_TITLE_IGNORE_THE = 50
SORT_METHOD_VIDEO_RATING = 19
SORT_METHOD_VIDEO_RUNTIME = 32
SORT_METHOD_VIDEO_SORT_TITLE = 26
SORT_METHOD_VIDEO_SORT_TITLE_IGNORE_THE = 27
SORT_METHOD_VIDEO_TITLE = 25
SORT_METHOD_VIDEO_USER_RATING = 20
SORT_METHOD_VIDEO_YEAR = 18


class _Item(NamedTuple):
    url: str
    item: 'xbmcgui.ListItem'
    folder: bool


@define
class PluginDirectory:
    """Plugin directory."""
    items: List[_Item] = field(factory=list)
    view: str = ''
    category: str = ''
    sort_method: int = SORT_METHOD_NONE
    label_mask: str = ''
    label2_mask: str = ''


_print_item_list_cb: Optional[Callable[[PluginDirectory], None]] = None
_directory = PluginDirectory()


def addDirectoryItem(handle: int,
                     url: str,
                     listitem: 'xbmcgui.ListItem',
                     isFolder: bool = False,
                     totalItems: int = 0) -> bool:
    _directory.items.append(_Item(url, listitem, isFolder))
    return True


def addDirectoryItems(handle: int,
                      items: List[Tuple[str,  'xbmcgui.ListItem',  bool]],
                      totalItems: int = 0) -> bool:
    _directory.items.extend((_Item(*it) for it in items))
    return True


def endOfDirectory(handle: int,
                   succeeded: bool = True,
                   updateListing: bool = False,
                   cacheToDisc: bool = True) -> None:
    from lib.fake.fake_api import fin_directory
    fin_directory()
    if _print_item_list_cb:
        _print_item_list_cb(_directory)


def setResolvedUrl(handle: int,
                   succeeded: bool,
                   listitem: 'xbmcgui.ListItem') -> None:
    pass


def addSortMethod(handle: int,
                  sortMethod: int,
                  labelMask: str = "",
                  label2Mask: str = "") -> None:
    _directory.sort_method = sortMethod
    _directory.label_mask = labelMask
    _directory.label2_mask = label2Mask


def getSetting(handle: int, id: str) -> str:
    return ""


def setSetting(handle: int, id: str, value: str) -> None:
    pass


def setContent(handle: int, content: str) -> None:
    _directory.view = content


def setPluginCategory(handle: int, category: str) -> None:
    _directory.category = category


def setPluginFanart(handle: int,
                    image: Optional[str] = None,
                    color1: Optional[str] = None,
                    color2: Optional[str] = None,
                    color3: Optional[str] = None) -> None:
    pass


def setProperty(handle: int, key: str, value: str) -> None:
    pass
