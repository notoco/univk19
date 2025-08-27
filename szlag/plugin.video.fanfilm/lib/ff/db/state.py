
from sqlite3 import IntegrityError
from time import time as cur_time, sleep
from itertools import chain
from dataclasses import InitVar
from datetime import datetime, date as dt_date
# from functools import reduce
# from operator import sub
from enum import Enum
import json
from random import randrange
from contextlib import contextmanager
from typing import Optional, Union, Any, Tuple, List, Dict, Set, Sequence, Mapping, Iterable, Iterator, ContextManager, overload
from typing import Type, NamedTuple, TypeVar, TYPE_CHECKING
from typing_extensions import Self, TypeAlias, Literal, Annotated, get_args as get_typing_args, cast
if TYPE_CHECKING:
    from ..info import FFItem
    from ..routing import URL

# from .control import dataPath as data_path
from .db import db_manager, load_value, dump_value_and_type, Lock, sql_dump, update_db_version, DbCursor, PrimaryKey, SQL
from . import orm
from ..calendar import utc_timestamp
from ..threads import Thread, Event
from ..kotools import xsleep
from ...defs import MediaType, RefType, MediaRef, XMediaRef
from ..log_utils import fflog
from ...service import SERVICE
from const import const, StateMode

# to avoid collision with "def set()"
# TODO: reanme function
from builtins import set as _set


T = TypeVar('T')

#: State DB version.
DB_VERSION: int = 6


class RowInfo(NamedTuple):
    """State row data."""
    key: str
    value: Any
    type: str
    updated_at: float


class Job(NamedTuple):
    """Job to execute."""
    command: str
    args: Any
    updated_at: float
    sender: str


class DirectoryListType(Enum):
    """Type of plugin folder."""
    LAST = 'last'


class DirectoryList(orm.DbTable):
    """Plugin folder entry."""
    __tablename__ = 'directory'
    id: PrimaryKey = None
    url: str
    type: DirectoryListType
    has_media: bool = False
    media_type: MediaType = ''  # type: ignore  - empyy string is better then NULL
    ref_type: RefType = ''
    timestamp: float = 0
    trakt_timestamp: float = 0
    # entries: List['DirectoryListEntry'] = relationship(back_populates='directory')


class DirectoryListEntry(orm.DbTable):
    """Plugin folder entry."""
    __tablename__ = 'directory_content'
    id: PrimaryKey = None
    directory_id: Optional[int] = orm.field(foreign_key='directory.id')
    # directory: DirectoryList = relationship(back_populates='entries')
    order: int
    xref: XMediaRef = orm.MISSING
    label: str = ''

    @property
    def ref(self) -> MediaRef:
        """Get media reference."""
        return MediaRef.from_sql_ref(self.xref)


#: Global state DB lock.
lock = Lock()


def sql_where(v):
    """Dump SQL where value (=V, IN NULL)."""
    if v is None:
        return 'IS NULL'
    return f'={sql_dump(v)}'


@contextmanager
def get_cursor(name: str = 'state', *, orm: bool = False) -> Iterator[DbCursor]:
    """Get "state" cursor in `with` statement."""
    with lock:
        db = db_manager[name]
        with db.cursor(initialize=False) as cur:
            if not db.initialized:
                _create_tables(cur)
                db.initialized = True
            cur.orm = orm
            yield cur


class Access(orm.DbTable):

    __tablename__ = 'access'

    id: PrimaryKey = None
    module: Annotated[str, 'UNIQUE']
    value: int
    state: Literal['ready', 'locking'] = 'ready'


def _create_tables(cur: DbCursor) -> None:
    """Create all missing tables in "state" DB."""
    # Handle DB migration.
    update_db_version(cur, DB_VERSION)

    # value, args as INTEGER to keep all types (TODO: RTFM)
    cur.create_tables(Access, DirectoryList, DirectoryListEntry)
    cur.execute('CREATE TABLE IF NOT EXISTS access '
                '(id INTEGER PRIMARY KEY, module TEXT UNIQUE, value INTEGER, state TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS state '
                '(id INTEGER PRIMARY KEY, module TEXT, key TEXT, value INTEGER, type TEXT, updated_at INTEGER,'
                ' UNIQUE(module, key))')
    cur.execute('CREATE TABLE IF NOT EXISTS jobs '
                '(id INTEGER PRIMARY KEY, module TEXT, command TEXT, args INTEGER, updated_at INTEGER, sender TEXT)')


# -----  access  -----


def _access(module: str, add: Literal[1, -1]) -> bool:
    """Enter into module section. Return if have access."""
    # TODO: use: UPDATE access SET value=value+1
    with get_cursor() as cur:
        cur.execute('INSERT OR IGNORE INTO access (module, value, state) VALUES (?, 0, "ready")', (module,))
        for _ in range(3):
            ok = cur.execute('UPDATE access SET state="locking" WHERE module=? AND state="ready"', (module,))
            if ok:
                cur.execute('SELECT id, value FROM access WHERE module=?', (module,))
                aid, value = cur.fetchone()
                value = max(0, value + add)
                cur.execute('UPDATE access SET value=?, state="ready" WHERE id=?', (value, aid))
                # value must be 1 for enter (+1) or zero for exit (-1)
                return value == (add > 0)
            # random sleep to get another try (10..50 ms)
            sleep(randrange(10, 50) / 1000)
        # no break, all tries failed
        raise RuntimeError(f'Can get {module} DB access')


def enter(module: str) -> bool:
    """Enter into module section. Return if have access (first enter, was unlocked)."""
    return _access(module, +1)


def exit(module: str) -> bool:
    """Enter into module section. Return if has access (last exit, leave unlocked)."""
    return _access(module, -1)


def get_access_value(module: str) -> int:
    """Return module access level."""
    with get_cursor() as cur:
        cur.execute('SELECT value FROM access WHERE module=?', (module,))
        row = cur.fetchone()
        return row[0] if row else 0


# -----  state (get, set)  -----

def _state_mode(*, module: Optional[str], mode: Optional[StateMode] = None) -> StateMode:
    """Determinate status mode / protocol."""
    if mode is None:
        mode = const.tune.db.module_state_mode.get(module or '', const.tune.db.state_mode)
    return mode


def set(key: str, value: Any, *, module: str, mode: Optional[StateMode] = None, connect: bool = True) -> bool:
    """Set value."""
    now = cur_time()
    mode = _state_mode(module=module, mode=mode)
    value, type_name = dump_value_and_type(value)
    if mode is StateMode.SERVICE:
        if SERVICE:
            from ...service.main import works
            works.state.set_variable(module=module, key=key, value=value, type=type_name, updated_at=now)
        else:
            from ...service.client import service_client, StateVar
            service_client.state_set([StateVar(module=module, key=key, value=value, type=type_name, updated_at=now)], connect=connect)
    else:
        with get_cursor() as cur:
            cur.execute('INSERT OR REPLACE INTO state (key, value, type, updated_at, module) VALUES (?, ?, ?, ?, ?)',
                        (key, value, type_name, now, module))
    return True


def multi_set(values: Union[Iterable[Tuple[str, Any]], Mapping[str, Any]],
              *,
              module: str,
              mode: Optional[StateMode] = None,
              connect: bool = True,
              ) -> bool:
    """Set many values: list of (key, value) pairs or dict."""
    now = cur_time()
    if isinstance(values, Mapping):
        value_dict: Mapping[str, Any] = values
        values = value_dict.items()
    db_values = [(key, value, type_name, now, module)
                 for key, val in values for value, type_name in (dump_value_and_type(val),)]
    mode = _state_mode(module=module, mode=mode)
    if mode is StateMode.SERVICE:
        from ...service.misc import StateVar
        variables = [StateVar(module=module, key=key, value=value, type=type_name, updated_at=now)
                     for key, value, type_name, now, module in db_values]
        if SERVICE:
            from ...service.main import works
            works.state.multi_set(variables)
        else:
            from ...service.client import service_client
            service_client.state_set(variables, connect=connect)
    else:
        with get_cursor() as cur:
            cur.executemany('INSERT OR REPLACE INTO state (key, value, type, updated_at, module) VALUES (?, ?, ?, ?, ?)',
                            db_values)
    return True


def get_info(key: str, *, module: str, mode: Optional[StateMode] = None) -> Optional[RowInfo]:
    """Get row info."""
    mode = _state_mode(module=module, mode=mode)
    if mode is StateMode.SERVICE:
        if SERVICE:
            from ...service.main import works
            var = works.state.get(module=module, key=key)
            if var is None:
                return None
            value = load_value(var.value, type=var.type)
            return RowInfo(key=var.key, value=value, type=var.type, updated_at=var.updated_at)
        else:
            from ...service.client import service_client
            for var in service_client.state_get(module=module, key=key):
                value = load_value(var.value, type=var.type)
                return RowInfo(key=var.key, value=value, type=var.type, updated_at=var.updated_at)
    else:
        with get_cursor() as cur:
            cur.execute('SELECT key, value, type, updated_at FROM state WHERE key=? AND module=?', (key, module))
            row = cur.fetchone()
            if row is None:
                return None
            key, value, type, updated_at = row
            value = load_value(value, type=type)
            return RowInfo(key, value, type, updated_at)


@overload
def get(key: str, *, module: str, cls: Type[T], default: Optional[T] = None, mode: Optional[StateMode] = None, from_boot: bool = False) -> Optional[T]: ...


@overload
def get(key: str, *, module: str, cls: None = None, default: Any = None, mode: Optional[StateMode] = None, from_boot: bool = False) -> Any: ...


def get(key: str, *, module: str, cls: Optional[Type[T]] = None, default: Any = None, mode: Optional[StateMode] = None, from_boot: bool = False) -> Any:
    """Get value (without info)."""
    row = get_info(key, module=module, mode=mode)
    if not row:
        return default
    if from_boot:
        from ..kotools import kodi_startup_timestamp
        startup = kodi_startup_timestamp().timestamp()
        if row.updated_at and row.updated_at < startup:
            startup = datetime.fromtimestamp(startup)
            updated = datetime.fromtimestamp(row.updated_at)
            # outdated, return default
            return default
    if cls is not None:
        return cls(**row.value)
    return row.value


# def multi_get(keys: List[str], *, module: Optional[str] = None) -> Any:
#     """Get list of values (without info)."""
#     row = get_info(key)
#     return row and row.value


def get_all(*, module: Optional[str] = None, mode: Optional[StateMode] = None) -> Dict[str, Any]:
    """Get all module values as dict."""
    mode = _state_mode(module=module, mode=mode)
    if mode is StateMode.SERVICE:
        if SERVICE:
            from ...service.main import works
            return {var.key: load_value(var.value, type=var.type) for var in works.state.get_all(module=module or '')}
        else:
            from ...service.client import service_client
            return {var.key: load_value(var.value, type=var.type) for var in service_client.state_get(module=module or '')}
    else:
        with get_cursor() as cur:
            cur.execute('SELECT key, value, type FROM state WHERE module=?', (module,))
            return {key: load_value(value, type=type)
                    for row in cur.fetchall()
                    for key, value, type in (row,)}


def delete(key: str, *, module: str, mode: Optional[StateMode] = None) -> None:
    """Delete value."""
    mode = _state_mode(module=module, mode=mode)
    if mode is StateMode.SERVICE:
        if SERVICE:
            from ...service.main import works
            works.state.delete(module=module, key=key)
        else:
            from ...service.client import service_client
            service_client.state_delete(module=module, key=key)
    else:
        with get_cursor() as cur:
            cur.execute('DELETE FROM state WHERE key=? AND module=?', (key, module))


def delete_like(like: str, *, module: str, mode: Optional[StateMode] = None) -> None:
    """Delete all values like `like` (SQL %-LIKE)."""
    mode = _state_mode(module=module, mode=mode)
    if mode is StateMode.SERVICE:
        if SERVICE:
            from ...service.main import works
            works.state.delete_like(module=module, key=like)
        else:
            fflog.error('state.delete_like() with StateMode.SERVICE is NOT supported yet')
    else:
        with get_cursor() as cur:
            cur.execute('DELETE FROM state WHERE key LIKE ? AND module=?', (like, module))


def delete_all(*, module: str, mode: Optional[StateMode] = None) -> None:
    """Delete all values in module."""
    mode = _state_mode(module=module, mode=mode)
    if mode is StateMode.SERVICE:
        if SERVICE:
            from ...service.main import works
            works.state.delete_all(module=module)
        else:
            from ...service.client import service_client
            service_client.state_delete(module=module or '')
    else:
        with get_cursor() as cur:
            cur.execute('DELETE FROM state WHERE module=?', (module,))


def wait_for_value(key: str, timeout: Optional[float] = None, *, module: str, value: Any = True, mode: Optional[StateMode] = None) -> bool:
    """Wait for DB state value."""
    mode = _state_mode(module=module, mode=mode)
    if mode is StateMode.SERVICE:
        from ...service.client import service_client
        service_client.state_wait(module=module, key=key, value=value, timeout=timeout)
    else:
        def wait():
            while not cancel.is_set():
                xsleep(const.tune.db.state_wait_read_interval, cancel_event=cancel)
                if get(key, module=module, mode=mode) == value:
                    event.set()
                    break

        if get(key, module=module, mode=mode) == value:
            return True
        event = Event()
        cancel = Event()
        th = Thread(target=wait)
        th.start()
        result = event.wait(timeout=timeout)
        cancel.set()
        th.join()
        return result


def with_var(key: str, *, module: str, mode: Optional[StateMode] = None) -> ContextManager[None]:
    """Statement with module.key variable. Inside block variable has value True.

    >>> with state.with_var('running', module='my_mod'):
    ...     do_your_job()
    """
    mode = _state_mode(module=module, mode=mode)
    if mode is StateMode.SERVICE:
        from ...service.client import service_client
        return service_client.state_with(module=module, key=key)
    else:
        @contextmanager
        def statement() -> Iterator[None]:
            set(module=module, key=key, value=True, mode=mode)
            try:
                yield None
            finally:
                set(module=module, key=key, value=False, mode=mode)
        return statement()


# -----  jobs  -----


def get_job(module: str, *, preview: bool = False) -> Optional[Job]:
    """Pop and return first pending job or None. Job is removed (if `preview` is False)."""
    with get_cursor() as cur:
        cur.execute('SELECT * FROM jobs WHERE module=?', (module,))
        row = cur.fetchone()
        if row is None:
            return None
        jid, mod, cmd, args, updated_at, sender = row
        if not preview:
            cur.execute('DELETE FROM jobs WHERE id=?', (jid,))
        if args:
            args = tuple(json.loads(args))
        else:
            args = ()
        return Job(cmd, args, updated_at, sender)


def jobs(module: str) -> Iterator[Job]:
    """Yield all pending jobs."""
    while True:
        job = get_job(module)
        if job is None:
            return
        yield job


def add_job(module: str, command: str, args: Optional[Tuple[Any, ...]] = None, sender: Optional[str] = None, *,
            unique: bool = False) -> bool:
    """Add job for module. Return True if it's a first job."""
    with get_cursor() as cur:
        now: float = cur_time()
        args_str = json.dumps(args) if args else None
        if unique:
            cur.execute('DELETE FROM jobs WHERE module=? AND command=? AND args=?', (module, command, args_str))
        cur.execute('INSERT INTO jobs (module, command, args, updated_at, sender) VALUES (?, ?, ?, ?, ?)',
                    (module, command, args_str, now, sender))
        cur.execute('SELECT COUNT(*) FROM jobs WHERE module=?', (module,))
        row = cur.fetchone()
        return row and row[0] > 0


# -----  directories  -----


def directory_info(*,
                   type: DirectoryListType = DirectoryListType.LAST,
                   ) -> Optional[DirectoryList]:
    """Get info about stored directory by its type."""
    with get_cursor(orm=True) as cur:
        return cur.exec(orm.select(DirectoryList).where(DirectoryList.type == type)).first()


def load_directory(*,
                   type: DirectoryListType = DirectoryListType.LAST,
                   ) -> Sequence['FFItem']:
    ...


def save_directory(url: Union[str, 'URL'],
                   items: Iterable[Optional['FFItem']],
                   *,
                   type: DirectoryListType = DirectoryListType.LAST,
                   now: Union[None, datetime, float] = None,
                   ) -> None:
    """Save kodi folder to DB."""
    now = utc_timestamp(now)
    trakt_timestamp = get('timestamp', module='trakt') or 0
    items = cast(Tuple['FFItem', ...], tuple(it for it in items if it))
    media_types = _set(get_typing_args(MediaType))  # ?? WTF! Ehy pyright screems!
    has_media = any(it.ref.type in media_types for it in items)
    media_type: MediaType = ''
    ref_type: RefType = ''
    if items:
        first_type = items[0].ref.real_type or ''
        if all(it_type == first_type for it in items if (it_type := it.ref.real_type or '')):
            ref_type = first_type
        if ref_type in media_types:
            media_type = cast(MediaType, ref_type)
    with get_cursor(orm=True) as cur:
        folder = DirectoryList(url=str(url or ''), type=type, timestamp=now, trakt_timestamp=trakt_timestamp,
                               has_media=has_media, media_type=media_type, ref_type=ref_type)
        if old := cur.exec(orm.select(DirectoryList).where(DirectoryList.type == type)).first():
            folder.id = old.id
        cur.add(folder)
        cur.commit()
        cur.exec(orm.delete(DirectoryListEntry).where(DirectoryListEntry.directory_id == folder.id))
        cur.insert_many(*(DirectoryListEntry(directory_id=folder.id, order=i, xref=it.ref.xref, label=it.label)
                          for i, it in enumerate(items)))


# ---------


if __name__ == '__main__':
    from argparse import ArgumentParser
    from ... import cmdline_argv
    p = ArgumentParser()
    pp = p.add_subparsers(title='command', dest='cmd')
    p_ac = pp.add_parser('access')
    args = p.parse_args(cmdline_argv[1:])

    if args.cmd == 'access':
        print(enter('test'))
        print(enter('test'))
        print(exit('test'))
        print(exit('test'))
