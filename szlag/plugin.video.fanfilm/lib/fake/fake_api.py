
from __future__ import annotations
from typing import Optional, Any, Callable, List, TYPE_CHECKING
from pathlib import Path
from attrs import fields
if TYPE_CHECKING:
    from .xbmcplugin import _Item as Item, PluginDirectory
    from attrs import Attribute


def find_kodi_path() -> Path:
    for path in (
        Path(__file__).parent.parent.parent.parent,
        '~/.kodi',
        '~/.var/app/tv.kodi.Kodi/data',
    ):
        path = Path(path).expanduser()
        if (path / 'userdata').exists():
            return path
    return Path('~/.kodi').expanduser()


KODI_PATH: Path = find_kodi_path()
FF3_PATH: Path
LOCALE: str = 'pl-PL'
INFO_LABEL: dict[str, str] = {}
SETTINGS: dict[str, str] = {}
SETTINGS_READONLY: bool = False


def __getattr__(key: str) -> Any:
    if key == 'FF3_PATH':
        return KODI_PATH / 'userdata/addon_data/plugin.video.fanfilm'
    if key == 'LANG':
        return LOCALE.partition('-')[0]
    raise AttributeError(key)


def auto(argv: Optional[List[str]] = None) -> None:
    """Auto configuration."""
    from os import pathsep
    from lib.fake.fake_term import print_item_list, print_log
    set_print_list_callback(print_item_list)
    set_print_log_callback(print_log)
    if argv:
        from argparse import ArgumentParser
        p = ArgumentParser(add_help=False)
        p.add_argument('-K', '--kodi-path', metavar=f'PATH[{pathsep}PATH]...',
                       help='path to KODI user data and optional additional installation paths')
        p.add_argument('--import-path', metavar='PATH', action='append', help='add python import path')
        p.add_argument('--import-addon', metavar='ADDON_ID', action='append', help='add kodi addon import path')
        args, _ = p.parse_known_args(argv)
        if args.kodi_path:
            global KODI_PATH
            KODI_PATH = Path(args.kodi_path.partition(pathsep)[0]).expanduser().absolute()
        if args.import_path:
            import sys
            for p in args.import_path:
                p = str(Path(p).expanduser().absolute())
                if p not in sys.path:
                    sys.path.append(p)
        if args.import_addon:
            import sys
            import re
            rxe = re.compile(r'<extension[^>]+point="xbmc.python.module"[^>]*>', flags=re.DOTALL)
            rxl = re.compile(r'\blibrary="([^"]*)"')
            rxr = re.compile(r'<requires>(.*?)</requires>', flags=re.DOTALL)
            rxi = re.compile(r'<import[^>]+\baddon="([^"]*)"[^>]*>', flags=re.DOTALL)
            used: set[str] = set()
            addons: list[str] = list(args.import_addon)
            while addons:
                addon = addons.pop(0)
                if addon in used:
                    continue
                used.add(addon)
                for k in (KODI_PATH, *(args.kodi_path or '').split(pathsep)):
                    k = Path(k).expanduser().absolute()
                    p = k / 'addons' / addon
                    if not p.exists():
                        p = k / 'addons' / f'script.module.{addon}'
                        if p.exists():
                            used.add(f'script.module.{addon}')
                    try:
                        xml = (p / 'addon.xml').read_text()
                    except OSError:
                        continue
                    if (extension := rxe.search(xml)) and (library := rxl.search(extension.group(0))):
                        p = str(p / library.group(1))
                        if p not in sys.path:
                            sys.path.append(p)
                            print(f'sys.path add: {p}')
                    if requires := rxr.search(xml):
                        for imp in rxi.finditer(requires.group(1)):
                            req_addon = imp.group(1)
                            if not req_addon.startswith('xbmc.') and req_addon not in used:
                                addons.append(req_addon)
                    break
                else:
                    print(f'Error reading addon.xml for {addon}', file=sys.stderr)


def set_print_list_callback(cb: Optional[Callable[[PluginDirectory], None]]) -> None:
    """Print ListItem folder callback."""
    import xbmcplugin
    xbmcplugin._print_item_list_cb = cb


def get_directory() -> PluginDirectory:
    """Get current plugin directory."""
    import xbmcplugin
    return xbmcplugin._directory


def fin_directory() -> None:
    """Finalize plugin directory."""
    import xbmcplugin
    sorting: dict[int, tuple[str, ...]] = {
        xbmcplugin.SORT_METHOD_ALBUM: (),
        xbmcplugin.SORT_METHOD_ALBUM_IGNORE_THE: (),
        xbmcplugin.SORT_METHOD_ARTIST: (),
        xbmcplugin.SORT_METHOD_ARTIST_IGNORE_THE: (),
        xbmcplugin.SORT_METHOD_BITRATE: (),
        xbmcplugin.SORT_METHOD_CHANNEL: (),
        xbmcplugin.SORT_METHOD_COUNTRY: (),
        xbmcplugin.SORT_METHOD_DATE: (),
        xbmcplugin.SORT_METHOD_DATEADDED: (),
        xbmcplugin.SORT_METHOD_DATE_TAKEN: (),
        xbmcplugin.SORT_METHOD_DRIVE_TYPE: (),
        xbmcplugin.SORT_METHOD_DURATION: (),
        xbmcplugin.SORT_METHOD_EPISODE: (),
        xbmcplugin.SORT_METHOD_FILE: (),
        xbmcplugin.SORT_METHOD_FULLPATH: (),
        xbmcplugin.SORT_METHOD_GENRE: (),
        xbmcplugin.SORT_METHOD_LABEL: ('getLabel', ),
        xbmcplugin.SORT_METHOD_LABEL_IGNORE_FOLDERS: (),
        xbmcplugin.SORT_METHOD_LABEL_IGNORE_THE: (),
        xbmcplugin.SORT_METHOD_LASTPLAYED: (),
        xbmcplugin.SORT_METHOD_LISTENERS: (),
        xbmcplugin.SORT_METHOD_MPAA_RATING: (),
        xbmcplugin.SORT_METHOD_PLAYCOUNT: (),
        xbmcplugin.SORT_METHOD_PLAYLIST_ORDER: (),
        xbmcplugin.SORT_METHOD_PRODUCTIONCODE: (),
        xbmcplugin.SORT_METHOD_PROGRAM_COUNT: (),
        xbmcplugin.SORT_METHOD_SIZE: (),
        xbmcplugin.SORT_METHOD_SONG_RATING: (),
        xbmcplugin.SORT_METHOD_SONG_USER_RATING: (),
        xbmcplugin.SORT_METHOD_STUDIO: (),
        xbmcplugin.SORT_METHOD_STUDIO_IGNORE_THE: (),
        xbmcplugin.SORT_METHOD_TITLE: (),
        xbmcplugin.SORT_METHOD_TITLE_IGNORE_THE: (),
        xbmcplugin.SORT_METHOD_TRACKNUM: (),
        xbmcplugin.SORT_METHOD_UNSORTED: (),
        xbmcplugin.SORT_METHOD_VIDEO_ORIGINAL_TITLE: (),
        xbmcplugin.SORT_METHOD_VIDEO_ORIGINAL_TITLE_IGNORE_THE: (),
        xbmcplugin.SORT_METHOD_VIDEO_RATING: (),
        xbmcplugin.SORT_METHOD_VIDEO_RUNTIME: (),
        xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE: (),
        xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE_IGNORE_THE: (),
        xbmcplugin.SORT_METHOD_VIDEO_TITLE: (),
        xbmcplugin.SORT_METHOD_VIDEO_USER_RATING: (),
        xbmcplugin.SORT_METHOD_VIDEO_YEAR: (),
    }
    d: PluginDirectory = xbmcplugin._directory
    if sort := sorting.get(d.sort_method):
        def key(item: Item) -> Any:
            pos = item.item.getProperty('SpecialSort')
            if pos == 'top':
                return -1, None
            if pos == 'bottom':
                return +1, None
            value = item.item
            for attr in sort:
                value = getattr(item.item, attr)()
            return 0, value
        d.items.sort(key=key)


def reset() -> None:
    """Reset all fake xmbc structures."""
    import xbmcplugin
    from attrs import NOTHING, Factory
    f: Attribute
    for f in fields(xbmcplugin.PluginDirectory):
        if isinstance(f.default, Factory):
            setattr(xbmcplugin._directory, f.name, f.default.factory())
        elif f.default is not NOTHING:
            setattr(xbmcplugin._directory, f.name, f.default)


def url_at_index(index: int) -> str:
    """Return URL for direcotry index."""
    import xbmcplugin
    return str(xbmcplugin._directory.items[index].url or '')


def set_print_log_callback(cb: Optional[Callable[[str, int], None]]) -> None:
    """Reset all fake xmbc structures."""
    import xbmc
    xbmc._print_log_cb = cb


def print_last_directory() -> None:
    """(Re)print last directory."""
    import xbmcplugin
    if xbmcplugin._print_item_list_cb:
        xbmcplugin._print_item_list_cb(xbmcplugin._directory)


def set_locale(locale: Optional[str] = None, *, api: Optional[str] = None):
    """Set Kodi and/or FF3-API locale."""
    if locale:
        global LOCALE
        LOCALE = locale.replace('_', '-')
    if api:
        from xbmcaddon import Settings
        Settings.API_LANGUAGE = api.replace('_', '-')
