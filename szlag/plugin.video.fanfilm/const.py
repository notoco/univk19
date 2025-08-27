"""
FanFilm const (low-level developper) settings.
Do NOT change if you don't know what you doing.

Avoid imports here, please.
Supports `local.py` from plugin userdata folder. File is created if missing.

You can override settings in `local.py`.
Just in the same form as in section "CONST SETTINGS",
>>> const.name = value

For define new const settings see cdefs.py.

Use const settings
------------------

And use in source code.
>>> from const import const
>>> if const.a.b.c == value: ...
"""

from cdefs import const, const_done, CONST_REF
from cdefs import (
    PlayCancel, StateMode, MediaWatchedMode, StrmFilename, OwnListDef, AddToMenu, WhenShowListName, ListType, DirItemSource,
    SourcePattern, SourceAttribute,
    MINUTE, HOUR, DAY, DO_NOT_CACHE, MiB, NetCache,
)
from lib.kolang import L  # semi-safe import

# ----------------------------------------------------------------------------- #
# -----                          SOME DOCUMENTATION                       ----- #
# ----------------------------------------------------------------------------- #
#
# `votes` – minmum number of votes
#  -  >= 0   - the number
#  -  == -1  - skip votes at all
#  -  None   - use default from user settings


# ----------------------------------------------------------------------------- #
# -----                          CONST SETTINGS                           ----- #
# ----------------------------------------------------------------------------- #

# --- Developing and debugging ---

# Use more logs. Useful with `grep -f LOG` on the Linux.
const.debug.enabled = True
# Use terminal seq (colors) in logs. Useful with `grep -f LOG` on the Linux.
const.debug.tty = False
# Add extra context menu item: CRASH, allows restart Python interpreter.
const.debug.crash_menu = False
# Extra developer menu.
const.debug.dev_menu = False
# Auto-reload modules on changes.
const.debug.autoreload = False
# Detailed service notification log.
const.debug.service_notifications = False
# Log xsleep jitter (shift in seconds). Zero means no log.
const.debug.log_xsleep_jitter = 0
# Log folder details.
const.debug.log_folders = False
# Show "logs" target in CM in "Add to" dialog.
const.debug.add_to_logs = False
#: Detailed exception log (eg. in threads).
const.debug.log_exception = True

#: Use remote debugger (debugpy, vscode, etc.). Function setup_debugger() in local.py must be declared.
const.debugger.enabled = False

# Override TMDB api_key for tests.
const.dev.tmdb.api_key = None
# Override TMDB session_id for tests.
const.dev.tmdb.session_id = None
# Override TMDB v4 read token for tests.
const.dev.tmdb.v4.bearer = None
# Override TMDB v4 access token for tests.
const.dev.tmdb.v4.access_token = None

# Override Trakt.tv client_id for tests.
const.dev.trakt.client = None
# Override Trakt.tv client_secret for tests.
const.dev.trakt.secret = None

# Override MDBList api_key for tests.
const.dev.mdblist.api_key = None

#: Echo all DB queries.
const.dev.db.echo = False
#: Do backup on DB update.
const.dev.db.backup = True
#: Fake source items prepend to found items in the source window.
const.dev.sources.prepend_fake_items = ()
#: Fake source items append to found items in the source window.
const.dev.sources.append_fake_items = ()
#: Detailed source provider exception log.
const.dev.sources.log_exception = True


# --- Global (independent) definitions ---

# Default language for the country.
const.global_defs.country_language = {
    'AD': 'ca', 'AE': 'ar', 'AL': 'sq', 'AM': 'hy', 'AO': 'pt', 'AR': 'es', 'AT': 'de', 'AZ': 'az', 'BB': 'en',
    'BD': 'bn', 'BE': 'de', 'BF': 'fr', 'BG': 'bg', 'BH': 'ar', 'BI': 'en', 'BJ': 'fr', 'BR': 'pt', 'BS': 'en',
    'BT': 'dz', 'BY': 'ru', 'BZ': 'en', 'CA': 'fr', 'CF': 'fr', 'CH': 'rm', 'CL': 'es', 'CM': 'en', 'CN': 'zh',
    'CO': 'es', 'CR': 'es', 'CU': 'es', 'CY': 'tr', 'DE': 'de', 'DJ': 'fr', 'DK': 'da', 'DM': 'en', 'DO': 'es',
    'EC': 'qu', 'EE': 'et', 'EG': 'ar', 'ER': 'ti', 'ES': 'es', 'ET': 'en', 'FI': 'sv', 'FJ': 'hi', 'FR': 'fr',
    'GA': 'fr', 'GB': 'en', 'GD': 'en', 'GE': 'ka', 'GH': 'en', 'GN': 'fr', 'GQ': 'es', 'GR': 'el', 'GT': 'es',
    'GY': 'en', 'HN': 'es', 'HR': 'hr', 'HU': 'hu', 'IE': 'ga', 'IL': 'he', 'IN': 'en', 'IQ': 'ar', 'IS': 'is',
    'IT': 'it', 'JM': 'en', 'JO': 'ar', 'JP': 'ja', 'KE': 'en', 'KG': 'ru', 'KH': 'km', 'KI': 'en', 'KM': 'fr',
    'KW': 'ar', 'KZ': 'ru', 'LB': 'ar', 'LI': 'de', 'LK': 'ta', 'LR': 'en', 'LS': 'en', 'LT': 'lt', 'LU': 'lb',
    'LV': 'lv', 'LY': 'ar', 'MC': 'fr', 'ME': 'sq', 'MG': 'mg', 'MH': 'en', 'MK': 'sq', 'ML': 'fr', 'MN': 'mn',
    'MR': 'ar', 'MT': 'en', 'MU': 'en', 'MX': 'es', 'MY': 'en', 'MZ': 'pt', 'NA': 'en', 'NE': 'fr', 'NG': 'en',
    'NI': 'es', 'NL': 'nl', 'NP': 'ne', 'OM': 'ar', 'PA': 'es', 'PE': 'qu', 'PK': 'ur', 'PL': 'pl', 'PT': 'pt',
    'QA': 'ar', 'RO': 'ro', 'RS': 'sr', 'RW': 'sw', 'SA': 'ar', 'SB': 'en', 'SD': 'en', 'SE': 'sv', 'SG': 'ta',
    'SK': 'sk', 'SL': 'en', 'SM': 'it', 'SN': 'fr', 'SO': 'ar', 'SR': 'nl', 'SS': 'en', 'SV': 'es', 'TD': 'fr',
    'TG': 'fr', 'TH': 'th', 'TN': 'fr', 'TO': 'to', 'TR': 'tr', 'TV': 'en', 'UA': 'uk', 'UG': 'sw', 'UY': 'es',
    'UZ': 'uz', 'VE': 'es', 'VU': 'fr', 'WS': 'en', 'YE': 'ar', 'ZA': 'zu', 'ZM': 'en'}


# --- Core ---

#: Call garbage collector (GC) for every nth plugin calls.
const.core.gc_every_nth = 5
#: Exit (close Python interpreter) for every nth plugin calls.
const.core.exit_every_nth = 25
#: Exit (close Python interpreter) for every nth plugin calls in widgets.
const.core.widgets_exit_every_nth = 1
#: Use service to keep volatile DBID (for seasons only at the moment).
const.core.volatile_ffid = True
#: Use volatile FFID in all sesons. It allows to monitor kodi operations on seasons.
#: To work needs const.core.volatile_ffid set to true.
const.core.volatile_seasons = True
#: How to watch list-item changes, ex. set (un)watched.
const.core.media_watched_mode = MediaWatchedMode.WATCH_LISTITEM

#: Use advancedsettings.xml to determinne kodi MyVideo DB.
const.core.kodidb.advanced_settings = True

# Save [ff]info media cache.
const.core.info.save_cache = False
# Copy year in FFItem.copy_from(), eg. episode from season and/or from tv-show.
const.core.info.copy_year = False

# Net-chache backend: 'filesystem', 'sqlite', 'redis'.
const.core.netcache.backend = 'filesystem'
# Net-chache serializer as tuple:
# - serializer type: 'pickle', 'json'
# - compressor:      'zlib', 'gzip', 'bz2', 'lzma' or empty string for no compression
const.core.netcache.serializer = ('pickle', 'gzip')
# Net-cache config.
#  - expires in seconds or settins expression.
#  - size limit in bytes (works only with `filesystem` cache backend).
const.core.netcache.cache = {
    # no cache
    '':         NetCache(DO_NOT_CACHE),
    # other or unknown data
    'other':    NetCache(MINUTE, size_limit=10 * MiB),
    # media data
    'media':    NetCache('{schedCleanMetaCache} * 3600', size_limit=100 * MiB),
    # media art (and similar stuff)
    'art':      NetCache(7 * DAY, size_limit=10 * MiB),
    # discover (best, popular etc.)
    'discover': NetCache('24 * HOUR if {listCache} else netcache.DO_NOT_CACHE', size_limit=10 * MiB),
    # lists (eg. trakt, tmdb, imdb, etc.) - should be short
    'lists':    NetCache('15 * MINUTE if {listCache} else netcache.DO_NOT_CACHE', size_limit=10 * MiB),
    # search - should be quite short I guess
    'search':   NetCache(15 * MINUTE, size_limit=10 * MiB),
}
# Use net-cache in widgets too.
const.core.netcache.widgets = True
# Net-cache cleanup (remove expired entries) interval in seconds.
const.core.netcache.cleanup.interval = 15 * MINUTE
# Net-cache cleanup after expire * factor, zero if not used.
const.core.netcache.cleanup.expire_factor = 2.0
# Net-cache cleanup after expire ( * factor if enabled) + offset.
const.core.netcache.cleanup.expire_offset = 0
# Net-cache redis host ('redis' backend only).
const.core.netcache.redis.host = 'localhost'
# Net-cache redis port ('redis' backend only).
const.core.netcache.redis.port = 6379
# Net-cache redis remove expired ('redis' backend only).
const.core.netcache.redis.ttl = True
# Net-cache redis remove expired time offset ('redis' backend only).
const.core.netcache.redis.ttl_offset = 3600


# --- Media (general) ---

# #: Low percentage limit. Less then means not watched.
# const.media.progress.min = 1
#: Watching percent count as watched.
const.media.progress.as_watched = 85
#: Count show and season progress by full watched episodes (ignore partially watched episodes).
const.media.progress.show.episodes_watched = True

# ----- Sources -----

# Color of the list item index (1/99).
const.sources_dialog.index_color = 'B3FFFFFF'
# Show empty source window (no sources).
const.sources_dialog.show_empty = True
# Rescan button open "edit source search".
const.sources_dialog.rescan_edit = False
# Add "edit source search" to video (movie, episode) context-menu.
const.sources_dialog.edit_search.in_menu = False
# Add "edit source search" to sources dialog.
const.sources_dialog.edit_search.in_dialog = True
# Add "edit source search" to sidebar.
const.sources_dialog.edit_search.in_filters = False
# Define quality label for external sources
# Avaiable: 4K, 1440p, 1080p, 720p, SD
# In local.py use:
# const.sources_dialog.external_quality_label = {**const.sources_dialog.external_quality_label, 'servicename': quality}
const.sources_dialog.external_quality_label = {
    'Netflix': '1080p',
    'amazon prime': '1080p',
    'max': '1080p',
    'disney+': '1080p',
    'bbc iplayer': '1080p',
    'curiosity stream': '1080p',
    'hulu': '1080p',
    'paramount+': '1080p',
    'player pl': '1080p',
    'polsat box': '1080p',
    'viaplay': '1080p',
    'sky showtime': '1080p',
    'UPC TV Go': '1080p',
    }
# Define priority to sort language type
const.sources_dialog.language_type_priority = {
    "lektor": 0,
    "dubbing": 1,
    "napisy": 2,
    }
#: Remove disabled hosts from sources list - default empty (eg. {'wrzucaj', 'wplik', 'gofile'} )
const.sources_dialog.disabled_hosts = {
    'booster'
}
#: Show DRM sources from cda scraper
const.sources_dialog.cda_drm = True
#: Refresh search for librared items when using cache
#: example 'rapideo', 'nopremium', 'twojlimit','tb7', 'xt7'
#: tb7/xt7 - long time to scrape
const.sources_dialog.library_cache = {

}

# ----- Folders -----

#: Use cacheToDisk in xbmcplugin.endOfDirectory().
const.folder.cache_to_disc = False
#: How long wait for HTTP server sync on directory refresh.
const.folder.lock_wait_timeout = 2.0
#: Extra delay if refresh is detected to allow service close the "folder-ready" semaphore.
const.folder.refresh_delay = 0.7
#: Maximum time between each plugin read in kodi scan process: fast enter into seasons on show set (un)watched.
const.folder.max_scan_step_interval = 1.5
#: Save folder info into DB (old way). Use HTTP /folder instead.
const.folder.db_save = False
# If FF is called as script (handler == -1) and directory is building, try to refresh container.
const.folder.script_autorefresh = True
# When show previous page item (except first page even if 'always'):
#   - `never`        - never show
#   - `always`       - on every page (except first page)
#   - `on_last_page` - only on last page (except first page)
const.folder.previous_page = 'on_last_page'
# Maximum page number to jump to.
const.folder.max_page_jump = 500
# Item fanart fallback (None, 'landscape', ...). If None or when art missing, plugin fanart is used.
const.folder.fanart_fallback = 'landscape'
# Auto category, how many parent labels to show in the folder label.
const.folder.category = 2
# Auto category, how many parent labels to show in the folder label for given skin.
const.folder.category_by_skin = {
    'skin.estuary': 1,
}

#: Format for future item (unaired, non-premiered).
const.folder.style.future = '[COLOR darkred][I]{}[/I][/COLOR]'
#: Format for item with role.
const.folder.style.role = '{item.label} [COLOR gray][{item.role}][/COLOR]'
#: Format for broken items (eg. not found in TMDB). Eg. '{} [COLOR red]![/COLOR]'
const.folder.style.broken = None

# ----- Indexes -----

# Default region.
const.indexer.region = 'PL'
# Default view for list of lists (eg. mine).
const.indexer.lists_view = 'sets'
# Sow or not empty folder message (no content to display). Message to show or True for default.
const.indexer.empty_folder_message = True
# Default page size.
const.indexer.page_size = 20
# Default limit for "Add to…" for general lists.
const.indexer.add_to_limit = 100
# Number of movies/tv-shows from Trakt/TMDB trending used in "library", "add to…" etc.
const.indexer.trending_scan_limit = CONST_REF.indexer.add_to_limit
# Fake thumb: alias to landscape (for episode) and poster (for other).
const.indexer.art.fake_thumb = True

# Style to update description (plot). Singe '{…}' means progress formatting, double '{{}}' means description formatting.
const.indexer.progressbar.style = '[B]{progressbar} {percent}%[/B]\n{{}}'
# General progress bar source mode:
#   - 'none'                 - do not show progressbar at all
#   - 'watching'             - show video percent progress (PERCENT) if video progress >0% and < 100% else show nothing
#   - 'watched'              - show only watched videos (movies and episodes progresses are skipped)
#   - 'percent'              - show video percent progress
#   - 'percent_and_watched'  - show video percent progress and watched in background (use const.indexer.progressbar.watched.*)
const.indexer.progressbar.mode = 'watched'
# Progress bar width (number of characters).
const.indexer.progressbar.width = 50
# Fill element (watched) color (kodi color eg. darkred, FFCC9900).
const.indexer.progressbar.fill.color = 'darkgreen'
# Fill element (watched) character (eg. ' ', '|', 'l', 'ı', '•', '⸋').
const.indexer.progressbar.fill.char = 'l'
# Partial filled element (watched & unwatched) color (kodi color eg. darkred, FFCC5500).
const.indexer.progressbar.partial.color = 'darkgreen'
# Partial filled element (watched & unwatched) character (eg. ' ', '|', 'l', 'ı', '•', '⸋').
const.indexer.progressbar.partial.char = 'ı'
# Empty element (unwatched) color (kodi color eg. darkred, gray, FF999999 or empty).
const.indexer.progressbar.empty.color = 'gray'
# Empty element (unwatched) character (eg. ' ', '|', 'l', 'ı', '•', '⸋').
const.indexer.progressbar.empty.char = 'ı'
# Already watched element on watching again color (kodi color eg. darkred, gray, FF999999 or empty).
const.indexer.progressbar.watched.color = 'white'
# Already watched element on watching again character (eg. ' ', '|', 'l', 'ı', '•', '⸋').
const.indexer.progressbar.watched.char = CONST_REF.indexer.progressbar.empty.char

# No directory content: show no-content item.
const.indexer.no_content.show_item = True
# No directory content: show no-content notification.
const.indexer.no_content.notification = True

# Content view type for search folder.
const.indexer.search.view = 'tags'
# Ask user if sure on history clear.
const.indexer.search.clear_if_sure = True
# When to show numeric dialog to enter year:
#   - never         - never show numeric dialog
#   - context-menu  - add context menu to "new search"
#   - entry         - add separate entry "new search with year"
#   - always        - always show numeric dialog in "new search"
const.indexer.search.year_dialog = 'entry'
# General pattern for search movie or tv-show by year.
const.indexer.search.year_pattern = r'\b(?:y(?:ear)?:([12]\d{3}))|\(([12]\d{3})\)'
# Color for search query option (eg. "y:1987").
const.indexer.search.query_option_format = '[COLOR gray]{}[/COLOR]'
# Show multi search entry if True.
const.indexer.search.multi_search = True

# Show CM: "add to..." anything :-)
# Empty AddToMenu uses const.dialog.add_to.lists.services.
# AddToMenu woth service name uses const.dialog.add_to.lists.services[service].
# AddToMenu with service and list adds item to the list without dialog.
const.indexer.context_menu.add_to = (
    # AddToMenu(name=L('Add to own favorites'), enabled=True, service='own', list=':favorites'),
    AddToMenu(name=L(30307, 'Add to...')),  # const.indexer.context_menu.add_to equivalent
    # AddToMenu(name=L('Add to library'), enabled='enable_library', service='library'),
    # AddToMenu(name=L('Add to trakt'), enabled='ListsInfo.trakt_enabled()', service='trakt'),  # TEST
    # AddToMenu(name='Add to logs (debug)', enabled='const.debug.add_to_logs', service='logs'),  # TEST
)

# -- Directories: main menu

# Show Trakt, TMDB, etc in separate folder. If False, show them in main menu.
const.indexer.navigator.lists_folder = False

# -- Directories: movies

# Default region for movies.
const.indexer.movies.region = CONST_REF.indexer.region
# Sort by `movies.sort` option index (popularity, year, ...) in movie discovery.
const.indexer.movies.discover_sort_by = (
    'popularity.desc',
    'primary_release_date.desc',
    'title.asc',
)
#: Time in seconds for movies / episodes without duration.
const.indexer.movies.missing_duration = 0
#: Means future (not premiered yet) movie if no date (None/null).
const.indexer.movies.future_if_no_date = True
#: Generate date from "year" (year-01-01) value if no movie date defined.
const.indexer.movies.date_from_year = False
#: Future (not premiered yet) movie can by played.
const.indexer.movies.future_playable = True
# Last watched date-time format in movie resume list. None if disabled.
const.indexer.movies.resume.watched_date_format = '%Y-%m-%d'
# Number of movies from TMDB discovery (or Trakt) used in "library", "add to…" etc.
const.indexer.movies.discovery_scan_limit = CONST_REF.indexer.add_to_limit
#: Override vote count for top-rated movies.
const.indexer.movies.top_rated.votes = 300
#: Override vote count for movies by genre.
const.indexer.movies.genre.votes = 50
#: Override vote count for movies by year.
const.indexer.movies.year.votes = 100
#: List of movie genres (main menu level).    NOT USED NOW !!!
# const.indexer.movies.genre.menu = {
#     12, 14, 16, 18, 27, 28, 35, 36, 37, 53, 80, 99, 878, 9648, 10402, 10749, 10751, 10752,
# }
#: Joke. Show hundreds of thousands production_companies.
const.indexer.movies.joke.production_company = False
#: Joke. Show hundreds of thousands keywords.
const.indexer.movies.joke.keyword = False
#: Trending source (tmdb, trakt):
const.indexer.movies.trending.service = 'trakt'
# Number of last days to see movies in cinema.
const.indexer.movies.cinema.last_days = 60
# Number of next days to see movies in cinema (ongoing).
const.indexer.movies.cinema.next_days = 4
# Filter cinema movies by selected region.
const.indexer.movies.cinema.use_region = False
#: Default Movies in TV service (filmweb, onet).
const.indexer.movies.tv.page_size = 50
#: Default Movies in TV service (filmweb, onet, or sequence of them).
const.indexer.movies.tv.service = ('filmweb', 'onet')
#: Movies in TV (fanfilm) list mode:
#: - movies (all movies)
#: - mixed (movie if single or folder if many)
#: - folders (folder always)
const.indexer.movies.tv.list_mode = 'mixed'
#: content vide for TV services menu.
const.indexer.movies.tv.service_view = 'sets'
# New movies votes.
const.indexer.movies.new.votes = 50
#: Movie style to update description (plot). Singe '{…}' means progress formating, double '{{}}' means description formating.
const.indexer.movies.progressbar.style = CONST_REF.indexer.progressbar.style
# Movie progress bar source mode:
#   - 'none'                 - do not show progressbar at all
#   - 'watching'             - show video percent progress (PERCENT) if video progress >0% and < 100% else show nothing
#   - 'watched'              - show only watched videos (movies and episodes progresses are skiped)
#   - 'percent'              - show video percent progress
#   - 'percent_and_watched'  - show video percent progress and watched in background (use const.indexer.progressbar.watched.*)
const.indexer.movies.progressbar.mode = 'percent'
#: Movie progress bar width (number of characters).
const.indexer.movies.progressbar.width = CONST_REF.indexer.progressbar.width
# Enable "my lists" in tv-show directory.
const.indexer.movies.my_lists.enabled = True
# Show root level "my lists" flat (show sub-list on root level).
const.indexer.movies.my_lists.root.flat = True
# Pattern for search movie by year.
const.indexer.movies.search.year_pattern = CONST_REF.indexer.search.year_pattern

# -- Directories: tv-shows

# Default region for tv-shows.
const.indexer.tvshows.region = CONST_REF.indexer.region
# Sort by `tvshows.sort` option index (popularity, year, ...) in tv-show discovery.
const.indexer.tvshows.discover_sort_by = (
    'popularity.desc',
    'first_air_date.desc',
    'name.asc',
)
#: Means future (not aired yet) tvshow if no date (None/null).
const.indexer.tvshows.future_if_no_date = True
#: Override vote count for top-tated tv-shows.
const.indexer.tvshows.top_rated.votes = 200
#: Override vote count for tvshow by genre.
const.indexer.tvshows.genre.votes = 50
#: Override vote count for tvshow by year.
const.indexer.tvshows.year.votes = 100
#: List of tvshow genres (main menu level).    NOT USED NOW !!!
# const.indexer.tvshows.genre.menu = {
#     16, 18, 35, 37, 80, 99, 9648, 10751, 10759, 10762, 10764, 10765, 10766, 10767, 10768,
# }
#: Joke. Show hundreds of thousands production_companies.
const.indexer.tvshows.joke.production_company = False
#: Trending source (tmdb, trakt):
const.indexer.tvshows.trending.service = 'trakt'
# Minimal numer of votes in tv-show premier (new tv-shows).
const.indexer.tvshows.premiere.votes = 20

# What to show in progress folder.
const.indexer.tvshows.progress.show = 'episode'
# What to show in progress folder.
#   - last      - episode are calculated using the last aired episode the user has watched.
#   - continued - episode are calculated using last watched episode (last activity).
#   - first     - episode are calculated using first unwatched episode.
#   - newest    - episode are calculated using the last aired episode at all.
const.indexer.tvshows.progress.next_policy = 'last'
# If True, show next episode as link to season folder
# if False, show next episode as playable video.
const.indexer.tvshows.progress.episode_folder = True
# Focus next episode on episodes list.
const.indexer.tvshows.progress.episode_focus = True
# Select next episode on episodes list (not all skins handle it).
const.indexer.tvshows.progress.episode_select = False
# Format next episode on episodes list ('{}' means title, '{item}' is FFItem).
const.indexer.tvshows.progress.episode_label_style = None
# Show 100% watched shows in progress folder.
const.indexer.tvshows.progress.show_full_watched = False

# Number of days to see tvshows in trakt calendar
# +3 - 3 days after today date, -10 - 10 days before todays date
# Range must be lower than 33 days
const.indexer.tvshows.calendar_range = (+3, -10)
# Number of tv-shows from TMDB discovery (or Trakt) used in "library", "add to…" etc.
const.indexer.tvshows.discovery_scan_limit = CONST_REF.indexer.add_to_limit
# Enable "my lists" in tv-show directory.
const.indexer.tvshows.my_lists.enabled = True
# Show root level "my lists" flat (show sub-list on root level).
const.indexer.tvshows.my_lists.root.flat = True
# Pattern for search movie by year.
const.indexer.tvshows.search.year_pattern = CONST_REF.indexer.search.year_pattern

# -- Directories: seasons

#: Season label format if no season title, selected by user setting `tvshow.season_label`.
#: Season FFItem is available as `item`.
const.indexer.seasons.no_title_labels = (
    '{locale.season} {season}',  # option: Season 1
    '{locale.season} {season}',  # option: Season 1 – Title
    '{locale.season} {season}',  # option: 1. Title
)
#: Season label format if season has its own title, selected by user setting `tvshow.season_label`.
#: Season FFItem is available as `item`.
const.indexer.seasons.with_title_labels = (
    '{locale.season} {season}',            # option: Season 1
    '{locale.season} {season} – {title}',  # option: Season 1 – Title
    '{season}. {title}',                   # option: 1. Title
)
#: Force override season title by generated label. Should be false.
const.indexer.seasons.override_title_by_label = False
#: Means future (not aired yet) season if no date (None/null).
const.indexer.seasons.future_if_no_date = True

# -- Directories: episodes

#: Time in seconds for movies / episodes without duration.
const.indexer.episodes.missing_duration = 0
#: Skip future (not aired yet) episodes in season (and show) progress.
const.indexer.episodes.progress_if_aired = True
#: Means future (not aired yet) episode if no date (None/null).
const.indexer.episodes.future_if_no_date = True
#: Generate date from "year" (year-01-01) value if no episode date defined.
const.indexer.episodes.date_from_year = False
#: Future (not aired yet) episode can by played.
const.indexer.episodes.future_playable = True
#: It True, episodes number must be for 1 to N (faster but dangerous).
const.indexer.episodes.continuing_numbers = False
#: Episode label format.
const.indexer.episodes.label = '{season}x{episode:02d}. {title}'
# Last watched date-time format in episode resume list. None if disabled.
const.indexer.episodes.resume.watched_date_format = '%Y-%m-%d'
#: Episode style to update description (plot). Singe '{…}' means progress formatting, double '{{}}' means description formatting.
const.indexer.episodes.progressbar.style = CONST_REF.indexer.progressbar.style
# Episode progress bar source mode:
#   - 'none'                 - do not show progressbar at all
#   - 'watching'             - show video percent progress (PERCENT) if video progress >0% and < 100% else show nothing
#   - 'watched'              - show only watched videos (movies and episodes progresses are skiped)
#   - 'percent'              - show video percent progress
#   - 'percent_and_watched'  - show video percent progress and watched in background (use const.indexer.progressbar.watched.*)
const.indexer.episodes.progressbar.mode = 'percent'
#: Episode progress bar width (number of characters).
const.indexer.episodes.progressbar.width = CONST_REF.indexer.progressbar.width

# -- Directories: persons

# Enable person directory.
const.indexer.persons.enabled = True
# Number of persons from TMDB discovery (or Trakt) used in "library", "add to…" etc.
const.indexer.persons.discovery_scan_limit = CONST_REF.indexer.add_to_limit
# Show tv-shows with persons role as "Self".
const.indexer.persons.show.include_self = False
# Enable "my lists" in person directory.
const.indexer.persons.my_lists.enabled = True
# Show "my lists" directly in person directory.
const.indexer.persons.my_lists.flat = True
# Show root level "my lists" flat (show sub-list on root level).
const.indexer.persons.my_lists.root.flat = True

# -- Directories: details

# Content view type for wideos in details folder.
const.indexer.details.videos.view = 'studios'

# -- Directories: stump idexers

const.indexer.stump.votes = 0

# -- Directories: lists

# - trakt

# If true, show entry in listing: /tools/trakt/entry.
const.indexer.trakt.show_sync_entry = True
# Trakt mixed collections enabled.
const.indexer.trakt.collection.mixed = True
# Trakt mixed recommendations enabled.
const.indexer.trakt.recommendation.mixed = True
# Trakt my list (list of the lists) view.
const.indexer.trakt.mine.view = CONST_REF.indexer.lists_view
# Watched date-time format in trkat lists (like history). None if disabled.
const.indexer.trakt.lists.watched_date_format = '%Y-%m-%d'
# Show ••• progress bar for shows.
const.indexer.trakt.progress.bar = True  # XXX: NOT USED
# Split any media progress into pages (default value).
const.indexer.trakt.progress.page_size = CONST_REF.indexer.page_size
# Split watching movies into pages.
const.indexer.trakt.progress.movies_page_size = CONST_REF.indexer.trakt.progress.page_size
# Split watching episodes into pages.
const.indexer.trakt.progress.episodes_page_size = CONST_REF.indexer.trakt.progress.page_size
# Split tv-shows progress into pages.
const.indexer.trakt.progress.shows_page_size = CONST_REF.indexer.trakt.progress.page_size
# Exact match for tv-shows progress into pages size. If false page could be smaller, but faster.
const.indexer.trakt.progress.shows_page_size_exact_match = True
#: Default trakt.tv list sorting ('.asc' could be replaced with '.desc'):
#: - 'trakt'          - trakt.tv settings (trakt user sets in WWW)
#: - 'added.asc'      - added time
#: - 'collected.asc'  - collection added time
#: - 'rank.asc'       - rank
#: - 'released.asc'   - movie/show released
#: - 'title.asc'      - movie/show title
#: - 'runtime.asc'    - movie/show runtime (duration)
#: - 'votes.asc'      - number of votes
#: - 'popularity.asc' - fake popularity (ranking is used)
#: - 'random'         - random order
const.indexer.trakt.sort.default = 'trakt'
#: Trakt.tv watchlist sorting.
const.indexer.trakt.sort.watchlist = 'added.desc'
#: Trakt.tv collection sorting.
#: NOTE: Mixed collection does NOT support 'trakt' sorting.
const.indexer.trakt.sort.collections = 'collected.asc'
#: Fix trakt sort order (X-Sort-how) to make 'asc' really ascending.
const.indexer.trakt.sort.reverse_order = {
    'added': False,
    'collected': True,
    'rank': False,
    'released': False,
    'title': False,
    'runtime': False,
    'votes': False,
    'popularity': False,
}

# - tmdb

#: TMDB root directory is flat (own lists at root level).
const.indexer.tmdb.root.flat = False
#: TMDB mixed collections enabled.
const.indexer.tmdb.favorites.mixed = True
#: TMDB mixed recommendations enabled.
const.indexer.tmdb.watchlist.mixed = True
#: TMDB my list (list of the lists) view.
const.indexer.tmdb.mine.view = CONST_REF.indexer.lists_view

# - imdb

#: IMDB media list page size (NOTE: using IMDB ID is slow).
const.indexer.imdb.page_size = CONST_REF.indexer.page_size
#: IMDB mixed recommendations enabled.
const.indexer.imdb.watchlist.mixed = True
#: IMDB my list (list of the lists) view.
const.indexer.imdb.mine.view = CONST_REF.indexer.lists_view

# - mdblist lists

# MDBList enabled if true.
const.indexer.mdblist.enabled = True
#: MDBList media list page size.
const.indexer.mdblist.page_size = CONST_REF.indexer.page_size
#: MDBList root directory is flat (own lists at root level).
const.indexer.mdblist.root.flat = False
#: MDBList my list (list of the lists) view.
const.indexer.mdblist.mine.view = CONST_REF.indexer.lists_view
#: MDBList my list (list of the lists) view.
const.indexer.mdblist.top.view = CONST_REF.indexer.lists_view

# - user own lists

# Own media list enabled if true.
const.indexer.own.enabled = True
# Own media list page size.
const.indexer.own.page_size = CONST_REF.indexer.page_size
# Show "my lists" directly in own list directory.
const.indexer.own.flat = True
# Show root level "my lists" flat (show sub-list on root level).
const.indexer.own.root.flat = True
# Own my list (list of the lists) view.
const.indexer.own.mine.view = CONST_REF.indexer.lists_view
# When to show list name as role. Used in "my lists" top level.
const.indexer.own.mine.show_list_name = WhenShowListName.IF_MANY
# Show flat "my lists" directly in any directory witch has no own flat setting. If all indexers has own settings, this value does not matter.
const.indexer.own.mine.flat_default = True
# Role for flat root lists if list is direct (media type, not items from flated list of lists).
# String or "{name}" or "" for no role.
const.indexer.own.mine.root_direct_role = ''
# Own build-in list (without favorites and watchlist).
const.indexer.own.generic = (
    OwnListDef(':favorites', 'mixed', 'db://own/:favorites', label=L(30146, 'Favorites'), icon='DefaultMovies.png', mixed=True),
    # OwnListDef(':watchlist', 'media', 'db://own/:watchlist', label=L('Watchlist'), icon='DefaultMovies.png', mixed=True),
    # OwnListDef(':collection', 'media', 'db://own/:collection', label=L('Collection'), icon='DefaultMovies.png', mixed=True),
)
# Own custom lists.
const.indexer.own.lists = (
    OwnListDef('/', 'list', 'db://own/'),
    # XXX EXAMPLE – REMOVE IT
    # OwnListDef('Argentyńske seriale kryminalne z odcinkami poniżej 30 min', 'show',
    #            'tmdb://show?with_origin_country=AR&with_genres=80&sort_by=first_air_date.desc&with_runtime<30',
    #            icon='https://www.themoviedb.org/t/p/w600_and_h900_bestv2/dtfwJKDN3cinNpXw86r89TUpuc8.jpg'),
    # OwnListDef('Łubu dubu', 'list', 'profile://example-list_of_lists.csv',
    #            icon='https://png.pngtree.com/png-clipart/20191123/original/pngtree-list-icon-png-image_5194124.jpg'),
    # OwnListDef('Abc', 'person', 'profile://example-list_of_lists.csv'),
)

# - history

# Show watching videos (partial watched, even if not played) in history folder.
const.indexer.history.show_watching = False
# Format for history item role.
const.indexer.history.role = '{played_at:%Y-%m-%d}'
#: How many items get from hostory in "Add to...".
const.indexer.history.limit = CONST_REF.indexer.add_to_limit

# - tools

# Content view type for tools folders.
const.indexer.tools.view = 'sets'

# -- Genre menu

#: Fix TMDB genres translations [kodi-language][tmdb-genre-id].
const.indexer_group.genres.translations = {
    'pl-PL': {
        10762: 'Dla dzieci',
        10763: 'Informacje',
        10764: 'Reality TV',
        10766: 'Romans',
        10767: 'Talk Shows',
        10768: 'Wojna i polityka',
        10770: 'Filmy telewizyjne',
    },
}
# Genre icons active set (fanfilm, kodi).
const.indexer_group.genres.icons_set = 'fanfilm'
# Genre icons by TMDB genre ID (is active icons_set).
const.indexer_group.genres.icons = {
    'fanfilm': {
        12: 'genres/Adventure.png',
        14: 'genres/Fantasy.png',
        16: 'genres/Animation.png',
        18: 'genres/Drama.png',
        27: 'genres/Horror.png',
        28: 'genres/Action.png',
        35: 'genres/Comedy.png',
        36: 'genres/History.png',
        37: 'genres/Western.png',
        53: 'genres/Thriller.png',
        80: 'genres/Crime.png',
        99: 'genres/Documentary.png',
        878: 'genres/Sci-Fi.png',
        9648: 'genres/Mystery.png',
        10402: 'genres/Music.png',
        10749: 'genres/Romance.png',
        10751: 'genres/Family.png',
        10752: 'genres/War.png',
        10759: 'genres/Action_and_Adventure.png',
        10762: 'genres/Kids.png',
        10763: 'genres/News.png',
        10764: 'genres/Reality_show.png',
        10765: 'genres/Sci_fi_and_fantasy.png',
        10766: 'genres/Romance.png',
        10767: 'genres/Television.png',
        10768: 'genres/Historical.png',
        10770: 'genres/Television.png',
    },
    'kodi': {
        12: 'resource://resource.images.moviegenreicons.white/Adventure.jpg',
    }
}

# -- Language menu

#: Set of favorite languages.
const.indexer_group.languages.default = {
    'cs', 'de', 'en', 'es', 'fr', 'it', 'ja', 'ko', 'pl', 'sv', 'uk', 'zh',
}
#: Set of top languages from favorites. Current Kodi language will be on top too.
const.indexer_group.languages.top = {
    'pl',
}
#: Custom language groups. Use `|` for OR, `,` for AND.
const.indexer_group.languages.groups = (
    # DirItemSource('pl|lt|uk|be', "I Rzeczpospolita"),
)
#: Override vote count for media by language. None for use default.
const.indexer_group.languages.votes = 0

# -- Country menu

#: Set of favorite countries.
const.indexer_group.countries.default = {
    'GB', 'CN', 'CZ', 'DE', 'DK', 'ES', 'FR', 'IT', 'JP', 'KR', 'PL', 'SE', 'UK', 'US',
}
#: Set of top countries from favorites. Current Kodi region will be on top too.
const.indexer_group.countries.top = {
    'PL',
}
#: Custom country groups. Use `|` for OR, `,` for AND.
const.indexer_group.countries.groups = (
    DirItemSource('DK|FI|IS|NO|SE', L(30102, 'Scandinavian')),  # Scandinavian
)
#: Override vote count for media by country. None for use default.
const.indexer_group.countries.votes = 0


# ----- tmdb.org settings -----

# =season/N in main request. Total max is 20 for all appends.
const.tmdb.append_seasons_count = 10
# =season/N in next seasons-only requests. Total max is 20 for all appends.
const.tmdb.append_seasons_max_count = 20
# Default languages used in `include_image_language` when info get with `append_to_response=images`.
# const.tmdb.image_languages = all_languages
# Mode of image getting:
#   - append       - use `append_to_response=images` with fixed `include_image_language`, no poster at all often
#   - append_en    - use `append_to_response=images` with fixed `include_image_language=en`
#   - append_lang  - use `append_to_response=images` with fixed `include_image_language={lang}`
#   - pull         - like `append` but get images in next request if fails (no images)
#   - full         - always make two requests, support all services (it is forced for non-tmdb services, e.g. fanart.tv)
#   - all          - use /images to get all images in concurrent request
const.tmdb.get_image_mode = 'append'
# Langauge code aliases. Non-ISO-631-1 TMDB extensions.
const.tmdb.language_aliases = (
    ('zh', 'cn'),
)
# Maximum number of HTTP threads in TMDB skeleton.
const.tmdb.skel_max_threads = 10
# Discover items without keywords IDs.
const.tmdb.avoid_keywords = (
    155477,  # softcore
)

# API version (most endpoints uses v3 and v3 could be generated from v4).
const.tmdb.auth.api = 4
# API auth dialog - refresh interval in seconds (ask TMDB for token and update progress).
const.tmdb.auth.dialog_interval = 5
# API auth dialog - expiration time in seconds, max is 900 – TMDB remove token after 15 min.
const.tmdb.auth.dialog_expire = 300
# TMDB auth link QR-Code scale.
const.tmdb.auth.qrcode_size = 10

# Number of tries to send request to TMDB.
const.tmdb.connection.try_count = 3
# Number of seconds between TMDB connection tries.
const.tmdb.connection.try_delay = 1.0
# TMDB request timeout.
const.tmdb.connection.timeout = 15
# TMDB commone request session (for all threads).
const.tmdb.connection.common_session = True
# Maximum number of concurrent connections to TMDB.
const.tmdb.connection.max = 0


# ----- trakt.tv settings -----

#: How many items get from recomendations in "Add to...".
const.trakt.recommendations_limit = CONST_REF.indexer.add_to_limit
#: Page size (page limit) in trakt.tv for directory.
const.trakt.page.limit = 20
#: Page limit in scan all pages in trakt.tv. DO NOT edit.
const.trakt.scan.page.limit = 100
#: Interval of first trakt sync (playback, watched, etc) after service started.
const.trakt.sync.startup_interval = 2
#: Interval of cyclic trakt sync (playback, watched, etc) refresh.
const.trakt.sync.interval = 1800
#: Time of cool-down before next sync starts. Used with series sync reqiests.
const.trakt.sync.cooldown = 30
#: How long delay the sync notification. Notification is hidden if sync take less time.
const.trakt.sync.notification_delay = 3
#: Timeout for wait synchronic trakt sync (via service).
const.trakt.sync.wait_for_service_timeout = 180
#: Default sync video -> trakt for alien video (plugins and all non-FF3 sources).
const.trakt.sync.alien.default = False
#: Tune alien video -> trakt URL schema sync: {schema: True/False}.
const.trakt.sync.alien.scheme = {
    # 'plugin': False,   # all plugins are not synced by default, you could stil filter by const.trakt.sync.alien.plugins
    # 'file': True,      # all local files are synced
}
#: Tune alien plugins video -> trakt sync: {plugin_id: True/False}.
const.trakt.sync.alien.plugins = {
    # 'plugin.video.my_super_extra_plugin': False,
    # 'plugin.video.nothing1': True,
}
#: Auto Trakt.tv auth. Register device every time if got 403.
const.trakt.auth.auto = False
#: Trakt.tv auth link QR-Code scale.
const.trakt.auth.qrcode.size = 20

# Number of tries to send request to trakt.tv.
const.trakt.connection.try_count = 3
# Number of seconds between trakt.tv connection tries.
const.trakt.connection.try_delay = 1.0
# Trakt.tv request timeout.
const.trakt.connection.timeout = 15

# ----- mdblist.com settings -----

# Number of tries to send request to trakt.tv.
const.mdblist.connection.try_count = 3
# Number of seconds between trakt.tv connection tries.
const.mdblist.connection.try_delay = 1.0
# Trakt.tv request timeout.
const.mdblist.connection.timeout = 15


# ----- justwatch.com settings -----

#: Max episodes in JustWatch requests
const.justwatch.episode_max_limit = 100


# ----- sources settings / tune -----

# All video duration ε, how big the video duration discrepancy can be (0.05 mens 5%).
const.sources.duration_epsilon = .08

# The keyword to detect whether we are dealing with anime
const.sources.check_anime = 'anime'

# Sources rules, color, order, play mode, etc.
# Order does matter, last rule is more important. Only defined attributes override previous one.
# Default rules always should applied. For update in `local.py` use:
# >>> const.sources.rules = {
# >>>     **const.sources.rules,
# >>>     SourcePattern(…): SourceAttribute(…),
# >>> }
# For color and order attributes description see SourceAttribute class in cdefs.py.
const.sources.rules = {
    # buy again CM
    SourcePattern(provider='tb7'): SourceAttribute(menu=('buy', 'play')),
    SourcePattern(provider='xt7'): SourceAttribute(menu=('buy', 'play')),
    # default for m3u8 (url or filename) when setting is enabled
    SourcePattern(m3u8=True, setting='isa.enabled'): SourceAttribute(play='isa'),
    # default for non-m3u8 (another file or setting is disabled)
    SourcePattern(setting='not isa.enabled'): SourceAttribute(play='direct'),
    SourcePattern(m3u8=False): SourceAttribute(play='direct'),
    # some not-working ISA
    SourcePattern(hosting='player', platform='android'): SourceAttribute(play='direct'),
    SourcePattern(hosting='lulustream', platform='android'): SourceAttribute(play='direct'),
    SourcePattern(hosting='lulustream', platform='windows'): SourceAttribute(play='direct'),
    # default for external
    SourcePattern(provider='external'): SourceAttribute(play='direct', menu=()),
}

# Dictionary for franchise names to check in sources.
# Use example: "search phrase": ["franchise1", "franchise2"]
const.sources.franchise_names = {
    # Star Wars seriale
    'Acolyte': ['Star Wars The Acolyte', 'Gwiezdne Wojny Akolita'],
    'Andor': ['Star Wars Andor', 'Gwiezdne Wojny Andor'],
    'Ahsoka': ['Star Wars Ahsoka', 'Gwiezdne Wojny Ahsoka'],
    'Mandalorian': ['Star Wars The Mandalorian', 'Gwiezdne Wojny Mandalorian'],
    'Boba Fett': ['Star Wars The Book of Boba Fett', 'Gwiezdne Wojny Księga Boby Fetta'],
    'Bad Batch': ['Star Wars The Bad Batch', 'Gwiezdne Wojny Zła Partia'],
    'Visions': ['Star Wars Visions', 'Gwiezdne Wojny Wizje'],
    # Star Wars filmy
    'Episode I': ['Star Wars Episode I The Phantom Menace', 'Star Wars I The Phantom Menace', 'Gwiezdne Wojny Mroczne Widmo', 'Gwiezdne Wojny Część I Mroczne Widmo'],
    'Episode II': ['Star Wars Episode II Attack of the Clones', 'Star Wars II Attack of the Clones', 'Gwiezdne Wojny Atak Klonów', 'Gwiezdne Wojny Część II Atak Klonów'],
    'Episode III': ['Star Wars Episode III Revenge of the Sith', 'Star Wars III Revenge of the Sith', 'Gwiezdne Wojny Zemsta Sithów', 'Gwiezdne Wojny Część III Zemsta Sithów'],
    'Episode IV': ['Star Wars Episode IV A New Hope', 'Star Wars IV A New Hope', 'Gwiezdne Wojny Nowa Nadzieja', 'Gwiezdne Wojny Część IV Nowa Nadzieja'],
    'Episode V': ['Star Wars Episode V The Empire Strikes Back', 'Star Wars V The Empire Strikes Back', 'Gwiezdne Wojny Imperium Kontratakuje', 'Gwiezdne Wojny Część V Imperium Kontratakuje'],
    'Episode VI': ['Star Wars Episode VI Return of the Jedi', 'Star Wars VI Return of the Jedi', 'Gwiezdne Wojny Powrót Jedi', 'Gwiezdne Wojny Część VI Powrót Jedi'],
    'Episode VII': ['Star Wars Episode VII The Force Awakens', 'Star Wars VII The Force Awakens', 'Gwiezdne Wojny Przebudzenie Mocy', 'Gwiezdne Wojny Część VII Przebudzenie Mocy'],
    'Episode VIII': ['Star Wars Episode VIII The Last Jedi', 'Star Wars VIII The Last Jedi', 'Gwiezdne Wojny Ostatni Jedi', 'Gwiezdne Wojny Część VIII Ostatni Jedi'],
    'Episode IX': ['Star Wars Episode IX The Rise of Skywalker', 'Star Wars IX The Rise of Skywalker', 'Gwiezdne Wojny Skywalker. Odrodzenie', 'Gwiezdne Wojny Część IX Skywalker. Odrodzenie'],
    'Rogue One': ['Rogue One A Star Wars Story', 'Łotr 1. Gwiezdne Wojny – Historia'],
    'Solo': ['Solo A Star Wars Story', 'Han Solo. Gwiezdne Wojny – Historie'],
}
# Dictionary for franchise names seperator.
const.sources.franchise_names_sep = r'[ .]'
# List of supported source languages.
const.sources.language_order = (
    'pl',
    'mul',
    'multi',
    'en',
    'de',
    'fr',
    'it',
    'es',
    'pt',
    'ko',
    'ru',
    '-',
    '',
)
# Translations for providers names.
const.sources.translations.providers = {
    'pl-PL': {
        'library': 'Biblioteka',
        'download': 'Pobrane',
    }
}
# Translations for hostings names.
const.sources.translations.hostings = {
}


# Use fallback, show source links event if player.pl can not find video.
const.sources.external.playerpl.fallback = False


# CDA video duration ε, how big the video duration discrepancy can be (0.05 mens 5%).
const.sources.cda.duration_epsilon = CONST_REF.sources.duration_epsilon
# Show CDA premium_free=true as given name. Default is empty (show nothing).
const.sources.cda.show_premium_free = ''


# tb7/xt7 fot before season number.
# If True, add dot before season number (e.g. ".s01")
const.sources.xtb7.dot_before_season = True

# tb7/xt7 space before season number.
const.sources.xtb7.space_before_season = False

# tb7/xt7 include base title in show name.
const.sources.xtb7.include_base_title_in_show_search = True

# tb7/xt7 use similarity.
const.sources.xtb7.similarity_check = False

# tb7/xt7 similarity threshold.
# If similarity is greater than this value, then the source is considered suitable.
const.sources.xtb7.similarity_threshold = 0.94


# Use the no_transfer function in source window
const.sources.premium.no_transfer = True

# ----- Player -----

#: True, if player should try to set Kodi DbId.
const.player.set_dbid = False
#: How to cancel playing video from the beginning.
const.player.cancel_start = PlayCancel.EMPTY
#: How to cancel playing video from the resume point. Avoid PlayCancel.EMPTY, could set `watched`.
const.player.cancel_resume = PlayCancel.TT430
#: How to cancel playing video from the resume point. Avoid PlayCancel.EMPTY, could set `watched`.
const.player.refresh_on_cancel_resume = True
#: Use (kodi default) or not HEAD request in player video.
const.player.head_lookup = False


# ----- Library -----

# Force always flat folder for shows (old format).
# If false new show folders uses season subfolders, existing old one uses flat structure.
# If true always use flat folder structure.
const.library.flat_show_folder = False
# The STRM file name for new movies and shows. Use another format if detected.
const.library.strm_filename = StrmFilename.TITLE_YEAR
# Language of title (and folder) in the library.
const.library.title_language = 'en-US'
# If True, sync Kodi library (update library) after each batch.
# if False, sync Kodi library only if no another batch in the queue (sync after batches group).
const.library.service.sync_every_batch = False
# If True, wait for each Kodi library sync (library update).
# If False, start next batch immediately.
const.library.service.sync_wait = True


# ----- Dialogues -----

# Auth dialog: link color.
const.dialog.auth.link_color = 'FFA30707'
# Auth dialog: code color.
const.dialog.auth.code_color = 'FFA3A307'

# Allowed media conversions in add-to dialog.
# Available conversions are limited by lib.ff.lists.ListConvertRules.
const.dialog.add_to.allowed_conversions = {
    'collection': ListType.MOVIE,
    'movie': ListType.COLLECTION,
    'show': ListType.SEASON | ListType.EPISODE,
    'season': ListType.SHOW | ListType.EPISODE,
    'episode': ListType.SHOW | ListType.SEASON,
}
# True if adding should be quiet (no notification).
const.dialog.add_to.quiet = False
# Add-to dialog: show absent (non-existing) media types.
const.dialog.add_to.media_type.absent_visible = ListType.MEDIA
# Add-to dialog: absent (non-existing) media color.
const.dialog.add_to.media_type.absent_color = '99666666'
# Add-to dialog: existing media color.
const.dialog.add_to.media_type.exist_color = 'FFEEEEFF'
# Add-to dialog: media converting color.
const.dialog.add_to.media_type.converting_color = 'FFFFCC66'
# Add-to dialog: disallowed color.
const.dialog.add_to.media_type.disallowed_color = 'FFFF6666'
# Type of media names in the "add to..." dialog header.
const.dialog.add_to.media_type.bar_mode = 'icons'
# All defined services (left column) and theirs lists (central column) in default Add-to dialog.
# Values are ListPointer names.
# This settings is used to handle "Add to..." dialog with no service name, see: const.indexer.context_menu.add_to.
const.dialog.add_to.lists.default = {
    L(30355, 'Local'): ('library', 'own:favorites', 'own:user', 'logs'),
    # L('Local'): ('library', 'own:favorites', 'own:watchlist', 'own:collection', 'own:user', 'logs'),
    L(30356, 'Trakt'): ('trakt:favorites', 'trakt:watchlist', 'trakt:collection', 'trakt:user'),
    L(32775, 'TMDB'): ('tmdb:favorites', 'tmdb:watchlist', 'tmdb:user'),
    L(30357, 'MDBList'): ('mdblist:watchlist', 'mdblist:user'),
    # L('Own lists'): ('own:favorites', 'own:watchlist', 'own:user'),  # TEST
    # L('Library'): ('library',),                                      # TEST
    # L('Logs'): ('logs',),                                            # TEST
    L(30146, 'Favorites'): ('own:favorites', 'trakt:favorites', 'tmdb:favorites'),
}
# All defined services (left column) and theirs lists (central column) in Add-to dialog with service name.
# Keys are ListService names. All keys must be used.
# Values are dialog services definitions: label and ListPointer names. More enrties could be used in single service.
# This settings is used to handle "Add to..." dialog with service name, see: const.indexer.context_menu.add_to.
const.dialog.add_to.lists.services = {
    'local': {
        L(30355, 'Local'): ('library', 'own:favorites', 'own:watchlist', 'own:user', 'logs'),
    },
    'library': {
        L(32541, 'Library'): ('library',),
    },
    'own': {
        L(30358, 'Own lists'): ('own:favorites', 'own:user'),
        # L('Own lists'): ('own:favorites', 'own:watchlist', 'own:collection', 'own:user'),
    },
    'trakt': {
        L(30356, 'Trakt'): ('trakt:favorites', 'trakt:watchlist', 'trakt:collection', 'trakt:user'),
    },
    'tmdb': {
        L(32775, 'TMDB'): ('tmdb:favorites', 'tmdb:watchlist', 'tmdb:user'),
    },
    'mdblist': {
        L(30357, 'MDBList'): ('mdblist:watchlist', 'mdblist:user'),
    },
    'logs': {
        L(30359, 'Logs'): ('logs',),
    },
}


# ----- Low level settings (don't change, you are warned) -----

# Interval in internal sleep loop.
const.tune.sleep_step = 0.1
# Interval in internal threads.Event.wait() loop.
const.tune.event_step = 0.1
# Max workers for api.depagine().
const.tune.depagine_max_workers = None

#: Sqlite3 connection timeout (python default is 5.0).
const.tune.db.connection_timeout = 3.0
#: DB state.wait_for_value() reading interval.
const.tune.db.state_wait_read_interval = 0.2
#: Where keep state varibables by default.
const.tune.db.state_mode = StateMode.SERVICE
#: Tune state varibables.
const.tune.db.module_state_mode = {
    'service': StateMode.DB,
    'trakt': StateMode.DB,
}

# Number of kept settings backup files.
const.tune.settings.vacuum_files = 5

#: Interval in internal sleep loop.
const.tune.service.check_interval = 3
#: Interval in internal sleep loop.
const.tune.service.job_list_sleep = 1
#: Interval for group update (kodi notification for seazon or show).
const.tune.service.group_update_timeout = 5
#: Show busy dialog on group update (kodi notification for seazon or show).
const.tune.service.group_update_busy_dialog = True
# Delay to set item focus after plugin dicrecory (plugin exit with 'focus' index).
const.tune.service.focus_item_delay = .5
# Extra hard dealy to start FF service.
const.tune.service.startup_delay = 0
# Timeout for service up.
const.tune.service.startup_timeout = 10
# Timeout for service RPC call response.
const.tune.service.rpc_call_timeout = 3

# Port number for proxy HTTP server. Zero means take any free port.
const.tune.service.http_server.port = 0
# Number of tries to get FF service URL.
const.tune.service.http_server.try_count = 12
# Wait between get FF service URL tries.
const.tune.service.http_server.wait_for_url = .25
# How verbose should be http service server? 0 - off.
const.tune.service.http_server.verbose = 1

# Port number for web HTTP server. Used only if settings is not set.
const.tune.service.web_server.port = 8663
# How verbose should be web http service server? 0 - off.
const.tune.service.web_server.verbose = 1
# Prase cookies from web server and convert them to settings.
const.tune.service.web_server.cookies = {
    'cda-hd.cc': {
        ':user_agent': 'cdahd.user_agent',
        'cf_clearance': 'cdahd.cookies_cf',
    },
    'filman.cc': {
        ':user_agent': 'filman.user_agent',
        'BKD_REMEMBER': 'filman.cookies',
        'cf_clearance': 'filman.cookies_cf',
    },
}

# Default QR-Code scale.
const.tune.misc.qrcode.size = 20

# Pattern for output (generated) window/dialog XML.
const.tune.gui.xml_output_filename = 'tmp--{stem}.{timestamp}.xml'
const.tune.gui.xml_output_filename = 'tmp--{name}'


# ----------------------------------------------------------------------------- #
# -----                              THE END                              ----- #
# ----------------------------------------------------------------------------- #

# --- must be on the bottom of the file
const_done()
