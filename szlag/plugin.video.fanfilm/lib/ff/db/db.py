"""Sqlite3 DB manager and base utilities."""

from sys import version_info as PY
from pathlib import Path
from enum import Enum
import json
import pickle
from ast import literal_eval
from datetime import datetime, date as dt_date, time as dt_time
from sqlite3 import connect as db_connect, Connection as SqlConnection, Cursor as SqlCursor, Error as DbError, DatabaseError
from dataclasses import is_dataclass, fields as dc_fields
from contextlib import contextmanager
from threading import Lock, local as thread_local, current_thread
from time import monotonic
import atexit
from typing import Optional, Union, Any, Tuple, List, Dict, Set, Iterator, Iterable, Sequence, Mapping, Type, TypeVar, Callable, TYPE_CHECKING
from typing_extensions import Self, Literal, TypeAlias, Annotated, get_origin, get_args, cast
from wrapt.wrappers import ObjectProxy
import attrs

try:
    from ..control import dataPath as _dataPath
    DB_PATH: Path = Path(_dataPath)
except ImportError:
    from ...fake.fake_api import FF3_PATH
    DB_PATH: Path = FF3_PATH
    # DB_PATH: Path = Path('~/.kodi/userdata/addon_data/plugin.video.fanfilm').expanduser()  # DEBUG (terminal)

from ..types import is_optional, remove_optional, JsonData
from ..tricks import singleton, is_namedtuple, MISSING
from ..calendar import fromisoformat
from ..log_utils import fflog, fflog_exc, log, LOGERROR
from ..threads import Thread as FFThread
from ...defs import MediaRef  # for know types
from const import const
if TYPE_CHECKING:
    from .orm import DbTable, Statement, Result


PrimaryKey: TypeAlias = Annotated[Optional[int], 'PRIMARY KEY']
ColumnName = str
ColumnConstraint = Literal['PRIMARY KEY', 'UNIQUE', 'NOT NULL', 'CHECK']
ColumnConstraints = Dict[ColumnName, ColumnConstraint]  # TODO: remove it
ExecuteParameters: TypeAlias = Union[Sequence[Any], Mapping[str, Any]]

T = TypeVar('T')
R = TypeVar('R')
TableType = TypeVar('TableType', bound='DbTable')


class SQL(str):
    """Just str but without quoting."""
    def __repr__(self) -> str:
        return f'SQL({str.__repr__(self)})'


if TYPE_CHECKING:
    class _DbCursorBase(ObjectProxy, SqlCursor): ...
else:
    _DbCursorBase = ObjectProxy


class DbCursor(_DbCursorBase):

    __wrapped__: SqlCursor

    def __init__(self, *, db: 'Db', cursor: SqlCursor, orm: Optional[bool] = None):
        super().__init__(cursor)
        self._self_db: Db = db
        self._self_orm = None
        self._self_remote_results = ()
        self._self_closed: bool = False
        if orm is not None:
            self.orm = orm

    @property
    def db(self) -> 'Db':
        return self._self_db

    def __repr__(self) -> str:
        return f'DbCursor(db={self.db}, cursor={self.__wrapped__})'

    @property
    def orm(self) -> bool:
        """True is ORM (row as dict)."""
        if self._self_orm is None:
            return self._self_db.orm
        return self._self_orm

    @orm.setter
    def orm(self, orm: bool) -> None:
        # set row factory for this cursor only
        self._self_orm = bool(orm)
        if self._self_orm:
            # Dict row factory.
            self.row_factory = dict_factory
        else:
            # Tuple row factory (default).
            self.row_factory = None

    def _auto_orm_set(self) -> None:
        """Set DB ORM if DB needs ORM autodetect."""
        # Autodetect ORM, set True, ORM needs rows as dicts.
        if self._self_db._orm is None:
            self._self_db.orm = True
        if self._self_orm is None:
            self.orm = True

    def create_tables(self, *tables: Type['DbTable']) -> None:
        self._auto_orm_set()
        for tab in tables:
            self.execute(tab._create_table_query())

    def commit(self) -> None:
        if self._self_db.mode.is_local:
            self.__wrapped__.connection.commit()
        else:
            self._self_db.remote(self, 'commit')

    def rollback(self) -> None:
        if self._self_db.mode.is_local:
            self.__wrapped__.connection.rollback()
        else:
            self._self_db.remote(self, 'rollback')

    def execute(self, sql: str, parameters: Any = ()) -> Self:
        try:
            if self._self_db.mode.is_local:
                self.__wrapped__.execute(sql, parameters)
            else:
                self._self_db.remote(self, 'execute', sql, parameters)
        except DatabaseError as exc:
            fflog(f'DB ERROR ({exc}) on {sql!r}')
            raise
        return self

    def executemany(self, sql: str, parameters: Iterable[Any] = ()) -> Self:
        try:
            if self._self_db.mode.is_local:
                self.__wrapped__.executemany(sql, parameters)
            else:
                self._self_db.remote(self, 'executemany', sql, parameters)
        except DatabaseError as exc:
            fflog(f'DB ERROR ({exc}) on {sql!r}')
            raise
        return self

    def executescript(self, sql_script: str) -> Self:
        try:
            if self._self_db.mode.is_local:
                self.__wrapped__.executescript(sql_script)
            else:
                self._self_db.remote(self, 'executescript', sql_script)
        except DatabaseError as exc:
            fflog(f'DB ERROR ({exc}) on {sql_script!r}')
            raise
        return self

    def __iter__(self):
        if self._self_db.mode.is_local:
            return self.__wrapped__.__iter__()
        else:
            return iter(self._self_remote_results)

    def fetchall(self) -> List[Any]:
        if self._self_db.mode.is_local:
            return self.__wrapped__.fetchall()
        else:
            return list(self._self_remote_results)

    def exec(self, statement: 'Statement[R]', data: Union[None, 'DbTable', Iterable['DbTable']] = None) -> 'Result[R]':
        self._auto_orm_set()
        return statement.exec(self, data)

    def add(self, *objs: 'DbTable') -> bool:
        """Adds objects (insert or update). Returns True if DB changed."""
        self._auto_orm_set()
        changed = False
        # # check for instert many
        # if objs:
        #     typ = type(objs[0])
        #     if all(type(o) is typ and not o._has_primary_index() for o in objs):
        #         ...
        # insert or update one by one
        for obj in objs:
            obj._update_db(self.db, self)
            if obj._has_primary_index():
                changed |= obj._update(self)
            else:
                changed |= obj._insert(self)
        return changed

    def insert_many(self, *objs: 'DbTable') -> None:
        """
        Adds objects (insert only).
        All objects must be the same type.
        This method does NOT update objects ID.
        """
        self._auto_orm_set()
        # check for instert many
        if not objs:
            return
        for obj in objs:
            obj._update_db(self.db, self)
        typ = type(objs[0])
        if not all(type(o) is typ for o in objs):
            raise TypeError(f'not the same type {typ.__name__}')
        if any(o._has_primary_index() for o in objs):
            raise TypeError('has ID, can not insert')
        queries, values = zip(*(o._prepare_insert() for o in objs))
        query = queries[0]
        self.executemany(query, values)

    def get(self, table: Type[TableType], id: int) -> Optional[TableType]:
        self._auto_orm_set()
        obj = table._get(self, id)
        if obj is not None:
            obj._update_db(self.db, self)
        return obj

    @property
    def closed(self) -> bool:
        """True if cursor is closed."""
        return self._self_closed

    def close(self) -> None:
        """Close the cursor."""
        self._self_closed = True
        self.__wrapped__.close()


DbMigrateCallback: TypeAlias = Callable[
    [DbCursor,  # - DB cursor
     int,       # - old db version
     int],      # - new db version
    bool]       # return: true if success

NamedTupleType = Type


class TypeMode(Enum):
    """How to dump SQL value."""
    Auto = 'auto'
    Json = 'json'
    Ast = 'ast'
    Pickle = 'pickle'


# def pickle_load(Union[bytes, str]) -> Any:
#     if isinstance(data, str):


# Helpers for store and restore value FF3 types.
ff3_types: Set[Type] = {
    MediaRef,
}
# Helpers for store and restore value types.
known_types: Set[Type] = {
    str, int, bool, float, datetime, dt_date, dt_time,
    *ff3_types,
}
known_types_by_name: Dict[str, Union[Type, Callable]] = {typ.__name__: typ for typ in known_types}
known_types_by_name['datetime'] = fromisoformat
known_types_by_name['date'] = dt_date.fromisoformat
known_types_by_name['time'] = dt_time.fromisoformat
known_types_by_name['json'] = json.loads
known_types_by_name['pickle'] = pickle.loads
known_types_by_name['ast'] = literal_eval
# FF3 types
known_types_by_name['MediaRef'] = MediaRef.__from_json__

#: sqlite3 column type by python type.
sqlite3_column_type: Dict[Type, str] = {
    str: 'TEXT',
    int: 'INTEGER',
    float: 'REAL',
    datetime: 'TEXT',
}


def sql_dump(v: Any, *, _inner: bool = False) -> str:
    """Dump SQL value."""
    from .orm import Expr, Statement
    if v is None:
        return 'NULL'
    if type(v) is bool:
        return str(int(v))
    if type(v) in (int, float):
        return str(v)
    if isinstance(v, (Expr, Statement)):
        return str(v)
    if is_dataclass(v):
        vv = ', '.join(sql_dump(getattr(v, f.name), _inner=True) for f in dc_fields(v))
        if _inner:
            return vv
        return f'({vv})'
    if is_namedtuple(v) or isinstance(v, (tuple, list)):
        vv = ', '.join(sql_dump(f, _inner=True) for f in v)
        if _inner:
            return vv
        return f'({vv})'
    if isinstance(v, Enum):
        return repr(v.value)
    if isinstance(v, SQL):
        return v
    if isinstance(v, (datetime, dt_date, dt_time)):
        v = str(v)
    return repr(v)


def db_create_columns(named_tuple: NamedTupleType, *, primary: bool = True,
                      constraints: Optional[ColumnConstraints] = None) -> str:
    """Return sqlite3 create table columns from NamedTuple for query."""
    def get_type(name, typ) -> str:
        not_null = False
        suffix = ''
        if get_origin(typ) is Annotated:
            args = get_args(typ)
            typ, meta = args[0], args[1:]
            if 'primary_key' in meta:
                nonlocal primary
                primary = False
                suffix = 'PRIMARY KEY'
        if isinstance(typ, str):
            out = typ
        else:
            not_null = not is_optional(typ)
            typ = remove_optional(typ)
            out = sqlite3_column_type.get(typ, 'TEXT')
        if name in constraints:
            out = f'{out} {constraints.get(name, "")}'
        elif not_null and not suffix:
            out = f'{out} NOT NULL'
        if suffix:
            out = f'{out} {suffix}'
        else:
            default = defaults.get(name, MISSING)
            if default is not MISSING:
                out = f'{out} DEFAULT {sql_dump(default)}'
        return out

    if constraints is None:
        constraints = {}
    types = named_tuple.__annotations__.items()
    defaults: Dict[str, Any] = getattr(named_tuple, '_field_defaults', {})
    query = ', '.join((f'{name} {get_type(name, typ)}'
                       f' {constraints.get(name, "")}')
                      for name, typ in types)
    if primary:
        query = f'id INTEGER PRIMARY KEY, {query}'
    return query


def db_list_columns(named_tuple: NamedTupleType) -> str:
    """Return list of NamedTuple columns names."""
    return ', '.join(named_tuple.__annotations__)


def load_value(value: Any, type: Optional[str] = None) -> Any:
    """Load (parse) SQL value."""
    if value is not None:
        value = known_types_by_name.get(type or '', str)(value)
    return value


def strict_dump_value(mode: TypeMode, value: Any) -> Union[str, bytes]:
    """Dump (encode) SQL value in given mode. Return value as str or bytes."""
    if mode == TypeMode.Auto:
        mode = TypeMode.Json
    if mode == TypeMode.Json:
        return json.dumps(value)
    if mode == TypeMode.Pickle:
        return pickle.dumps(value)
    if mode == TypeMode.Ast:
        # NOTE: it could be incorrect, not all __repr__ prints AST form.
        return repr(value)
    raise ValueError(f'Unknow SQL value type {mode!r}')


def dump_value_and_type(value: Any, *, mode: Optional[Union[TypeMode, str]] = None, force_str: bool = False) -> Tuple[Any, str]:
    """Dump (encode) SQL value. Return value and type, value could be non-str."""
    type_name = None
    if type(value) in known_types:
        type_name = value.__class__.__name__
        if serializer := getattr(value, '__to_json__', None):
            value = serializer()
        elif attrs.has(value):
            value = json.dumps(attrs.asdict(value))
    elif serializer := getattr(value, '__to_json__', None):
        type_name, value = TypeMode.Json, serializer()
    elif attrs.has(value):
        type_name, value = TypeMode.Json, json.dumps(attrs.asdict(value))
    elif isinstance(value, (dict, list, tuple)):
        if mode is None:
            mode = TypeMode.Json
        elif isinstance(mode, str):
            mode = TypeMode(mode)
        type_name, value = mode.value, strict_dump_value(mode, value)
    if force_str:
        value = str(value)
    return value, type_name


def auto_migrate(cur: DbCursor, old_ver: int, ver: int) -> bool:
    """Auto migrate, find ./lib/sql/migrate/NAME.VER.sql and apply them."""
    path = Path(__file__).parent.parent.parent / 'sql' / 'migrate'
    for i in range(old_ver + 1, ver + 1):
        patch = path / f'{cur.db.name}.{i}.sql'
        if patch.exists():
            try:
                cur.executescript(patch.read_text())
            except (IOError, DbError) as exc:
                log.error(f'DB {cur.db.name} migrate FAILED on step {i}: {exc}')
                return False
            try:
                cur.execute('UPDATE db SET version=?', (i,))
            except DatabaseError as exc:
                log.warning(f'DB {cur.db.name} migrate: update version {i} FAILED: {exc}')
    return True


def update_db_version(cur: DbCursor,
                      version: int,
                      *,
                      migrate: Optional[DbMigrateCallback] = auto_migrate,
                      backup: Optional[bool] = None,
                      ) -> Optional[int]:
    """Update DB version and return old version or None, if there was no table at all."""
    cur.execute('CREATE TABLE IF NOT EXISTS db (version INTEGER)')
    cur.execute('SELECT version from db')
    old_ver_row: Union[None, Dict[str, int], Tuple[int]] = cur.fetchone()
    if old_ver_row:
        if isinstance(old_ver_row, Mapping):
            old_ver = old_ver_row['version']
        else:
            old_ver = old_ver_row[0]
        if old_ver != version:
            if backup is None:
                backup = const.dev.db.backup
            if backup and cur.db.path:
                from shutil import copy2
                if PY >= (3, 9):
                    dst = cur.db.path.with_stem(f'{cur.db.path.stem}.{old_ver}')
                else:
                    dst = cur.db.path.with_name(f'{cur.db.path.stem}.{old_ver}{cur.db.path.suffix}')
                try:
                    copy2(cur.db.path, dst)
                except IOError as exc:
                    fflog(f'[WARNING] Can NOT create DB backup of {cur.db.path} as {dst}: {exc}')
            if not callable(migrate) or migrate(cur, old_ver, version):
                cur.execute('UPDATE db SET version=?', (version,))
        return old_ver
    else:
        cur.execute('INSERT INTO db (version) VALUES (?)', (version,))
        return None


def dict_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(fields, row)}


class DbMode(Enum):
    """DB mode - how to all DBs work."""
    # DB connections are separated.
    # Every process/interpreter and every thread has own connection pool separated from another thread.
    # It forces WAL mode.
    SEPARATED = 'separated'
    # Manager locks connection's cursors to avoid corruption on concurrent access.
    MULTI_THREAD = 'multi_thread'
    # Remote access (via server) - NOT IMPLEMENTED yet.
    REMOTE_HTTP = 'remote_http'

    @property
    def is_local(self):
        return self is DbMode.SEPARATED or self is DbMode.MULTI_THREAD


class Db:
    """Proxy to database."""

    def __init__(self, *, name: str, conn: Optional[SqlConnection] = None, path: Optional[Path] = None,
                 echo: bool = False, orm: Optional[bool] = None, mode: DbMode = DbMode.SEPARATED) -> None:
        if conn is None:
            conn = DbManager()[name]._conn
        #: Mode.
        self.mode: DbMode = mode
        #: DB Connection.
        self._conn: SqlConnection = conn
        #: Thread-safe locker.
        self.lock = Lock()
        #: Database name.
        self.name: str = name
        #: Database path.
        self.path: Optional[Path] = path
        #: Use ORM (row as dict). If None, then autodetect.
        self._orm: Optional[bool] = orm
        #: Debug echo queries.
        self._echo: bool = not echo  # Force change echo detection.
        #: True if is initialized.
        self.initialized: bool = False
        # Set echo.
        self.echo = echo
        # Dict row factory.
        if self._orm:
            self._conn.row_factory = dict_factory

    def __repr__(self) -> str:
        return f'Db({self.name!r}, path={self.path!r})'

    @property
    def orm(self) -> bool:
        """True is ORM (row as dict)."""
        return self._orm or False

    @orm.setter
    def orm(self, orm: bool) -> None:
        self._orm = bool(orm)
        if self._orm:
            # Dict row factory.
            self._conn.row_factory = dict_factory
        else:
            # Tuple row factory (default).
            self._conn.row_factory = None

    @property
    def echo(self) -> bool:
        """Echo queries (debug)."""
        return self._echo

    @echo.setter
    def echo(self, echo: bool) -> None:
        """Echo queries (debug)."""
        echo = bool(echo)
        if self._echo != echo:
            self._echo = echo
            if self._echo:
                self._conn.set_trace_callback(self._log_statement)
            else:
                self._conn.set_trace_callback(None)

    def _log_statement(self, stmt: str):
        """Echo SQL statement."""
        fflog(f'(DB:{self.name}) \033[38;5;244m {stmt!r} \033[0m', stack_depth=2)

    @contextmanager
    def cursor(self, *, initialize: bool = True) -> Iterator[DbCursor]:
        with self.lock:
            cur = DbCursor(db=self, cursor=self._conn.cursor())
            try:
                if initialize and not self.initialized:
                    self._create_tables(cur)
                    self.initialized = True
                yield cur
            finally:
                try:
                    cur.connection.commit()
                finally:
                    cur.close()

    def _create_tables(self, cur: DbCursor) -> None:
        """Create tables. To override by custom classes."""

    def remote(self, db: DbCursor, method: str, query: str = '', params: Optional[Iterable[Any]] = None) -> None:
        ...


@attrs.define
class DbLocal:
    ff_db_manager_connections: Dict[Path, Db] = attrs.Factory(dict)


@singleton
class DbManager:
    """Manager for all databases."""

    def __init__(self, path: Optional[Path] = None, *, echo: Optional[bool] = None, mode: DbMode = DbMode.SEPARATED):
        # [[ Note, it's singleton, this __init__ is called only once. ]]
        #: Mode.
        self._mode: DbMode = mode
        #: All connections if mode is NOT "separated".
        self._local: Optional[DbLocal] = None
        #: Lack for multithread access.
        self.lock = Lock()
        #: Base path.
        self.path: Path = DB_PATH if path is None else path
        #: Debug echo queries.
        self.echo: bool = const.dev.db.echo if echo is None else bool(echo)
        # Register cleanup on interpreter exit.
        atexit.register(self.clear)

    @property
    def mode(self) -> DbMode:
        """Reads DB access mode."""
        return self._mode

    @property
    def connections(self) -> Dict[Path, Db]:
        """DB connections pool."""
        if self._local is None:
            if self._mode is DbMode.SEPARATED:
                self._local = cast(DbLocal, thread_local())
            else:
                self._local = DbLocal()
        if self._mode is DbMode.SEPARATED:
            new = {}
            if new is self._local.__dict__.setdefault('ff_db_manager_connections', new):
                th = current_thread()
                if isinstance(th, FFThread):
                    th.on_finished.add(self.clear)
        return self._local.ff_db_manager_connections

    def clear(self) -> None:
        """Clear manager, close all DB connections."""
        with self.lock:
            connections = self.connections
            for db in connections.values():
                db._conn.close()
            connections.clear()

    def _create_connection(self, name: str, path: Path, mode: DbMode) -> Db:
        """Create new connection. User have to handle concurrency (locks)."""
        timestamp = monotonic()
        if self._mode is DbMode.SEPARATED:
            log_suffix = f' @ thread({current_thread().name})'
        else:
            log_suffix = ''
        try:
            fflog(f'[DB] new connection {name!r} to {path}{log_suffix}')
            path.parent.mkdir(parents=True, exist_ok=True)
            timeout = const.tune.db.connection_timeout
            conn = db_connect(path, check_same_thread=False, timeout=timeout)
            fflog(f'[DB] connected {name!r} to {path}: {conn}{log_suffix}')
        except Exception:
            log(f'[DB] Connection to DB {path}{log_suffix} fails.', LOGERROR)
            raise
        connection_time = monotonic() - timestamp
        if connection_time > 1.0:
            fflog('[WARNING] Connection to DB {path}{log_suffix} took {connection_time:.1f} seconds')
        # force WAL for separated access
        if self._mode is DbMode.SEPARATED:
            conn.execute('PRAGMA journal_mode=WAL')
        # DB wrapper
        db = Db(name=name, conn=conn, path=path, echo=self.echo, mode=mode)
        return db

    def path_for_db(self, name: str) -> Path:
        """Return path to DB."""
        return self.path / f'{name}.db'

    def remove_db(self, name: str) -> bool:
        """Remove database."""
        path = self.path_for_db(name)
        with self.lock:
            connections = self.connections
            if db := connections.pop(path, None):
                db._conn.close()
            if path.exists():
                try:
                    path.unlink()
                    return True
                except OSError:
                    fflog_exc()
        return False

    def _get(self, name: str) -> Tuple[Db, bool]:
        """Get or open DB connection."""
        just_opened = False
        path = self.path_for_db(name)
        with self.lock:
            connections = self.connections
            db = connections.get(path)
            if db is None:
                db = self._create_connection(name, path, mode=self._mode)
                connections[path] = db
                just_opened = True
            return db, just_opened

    def __getitem__(self, name: str) -> Db:
        """Get or open DB connection."""
        db, _ = self._get(name)
        return db

    def __delitem__(self, name: str) -> None:
        """Close connection."""
        path = self.path_for_db(name)
        with self.lock:
            db = self.connections.pop(path, None)
            if db is not None:
                db._conn.close()

    @contextmanager
    def db(self, name: str) -> Iterator[Db]:
        """Access to db with state statement."""
        db, should_close = self._get(name)
        try:
            yield db
        finally:
            if should_close:
                del self[name]


@contextmanager
def get_cursor(name: str) -> Iterator[DbCursor]:
    """Open connection and get cursor. After `with` close cursor and connection."""
    with DbManager().db(name) as db:
        with db.cursor() as cur:
            yield cur


#: Global manager. Alternately you can use just DbManager(), it's a singleton.
db_manager = DbManager()


if __name__ == '__main__':
    ...
