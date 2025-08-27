from sqlite3 import connect as db_connect, Connection
import threading
from pathlib import Path
from typing import Optional, Union, NamedTuple

import xbmcvfs

from lib.ff import control
from lib.ff.log_utils import LOGERROR, fflog


DbPath = Union[Path, str]


class ConnectionInfo(NamedTuple):
    #: DB connection.
    conn: Connection
    #: DB name.
    name: str
    #: Path to database file.
    path: DbPath


class ConnectionManager:
    """DB connection manager. Singleton."""

    #: Singleton instance.
    _instance: 'ConnectionManager' = None

    def __new__(cls) -> 'ConnectionManager':
        if cls._instance is None:
            fflog(f"Creating a singleton instance of ConnectionManager in thread {threading.get_ident()}")
            cls._instance = super(ConnectionManager, cls).__new__(cls)
            cls._instance.thread_connections = threading.local()
            cls._instance.thread_connections.conns = {}
        return cls._instance

    def _init_connection_params(self, conn: Connection) -> None:
        pass
        # --- i tak nie działa, bo aplikuje się do tabeli "main" a nie tej, która jest tworzona ---
        # settings = [
        #     "PRAGMA page_size = 32768",
        #     "PRAGMA journal_mode = OFF",
        #     "PRAGMA synchronous = OFF",
        #     "PRAGMA temp_store = memory",
        #     "PRAGMA mmap_size = 0",
        #     "PRAGMA cache_size = -2048",
        #     "PRAGMA foreign_keys = OFF",
        # ]
        # for setting in settings:
        #     conn.execute(setting)

    def _create_connection(self, db_path: DbPath):
        try:
            conn = db_connect(db_path, timeout=60)
            self._init_connection_params(conn)
            return conn
        except Exception as e:
            fflog(f"Error while creating connection: {e}", LOGERROR)
            raise

    def get_connection(self, name, db_path: Optional[DbPath] = None) -> Connection:
        """
        Return opened connection. Create DB if missing.

        If `db_path` is None, database `name.db` is created in data folder.
        """
        if not xbmcvfs.exists(control.dataPath):
            xbmcvfs.mkdir(control.dataPath)
        connections = getattr(self.thread_connections, "conns", None)
        if connections is None:
            self.thread_connections.conns = connections = {}

        if db_path is None:
            db_path = Path(control.dataPath) / f'{name}.db'

        path = db_path if db_path == ":memory:" else Path(db_path)
        conn: ConnectionInfo = connections.get(name)
        if conn is None:
            conn = ConnectionInfo(self._create_connection(path), name, path)
            connections[name] = conn
        else:
            assert conn.path == path

        # Logowanie w trybie debug
        # len(connections)
        # ", ".join(connections.keys())
        # fflog(
        #     f"Aktywne połączenia: {active_connections}, Bazy danych: {active_databases}"
        # )

        return conn.conn

    def close_all(self):
        connections = getattr(self.thread_connections, "conns", {})
        for conn in connections.values():
            conn.conn.close()
        self.thread_connections.conns = {}


connection_manager = ConnectionManager()
