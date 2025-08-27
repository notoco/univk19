
from __future__ import annotations
from typing import Mapping, cast, TYPE_CHECKING
from typing_extensions import Literal, get_args as get_typing_args
import re
import json
from urllib.parse import unquote
from attrs import define
from requests import Session
import xbmcvfs
from ..defs import MediaRef, FFRef, ItemList, XMediaRef
from .types import EnumName
from .item import FFItem
from .url import URL
from .log_utils import fflog
from .db.orm import DbTable, PrimaryKey, OrmDatabase, field, relationship, DbCursor, select, delete
# from const import const
from cdefs import ListType, OwnListDef
if TYPE_CHECKING:
    from typing import Optional, Union, Dict, Sequence, Iterator, Iterable, Pattern, ClassVar
    from .types import JsonResult
    from .menu import ContextMenuItem

#: Ownlists DB version.
DB_VERSION: int = 1

#: Any media type supported by TMDB.
OwnMediaType = Literal['media', 'movie', 'show', 'person', 'collection']

OwnMediaTypeAllowed = get_typing_args(OwnMediaType)


class LocalListFolder(DbTable):
    """Local list (own list) definition."""

    __tablename__ = 'list'
    __table_args__ = ('UNIQUE("name")',)

    FAVORITES: ClassVar[str] = ':favorites'
    WATCHLIST: ClassVar[str] = ':watchlist'
    COLLECTION: ClassVar[str] = ':collection'
    OWN: ClassVar[str] = ':own'  # root folder

    BASE_LISTS: ClassVar[Dict[str, ListType]] = {
        FAVORITES: ListType.MIXED,
        WATCHLIST: ListType.MEDIA | ListType.COLLECTION,
        COLLECTION: ListType.MEDIA | ListType.COLLECTION,
        OWN: ListType.LIST,
    }

    id: PrimaryKey = None
    name: str
    type: EnumName[ListType]
    entries: Sequence[LocalListItem] = relationship(back_populates='folder')

    def media_match(self, media: Union[OwnMediaType, str, None]) -> bool:
        """Return True if list should be support for given media type."""
        if media in OwnMediaTypeAllowed:
            return OwnListDef.type_match(self.type, media)
        return False


class LocalListItem(DbTable):
    """Local list (own list) single item."""

    __tablename__ = 'item'
    # __table_args__ = ('UNIQUE("xref::type", "xref::ffid", "xref::season", "xref::episode", "link")',)

    id: PrimaryKey = None
    folder_id: Optional[int] = field(foreign_key='lists.id')
    folder: LocalListFolder = relationship(back_populates='entries')
    xref: XMediaRef = field(converter=MediaRef.to_sql_ref)
    subfolder: Optional[LocalListFolder] = relationship(on='xref.ffid', when='xref.type == "list"')
    link: str = ''

    def __attrs_post_init__(self):
        self.xref = self.xref.sql_ref

    @property
    def ref(self) -> MediaRef:
        return MediaRef.from_sql_ref(self.xref)

    @ref.setter
    def ref(self, ref: MediaRef) -> None:
        self.xref = ref.sql_ref

    @property
    def subfolder_name(self) -> str | None:
        sub = self.subfolder
        return None if sub is None else sub.name


def on_db_connect(cur: DbCursor) -> None:
    """Add basic folders on connect (if missing)."""
    for name, typ in LocalListFolder.BASE_LISTS.items():
        if cur.exec(select(LocalListFolder).where(LocalListFolder.name == name)).first() is None:
            cur.add(LocalListFolder(name=name, type=typ))
    cur.commit()


#: OwnLists database.
# db = OrmDatabase('ownlists', LocalListFolder, LocalListItem, verison=DB_VERSION, on_connect=on_db_connect)


@define
class OwnDb:

    db: OrmDatabase = field(init=False,
                            factory=lambda: OrmDatabase('ownlists', LocalListFolder, LocalListItem, version=DB_VERSION, on_connect=on_db_connect))

    FAVORITES: ClassVar[str] = LocalListFolder.FAVORITES
    WATCHLIST: ClassVar[str] = LocalListFolder.WATCHLIST
    COLLECTION: ClassVar[str] = LocalListFolder.COLLECTION
    OWN: ClassVar[str] = LocalListFolder.OWN

    def _folder(self, list_id: Union[int, str], *, cur: DbCursor) -> Optional[LocalListFolder]:
        """Get list items by list id."""
        try:
            if isinstance(list_id, int):
                return cur.get(LocalListFolder, list_id)
            else:
                return cur.exec(select(LocalListFolder).where(LocalListFolder.name == str(list_id))).first()
        except Exception:
            fflog.warning(f'No own list {list_id!r}')
        return None

    def root(self) -> Optional[LocalListFolder]:
        """Get root folder object."""
        return self.folder(LocalListFolder.OWN)

    def folder(self, list_id: Union[int, str]) -> Optional[LocalListFolder]:
        """Get folder object."""
        with self.db.cursor() as cur:
            return self._folder(list_id, cur=cur)

    # def list(self, list_id: Union[int, str]) -> Iterator[MediaRef]:
    #     """Get list items by list id."""
    #     with self.db.cursor() as cur:
    #         folder = self._folder(list_id, cur=cur)
    #         if folder is None:
    #             return
    #         yield from (it.ref for it in folder.entries)

    def list(self, list_id: Union[int, str]) -> Iterator[FFItem]:
        """Get list items by list id."""
        def make(it: LocalListItem) -> FFItem:
            """Convert LocalListItem to FFItem."""
            if sub := it.subfolder:
                ff = FFItem(sub.name, type='list', ffid=it.id, mode=FFItem.Mode.Folder, properties={
                    'list_type': str(it.subfolder.type),
                })
                ff.vtag.setTitle(sub.name)
                ff.vtag.setUniqueID(f'db://own/{sub.name}', 'list-url')
                ff.vtag.setUniqueID(str(it.subfolder.type), 'list-type')
                return ff
            return FFItem(it.ref)

        with self.db.cursor() as cur:
            folder = self._folder(list_id, cur=cur)
            if folder is None:
                return
            yield from (make(it) for it in folder.entries)

    def list_add(self, list_id: Union[int, str], items: Iterable[FFRef]) -> int:
        """Add items to list. Return number of items added."""
        with self.db.cursor() as cur:
            folder = self._folder(list_id, cur=cur)
            if folder is None:
                return 0
            exists = {it.ref for it in folder.entries}
            count = 0
            for it in items:
                ref = it.ref
                if ref not in exists and folder.media_match(ref.type):
                    count += 1
                    cur.add(LocalListItem(folder_id=folder.id, xref=ref))
            return count

    def remove_items(self, list_id: Union[int, str], items: Iterable[FFRef]) -> int:
        """Remove items from list. Return number of items removed."""
        with self.db.cursor() as cur:
            folder = self._folder(list_id, cur=cur)
            if folder is None:
                return 0
            exists = {it.ref: it.id for it in folder.entries}
            if not exists:
                return 0
            count = 0
            # breakpoint()
            for it in items:
                ref = it.ref
                if iid := exists.get(ref):
                    count += 1
                    cur.exec(delete(LocalListItem).where(LocalListItem.id == iid))
            return count

    def list_type(self, list_id: Union[int, str]) -> ListType:
        """Return list content type flags."""
        with self.db.cursor() as cur:
            folder = self._folder(list_id, cur=cur)
            if folder is None:
                return ListType(0)
            return folder.type

    def create_list(self, name: str, *, type: ListType = ListType.MIXED, parent: LocalListFolder | str | int | None = None) -> LocalListFolder:
        """Create new folder (in `folder` or root)."""
        with self.db.cursor() as cur:
            if not isinstance(parent, LocalListFolder):
                parent = self._folder(parent or LocalListFolder.OWN, cur=cur)
            folder = LocalListFolder(name=name, type=type)
            cur.add(folder)
            cur.commit()
            cur.add(LocalListItem(folder_id=parent.id, xref=MediaRef('list', folder.id or 0)))
        return folder

    def delete_list(self, list_id: Union[int, str]) -> bool:
        """Detele the list and its content. Return true on success."""
        with self.db.cursor() as cur:
            folder = self._folder(list_id, cur=cur)
            if folder is None:
                return False
            # remove all items
            cur.exec(delete(LocalListItem).where(LocalListItem.folder_id == folder.id))
            # remove folder item in parent folder (and any others folders)
            cur.exec(delete(LocalListItem).where(LocalListItem.xref == MediaRef('list', folder.id or 0)))
            # remove folder
            cur.exec(delete(LocalListFolder).where(LocalListFolder.id == folder.id))
            return True


# The own "API". It's so simple there is here, not in lib/api/
@define
class OwnList:
    #: List content type (type of items).
    type: ListType
    #: List of item URL / path.
    url: str
    #: Custom requests HTTP session.
    sess: Optional[Session] = None

    RX_DB_LIST_ID: ClassVar[Pattern[str]] = re.compile(r'/[1-9](\d*)')

    def match(self, media: Union[ListType, str, None]) -> bool:
        """Return True if list should be visible for given media type."""
        return OwnListDef.type_match(self.type, media)

    def load(self, *,
             page: int = 1,
             media: Union[ListType, str, None] = None,
             ) -> Sequence[FFRef]:
        media = ListType.new(media or ListType.ALL)
        url = self.url
        # convert info "URL"
        u = URL(url)
        # (local sqlite3 db)
        if u.scheme == 'db':  # db://own/list (name or id)
            if mch := self.RX_DB_LIST_ID.fullmatch(u.path):
                list_id = int(mch[1])
            else:
                list_id = u.path[1:]  # omit leading '/'
            items = own_db.list(list_id or ':own')
            if media:
                items = (ref for ref in items if ListType.from_media_ref(ref.ref) & media)
            items = sorted(items, key=lambda it: it.label.lower())
            return ItemList.single(items)
        # (file in FF3 profile)
        elif u.scheme == 'profile':
            import xbmcaddon
            prefix = xbmcaddon.Addon().getAddonInfo('profile')
            if u.hostname:
                url = f'{prefix}/{u.hostname}{u.path}'
            else:
                url = f'{prefix}{u.path}'
            if u.query:
                url = '{url}?{u.query}'
            u = URL(url)
        # (file in any FF3 addon info)
        elif u.scheme == 'info':
            import xbmcaddon
            prefix = xbmcaddon.Addon().getAddonInfo(u.hostname or 'profile')
            url = f'{prefix}{u.path}'
            if u.query:
                url = '{url}?{u.query}'
            u = URL(url)
        # dynamic list
        if handler := getattr(self, f'query_{u.scheme}', None):
            return handler(page=page)
        # HTTP link
        if u.scheme in ('http', 'https'):
            sess = self.sess or Session()
            try:
                resp = sess.get(url)
            except OSError as exc:
                fflog(f'Download own list {url} failed: {exc!r}')
                return ()
            content = resp.text
        # another link (file, NFS, ...), use Kodi
        else:
            try:
                with xbmcvfs.File(url) as f:
                    content = f.read()
            except Exception as exc:
                fflog(f'Read own list {url} failed: {exc!r}')
                return ()
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # not a JSON, try CSV
            return ItemList.single(self.parse_csv(content, type=self.type, media=media))
        else:
            return ItemList.single(self.parse_json(data, type=self.type, media=media))

    @staticmethod
    def make_media(it, *, media: Optional[str] = None) -> Optional[MediaRef]:
        if isinstance(it, Mapping):
            typ = it.get('type')
            if media and media != typ:
                return None
            try:
                tmdb = int(it.get('tmdb', 0))
            except (ValueError, TypeError):
                return None
            if tmdb and typ != 'mixed' and typ != 'media' and typ in OwnMediaTypeAllowed:
                if TYPE_CHECKING:
                    assert typ in ('movie', 'show', 'person', 'collection')
                return MediaRef.from_tmdb(typ, tmdb)
        return None

    @staticmethod
    def make_list(it, *, media: Optional[str] = None) -> Optional[FFItem]:
        if isinstance(it, Mapping):
            typ = it.get('type')
            if media and media != typ:
                return None
            label = it.get('label')
            url = it.get('url')
            if url and typ:
                u = URL(url)
                item = FFItem(label or u.path or u.hostname or '?', type='list', mode=FFItem.Mode.Folder)
                item.vtag.setUniqueID(url, 'list-url')
                item.vtag.setUniqueID(typ, 'list-type')
                if icon := it.get('icon'):
                    item.setArt({'thumb': icon})
                return item
        return None

    def parse_csv(self, data: str, *, type: ListType, media: Optional[str] = None) -> Sequence[FFRef]:
        from io import StringIO
        from csv import DictReader
        with StringIO(data) as f:
            if type == 'list':
                return tuple(ffitem for it in DictReader(f) if (ffitem := self.make_list(it, media=media)))
            if type in OwnMediaTypeAllowed:
                return tuple(ffitem for it in DictReader(f) if (ffitem := self.make_media(it, media=media)))
        return ()

    def parse_json(self, data: JsonResult, *, type: Optional[ListType], media: Optional[str] = None) -> Sequence[FFRef]:
        if not isinstance(data, Mapping):
            return ()
        list_type = data.get('type') or type or self.type or 'mixed'
        # is requested type compatible with real list type?
        if (list_type == 'list') ^ (type == 'list'):
            return ()
        if list_type == 'list':
            return tuple(ffitem for it in data.get('items', ()) if (ffitem := self.make_list(it, media=media)))
        if list_type in OwnMediaTypeAllowed:
            return tuple(ffitem for it in data.get('items', ()) if (ffitem := self.make_media(it, media=media)))
        return ()

    def query_tmdb(self, *, page: int = 1) -> Sequence[FFRef]:
        """Return media from TMDB dicover.All DiscoveryFilters are supported (with explicite comparations: '?with_runtime<=90')."""
        from .tmdb import tmdb
        from ..api.tmdb import Condition
        u = URL(self.url)
        if u.hostname in ('movie', 'show'):
            return tmdb.discover(u.hostname, page=page, **Condition.filters_from_str_expr_list(map(unquote, u.query.split('&'))))
        return ()


own_db = OwnDb()


if __name__ == '__main__':
    from ..defs import VideoIds
    tmdb = VideoIds.ffid_from_tmdb_id
    items = [
        MediaRef('movie', tmdb(78)),
        MediaRef('show', tmdb(119051)),
        MediaRef('show', tmdb(1434), 2),
        MediaRef('show', tmdb(213834), 3, 4),
        MediaRef('person', tmdb(190)),
        MediaRef('collection', tmdb(726871)),
        MediaRef('genre', tmdb(12)),
    ]
    if 0:
        print(own_db.list_add(':favorites', items))
        # print(own_db.list_add(':watchlist', items))
        f = own_db.folder(1)
        print(f)
    if 0:
        try:
            own_db.create_list('ala')
        except:
            print('ala not added')
        print(own_db.folder('ala'))
        for e in own_db.root().entries:
            print(f' - {e} : {e.subfolder}')
