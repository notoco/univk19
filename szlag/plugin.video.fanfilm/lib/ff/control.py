"""
    Fanfilm Add-on

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

from __future__ import annotations
import sys
import os.path
from urllib.parse import parse_qsl
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Union, Any, Tuple, List, Dict, Iterator, Sequence, Callable, ClassVar, overload, TYPE_CHECKING
from typing_extensions import Literal
from attrs import define, field

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

from .locales import kodi_locale
from .settings import settings
from ..kolang import L
if TYPE_CHECKING:
    from .kotools import Notification


AddonInfo = Literal['author', 'changelog', 'description', 'disclaimer', 'fanart', 'icon', 'id', 'name',
                    'path', 'profile', 'stars', 'summary', 'type', 'version']


def reset() -> None:
    """Reset control stuff for reuse code (re-run in the same Python interpreter)."""
    global sysaddon, syshandle, sysparams, sysaction
    sysaddon = sys.argv[0]
    syshandle = int(sys.argv[1]) if len(sys.argv) > 1 else -1
    sysparams = dict(parse_qsl(sys.argv[2][1:])) if len(sys.argv) > 2 else {}
    sysaction = sysparams.get("action")


# set in reset
sysaddon: str = None
syshandle: int = 0
sysparams: Dict[str, str] = None  # NOTE: it's simplified PARAMs, for full one use main.get_params()
sysaction: str = None

reset()

HOME_WINDOW = 10_000
WINDOW_DIALOG_BUSY = 10_138
WINDOW_DIALOG_BUSY_NOCANCEL = 10_160
ACTIVE_WINDOW = -1


def setting(id: str) -> str:
    """Get K19 setting (everything is string)."""
    return settings.get_string(id, stack_depth=2)


def setSetting(id: str, value: str) -> None:
    """Set K19 setting (everything is string)."""
    settings.set_string(id, value, stack_depth=2)


def addon(*args, **kwargs):
    return xbmcaddon.Addon(*args, **kwargs)


def window(*args, **kwargs):
    """HOME window."""
    return xbmcgui.Window(10000, *args, **kwargs)


def dialog(*args, **kwargs):
    return xbmcgui.Dialog(*args, **kwargs)


def progressDialog(*args, **kwargs):
    return xbmcgui.DialogProgress(*args, **kwargs)


def progressDialogBG(*args, **kwargs):
    return xbmcgui.DialogProgressBG(*args, **kwargs)


def windowDialog(*args, **kwargs):
    return xbmcgui.WindowDialog(*args, **kwargs)


def keyboard(*args, **kwargs):
    return xbmc.Keyboard(*args, **kwargs)


# def monitor(*args, **kwargs):
#     return xbmc.Monitor(*args, **kwargs)


def addonInfo(info: AddonInfo, *args, **kwargs) -> str:
    # author, changelog, description, disclaimer, fanart, icon, id, name, path, profile, stars, summary, type, version
    return xbmcaddon.Addon().getAddonInfo(info, *args, **kwargs)


def lang(string_id, *args, **kwargs):
    if isinstance(string_id, str):
        return string_id
    return xbmcaddon.Addon().getLocalizedString(string_id, *args, **kwargs)


def player(*args, **kwargs):
    return xbmc.Player(*args, **kwargs)


def getCurrentDialogId(*args, **kwargs):
    return xbmcgui.getCurrentWindowDialogId(*args, **kwargs)


def playlist(type=xbmc.PLAYLIST_VIDEO, *args, **kwargs):
    return xbmc.PlayList(type, *args, **kwargs)


plugin_id: str = addonInfo('id')
plugin_url: str = f'plugin://{plugin_id}/'
ff2_plugin_url: str = 'plugin://plugin.video.fanfilm/'  # old fixed name
ff3a_plugin_url: str = 'plugin://plugin.video.fanfilm3/'  # new fixed name of FF3 alpha, YES fanfilm3, 3 (sic!)

integer = 1000

lang2 = xbmc.getLocalizedString

addItem = xbmcplugin.addDirectoryItem
addItems = xbmcplugin.addDirectoryItems

item = xbmcgui.ListItem

directory = xbmcplugin.endOfDirectory

content = xbmcplugin.setContent

property = xbmcplugin.setProperty

infoLabel = xbmc.getInfoLabel

condVisibility = xbmc.getCondVisibility

jsonrpc = xbmc.executeJSONRPC

button = xbmcgui.ControlButton

image = xbmcgui.ControlImage

openFile = xbmcvfs.File

make_dir = xbmcvfs.mkdir

deleteFile = xbmcvfs.delete

deleteDir = xbmcvfs.rmdir

listDir = xbmcvfs.listdir

existsPath = xbmcvfs.exists

transPath = xbmcvfs.translatePath

skinPath = xbmcvfs.translatePath("special://skin/")

addonPath = xbmcvfs.translatePath(addonInfo("path"))

dataPath = xbmcvfs.translatePath(addonInfo("profile"))

settingsFile = os.path.join(dataPath, "settings.xml")

viewsFile = os.path.join(dataPath, "views.db")

bookmarksFile = os.path.join(dataPath, "bookmarks.db")

providercacheFile = os.path.join(dataPath, "providers.14.db")

episodesFile = os.path.join(dataPath, "episodes.json")

sourcescacheFile = os.path.join(dataPath, "sources.1.db")

searchFile = os.path.join(dataPath, "search.1.db")

libcacheFile = os.path.join(dataPath, "library.db")

cacheFile = os.path.join(dataPath, "cache.db")

downloadsFile = os.path.join(dataPath, "downloads.1.db")

key = "RgUkXp2s5v8x/A?D(G+KbPeShVmYq3t6"

iv = "p2s5v8y/B?E(H+Mb"

skin = xbmc.getSkinDir()


def addon_file(fname: str) -> Path:
    """Return path to addon file."""
    return Path(addonPath) / fname


def resources_file(fname: str) -> str:
    """Return path to addon resources file (not media addon)."""
    return str(Path(addonPath) / 'resources' / fname)


# Modified `sleep` command that honors a user exit request
def sleep(time_msec, /):
    from .kotools import xsleep
    xsleep(time_msec / 1000)


def execute(function: str, wait: bool = False) -> None:
    """Execute Kodi built-in function."""
    from .log_utils import fflog
    fflog(f'Built-in ({function}) executed (wait={wait})', stack_depth=2)
    xbmc.executebuiltin(function, wait)


def run_plugin(url: str):
    from .log_utils import fflog
    fflog(f'RunPlugin({url}) executed', stack_depth=2)
    return xbmc.executebuiltin(f'RunPlugin({url})')


def addonIcon():
    return addonInfo("icon")


def addonThumb():
    return os.path.join(art_path, "common/poster.png")


def addonPoster():
    return os.path.join(art_path, "common/poster.png")


def addonBanner():
    return os.path.join(art_path, "common/banner.png")


def addonFanart():
    return os.path.join(art_path, "fanart.jpg")


def addonLandscape():
    return os.path.join(art_path, "common/landscape.jpg")


def addonNext():
    return os.path.join(art_path, "common/poster_next.jpg")


def addonId():
    return addonInfo("id")


def addonName():
    return addonInfo("name")


def artPath():
    return os.path.join(
        xbmcaddon.Addon("script.fanfilm.media").getAddonInfo("path"),
        "resources",
        "media",
    )


art_path = artPath()


def infoDialog(message, heading=addonInfo("name"), icon="", time=3000, sound=False):
    if icon == "":
        icon = addonIcon()
    elif icon == "INFO":
        icon = xbmcgui.NOTIFICATION_INFO
    elif icon == "WARNING":
        icon = xbmcgui.NOTIFICATION_WARNING
    elif icon == "ERROR":
        icon = xbmcgui.NOTIFICATION_ERROR
    dialog().notification(heading, message, icon, time, sound=sound)


def notification(
    # Dialog heading (title).
    heading: str,
    # heading: str = field()
    # Dialog message.
    message: str,
    # message: str = field()
    # Icon to use. Default is FanFilm icon.
    icon: Optional[str] = None,
    # Time in SECONDS (sic!). Default 5, None or -1 means forever.
    interval: Optional[float] = 5,
    # Play notification sound, default True.
    sound: bool = True,
    # True if the notification is visible, if not, you must use show().
    visible: bool = False,
    # Startup show delay in seconds.
    delay: float = -1,  # -1 means auto (zero or almost zero)
    # Show works if True otherwise hidden notification (show is not enabled).
    enabled: bool = True
) -> Notification:
    from .kotools import Notification
    return Notification(heading=heading, message=message, icon=icon, interval=interval, sound=sound, visible=visible, delay=delay, enabled=enabled)


def yesnoDialog(*lines: str, heading: str = addonInfo('name'), nolabel: str = '', yeslabel: str = '') -> bool:
    return dialog().yesno(heading, '\n'.join(lines), nolabel, yeslabel)


def selectDialog(list, heading=addonInfo("name")):
    return dialog().select(heading, list)


def apiLanguage() -> Dict[str, str]:
    """Return dict with language (pl) or locale (pl-PL) for services."""
    # locale in ISO 639/1 & 3136/1 (eg. "pl-PL")
    locale: str = settings.getString('api.language')
    if locale and locale[0].isupper() and locale[-1].islower():  # old format: eg. "Polish"
        locale = 'pl-PL'  # force default
    if not locale or locale == 'AUTO':
        locale = kodi_locale()
    # language in ISO 639/1 (eg. "pl")
    lang: str = locale.partition('-')[0]
    return {
        'trakt': lang,
        'youtube': lang,
        'tmdb': locale,
        'image': lang,
    }


def api_language(service: Literal['tmdb', 'trakt', 'image', 'youtube']) -> str:
    """Return corrent language for given service."""
    langs = apiLanguage()
    return langs.get(service, langs['tmdb'])


def version():
    num = ""
    try:
        version = addon("xbmc.addon").getAddonInfo("version")
    except Exception:
        version = "999"
    for i in version:
        if i.isdigit():
            num += i
        else:
            break
    return int(num)


def cdnImport(uri, name):
    import imp

    from lib.ff import client

    path = os.path.join(dataPath, "py" + name)
    path = path.decode("utf-8")

    deleteDir(os.path.join(path, ""), force=True)
    make_dir(dataPath)
    make_dir(path)

    r = client.request(uri)
    p = os.path.join(path, name + ".py")
    f = openFile(p, "w")
    f.write(r)
    f.close()
    m = imp.load_source(name, p)

    deleteDir(os.path.join(path, ""), force=True)
    return m


def openSettings() -> None:
    xbmcaddon.Addon().openSettings()


def getCurrentViewId():
    win = xbmcgui.Window(xbmcgui.getCurrentWindowId())
    return str(win.getFocusId())


@overload
def get_window_property(key: str) -> str: ...


@overload
def get_window_property(window: int, key: str) -> str: ...


def get_window_property(window: int = HOME_WINDOW, key: str = ...) -> str:  # type: ignore
    """Return single property `key` from the window."""
    if key is ...:
        window, key = HOME_WINDOW, window
    if window == ACTIVE_WINDOW:
        window = xbmcgui.getCurrentWindowId()
    win = xbmcgui.Window(window)
    return win.getProperty(key)


def get_window_properties(window: int = HOME_WINDOW, *keys: str) -> Sequence[str]:
    """Return all properties `keys` from the window as tuple (in keuys order)."""
    if window == ACTIVE_WINDOW:
        window = xbmcgui.getCurrentWindowId()
    win = xbmcgui.Window(window)
    return tuple(win.getProperty(key) for key in keys)


def get_window_properties_dict(window: int = HOME_WINDOW, *keys: str) -> Dict[str, str]:
    """Return all properties `keys` from the window as dict."""
    if window == ACTIVE_WINDOW:
        window = xbmcgui.getCurrentWindowId()
    win = xbmcgui.Window(window)
    return {key: win.getProperty(key) for key in keys}


def is_plugin_folder() -> bool:
    """Return True if listing the plugin (FF3). False otherwise (example in a widget)."""
    return xbmc.getInfoLabel('Container.PluginName') == plugin_id


def refresh():
    from .log_utils import fflog
    fflog('refresh: Container.Refresh executed', stack_depth=2)
    return execute("Container.Refresh()")


def update(path: Optional[str] = None, *, replace: bool = False):
    from .log_utils import fflog
    fflog(f'refresh: Container.Update executed, {replace=}', stack_depth=2)
    if replace:
        return execute(f"Container.Update({path or ''},replace)")
    return execute(f"Container.Update({path or ''})")


def idle():
    from .log_utils import fflog
    fflog('idle: Dialog.Close(busydialognocancel) executed', stack_depth=2)
    execute("Dialog.Close(busydialognocancel)")  # Kodi 17


def queueItem():
    from .log_utils import fflog
    fflog('queueItem: Action(Queue) executed', stack_depth=2)
    return execute("Action(Queue)")


def metadataClean(metadata):
    """Filter out non-existing/custom keys. Otherwise there are tons of errors in Kodi 18 log."""
    if metadata is None:
        return metadata
    allowed = {
        "genre",
        "country",
        "year",
        "episode",
        "season",
        "sortepisode",
        "sortseason",
        "episodeguide",
        "showlink",
        "top250",
        "setid",
        "tracknumber",
        "rating",
        "userrating",
        # "watched",
        "playcount",
        "overlay",
        "cast",
        "castandrole",
        "director",
        "mpaa",
        "plot",
        "plotoutline",
        "title",
        "originaltitle",
        "sorttitle",
        "duration",
        "studio",
        "tagline",
        "writer",
        "tvshowtitle",
        "premiered",
        "status",
        "set",
        "setoverview",
        "tag",
        "imdbnumber",
        "code",
        "aired",
        "credits",
        "lastplayed",
        "album",
        "artist",
        "votes",
        "path",
        "trailer",
        "dateadded",
        "mediatype",
        "dbid",
    }
    return {k: v for k, v in metadata.items() if k in allowed}


def busy_dialog(show: bool = True, *, cancellable: bool = False, stack_depth: int = 1) -> None:
    """
    Change busy-dialog state (open or close).

    show         - open if True else close
    cancellable  - if True opened dialog could be cancelled by user
    """
    from .log_utils import fflog
    if show:
        win_id = WINDOW_DIALOG_BUSY if cancellable else WINDOW_DIALOG_BUSY_NOCANCEL
        fflog('Open busy-dialog', stack_depth=stack_depth + 1)
        execute(f'ActivateWindow({win_id})')
    else:
        fflog('Close busy-dialog', stack_depth=stack_depth + 1)
        execute(f'Dialog.Close({WINDOW_DIALOG_BUSY})')
        execute(f'Dialog.Close({WINDOW_DIALOG_BUSY_NOCANCEL})')


def close_busy_dialog(*, force: bool = False, stack_depth: int = 1) -> None:
    busy_dialog(False, stack_depth=stack_depth + 1)


@contextmanager
def busy_section(*,
                 complete_notif: Union[None, bool, str] = False,
                 sound: bool = True,
                 cancellable: bool = False,
                 stack_depth: int = 1,
                 ) -> Iterator[None]:
    """
    Section with busy dialog active.

    >>> with busy_section():
    ...    do_your_stuff()
    """
    busy_dialog(True, cancellable=cancellable, stack_depth=stack_depth + 1)
    try:
        yield None
    finally:
        busy_dialog(False, cancellable=cancellable, stack_depth=stack_depth + 1)
        if complete_notif:
            if not isinstance(complete_notif, str):
                complete_notif = L(32057, 'Process Complete')
            infoDialog(complete_notif, sound=sound)


def pretty_log_info() -> None:
    """Log info in pretty format."""
    from sqlite3 import sqlite_version
    from .log_utils import info as log
    from .kotools import get_platform
    # author, changelog, description, disclaimer, fanart, icon, id, name, path, profile, stars, summary, type, version
    info = xbmcaddon.Addon().getAddonInfo
    name = info('name')
    ver = info('version')
    media_ver = xbmcaddon.Addon('script.fanfilm.media').getAddonInfo('version') or '---'
    kodi_ver = xbmc.getInfoLabel('System.BuildVersion') or '---'
    log(f'''=== {name} ===
    {plugin_id}: {ver}
    script.fanfilm.media: {media_ver}
    kodi: {kodi_ver}
    python: {sys.version}
    sqlite3: {sqlite_version}
    platform: {get_platform()}''')


def max_thread_workers() -> int:
    """Return max number of thread worker from settings."""
    num = settings.getInt('threads.count')
    if num <= 0:
        from os import cpu_count
        num = min(32, (cpu_count() or 1) + 4)  # default since Python 3.8
    return num


@define
class Finally:
    _list: ClassVar[List['Finally']] = []

    func: Callable
    args: Tuple[Any, ...] = ()
    kwargs: Dict[str, Any] = field(factory=dict)

    def __call__(self) -> Any:
        return self.func(*self.args, **self.kwargs)

    @classmethod
    def call(cls, function: Callable, *args, **kwargs) -> 'Finally':
        fin = Finally(function, args, kwargs)
        cls._list.append(fin)
        return fin

    @classmethod
    def iter(cls) -> Iterator['Finally']:
        return iter(cls._list)

    @classmethod
    def clear(cls):
        cls._list.clear()
