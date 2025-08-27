from __future__ import annotations
from typing import TYPE_CHECKING
from lib.ff.log_utils import fflog_exc, fflog
from . import control
from .db_connection_manager import connection_manager
import time
if TYPE_CHECKING:
    from sqlite3 import Connection, Cursor


class ViewManager:
    def __init__(self):
        self.view_cache = {}

    def get_cursor(self) -> tuple[Connection, Cursor]:
        dbcon = connection_manager.get_connection("views", control.viewsFile)
        dbcur = dbcon.cursor()
        try:
            dbcur.execute(
                """
                CREATE TABLE IF NOT EXISTS views (
                    skin TEXT,
                    view_type TEXT,
                    view_id TEXT,
                    UNIQUE(skin, view_type)
                )
                """
            )
        except Exception as e:
            fflog_exc(f"Error creating views table: {e}")
        return dbcon, dbcur

    def add_custom_view(self, content):
        dbcon = None
        try:
            skin = control.skin
            record = (skin, content, str(control.getCurrentViewId()))
            control.make_dir(control.dataPath)

            dbcon, dbcur = self.get_cursor()
            dbcur.execute(
                "DELETE FROM views WHERE skin = ? AND view_type = ?", (record[0], record[1])
            )
            dbcur.execute("INSERT INTO views VALUES (?, ?, ?)", record)
            dbcon.commit()

            # Czyszczenie cache po dodaniu nowego widoku
            self.view_cache.clear()

            view_name = control.infoLabel("Container.Viewmode")
            skin_name = control.addon(skin).getAddonInfo("name")
            skin_icon = control.addon(skin).getAddonInfo("icon")

            control.infoDialog(view_name, heading=skin_name, sound=True, icon=skin_icon)
        except Exception as e:
            fflog_exc(f"Error in add_custom_view: {e}")

    def set_custom_view(self, content, view_dict=None):
        dbcon = None
        try:
            skin = control.skin

            if view_dict and skin in view_dict:
                control.execute(f"Container.SetViewMode({view_dict[skin]})")
                return

            view = self.view_cache.get((skin, content))

            if view is None:
                try:
                    dbcon, dbcur = self.get_cursor()
                    dbcur.execute(
                        "SELECT view_id FROM views WHERE skin = ? AND view_type = ?",
                        (skin, content),
                    )
                    view_row = dbcur.fetchone()
                    view = view_row[0] if view_row else None

                    self.view_cache[(skin, content)] = view
                except Exception as e:
                    fflog_exc(f"Database error in set_custom_view: {e}")

            if view is not None:
                for _ in range(50):  # max 500 ms czekania
                    time.sleep(0.01)
                    if control.condVisibility(f"Container.Content({content})"):
                        break

                if control.condVisibility(f"Container.Content({content})"):
                    control.execute(f"Container.SetViewMode({view})")
        except Exception as e:
            fflog_exc(f"Unexpected error in set_custom_view: {e}")


# Inicjalizacja managera widoków
view_manager = ViewManager()
