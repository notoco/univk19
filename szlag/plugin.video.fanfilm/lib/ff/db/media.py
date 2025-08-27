"""Media DB."""

from typing import Optional, Union, Tuple, List, Dict, Set, Sequence, Iterable, Iterator, NamedTuple
from contextlib import contextmanager
from sqlite3 import Cursor, IntegrityError
from time import time as time_now

from ...defs import MediaType, MediaRef, RefType
# from ..item import FFItem
from .db import db_manager, update_db_version, db_create_columns, db_list_columns, Lock, sql_dump


#: WHERE IN VALUES (type, main_ffid, season, episode)
MediaInfoWhereValue = Tuple[str, int, int, int]


# @dataclass
class Person:

    name: str
    poster: str


class MediaInfoRow(NamedTuple):
    """Media meta-info."""

    __table__ = 'info'

    type: RefType
    #: Movie or TV-show ID.
    ffid: int
    #: Parent ID (movie itself or tvshow ID for rest).
    main_ffid: int = 0
    #: TV-show ID for show (`ffid` duplicate), season and episode.
    # tv_ffid: int = 0
    #: Season number, used with type='show' and tv_ffid.
    season: int = -1
    #: Episode number, used with type='show', tv_ffid and season.
    episode: int = -1
    tmdb: Optional[int] = None
    imdb: Optional[str] = None
    trakt: Optional[int] = None
    #: User language (FanFilm setting), used for TMDB title translation.
    ui_lang: Optional[str] = None

    #: Title in `ui_lang`
    title: Optional[str] = None
    #: Title in English.
    en_title: Optional[str] = None
    # #: Title in origin language.
    # orig_title: Optional[str] = None
    #: Video duration.
    duration: Optional[int] = None

    #: Data dump type ('json').
    data_type: str = 'json'
    #: Data dump.
    data: Union[None, str, bytes] = None

    #: Timestamp of last update.
    updated_at: int = 0

    @property
    def ref(self) -> MediaRef:
        """Return media reference."""
        if self.type == 'show':
            season = None if self.season < 0 else self.season
            episode = None if self.episode < 0 else self.episode
            return MediaRef(type=self.type, ffid=self.main_ffid, season=season, episode=episode)
        return MediaRef(type=self.type, ffid=self.ffid)

    def denormalized_ref(self) -> MediaRef:
        """Return direct/denormalized media reference."""
        if self.episode >= 0:
            return MediaRef(type='episode', ffid=self.ffid)
        if self.season >= 0:
            return MediaRef(type='season', ffid=self.ffid)
        return MediaRef(type=self.type, ffid=self.ffid)

    @classmethod
    def sql_columns(cls) -> str:
        return db_list_columns(cls)

    # def sql_where(self) -> str:
    #     """SQL WHERE arguments."""
    #     def dump(v):
    #         if v is None:
    #             return ' is NULL'
    #         return f'={v}'

    #     if self.tv_ffid:
    #         return f'tv_ffid={self.tv_ffid} AND season{dump(self.season)} AND episode{dump(self.episode)}'
    #     return f'ffid={self.ffid}'


#: Media DB version.
DB_VERSION: int = 1

#: Global state DB lock.
lock = Lock()


@contextmanager
def get_cursor(name: str = 'media') -> Iterator[Cursor]:
    """Get "state" cursor in `with` statement."""
    with lock:
        db = db_manager[name]
        with db.cursor() as cur:
            _create_tables(cur)
            yield cur


@contextmanager
def media_cursor() -> Iterator[Cursor]:
    """Get "state" cursor in `with` statement."""
    with get_cursor('media') as cur:
        yield cur


def _update_db(cur: Cursor, ver: int) -> None:
    """Update (alter) DB to newest version."""
    # TODO: implement it (read sequencs of migration sql files)


def _create_tables(cur: Cursor) -> None:
    """Create all missing tables in "state" DB."""
    # Handle DB migration.
    update_db_version(cur, DB_VERSION)

    # Directory items info.
    cur.execute(f'CREATE TABLE IF NOT EXISTS {MediaInfoRow.__table__} ({db_create_columns(MediaInfoRow)},'
                ' UNIQUE(type, ffid), UNIQUE(type, main_ffid, season, episode))')
    # Ref lists.
    # TODO: FOREIGN KEY
    cur.execute(f'CREATE TABLE IF NOT EXISTS {RefListRow.__table__} ({db_create_columns(RefListRow)},'
                ' UNIQUE(name))')
    cur.execute(f'CREATE TABLE IF NOT EXISTS {RefListItemRow.__table__} ({db_create_columns(RefListItemRow)},'
                ' UNIQUE(list_id, order_number))')


def find_media_info(ref: MediaRef) -> Dict[MediaRef, MediaInfoRow]:
    """Find media (with denormalized refs) and return rows as dict."""
    if ref.is_normalized:
        return get_media_info([ref])

    table = MediaInfoRow.__table__
    with get_cursor() as cur:
        subshow = ref.type in ('season', 'episode')
        if subshow:
            ep_where = 'episode!=-1' if ref.type == 'episode' else 'episode=-1'
            cur.execute((f'SELECT * FROM {table}'
                         f' WHERE (type=? AND ffid=?) OR (type=? AND ffid=? AND season!=-1 AND {ep_where})'),
                        (ref.type, ref.ffid, 'show', ref.ffid))
        else:
            cur.execute(f'SELECT * FROM {table} WHERE type=? AND ffid=?', (ref.type, ref.ffid))
        row = cur.fetchone()
        if not row:
            return {}
        info = MediaInfoRow(*row[1:])
        result = {info.ref: info}
        keys = []
        if subshow:
            keys.append(('show', info.main_ffid, -1, -1))
            if ref.type == 'episode':
                keys.append(('show', info.main_ffid, info.season, -1))
        if keys:
            values = ','.join(f'({",".join(sql_dump(x) for x in key)})' for key in keys)
            cur.execute(f'SELECT * FROM {table} WHERE (type, main_ffid, season, episode) IN (VALUES {values})')
            result.update((info.ref, info) for row in cur.fetchall() for info in (MediaInfoRow(*row[1:]),))
        return result


def get_media_info(refs: Iterable[MediaRef]) -> Dict[MediaRef, MediaInfoRow]:
    """Get media info rows as dict."""
    def make_where(ref: MediaRef) -> Iterator[MediaInfoWhereValue]:
        if ref.type == 'show':
            yield ref.type, ref.ffid, -1, -1
            if ref.season:
                yield ref.type, ref.ffid, ref.season, -1
                if ref.episode:
                    yield ref.type, ref.ffid, ref.season, ref.episode
        else:
            # movies and anything else
            yield ref.type, ref.ffid, -1, -1

    keys: Set[MediaInfoWhereValue] = {key for ref in refs for key in make_where(ref)}
    if not keys:
        return {}
    values = ','.join(f'({",".join(sql_dump(x) for x in key)})' for key in keys)
    where = f'(type, main_ffid, season, episode) IN (VALUES {values})'
    # print(f'{where=}')
    with get_cursor() as cur:
        cur.execute(f'SELECT * FROM {MediaInfoRow.__table__} WHERE {where}')
        return {info.ref: info for row in cur.fetchall() for info in (MediaInfoRow(*row[1:]),)}


def set_media_info(values: Sequence[MediaInfoRow]) -> None:
    """Insert / update given media items."""
    cols = MediaInfoRow.__annotations__
    column_pat: str = MediaInfoRow.sql_columns()
    insert_pat: str = ','.join('?' for _ in cols)
    update_pat: str = ','.join(f'{k}=?' for k in cols)
    with get_cursor() as cur:
        cur.executemany((f'UPDATE OR IGNORE {MediaInfoRow.__table__} SET {update_pat}'
                         ' WHERE type=? AND main_ffid=? AND season=? AND episode=?'),
                        tuple((*val, ref.type, ref.sql_main_ffid, ref.sql_season, ref.sql_episode)
                              for val in values for ref in (val.ref,)))
        cur.executemany(f'INSERT OR IGNORE INTO {MediaInfoRow.__table__} ({column_pat}) VALUES ({insert_pat})', values)


class RefListRow(NamedTuple):
    """MediaRef list."""

    __table__ = 'ref_list'

    #: List name.
    name: str

    # Media type (coulf be empty).
    type: Optional[MediaType] = None

    #: Timestamp of last update.
    updated_at: int = 0

    @classmethod
    def sql_columns(cls) -> str:
        return db_list_columns(cls)


class RefListItemRow(NamedTuple):
    """MediaRef list."""

    __table__ = 'ref_list_items'

    #: Reference to RefListRow.
    list_id: int
    #: Item order.
    order_number: int

    # --- ref ---
    # Media type.
    type: RefType
    #: Movie or TV-show ID.
    ffid: int
    #: Season number, used with type='show' and tv_ffid.
    season: Optional[int] = None
    #: Episode number, used with type='show', tv_ffid and season.
    episode: Optional[int] = None

    #: Custom role, eg. character for cast, or job for crew.
    role: Optional[str] = None

    @property
    def ref(self) -> MediaRef:
        """Return media reference."""
        return MediaRef(type=self.type, ffid=self.ffid, season=self.season, episode=self.episode)

    @classmethod
    def sql_columns(cls) -> str:
        return db_list_columns(cls)


def get_ref_list(name: str, *, offset: int = 0, count: Optional[int] = None) -> Optional[List[MediaRef]]:
    """Return media ref list or None, if list is not exist at all or is outdated."""
    with get_cursor() as cur:
        # simpler then join
        limit = '' if count is None else f'LIMIT {count} OFFSET {offset}'
        cur.execute((f'SELECT type, ffid, season, episode FROM {RefListItemRow.__table__}'
                     f' WHERE list_id=(SELECT id FROM {RefListRow.__table__} WHERE name=?)'
                     f' ORDER BY order_number {limit}'), (name,))
        refs = [MediaRef(*row) for row in cur.fetchall()]
        if refs:
            return refs
        cur.execute(f'SELECT id FROM {RefListRow.__table__} WHERE name=?', (name,))
        return [] if cur.fetchone() else None


def get_ref_list_rows(name: str, *, offset: int = 0, count: Optional[int] = None) -> Optional[List[RefListItemRow]]:
    """Return media list items or None, if list is not exist at all or is outdated."""
    with get_cursor() as cur:
        # simpler then join
        limit = '' if count is None else f'LIMIT {count}'
        cur.execute((f'SELECT * FROM {RefListItemRow.__table__}'
                     f' WHERE list_id=(SELECT id FROM {RefListRow.__table__} WHERE name=?)'
                     f' ORDER BY order_number OFFSET {limit} {offset}'), (name,))
        rows = [RefListItemRow(*row) for row in cur.fetchall()]
        if rows:
            return rows
        cur.execute(f'SELECT id FROM {RefListRow.__table__} WHERE name=?', (name,))
        return [] if cur.fetchone() else None


def set_ref_list(name: str, refs: Iterable[MediaRef], *, type: Optional[MediaType] = None) -> None:
    """Set media ref list."""
    now = int(time_now())
    column_pat: str = RefListItemRow.sql_columns()
    with get_cursor() as cur:
        cur.execute(f'DELETE FROM {RefListItemRow.__table__}'
                    f' WHERE list_id=(SELECT id FROM {RefListRow.__table__} WHERE name=?)', (name,))
        cur.execute(f'REPLACE INTO {RefListRow.__table__} (name, type, updated_at) VALUES (?,?,?)', (name, type, now))
        lst = cur.lastrowid
        if not lst:
            cur.execute(f'DELETE FROM {RefListRow.__table__} WHERE name=?)', (name,))
            return
        values = [RefListItemRow(lst, i, ref.type, ref.ffid, ref.season, ref.episode) for i, ref in enumerate(refs)]
        cur.executemany(f'INSERT INTO {RefListItemRow.__table__} ({column_pat}) VALUES (?,?,?,?,?,?,?)', values)


if __name__ == '__main__':
    from argparse import ArgumentParser
    from ... import cmdline_argv

    p = ArgumentParser()
    p.add_argument('type', choices=('movie', 'show', 'season', 'episode'))
    p.add_argument('id', type=int)
    p.add_argument('season', type=int, nargs='?')
    p.add_argument('episode', type=int, nargs='?')
    args = p.parse_args(cmdline_argv[1:])

    # from ..info import ffinfo
    # data = ffinfo.tmdb.get_media_by_ref(MediaRef.movie(14337))
    # item = ffinfo.parse_tmdb_item(data)
    # print(item)
    print('--===--')
    ref = MediaRef(args.type, args.id, args.season, args.episode)
    # get_media_info([MediaRef.movie(14337)])
    # get_media_info([MediaRef.tvshow(84958, 1, 2)])
    # result = get_media_info([ref])
    result = find_media_info(ref)
    print(f'LEN: {len(result)}')
    print('\n'.join(f'  {m}' for m in result))
    print(result)
