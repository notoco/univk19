"""
    Fanfilm Add-on

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

import re
from datetime import date as dt_date, timedelta
from typing import Optional, List, Sequence, TYPE_CHECKING

from ..ff.routing import route, subobject, url_for, info_for, PathArg
from ..ff.menu import directory, KodiDirectory, ContextMenuItem, CMenu
from ..ff.settings import settings
from ..ff.tmdb import tmdb
from ..ff.trakt import trakt
from ..api.tmdb import DiscoveryFilters
from ..api.tv import TvProgram, TvServiceName
from ..kolang import L
from ..ff.item import FFItem
from ..ff.info import ffinfo
from ..ff.db import state
from ..ff.log_utils import fflog
from ..ff.control import is_plugin_folder
from .search import Search
from .core import MainIndexer
from .folder import list_directory, item_folder_route, pagination
from .lists import ListsInfo
from .navigator import play, nav
from const import const
if TYPE_CHECKING:
    from ..ff.routing import EndpointInfo
    from ..api.tv import TvMovie


class Movies(MainIndexer):
    """Movies navigation."""

    MODULE = 'movies'  # to read const settings
    TYPE = 'movie'
    VIDEO_TYPE = 'movie'
    TMBD_CONTENT = 'movie'
    TRAKT_CONTENT = 'movies'
    VOTE_COUNT_SETTING = 'tmdbmovie.vote'
    VIEW = 'movies'
    IMAGE = 'movies/main.png'

    @route('/')
    def home(self) -> None:
        """Create root / main menu."""
        linfo = ListsInfo()
        with list_directory(view='addons', icon='movies/main.png') as kdir:
            if const.indexer.movies.joke.production_company:
                kdir.folder(L(30138, 'Companies'), info_for(self.joke, type='production_company'))
            if const.indexer.movies.joke.keyword:
                kdir.folder(L(30137, 'Keywords'), info_for(self.joke, type='keyword'))
            kdir.folder(L(32010, 'Search'), self.search, thumb='movies/search.png')
            if linfo.enabled():
                kdir.folder(L(32003, 'My Movies'), self.lists, thumb='movies/my.png', icon='DefaultVideoPlaylists.png')
            kdir.folder(L(32801, 'Currently watching'), info_for(self.resume), thumb='movies/currentlywatching.png', icon='DefaultVideoPlaylists.png')
            kdir.folder(L(32017, 'People Watching'), info_for(self.trending), thumb='movies/peoplewarching.png', icon='DefaultRecentlyAddedMovies.png')
            kdir.folder(L(32018, 'Most Popular'), info_for(self.popular), thumb='movies/popular.png')
            kdir.folder(L(32019, 'Top rated'), info_for(self.top_rated), thumb='movies/toprated.png')
            kdir.folder(L(32011, 'Genres'), self.genre, thumb='movies/genres.png')
            kdir.folder(L(32005, 'New Movies'), info_for(self.new), thumb='movies/new.png', icon='DefaultRecentlyAddedMovies.png')
            kdir.folder(L(32022, 'In Theaters'), info_for(self.cinema), thumb='movies/intheaters.png', icon='DefaultRecentlyAddedMovies.png')
            kdir.folder(L(32007, 'Today in TV'), self.tv, thumb='movies/today.png')
            kdir.folder(L(32020, 'Box Office'), info_for(self.boxoffice), thumb='movies/boxoffice.png')
            kdir.folder(L(30138, 'Companies'), self.companies, thumb='movies/companies.png')
            kdir.folder(L(30267, 'Providers'), self.provider_list, thumb='movies/providers.png')
            kdir.folder(L(32012, 'Year'), self.year, thumb='movies/year.png')
            kdir.folder(L(32014, 'Languages'), self.language, thumb='movies/languages.png')
            kdir.folder(L(30104, 'Countries'), self.country, thumb='movies/country.png')
            kdir.folder(L(32631, 'Awards'), self.awards, thumb='movies/awards.png')
            kdir.folder(L(32036, 'History'), nav.history.movies, thumb='movies/history.png')
            if settings.getBool('downloads'):
                kdir.folder(L(30319, 'Movies downloaded'), f'{settings.getString("movie.download.path")}', thumb='movies/download.png')


    @subobject
    def search(self) -> 'Search':
        """Search submodule."""
        return Search(indexer=self)

    def not_so_today(self) -> dt_date:
        """Fake today, without cinema last N months."""
        today = self.today()
        months: int = settings.getInt('hidecinema.rollback') if settings.getBool('hidecinema') else 0
        if months:
            return today - timedelta(days=30 * months)
        return today

    def play_url(self, it: FFItem, *, edit: bool = False) -> 'Optional[EndpointInfo]':
        """Returns URL for movie play."""
        if it.aired_before(self.today()) and not const.indexer.movies.future_playable:
            return info_for(KodiDirectory.no_op)
        if edit:
            return info_for(play, ref=it.ref, edit=edit)
        return info_for(play, ref=it.ref)
        # return info_for(play_movie, ffid=it.ffid, edit=edit)

    def do_show_item(self, kdir: KodiDirectory, it: FFItem, *, alone: bool, link: bool, menu: List[ContextMenuItem]) -> None:
        """Process discover item. Called from discover()."""
        it.label = f'{it.title}'
        it.setLabel2('%T|%Y')
        it.mode = it.Mode.Playable
        self.item_progress(it, menu=menu)
        # library_enabled = settings.getBool('enable_library')
        cm_show_details = is_plugin_folder() and settings.getBool('cm.details')
        cm_show_custom_search = settings.getBool('cm.custom_search') or const.sources_dialog.edit_search.in_menu
        menu = [
            CMenu(L(30162, 'Details'), url_for(self.media_info, ref=it.ref), visible=cm_show_details),
            CMenu(L(30207, 'Edit search'), self.play_url(it, edit=True), visible=cm_show_custom_search),
        ]
        if settings.getBool('cm.movie_collection') and (collection := ffinfo.item_collection(it)):
            menu.append((L(30130, 'Movie Collection'), info_for(nav.collection.item, oid=collection.ref.ffid)))
        kdir.add(it, url=self.play_url(it), auto_menu=self.item_auto_menu(it, kdir=kdir), menu=menu)

    def post_show_items(self, kdir: KodiDirectory):
        """Called after item list folder is created."""
        refs = [item.ref for item in kdir.items if item.ref]
        state.set('multilib_refs', refs, module='library')

    def show_media_info_item(self, kdir: KodiDirectory, it: FFItem):
        """Add media item in details view."""
        it.mode = it.Mode.Separator
        it.label = f'[B]{it.title}[/B]'
        kdir.add(it, url=self.play_url(it))

    def discover_year(self, year: int, end: int, *, page: int = 1) -> None:
        """Discover media in year range. Override it for tune."""
        vote_count = const.indexer.movies.year.votes
        if year == end:
            return self.discover(page=page, votes=vote_count,
                                 sort_by='primary_release_date.asc', primary_release_year=year)
        else:
            return self.discover(page=page, votes=vote_count, sort_by='popularity.desc',
                                 primary_release_date=tmdb.Date.range(dt_date(year, 1, 1), dt_date(end, 12, 31)))

    @route
    def lists(self) -> None:
        """My movie lists."""
        from .navigator import nav
        linfo = ListsInfo()
        with list_directory(view='sets', icon='movies/main.png') as kdir:
            if linfo.trakt_enabled():
                kdir.folder(L(32032, 'Collection'), info_for(nav.trakt.collection, media='movie'), thumb='services/trakt/collection.png')
                kdir.folder(L(32033, 'Watchlist'), info_for(nav.trakt.ulist, media='movie', list_type='watchlist',
                                                            sort=const.indexer.trakt.sort.watchlist), thumb='services/trakt/watchlist.png')
                kdir.folder(L(30146, 'Favorites'), info_for(nav.trakt.ulist, media='movie', list_type='favorites'), thumb='services/trakt/favorites.png')
                kdir.folder(L(32035, 'Featured'), info_for(nav.trakt.recommendation, media='movie'), thumb='services/trakt/featured.png')
                kdir.folder(L(32036, 'History'), info_for(nav.trakt.ulist, media='movie', list_type='history'), thumb='services/trakt/history.png')

            if linfo.tmdb_enabled():
                kdir.folder(L(32802, 'TMDB Watchlist'), info_for(nav.tmdb.watchlist, media='movie'), thumb='services/tmdb/watchlist.png')
                kdir.folder(L(32803, 'TMDB Favorites'), info_for(nav.tmdb.favorite, media='movie'), thumb='services/tmdb/favorites.png')

            if linfo.imdb_enabled():
                kdir.folder(L(30346, 'IMDB Watchlist'), info_for(nav.imdb.watchlist, media='movie'), thumb='services/imdb/watchlist.png')

            if linfo.mdblist_enabled():
                kdir.folder(L(30363, 'MDBList Watchlist'), info_for(nav.mdblist.watchlist, media='movie'), thumb='services/mdblist/watchlist.png')

            if linfo.own_enabled():
                # kdir.folder(L(30347, 'Own Watchlist'), info_for(nav.own.watchlist, media='movie'), thumb='people.png')
                kdir.folder(L(30348, 'Own Favorites'), info_for(nav.own.favorites, media='movie'), thumb='services/own/favorites.png')
                nav.own.add_generic_lists(kdir, media='movie', favorites=False, icon='people.png')

            # user lists
            if linfo.trakt_enabled():
                kdir.folder(L(30164, 'My Trakt Lists'), url_for(nav.trakt.mine, likes=True, media='movie'), thumb='services/trakt/lists.png')
            if linfo.tmdb_enabled():
                kdir.folder(L(30165, 'My TMDB Lists'), url_for(nav.tmdb.mine, media='movie'), thumb='services/tmdb/lists.png')
            if linfo.imdb_enabled():
                kdir.folder(L(30349, 'My IMDB Lists'), url_for(nav.imdb.mine, media='movie'), thumb='services/imdb/lists.png')
            if linfo.mdblist_enabled():
                kdir.folder(L(30367, 'My MDBList Lists'), url_for(nav.mdblist.mine, media='movie'), thumb='services/mdblist/lists.png')
            if linfo.own_enabled() and const.indexer.movies.my_lists.enabled:
                kdir.folder(L(30327, 'My Own Lists'), url_for(nav.own.mine, media='movie'), thumb='services/own/lists.png')

    @item_folder_route('/popular', limit=const.indexer.tvshows.discovery_scan_limit)
    @pagination
    def popular(self, *, page: PathArg[int] = 1) -> Sequence[FFItem]:
        """Most popular movies."""
        # FF: primary_release_date.lte=%s&sort_by=popularity.desc
        return self.discover_items(page=page, sort_by='popularity.desc', primary_release_date=tmdb.Date <= self.today())

    @item_folder_route('/top_rated', limit=const.indexer.tvshows.discovery_scan_limit)
    @pagination
    def top_rated(self, *, page: PathArg[int] = 1) -> Sequence[FFItem]:
        """Top rated movies."""
        # TMDB API: sort_by=vote_average.desc&without_genres=99,10755&vote_count.gte=200'
        filters: DiscoveryFilters = {
            'sort_by': 'vote_average.desc',
            'without_genres': '99,10755',
            'primary_release_date': tmdb.Date <= self.not_so_today(),
        }
        if vote_count := const.indexer.movies.top_rated.votes:
            filters['vote_count'] = tmdb.VoteCount >= vote_count
        return self.discover_items(page=page, **filters)

    @route
    def new(self, *, page: PathArg[int] = 1) -> None:
        """Latest movies list."""
        # FF: sort_by=primary_release_date.desc&primary_release_date.lte=%s&vote_count.gte=%s
        self.discover(page=page, sort_by='primary_release_date.desc', primary_release_date=tmdb.Date <= tmdb.Today,
                      votes=const.indexer.movies.new.votes)

    @route
    def cinema(self, *, page: PathArg[int] = 1) -> None:
        """In Theaters (in cinema)."""
        # FF: sort_by=primary_release_date.desc&release_date.gte=%s&release_date.lte=%s&with_release_type=3&vote_count.gte=%s
        today = self.today()
        old = today - timedelta(days=const.indexer.movies.cinema.last_days)
        today += timedelta(days=const.indexer.movies.cinema.next_days)
        filters: DiscoveryFilters = {
            'sort_by': 'primary_release_date.desc',
            'with_release_type': 3,
            'release_date': tmdb.Date.range(old, today),
        }
        if const.indexer.movies.cinema.use_region:
            filters['watch_region'] = const.indexer.movies.region
        self.discover(page=page, **filters)

    @route('/tv/{service}/{entry_id}')
    def tv_items(self, service: TvServiceName, entry_id: str, *, page: PathArg[int] = 1) -> None:
        """Today in TV. Must be above tv/{service} to override it."""
        if not (common := TvProgram.tv_service(service=service)):
            return self.no_content()
        self.show_items(common.tv_movie_items(entry_id))

    @route('tv/{service}')
    @route('tv')
    def tv(self, service: Optional[TvServiceName] = None, *, page: PathArg[int] = 1) -> None:
        """Today in TV."""
        def add_tv(kdir: KodiDirectory, tv: 'TvMovie') -> None:
            kdir.folder(tv.title, url_for(self.tv_items, service=service, entry_id=tv.id),
                        thumb=tv.image or 'DefaultMovies.png', descr=tv.descr, role=tv.role())

        if service is None:
            if isinstance(const.indexer.movies.tv.service, str):
                service = const.indexer.movies.tv.service
            else:
                # Multi service, add folder with services names
                with directory(view=const.indexer.movies.tv.service_view) as kdir:
                    for service in const.indexer.movies.tv.service:
                        kdir.folder(service, url_for(service=service), thumb='movies/today.png')
                return
        if not (common := TvProgram.tv_service(service=service)):
            return self.no_content()
        mode = const.indexer.movies.tv.list_mode
        size = const.indexer.movies.tv.page_size
        fflog(f'In TV: {service=}, {mode=}, {page=}, page_size={size}')
        if not size:
            size = 1_000_000_000
        if mode == 'media':
            self.show_items(common.tv_movie_all_items(page=page, limit=size))
        elif mode == 'mixed':
            movies = common.tv_movie_mixed_items(page=page, limit=size)
            with directory(movies, view='movies') as kdir:
                for it in movies:
                    if isinstance(it, FFItem):
                        self.show_item(kdir, it)
                    else:
                        add_tv(kdir, it)
        elif mode == 'folders':
            movies = common.tv_movies(page=page, limit=size)
            with directory(movies, view='movies') as kdir:
                for tv in movies:
                    add_tv(kdir, tv)
        else:
            self.no_content()

    @route
    def boxoffice(self) -> None:
        """Box office."""
        items = trakt.box_office()
        self.show_items(items)

    @route
    def awards(self) -> None:
        """Create main awards menu. Must be called from @route, eg. awards()."""
        with directory(view='sets', thumb='movies/awards.png') as kdir:
            kdir.folder(L(30166, 'Oscar Winner'), url_for(self.awards_media, name='oscar_winner'), thumb='movies/oscars.png')
            kdir.folder(L(30167, 'Oscar Nominee'), url_for(self.awards_media, name='oscar_nominee'), thumb='movies/oscars.png')
            kdir.folder(L(30168, 'Oscar Best Picture Winner'), url_for(self.awards_media, name='best_picture_winner'), thumb='movies/oscars.png')
            kdir.folder(L(30169, 'Oscar Best Picture Nominee'), url_for(self.awards_media, name='oscar_best_picture_nominees'), thumb='movies/oscars.png')
            kdir.folder(L(30170, 'Oscar Best Director Winner'), url_for(self.awards_media, name='best_director_winner'), thumb='movies/oscars.png')
            kdir.folder(L(30171, 'Oscar Best Director Nominee'), url_for(self.awards_media, name='oscar_best_director_nominees'), thumb='movies/oscars.png')
            kdir.folder(L(30309, 'Golden Globe Winner'), info_for(self.awards_media, name='golden_globe_winner'), thumb='movies/golden.png')
            kdir.folder(L(30410, 'Golden Globe Nominee'), info_for(self.awards_media, name='golden_globe_nominee'), thumb='movies/golden.png')
            kdir.folder(L(30172, 'Razzie Winner'), url_for(self.awards_media, name='razzie_winner'), thumb='movies/razzie.png')
            kdir.folder(L(30173, 'Razzie Nominee'), url_for(self.awards_media, name='razzie_nominee'), thumb='movies/razzie.png')

    @route
    def companies(self, cid: Optional[PathArg[str]] = None, page: PathArg[int] = 1) -> None:
        """Predefined tv networks."""
        if cid:
            return self.discover(page=page, votes=0, with_companies=cid)

        from xbmcaddon import Addon
        from xbmcvfs import exists
        rx = re.compile(r'["/:]')
        has_white_icons: bool = False
        try:
            if Addon('resource.images.studios.white').getAddonInfo('path'):
                has_white_icons = True
        except Exception:
            pass
        with directory(view='studios') as kdir:
            for cid, name, whitelogo, logo in sorted(self._get_companies(), key=lambda x: x[1]):
                icon = None
                if has_white_icons:
                    icon = f'resource://resource.images.studios.white/{whitelogo}.png'
                    if not exists(icon):
                        icon = None
                if not icon and logo:
                    icon = f'{tmdb.art_image_url}/{logo}'
                kdir.folder(name, url_for(cid=cid), icon=icon, thumb=icon)


    # -----

    def _get_companies(self):
        """Return predefined companies."""
        # TMDB-ID, Name, studios.white name, TMDB icon
        return (
            ('20580',       'Amazon Studios',             'Amazon Studios',                 'oRR9EXVoKP9szDkVKlze5HVJS7g.png'),
            ('178464',      'Netflix',                    'Netflix',                        'tyHnxjQJLH6h4iDQKhN5iqebWmX.png'),
            ('3268|7429',   'HBO',                        'HBO',                            'tuomPhY2UtuPTqqFnKMVHvSb724.png'),
            ('6480',        'TVP',                        'TVP',                            'qJUUNzFYXNUDaisssBTV3Zdki9R.png'),
            ('5622',        'TVN Group',                  'TVN',                            'bKcpepYRLylECRb5LVkskW0TQIX.png'),
            ('25|127928',   '20th Century',               '20th Century Fox',               'qZCc1lty5FzX30aOCVRBLzaVmcp.png'),
            ('7',           'DreamWorks Pictures',        'DreamWorks Pictures',            '1kqoutvio9eDaQpp0l4gQoEF4Yf.png'),
            ('4',           'Paramount',                  'Paramount',                      'gz66EfNoYPqHTYI4q9UEN4CbHRc.png'),
            ('33',          'Universal Pictures',         'Universal Pictures',             '8lvHyhjr8oUKOOy2dKXoALWKdp0.png'),
            ('2',           'Walt Disney Pictures',       'Walt Disney Pictures Presents',  'wdrCwmRnLFJhEoH8GSfymY85KHT.png'),
            ('17',          'Warner Bros. Entertainment', 'Warner Bros. Entertainment',     '7Qu05UOqxdTGLl3kOvkRBv723Vz.png'),
            ('3',           'Pixar',                      'Pixar',                          '1TjvGVDMYsj6JBxOAkUHpPEwLf7.png'),
            ('1',           'Lucasfilm Ltd.',             'Lucasfilm Ltd.',                 'tlVSws0RvvtPBwViUyOFAO0vcQS.png'),
            ('5',           'Columbia Pictures',          'Columbia Pictures',              '71BqEFAF4V3qjjMPCpLuyJFB9A.png' ),
            ('34',          'Sony Pictures',              'Sony Pictures',                  'mtp1fvZbe4H991Ka1HOORl572VH.png'),
            ('38',          'Zespół Filmowy "Tor"',       'Studio Filmowe Tor',             'qMi10Y3HnR7BQRqMC4ch7qZ6HN4.png'),
            ('21',          'Metro-Goldwyn-Mayer',        'Metro-Goldwyn-Mayer',            'usUnaYV6hQnlVAXP6r4HwrlLFPG.png'),
            ('7926',        'Zespół Filmowy Kadr',        'Kadr',                           ''                               ),
            ('58225',       'Studio Filmowe Zebra',       'Studio Filmowe Zebra',           ''                               ),
            ('81883',       'Studio Filmowe Iluzjon',     'Studio Filmowe Iluzjon',         ''                               ),
            ('18392',       'Monolith Films',             'Monolith Films',                 ''                               ),
            ('14',          'Miramax',                    'Miramax',                        'm6AHu84oZQxvq7n1rsvMNJIAsMu.png'),
            ('6704',        'Illumination',               'Illumination Entertainment',     'uwy3O0fb0CKeLqINPgiGKbTMeux.png'),
            ('12',          'New Line Cinema',            'New Line Cinema',                'iaYpEp3LQmb8AfAtmTvpqd4149c.png'),
            ('56',          'Amblin Entertainment',       'Amblin Entertainment',           'cEaxANEisCqeEoRvODv2dO1I0iI.png'),
            ('429',         'DC Comics',                  'DC Comics',                      '2Tc1P3Ac8M479naPp1kYT3izLS5.png'),
            ('923',         'Legendary Pictures',         'Legendary Pictures',             '8M99Dkt23MjQMTTWukq4m5XsEuo.png'),
            ('10342',       'Studio Ghibli',              'Studio Ghibli',                  'eS79pslnoKbWg7t3PMA9ayl0bGs.png'),
            ('521',         'DreamWorks Animation',       'DreamWorks Animation',           'kP7t6RwGz2AvvTkvnI1uteEwHet.png'),
        )
