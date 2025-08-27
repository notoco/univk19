# -*- coding: utf-8 -*-
"""
    FanFilm Add-on

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


import hashlib
import json
import os
import re
import time
from ast import literal_eval

try:
    from sqlite3 import OperationalError
    from sqlite3 import dbapi2 as db
except ImportError:
    from pysqlite2 import OperationalError
    from pysqlite2 import dbapi2 as db

from lib.ff import control
from .settings import settings
from lib.ff.db_connection_manager import connection_manager
from lib.ff.log_utils import LOGERROR, fflog

# Przechowujemy często używane ścieżki i ustawienia w zmiennych
data_path = control.dataPath


# --- NIGDY NIE UŻYWANA, BO NADPISANA PRZEZ TO CO PONIŻEJ ---
# def _get_connection_cursor(db_path=None):
#     if db_path is None:
#         db_path = data_path  # Użycie zmiennej zamiast ponownego wywoływania funkcji
#     conn = connection_manager.get_connection("cache", db_path)
#     return conn.cursor()


def _get_connection_cursor(db_path=None, conn=None):
    if conn is None:
        conn = _get_connection(db_path)
    return conn.cursor()


# --- NIGDY NIE UŻYWANA, BO NADPISANA PRZEZ TO CO PONIŻEJ ---
# def _hash_function(function, args, kwargs):
#     combined = f"{function.__name__}_{args}_{kwargs}"
#     return hashlib.md5(combined.encode()).hexdigest()


def _hash_function(function_instance, *args):
    return _get_function_name(function_instance) + _generate_md5(args)


# --- NIGDY NIE UŻYWANA, BO NADPISANA PRZEZ TO CO PONIŻEJ ---
# def _is_cache_valid(stored_time, duration):
#     current_time = int(time.time())
#     fflog(f"current_time: {current_time}")
#     fflog(f"stored_time: {stored_time}")
#     return (current_time - int(stored_time)) < duration


def _is_cache_valid(cached_time, cache_timeout):
    now = int(time.time())
    diff = now - cached_time
    return (cache_timeout * 3600) > diff


def _is_valid_result(result):
    return result not in [None, "", [], {}, "404:NOT FOUND"]


def create_cache_table(db_path=None, *, table="cache"):
    cursor = _get_connection_cursor(db_path)
    cursor.execute(
        f"CREATE TABLE IF NOT EXISTS {table} ("
        "key TEXT PRIMARY KEY, value TEXT, date INTEGER)"
    )


def get(function, duration, db_path=None, *args, **kwargs):
    if not settings.getBool("enableSourceCache"):
        return function(*args, **kwargs)

    key = _hash_function(function, args, kwargs)
    cache_result = cache_get(key, db_path)

    if cache_result:
        if _is_cache_valid(cache_result["date"], duration):
            try:
                if cache_result["value"] == "True":
                    return []
                return json.loads(cache_result["value"])
            except Exception:
                fflog("Błąd przetwarzania wyniku pamięci podręcznej")

    fresh_result = function(*args, **kwargs)

    if _is_valid_result(fresh_result):
        try:
            cache_insert(key, json.dumps(fresh_result), db_path)
            return fresh_result
        except Exception as e:
            fflog(f"Nie dodano poprawnego rezultatu do cache: {e}")
            fflog(f"Cache fresh result: {str(fresh_result)}")

    if cache_result:
        return json.loads(cache_result["value"])

    if fresh_result == "404:NOT FOUND":
        cache_insert(key, None)

    return None


def timeout(function_, *args):
    key = _hash_function(function_, args)
    result = cache_get(key)
    return int(result["date"]) if result else 0


def cache_existing(function, *args):
    cache_result = cache_get(_hash_function(function, args))
    return literal_eval(cache_result["value"]) if cache_result else None


def cache_get(key, db_path=None, *, table="cache", key_column="key"):
    """Return cached row."""
    # assert db_path is None or db_path == control.sourcescacheFile
    try:
        create_cache_table(db_path, table=table)
        cursor = _get_connection_cursor(db_path)
        cursor.execute(f"SELECT * FROM {table} WHERE {key_column}=?", (key,))
        return cursor.fetchone()
    except OperationalError:
        return None


def cache_value(key, db_path=None, *, table="cache", default=None, column="value", key_column="key"):
    """Return cached value (not whole row)."""
    if val := cache_get(key, db_path, table=table, key_column=key_column):
        return val[column]
    return default


def cache_insert(key, value, db_path=None, *, table="cache"):
    try:
        create_cache_table(db_path, table=table)
        cursor = _get_connection_cursor(db_path)
        now = int(time.time())
        cursor.execute(f"INSERT OR REPLACE INTO {table} (key, value, date) VALUES (?, ?, ?)", (key, value, now))
        cursor.connection.commit()
    except OperationalError:
        pass


# def remove_partial_key(partial_key, db_path=None, *, table="cache"):
#     try:
#         create_cache_table(db_path, table=table)
#         cursor = _get_connection_cursor(db_path)
#         cursor.execute(f"DELETE FROM {table} WHERE key LIKE '%{partial_key}%'")
#         cursor.connection.commit()
#     except OperationalError:
#         pass


# def remove(function, db_path=None, table="cache", *args, **kwargs):
#     create_cache_table(db_path, table=table)
#     key = _hash_function(function, args, kwargs)
#     try:
#         cursor = _get_connection_cursor(db_path)
#         cursor.execute(f"DELETE FROM {table} WHERE key={key}")
#         cursor.connection.commit()
#     except OperationalError:
#         pass


def cache_clear(flush_only=False, db_path=None, *, table="cache"):
    try:
        dbcur = _get_connection_cursor(db_path)
        if flush_only:
            dbcur.execute(f"""DELETE FROM {table}""")
            dbcur.connection.commit()
            dbcur.execute("""VACUUM""")
        else:
            dbcur.execute(f"""DROP TABLE IF EXISTS {table}""")
            dbcur.execute("""VACUUM""")
            dbcur.connection.commit()
    except Exception as e:
        fflog(f"Cache Clear Error: {e}")


def cache_clear_providers():
    try:
        cursor = _get_connection_cursor_providers()
        for t in ["cache", "temporary"]:
            cursor.execute("DROP TABLE IF EXISTS %s" % t)
            cursor.execute("VACUUM")
            cursor.connection.commit()
    except Exception as e:
        fflog(f"Cache Clear Providers Error: {e}")


def cache_clear_sources():
    try:
        for cursor, tables in [
            (_get_connection_cursor_sources(), ["rel_src", "rel_url"]),
            (_get_connection_cursor_providers(), ["temporary"])
        ]:
            for table in tables:
                cursor.execute(f"DROP TABLE IF EXISTS {table}")
                cursor.execute("VACUUM")
                cursor.connection.commit()
    except Exception as e:
        fflog(f"Cannot delete cached sources from database, error: {e}")


def cache_clear_downloader():
    try:
        create_cache_table()
        cursor = _get_connection_cursor_downloader()
        cursor.execute("DELETE FROM download_manager")
        cursor.connection.commit()
    except Exception as e:
        fflog(f"Cannot delete cached sources from database, error: {e}")


def cache_clear_search():
    try:
        cursor = _get_connection_cursor_search()
        for t in ["tvshow", "movies"]:
            cursor.execute("DROP TABLE IF EXISTS %s" % t)
            cursor.execute("VACUUM")
            cursor.connection.commit()
    except Exception as e:
        fflog(f"Cache Clear Search Error: {e}")


def cache_clear_search_by_term(term_value):
    try:
        cursor = _get_connection_cursor_search()
        for t in ["tvshow", "movies"]:
            cursor.execute("DELETE FROM %s WHERE term = ?" % t, (term_value,))
            cursor.connection.commit()
    except Exception as e:
        fflog(f"Cache Clear Search By Term Error: {e}")


def cache_clear_view():
    try:
        cursor = _get_connection_cursor_views()
        for t in ["views"]:
            cursor.execute("DROP TABLE IF EXISTS %s" % t)
            cursor.execute("VACUUM")
            cursor.connection.commit()
    except Exception as e:
        fflog(f"Cache Clear View Error: {e}")


def cache_clear_bookmarks():
    try:
        cursor = _get_connection_cursor_bookmarks()
        for t in ["bookmarks"]:
            cursor.execute("DROP TABLE IF EXISTS %s" % t)
            cursor.execute("VACUUM")
            cursor.connection.commit()
    except Exception as e:
        fflog(f"Cache Clear Bookmarks Error: {e}")


def cache_clear_all():
    # from .requests import clear_netcache
    fflog('Clearing all caches')
    # cache_clear()
    cache_clear_providers()
    cache_clear_sources()
    # clear_netcache()


def remove_partial_key(partial_key):
    try:
        create_cache_table()
        cursor = _get_connection_cursor()
        cursor.execute(f"DELETE FROM cache WHERE key LIKE '%{partial_key}%'")
        cursor.connection.commit()
    except OperationalError:
        pass


def _get_connection(db_path=None):
    if db_path is None:
        db_path = control.cacheFile

    if not control.existsPath(control.dataPath):
        control.make_dir(control.dataPath)

    conn = connection_manager.get_connection(db_path, db_path)
    conn.row_factory = _dict_factory
    return conn


def _get_connection_cursor_providers():
    conn = _get_connection(os.path.join(data_path, control.providercacheFile))
    return conn.cursor()


def _get_connection_cursor_sources():
    conn = _get_connection(os.path.join(data_path, control.sourcescacheFile))
    return conn.cursor()


def _get_connection_cursor_search():
    conn = _get_connection(os.path.join(data_path, control.searchFile))
    return conn.cursor()


def _get_connection_cursor_views():
    conn = _get_connection(os.path.join(data_path, control.viewsFile))
    return conn.cursor()


def _get_connection_cursor_bookmarks():
    conn = _get_connection(os.path.join(data_path, control.bookmarksFile))
    return conn.cursor()

def _get_connection_cursor_downloader():
    conn = _get_connection(os.path.join(data_path, control.downloadsFile))
    return conn.cursor()

def _dict_factory(cursor, row):
    return {column[0]: value for column, value in zip(cursor.description, row)}


def _get_function_name(function_instance):
    return re.sub(
        r".+\smethod\s|.+function\s|\sat\s.+|\sof\s.+", "", repr(function_instance)
    )


def _generate_md5(*args):
    md5_hash = hashlib.md5()
    try:
        [md5_hash.update(str(arg)) for arg in args]
    except Exception:
        [md5_hash.update(str(arg).encode("utf-8")) for arg in args]
    return str(md5_hash.hexdigest())


def get_old(function_, duration, *args, **table):
    try:
        response = None

        f = repr(function_)
        f = re.sub(r".+\smethod\s|.+function\s|\sat\s.+|\sof\s.+", "", f)

        a = hashlib.md5()
        for i in args:
            try:
                a.update(str(i))
            except Exception:
                a.update(str(i).encode("utf-8"))
        a = str(a.hexdigest())
    except Exception:
        pass

    try:
        table = table["table"]
    except Exception:
        table = "rel_list"

    try:
        control.make_dir(control.dataPath)
        dbcon = db.connect(control.cacheFile)
        dbcur = dbcon.cursor()
        dbcur.execute(
            "SELECT * FROM {tn} WHERE func = '{f}' AND args = '{a}'".format(
                tn=table, f=f, a=a
            )
        )
        match = dbcur.fetchone()

        try:
            response = literal_eval(match[2].encode("utf-8"))
        except AttributeError:
            response = literal_eval(match[2])

        t1 = int(match[3])
        t2 = int(time.time())
        update = (abs(t2 - t1) / 3600) >= int(duration)
        if not update:
            return response
    except Exception:
        pass

    try:
        r = function_(*args)
        if (r is None or r == []) and response is not None:
            return response
        elif r is None or r == []:
            return r
    except Exception:
        return

    try:
        r = repr(r)
        t = int(time.time())
        dbcur.execute(
            "CREATE TABLE IF NOT EXISTS {} ("
            "func TEXT, "
            "args TEXT, "
            "response TEXT, "
            "added TEXT, "
            "UNIQUE(func, args)"
            ");".format(table)
        )
        dbcur.execute(
            "DELETE FROM {0} WHERE func = '{1}' AND args = '{2}'".format(table, f, a)
        )
        dbcur.execute("INSERT INTO {} Values (?, ?, ?, ?)".format(table), (f, a, r, t))
        dbcon.commit()
    except Exception:
        pass

    try:
        return literal_eval(r.encode("utf-8"))
    except Exception:
        return literal_eval(r)
