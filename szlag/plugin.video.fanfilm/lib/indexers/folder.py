
from typing import Optional, Union, Any, Tuple, Dict, Sequence, Iterator, Iterable, Callable, Type, TypeVar, ClassVar, overload, cast, TYPE_CHECKING
from typing_extensions import Concatenate, ParamSpec, Protocol, TypedDict, NotRequired, Unpack, Literal, Generic
from sys import maxsize
from inspect import signature, Signature, Parameter, ismethod
from functools import wraps
from itertools import chain
from contextlib import contextmanager
from enum import Enum, auto as auto_enum
from attrs import define, frozen, field, fields, asdict, evolve
from ..defs import Pagina, ItemList, FFRef, MediaRef, MediaRefWithNoType
from ..ff.item import FFItem
from ..ff.routing import main_router, unwrap, current_route, EndpointInfo, RouteObject, RouteEntry, URL
from ..ff.routing import _ATTR_TARGET_ROUTE_DEFS
from ..ff.requests import RequestsPoolExecutor
from ..ff.types import is_optional, Params
from ..ff.menu import ContentView, AutoContextMenu, Target, ContextMenu, ContextMenuItem, CMenu, PagedItemList, KodiDirectoryKwArgs, KodiDirectory, directory
from ..ff.control import notification
from ..ff.log_utils import fflog, fflog_exc, LOGDEBUG
from ..api import ALL_PAGES
from ..kolang import L
from cdefs import ShowCxtMenu, ListType, AddToService, ListTarget, ListPointer
from const import const
if TYPE_CHECKING:
    from ..defs import RefType
    from ..ff.routing import RouteDecoratorProtocol
    from ..ff.lists import ServiceDescr, AddToListRemoveOptionsNames
    from ..windows.add_to import ListInfo
    from .core import ShowItemKwargs


# typing...
T = TypeVar('T')
D = TypeVar('D', bound=TypedDict)
P = ParamSpec('P')
R = TypeVar('R')

#: Indexers' folder endpoint type.
FolderEndpointName = Literal['add', 'library', 'list', 'logs', 'remove_list_items', 'delete_list']


#: The property name for add-to... endpoint (show dialog).
ADD_TO_ENDPOINT_FORMAT = '{func}__add_to'
#: The routing path for add-to... endpoint (show dialog).
ADD_TO_ENDPOINT_PATH = '{}/add/to/{__service_name}/{__list_name}'

#: The property name for add-to-library endpoint.
ADD_TO_LIBRARY_ENDPOINT_FORMAT = '{func}__add_to_the_library'
#: The routing path for add-to-library endpoint.
ADD_TO_LIBRARY_ENDPOINT_PATH = '{}/library/add'

#: The property name for add-to-user-list endpoint.
ADD_TO_USER_LIST_ENDPOINT_FORMAT = '{func}__add_to_the_list'
#: The routing path for add-to-user-list endpoint.
ADD_TO_USER_LIST_ENDPOINT_PATH = '{}/list/add/{__service_name}/{__list_name}'

#: The property name for add-to-log endpoint.
ADD_TO_LOGS_ENDPOINT_FORMAT = '{func}__add_to_the_logs'
#: The routing path for add-to-log endpoint.
ADD_TO_LOGS_ENDPOINT_PATH = '{}/logs/add'

#: The property name for remove-from-user-list endpoint.
REMOVE_FROM_USER_LIST_ENDPOINT_FORMAT = '{func}__remove_from_the_list'
#: The routing path for remove-from-user-list endpoint.
REMOVE_FROM_USER_LIST_ENDPOINT_PATH = '{}/list/remove/{ref}'
# REMOVE_FROM_USER_LIST_ENDPOINT_PATH = '{}/list/remove/{ref_to_remove}'

#: The property name for delete-user-list endpoint.
DELETE_USER_LIST_ENDPOINT_FORMAT = '{func}__delete_the_list'
#: The routing path for delete-user-list endpoint.
DELETE_USER_LIST_ENDPOINT_PATH = '{}/list/delete'


@frozen
class FolderEnpointDef:
    name: FolderEndpointName
    format: str
    path: str
    use_parent: bool = field(default=False, kw_only=True)  # if True, this endpoint based on parent method (not item method)


@frozen
class FolderEnpoint:
    name: FolderEndpointName
    format: str
    path: str
    method: Callable[..., None]
    use_parent: bool = False  # if True, this endpoint based on parent method (not item method)


endpoint_defs: Dict[FolderEndpointName, FolderEnpointDef] = {
    'add': FolderEnpointDef('add', ADD_TO_ENDPOINT_FORMAT, ADD_TO_ENDPOINT_PATH),
    'library': FolderEnpointDef('library', ADD_TO_LIBRARY_ENDPOINT_FORMAT, ADD_TO_LIBRARY_ENDPOINT_PATH),
    'list': FolderEnpointDef('list', ADD_TO_USER_LIST_ENDPOINT_FORMAT, ADD_TO_USER_LIST_ENDPOINT_PATH),
    'logs': FolderEnpointDef('logs', ADD_TO_LOGS_ENDPOINT_FORMAT, ADD_TO_LOGS_ENDPOINT_PATH),
    'remove_list_items': FolderEnpointDef('remove_list_items', REMOVE_FROM_USER_LIST_ENDPOINT_FORMAT, REMOVE_FROM_USER_LIST_ENDPOINT_PATH,
                                          use_parent=True),
    'delete_list': FolderEnpointDef('delete_list', DELETE_USER_LIST_ENDPOINT_FORMAT, DELETE_USER_LIST_ENDPOINT_PATH),
}


def filter_kwargs(cls: Type[D], kwargs: Union[Dict[str, Any], TypedDict]) -> D:
    """Filter dict by TypedDict definition."""
    allowed = cls.__annotations__
    dct = {k: v for k, v in kwargs.items() if k in allowed}
    return cast(D, dct)


class FolderPurpose(Enum):
    #: Regular Kodi directory.
    FOLDER = 0
    #: Library add.
    ADD_TO = 1
    #: Library add.
    LIBRARY = 2
    #: Add to custom (trakt, tmdb...) user list.
    USER_LIST = 3
    #: Add to logs (debug).
    LOGS = 4

    def request(self) -> 'FolderRequest':
        return FolderRequest(purpose=self)


@define(kw_only=True)
class FolderShowOptions:
    """
    Folder options, see Navigator.show_items() and directory().
    Class version of ShowItemKwargs with KodiDirectoryAddArgs.
    """

    # -- ShowItemKwargs --

    # FFinfo data limit, now only cast/crew limit, None - default, 0 - no cast, N – max N actors.
    crew_limit: Optional[int] = None
    # Message to show in a notification, if item list is empty. Do not show any notification if None.
    empty_message: Optional[str] = None
    # Standalone items (ex. episode without show), item label should show full info (ex. show and episode title).
    alone: Optional[bool] = None
    # Item URL to show an item if True, else execute the item. Ex. link to an episode: shows episodes else plays the episode.
    link: Optional[bool] = None
    # Item should have progress bar (|||) if is supported for those refs.
    progress: Optional[bool] = None
    # Extra format to set [ROLE].
    role_format: Union[str, Callable[[FFItem, int], str], None] = None
    # Extra context menu, not necessary in 99%. See Indexer.prepare_item().
    menu: Optional[ContextMenu] = None
    # Get more info about shows (and its seasons) to obtain episodes.
    tv_episodes: Optional[bool] = None
    # Do not get info (already got).
    skip_ffinfo: Optional[bool] = None

    # -- KodiDirectoryAddArgs --

    # Content view type.
    view: Optional[ContentView] = None
    #: Update the listing (updateListing=True).
    update: Optional[bool] = None
    #: Art: thumb.
    thumb: Optional[str] = None
    #: Art: icon.
    icon: Optional[str] = None
    #: Art: poster.
    poster: Optional[str] = None
    #: Art: landscape.
    landscape: Optional[str] = None
    #: Art: banner.
    banner: Optional[str] = None
    #: Art: fanart.
    fanart: Optional[str] = None
    #: Auto-format (ex. unaired).
    autoformat: Optional[bool] = None
    #: Style format.
    style: Optional[str] = None
    #: Context menu (append on top).
    menu_top: Optional[Iterable[Tuple[str, Target]]] = None
    #: Context menu (append on bottom).
    menu_bottom: Optional[Iterable[Tuple[str, Target]]] = None
    #: Auto context menu creators.
    auto_menu: Optional[Iterable[AutoContextMenu]] = None

    # -- menu.Directory methods --

    #: Focused items.
    # focused_item: Optional[FFItem] = None


@frozen(kw_only=True)
class FolderRequest:
    purpose: FolderPurpose
    show: FolderShowOptions = field(factory=FolderShowOptions)
    name: Optional[str] = None
    #: If true, pagination is used, else all pages will be collected (depagination).
    pagination: bool = True

    Purpose: ClassVar[Type[FolderPurpose]] = FolderPurpose

    @property
    def as_folder(self) -> bool:
        return self.purpose is FolderPurpose.FOLDER

    @property
    def as_all_items(self) -> bool:
        return self.purpose is not FolderPurpose.FOLDER

    @property
    def as_library(self) -> bool:
        return self.purpose is FolderPurpose.LIBRARY

    @property
    def as_user_list(self) -> bool:
        return self.purpose is FolderPurpose.USER_LIST


def sure_sequence(items: Iterable[FFRef]) -> Sequence[FFRef]:
    if items is None:
        return ()
    if isinstance(items, Sequence):
        return items
    return tuple(items)


@define(kw_only=True)
class Folder(FolderShowOptions):
    """Folder response (list of items) with nav.show_items() options."""
    #: Media items.
    items: Sequence[FFRef] = field(converter=sure_sequence, kw_only=False)
    #: Page number to show. Used to convert `items` to Pagina.
    page: int = 0
    #: Page limit (page size to show). Used to convert `items` to Pagina.
    limit: int = 20
    #: Custom name (ex. library batch name).
    name: Optional[str] = None
    #: User list spec.
    list_spec: Optional[str] = None
    #: User list target.
    list_target: Optional[ListTarget] = None

    def pagina(self) -> Sequence[FFRef]:
        if isinstance(self.items, ItemList):
            return self.items
        if not isinstance(self.items, Pagina) and self.page > 0 and self.limit > 0:
            self.items = Pagina(self.items, page=self.page, limit=self.limit)
        return self.items

    # --- ItemList protocol ---

    def __iter__(self) -> Iterator[FFRef]:
        return iter(self.pagina())

    def __len__(self) -> int:
        return len(self.pagina())

    @overload
    def __getitem__(self, index: int) -> FFRef: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[FFRef]: ...

    def __getitem__(self, index: Union[int, slice]) -> Any:
        return self.pagina()[index]

    @property
    def page_size(self) -> int:
        """Page size."""
        return getattr(self.items, 'page_size', self.limit)

    @property
    def total_pages(self) -> int:
        """Total number of pages."""
        return getattr(self.items, 'total_pages', 1)

    @property
    def total_results(self) -> int:
        """Total number of items."""
        count = getattr(self.items, 'total_results', None)
        if count is None:
            count = len(self.items)
        return count

    def next_page(self) -> Optional[int]:
        """Return next page number or None."""
        total_pages = self.total_pages
        if self.page and total_pages and self.page < total_pages:
            return self.page + 1
        return None

    # ---

    def show_items_args(self) -> 'ShowItemKwargs':
        from .core import ShowItemKwargs
        allowed = ShowItemKwargs.__annotations__
        return {f.name: val for f in fields(self.__class__)
                if f.name in allowed and (val := getattr(self, f.name)) is not None}  # type: ignore[reportReturnType]

    def extend(self, items: Union[Iterable[FFRef], 'Folder']) -> None:
        """Append items."""
        if isinstance(items, Folder):
            items = items.items
        if isinstance(self.items, list):
            self.items.extend(items)
        else:
            self.items = [*self.items, *items]

    @classmethod
    def from_response(cls,
                      folder: 'FolderReturn',
                      *,
                      req: FolderRequest,
                      func: Optional[Callable[..., Any]] = None,
                      kwargs: Optional[Params] = None,
                      ) -> 'Folder':
        """Return full folder with all show options."""
        if isinstance(folder, Folder):
            if req.as_folder:
                folder.pagina()
        else:
            if req.as_folder:
                folder = cls(folder, name=req.name, **asdict(req.show))
            else:
                # ignore show options if there is not items folder
                folder = cls(folder, name=req.name, page=0, limit=0)
        folder.list_spec = getattr(func, '_ff_list_spec', None)
        if folder.list_spec and kwargs is not None:
            try:
                folder.list_target = ListTarget.from_pointer(folder.list_spec.format(**kwargs))
            except AttributeError:
                pass
        return folder


FolderReturn = Union[Iterable[FFRef], PagedItemList[FFRef], Folder]
FolderSequenceReturn = Union[Sequence[FFRef], PagedItemList[FFRef], Folder]
FolderMethodOut = Callable[P, None]
FolderFuncIn = Callable[Concatenate[FolderRequest, P], FolderReturn]         # ???
FolderMethodIn = Callable[Concatenate[Any, FolderRequest, P], FolderReturn]  # ???
FolderExecute = Callable[[FolderRequest, Folder], None]
ActionExecute = Callable[..., None]

F = TypeVar('F', bound=FolderReturn)


class WraperMode(Enum):
    """Type of decorator wrapper."""
    FOLDER_ITEMS = auto_enum()
    SINGLE_ITEM = auto_enum()


class FolderDecoratedProto(Protocol, Generic[P]):
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> None: ...

    def endpoint(self, endpoint: FolderEndpointName) -> Callable[..., None]: ...


class FolderDecoratorProto(Protocol):
    # TODO: use FolderDecoratedProto if could be work without Intersection
    @overload
    def __call__(self, func: Callable[Concatenate[FolderRequest, P], FolderReturn], /) -> Callable[P, None]: ...
    @overload
    def __call__(self, method: Callable[Concatenate[Any, FolderRequest, P], FolderReturn], /) -> Callable[Concatenate[Any, P], None]: ...  # type: ignore[reportOverlappingOverload]
    @overload
    def __call__(self, func: Callable[P, FolderReturn], /) -> Callable[P, None]: ...
    @overload
    def __call__(self, method: Callable[Concatenate[Any, P], FolderReturn], /) -> Callable[Concatenate[Any, P], None]: ...  # type: ignore[reportOverlappingOverload]


@overload
def item_folder_route(func: Callable[Concatenate[FolderRequest, P], FolderReturn], /) -> Callable[P, None]: ...


@overload
def item_folder_route(method: Callable[Concatenate[Any, FolderRequest, P], FolderReturn], /) -> Callable[Concatenate[Any, P], None]: ...  # type: ignore[reportOverlappingOverload]


@overload
def item_folder_route(func: Callable[P, FolderReturn], /) -> Callable[P, None]: ...


@overload
def item_folder_route(method: Callable[Concatenate[Any, P], FolderReturn], /) -> Callable[Concatenate[Any, P], None]: ...  # type: ignore[reportOverlappingOverload]


@overload
def item_folder_route(path: str, /, *, library: Union[bool, str] = True, lists: Union[bool, str] = True, name: Optional[str] = None,
                      limit: Optional[int] = None, list_spec: Optional[str] = None) -> FolderDecoratorProto: ...


def item_folder_route(func_or_path,
                      /, *,
                      # Add to... support (show dialog where to add).
                      add_to: Union[bool, str] = True,
                      # Add library support (add to library the list item).
                      library: Union[bool, str] = True,
                      # Add lists support (add to user list the list item).
                      lists: Union[bool, str] = False,  # NO USED NOW
                      # Add logs support (logs all items, for debug only).
                      logs: Union[bool, str] = True,
                      #
                      remove_list_items: Union[bool, str] = True,
                      #
                      delete_list: Union[bool, str] = True,
                      # Custom items name (ex. library batch name).
                      name: Optional[str] = None,
                      # Limit for depagination – all items but not more then limit. Used with @pagination.
                      limit: Optional[int] = None,
                      #
                      list_spec: Optional[str] = None,
                      ) -> Any:
    """
    Decorate ffitem folder method with @route. The method must return items (MediaRef or FFItem).

    Method must accept FolderRequest type argument as first positional argument.

    >>> class A(RouteObject):
    >>>     @item_folder_route
    >>>     def my_items(self, req: FolderRequest, /, num: PathArg[int], query: int) -> Iterable[FFIem]:
    >>>         item = ...
    >>>         return items
    """

    def wrapper(func: FolderMethodIn) -> FolderMethodOut:
        sig = signature(func)
        params = sig.parameters
        has_self = sig.parameters and next(iter(sig.parameters)) in ('self', 'cls')  # it looks like method or classmethod
        the_func = unwrap(func)
        endpoints: Dict[FolderEndpointName, Callable[..., None]] = {}

        item_auto_menu: 'list[AutoFolderMenu]' = [
            auto_remove_list_items_refmenu(),
        ]
        item_auto_menu = [menu for menu in item_auto_menu if menu.is_enabled()]

        def add_route(execute: FolderExecute, *, path: Optional[str], name: str = '', wrapped: Callable[..., None]) -> Tuple[Params, RouteEntry]:
            esig = signature(execute)
            kwargs = {p.name: p for p in esig.parameters.values() if p.kind is p.KEYWORD_ONLY}
            if kwargs:
                if conflict := kwargs.keys() & sig.parameters.keys():
                    args_str = ', '.join(sorted(conflict))
                    fflog.warning(f'Argument conflict: {name or execute.__name__} uses {args_str} argument(s), endpoint {func} will NOT get it')
                route_sig = sig.replace(parameters=[*(p for p in sig.parameters.values() if p.name not in kwargs), *kwargs.values()])
            else:
                route_sig = sig
            route = main_router.function_route(path=fn_path, method=wrapped, signature=route_sig)
            if path:
                route.embed(path)
            return kwargs, route

        # call func
        if has_self:
            # create method wrapper
            def method_wrapper(req: FolderRequest, execute: FolderExecute, *, path: Optional[str], func_name: Optional[str] = None,
                               mod_name: Optional[FolderEndpointName] = None) -> Tuple[Callable[..., None], RouteEntry]:
                @wraps(func)
                def wrapped(self, *args: P.args, **kwargs: P.kwargs) -> None:
                    ekwargs = {k: v for k, v in kwargs.items() if k in execute_params}
                    fkwargs = {k: v for k, v in kwargs.items() if k not in execute_params}
                    if not req.pagination:
                        # no pages / all items (ex. add to library)
                        if 'page' in sig.parameters:
                            fkwargs['page'] = ALL_PAGES
                        if 'limit' in sig.parameters:
                            fkwargs['limit'] = limit
                    if req_param:
                        items = func(self, req, *args, **fkwargs)
                    else:
                        items = func(self, *args, **fkwargs)  # type: ignore  [reportCallIssue]  # omit FolderRequest
                    folder = Folder.from_response(items, req=req, func=func, kwargs=kwargs)
                    execute(req, folder, **ekwargs)
                if func_name:
                    wrapped.__name__ = func_name.format(func=the_func.__name__)
                execute_params, route = add_route(execute, path=path, name=mod_name or '', wrapped=wrapped)
                if mod_name:
                    endpoints[mod_name] = wrapped
                return wrapped, route

            create_wrapper = method_wrapper
            req_param = next(iter(p for i, p in enumerate(sig.parameters.values()) if i == 1), None)
            params = [p for i, p in enumerate(sig.parameters.values()) if i != 1]
        else:
            # create function wrapper
            def func_wrapper(req: FolderRequest, execute: FolderExecute, *, path: Optional[str], func_name: Optional[str] = None,
                             mod_name: Optional[FolderEndpointName] = None) -> Tuple[Callable[..., None], RouteEntry]:
                @wraps(func)
                def wrapped(*args: P.args, **kwargs: P.kwargs) -> None:
                    ekwargs = {k: v for k, v in kwargs.items() if k in execute_params}
                    fkwargs = {k: v for k, v in kwargs.items() if k not in execute_params}
                    if not req.pagination:
                        # no pages / all items (ex. add to library)
                        if 'page' in sig.parameters:
                            fkwargs['page'] = ALL_PAGES
                        if 'limit' in sig.parameters:
                            fkwargs['limit'] = limit
                    if req_param:
                        items = func(req, *args, **fkwargs)  # type: ignore  [reportCallIssue]  # call function not method
                    else:
                        items = func(*args, **fkwargs)  # type: ignore  [reportCallIssue]  # call function not method and omit FolderRequest
                    folder = Folder.from_response(items, req=req, func=func, kwargs=kwargs)
                    execute(req, folder, **ekwargs)
                if func_name:
                    wrapped.__name__ = func_name.format(func=the_func.__name__)
                execute_params, route = add_route(execute, path=path, name=mod_name or '', wrapped=wrapped)
                if mod_name:
                    endpoints[mod_name] = wrapped
                return wrapped, route

            create_wrapper = func_wrapper
            req_param = next(iter(p for i, p in enumerate(sig.parameters.values()) if i == 0), None)
            params = [p for i, p in enumerate(sig.parameters.values()) if i != 0]

        def create_action(execute: Callable[..., None],
                          *,
                          path: Optional[str],
                          func_name: Optional[str] = None,
                          mod_name: Optional[FolderEndpointName] = None,
                          ) -> Tuple[Callable[..., None], RouteEntry]:
            esig = sig
            eparams = {p.name: p for p in signature(execute).parameters.values() if p.kind is p.KEYWORD_ONLY}
            if eparams:
                func_params = list(sig.parameters.values())
                param_index = -1 if func_params and func_params[-1].kind is Parameter.VAR_KEYWORD else len(func_params)
                func_params[param_index:param_index] = eparams.values()
                esig = sig.replace(parameters=func_params)
            wrapped = wraps(func)(execute)
            if func_name:
                wrapped.__name__ = func_name.format(func=the_func.__name__)
            route = main_router.function_route(path=fn_path, method=wrapped, signature=esig)
            if path:
                route.embed(path)
            if mod_name:
                endpoints[mod_name] = wrapped
            return wrapped, route

        if req_param and req_param.annotation in (FolderRequest, 'FolderRequest'):
            sig = sig.replace(parameters=params, return_annotation=None)
        else:
            req_param = None
            sig = sig.replace(return_annotation=None)
        if path is None:
            fn_path = the_func.__name__
        else:
            fn_path = path

        def exec_show(req: FolderRequest, folder: Folder) -> None:
            from .navigator import nav
            nav.show_items(folder.items, **{
                'auto_menu': item_auto_menu,
                'list_target': folder.list_target,
                **folder.show_items_args(),
            })

        show, _ = create_wrapper(FolderRequest(purpose=FolderPurpose.FOLDER), exec_show, path=None)

        if add_to:
            create_wrapper(FolderRequest(purpose=FolderPurpose.ADD_TO, pagination=False), exec_add_to, mod_name='add',
                           func_name=ADD_TO_ENDPOINT_FORMAT,
                           path=ADD_TO_ENDPOINT_PATH if add_to is True else add_to)

        if library:
            batch_name = f'method:{the_func.__qualname__}' if name is None else name
            create_wrapper(FolderRequest(purpose=FolderPurpose.LIBRARY, pagination=False, name=batch_name), exec_library_add, mod_name='library',
                           func_name=ADD_TO_LIBRARY_ENDPOINT_FORMAT,
                           path=ADD_TO_LIBRARY_ENDPOINT_PATH if library is True else library)

        if lists:  # -- XXX -- NOT USED (use "add_to")
            create_wrapper(FolderRequest(purpose=FolderPurpose.USER_LIST, pagination=False), exec_user_list_add, mod_name='list',
                           func_name=ADD_TO_USER_LIST_ENDPOINT_FORMAT,
                           path=ADD_TO_USER_LIST_ENDPOINT_PATH if lists is True else lists)

        if logs:
            create_wrapper(FolderRequest(purpose=FolderPurpose.LOGS, pagination=False), exec_logs_add, mod_name='logs',
                           func_name=ADD_TO_LOGS_ENDPOINT_FORMAT,
                           path=ADD_TO_LOGS_ENDPOINT_PATH if logs is True else logs)

        if delete_list and list_spec:
            def delete_list_endpoint(*args, **kwargs) -> None:
                assert list_spec is not None
                target, srv = list_spec_service(list_spec, remove_options='lists', kwargs=kwargs)
                if srv:
                    exec_delete_list(srv, target)
            ep, _ = create_action(delete_list_endpoint,
                                  path=DELETE_USER_LIST_ENDPOINT_PATH if delete_list is True else delete_list,
                                  func_name=DELETE_USER_LIST_ENDPOINT_FORMAT,
                                  mod_name='delete_list')
            ep._ff_list_spec = list_spec

        if remove_list_items and list_spec:
            # def remove_list_items_endpoint(*args, ref_to_remove: MediaRef, **kwargs) -> None:
            def remove_list_items_endpoint(*args, ref: MediaRef, **kwargs) -> None:
                assert list_spec is not None
                target, srv = list_spec_service(list_spec, remove_options='items', kwargs=kwargs)
                if srv:
                    exec_remove_list_items(srv, target, ref)
            ep, _ = create_action(remove_list_items_endpoint,
                                  path=REMOVE_FROM_USER_LIST_ENDPOINT_PATH if remove_list_items is True else remove_list_items,
                                  func_name=REMOVE_FROM_USER_LIST_ENDPOINT_FORMAT,
                                  mod_name='remove_list_items')
            ep._ff_list_spec = list_spec

        # method for sub-function route, to use with url_for() for add_to etc.
        def endpoint(endpoint: FolderEndpointName) -> Optional[FolderEnpoint]:
            if (ep := endpoint_defs.get(endpoint)) and (call := endpoints.get(endpoint)):
                return FolderEnpoint(**asdict(ep), method=call)
            return None

        the_func.endpoint = endpoint
        func.endpoint = endpoint
        show.endpoint = endpoint
        if list_spec:
            func._ff_list_spec = list_spec
            show._ff_list_spec = list_spec
        return show

    path: Optional[str]
    if callable(func_or_path):
        path = None
        return wrapper(func_or_path)  # type: ignore[reportArgumentType]  # func is FolderFuncIn or FolderMethodIn
    path = func_or_path
    return wrapper


# --- Add to... endpoints. Added by @mediaref_endpoint. ---

@main_router.route(ADD_TO_ENDPOINT_PATH.replace('{}', '/{ref}'))
def add_ref_to(ref: MediaRef, *,
               service_name: Optional[AddToService] = None,
               list_name: Optional[str] = None,
               quiet: bool = const.dialog.add_to.quiet) -> None:
    """Add single media to... (GUI dialog)."""
    # fflog(f'Add {ref!r} to {service_name=}, {list_name=} ({quiet=})')
    exec_add_to(FolderPurpose.ADD_TO.request(), Folder(items=[ref]), service_name=service_name, list_name=list_name, quiet=quiet)


@main_router.route(ADD_TO_LIBRARY_ENDPOINT_PATH.replace('{}', '/{ref}'))
def add_ref_to_lib(ref: MediaRef, *,
                   quiet: bool = True) -> None:
    """Add single media to library."""
    # fflog(f'Add {ref!r} to library ({quiet=})')
    exec_library_add(FolderPurpose.LIBRARY.request(), Folder(items=[ref]), quiet=quiet)


@main_router.route(ADD_TO_LOGS_ENDPOINT_PATH.replace('{}', '/{ref}'))
def add_ref_to_logs(ref: MediaRef) -> None:
    """Add single media to logs (debug)."""
    exec_logs_add(FolderPurpose.LOGS.request(), Folder(items=[ref]))


# @main_router.route(REMOVE_FROM_USER_LIST_ENDPOINT_PATH.replace('{}', '/{ref}'))
# def remove_ref_from_list(ref: MediaRef) -> None:
#     """Remove item from list."""
#     breakpoint()
#     exec_logs_add(FolderPurpose.LOGS.request(), Folder(items=[ref]))


def _media_endpoint(endpoint: FolderEndpointName) -> Optional[FolderEnpoint]:
    if (ep := endpoint_defs.get(endpoint)) and (call := _media_endpoints.get(endpoint)):
        return FolderEnpoint(**asdict(ep), method=call)
    return None


_media_endpoints: Dict[FolderEndpointName, Callable[..., None]] = {
    'add': add_ref_to,
    'library': add_ref_to_lib,
    'logs': add_ref_to_logs,
    'remove_list_items': None,
}


@overload
def mediaref_endpoint(func: Callable[P, None], /) -> Callable[P, None]: ...


@overload
def mediaref_endpoint(func: Literal[None] = None,
                      /, *,
                      param_ref: Optional[str] = None,
                      param_ref_type: Optional[str] = None,
                      param_ref_ffid: Optional[str] = None,
                      param_ref_season: Optional[str] = 'season',
                      param_ref_episode: Optional[str] = 'episode',
                      ) -> Callable[[Callable[P, None]], Callable[P, None]]: ...


def mediaref_endpoint(func: Optional[Callable[P, None]] = None,
                      /, *,
                      param_ref: Optional[str] = None,
                      param_ref_type: Optional[str] = None,
                      param_ref_ffid: Optional[str] = None,
                      param_ref_season: Optional[str] = 'season',
                      param_ref_episode: Optional[str] = 'episode',
                      ) -> Any:
    """
    Decorate @route method with single MediaRef argument (direct or by its args) to add extra endpoints.

    Example:
    >>> class A(RouteObject):
    >>>     @mediaref_endpoint
    >>>     @route('/item/{ref}')
    >>>     def my_item(self, ref: MediaRef, /, page: int = 1) -> None: ...

    >>> class A(RouteObject):
    >>>     @mediaref_endpoint(param_ref_ffid='tv')
    >>>     @route('/show/{tv}')
    >>>     def my_item(self, tv: int, /, page: int = 1) -> None: ...
    """

    def wrapper(method: Callable[P, None]) -> Callable[P, None]:
        func = unwrap(method)
        route_defs = getattr(func, _ATTR_TARGET_ROUTE_DEFS, ())  # ensure func has _ff_route_defs
        if not route_defs:
            return func  # no route, nothing to do
        p_ref, p_ref_type, p_ref_ffid = param_ref, param_ref_type, param_ref_ffid
        if p_ref is None and p_ref_type is None and p_ref_ffid is None:
            p_ref = 'ref'
            p_ref_type = 'type'
            p_ref_ffid = 'ffid'
        route: 'RouteEntry' = route_defs[-1].route  # take the last route
        # route.signature
        # route.params
        if ismethod(func):
            base = func.__func__
        else:
            base = func
        base = unwrap(base)
        base.endpoint = _media_endpoint
        if p_ref == 'ref' and (ref := route.params.get(p_ref)) and MediaRef in ref.types:
            pass  # ref is already MediaRef, no need to transform the args
        else:
            # convert needed args to ref:MediaRef
            def convert_endpoint_args(item: FFItem, target: EndpointInfo) -> Params:
                params = target.params
                if p_ref:
                    ref: MediaRef = params[p_ref]
                    if isinstance(ref, MediaRefWithNoType) or not ref.type:
                        if not ismethod(target.method) or (mtype := getattr(target.method.__self__, 'TYPE', None)) is None:
                            fflog.warning(f'Cannot convert {target.method} args {target.params} to MediaRef, {p_ref_type=} or {p_ref_ffid=} or {p_ref=}')
                            return {}
                    return {'ref': ref}
                mtype: Optional['RefType'] = None
                if p_ref_type:
                    mtype = params[p_ref_type]
                elif 'type' in params:
                    mtype = params['type']
                elif 'mdeia_type' in params:
                    mtype = params['type']
                elif ismethod(target.method) and (mtype := getattr(target.method.__self__, 'TYPE', None)) is not None:
                    pass
                if mtype is not None and p_ref_ffid:
                    season: Optional[int] = params.get(param_ref_season) if param_ref_season else None
                    episode: Optional[int] = params.get(param_ref_episode) if param_ref_episode else None
                    ref = MediaRef(mtype, params[p_ref_ffid], season=season, episode=episode)
                    return {'ref': ref}
                fflog.warning(f'Cannot convert {target.method} args {target.params} to MediaRef, {p_ref_ffid=} or {p_ref_type=} or {p_ref=}')
                return {}
            base.convert_endpoint_args = convert_endpoint_args
        return func

    if func is None:
        # decorator with parameters
        return wrapper

    return wrapper(func)


class ApiPageMode(Enum):
    """API pagination mode."""
    UNKNOWN = auto_enum()
    NO = auto_enum()
    YES = auto_enum()
    OPTIONAL = auto_enum()


@define(kw_only=True)
class ApiPage:
    """API page description."""
    size: int
    min: int = 0
    max: int = 0
    # mode: ApiPageMode = ApiPageMode.UNKNOWN

    # NO: ClassVar[ApiPageMode] = ApiPageMode.NO
    # YES: ClassVar[ApiPageMode] = ApiPageMode.YES
    # OPTIONAL: ClassVar[ApiPageMode] = ApiPageMode.OPTIONAL

    def __attrs_post_init__(self):
        # if self.mode is ApiPageMode.UNKNOWN:
        #     if self.size:
        #         self.mode = ApiPageMode.YES
        #     elif self.min or self.max:
        #         self.mode = ApiPageMode.OPTIONAL
        if not self.size and (max_size := max(self.min, self.max)):
            self.size = max_size
        if not self.min:
            self.min = self.size
        if not self.max:
            self.max = self.size


@overload
def pagination(func: Callable[P, FolderReturn], /) -> Callable[P, FolderReturn]: ...


@overload
def pagination(size: int = const.indexer.page_size, *, limit: Optional[int] = None, api: Union[ApiPage, int, None] = None,
               all_pages: bool = True) -> Callable[[Callable[P, FolderReturn]], Callable[P, FolderReturn]]: ...


def pagination(size: Union[Callable[P, FolderReturn], int] = const.indexer.page_size,
               *,
               limit: Optional[int] = None,
               api: Union[ApiPage, int, None] = None,
               # Endpoint supports ALL_PAGES (page 0).
               all_pages: bool = True,
               # single_page: bool = False,
               ) -> Any:
    """
    (Re)-pagination getting items decorator.

    :param size:        The default page size
    :param limit:       The default items limit for depagination (all items)
    :param api:         API page description (or just API page size)
    :param all_pages:   If True, endpoint supports ALL_PAGES (page 0).
    :param single_page: If True, endpoint returns single page (no page split).  [XXX]

    >>> @pagination(size=20, api=ApiPage(size=250))
    >>> def my_items(*, page: Optional[int] = 1) -> Sequence[FFItem]:
    >>>     ...

    Pagination define route arguments `page` and `limit`:
    - page = 0, limit = 0  – all items (depagination)
    - page = 0, limit > 0  - first `limit` items (partial depagination for very long lists)
    - page > 0, limit = 0  - single page with default page size
    - page > 0, limit > 0  - single page with defined page size

    Pagination supports endpoint optional arguments `page` and `limit`.
    """
    def sure_seq(items: FolderReturn) -> FolderSequenceReturn:
        if items is None:
            return ()
        if isinstance(items, (Folder, Sequence)):
            return items
        return tuple(items)

    def the_page(items: FolderReturn, new: FolderSequenceReturn = (), *, offset: int = 0, limit: int, page: int = 1,
                 page_size: int = 0, total_pages: int = 1, total_results: int = 0) -> FolderSequenceReturn:
        result = items = sure_seq(items)
        if len(items) < offset + limit and new:
            items = (*items, *new)
        if offset or len(items) > offset + limit:
            items = items[offset:offset+limit]
        if not total_results:
            total_results = len(items)
        items = ItemList(items, page=page, page_size=page_size, total_pages=total_pages, total_results=total_results)

        if isinstance(result, Folder):
            result.items = items
            result.page = page
            result.limit = limit
            items = result
        return items

    def wrapper(func: Callable[P, FolderReturn]) -> Callable[P, FolderReturn]:

        @wraps(func)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> FolderReturn:
            def get(page: int):
                kwargs['page'] = page
                return sure_seq(func(*args, **kwargs))

            def paginate(items: FolderSequenceReturn) -> FolderSequenceReturn:
                a_limit = 20 if req_limit is None else req_limit
                if isinstance(items, Folder):
                    items.items = Pagina(items.items, page=req_page, limit=a_limit)
                else:
                    items = Pagina(items, page=req_page, limit=a_limit)
                return items

            if page_param := sig.parameters.get('page'):
                single_page = False
                req_page = cast(int, kwargs.get('page', 1 if page_param.default is page_param.empty else page_param.default))
            else:
                req_page: int = cast(int, kwargs.pop('page', 1))
                single_page = True  # single page, endpoint does not support page
            if limit_param := sig.parameters.get('limit'):
                req_limit = cast(Optional[int], kwargs.get('limit', None if limit_param.default is limit_param.empty else limit_param.default))
            else:
                req_limit = cast(Optional[int], kwargs.pop('limit', None))

            # -- depagination --
            if req_page == ALL_PAGES or not req_page:
                if req_limit is None:
                    req_limit = limit
                if not req_limit:
                    req_limit = maxsize

                # no pages, already depaginated, return items as is
                if single_page:
                    return the_page(func(*args, **kwargs), limit=req_limit)

                # the first page matches requested limit
                if _api and req_limit <= _api.max:
                    if page_param:
                        kwargs['page'] = 1
                    if limit_param:
                        kwargs['limit'] = req_limit
                    return the_page(func(*args, **kwargs), limit=req_limit)

                # API can deliver all items at once? Check it now!
                total_results: int
                items = ()
                # endpoint has no ALL_PAGE support and we know page size and limit, we can calculate all pages
                if not all_pages and _api and _api.size and req_limit:
                    start_page = 1
                    # prepare to collect all pages
                    real_page_size = _api.size
                    total_results = req_limit
                # we don't have enough info, we need to scan the first page
                else:
                    start_page = 2
                    if page_param:
                        kwargs['page'] = ALL_PAGES
                    if limit_param:
                        kwargs['limit'] = 0
                    try:
                        items = sure_seq(func(*args, **kwargs))
                    except Exception:
                        # catch exception for page=0 (endpoint can't handle it)
                        fflog_exc(level=LOGDEBUG)
                    else:
                        if len(items) >= req_limit or not page_param or getattr(items, 'total_pages', 0) == 1:
                            return the_page(items, limit=req_limit)

                    # first we have to get the first page to get how many items are there
                    if page_param:
                        kwargs['page'] = 1
                    if limit_param:
                        if _api and _api.max:
                            kwargs['limit'] = _api.max
                        elif limit_can_be_none:
                            kwargs['limit'] = None
                    # if we have no the first page, we need get it
                    if getattr(items, 'page', 0) != 1:
                        items = sure_seq(func(*args, **kwargs))
                        # is enough? or endpoint has no page support (there we can NOT get more pages)
                        if len(items) >= req_limit or not page_param:
                            return the_page(items, limit=req_limit)

                    # prepare to collect all pages
                    real_page_size = len(items)
                    total_results = getattr(items, 'total_results', 0)

                # -- collect all pages --
                parts = []

                # we know how many items are there
                if total_results:
                    pages_count = (min(total_results, req_limit) + real_page_size - 1) // real_page_size
                    # exactly two pages, we already have the first, now get the second
                    if pages_count == start_page:
                        kwargs['page'] = start_page
                        parts.extend(func(*args, **kwargs))
                    # more pages, we collect then concurrent
                    else:
                        with RequestsPoolExecutor() as pool:
                            parts.extend(chain(*pool.map(get, range(start_page, pages_count+1))))
                # we do NOT know how many items are there, we have to iterate page by page
                else:
                    for page_number in range(start_page, 1001):  # up to 1000 pages :-D
                        kwargs['page'] = page_number
                        part = sure_seq(func(*args, **kwargs))
                        if not part:  # no more items
                            break
                        parts.extend(part)
                # return joined pages
                return the_page(items, parts, limit=req_limit)

            # -- pagination --
            else:
                if req_limit is None:
                    req_limit = page_size

                # no pages, already depaginated, return subset of items (page)
                # if single_page:
                #     return the_page(func(*args, **kwargs), limit=req_limit)

                # direct pagination (requested page size matches to API capability)
                if _api and _api.min <= req_limit <= _api.max:
                    if req_page == 1 or page_param:
                        if req_page > 1:
                            kwargs['page'] = req_page
                        if limit_param and req_page != _api.size:
                            kwargs['limit'] = req_limit
                        items = sure_seq(func(*args, **kwargs))
                        if req_page and req_limit and len(items) > req_limit:
                            return paginate(items)
                        return items

                # repagination with no page support, only first API page could be used
                if not page_param:
                    items = sure_seq(func(*args, **kwargs))
                    if isinstance(items, Folder):
                        items.items = Pagina(items.items, page=req_page, limit=req_limit)
                    else:
                        items = Pagina(items, page=req_page, limit=req_limit)
                    return items

                # repagination
                first = ()
                items = ItemList(page=0, total_pages=0)
                index = (req_page - 1) * req_limit  # item index (count from zero)

                # repagination with well known page size
                if _api and _api.max:
                    if limit_param:
                        kwargs['limit'] = site_page_size = _api.max
                    else:
                        site_page_size = _api.size
                # unknown page size, we have to get some items
                else:
                    items = sure_seq(func(*args, **kwargs))
                    site_page: int = getattr(items, 'page', 0)
                    site_page_size: int = getattr(items, 'page_size', 0)
                    site_total_pages: int = getattr(items, 'total_pages', 0)
                    site_total_results: int = getattr(items, 'total_results', 0)
                    # only one page, we got everything already
                    if site_total_pages == 1:
                        return paginate(items)
                    # now we know the page size
                    if site_page_size:
                        first = items
                    # matches requested page, we guess
                    elif (req_page == site_page and (len(items) == req_limit
                                                     or (site_total_pages == site_page
                                                         and (not site_total_results or index + req_limit <= site_total_results)))):
                        return items
                    # we don't know nothing, return as is
                    else:
                        fflog(f'Unsported pagination {func} (page={req_page}, size={req_limit})')
                        return items

                api_range = range(index // site_page_size + bool(first) + 1, (index + req_limit - 1) // site_page_size + 2)  # api page range
                parts = ()
                if len(api_range) == 1:
                    if first:
                        parts = get(api_range.start)
                    else:
                        first = get(api_range.start)
                elif len(api_range) > 1:
                    with RequestsPoolExecutor() as pool:
                        parts = tuple(pool.map(get, api_range))
                        if not first and parts:
                            first, *parts = parts
                        parts = tuple(chain(*parts))
                site_total_results: int = getattr(first, 'total_results', 0)
                total_pages = (site_total_results + req_limit + 1) // req_limit
                items = the_page(first, parts, offset=index % site_page_size, limit=req_limit, page=req_page, page_size=site_page_size,
                                 total_pages=total_pages, total_results=site_total_results)
                return items

        sig = wrap_sig = signature(func)
        limit_can_be_none = (p := sig.parameters.get('limit', None)) and is_optional(p.annotation)
        if 'page' not in sig.parameters:
            wrap_sig = wrap_sig.replace(parameters=[*wrap_sig.parameters.values(),
                                                    Parameter('page', Parameter.KEYWORD_ONLY, default=1, annotation=int)])
        if 'limit' not in sig.parameters:
            wrap_sig = wrap_sig.replace(parameters=[*wrap_sig.parameters.values(),
                                                    Parameter('limit', Parameter.KEYWORD_ONLY, default=None, annotation=Optional[int])])
        # if wrap_sig is not sig:
        wrapped.__signature__ = wrap_sig  # hack
        return wrapped

    if isinstance(api, int):
        api = ApiPage(size=api)
    _api = api
    if callable(size):
        func, page_size = size, const.indexer.page_size
        return wrapper(func)
    page_size = size
    return wrapper


# -----


def add_to(service: Optional[AddToService], list_id: Optional[str], items: Iterable[FFRef], *, quiet: bool = const.dialog.add_to.quiet) -> None:
    """
    Add items to the list.

    :param service:  Service name (AddToService).
    :param list_id:  List ID or name.
    :param items:    Items to add.
    :param quiet:    If True, no notification will be shown.
    """
    from ..ff.lists import LIST_POINTERS
    # fflog.debug(f'ADD TO ... {service=}, {list_id=}: {len(items)} item(s)')
    dialog_service = const.dialog.add_to.lists.services[service] if service else const.dialog.add_to.lists.default
    srv = None
    if service:
        target = ListTarget.from_url(service, list_id)
        srv = LIST_POINTERS.get(target.pointer())
        if not srv and len(dialog_service) == 1 and len(pointers := tuple(next(iter(dialog_service.values())))) == 1:
            srv = LIST_POINTERS.get(pointers[0])

        if srv:
            # target is well defined, use it
            count = srv.add_items(target, items, quiet=quiet)
            if not quiet:
                label = next(iter(dialog_service)) if dialog_service else '...'
                notification(L(30477, 'Add to {name} list').format(name=label),
                             L(30478, 'Added {n} item to {name}|||Added {n} items to {name}', n=count, name=list_id or ""), visible=True)

    if srv is None:
        from ..windows.add_to import AddToDialog
        # breakpoint()
        # xservices = {label: [LIST_POINTERS[ptr] if isinstance(ptr, str) else ptr for ptr in pointers]
        #              for label, pointers in (dialog_service or const.dialog.add_to.lists.services).items()}
        lst: Optional[ListInfo] = AddToDialog(services=dialog_service, items=items).doModal()
        if lst:
            count = lst.add_items(items)
            if not quiet:
                notification(L(30477, 'Add to {name} list').format(name=lst.tab_label),
                             L(30478, 'Added {n} item to {name}|||Added {n} items to {name}', n=count, name=lst.name), visible=True)


# -----

def is_cm_enabled(value: ShowCxtMenu, /) -> bool:
    """Return True is CM is enabled (bool directly, or settings is true if str)."""
    if isinstance(value, str):
        from ..ff.settings import settings
        return settings.eval(value)
    return bool(value)


class AutoFolderMenu(AutoContextMenu):
    """Add-to-ANYTHING context-menu generator."""

    def label(self) -> str:
        """Return CM label."""
        return ''

    def is_enabled(self) -> bool:
        """Return true if module is enabled."""
        return True

    def endpoint_path(self) -> str:
        """Return endpoint path to find route."""
        return ''

    def endpoint_format(self) -> str:
        """Return endpoint format to find route."""
        return ''

    def subobject_name(self) -> str:
        """Return subobject name used in sub-class names this-name with `@route` decorator."""
        return ''

    def endpoint_name(self) -> Optional[FolderEndpointName]:
        """Return folder enpoint name if any."""
        return None

    def menu_target_params(self, item: FFItem, *, target: EndpointInfo) -> Params:
        """Return all paramters for menu endpoint (target and extra if any)."""
        conv: Optional[Callable[[FFItem, EndpointInfo], Params]]
        if callable(conv := getattr(target.method, 'convert_endpoint_args', None)):
            # convert endpoint args to params
            return conv(item, target)
        return target.params

    def is_endpoint_valid(self,
                          item: FFItem,
                          target: EndpointInfo,
                          *,
                          endpoint: Optional[FolderEnpoint] = None,
                          method: Optional[Callable[..., Any]] = None,
                          kdir: Optional[KodiDirectory] = None,
                          ) -> bool:
        return True

    def menu_item(self, url: URL, *, item: FFItem, target: EndpointInfo, kdir: Optional[KodiDirectory] = None) -> ContextMenuItem:
        """Return context menu item for the endpoint."""
        return self.label(), url

    def generate(self,
                 item: FFItem,
                 *,
                 target: Optional[Target] = None,
                 menu: Sequence[ContextMenuItem] = (),
                 kdir: Optional[KodiDirectory] = None,
                 ) -> Iterator[ContextMenuItem]:
        from inspect import ismethod

        # module is enabled in the settings
        if not self.is_enabled():
            return
        # `info_for()` must be used to add list item
        if not isinstance(target, EndpointInfo):
            return
        # only class method could be used (pointed in info_for), then we need to stop
        if not ismethod(target.method):
            # special support for functions before we stop
            endpoint: Optional[Callable[[FolderEndpointName], Optional[FolderEnpoint]]]
            if (ep_name := self.endpoint_name()) and callable(target.method) and (endpoint := getattr(target.method, 'endpoint', None)):
                # it have to be valid endpoint
                if (ep := endpoint(ep_name)) and self.is_endpoint_valid(item, target, endpoint=ep, kdir=kdir):
                    if (ep_url := target.main_router.url_for(ep.method, **self.menu_target_params(item, target=target))):
                        yield self.menu_item(ep_url, item=item, target=target, kdir=kdir)
            return

        # it works only in RouteObject class
        obj = target.method.__self__
        if not isinstance(obj, RouteObject):
            return

        # if it's regular route method, then we can use it
        meth = target.method
        func = unwrap(meth)
        if hasattr(func, '_ff_route_defs'):
            endpoint: Optional[Callable[[FolderEndpointName], Optional[FolderEnpoint]]]
            if ((ep_name := self.endpoint_name()) and (ismethod(func) or ismethod(meth))
                    and ((endpoint := getattr(func, 'endpoint', None)) or (endpoint := getattr(getattr(func, '__func__', None), 'endpoint', None)))):
                # it have to be valid endpoint
                if (ep := endpoint(ep_name)) and self.is_endpoint_valid(item, target, endpoint=ep, kdir=kdir):
                    if (ep_url := target.main_router.url_for(ep.method, **self.menu_target_params(item, target=target))):
                        yield self.menu_item(ep_url, item=item, target=target, kdir=kdir)

        # --- the first case: @item_folder_route
        if ep_method := getattr(obj, self.endpoint_format().format(func=func.__name__), None):
            if self.is_endpoint_valid(item, target, method=ep_method, kdir=kdir):
                if ep_url := target.main_router.url_for(ep_method, **self.menu_target_params(item, target=target)):
                    yield self.menu_item(ep_url, item=item, target=target, kdir=kdir)
            return

        # --- the second case: sub-class
        # class must have sub-class names subobject_name() with `@route` decorator
        ep_obj = getattr(obj, self.subobject_name(), None)  # access to route descriptor (build from @route SubClass)
        if not isinstance(ep_obj, RouteObject):
            return
        # routes in sub-class have to be named the same
        ep_method = getattr(ep_obj, target.method.__name__, None)
        if not callable(ep_method):
            return
        # it have to be valid endpoint, name the same and
        # there is not allow to use more sub-class route method arguments then in class method
        if self.is_endpoint_valid(item, target, method=ep_method, kdir=kdir):
            if ep_url := target.main_router.url_for(ep_method, **self.menu_target_params(item, target=target)):
                yield self.menu_item(ep_url, item=item, target=target, kdir=kdir)


class ListActionFolderMenu(AutoFolderMenu):
    """Action context-menu generator for user lists and theirs items."""

    REMOVE_OPTION: ClassVar[str] = ''

    def is_endpoint_valid(self,
                          item: FFItem,
                          target: EndpointInfo,
                          *,
                          endpoint: Optional[FolderEnpoint] = None,
                          method: Optional[Callable[..., Any]] = None,
                          kdir: Optional[KodiDirectory] = None,
                          ) -> bool:
        if list_spec := getattr(endpoint, '_ff_list_spec', None):
            pass
        elif target and (list_spec := getattr(target.method, '_ff_list_spec', None)):
            pass
        elif endpoint and (list_spec := getattr(endpoint.method, '_ff_list_spec', None)):
            pass
        else:
            return False
        from ..ff.lists import LIST_POINTERS
        try:
            pointer = list_spec.format(**target.params)
        except AttributeError:
            return False
        list_target = ListTarget.from_pointer(pointer)  # type: ignore[reportArgumentType]
        if srv := LIST_POINTERS.get(list_target.pointer()):
            if not self.REMOVE_OPTION or (srv.remove_options and srv.remove_options.get(self.REMOVE_OPTION)):
                return True
        return False


class auto_add_to_menu(AutoFolderMenu):
    """
    Add-to... anything (show dialog) context-menu generator.

    Allows to create CM "Add to..." for items defined in Library sub-class.
    Target endpoint opens dialog and allows user to select where to add.
    See `auto_library_menu` for usage.
    """

    def __init__(self, *,
                 enabled: ShowCxtMenu = False,  # const.indexer.context_menu.add_to,
                 service: Optional[AddToService] = None,
                 list: Optional[str] = None,
                 name: Optional[str] = None,
                 ) -> None:
        super().__init__()
        self.service = service
        self.list = list
        self.name = name
        self._enabled = enabled

    def label(self) -> str:
        return self.name or L(30307, 'Add to...')

    def is_enabled(self) -> bool:
        return is_cm_enabled(self._enabled)

    def endpoint_format(self) -> str:
        return ADD_TO_ENDPOINT_FORMAT

    def endpoint_name(self) -> Optional[FolderEndpointName]:
        return 'add'

    def menu_target_params(self, item: FFItem, *, target: EndpointInfo) -> Params:
        """Return extra paramters for menu endpoint."""
        data = super().menu_target_params(item, target=target)
        if self.service:
            data = dict(data)  # copy to avoid changing original
            data['service_name'] = self.service
            if self.list:
                data['list_name'] = self.list
        return data


class auto_library_menu(AutoFolderMenu):
    """
    Add-to-library context-menu generator.

    Allows to create CM "Add to library" for items defined in Library sub-class.

    First usage. @item_library_folder_route used. Some conditions:
      - library is enabled in the settings
      - generator is used with `auto_menu=[auto_library_menu()]`
      - `info_for()` must be used to add list item (`url_for` or direct method is not enough)
      - @item_library_folder_route must be used, then method must return sequence of MediaRef or FFItem

    >>> class A(RouteObject):
    >>>
    >>>     @route
    >>>     def my_dir(self) -> None:
    >>>         # auto_menu with auto_library_menu() is used
    >>>         with directory(auto_menu=[auto_library_menu()]) as kdir:
    >>>             # info_for() used
    >>>             kdir.add(L('My List'), info_for(self.my_list, a=1, page=1))
    >>>
    >>>     @item_library_folder_route
    >>>     def my_list(self, arg: int, page: int = 1) -> Sequence[FFItem]:
    >>>         items = ...
    >>>         return items  # return media items, ill be used by the folder and by the library

    Second usage. Several condition must be matched:
      - library is enabled in the settings
      - generator is used with `auto_menu=[auto_library_menu()]`
      - `info_for()` must be used to add list item (`url_for` or direct method is not enough)
      - class must have sub-class names `Library` with `@route` decorator
      - routes in sub-class Library have to be named the same (`my_list` in the example)
      - there is not allow to use more sub-class route method arguments then in class method, could be less

    >>> class A(RouteObject):
    >>>
    >>>     @route
    >>>     def my_dir(self) -> None:
    >>>         # auto_menu with auto_library_menu() is used
    >>>         with directory(auto_menu=[auto_library_menu()]) as kdir:
    >>>             # info_for() used
    >>>             kdir.add(L('My List'), info_for(self.my_list, a=1, page=1))
    >>>
    >>>     @route
    >>>     def my_list(self, arg: int, page: int = 1) -> None:
    >>>         items = ...
    >>>         nav.show_items(items) # add media items to the directory
    >>>
    >>>         # routed sub-class strict named `Library`
    >>>         @route
    >>>         class Library:
    >>>
    >>>             # the same name `my_list` like in `A.my_list`, no more arguments
    >>>             @route
    >>>             def my_list(self, arg: int) -> None:
    >>>                 items = ...
    >>>                 service_client.library_add(items)
    """

    def label(self) -> str:
        return L(30124, 'Add to library')

    def is_enabled(self) -> bool:
        return is_cm_enabled(False)  # const.indexer.context_menu.add_to_library

    def endpoint_format(self) -> str:
        return ADD_TO_LIBRARY_ENDPOINT_FORMAT

    def endpoint_name(self) -> Optional[FolderEndpointName]:
        return 'library'

    def subobject_name(self) -> str:
        return 'library'


class auto_user_list_menu(AutoFolderMenu):  # XXX -- NOT USED ---
    """
    Add-to-user-list context-menu generator.

    Allows to create CM "Add to user list" for items defined in Library sub-class.
    See `auto_library_menu` for usage.
    """

    def label(self) -> str:
        return L(30345, 'Add to user list')

    def is_enabled(self) -> bool:
        return False

    def endpoint_name(self) -> Optional[FolderEndpointName]:
        return 'list'

    def endpoint_format(self) -> str:
        return ADD_TO_USER_LIST_ENDPOINT_FORMAT


class auto_log_list_menu(AutoFolderMenu):
    """
    Add-to-log context-menu generator.

    Allows to create CM "Add to log" for items defined in Library sub-class.
    Target endpoint only logs every media.
    See `auto_library_menu` for usage.
    """

    def label(self) -> str:
        return L(30308, 'Add to log')

    def is_enabled(self) -> bool:
        return is_cm_enabled(False)

    def endpoint_format(self) -> str:
        return ADD_TO_LOGS_ENDPOINT_FORMAT

    def endpoint_name(self) -> Optional[FolderEndpointName]:
        return 'logs'


class auto_delete_list_menu(ListActionFolderMenu):
    """
    Delete-list context-menu generator.

    Allows to create CM "Delete the list".
    """

    REMOVE_OPTION = 'lists'

    def label(self) -> str:
        return L(30479, 'Delete list')

    def is_enabled(self) -> bool:
        return is_cm_enabled(True)  # XXX TODO: add const

    def endpoint_format(self) -> str:
        return DELETE_USER_LIST_ENDPOINT_FORMAT

    def endpoint_name(self) -> Optional[FolderEndpointName]:
        return 'delete_list'

    def menu_item(self, url: URL, *, item: FFItem, target: EndpointInfo, kdir: Optional[KodiDirectory] = None) -> ContextMenuItem:
        return CMenu(self.label(), url, order=40)


class auto_remove_list_items_refmenu(ListActionFolderMenu):
    """
    Remove-list-item context-menu generator.

    Allows to create CM "Remove item from the list".
    """

    REMOVE_OPTION = 'items'

    def label(self) -> str:
        return L(30480, 'Remove list item')

    def is_enabled(self) -> bool:
        return is_cm_enabled(True)  # XXX TODO: add const

    def endpoint_path(self) -> str:
        return REMOVE_FROM_USER_LIST_ENDPOINT_PATH

    def endpoint_format(self) -> str:
        return REMOVE_FROM_USER_LIST_ENDPOINT_FORMAT

    def endpoint_name(self) -> Optional[FolderEndpointName]:
        return 'remove_list_items'

    def is_endpoint_valid(self,
                          item: FFItem,
                          target: EndpointInfo,
                          *,
                          endpoint: Optional[FolderEnpoint] = None,
                          method: Optional[Callable[..., Any]] = None,
                          kdir: Optional[KodiDirectory] = None,
                          ) -> bool:
        if kdir and (list_target := kdir.list_target):
            from ..ff.lists import LIST_POINTERS
            if srv := LIST_POINTERS.get(list_target.pointer()):
                if not self.REMOVE_OPTION or srv.remove_options is None or srv.remove_options.get(self.REMOVE_OPTION, True):
                    return True
        return False

    def menu_item(self, url: URL, *, item: FFItem, target: EndpointInfo, kdir: Optional[KodiDirectory] = None) -> ContextMenuItem:
        return CMenu(self.label(), url, order=30)


@contextmanager
def list_directory(items: Optional[PagedItemList] = None,  # optional items get pagination
                   *,
                   # Extra arguments for "next page" routing, next page url_for().
                   route_args: Optional[Dict[str, Any]] = None,
                   # All KodiDirectoryKwArgs arguments.
                   **kwargs: Unpack[KodiDirectoryKwArgs],
                   ) -> Iterator[KodiDirectory]:
    # kwargs.setdefault('auto_menu', [auto_add_to_menu(), auto_library_menu(), auto_user_list_menu(), auto_log_list_menu()])
    kwargs.setdefault('auto_menu', [
        auto_add_to_menu(),
        auto_library_menu(),
        # auto_user_list_menu(),
        auto_log_list_menu(),
        *(auto_add_to_menu(enabled=cm.enabled, service=cm.service, list=cm.list, name=cm.name)
          for cm in const.indexer.context_menu.add_to),
        auto_delete_list_menu(),
    ])
    with directory(items, route_args=route_args, **kwargs) as kdir:
        yield kdir


def list_spec_service(list_spec: str,
                      *,
                      remove_options: 'Optional[AddToListRemoveOptionsNames]' = None,
                      kwargs: Params,
                      ) -> 'Tuple[ListTarget, Optional[ServiceDescr]]':
    """Get list service description from list spec and endpoint args."""
    from ..ff.lists import LIST_POINTERS
    assert list_spec is not None
    try:
        pointer = list_spec.format(**kwargs)
    except AttributeError as exc:
        fflog.warning(f'Missing argmuent for delete list endpoint, spec: {list_spec!r}, args: {kwargs}, exc: {exc}')
        return ListTarget(service='local'), None
    target = ListTarget.from_pointer(pointer)  # type: ignore[reportArgumentType]
    if srv := LIST_POINTERS.get(target.pointer()):
        if not remove_options or srv.has_remove_option(remove_options, target):
            return target, srv
    return target, None


def exec_add_to(req: FolderRequest,
                folder: Folder,
                *,
                service_name: Optional[AddToService] = None,
                list_name: Optional[str] = None,
                quiet: bool = False,
                ) -> None:
    fflog.debug(f'ADD TO...  {service_name=}, {list_name=} dialog with {len(folder.items)} item(s)')
    if service_name == 'library' or (service_name == 'local' and list_name == ':library'):
        from ..service.client import service_client
        service_client.library_add(folder.items, quiet=quiet)
    else:
        add_to(service_name, list_name, folder)


def exec_library_add(req: FolderRequest,
                     folder: Folder,
                     *,
                     quiet: bool = False,
                     ) -> None:
    from ..service.client import service_client
    service_client.library_add(folder.items, name=req.name, quiet=quiet)


def exec_user_list_add(req: FolderRequest,
                       folder: Folder,
                       *,
                       service_name: Optional[AddToService] = None,
                       list_name: Optional[str] = None,
                       ) -> None:
    print(f'ADDING TO USER LIST... {service_name=}, {list_name=}: {len(folder.items)} item(s): {folder.items}')
    add_to(service_name, list_name, folder)


def exec_logs_add(req: FolderRequest,
                  folder: Folder,
                  ) -> None:
    def dump_item(ref: FFRef) -> str:
        return f'  {ref}'
    items_str = '\n'.join(dump_item(it) for it in folder.items)
    fflog.info(f'ADDING TO LOG... {len(folder.items)} item(s):\n{items_str}')


def exec_delete_list(srv: 'ServiceDescr',
                     target: ListTarget,
                     *,
                     quiet: bool = False,
                     ) -> None:
    fflog.debug(f'DELETE LIST {target}')
    from ..ff.control import yesnoDialog, refresh
    name = target.list or target.section or target.service
    if yesnoDialog(L(30481, 'Delete {name} list?').format(name=name), L(30482, 'All items in list will be removed!')):
        if srv.remove_list(target, quiet=quiet):
            refresh()


def exec_remove_list_items(srv: 'ServiceDescr',
                           target: ListTarget,
                           ref: MediaRef,
                           *,
                           quiet: bool = False,
                           ) -> None:
    from ..ff.control import yesnoDialog, refresh
    fflog.debug(f'REMOVE {ref} FROM LIST...  {target}')
    name = target.list or target.section or target.service
    if yesnoDialog(L(30483, 'Remove item from {name} list?').format(name=name)):
        if srv.remove_items(target, [ref], quiet=quiet):
            refresh()
