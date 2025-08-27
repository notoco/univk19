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

from enum import Enum
from typing import Optional, Any, Tuple, List, Sequence, TYPE_CHECKING
from datetime import date as dt_date, timedelta

from ..kolang import L
from ..defs import MediaRef
from ..ff.item import FFItem
from ..ff.info import ffinfo
from ..ff.menu import directory, KodiDirectory, ContextMenuItem, CMenu
from ..ff.routing import route, subobject, url_for, info_for, PathArg
from ..ff.tmdb import tmdb
from ..ff.settings import settings
from ..ff.control import is_plugin_folder
from ..ff.tricks import adict, FormatObjectGetter
from ..api.tmdb import DiscoveryFilters
from ..ff.log_utils import fflog
from .navigator import play, nav
from .core import MainIndexer, no_content
from .folder import list_directory, item_folder_route, pagination, mediaref_endpoint
from .lists import ListsInfo
from .search import Search
from const import const
if TYPE_CHECKING:
    from ..ff.routing import EndpointInfo


class Flatten(Enum):
    """Flat seasons (show eposodes directly in tvshow)."""
    Never = 0
    Single = 1
    Always = 2

    @classmethod
    def _missing_(cls, value: Any) -> 'Flatten':
        fflog.error(f'ERROR: Unknown type of Faltten: {value!r}')
        return Flatten.Never


class TVShows(MainIndexer):
    """TV-show navigation."""

    MODULE = 'tvshows'  # to read const settings
    TYPE = 'show'
    VIDEO_TYPE = 'episode'
    TMBD_CONTENT = 'tv'
    TRAKT_CONTENT = 'shows'
    VOTE_COUNT_SETTING = 'tmdbtv.vote'
    VIEW = 'tvshows'
    IMAGE = 'tvshows/main.png'

    @route('/')
    def home(self) -> None:
        """Create root / main menu."""
        linfo = ListsInfo()
        # u = url_for(self.popular)
        with list_directory(view='addons', icon='tvshows/main.png') as kdir:
            if const.indexer.tvshows.joke.production_company:
                kdir.folder(L(30138, 'Companies'), url_for(self.joke, type='production_company'))
            kdir.folder(L(32010, 'Search'), self.search, thumb='tvshows/search.png')
            if linfo.enabled():
                kdir.folder(L(32004, 'My TV Shows'), self.lists, thumb='tvshows/my.png', icon='DefaultVideoPlaylists.png')
            kdir.folder(L(32805, 'Episodes in progress'), self.resume, thumb="tvshows/progress.png")
            kdir.folder(L(32017, 'People Watching'), info_for(self.trending), thumb='tvshows/peoplewatching.png')
            kdir.folder(L(32018, 'Most Popular'), info_for(self.popular), thumb='tvshows/mostpopular.png')
            kdir.folder(L(32019, 'Top rated'), info_for(self.top_rated), thumb='tvshows/toprated.png')
            kdir.folder(L(32024, 'Airing today'), self.aired_today, thumb='tvshows/airingtoday.png')
            kdir.folder(L(32026, 'New TV Shows'), self.premiere, thumb='tvshows/new.png')
            kdir.folder(L(32011, 'Genres'), self.genre, thumb='tvshows/genres.png')
            kdir.folder(L(32016, 'Networks'), self.network, thumb="tvshows/networks.png")
            kdir.folder(L(30267, 'Providers'), self.provider_list, thumb='tvshows/providers.png')
            kdir.folder(L(32012, 'Year'), self.year, thumb='tvshows/year.png')
            kdir.folder(L(32014, 'Languages'), self.language, thumb='tvshows/languages.png')
            kdir.folder(L(30104, 'Countries'), self.country, thumb='tvshows/country.png')
            kdir.folder(L(32631, 'Awards'), self.awards, thumb='tvshows/awards.png')
            kdir.folder(L(32036, 'History'), nav.history.tvshows, thumb='tvshows/history.png')
            if settings.getBool('downloads'):
                kdir.folder(L(30320, 'TV Shows downloaded'), f'{settings.getString("tv.download.path")}', thumb='tvshows/download.png')


    @subobject
    def search(self) -> 'Search':
        """Search submodule."""
        return Search(indexer=self)

    def play_url(self, it: FFItem, *, edit: bool = False) -> 'Optional[EndpointInfo]':
        """Returns URL for episode play."""
        if it.aired_before(self.today()) and not const.indexer.episodes.future_playable:
            return info_for(KodiDirectory.no_op)
        if edit:
            return info_for(play, ref=it.ref, edit=edit)
        return info_for(play, ref=it.ref)

    @route
    def single(self, ffid: PathArg[int]) -> None:
        """DEBUG. Show list with single tv-show."""
        ref = MediaRef.tvshow(ffid)
        self.show_items([ref])

    def do_show_item(self, kdir: KodiDirectory, it: FFItem, *, alone: bool, link: bool, menu: List[ContextMenuItem]) -> None:
        """Process discover item. Called from discover()."""
        ref = it.ref
        mtype = it.ref.real_type
        if mtype == 'episode':
            it.label = self._episode_label(it, alone=alone)
            it.copy_from(it.season_item, it.show_item)  # year?
            if link:
                it.mode = it.Mode.Folder
                url = info_for(self.episodes, tv_ffid=ref.ffid, season=ref.season, select=ref.episode)
            else:
                it.mode = it.Mode.Playable
                url = self.play_url(it)
                menu += [
                    CMenu(L(30207, 'Edit search'), self.play_url(it, edit=True), visible=settings.getBool('cm.custom_search') or const.sources_dialog.edit_search.in_menu),
                ]
        elif mtype == 'season':
            it.label = self._season_label(it, alone=alone)
            it.mode = it.Mode.Folder
            it.copy_from(it.show_item)
            url = info_for(self.episodes, tv_ffid=ref.ffid, season=ref.season)
        else:
            it.label = f'{it.title}'
            it.setLabel2('%Y')
            it.mode = it.Mode.Folder
            url = info_for(self.seasons, tv_ffid=it.ffid)
        # test fix for double mark as watched/unwatched i TVShows/seasons
        # self.item_progress(it, menu=menu)
        # library_enabled = settings.getBool('enable_library')
        cm_show_details = is_plugin_folder() and settings.getBool('cm.details')
        cm_show_custom_search = settings.getBool('cm.custom_search') or const.sources_dialog.edit_search.in_menu
        menu += [
            CMenu(L(30162, 'Details'), url_for(self.media_info, ref=it.ref), visible=cm_show_details),
            # CMenu(L(30124, 'Add to library'), url_for(self.add_to_library, ref=it.ref), visible=library_enabled),
            # CMenu(L(30163, 'Add to library multiple'), url_for(self.add_to_library_multiple), visible=library_enabled),
        ]
        kdir.add(it, url=url, auto_menu=self.item_auto_menu(it, kdir=kdir), menu=menu)

    def show_media_info_item(self, kdir: KodiDirectory, it: FFItem):
        """Add media item in details view."""
        ref = it.ref
        mtype = ref.real_type
        if mtype == 'show' or it.show_item:
            up = it.show_item or it
            up.label = f'[B]{up.title}[/B]'
            menu = []
            self.item_progress(up, menu=menu)
            url = info_for(self.seasons, tv_ffid=up.ref.ffid, select=it.season)
            kdir.add(up, url=url, menu=menu)
        if mtype == 'season' or it.season_item:
            up = it.season_item or it
            up.label = self._season_label(up)
            up.label = f'[B]{up.label}[/B]'
            up.copy_from(it.show_item)
            menu = []
            self.item_progress(up, menu=menu)
            kdir.add(up, url=info_for(self.episodes, tv_ffid=up.ref.ffid, season=it.season, select=it.episode), menu=menu)
        if mtype == 'episode':
            it.label = self._episode_label(it=it)
            it.label = f'[B]{it.label}[/B]'
            it.copy_from(it.season_item, it.show_item)  # year?
            menu = []
            self.item_progress(it, menu=menu)
            if const.sources_dialog.edit_search.in_menu:
                menu = [*menu, (L(30207, 'Edit search'), self.play_url(it, edit=True))]
            it.mode = it.Mode.Playable
            kdir.add(it, url=self.play_url(it), menu=menu)

    def discover_year(self, year: int, end: int, *, page: int = 1) -> None:
        """Discover media in year range. Override it for tune."""
        vote_count = const.indexer.tvshows.year.votes
        sort_by = 'first_air_date.asc' if year == end else 'popularity.desc'
        return self.discover(page=page, sort_by=sort_by, votes=vote_count,
                             first_air_date=tmdb.Date.range(dt_date(year, 1, 1), dt_date(end, 12, 31)))

    @route
    def lists(self) -> None:
        """My tv-show lists."""
        from .navigator import nav
        linfo = ListsInfo()
        with list_directory(view='sets', icon='tvshows/main.png') as kdir:
            if linfo.trakt_enabled():
                kdir.folder(L(32037, 'Progress'), info_for(nav.trakt.shows_progress), thumb='services/trakt/progress.png')
                kdir.folder(L(32032, 'Collection'), info_for(nav.trakt.collection, media='show'), thumb='services/trakt/collection.png')
                kdir.folder(L(32033, 'Watchlist'), info_for(nav.trakt.ulist, media='show', list_type='watchlist', sort=const.indexer.trakt.sort.watchlist), thumb='services/trakt/watchlist.png')
                kdir.folder(L(30146, 'Favorites'), info_for(nav.trakt.ulist, media='show', list_type='favorites'), thumb='services/trakt/favorites.png')
                kdir.folder(L(32035, 'Featured'), info_for(nav.trakt.recommendation, media='show'), thumb='services/trakt/featured.png')
                kdir.folder(L(32036, 'History'), info_for(nav.trakt.ulist, media='show', list_type='history'), thumb='services/trakt/history.png')
                # kdir.folder(L('Watched'), info_for(nav.trakt.ulist, media='show', list_type='watched'), thumb='trakt.png')
                kdir.folder(L(30199, 'Calendarium'), info_for(nav.trakt.calendarium, media='show'), thumb='services/trakt/calendar.png')
                # kdir.separator('ǀ,ǁ,ǀǀǀǀǀ,⸋,[COLOR red][B]⸋⸋⸋⸋⸋  _XXX_X_XX  _###_#_####  _OOO_O_OOO  ••• • ••[/B][/COLOR]')

            if linfo.tmdb_enabled():
                kdir.folder(L(32802, 'TMDB Watchlist'), info_for(nav.tmdb.watchlist, media='show'), thumb='services/tmdb/watchlist.png')
                kdir.folder(L(32803, 'TMDB Favorites'), info_for(nav.tmdb.favorite, media='show'), thumb='services/tmdb/favorites.png')

            if linfo.imdb_enabled():
                kdir.folder(L(30346, 'IMDB Watchlist'), info_for(nav.imdb.watchlist, media='show'), thumb='services/imdb/watchlist.png')

            if linfo.mdblist_enabled():
                kdir.folder(L(30363, 'MDBList Watchlist'), info_for(nav.mdblist.watchlist, media='show'), thumb='services/mdblist/watchlist.png')

            if linfo.own_enabled():
                # kdir.folder(L(30347, 'Own Watchlist'), info_for(nav.own.watchlist, media='show'), thumb='people.png')
                kdir.folder(L(30348, 'Own Favorites'), info_for(nav.own.favorites, media='show'), thumb='services/own/favorites.png')
                nav.own.add_generic_lists(kdir, media='show', favorites=False, icon='services/own/main.png')

            if linfo.trakt_enabled():
                kdir.folder(L(30164, 'My Trakt Lists'), info_for(nav.trakt.mine, likes=True, media='show'), thumb='services/trakt/lists.png')
            if linfo.tmdb_enabled():
                kdir.folder(L(30165, 'My TMDB Lists'), info_for(nav.tmdb.mine, media='show'), thumb='services/tmdb/lists.png')
            if linfo.imdb_enabled():
                kdir.folder(L(30349, 'My IMDB Lists'), info_for(nav.imdb.mine, media='show'), thumb='services/imdb/lists.png')
            if linfo.mdblist_enabled():
                kdir.folder(L(30367, 'My MDBList Lists'), url_for(nav.mdblist.mine, media='show'), thumb='services/mdblist/lists.png')
            if linfo.own_enabled() and const.indexer.tvshows.my_lists.enabled:
                kdir.folder(L(30327, 'My Own Lists'), info_for(nav.own.mine, media='show'), thumb='services/own/lists.png')

    @item_folder_route('/popular', limit=const.indexer.tvshows.discovery_scan_limit)
    @pagination
    def popular(self, *, page: PathArg[int] = 1) -> Sequence[FFItem]:
        """Most popular tv-shows."""

        # Ukrywaj stare seriale
        def old_date(flt: str, setting_name: str) -> None:
            rollback = settings.getInt(setting_name)
            if rollback and hideoldshows:
                # rallback > 0 i hideoldshows jest true
                filters[flt] = tmdb.Date >= today - timedelta(days=365 * rollback)

        today = self.today()
        vote_count: int = settings.getInt('tmdbtv.votePopular')
        filters: DiscoveryFilters = {
            'sort_by': 'popularity.desc',
            'first_air_date': tmdb.Date <= today,
            'vote_count': tmdb.VoteCount >= vote_count,
            'with_watch_monetization_types': 'flatrate|free|ads|rent|buy',
            'without_genres': '10763,10764,10767',
            'watch_region': const.indexer.tvshows.region,
        }
        hideoldshows = settings.getBool('hideoldshows')
        # Ukrywaj seriale starsze niż
        old_date('first_air_date', 'hideoldshows.rollback')
        # Ukrywaj seriale których ostatni odcinek jest starszy niż
        old_date('air_date', 'hideoldshowsepi.rollback')
        # Ukrywanie anime, domyślnie wyłączone
        if settings.getBool("withoutAnime"):
            filters['without_keywords'] = (210024, *const.tmdb.avoid_keywords)

        return self.discover_items(page=page, **filters)

    @item_folder_route('/top_rated', limit=const.indexer.tvshows.discovery_scan_limit)
    @pagination
    def top_rated(self, *, page: PathArg[int] = 1) -> Sequence[FFItem]:
        """Top rated tv-shows."""
        # TMDB API: sort_by=vote_average.desc&vote_count.gte=200'
        filters: DiscoveryFilters = {
            'sort_by': 'vote_average.desc',
        }
        if vote_count := const.indexer.tvshows.top_rated.votes:
            filters['vote_count'] = tmdb.VoteCount >= vote_count
        return self.discover_items(page=page, **filters)

    @item_folder_route('/aired_today', limit=const.indexer.tvshows.discovery_scan_limit)
    @pagination
    def aired_today(self, *, page: PathArg[int] = 1) -> Sequence[FFItem]:
        """Aired today."""
        # TMDB API: sort_by=popularity.desc&air_date.lte={max_date}&air_date.gte={min_date}'
        filters: DiscoveryFilters = {
            'sort_by': 'popularity.desc',
            'air_date': tmdb.Date.range(tmdb.Today, tmdb.Today),
            'with_watch_monetization_types': 'flatrate|free|ads|rent|buy',
            'without_genres': '10763,10764,10767',
            'watch_region': const.indexer.tvshows.region,
        }
        self.discover(page=page, **filters)
        return self.discover_items(page=page, **filters)

    @item_folder_route('/premiere', limit=const.indexer.tvshows.discovery_scan_limit)
    @pagination
    def premiere(self, *, page: PathArg[int] = 1) -> Sequence[FFItem]:
        """New tv-shows."""
        filters: DiscoveryFilters = {
            'sort_by': 'first_air_date.desc',
            'first_air_date': tmdb.Date <= tmdb.Today,
            'with_watch_monetization_types': 'flatrate|free|ads|rent|buy',
            'without_genres': '10763,10764,10767',
            'watch_region': const.indexer.tvshows.region,
        }
        return self.discover_items(page=page, votes=const.indexer.tvshows.premiere.votes, **filters)

    @route
    def awards(self) -> None:
        """Create main awards menu. Must be called from @route, eg. awards()."""
        with directory(view='sets', thumb='tvshows/awards.png') as kdir:
            kdir.folder(L(30413, 'Emmy Winner'), info_for(self.awards_media, name='emmy_winner'), thumb='tvshows/emmy.png')
            kdir.folder(L(30174, 'Emmy Nominee'), info_for(self.awards_media, name='emmy_nominee'), thumb='tvshows/emmy.png')
            kdir.folder(L(30309, 'Golden Globe Winner'), info_for(self.awards_media, name='golden_globe_winner'), thumb='tvshows/golden.png')
            kdir.folder(L(30410, 'Golden Globe Nominee'), info_for(self.awards_media, name='golden_globe_nominee'), thumb='tvshows/golden.png')

    @route
    def network(self, nid: Optional[PathArg[int]] = None, page: PathArg[int] = 1) -> None:
        """Predefined tv networks."""
        if nid:
            return self.discover(page=page, votes=0, with_networks=nid)

        with directory(view='studios') as kdir:
            for nid, name, logo in self._get_networks():
                kdir.folder(name, info_for(nid=nid), icon=logo, thumb=logo)

    # --- sezony i odcinki ---

    def _season_label(self, it: FFItem, *, alone: bool = False) -> str:
        lbl = ffinfo.api_labels(20373)  # Kodi global string: "Season"
        has_title = f'{lbl} {it.season}' != it.title and f'Season {it.season}' != it.title
        if has_title:
            formats = const.indexer.seasons.with_title_labels
        else:
            formats = const.indexer.seasons.no_title_labels
        fmt_index = settings.getInt('tvshow.season_label')
        try:
            fmt = formats[fmt_index]
        except IndexError:
            fflog.error(f'No seazon format (title={has_title}) at index {fmt_index}')
            fmt = formats[0]
        if alone and it.show_item:
            fmt = f'{it.show_item.title} – {fmt}'
        label = fmt.format(it=it, item=FormatObjectGetter(it), locale=adict(season=lbl),
                           title=it.title, season=it.season, episode=it.episode or 0,
                           year=it.year, date=it.date)
        if const.indexer.seasons.override_title_by_label:
            it.title = label
        return label

    def _episode_label(self, it: FFItem, *, alone: bool = False) -> str:
        fmt = '{it.season}x{it.episode:02d}. {it.title}'
        if alone and it.show_item:
            fmt = f'{it.show_item.title} – {fmt}'
        return fmt.format(it=it)

    @mediaref_endpoint(param_ref_ffid='tv_ffid')
    @route('/')
    def seasons(self, tv_ffid: PathArg[int], *, select: Optional[int] = None):
        """Do list tvshow seasons (or episodes if flatten)."""
        flatten = Flatten(settings.getInt('flatten.tvshows'))
        # print(f'TVShows.seasons({tv_ffid=}, {flatten=})')
        tv_item: Optional[FFItem] = ffinfo.get_item(MediaRef.tvshow(tv_ffid))  # skip tv_episodes=True
        if tv_item is None:
            fflog('ERROR: tvshow {tv_ffid} NOT found')
            return no_content('seasons')
        seasons = list(tv_item.season_iter())
        if flatten == Flatten.Always or (flatten == Flatten.Single and len(seasons) == 1):
            # episodes (flatten view)
            self.flatten_show(tv_ffid, tv_item, seasons)
        else:
            # seasons
            show_unaired = settings.getBool('showunaired')
            # library_enabled = settings.getBool('enable_library')
            cm_show_details = is_plugin_folder() and settings.getBool('cm.details')
            with list_directory(view='seasons') as kdir:
                for it in seasons:
                    if show_unaired or not it.unaired:
                        it.label = self._season_label(it)
                        it.copy_from(tv_item)
                        menu = []
                        self.prepare_item(kdir, it, menu=menu)
                        self.item_properties(it)
                        self.item_progress(it, menu=menu)
                        it.mode = it.Mode.Folder
                        url_info = info_for(self.episodes, tv_ffid=tv_ffid, season=it.season)
                        # if url_info := info_for(self.episodes, tv_ffid=tv_ffid, season=it.season):
                        #     it.url = str(url_info.url)
                        if select is not None and it.season == select:
                            it.select(True)
                        kdir.add(it, url=url_info, menu=[
                            CMenu(L(30162, 'Details'), url_for(self.media_info, ref=it.ref), visible=cm_show_details),
                            *menu,
                            # CMenu(L(30124, 'Add to library'), url_for(self.add_to_library, ref=it.ref), visible=library_enabled),
                        ])
                    else:
                        fflog(f'Not-aired: {it.ref}, date={it.date}')

    @mediaref_endpoint(param_ref_ffid='tv_ffid')
    @route('/')
    def episodes(self, tv_ffid: PathArg[int], season: PathArg[int], *, select: Optional[int] = None):
        """List tvshow seasons."""
        print(f'TVShows.episodes({tv_ffid=}, {season=})')
        season_item: Optional[FFItem] = ffinfo.get_item(MediaRef.tvshow(tv_ffid, season))
        if season_item is None:
            fflog('ERROR: season {tv_ffid} / {season} NOT found')
            # return Folder([])
            return no_content('episodes')
        refs = [it.ref for it in season_item.episode_iter()]
        return self._episodes(tv_ffid, ffinfo.get_items(refs), select=select)  # show season episodes

    def flatten_show(self, tv_ffid: int, tv_item: FFItem, tv_seasons: List[FFItem]) -> None:
        """List all episodes of the tvshow (flatten). Called from seasons()."""
        # episode numbers must be 1..N in each season – single fetch
        if const.indexer.episodes.continuing_numbers:
            refs = [MediaRef.tvshow(tv_ffid, sz.season, ep)
                    for sz in tv_seasons
                    for ep in range(1, sz.children_count + 1)]
        else:
            # any episode number – double fetch (seasons, episodes)
            refs = [it.ref for it in tv_item.season_iter()]  # seasons
            seasons = ffinfo.get_items(refs)
            refs = [it.ref for sz in seasons if sz for it in sz.episode_iter()]  # episodes
        # show all episodes
        self._episodes(tv_ffid, ffinfo.get_items(refs))

    def _episodes(self, tv_ffid: int, episodes: List[FFItem], *, select: Optional[int] = None) -> None:  # Folder:
        """Create directory with episodes."""
        show_unaired = settings.getBool('showunaired')
        # library_enabled = settings.getBool('enable_library')
        cm_show_details = is_plugin_folder() and settings.getBool('cm.details')
        cm_show_custom_search = settings.getBool('cm.custom_search') or const.sources_dialog.edit_search.in_menu
        with list_directory(view='episodes') as kdir:
            # iterate over all episodes
            for it in episodes:
                if show_unaired or not it.unaired:
                    it.label = self._episode_label(it)
                    it.copy_from(it.season_item, it.show_item)  # year?
                    menu = []
                    self.prepare_item(kdir, it, menu=menu)
                    self.item_properties(it)
                    self.item_progress(it, menu=menu)
                    it.mode = it.Mode.Playable
                    style = None
                    if select is not None and not KodiDirectory.INFO.refresh and it.episode == select:
                        if const.indexer.tvshows.progress.episode_focus:
                            kdir.focus_item(it)
                        if const.indexer.tvshows.progress.episode_select:
                            it.select(True)
                        style = const.indexer.tvshows.progress.episode_label_style
                    kdir.add(it, url=self.play_url(it), style=style, menu=[
                        CMenu(L(30162, 'Details'), url_for(self.media_info, ref=it.ref), visible=cm_show_details),
                        *menu,
                        CMenu(L(30207, 'Edit search'), self.play_url(it, edit=True), visible=cm_show_custom_search),
                        # CMenu(L(30124, 'Add to library'), url_for(self.add_to_library, ref=it.ref), visible=library_enabled),
                    ])
                else:
                    fflog(f'Not-aired: {it.ref}, date={it.date}')

    # -----

    def _get_networks(self) -> Sequence[Tuple[int, str, str]]:
        """Return predefined tv networks."""
        # Hmmm... logo i nazwy można wziąć z API: https://api.themoviedb.org/3/network/{network_id}
        return (
            (54, 'Disney Channel', 'https://i.imgur.com/ZCgEkp6.png'),
            (44, 'Disney XD', 'https://i.imgur.com/PAJJoqQ.png'),
            (2, 'ABC', 'https://i.imgur.com/qePLxos.png'),
            (493, 'BBC America', 'https://i.imgur.com/TUHDjfl.png'),
            (6, 'NBC', 'https://i.imgur.com/yPRirQZ.png'),
            (13, 'Nickelodeon', 'https://i.imgur.com/OUVoqYc.png'),
            (14, 'PBS', 'https://i.imgur.com/r9qeDJY.png'),
            (16, 'CBS', 'https://i.imgur.com/8OT8igR.png'),
            (19, 'FOX', 'https://i.imgur.com/6vc0Iov.png'),
            (21, 'The WB', 'https://i.imgur.com/rzfVME6.png'),
            (24, 'BET', 'https://i.imgur.com/ZpGJ5UQ.png'),
            (30, 'USA Network', 'https://i.imgur.com/Doccw9E.png'),
            (32, 'CBC', 'https://i.imgur.com/unQ7WCZ.png'),
            (33, 'MTV', 'https://i.imgur.com/QM6DpNW.png'),
            (34, 'Lifetime', 'https://i.imgur.com/tvYbhen.png'),
            (35, 'Nick Junior', 'https://i.imgur.com/leuCWYt.png'),
            (41, 'TNT', 'https://i.imgur.com/WnzpAGj.png'),
            (43, 'National Geographic', 'https://i.imgur.com/XCGNKVQ.png'),
            (47, 'Comedy Central', 'https://i.imgur.com/ko6XN77.png'),
            (49, 'HBO', 'https://i.imgur.com/Hyu8ZGq.png'),
            (55, 'Spike', 'https://i.imgur.com/BhXYytR.png'),
            (67, 'Showtime', 'https://i.imgur.com/SawAYkO.png'),
            (56, 'Cartoon Network', 'https://i.imgur.com/zmOLbbI.png'),
            (65, 'History Channel', 'https://i.imgur.com/LEMgy6n.png'),
            (84, 'TLC', 'https://i.imgur.com/c24MxaB.png'),
            (68, 'TBS', 'https://i.imgur.com/RVCtt4Z.png'),
            (71, 'The CW', 'https://i.imgur.com/Q8tooeM.png'),
            (74, 'Bravo', 'https://i.imgur.com/TmEO3Tn.png'),
            (76, 'E!', 'https://i.imgur.com/3Delf9f.png'),
            (77, 'Syfy', 'https://i.imgur.com/9yCq37i.png'),
            (80, 'Adult Swim', 'https://i.imgur.com/jCqbRcS.png'),
            (91, 'Animal Planet', 'https://i.imgur.com/olKc4RP.png'),
            (110, 'CTV', 'https://i.imgur.com/qUlyVHz.png'),
            (129, 'A&E', 'https://i.imgur.com/xLDfHjH.png'),
            (158, 'VH1', 'https://i.imgur.com/IUtHYzA.png'),
            (174, 'AMC', 'https://i.imgur.com/ndorJxi.png'),
            (928, 'Crackle', 'https://i.imgur.com/53kqZSY.png'),
            (202, 'WGN America', 'https://i.imgur.com/TL6MzgO.png'),
            (209, 'Travel Channel', 'https://i.imgur.com/mWXv7SF.png'),
            (213, 'Netflix', 'https://i.imgur.com/jI5c3bw.png'),
            (251, 'Audience', 'https://i.imgur.com/5Q3mo5A.png'),
            (270, 'SundanceTV', 'https://i.imgur.com/qldG5p2.png'),
            (318, 'Starz', 'https://i.imgur.com/Z0ep2Ru.png'),
            (359, 'Cinemax', 'https://i.imgur.com/zWypFNI.png'),
            (364, 'truTV', 'https://i.imgur.com/HnB3zfc.png'),
            (384, 'Hallmark Channel', 'https://i.imgur.com/zXS64I8.png'),
            (397, 'TV Land', 'https://i.imgur.com/1nIeDA5.png'),
            (1024, 'Amazon', 'https://i.imgur.com/ru9DDlL.png'),
            (1267, 'Freeform', 'https://i.imgur.com/f9AqoHE.png'),
            (4, 'BBC One', 'https://i.imgur.com/u8x26te.png'),
            (332, 'BBC Two', 'https://i.imgur.com/SKeGH1a.png'),
            (3, 'BBC Three', 'https://i.imgur.com/SDLeLcn.png'),
            (100, 'BBC Four', 'https://i.imgur.com/PNDalgw.png'),
            (214, 'Sky One', 'https://i.imgur.com/xbgzhPU.png'),
            (9, 'ITV', 'https://i.imgur.com/5Hxp5eA.png'),
            (26, 'Channel 4', 'https://i.imgur.com/6ZA9UHR.png'),
            (99, 'Channel 5', 'https://i.imgur.com/5ubnvOh.png'),
            (136, 'E4', 'https://i.imgur.com/frpunK8.png'),
            (210, 'HGTV', 'https://i.imgur.com/INnmgLT.png'),
            (453, 'Hulu', 'https://i.imgur.com/uSD2Cdw.png'),
            (1436, 'YouTube Red', 'https://i.imgur.com/ZfewP1Y.png'),
            (64, 'Discovery Channel', 'https://i.imgur.com/8UrXnAB.png'),
            (2739, 'Disney+', 'https://i.imgur.com/DVrPgbM.png'),
            (2552, 'Apple TV +', 'https://i.imgur.com/fAQMVNp.png'),
            (2697, 'Acorn TV', 'https://i.imgur.com/fSWB5gB.png'),
            (1709, 'CBS All Access', 'https://i.imgur.com/ZvaWMuU.png'),
            (3186, 'HBO Max', 'https://i.imgur.com/mmRMG75.png'),
            (2243, 'DC Universe', 'https://i.imgur.com/bhWIubn.png'),
            (2076, 'Paramount Network', 'https://i.imgur.com/ez3U6NV.png'),
            (4330, 'Paramount+', 'https://i.imgur.com/dmUjWmU.png'),
            (3353, 'Peacock', 'https://imgur.com/1JXFkSM.png'),
            (504, 'TVN', 'https://i.imgur.com/yA8TJ4o.png'),
            (483, 'TVP1', 'https://i.imgur.com/as4ipbu.png'),
            (466, 'TVP2', 'https://i.imgur.com/qj1Ta1Q.png'),
            (315, 'Polsat', 'https://i.imgur.com/knnmJG5.png'),
        )
