"""Common module for all kind of lists."""

from __future__ import annotations
from typing import Sequence, TYPE_CHECKING
from typing_extensions import TypedDict, NotRequired, Literal, TypeAlias
from pathlib import Path
from attrs import frozen, define, field
from .item import FFItem
from ..defs import FFRef, RefType
from ..ff import control
from ..ff.log_utils import fflog
from ..kolang import L
from cdefs import ListType, ListTarget, ListPointer, ShowCxtMenu
from const import const
if TYPE_CHECKING:
    from typing import Iterator, Iterable, ClassVar
    # from ..api.tmdb import UserGeneralListType


# class AddToServices(TypedDict, extra_items=Sequence[ListPointer]):
#     """All services and theirs list settings. Keys are ListService (defined pointers) or any (any pointers)."""
#     local: NotRequired[Sequence[Literal['library', 'own:favorites', 'own:watchlist', 'own:user', 'logs']]]
#     own: NotRequired[Sequence[Literal['own:favorites', 'own:watchlist', 'own:user']]]
#     trakt: NotRequired[Sequence[Literal['trakt:favorites', 'trakt:watchlist', 'trakt:collection', 'trakt:user']]]
#     tmdb: NotRequired[Sequence[Literal['tmdb:favorites', 'tmdb:watchlist', 'tmdb:user']]]
#     library: NotRequired[Sequence[Literal['library']]]
#     logs: NotRequired[Sequence[Literal['logs']]]


AddToServiceDefs: TypeAlias = 'dict[str, Sequence[ListPointer]]'
"""All services and theirs lists pointers. Keys are L() translated service names, values are available pointers for this service."""

AddToServices: TypeAlias = 'dict[str, Sequence[ServiceDescr]]'
"""All services and theirs lists descriptions. Keys are L() translated service names, values are available pointers for this service."""


class ListConvertRules(TypedDict):
    """
    Rules for convert refs. Missing key means 'ignore'.

    Dialog "add to…" can filter out those options by const.dialog.add_to.allowed_conversions.
    """

    show: NotRequired[Literal['ignore', 'season', 'episode']]
    season: NotRequired[Literal['ignore', 'show', 'episode']]
    episode: NotRequired[Literal['ignore', 'show', 'season']]
    collection: NotRequired[Literal['ignore', 'movie']]
    movie: NotRequired[Literal['ignore', 'collection']]


#: All available media conversions. Build from ListConvertRules. Can be filter-out by const.dialog.add_to.allowed_conversions.
AVALIABLE_CONVERSITION: dict[RefType, ListType] = {
    'collection': ListType.MOVIE,
    'movie': ListType.COLLECTION,
    'show': ListType.SEASON | ListType.EPISODE,
    'season': ListType.SHOW | ListType.EPISODE,
    'episode': ListType.SHOW | ListType.SEASON,
}


class AddToListCreateOptions(TypedDict):
    """Options for new list creation."""

    public: NotRequired[bool]


AddToListRemoveOptionsNames = Literal['items', 'lists']


class AddToListRemoveOptions(TypedDict):
    """Options for removing (items and lists)."""

    items: NotRequired[bool]  # default True
    lists: NotRequired[bool]  # default False


def converted_types(types: ListType = ListType.ALL) -> ListType:
    """Return real enabled conversions for `types`."""
    ref_types: set[RefType] = AVALIABLE_CONVERSITION.keys() & const.dialog.add_to.allowed_conversions.keys()
    allowed = ListType.NONE
    for ref_type in ref_types:
        if ListType.from_media_ref(ref_type) & types:
            allowed |= AVALIABLE_CONVERSITION[ref_type] & const.dialog.add_to.allowed_conversions[ref_type]
    return allowed


def convert_refs(refs: Iterable[FFRef], *, allowed: ListType, rules: ListConvertRules | str | None = None) -> Sequence[FFRef]:
    """
    Convert refs to allowed types with `convert` rules.

    Rules could be as string, ex.: 'collection:movie,show:episode'.
    """
    # TODO: split process into steps:
    #       1. scan for conversion and collect all items to need to be expanded
    #       2  get extra needed info from TMDB (in parallel)
    #       3. convert all items in order using collected data

    def convert(it: FFRef) -> Iterator[FFRef]:
        ref = it.ref
        real_type = ref.real_type
        typ = ListType.from_media_ref(real_type)
        if typ & allowed:
            yield it
        elif real_type == 'movie':
            if _rules.get('movie') == 'collection':
                ...  # Oh no! I have no collection here!
        elif real_type == 'show':
            if (rule := _rules.get('show')) == 'season':
                ...  # Oh no! I have no seasons here (no show content)!
            elif rule == 'episode':
                ...  # Oh no! I have no episodes here (no show content)!
        elif real_type == 'season':
            if (rule := _rules.get('season')) == 'show':
                if TYPE_CHECKING:
                    assert ref.show_ref
                yield ref.show_ref
            elif rule == 'episode':
                ...  # Oh no! I have no episodes here (no season content)!
        elif real_type == 'episode':
            if (rule := _rules.get('episode')) == 'show':
                if TYPE_CHECKING:
                    assert ref.show_ref
                yield ref.show_ref
            elif rule == 'season':
                if TYPE_CHECKING:
                    assert ref.season_ref
                yield ref.season_ref
        elif real_type == 'collection':
            if _rules.get('collection') == 'movie':
                ...  # Oh no! I have no movies here (no collection content)!

    # parse rules if string
    _rules: ListConvertRules
    if rules is None:
        _rules = {}
    elif isinstance(rules, str):
        _rules = {k: v for rr in (convert or '').split(',') for k, _, v in (rr.partition(':'),) if k and v}  # type: ignore[reportAssignmentType]
    else:
        _rules = rules

    # filter rules by allowed types, keys and values (except "ignore") are valid ListType type names
    _rules = {k: v for k, v in _rules.items() if ListType.from_media_ref(v) & allowed}  # type: ignore[reportAssignmentType]

    # convert
    return [x for ref in refs for x in convert(ref)]


@frozen
class ServiceDescr:
    """Service description for any list item add, including "add to" dialog."""

    #: Service pointer (name and optional section).
    pointer: ListPointer
    #: Options for new list creation, if supported by this service.
    #: If not None (even empty dict), then this service supports creating new lists.
    new_list_options: AddToListCreateOptions | None = field(default=None, kw_only=True)
    #: Supported list types for this service instance (pointer).
    types: ListType = field(default=ListType.NONE, kw_only=True)
    #: Supported new list types (default settings in new window).
    new_types: ListType = field(default=ListType.NONE, kw_only=True)
    #: Supported new list types, enbeld to change.
    edit_types: ListType = field(default=ListType.NONE, kw_only=True)
    #: Group names for all list pointers. Diffrent groups are separated (horizontal line) in Add-to dialog.
    group: str = field(default='', kw_only=True)
    #: When the pointer (service & section) is enabled in Add-to dialog.
    enabled: ShowCxtMenu = field(default=True, kw_only=True)
    #: Remove options (can remove itms and/or lists).
    remove_options: AddToListRemoveOptions | None = field(default=None, kw_only=True)

    #: Default list types for this service, used if `types` is not set.
    DEFAULT_TYPES: ClassVar[ListType] = ListType.MAIN

    def __attrs_post_init__(self) -> None:
        if not self.types:
            object.__setattr__(self, 'types',  self.DEFAULT_TYPES)

    def is_enabled(self) -> bool:
        """Return True if this service is enabled in Add-to dialog."""
        from .settings import settings
        if isinstance(self.enabled, bool):
            return self.enabled
        return settings.eval(self.enabled)

    def lists(self) -> Sequence[FFItem]:
        """Return list FFItem items for `pointer` to show lists in a dialog."""
        def proc(it: FFItem) -> FFItem:
            if types := it.getProperty('list_type'):
                types = ListType.new(types)
            else:
                types = self.DEFAULT_TYPES
                it.setProperty('list_type', str(types))
            for typ in ListType.iter_single_flags():
                it.setProperty(f'type.{typ.attr}', 'true' if typ & types else 'false')
            # if not it.getProperty('service_description'):
            #     it.setProperty('service_description', self.__class__.__name__)
            if not it.getProperty('service'):
                it.setProperty('service', service)
            if not it.getProperty('section'):
                it.setProperty('section', section)
            if not it.getProperty('pointer'):
                it.setProperty('pointer', pointer)
            if not it.getProperty('group'):
                it.setProperty('group', lst.group if lst else '')
            return it

        pointer: ListPointer = self.pointer
        lst = LIST_POINTERS.get(pointer)
        service, _, section = pointer.partition(':')
        return tuple(proc(it) for it in self._lists(pointer))

    # Override this method in subclass.
    def _lists(self, pointer: ListPointer) -> Iterable[FFItem]:
        if False:  # force generator
            yield

    def create_enabled(self) -> bool:
        """Return True if this service supports creating new lists."""
        return self.new_list_options is not None

    def create(self, name: str, *, type: ListType = ListType.MEDIA, public: bool = False) -> bool:
        """Create new list in this service."""
        return False

    # Override this method in subclass.
    def _add_items(self, target: ListTarget, items: Iterable[FFRef]) -> int | None:
        return None

    # Override this method in subclass.
    def _remove_items(self, target: ListTarget, items: Iterable[FFRef]) -> int | None:
        return None

    # Override this method in subclass.
    def _remove_list(self, target: ListTarget) -> int | None:
        return None

    def add_items(self, target: ListTarget, items: Iterable[FFRef], *, quiet: bool = True) -> int | None:
        """
        Add items to this service.

        :param  target: target list to add items_str
        :param items: items to add
        :return: number of added items or None if not supported
        """
        return self._add_items(target, items)

    def add_folder_items(self, folder: FFItem, items: Iterable[FFRef]) -> int | None:
        """
        Add items to this service.

        :param  name: list name or location (e.g. 'favorites', 'watchlist')
        :param items: items to add
        :return: number of added items or None if not supported
        """
        return self._add_items(ListTarget.from_ffitem(folder), items)

    def has_remove_option(self, option: AddToListRemoveOptionsNames, target: ListTarget) -> bool:
        """
        Return True if this service supports removing items or lists.

        :param option: 'items' or 'lists'
        :return: True if supported, False otherwise
        """
        # special case, default True
        if option == 'items':
            return self.item_remove_enabled(target)
        # rest options are False by default
        if self.remove_options is None:
            return False
        return self.remove_options.get(option, False)

    def item_remove_enabled(self, target: ListTarget) -> bool:
        """Return True if this service supports removing items."""
        return self.remove_options is None or self.remove_options.get('items', True)
        # return self.remove_options is not None and self.remove_options.get('items', False)

    def remove_items(self, target: ListTarget, items: Iterable[FFRef], *, quiet: bool = True) -> int | None:
        """
        Remove items from this service.

        :param  target: target list to add items_str
        :param items: items to remove
        :return: number of added items or None if not supported
        """
        return self._remove_items(target, items)

    def list_remove_enabled(self, target: ListTarget) -> bool:
        """Return True if this service supports removing lists."""
        return self.remove_options is not None and self.remove_options.get('lists', False)

    def remove_list(self, target: ListTarget, *, quiet: bool = True) -> int | None:
        """
        Remove (delete) items from this service.

        :param  target: target list to add items_str
        :param items: items to remove
        :return: number of added items or None if not supported
        """
        return self._remove_list(target)


class LibraryServiceDescr(ServiceDescr):

    DEFAULT_TYPES: ClassVar[ListType] = ListType.MAIN

    def _lists(self, pointer: ListPointer) -> Iterable[FFItem]:
        if pointer == 'library':
            yield FFItem(L(32541, 'Library'), properties={'list_type': format(ListType.MAIN), 'service': 'library'})

    def _add_items(self, target: ListTarget, items: Iterable[FFRef]) -> int | None:
        from ..service.client import service_client
        allowed = {'movie', 'show', 'season', 'episode'}
        items = tuple(it for it in items if it.ref.real_type in allowed)
        service_client.library_add(items, name=target.list or None, quiet=True)
        return len(items)


class LogsServiceDescr(ServiceDescr):

    DEFAULT_TYPES: ClassVar[ListType] = ListType.ALL

    def _lists(self, pointer: ListPointer) -> Iterable[FFItem]:
        if pointer == 'logs':
            yield FFItem(L(30359, 'Logs'), properties={'list_type': format(ListType.ALL)})

    def _add_items(self, target: ListTarget, items: Iterable[FFRef]) -> int | None:
        def dump_item(ref: FFRef) -> str:
            return f'  {ref}'
        items = tuple(items)
        items_str = '\n'.join(dump_item(it) for it in items)
        fflog.info(f'ADDING TO LOG... {len(items)} item(s):\n{items_str}')
        return len(items)


@frozen
class OwnServiceDescr(ServiceDescr):

    DEFAULT_TYPES: ClassVar[ListType] = ListType.MIXED

    def _lists(self, pointer: ListPointer) -> Iterable[FFItem]:
        from ..ff.ownlists import own_db
        art = {'thumb': art_path('userlists.png')}
        if pointer == 'own:favorites':
            if folder := own_db.folder(own_db.FAVORITES):
                yield FFItem(L(30348, 'Own Favorites'), properties={'list_type': format(folder.type), 'list_id': ':favorites'}, art=art)
        elif pointer == 'own:watchlist':
            if folder := own_db.folder(own_db.WATCHLIST):
                yield FFItem(L(30347, 'Own Watchlist'), properties={'list_type': format(folder.type), 'list_id': ':watchlist'}, art=art)
        elif pointer == 'own:user':
            if root := own_db.root():
                for ent in root.entries:
                    if name := ent.subfolder_name:
                        if TYPE_CHECKING:
                            assert ent.subfolder is not None
                        yield FFItem(name, properties={'list_type': format(ent.subfolder.type)}, art=art)

    def create(self, name: str, *, type: ListType = ListType.MIXED, public: bool = False) -> bool:
        from ..ff.ownlists import own_db
        try:
            own_db.create_list(name, type=type)
            return True
        except Exception:
            return False

    def _list(self, target: ListTarget) -> str | None:
        from ..ff.ownlists import own_db
        list_names = {
            'favorites': own_db.FAVORITES,
            'watchlist': own_db.WATCHLIST,
            'collection': own_db.COLLECTION,
            'user': target.list,
        }
        return list_names.get(target.section)

    def _add_items(self, target: ListTarget, items: Iterable[FFRef]) -> int | None:
        from ..ff.ownlists import own_db
        if list_id := self._list(target):
            return own_db.list_add(list_id, items)
        return None  # not supported

        # if target.section == 'favorites':
        #     list_id = own_db.FAVORITES
        # elif target.section == 'watchlist':
        #     list_id = own_db.WATCHLIST
        # elif target.section == 'user':
        #     list_id = target.list
        # else:
        #     return None  # not supported
        # return own_db.list_add(list_id, items)

    def _remove_list(self, target: ListTarget) -> int | None:
        from ..ff.ownlists import own_db
        if list_id := self._list(target):
            return own_db.delete_list(list_id)
        return None  # not supported

    def _remove_items(self, target: ListTarget, items: Iterable[FFRef]) -> int | None:
        from ..ff.ownlists import own_db
        if list_id := self._list(target):
            return own_db.remove_items(list_id, items)
        return None  # not supported


@frozen
class TmdbServiceDescr(ServiceDescr):

    DEFAULT_TYPES: ClassVar[ListType] = ListType.MAIN

    def _lists(self, pointer: ListPointer) -> Iterable[FFItem]:
        from ..ff.tmdb import tmdb
        list_type = str(ListType.MAIN)
        art = {'thumb': art_path('tmdb.png')}
        if pointer == 'tmdb:favorites':
            yield FFItem(L(32803, 'TMDB Favorites'), properties={'list_type': list_type, 'list_id': 'favorite'}, art=art)
        elif pointer == 'tmdb:watchlist':
            yield FFItem(L(32802, 'TMDB Watchlist'), properties={'list_type': list_type, 'list_id': 'watchlist'}, art=art)
        elif pointer == 'tmdb:user':
            for it in sorted(tmdb.user_lists(), key=lambda it: it.label.lower()):
                it.setProperty('list_type', list_type)
                it.setArt(art)
                yield it

    def create(self, name: str, *, type: ListType = ListType.MAIN, public: bool = False) -> bool:
        from ..ff.tmdb import tmdb
        return bool(tmdb.create_user_list(name, public=public))

    def _add_items(self, target: ListTarget, items: Iterable[FFRef]) -> int | None:
        from ..ff.tmdb import tmdb
        if target.section == 'favorites':
            return tmdb.add_items_to_general_list('favorite', items)
        if target.section == 'watchlist':
            return tmdb.add_items_to_general_list('watchlist', items)
        if target.section == 'user' and target.list.isdecimal():
            return tmdb.add_to_user_list(int(target.list), items)
        return None  # not supported

    def _remove_list(self, target: ListTarget) -> int | None:
        from ..ff.tmdb import tmdb
        if target.section == 'user' and target.list.isdecimal():
            return tmdb.delete_user_list(int(target.list))

    def _remove_items(self, target: ListTarget, items: Iterable[FFRef]) -> int | None:
        from ..ff.tmdb import tmdb
        if target.section == 'favorites':
            return tmdb.remove_items_from_general_list('favorite', items)
        if target.section == 'watchlist':
            return tmdb.remove_items_from_general_list('favorite', items)
        if target.section == 'user' and target.list.isdecimal():
            return tmdb.remove_from_user_list(int(target.list), items)
        return None  # not supported


@frozen
class TraktServiceDescr(ServiceDescr):

    DEFAULT_TYPES: ClassVar[ListType] = ListType.MEDIA | ListType.PERSON

    def _lists(self, pointer: ListPointer) -> Iterable[FFItem]:
        from ..ff.trakt import trakt
        art = {'thumb': art_path('trakt.png')}
        if pointer == 'trakt:favorites':
            yield FFItem(L(30360, 'Trakt Favorites'), properties={'list_type': str(ListType.MAIN)}, art=art)
        elif pointer == 'trakt:watchlist':
            yield FFItem(L(30361, 'Trakt Watchlist'), properties={'list_type': str(ListType.MEDIA)}, art=art)
        elif pointer == 'trakt:collection':
            yield FFItem(L(30362, 'Trakt Collection'), properties={'list_type': str(ListType.MEDIA)}, art=art)
        elif pointer == 'trakt:user':
            for it in sorted(trakt.user_lists(), key=lambda it: it.label.lower()):
                it.setArt(art)
                yield it

    def create(self, name: str, *, type: ListType = ListType.MAIN, public: bool = False) -> bool:
        from ..ff.trakt import trakt
        privacy = 'public' if public else 'private'
        return bool(trakt.create_user_list(name, privacy=privacy))

    def _add_items(self, target: ListTarget, items: Iterable[FFRef]) -> int | None:
        from ..ff.trakt import trakt
        if target.section in ('favorites', 'watchlist', 'collection'):
            ok, num = trakt.add_to_generic_list(target.section, items)
            return num
            # return num if ok else None
        if target.section == 'user':
            ok, num = trakt.add_to_user_list(target.list, items)
            return num
        return None  # not supported

    def _remove_list(self, target: ListTarget) -> int | None:
        from ..ff.trakt import trakt
        if target.section == 'user' and target.list:
            return trakt.delete_user_list(target.list)

    def _remove_items(self, target: ListTarget, items: Iterable[FFRef]) -> int | None:
        from ..ff.trakt import trakt
        if target.section in ('favorites', 'watchlist', 'collection'):
            ok, num = trakt.remove_from_generic_list(target.section, items)
            return num
            # return num if ok else None
        if target.section == 'user':
            ok, num = trakt.remove_from_user_list(target.list, items)
            return num
        return None  # not supported


@frozen
class MdblistServiceDescr(ServiceDescr):

    DEFAULT_TYPES: ClassVar[ListType] = ListType.MAIN

    def _lists(self, pointer: ListPointer) -> Iterable[FFItem]:
        from ..api.mdblist import mdblist
        art = {'thumb': art_path('mdblist.png')}
        if pointer == 'mdblist:watchlist':
            yield FFItem(L(30363, 'MDBList Watchlist'), properties={'list_type': str(ListType.MAIN), 'list_id': 'watchlist'}, art=art)
        elif pointer == 'mdblist:user':
            list_type = str(ListType.MEDIA)
            for it in sorted(mdblist.user_lists(static=True), key=lambda it: it.label.lower()):
                it.setProperty('list_type', list_type)
                it.setArt(art)
                yield it

    # def create(self, name: str, *, type: ListType = ListType.MAIN, public: bool = False) -> bool:
    #     from ..api.mdblist import mdblist
    #     return bool(mdblist.create_user_list(name, public=public))

    def _add_items(self, target: ListTarget, items: Iterable[FFRef]) -> int | None:
        from ..api.mdblist import mdblist
        if target.section == 'watchlist':
            ok, num = mdblist.add_to_watchlist(items)
            return num
        if target.section == 'user' and target.list.isdecimal():
            ok, num = mdblist.add_to_user_list(int(target.list), items)
            return num
        return None  # not supported

    def _remove_items(self, target: ListTarget, items: Iterable[FFRef]) -> int | None:
        from ..api.mdblist import mdblist
        if target.section == 'watchlist':
            ok, num = mdblist.remove_from_watchlist(items)
            return num
        if target.section == 'user' and target.list.isdecimal():
            ok, num = mdblist.remove_from_user_list(int(target.list), items)
            return num
        return None  # not supported


# Define all available list services.
# remove_options: 'items' is True by default, 'lists' is False by default.
LIST_POINTERS: dict[ListPointer, ServiceDescr] = {srv.pointer: srv for srv in (
    ServiceDescr('local'),  # dummy pointer, empty list, do NOT use it
    LibraryServiceDescr('library',           group='library',    enabled='enable_library',
                        remove_options={'items': False}),
    LogsServiceDescr('logs',                 group='logs',       enabled='const.debug.add_to_logs',
                     remove_options={'items': False}),

    OwnServiceDescr('own:favorites',         group='own:generic', enabled='ListsInfo.own_enabled()'),
    OwnServiceDescr('own:watchlist',         group='own:generic', enabled='ListsInfo.own_enabled()'),
    OwnServiceDescr('own:collection',        group='own:generic', enabled='ListsInfo.own_enabled()'),
    OwnServiceDescr('own:user',              group='own:user',    enabled='ListsInfo.own_enabled()',
                    new_list_options={}, edit_types=ListType.ALL, remove_options={'lists': True}),

    TmdbServiceDescr('tmdb:favorites',       group='tmdb:generic',  enabled='ListsInfo.tmdb_enabled()'),
    TmdbServiceDescr('tmdb:watchlist',       group='tmdb:generic',  enabled='ListsInfo.tmdb_enabled()'),
    TmdbServiceDescr('tmdb:user',            group='tmdb:user',     enabled='ListsInfo.tmdb_enabled()',
                     new_list_options={'public': True}, remove_options={'lists': True}),

    TraktServiceDescr('trakt:favorites',     group='trakt:generic', enabled='ListsInfo.trakt_enabled()'),
    TraktServiceDescr('trakt:watchlist',     group='trakt:generic', enabled='ListsInfo.trakt_enabled()'),
    TraktServiceDescr('trakt:collection',    group='trakt:generic', enabled='ListsInfo.trakt_enabled()'),
    TraktServiceDescr('trakt:user',          group='trakt:user',    enabled='ListsInfo.trakt_enabled()',
                      new_list_options={'public': True}, new_types=ListType.MIXED, remove_options={'lists': True}),

    MdblistServiceDescr('mdblist:watchlist', group='mdblist:generic', enabled='ListsInfo.mdblist_enabled(premium=True)'),
    MdblistServiceDescr('mdblist:user',      group='mdblist:user',    enabled='ListsInfo.mdblist_enabled(premium=True)'),  # no create in API !!!
)}

# LIST_SERVICES: dict[AddToListService, ServiceDescr] = {s.name: s for s in (
#     LocalServiceDescr(),
#     TraktServiceDescr(),
#     TmdbServiceDescr(),
#     OwnServiceDescr(),
#     LibraryServiceDescr(),
#     LogsServiceDescr(),
# )}


def art_path(fname: str) -> str:
    return str(Path(control.art_path) / fname)
