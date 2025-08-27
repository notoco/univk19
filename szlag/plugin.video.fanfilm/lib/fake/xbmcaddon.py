from __future__ import annotations
from typing import Optional, List, Dict, ClassVar, TYPE_CHECKING
import re
from pathlib import Path
import atexit as _atexit
try:
    from lxml import etree as _etree
    def _xpath(elem: _Element, _path: str, **kwargs):
        # print(f'@@@@@@@@@@@@@@@@@  {_path!r}: {len(elem.xpath(_path, **kwargs))}')
        return elem.xpath(_path, **kwargs)
except ImportError:
    from xml.etree import ElementTree as _etree
    def _xpath(elem: _Element, _path: str, **kwargs):
        # print(f'@@@@@@@@@@@@@@@@@  {_path!r}: {len(elem.findall(_path, **kwargs))}')
        return elem.findall(_path, **kwargs)
from lib.fake.fake_tools import DeprecatedError, deprecated_warning
from lib.fake import fake_api
if TYPE_CHECKING:
    from lxml.etree import _ElementTree, _Element

__fake_kodi__ = True


@_atexit.register
def _save_settings():
    """Save all changed settings."""
    from shutil import copy2
    from datetime import datetime
    now = datetime.now()
    for addon in Addon._instances.values():
        if (sets := addon._settings) and sets._tree and sets._path:
            if fake_api.SETTINGS_READONLY:
                print('Settings are read-only, not saving changes')
            else:
                if sets._path.exists():
                    old = sets._path.with_suffix(f'.{now:%Y%m%d-%H%M%S}{sets._path.suffix}')
                    if not old.exists():
                        copy2(sets._path, old)
                # _etree.tostring(sets._root, pretty_print=True)
                try:
                    sets._tree.write(str(sets._path), pretty_print=True)
                except TypeError:
                    sets._tree.write(str(sets._path))


class Addon:

    _instances: ClassVar[Dict[str, 'Addon']] = {}
    _current: ClassVar[Optional['Addon']] = None

    def __new__(cls, id: Optional[str] = None) -> 'Addon':
        try:
            return cls._instances[id or '']
        except KeyError:
            pass
        obj = object.__new__(cls)
        return obj

    def __init__(self, id: Optional[str] = None) -> None:
        self._id: str = id or ''
        self._lang: str = fake_api.LOCALE
        self._settings: Optional[Settings] = None
        self._xml_root: _Element = None  # 'addon.xml'
        self._translation: Optional[Dict[int, str]] = None
        self.__class__._instances[self._id] = self
        if not self._id:
            self._id = self.xml_root.attrib.get('id', 'plugin.video.fanfilm')
            self.__class__._instances[self._id] = self
            self.__class__._current = self

    @property
    def path(self) -> Path:
        if self._id and self is not self._current:
            path = Path(__file__).parent.parent.parent.parent / self._id
            if path.exists():
                return path
            return fake_api.KODI_PATH / 'addons' / self._id
        return Path(__file__).parent.parent.parent

    @property
    def xml_root(self) -> _Element:
        if self._xml_root is None:
            try:
                tree: _ElementTree = _etree.parse(str(self.path / 'addon.xml'))
                self._xml_root = tree.getroot()
            except OSError:
                self._xml_root = _etree.Element('addon')
        return self._xml_root

    @property
    def translation(self) -> Dict[int, str]:
        if self._translation is None:
            self._translation = {}
            rx_id = re.compile(r'msgctxt\s+"#(\d+)"')
            rx_en = re.compile(r'msgid\s+"(.*)"')
            rx_tr = re.compile(r'msgstr\s+"(.*)"')
            if self._id.startswith('resource.language.') and (path := self.path / 'resources' / 'strings.po').exists():
                pass
            else:
                for lang in (self._lang, 'en_GB', 'en_US'):
                    path = self.path / 'resources' / 'language' / f'resource.language.{lang.lower().replace("-", "_")}' / 'strings.po'
                    if path.exists():
                        break
                else:
                    return {}
            with open(path, encoding='utf-8') as f:
                mid, src = None, ''
                for ln in f:
                    ln = ln.rstrip()
                    if (m := rx_id.fullmatch(ln)):
                        mid = int(m[1])
                    elif (m := rx_en.fullmatch(ln)):
                        src = m[1]
                    elif (m := rx_tr.fullmatch(ln)):
                        if mid:
                            self._translation[mid] = m[1] or src
                        mid, src = None, ''
                    else:
                        mid, src = None, ''
        return self._translation

    def getLocalizedString(self, id: int) -> str:
        return self.translation.get(id, f'#{id}')

    def getSettings(self) -> 'Settings':
        if self._settings is None:
            path = Path(self.getAddonInfo('profile')) / 'settings.xml'
            if not path.exists():
                Settings._create(path)
            self._settings = Settings(path)
        return self._settings

    def getSetting(self, id: str) -> str:
        return self.getSettings().getString(id)

    def getSettingBool(self, id: str) -> bool:
        raise DeprecatedError()
        return True

    def getSettingInt(self, id: str) -> int:
        raise DeprecatedError()
        return 0

    def getSettingNumber(self, id: str) -> float:
        raise DeprecatedError()
        return 0.0

    def getSettingString(self, id: str) -> str:
        raise DeprecatedError()
        return ""

    def setSetting(self, id: str, value: str) -> None:
        raise DeprecatedError()
        pass

    def setSettingBool(self, id: str, value: bool) -> bool:
        deprecated_warning()
        self.getSettings().setBool(id, value)
        return True

    def setSettingInt(self, id: str, value: int) -> bool:
        deprecated_warning()
        self.getSettings().setInt(id, value)
        return True

    def setSettingNumber(self, id: str, value: float) -> bool:
        deprecated_warning()
        self.getSettings().setNumber(id, value)
        return True

    def setSettingString(self, id: str, value: str) -> bool:
        deprecated_warning()
        self.getSettings().setString(id, value)
        return True

    def openSettings(self) -> None:
        pass

    def getAddonInfo(self, id: str) -> str:
        id = id.lower()
        if id == 'id':
            return self._id
        if id == 'path':
            return str(self.path)
        if id == 'name':
            return self.xml_root.attrib.get('name', self._id)
        if id == 'version':
            return self.xml_root.attrib.get('version', 999)
        if id == 'profile':
            # TODO: add suport default path for Windows.
            return str(fake_api.KODI_PATH / f'userdata/addon_data/{self._id}/')
        if id == 'author':
            return self.xml_root.attrib.get('provider-name', '')
        if id == 'changelog':
            meta = _xpath(self.xml_root, './extension[@point="xbmc.addon.metadata"]/news')
            return meta[0].text if meta else ''
        if id == 'description':
            meta = None
            lang = self._lang.partition('_')[0].lower()
            if lang:
                meta = _xpath(self.xml_root, f'./extension[@point="xbmc.addon.metadata"]/description[@lang="{lang}"]')
            if not meta:
                meta = _xpath(self.xml_root, './extension[@point="xbmc.addon.metadata"]/description')
            return meta[0].text if meta else ''
        if id in ('fanart', 'icon'):
            meta = _xpath(self.xml_root, f'./extension[@point="xbmc.addon.metadata"]/assets/{id}')
            if meta:
                return str(self.path / meta[0].text)
            return ''
        return ''
        # MISSING: disclaimer stars summary type
        # ALL: author changelog description disclaimer fanart icon id name path profile stars summary type version


class Settings:

    API_LANGUAGE: ClassVar[Optional[str]] = None

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path: Optional[Path] = path
        self._tree: Optional[_ElementTree] = None
        self._root: Optional[_Element] = None
        if self._path and self._path.exists():
            self._tree = _etree.parse(str(path))
            self._root = self._tree.getroot()
        self._setting_defs = _etree.parse(str(Path(__file__).parent.parent.parent / 'resources' / 'settings.xml')).getroot()
        self._types = {s.attrib['id']: s.attrib['type'] for s in _xpath(self._setting_defs, './/setting')}
        self._dirty: bool = False

    def getBool(self, id: str) -> bool:
        return self.getString(id).lower() in ('true', '1')

    def getInt(self, id: str) -> int:
        return int(self.getString(id))

    def getNumber(self, id: str) -> float:
        return float(self.getString(id))

    def getString(self, id: str) -> str:
        if (value := fake_api.SETTINGS.get(id)) is not None:
            return value
        if self.API_LANGUAGE is not None and id == 'api.language':
            return self.API_LANGUAGE
        if self._root is not None:
            try:
                return _xpath(self._root, f'./setting[@id="{id}"]')[0].text or ''
            except IndexError:
                pass
        return ''

    def getBoolList(self, id: str) -> List[bool]:
        return []

    def getIntList(self, id: str) -> List[int]:
        return []

    def getNumberList(self, id: str) -> List[float]:
        return []

    def getStringList(self, id: str) -> List[str]:
        return []

    def setBool(self, id: str, value: bool) -> None:
        pass

    def setInt(self, id: str, value: int) -> None:
        pass

    def setNumber(self, id: str, value: float) -> None:
        pass

    def setString(self, id: str, value: str) -> None:
        fake_api.SETTINGS[id] = value
        if fake_api.SETTINGS_READONLY:
            return
        if self._tree is None or self._root is None:
            from lib.ff.log_utils import warning
            warning('Settings.set... without path - ignored')
            return
        try:
            node = _xpath(self._root, f'./setting[@id="{id}"]')[0]
        except IndexError:
            from lib.ff.log_utils import error
            error(f'There is no {id!r} setting')
            return
        if node.text == value:
            return
        self._dirty = True
        node.text = str(value)
        try:
            del node.attrib['default']
        except KeyError:
            pass

    def setBoolList(self, id: str, values: List[bool]) -> None:
        pass

    def setIntList(self, id: str, values: List[int]) -> None:
        pass

    def setNumberList(self, id: str, values: List[float]) -> None:
        pass

    def setStringList(self, id: str, values: List[str]) -> None:
        pass

    @staticmethod
    def _create(path: Path, *, source: Optional[Path] = None) -> None:
        if source is None:
            source = Path(__file__).parent.parent.parent / 'resources' / 'settings.xml'
        path.parent.mkdir(parents=True, exist_ok=True)
        tree = _etree.parse(str(source))
        root: _Element = tree.getroot()
        out = _etree.Element('settings', version='2')
        for node in root.iterfind('.//setting'):
            if fake_api.SETTINGS_READONLY:
                if (default := node.find('./default')) is not None:
                    fake_api.SETTINGS.setdefault(node.attrib['id'], default.text)
            else:
                # default="true" ?
                sub = _etree.SubElement(out, 'setting', id=node.attrib['id'])
                if (preset := fake_api.SETTINGS.get(node.attrib['id'])) is not None:
                    sub.text = preset
                elif (default := node.find('./default')) is not None:
                    sub.text = default.text
        if not fake_api.SETTINGS_READONLY:
            try:
                path.write_bytes(_etree.tostring(out, pretty_print=True))
            except TypeError:
                path.write_bytes(_etree.tostring(out))
        # print(_etree.tostring(out, pretty_print=True).decode())
