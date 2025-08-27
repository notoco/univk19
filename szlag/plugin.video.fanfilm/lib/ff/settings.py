"""Just Kodi settings, separated from control."""

from __future__ import annotations
from pathlib import Path
from threading import Lock
import json
import re
from copy import deepcopy
from string import Formatter
from datetime import datetime, date as dt_date, time as dt_time
from enum import IntEnum
from typing import Any, Sequence, Callable, ClassVar, Generic, TypeVar, get_args, overload, TYPE_CHECKING
from typing_extensions import Literal
from attrs import frozen
from xbmcaddon import Addon, Settings
import xbmcvfs
from .types import mk_bool
from .log_utils import fflog
from const import const
if TYPE_CHECKING:
    import ast
    from attr._make import NOTHING, _Nothing
    from simpleeval import SimpleEval
    from typing import Optional, Union, Tuple, Dict
    from typing_extensions import Pattern
else:
    from attr._make import NOTHING

T = TypeVar('T')

GetCallable = Callable[[str], Any]
SetCallable = Callable[[str, Any], None]

MethodGetName = Literal['getBool', 'getInt', 'getNumber', 'getString', 'getBoolList', 'getIntList', 'getNumberList', 'getStringList', 'getAction']
MethodSetName = Literal['setBool', 'setInt', 'setNumber', 'setString', 'setBoolList', 'setIntList', 'setNumberList', 'setStringList']
SettingsEvalType = Literal['bool', 'str', 'int', 'float']

SettingType = Literal['string', 'urlencodedstring', 'date', 'time', 'path', 'boolean', 'integer', 'number', 'action']


class SettingChanges(IntEnum):
    """Settings changes types."""
    NONE = 0
    CHANGED = 1
    DEFAULTS = 2


@frozen
class SettingDefinition:
    """Settings definition from resources/settings.xml."""

    id: str
    type: SettingType
    label: str = ''
    label_id: int = 0
    default_string: str = ''
    default: Any = None


@frozen
class SettingTypeDescription:
    """Settings type description."""

    type: SettingType
    getter: MethodGetName
    factory: Callable[[str], Any]


class SettingsProxy:
    """Settings proxy for settings manager."""

    def __init__(self, settings: SettingsManager, prefix: str = '') -> None:
        self._settings = settings
        self._prefix = prefix

    def __getattr__(self, key: str) -> Any:
        """Get settings by key."""
        if self._prefix:
            name = f'{self._prefix}.{key}'
        else:
            name = key
        sdef = self._settings.definitions.get(name)
        if sdef:
            return self._settings.get(name)
        if name in self._settings.definition_prefixes:
            return SettingsProxy(self._settings, name)
        fflog.warning(f'There is no setting {name!r}.')
        raise KeyError(f'There is no setting {name!r}.')


class SettingsManager:
    """K20+ settings proxy."""

    RX_SINGLE_VALUE_EXPR: ClassVar[Pattern[str]] = re.compile(r'\s*(not\s+)?((?!const\.)[\w.]+)\s*')
    BACKUP_FORMAT: ClassVar[str] = 'settings-%Y%m%d-%H%M.xml'

    DEF_TYPE: ClassVar[dict[str, SettingTypeDescription]] = {descr.type: descr for descr in (
        SettingTypeDescription('string',           'getString', str),
        SettingTypeDescription('urlencodedstring', 'getString', str),
        SettingTypeDescription('date',             'getString', dt_date.fromisoformat),
        SettingTypeDescription('time',             'getString', dt_time.fromisoformat),
        SettingTypeDescription('path',             'getString', str),
        SettingTypeDescription('boolean',          'getBool', mk_bool),
        SettingTypeDescription('integer',          'getInt', int),
        SettingTypeDescription('number',           'getNumber', float),
        SettingTypeDescription('action',           'getAction', str),
    )}

    Changes = SettingChanges

    def __init__(self, *, k19log: bool = True, safe: bool = False) -> None:
        #: Access lock
        self.lock = Lock()
        #: The addon.
        self._addon: Optional[Addon] = None
        #: K20+ settings object.
        self._settings: Optional[Settings] = None
        #: Log every outdated K19 get/set.
        self.k19log: bool = bool(k19log)
        #: Force use safe getter.
        self.safe: bool = bool(safe)
        # Create addon and settings.
        self.reset()
        #: Path to settings file.
        self.path = Path(xbmcvfs.translatePath(self._addon.getAddonInfo('profile'))) / 'settings.xml'
        #: Simple evalulator for settings expression.
        self._expr_eval: SimpleEval | None = None
        #: Simple evalulator for settings expression.
        self._expr_frm: SettingsFormatter | None = None
        #: Settings definitions (from resources/settings.xml).
        self._definitions: dict[str, SettingDefinition] | None = None
        #: Settings definition prefixes (from resources/settings.xml). Pseudo objects names.
        self._definition_prefixes: set[str] | None = None

    def _reset(self) -> None:
        """Reset setting access. Remove addon and recreate it again."""
        self._addon = Addon()
        self._settings = self._addon.getSettings()
        self._propagate_settings()

    def reset(self) -> None:
        """Reset setting access. Remove addon and recreate it again."""
        with self.lock:
            self._reset()

    def delete(self) -> None:
        with self.lock:
            self._addon = None
            self._settings = None

    @property
    def addon(self) -> Addon:
        with self.lock:
            if self._addon is None:
                self._reset()
                assert self._addon is not None
            return self._addon

    @addon.deleter
    def addon(self) -> None:
        with self.lock:
            self._addon = None
            self._settings = None

    @property
    def settings(self) -> Settings:
        with self.lock:
            if self._settings is None:
                self._reset()
                assert self._settings is not None
            return self._settings

    @settings.deleter
    def setting(self) -> None:
        with self.lock:
            self._settings = None

    def _propagate_settings(self) -> None:
        """Propagate changes to other modules."""
        from .log_utils import options  # import is here to avoid recurrence
        del options.show_fflog          # force refresh log setting

    def get_string(self, id: str, *, stack_depth: int = 1, k19log: Optional[bool] = None) -> str:
        """Get K19 setting (everything is string)."""
        if k19log is None:
            k19log = self.k19log
        if k19log:
            fflog(f'K19 outdated get setting {id!r}', stack_depth=stack_depth+1)
        return self.addon.getSetting(id)

    def set_string(self, id: str, value: str, *, stack_depth: int = 1) -> None:
        """Set K19 setting (everything is string)."""
        if self.k19log:
            fflog(f'K19 outdated set setting {id!r}', stack_depth=stack_depth+1)
        self.addon.setSetting(id, value)

    @overload
    def __getattr__(self, key: Literal['getBool']) -> Callable[[str], bool]: ...

    @overload
    def __getattr__(self, key: Literal['getInt']) -> Callable[[str], int]: ...

    @overload
    def __getattr__(self, key: Literal['getNumber']) -> Callable[[str], float]: ...

    @overload
    def __getattr__(self, key: Literal['getString']) -> Callable[[str], str]: ...

    @overload
    def __getattr__(self, key: MethodGetName) -> GetCallable: ...

    @overload
    def __getattr__(self, key: MethodSetName) -> SetCallable: ...

    # @overload
    # def __getattr__(self, key: str) -> Callable[..., Any]: ...

    def __getattr__(self, key: str) -> Union[GetCallable, SetCallable, Callable]:
        """Get settigns from kodi addon settings."""
        def safe_getter(*args, **kwargs):
            from .log_utils import log, LOGWARNING  # force logging, do NOT use fflog to avoid recurrence
            try:
                val = func(*args, **kwargs)
            except TypeError:
                pass  # pass to reset
            else:
                return val
            log(f'[SETTINGS] force RESET for {key}(*{args}, **{kwargs})', LOGWARNING)  # do NOT use fflog() here
            # settings are corrupted
            self.reset()
            # retry to get settings
            return func(*args, **kwargs)

        with self.lock:
            if self._settings is None:
                self._reset()
            # if self._addon is None:
            #     self._addon = Addon()
            # if self._settings is None:
            #     self._settings = self._addon.getSettings()
            if key.startswith('set'):
                # Addon().getSettings.setString(name, val) not works! Use old method.
                return getattr(self._addon, f'setSetting{key[3:]}')
            # special case, if kodi recall the plugin settings are corrupted, need to be reset
            if self.safe:
                # proxy to allow settings reset on corruption
                func = getattr(self._settings, key)
                return safe_getter
            # default getter
            return getattr(self._settings, key)

    def getAction(self, id: str) -> str:
        """Get action setting as string (kodi extension)."""
        if sdef := self.definitions.get(id):
            return sdef.default_string
        return ''

    @overload
    def get(self, key: str, *, default: Literal[_Nothing.NOTHING] = NOTHING) -> Any:  ...

    @overload
    def get(self, key: str, *, default: T) -> T:  ...

    def get(self, key: str, *, default: Any = NOTHING) -> Any:
        """Return setting value by key with correct type."""
        sdef = self.definitions.get(key)
        if sdef is None:
            if default is NOTHING:
                raise KeyError(f'Setting {key!r} is not defined.')
            return default
        descr = self.DEF_TYPE.get(sdef.type)
        if descr is None:
            from .log_utils import log  # force logging, do NOT use fflog to avoid recurrence
            log.warning(f'[SETTINGS] missing type {sdef.type!r} description for variable {key}')  # do NOT use fflog() here
            descr = SettingTypeDescription('string', 'getString', str)
        val = getattr(self, descr.getter)(key)
        if isinstance(val, str):
            val = descr.factory(val)
        return val

    def get_json(self, key: str, *, default: Any = None) -> Any:
        """Return JSON from settings string."""
        value = self.getString(key)
        if value:
            return json.loads(value)
        return default

    def set_json(self, key: str, value: Any) -> None:
        """Set JSON as settings string."""
        return self.setString(key, json.dumps(value))

    @property
    def data(self) -> SettingsProxy:
        """Return settings data as dict."""
        return SettingsProxy(self)

    def expr_tools(self) -> Tuple[SimpleEval, SettingsFormatter]:
        """Helper. Return simple eval and formatter instances."""
        from simpleeval import SimpleEval
        from cdefs import MINUTE, HOUR, DAY, WEEK, KiB, MiB, GiB, TiB
        from requests_cache.policy.expiration import DO_NOT_CACHE, EXPIRE_IMMEDIATELY, NEVER_EXPIRE
        if self._expr_eval is None:
            def name_handler(node: ast.Name):
                if val := names.get(node.id):
                    return val
                proxy = SettingsProxy(self)
                return getattr(proxy, node.id)
            from ..indexers.lists import ListsInfo
            from const import const
            names = {
                'const': const,            # trick to use const settings in expressions
                'settings': self.data,     # trick to direct use the settings in expressions
                'ListsInfo': ListsInfo(),  # trick to use ListsInfo (list services logged) in expressions
                'MINUTE': MINUTE, 'HOUR': HOUR, 'DAY': DAY, 'WEEK': WEEK,
                'KiB': KiB, 'MiB': MiB, 'GiB': GiB, 'TiB': TiB,
                'netcache': {
                    'DO_NOT_CACHE': DO_NOT_CACHE,
                    'EXPIRE_IMMEDIATELY': EXPIRE_IMMEDIATELY,
                    'NEVER_EXPIRE': NEVER_EXPIRE,
                },
            }
            self._expr_eval = SimpleEval(names=name_handler)
        fmt = self._expr_frm
        if fmt is None:
            self._expr_frm = fmt = SettingsFormatter(self)
        return self._expr_eval, fmt

    def eval(self, expr: str | bool) -> Any:
        """
        Return evaluated settings expression. Used in conditions.

        If `expr` is boolean, it is returned as is.

        All setting is taken directly (also prepended with `not`).
        Type is taken from settings definition (resources/settings.xml).
        Type could be placed into `{name:type}`. Supported types: str, bool, int, float. It is NOT recommended.

        Const settings are available as `const.name` (e.g. `const.library.service.notification`).

        Simple Python expression could be used.

        Examples.
        >>> settings.eval('any_setting_name')       # True if `bool_settgin_name` is true
        >>> settings.eval('not bool_setting_name')  # True if `bool_settgin_name` is false
        >>> settings.eval('{int_settings} > 5')     # True if `int_settings` is grather then 5
        >>> settings.eval('{name} / 2')             # Value of `name` divided by 2
        """
        if expr is None:
            return None
        if isinstance(expr, bool):
            return expr
        se, fmt = self.expr_tools()
        if mch := self.RX_SINGLE_VALUE_EXPR.fullmatch(expr):
            neg, name = mch.groups()
            val = self.get(name)
            return not val if neg else val
        expr = fmt.format(expr)
        return se.eval(expr)

    def load_defaults(self) -> dict[str, str]:
        """Load default settings from adddon settings 'resources/settings.xml'."""
        from xml.etree import ElementTree as ET
        defs_path = Path(__file__).parent.parent.parent / 'resources' / 'settings.xml'
        root = ET.parse(defs_path).getroot()
        if root.tag != 'settings':
            fflog.error(f'Addon settings {defs_path} is incorrect')
            return {}
        return {sid: default_node.text or ''
                for node in root.iterfind('.//setting')
                if (sid := node.get('id')) and (default_node := next(node.iterfind('./default'), None)) is not None}

    def _override_setting(self, *, data: bytes | None = None, source: Path | None = None) -> bool:
        """Atomic override user settings by `data` or `source` file (not both)."""
        if data is not None and source is not None:
            raise TypeError('Settings._override_setting() accepts data or source, not both')
        path = self.path.with_name(f'.settings-new-{datetime.now():%Y%m%d%H%M%S}.xml')
        try:
            if data:
                path.write_bytes(data)
            elif source:
                from shutil import copy2
                copy2(source, path)
        except OSError as exc:
            fflog.warning(f'Writing settings {path} FAILED: {exc}')
        else:
            try:
                # Replace should be atomic (on Linux rename is used).
                path.replace(self.path)
            except OSError as exc:
                fflog.warning(f'Override settings {self.path} FAILED: {exc}')
            else:
                return True
        return False

    def factory_reset(self) -> bool:
        """Reset settings to factory defaults. Returns True if settings changed."""
        if not self.path.exists():
            return False
        # backup current user settings
        self.make_backup()
        # remove user settings file
        try:
            self.path.unlink(missing_ok=True)
            return True
        except OSError as exc:
            fflog.warning(f'Factory reset settings {self.path} FAILED: {exc}')
            return False

    def clear_undefined(self, *, override_defaults: bool = False, vacuum: bool = True, dry_run: bool = False) -> SettingChanges | bool:
        """
        Clear user settings and remove all undefined ones. Returns True if settings changed.

        Settings definition is in 'resources/settings.xml'.
        Kodi adds new settings to user file but do not remove old one.
        This method remove all old (non-defined) user settings.

        If `override_defaults` is True, all settings will be set to default values.
        """
        if not self.path.exists():
            return False
        from xml.etree import ElementTree as ET
        # load user settings
        root = ET.parse(self.path).getroot()
        if root.tag != 'settings':
            fflog.error(f'User settings {self.path} is incorrect')
            return False
        # read current addon settings (user defaults)
        defs = self.load_defaults()
        # filter-out undefined user settings
        indent = '\n    '
        out = ET.Element('settings', version='2')
        out.text = indent
        current: dict[str, tuple[str, bool]] = {node.attrib['id']: ((node.text or ''), (node.get('default') == 'true'))
                                                for node in root.iterfind('.//setting')}
        removed: set[str] = current.keys() - defs.keys()
        # set all defined settings
        for sid, default in defs.items():
            sub = ET.SubElement(out, 'setting', id=sid)
            cur_val, cur_default = current.get(sid, (sid, True))
            sub.text = default if override_defaults and cur_default else cur_val
            if (sub.text or '') == default:
                sub.set('default', 'true')
            sub.tail = indent
        if len(out):
            out[-1].tail = '\n'
        new_data = ET.tostring(out)
        if dry_run:
            if self.path.read_bytes() == new_data:
                return SettingChanges.NONE  # no changes
            if override_defaults:
                if any(df and val != defs.get(sid) for sid, (val, df) in current.items()):
                    return SettingChanges.DEFAULTS  # dry run, settings changed, defaults updated
            return SettingChanges.CHANGED  # dry run, settings changed
        # backup current user settings
        self.make_backup(vacuum=vacuum)
        # write cleaned user settings
        if not self._override_setting(data=new_data):
            return False
        if removed:
            fflog(f'Removed user settings: {", ".join(sorted(removed))}')
        return True

    def get_settings_getter(self, name: str) -> Callable[[str], Any]:
        """Return settings getter by settings name/id."""
        if sdef := self.definitions.get(name):
            descr = self.DEF_TYPE[sdef.type]
            return getattr(self, descr.getter)
        # ERROR
        return self.getBool

    @property
    def definitions(self) -> dict[str, SettingDefinition]:
        """Return settings definitions (resources/settings.xml)."""
        from xml.etree import ElementTree as ET
        if self._definitions is None:
            def make_def(elem: ET.Element) -> SettingDefinition:
                dtype: SettingType = elem.attrib.get('type', 'string')  # type: ignore[reportAssignmentType]
                default, default_string = None, ''
                if dtype == 'action':
                    default_node = elem.find('./data')
                else:
                    default_node = elem.find('./default')
                if default_node is not None:
                    if default_string := (default_node.text or ''):
                        try:
                            default = self.DEF_TYPE[dtype].factory(default_string)
                        except (ValueError, TypeError):
                            fflog.error(f'Incorrect default value for setting {elem.attrib["id"]!r}: {default_string!r}')
                    else:
                        try:
                            default = self.DEF_TYPE[dtype].factory('')
                        except (ValueError, TypeError):
                            default = None
                label = elem.attrib.get('label')
                return SettingDefinition(
                    id=elem.attrib['id'],
                    type=dtype,
                    label_id=int(label) if label and label.isdecimal() else 0,
                    default_string=default_string,
                    default=default,
                )
            defs_path = Path(__file__).parent.parent.parent / 'resources' / 'settings.xml'
            root = ET.parse(defs_path).getroot()
            self._definitions = {s.attrib['id']: make_def(s) for s in root.iterfind('.//setting')}
        return self._definitions

    @property
    def definition_prefixes(self) -> set[str]:
        """Return settings definition prefixes / pseud objects names (from resources/settings.xml)."""
        if self._definition_prefixes is None:
            definitions = self.definitions
            self._definition_prefixes = set()
            for name in definitions:
                prefix = name.rpartition('.')[0]
                while prefix and prefix not in definitions:
                    self._definition_prefixes.add(prefix)
                    prefix = prefix.rpartition('.')[0]
        return self._definition_prefixes

    def make_backup(self, *, vacuum: bool = True) -> bool:
        """Create user settings backup."""
        from shutil import copy2
        path = self.path.with_name(datetime.now().strftime(self.BACKUP_FORMAT))
        if path.exists():
            for i in range(1, 1000):
                if not (p := path.with_name(f'{path.stem}+{i:03d}{path.suffix}')).exists():
                    path = p
                    break
            else:
                fflog.warning(f'Can not find any available name for backup settings for {path}')
                return False
        try:
            copy2(self.path, path)
        except OSError as exc:
            fflog.warning(f'Copy settings to {path} FAILED: {exc}')
            return False
        return True

    def restore_backup(self, path: Path) -> bool:
        """Restore backup. `path` must be a full path."""
        if path.exists():
            return self._override_setting(source=path)
        fflog(f'Restore backup failed, {path} does not exist')
        return False

    def backup_files(self) -> Sequence[Path]:
        """Return sorted list of backup files. First is newest."""
        folder = self.path.parent
        pattern = re.sub(r'(?:%.|\*)+', '*', self.BACKUP_FORMAT)
        return sorted((path for path in folder.glob(pattern) if path.is_file()), reverse=True)

    def vacuum(self, *, vacuum_files: int | None = None) -> None:
        """Remove old backups, keep last `vacuum_files` files."""
        if vacuum_files is None:
            vacuum_files = const.tune.settings.vacuum_files
        backups = self.backup_files()
        for path in backups[vacuum_files:]:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                fflog(f'Can NOT remove old backup {path}: {exc}')
        print(backups)


class AdvancedSettings:
    """
    Settings from advancedsettings.xml.

    >>> advanced_settings.get('network', 'disablehttp2')
    >>> # True

    >>> advanced_settings.get('videodatabase', 'type')
    >>> # 'mysql',

    >>> advanced_settings.get('videodatabase')
    >>> # {
    ... #   'type': 'mysql',
    ... #   'host': '127.0.0.1',
    ... #   'port': 3306,
    ... #   'user': 'kodi',
    ... #   'pass': 'secret123',
    >>> # }
    """

    def __init__(self) -> None:
        #: Access lock
        self.lock = Lock()
        # advancedsettings.xml data
        self._data: Optional[Dict[str, Any]] = None

    def _load(self) -> Dict[str, Any]:
        from ..service import SERVICE
        if SERVICE:
            from xml.etree import ElementTree as ET
            from .log_utils import fflog, fflog_exc
            path = Path(xbmcvfs.translatePath("special://userdata")) / 'advancedsettings.xml'
            try:
                tree = ET.parse(str(path))
                root = tree.getroot()
                if root.tag != 'advancedsettings':
                    fflog(f'Incorrect advancedsettings in {path}')
                    return {}
            except OSError:
                return {}  # no file
            except Exception:
                fflog_exc()
                return {}
        else:
            from ..service.client import service_client
            return service_client.advanced_settings()

        def scan(elem: ET.Element) -> Tuple[str, Any]:
            if not len(elem):
                if elem.tag == 'pass':
                    return elem.tag, elem.text
                value = elem.text or ''
                if value.lower() == 'false':
                    value = False
                elif value.lower() == 'true':
                    value = True
                elif value.isdigit():
                    value = int(value)
                return elem.tag, value
            return elem.tag, dict(scan(el) for el in elem)

        if not len(root):  # empty <advancedsettings/>
            return {}
        return scan(root)[1]

    def get(self, *keys: str, default: Any = None) -> Any:
        """Get advanced setting by list of keys."""
        with self.lock:
            if self._data is None:
                self._data = self._load()
            data = self._data
        for key in keys:
            try:
                data = data[key]
            except KeyError:
                return default
        return deepcopy(data)

    def reset(self) -> None:
        """Reset setting access. Remove addon and recreate it again."""
        with self.lock:
            self._data = None


settings = _settings = SettingsManager(k19log=True)

advanced_settings = AdvancedSettings()


def __getattr__(key: str) -> Union[GetCallable, SetCallable]:
    """Return settings function on module level."""
    if key.startswith('get') or key.startswith('set'):
        return getattr(settings, key)
    raise AttributeError(f'Module settings has no attribute {key!r}')


class SettingsFormatter(Formatter):

    FORMATS: dict[str, MethodGetName] = {
        '': 'getBool',
        'bool': 'getBool',
        'str': 'getString',
        'int': 'getInt',
        'float': 'getNumber',
    }

    def __init__(self, settings: SettingsManager | None = None):
        super().__init__()
        if settings is None:
            settings = _settings
        self.settings = settings

    def get_field(self, field_name: str, args, kwargs):  # -> Tuple[Any, Any]:
        try:
            return super().get_field(field_name, args, kwargs)
        except (KeyError, AttributeError, IndexError):
            pass
        return field_name, ()

    def format_field(self, value: Any, format_spec: str) -> str:
        if format_spec:
            getter_name = self.FORMATS[format_spec]
            getter = getattr(self.settings, getter_name)
        else:
            getter = self.settings.get_settings_getter(value)
        return repr(getter(value))


if __name__ == '__main__':
    from .cmdline import DebugArgumentParser
    from .. import service
    service.SERVICE = True  # to allow advanced settings read directly
    p = DebugArgumentParser()
    p.add_argument('-a', '--advanced', action='store_true', help='read advanced settigns')
    p.add_argument('-A', '--all', action='store_true', help='show all settigns')
    p.add_argument('--defs', action='store_true', help='print settigns definitions')
    p.add_argument('name', nargs='*', help='setting name')
    args = p.parse_args()

    if args.defs:
        width = max((len(name) for name in settings.definitions), default=0) + 1
        for name, sdef in settings.definitions.items():
            name = f'{name}:'
            print(f'{name:<{width}} {sdef}')
    elif args.all:
        if args.advanced:
            def show(d: dict[str, Any], path: Sequence[str] = ()) -> None:
                for k, v in d.items():
                    if isinstance(v, dict):
                        show(v, (*path, k))
                    else:
                        name = '.'.join((*path, k))
                        print(f'{name} = {v!r} ({type(v).__name__})')
            val = advanced_settings.get()
            show(val)
        else:
            for name in settings.definitions:
                val = settings.get(name)
                print(f'{name} = {val!r} ({type(val).__name__})')
    else:
        for name in args.name:
            if args.advanced:
                val = advanced_settings.get(name.split('.'))
            else:
                val = settings.get(name)
            print(f'{name} = {val!r} ({type(val).__name__})')
