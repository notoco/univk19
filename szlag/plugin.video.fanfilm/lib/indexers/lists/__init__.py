from __future__ import annotations


class ListsInfo:
    """Simple class to check if "my lists" are enabled."""

    def enabled(self) -> bool:
        """Return True if any of list list service is enabled."""
        return self.trakt_enabled() or self.tmdb_enabled() or self.imdb_enabled() or self.own_enabled()

    def trakt_enabled(self) -> bool:
        from ...ff.trakt import trakt
        return bool(trakt.credentials())

    def tmdb_enabled(self) -> bool:
        from ...ff.tmdb import tmdb
        return bool(tmdb.credentials())

    def imdb_enabled(self) -> bool:
        from ...ff.settings import settings
        return bool(settings.getString('imdb.user'))

    def mdblist_enabled(self, *, premium: bool | None = None) -> bool:
        from const import const
        from ...ff.settings import settings
        if const.indexer.mdblist.enabled and (const.dev.mdblist.api_key or settings.getString("mdblist.api_key")):
            if premium is not None:
                from .mdblist import mdblist
                return mdblist.is_premium() == premium
            return True
        return False

    def own_enabled(self) -> bool:
        from const import const
        return bool(const.indexer.own.enabled)
