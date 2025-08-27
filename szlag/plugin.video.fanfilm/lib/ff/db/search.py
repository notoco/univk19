
from typing import Optional, Tuple, List, Iterator, Sequence
from typing_extensions import TypeAlias, Literal
from contextlib import contextmanager
from sqlite3 import Cursor
from pathlib import Path
import json
import re

from .db import db_manager, db_create_columns, Lock, update_db_version, PrimaryKey
from .orm import OrmDatabase, DbTable, DbCursor, select, delete, AND
from ..log_utils import fflog, fflog_exc
from ..calendar import utc_timestamp
from ..types import JsonData
from ...defs import SearchType


#: Search DB version.
DB_VERSION: int = 1


class SearchEntry(DbTable):
    """Single row in search table."""

    __tablename__ = 'search'
    __table_args__ = ('UNIQUE("search_type", "key", "options")',)

    #: The primary DB key.
    id: PrimaryKey = None
    #: What is searched.
    search_type: SearchType
    #: Query text to search.
    query: str
    #: Timestamp for create / update the search.
    updated_at: int
    #: Timestamp for create / update the search.
    last_used_at: int = 0
    #: Extra options (JSON).
    options: str = '{}'
    #: Query kkey to search (lower-case query).
    key: str = ''

    def __attrs_post_init__(self) -> None:
        """Post-init hook to set the key."""
        if not self.key:
            self.key = re.sub(r'\s+', '', self.query.lower()).strip()


def _migrate_old(cur: DbCursor) -> None:
    """Migrate old (FF2) search entries (search.1.db)."""
    from sqlite3 import connect as db_connect
    from ..control import dataPath

    @contextmanager
    def old_cursor() -> Iterator[Cursor]:
        db = db_connect(path, timeout=1.)
        cur = db.cursor()
        try:
            yield cur
        finally:
            try:
                cur.connection.commit()
            finally:
                cur.close()
            db.close()

    path = Path(dataPath) / 'search.1.db'
    if path.exists():
        try:
            with old_cursor() as old_cur:
                yesterday = int(utc_timestamp()) - 86400  # a day ago
                for stype, old_tab in (('movie', 'movies'), ('show', 'tvshow')):
                    old_cur.execute(f'SELECT term FROM {old_tab} ORDER BY id DESC')
                    for i, row in enumerate(old_cur.fetchall()):
                        term = row[0]
                        cur.add(SearchEntry(search_type=stype, query=term, updated_at=yesterday - i, last_used_at=yesterday-i))
        except Exception:
            fflog('Migraet old search history FAILED')
            fflog_exc()
        else:
            target = Path(dataPath) / 'search.ff2.db'
            try:
                path.replace(target)
            except OSError as exc:
                fflog(f'Failed to rename old search history file {target}: {exc}')


#: Global state DB lock.
db = OrmDatabase('search', SearchEntry, version=DB_VERSION, on_create=_migrate_old)


# -----


def get_search_history(type: SearchType) -> Sequence[SearchEntry]:
    """Get search list."""
    with db.cursor() as cur:
        return cur.exec(select(SearchEntry).where(SearchEntry.search_type == type).order_by('last_used_at DESC')).all()


def get_search_item(id: int, *, type: Optional[SearchType] = None) -> Optional[SearchEntry]:
    """Get search list."""
    with db.cursor() as cur:
        entry = cur.get(SearchEntry, id)
        if entry and type == entry.search_type:
            return entry
        return None


def set_search_item(type: SearchType,
                    query: str,
                    *,
                    options: Optional[JsonData] = None,
                    id: Optional[int] = None,
                    ) -> int:
    """Set (update or insert) search item. Return ID. If `id` is not None, update item `id`."""
    now = int(utc_timestamp())
    if options is None:
        options = {}
    opt = json.dumps(options)
    key = re.sub(r'\s+', ' ', query.lower()).strip()
    with db.cursor() as cur:
        if id is None:
            entry = cur.exec(select(SearchEntry).where(AND(
                SearchEntry.search_type == type,
                SearchEntry.key == key,
                SearchEntry.options == opt))).first()
            # cur.execute(f'SELECT id FROM {SearchRow.__table__} WHERE search_type=? AND query=?', (type, query))
        else:
            # re-select id to check type
            entry = cur.exec(select(SearchEntry).where(AND(SearchEntry.search_type == type, SearchEntry.id == id))).first()
            # cur.execute(f'SELECT id FROM {SearchRow.__table__} WHERE search_type=? AND id=?', (type, id))
        if not entry:
            entry = SearchEntry(search_type=type, key=key, query=query, updated_at=now, options=opt)
        entry.query = query
        entry.updated_at = now
        entry.last_used_at = now
        entry.options = opt
        cur.add(entry)
        cur.commit()
    assert entry.id
    return entry.id


def remove_search_item(id: int) -> None:
    """Remove search list."""
    with db.cursor() as cur:
        cur.exec(delete(SearchEntry).where(SearchEntry.id == id))
        # cur.execute(f'DELETE FROM {SearchRow.__table__} WHERE id = ?', (id,))


def remove_search_history(type: Optional[SearchType]) -> None:
    """Remove search history."""
    with db.cursor() as cur:
        if type:
            cur.exec(delete(SearchEntry).where(SearchEntry.search_type == type))
            # cur.execute(f'DELETE FROM {SearchRow.__table__} WHERE search_type = ?', (type,))
        else:
            cur.exec(delete(SearchEntry))
            # cur.execute(f'DELETE FROM {SearchRow.__table__}')


def touch_search_item(id: int) -> None:
    """Touches seartch item, updates `last_used_at`."""
    with db.cursor() as cur:
        entry = cur.get(SearchEntry, id)
        if entry:
            entry.last_used_at = int(utc_timestamp())
            cur.add(entry)
