"""
    FanFilm Add-on
    Copyright (C) 2017 FanFilm

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
import re
from pathlib import Path
from pkgutil import walk_packages
from typing import Union, Any, Sequence, Iterator, Iterable, Callable, ClassVar, overload, TYPE_CHECKING
from typing_extensions import Literal, Protocol, TypedDict, NotRequired, Unpack, ParamSpec, TypeVar, Self
from functools import wraps
from attrs import frozen, define, field, evolve, asdict, fields, filters
from ..ff.log_utils import log, fflog_exc, log_submodule
from ..ff.debug.timing import logtime  # TODO: remove, only for testing
from cdefs import SourcePattern, SourceAttribute, PlayMode, SourceAction
from const import const
if TYPE_CHECKING:
    from typing_extensions import KeysView, Pattern
    from types import ModuleType
    from attrs import Attribute
    from ..ff.item import FFItem
    from ..ff.types import JsonData


T = TypeVar('T')
R = TypeVar('R')
P = ParamSpec('P')


# Część wspólna opcjonalnych danych.
# Opcjonalne zarówno w tym co zwraca provider jak i w elemencie źródła.
class SourceOptionalData(TypedDict):
    size: NotRequired[str]
    filename: NotRequired[str]
    color_identify: NotRequired[str]
    icon: NotRequired[str]
    debridonly: NotRequired[bool]
    direct: NotRequired[bool]
    # True, if file is on local (or locally mounted) storage. Set by provider.
    local: NotRequired[bool]
    premium: NotRequired[bool]
    on_account: NotRequired[bool]
    on_account_link: NotRequired[str]
    on_account_expires: NotRequired[str]
    no_transfer: NotRequired[bool]
    # --- DEBUG ---
    fake: NotRequired[bool]
    resolve_to: NotRequired[Union[None, str, Path]]


# Opis typu elementu opisu pozycji zgłaszanej przez scaper, de facto słownika
class SourceItem(SourceOptionalData):
    # source is de fact hosting name
    source: NotRequired[str]  # TODO: rename it to "hosting"
    info: NotRequired[str]
    info2: NotRequired[str]
    url: str
    language: NotRequired[str]
    quality: NotRequired[str]
    debrid: NotRequired[str]


# Opis typu elementu opisu pozycji, de facto słownika
class SourceMeta(SourceOptionalData):
    provider: str
    hosting: str  # old "source" from providers' source items
    label: str
    info: str
    info2: str
    url: str
    language: str
    quality: str
    debrid: str


# Dodatkowe argumenty, które mogą spaść z okna ze żródłami jako `for_resolve`.
class SourceResolveKwargs(TypedDict):
    buy_anyway: NotRequired[bool]


# Because Python is still missing Introsection or KeyType we haveto copy all SourceMeta keys explicite.
SourceMetaRequiredKey = Literal['provider', 'hosting', 'label', 'info', 'url', 'language', 'quality', 'debrid']
SourceMetaOptionalStrKey = Literal['size', 'filename', 'color_identify', 'icon', 'info2', 'on_account_link', 'on_account_expires', 'resolve_to', 'no_transfer']
SourceMetaOptionalBoolKey = Literal['debridonly', 'direct', 'local', 'premium', 'on_account', 'fake']
SourceMetaOptionalKey = Union[SourceMetaOptionalStrKey, SourceMetaOptionalBoolKey]
SourceMetaKey = Union[SourceMetaRequiredKey, SourceMetaOptionalKey]


@define(kw_only=True)
class Source:
    url: str
    provider: str
    hosting: str
    ffitem: FFItem
    attr: SourceAttribute = field(factory=SourceAttribute)
    meta: SourceMeta = field(factory=lambda: {k: '' for k in SourceMeta.__annotations__.keys() - SourceOptionalData.__annotations__.keys()})  # type: ignore
    resolved: bool = False

    RX_M38U: ClassVar[Pattern[str]] = re.compile(r'^https?://.*\.m3u8\b')
    RX_NOT_M38U: ClassVar[Pattern[str]] = re.compile(r'\.(?:avi|mkv|mp4|ts|mpg)\b')

    def attr_update(self) -> bool:
        """Find mathing rule, return True if changed."""
        from ..ff.kotools import get_platform
        from ..ff.settings import settings

        def pat_match(pat: SourcePattern) -> bool:
            if pat.provider and pat.provider != self.provider:
                return False
            if pat.hosting and pat.hosting != self.hosting:
                return False
            if pat.platform and pat.platform != platform:
                return False
            if pat.m3u8 is not None and ((m3u8 := self.is_m3u8()) is None or pat.m3u8 != m3u8):
                return False
            if pat.setting and not settings.eval(pat.setting):
                return False
            return True

        # old attrs
        attr = asdict(self.attr)
        # data for mathing
        platform = get_platform()
        # lookup
        changed = False
        ff: Sequence[Attribute] = fields(SourceAttribute)
        for pat, new in const.sources.rules.items():
            if pat_match(pat):
                for f in ff:
                    val = getattr(new, f.name)
                    if val is not None and getattr(self.attr, f.name) is None and val != attr[f.name]:
                        attr[f.name] = val
                        changed = True
        if changed:
            self.attr = SourceAttribute(**attr)
        return changed

    @property
    def resolved_url(self) -> str:
        """Return URL after resolve or empty string."""
        return self.url if self.resolved else ''

    def is_m3u8(self) -> bool | None:
        """Determine if is m3u8 file. Return None if unknown."""
        # stream URL is known
        if self.resolved:
            return bool(self.RX_M38U.search(self.url))
        # link is not resolved, the name could be ok or not, then...
        # ... it's m3u8
        if self.RX_M38U.search(self.url):
            return True
        # ... it's another file
        if self.RX_NOT_M38U.search(self.url):
            return False
        # ... we ca not determine
        return None

    def set_play_mode(self, play: PlayMode) -> None:
        self.attr = evolve(self.attr, play=play)

    def menu_actions(self) -> Iterator[SourceAction]:
        """Iterate over avaliable contex-menu actions (like play-modes). Action `play` is replaced with `direct or `isa`."""
        actions = self.attr.menu
        if actions is None:
            actions = ('play', )
        for act in actions:
            if act == 'play':
                if self.attr.play != 'direct':
                    yield 'direct'
                # ISA is not a default and m3u8 is not false (means is true or none/unknown)
                if self.attr.play != 'isa' and self.is_m3u8() is not False:
                    yield 'isa'
            else:
                yield act

    def as_json(self) -> JsonData:
        """Return JSON data without FFItem."""
        return asdict(self, recurse=True, filter=filters.exclude('ffitem'))

    @classmethod
    def from_json(cls, data: JsonData, *, ffitem: FFItem) -> Self:
        """Return source from JSON data with FFItem."""
        data = dict(data)
        attr = SourceAttribute(**data.pop('attr'))
        return cls(ffitem=ffitem, attr=attr, **data)

    @classmethod
    def from_provider_dict(cls, *, provider: str, ffitem: FFItem, item: SourceItem) -> Self:
        """Create instance from provider's meta-item-dict."""
        meta: SourceMeta = dict(item)
        url = item.get('url', '')
        # hosting = item.get('hosting', '') or item.get('source', '').rpartition('.')[0].lower()
        hosting = item.get('hosting', '') or item.get('source', '').lower()
        attr = SourceAttribute()
        return cls(url=url, provider=provider, hosting=hosting, ffitem=ffitem, attr=attr, meta=meta)

    @classmethod
    def from_meta(cls, *, ffitem: FFItem, meta: SourceMeta) -> Self:
        """Create instance from already udpated meta-dict. Useful for const prepend and append."""
        attr = SourceAttribute()
        url = meta.get('url', '')
        provider = meta.get('provider', '')
        hosting = meta.get('hosting', '') or meta.get('source', '').lower()
        src = cls(url=url, provider=provider, hosting=hosting, ffitem=ffitem, attr=attr, meta=meta)
        src.attr_update()
        return src

    @classmethod
    def action_label(cls, action: SourceAction) -> str:
        from ..kolang import L
        if action == 'direct':
            return L(30311, 'Play direct')
        elif action == 'isa':
            return L(30310, 'Play via InputStream')
        elif action == 'buy':
            return L(30116, 'Buy it again')
        return ''

    # --- dict-like infterface (readonly) ---

    def __contains__(self, key: Any) -> bool:
        return key in self.meta

    def __getitem__(self, key: SourceMetaRequiredKey) -> str:
        if key == 'provider':
            return self.provider
        if key == 'hosting':
            return self.hosting
        return self.meta[key]

    @overload
    def get(self, key: SourceMetaRequiredKey, default: Any = None) -> str: ...

    @overload
    def get(self, key: SourceMetaOptionalStrKey, default: T = None) -> Union[str, T]: ...

    @overload
    def get(self, key: SourceMetaOptionalBoolKey, default: T = None) -> Union[bool, T]: ...

    @overload
    def get(self, key: Any, default: T = None) -> T: ...

    def get(self, key: Any, default: T = None) -> Union[str, bool, T]:
        if key == 'hosting':
            return self.hosting
        return self.meta.get(key, default)

    def keys(self) -> KeysView[str]:
        return self.meta.keys()

    def values(self):  # -> ValuesView[Union[int, bool]]:
        return self.meta.values()

    def items(self):  # -> ItemsView[str, Union[int, bool]]:
        return self.meta.items()

    # --- dict-like infterface (write) ---  TODO: think it's really necesery

    @overload
    def __setitem__(self, key: Union[SourceMetaRequiredKey, SourceMetaOptionalStrKey], value: str) -> None: ...

    @overload
    def __setitem__(self, key: SourceMetaOptionalBoolKey, value: bool) -> None: ...

    def __setitem__(self, key: str, value: Union[str, bool]) -> None:
        if key == 'provider':
            log.error(f'Set Source[{key:r}] is not allowed')
        self.meta[key] = value

    def update(self, data: dict[SourceMetaKey, Any], /):
        if wrong := ({'provider'} & data.keys()):
            log.error(f'Source.update() for {", ".join(map(repr, wrong))} is not allowed')
        self.meta.update(data)  # type: ignore[reportCallIssue]  # there is no Partial[SourceMeta] yet


#: "class source" type.
class ProviderProtocol(Protocol):
    """Source provider class protocol (api)."""

    #: True, if __init__ accepts ffitem.
    INIT_WITH_FFITEM: ClassVar[bool] = False

    # -- old "sources" api (still used) ---
    priority: ClassVar[int] = 1
    language: ClassVar[Sequence[str]] = ()
    # "domains" is not used

    # --- those settings are parsed but not requiered, see Provider class ---
    # has_sort_order: ClassVar[bool] = False
    # has_color_identify2: ClassVar[bool] = False
    # has_library_color_identify2: bool = False
    # use_premium_color: ClassVar[bool] = False

    # --- provider instance data, set in sources.py ---
    canceled: bool
    ffitem: FFItem   # set in ff/sources.py at that moment

    # def __init__(self, *, ffitem: FFItem) -> None: ...

    def movie(self, imdb: str, title: str, localtitle: str, aliases: str, year: str) -> str | None: ...

    def episode(self, url: str, imdb: str, tvdb: str, title: str, premiered: str, season: str, episode: str) -> str | None: ...

    def tvshow(self, imdb: str, tvdb: str, tvshowtitle: str, localtvshowtitle: str, aliases: str, year: str) -> Any: ...

    def sources(self, url: str, host_list: Sequence[str], pr_host_list: Sequence[str], /, from_cache: bool = False) -> Sequence[SourceItem]: ...

    def resolve(self, url: str, **kwargs: Unpack[SourceResolveKwargs]) -> str: ...


class Provider:
    """Base provider class."""

    #: True, if __init__ accepts ffitem.
    INIT_WITH_FFITEM: ClassVar[bool] = True

    #: This class has support for *.sort.order setting
    has_sort_order: ClassVar[bool] = False
    #: This class has support for *.color.identify2 setting
    has_color_identify2: ClassVar[bool] = False
    # This class has support for *.library.color.identify2 setting
    has_library_color_identify2: bool = False
    #: Mark sources with prem.color.identify2 setting
    use_premium_color: ClassVar[bool] = False

    # -- old "sources" api (still used) ---
    priority: ClassVar[int] = 1
    language: ClassVar[Sequence[str]] = ()
    # domains: ClassVar[Sequence[str]] = ()  # ???  (used only a few times)

    # --- provider instance data, set in sources.py ---
    ffitem: FFItem   # set in ff/sources.py at that moment
    canceled: bool

    def __init__(self, *, ffitem: FFItem) -> None:
        self.ffitem = ffitem
        self.canceled = False


@frozen
class SourceModule:
    """Tuple from load source/*/* modules, provider proxy."""
    #: Module name.
    name: str
    #: Module source object.
    provider: ProviderProtocol
    #: Group of the sources (eg. language like "en", "pl").
    group: str = ''


@frozen
class SourcePythonModule:
    """Python module from load source/*/*."""
    #: Module name.
    name: str
    #: Module python object.
    module: ModuleType
    #: Group of the sources (eg. language like "en", "pl").
    group: str = ''

    def load_providers(self, *, ffitem: FFItem) -> Iterable[SourceModule]:
        """Load providers form python module."""
        with logtime(name=f'Create providers from {self.name}'):
            try:
                if register := getattr(self.module, 'register', None):
                    sources: list[SourceModule] = []
                    register(sources, group=self.group)
                    yield from sources
                else:
                    provider_class = self.module.source
                    if getattr(provider_class, 'INIT_WITH_FFITEM', False):
                        provider = provider_class(ffitem=ffitem)
                    else:
                        provider = provider_class()
                        provider.ffitem = ffitem
                    yield SourceModule(name=self.name, provider=provider, group=self.group)
            except Exception as e:
                log.warning(f'Provider creating Error - {self.name!r}: {e}')
                fflog_exc()


def scan_source_modules(*, ffitem: FFItem) -> list[SourceModule]:
    """Scan source/*/*.py and load modules."""
    global _source_modules
    if _source_modules is None:
        _source_modules = []
        path = Path(__file__).parent.resolve()
        # NOTE, map(str,…) for workaround py3.10 bug
        for info in walk_packages(map(str, path.glob("[!_.]*"))):
            if not info.ispkg:
                with log_submodule(f'loading:{info.name}'):
                    with logtime(name=f'Load module {info.name}'):
                        try:
                            spec = info.module_finder.find_spec(info.name, None)
                            if spec is not None and spec.loader is not None:
                                group = str(Path(info.module_finder.path).relative_to(path))
                                module = spec.loader.load_module(info.name)
                                _source_modules.append(SourcePythonModule(name=info.name, module=module, group=group))
                        except Exception as e:
                            log.warning(f'Provider loading Error - {info.name!r}: {e}')
                            fflog_exc()
    return [src for mod in _source_modules for src in mod.load_providers(ffitem=ffitem)]


def clear_source_modules() -> None:
    """Clean source modules, destroy provider objects."""


def class_single_call(method: Callable[P, R], /) -> Callable[P, R]:
    """Decorator for single call method. Once per class not per instance!"""
    @wraps(method)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        nonlocal result
        if result is ...:
            result = method(*args, **kwargs)
        return result
    result = ...
    return wrapped


def single_call(method: Callable[P, R], /) -> Callable[P, R]:
    """Decorator for single call a method, ex. init(), per instance."""
    @wraps(method)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        if not args:
            return method(*args, **kwargs)
        self = args[0]
        key = f'_single_call_result_{method.__name__}'
        result = getattr(self, key, ...)
        if result is ...:
            result = method(*args, **kwargs)
            setattr(self, key, result)
        return result
    return wrapped


_source_modules: list[SourcePythonModule] | None = None
