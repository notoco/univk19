"""History module (played from KodiDb)."""

from typing import List, Sequence, TYPE_CHECKING
from datetime import datetime

from .core import Indexer
from .folder import item_folder_route, pagination, list_directory
from .lists import ListsInfo
from .navigator import nav
from ..ff.item import FFItem
from ..ff.routing import info_for, route
from ..ff.kodidb import video_db
# from ..ff.log_utils import fflog
from ..kolang import L
from const import const
if TYPE_CHECKING:
    from ..defs import MediaPlayType


class History(Indexer):
    """History indexer."""

    @route('/')
    def root(self) -> None:
        """Main history menu."""
        linfo = ListsInfo()
        with list_directory() as kdir:
            kdir.folder(L(32001, 'Movies'), info_for(self.movies), thumb='movies/history.png', icon='DefaultMovies.png')
            kdir.folder(L(32002, 'TV Shows'), info_for(self.tvshows), thumb='tvshows/history.png', icon='DefaultTVShows.png')
            if linfo.trakt_enabled():
                kdir.folder(L(30469, 'Trakt Movies'), info_for(nav.trakt.ulist, media='movie', list_type='history'), thumb='services/trakt/history.png')
                kdir.folder(L(30470, 'Trakt TV Shows'), info_for(nav.trakt.ulist, media='show', list_type='history'), thumb='services/trakt/history.png')

    @item_folder_route('/movie', limit=const.indexer.history.limit)
    @pagination(limit=const.indexer.movies.discovery_scan_limit)
    def movies(self) -> Sequence[FFItem]:
        """Show watched movies."""
        return self._get_watched_items(media_type='movie')

    @item_folder_route('/show', limit=const.indexer.history.limit)
    @pagination(limit=const.indexer.tvshows.discovery_scan_limit)
    def tvshows(self) -> Sequence[FFItem]:
        """Show watched TV show episodes directly."""
        return self._get_watched_items(media_type='episode')

    def _get_watched_items(self, *, media_type: 'MediaPlayType') -> List[FFItem]:
        """Get watched media items from Kodi database with pagination."""
        partial = const.indexer.history.show_watching
        skip_broken = True  # There is no sense to add this to const IMHO.
        plays = (play for play in video_db.get_plays() if play.ref.real_type == media_type)
        plays = (play for play in plays if play.play_count or (partial and play.has_progress))
        if skip_broken:
            # Broken items – invalid ffid
            from ..defs import VideoIds
            plays = (play for play in plays if play.ref.ffid not in VideoIds.KODI)
        plays = (play for play in plays if play.play_count or (partial and play.has_progress))
        plays = sorted(plays, key=lambda x: x.played_at or 0, reverse=True)
        return [play.ffitem(role=const.indexer.history.role) for play in plays]
