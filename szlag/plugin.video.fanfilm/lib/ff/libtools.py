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


from __future__ import annotations
from typing import Any, Optional, List, Union, Dict, TypedDict, Iterator, Sequence, ClassVar, cast
from typing_extensions import Protocol, Pattern, NotRequired, Literal, overload
import re
from functools import lru_cache

import xml.etree.ElementTree as ET
from contextlib import contextmanager
from attrs import frozen, evolve
from xbmcvfs import translatePath, mkdirs, File, makeLegalFilename, listdir
from xbmc import executebuiltin
from xbmcgui import Dialog
from datetime import datetime, timedelta

from .anypath import APath
from .item import FFItem
from .log_utils import fflog, fflog_exc
from .settings import settings
from .routing import url_for
from .info import ffinfo
from .kotools import KodiRpc
from ..defs import MediaRef
from ..indexers.navigator import play
from ..kolang import L
from const import const, StrmFilename


class InLibDict(TypedDict):
    file: str
    season: int
    episode: int
    streamdetails: NotRequired[dict[str, Any]]  # Optional, only if include_streamdetails is True


class KodiWritableFile(Protocol):
    def write(self, buffer: Union[str,  bytes,  bytearray]) -> bool: ...
    def close(self) -> None: ...


class DummyFile:

    def write(self, buffer: Union[str,  bytes,  bytearray]) -> bool:
        return True

    def close(self) -> None:
        pass


@frozen(kw_only=True)
class TitleFormat:
    # mode: StrmFilename
    title: str
    sep: str = ' '


@frozen(kw_only=True)
class FileTarget:
    path: APath
    mode: StrmFilename
    titles: Dict[StrmFilename, TitleFormat]


_RX_BORDER_REMOVE: Pattern[str] = re.compile(r'_(?=\s)')
# _RX_SAFE_REMOVE: Pattern[str] = re.compile(r'[_:*?!\"\'<>|/\\]+')
_RX_SAFE_REMOVE: Pattern[str] = re.compile(r'[^\w\s]|_')
_RX_MULIT_SPACE: Pattern[str] = re.compile(r'\s+')


def make_legal_fname(fname: str) -> str:
    """Fix kodi function, remove trailing /."""
    prefix = APath('/x')  # kodi skips first path segment
    fname = makeLegalFilename(str(prefix / fname))
    fname = fname[len(str(prefix))+1:]
    fname = _RX_BORDER_REMOVE.sub('', fname)
    return fname.rstrip('/')


def exists(path: Union[APath, str]) -> Optional[APath]:
    """Return name of the existing file if any has the same or a similar name. Otherwise None."""
    path = APath(path)
    path, fname = path.parent, _RX_MULIT_SPACE.sub(' ', _RX_SAFE_REMOVE.sub(' ', path.name.lower()))
    for fs in listdir(path):
        for f in fs:
            if fname == _RX_MULIT_SPACE.sub(' ', _RX_SAFE_REMOVE.sub(' ', f.lower())):
                return path / f
    return None


class LibTools:
    """Base class for library tools"""

    _DEBUG_FOLDER: ClassVar[Optional[str]] = None
    _DRY_RUN: ClassVar[bool] = False

    # EN locales
    EN_LOCALES: ClassVar[Sequence[str]] = ('en-US', 'en-GB', 'en')

    _RX_FNAME: ClassVar[Pattern[str]] = re.compile(r'[^\w\-]')
    _RX_WINDEVICE: ClassVar[Pattern[str]] = re.compile(r'\b(CON|PRN|AUX|NUL|COM\d+|LPT\d+)\.', flags=re.IGNORECASE)

    @property
    def movies_dir(self) -> APath:
        if self._DEBUG_FOLDER:
            return APath(self._DEBUG_FOLDER) / 'Movies'
        return APath(translatePath(settings.getString('library.movie')))

    @property
    def tv_dir(self) -> APath:
        if self._DEBUG_FOLDER:
            return APath(self._DEBUG_FOLDER) / 'TVShows'
        return APath(translatePath(settings.getString('library.tv')))

    def item_en_title(self, item: FFItem) -> str:
        """Return main English title of movie or show."""
        vtag = item.vtag
        if item.ref.season:  # season or episode
            if title := vtag.getEnglishTvShowTitle() or vtag.getTVShowTitle():
                return title
        return vtag.getEnglishTitle() or vtag.getTitle()

    def item_title(self, item: FFItem) -> str:
        """Return main local title of movie or show."""
        vtag = item.vtag
        if item.ref.season:  # season or episode
            if title := vtag.getTVShowTitle():
                return title
        return vtag.getTitle()

    def old_legal_filename(self, fname: str, *, sep: str = '.') -> str:
        fname = self._RX_FNAME.sub(sep, fname.strip()).strip()
        fname = _RX_BORDER_REMOVE.sub('', fname)
        fname = self._RX_WINDEVICE.sub(r'\1', fname)
        try:
            return make_legal_fname(fname)
        except RuntimeError:
            return fname

    def item_path_and_title(self, item: FFItem) -> FileTarget:
        """Return absolute path to item folder, item title (with year) and all old title formats."""
        path = self.tv_dir if item.ref.type == 'show' else self.movies_dir
        suffix = f' ({item.year})' if item.year else ''
        lang = const.library.title_language
        if not lang or lang in self.EN_LOCALES:
            title = self.item_en_title(item)
        else:
            # custom folder language
            en_title = self.item_en_title(item)
            en_path = path / f'{make_legal_fname(en_title)}{suffix}'
            if exists(en_path):
                # English folder exists, ues it to avoid duplication
                title = en_title
            else:
                # there is no English folder, specifed language could be used
                title = self.item_title(item)
        full_title = make_legal_fname(f'{title}{suffix}')

        return FileTarget(path=path / full_title, mode=const.library.strm_filename, titles={
            StrmFilename.DOT: TitleFormat(title=self.old_legal_filename(title), sep='.'),
            StrmFilename.LOW_LINE: TitleFormat(title=self.old_legal_filename(title, sep='_'), sep='.'),
            StrmFilename.TITLE: TitleFormat(title=make_legal_fname(title), sep=' '),
            StrmFilename.TITLE_YEAR: TitleFormat(title=full_title, sep=' '),
        })

    @overload
    def check_in_library(self, imdb_id: str, year: Optional[int] = None, *, all_episodes: Literal[True],
                         season: Optional[int] = None, episode: Optional[int] = None, include_streamdetails: bool = False) -> Optional[List[InLibDict]]: ...

    @overload
    def check_in_library(self, imdb_id: str, year: Optional[int] = None, *, all_episodes: Literal[False] = False,
                         season: Optional[int] = None, episode: Optional[int] = None, include_streamdetails: Literal[True]) -> Optional[InLibDict]: ...

    @overload
    def check_in_library(self, imdb_id: str, year: Optional[int] = None, *, all_episodes: Literal[False] = False,
                         season: Optional[int] = None, episode: Optional[int] = None, include_streamdetails: Literal[False] = False) -> Optional[str]: ...

    # TODO: rewrite this functon
    @lru_cache(maxsize=1000)
    def check_in_library(
        self,
        imdb_id: str,
        year: Optional[int] = None,
        *,
        all_episodes: bool = False,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        include_streamdetails: bool = False,
    ) -> Optional[Union[str, InLibDict, List[InLibDict]]]:
        rpc_client = KodiRpc()

        def find_tvshow() -> Optional[dict]:
            try:
                tvshows = rpc_client.rpc_list(
                    'VideoLibrary.GetTVShows',
                    params={'filter': {'field': 'year', 'operator': 'is', 'value': str(year)}},
                    fields=['uniqueid', 'title', 'originaltitle', 'file']
                )
                return next((s for s in tvshows if s.get('uniqueid', {}).get('imdb') == imdb_id), None)
            except Exception:
                return None

        def get_episodes(tvshow_id: int, filter_params: Optional[dict] = None, include_streamdetails: bool = False) -> list[InLibDict]:
            try:
                return cast(list[InLibDict], rpc_client.rpc_list(
                    'VideoLibrary.GetEpisodes',
                    params={'tvshowid': tvshow_id, **({'filter': filter_params} if filter_params else {})},
                    fields=['file', 'season', 'episode'] + (['streamdetails'] if include_streamdetails else [])
                ))
            except Exception:
                return []

        if all_episodes:
            fflog(f'Sprawdzanie serialu z IMDb ID: {imdb_id} z rokiem: {year}')
            tvshow = find_tvshow()
            if tvshow:
                fflog(f'Znaleziono serial: {tvshow.get("title") or tvshow.get("originaltitle")} (tvshowid: {tvshow["tvshowid"]})')
                episodes_in_library = get_episodes(tvshow['tvshowid'], include_streamdetails=include_streamdetails)
                return [ep for ep in episodes_in_library]
            fflog(f'Serial z IMDb ID: {imdb_id} nie znaleziony w bibliotece.')
            return None

        elif season is not None and episode is not None:
            fflog(f'Sprawdzanie odcinka S{season}E{episode} serialu z IMDb ID: {imdb_id}')
            tvshow = find_tvshow()
            if tvshow:
                fflog(f'Znaleziono serial (tvshowid: {tvshow["tvshowid"]}), sprawdzam odcinek...')
                filter_params = {
                    'and': [
                        {'field': 'season', 'operator': 'is', 'value': season},
                        {'field': 'episode', 'operator': 'is', 'value': episode}
                    ]
                }
                episodes_in_library = get_episodes(tvshow['tvshowid'], filter_params, include_streamdetails=include_streamdetails)
                if episodes_in_library:
                    return episodes_in_library[0] if include_streamdetails else episodes_in_library[0]['file']
                fflog(f'Odcinek S{season}E{episode} nie znaleziony.')
            else:
                fflog(f'Serial z IMDb ID: {imdb_id} nie znaleziony.')
            return None

        else:
            fflog(f'Sprawdzanie filmu z IMDb ID: {imdb_id} z rokiem: {year}')
            try:
                movies = rpc_client.rpc_list(
                    'VideoLibrary.GetMovies',
                    params={'filter': {'field': 'year', 'operator': 'is', 'value': str(year)}},
                    fields=['uniqueid', 'title', 'originaltitle', 'file'] + (['streamdetails'] if include_streamdetails else [])
                )
                for movie in movies:
                    if movie.get('uniqueid', {}).get('imdb') == imdb_id:
                        fflog(f'Znaleziono film: {movie.get("title") or movie.get("originaltitle")}')
                        return movie if include_streamdetails else movie['file']
                fflog(f'Film z IMDb ID: {imdb_id} nie znaleziony.')
            except Exception:
                fflog(f'Błąd podczas sprawdzania filmu z IMDb ID: {imdb_id}')
            return None

    def clear_cache(self):
        try:
            # spodziewam się tu wyjątku zawsze (rysson)
            self.check_in_library.cache_clear()
        except Exception:
            fflog_exc()

    @contextmanager
    def write(self, path: APath) -> Iterator[KodiWritableFile]:
        """Just fill the file with its content"""
        if exists(path):
            # fflog(f'Dummy open path {path} : {path.exists()}')
            yield DummyFile()
        elif self._DRY_RUN:
            print(f'DRY: write file {path}')
            yield DummyFile()
        else:
            # fflog(f'Try to open path {path} : {path.exists()}')
            with File(path, 'w') as file:
                # fflog(f'Open path {path} : {path.exists()} – {file}')
                yield file

    def mkdirs(self, path: APath) -> Optional[APath]:
        """Create directories like APath.mkdir(parents=True, exist_ok=True)."""
        if old := exists(path):
            return old
        if self._DRY_RUN:
            print(f'DRY: mkdir {path}')
            return path
        if mkdirs(path):
            return path
        return None

    def write_nfo(self, path: str, item: FFItem) -> None:
        """Write nfo info in base XML format
            TODO: Add more tags if neccessary
        """
        # root element
        media_tag = ET.Element(str(item.type))
        # child title elem
        title = ET.SubElement(media_tag, "title")
        title.text = item.title
        # child unique id elem
        uniqueid = ET.SubElement(media_tag, "uniqueid")
        uniqueid.set("type", "tmdb")
        uniqueid.set("default", "true")
        uniqueid.text = str(item.ffid)
        # create an ETree from root
        tree = ET.ElementTree(media_tag)
        ET.indent(tree, space="\t", level=0)
        # write to file
        if self._DRY_RUN:
            print(f'DRY: write nfo  {path}')
        else:
            tree.write(path, encoding="UTF-8", xml_declaration=True, method="xml")

    @contextmanager
    def open_title(self, target: FileTarget, fname_format: str) -> Iterator[KodiWritableFile]:
        """Open file to write with title or old_titles if detected."""
        path = target.path
        for mode, tit in target.titles.items():
            if mode != target.mode and (old := exists(path / fname_format.format(title=tit.title, sep=tit.sep))):
                # another format detected, switch the format
                path = old
                break
        else:
            fmt = target.titles[target.mode]
            path = path / fname_format.format(title=fmt.title, sep=fmt.sep)
        if self._DRY_RUN:
            print(f'DRY: write title {path}')
            yield DummyFile()
        else:
            with self.write(path) as file:
                yield file

    def _add_movie(self, item: FFItem, *, reload: bool = True) -> None:
        """Add single movie to the library."""
        ref = item.ref

        target = self.item_path_and_title(item)
        imdb_id = item.vtag.getIMDBNumber()
        year = item.vtag.getYear()
        if settings.getBool('library.check'):
            if self.check_in_library(imdb_id=imdb_id, year=year):
                fflog(f'Film {imdb_id} already exists in library.')
                return

        if old := self.mkdirs(target.path):
            target = evolve(target, path=old)
        # prepare strm file
        with self.open_title(target, '{title}.strm') as f:
            f.write(str(url_for(play, ref=MediaRef('movie', ref.ffid))))
        # prepare nfo file
        with self.write(target.path / 'movie.nfo') as f:
            f.write(ffinfo.web_url(ref))
        # update kodi library
        if reload:
            executebuiltin('UpdateLibrary(video)', True)

    def _should_write_episode(self, ep: FFItem, existing_episodes: Optional[List[InLibDict]]) -> bool:
        """Determine if an episode should be written to the library."""
        if settings.getBool('library.check') and existing_episodes is not None:
            for existing in existing_episodes:
                if existing.get('season') == ep.season and existing.get('episode') == ep.episode:
                    return False  # Episode already exists, do not write

        include_unknown = settings.getBool('library.include_unknown')
        days_delay = settings.getInt('library.days_delay')
        cutoff_date = datetime.now() - timedelta(days=days_delay)

        if not (include_unknown or ep.aired_before(cutoff_date)):
            return False  # Conditions for writing are not met

        return True  # Episode should be written

    def _write_episode(self, ep: FFItem, *, target: FileTarget, existing_episodes: Optional[List[InLibDict]]) -> None:
        """Write single episode."""
        fflog(f'Entering _write_episode for S{ep.season:02d}E{ep.episode:02d}.')

        if not self._should_write_episode(ep, existing_episodes):
            return  # Episode should not be written

        fflog(f'Attempting to write episode S{ep.season:02d}E{ep.episode:02d}.')
        with self.open_title(target, f'{{title}}{{sep}}S{ep.season:02d}E{ep.episode:02d}.strm') as f:
            f.write(str(url_for(play, ref=MediaRef('show', ep.ref.ffid, season=ep.ref.season, episode=ep.ref.episode))))
        fflog(f'Successfully wrote episode S{ep.season:02d}E{ep.episode:02d}.')

    def _write_season(self, sz: FFItem, *, target: FileTarget, flat: bool, existing_episodes: Optional[List[InLibDict]]) -> None:
        """Write single season."""
        # Check if any episode in this season needs to be written
        episodes_to_write = [ep for ep in sz.episode_iter() if self._should_write_episode(ep, existing_episodes)]

        if not episodes_to_write:
            fflog(f'No episodes to write for Season {sz.season}. Skipping season folder creation.')
            return  # No episodes to write, so skip creating the season folder

        season_path = target.path if flat else target.path / f'Season {sz.season}'
        self.mkdirs(season_path)
        # check style of first episode (with or without year) - optamlize, to avoid checking for each episode
        for mode, tit in target.titles.items():
            if mode != target.mode and exists(season_path / f'{tit.title}{tit.sep}S{sz.season:02d}E01.strm'):
                # another format detected, switch the format (and udpate season path)
                target = evolve(target, mode=mode, path=season_path)
                break
        else:
            # no other format detectef, use prefered one (and udpate season path)
            if target.path != season_path:
                target = evolve(target, path=season_path)
        # iterate over episodes
        for ep in episodes_to_write:  # Iterate only over episodes that need to be written
            self._write_episode(ep, target=target, existing_episodes=existing_episodes)

    def _add_show(self, item: FFItem, *, reload: bool = True) -> None:
        """Add single show (with all episodes) to the library."""
        show_item = item if item.ref.is_show else item.show_item
        if show_item is None:
            fflog(f'Missing show_item for {item.ref!r}')
            return
        target = self.item_path_and_title(show_item)
        existing_episodes = None
        imdb_id = show_item.vtag.getIMDBNumber()
        year = int(show_item.vtag.getYear())

        if settings.getBool('library.check'):
            result = self.check_in_library(imdb_id, year=year, all_episodes=True)
            if isinstance(result, list):
                existing_episodes: Optional[List[InLibDict]] = result
            else:
                existing_episodes = None
        else:
            fflog(f'Library check is disabled, adding all episodes for {imdb_id}.')

        # Determine if any episodes need to be written for the entire show
        any_episode_to_write = False
        if item.ref.is_show:
            for sz in item.season_iter():
                for ep in sz.episode_iter():
                    if self._should_write_episode(ep, existing_episodes):
                        any_episode_to_write = True
                        break
                if any_episode_to_write:
                    break
        elif item.ref.is_season:
            for ep in item.episode_iter():
                if self._should_write_episode(ep, existing_episodes):
                    any_episode_to_write = True
                    break
        elif item.ref.is_episode:
            if self._should_write_episode(item, existing_episodes):
                any_episode_to_write = True

        if not any_episode_to_write:
            fflog(f'No episodes to write for show {imdb_id}. Skipping show folder creation.')
            return  # No episodes to write, so skip creating the show folder

        if old := self.mkdirs(target.path):
            target = evolve(target, path=old)

        if const.library.flat_show_folder:
            flat = True
        else:
            # detect if any *.strm exists in the show folder
            flat = bool(next(iter(target.path.glob('*.strm')), None))
        # write strm file(s)
        if item.ref.is_show:
            # iterate over seasons
            for sz in item.season_iter():
                self._write_season(sz, target=target, flat=flat, existing_episodes=existing_episodes)
        elif item.ref.is_season:
            # write single season
            self._write_season(item, target=target, flat=flat, existing_episodes=existing_episodes)
        elif item.ref.is_episode:
            # create season path and write single epsiode
            if flat:
                season_target = target
            else:
                season_target = evolve(target, path=target.path / f'Season {item.season}')
            self.mkdirs(season_target.path)
            self._write_episode(item, target=season_target, existing_episodes=existing_episodes)
        else:
            fflog(f'PANIC!!! unknown ref {item.ref!r}')
        # prepare nfo file
        with self.write(target.path / 'tvshow.nfo') as f:
            f.write(ffinfo.web_url(show_item.ref))
        # update kodi library
        if reload:
            executebuiltin("UpdateLibrary(video)", True)

    def add(self, items: Union[MediaRef, FFItem, Sequence[Union[MediaRef, FFItem]]], *, reload: bool = True) -> None:
        """Add item or items (normalized with TMDB id). Get skeleton data."""
        if not items:
            return
        if isinstance(items, (MediaRef, FFItem)):
            items = [items]
        for item in ffinfo.get_en_skel_items(items, locale=const.library.title_language):
            if self._DRY_RUN:
                print(f'ADD: {item}')
            if item.ref.is_movie:
                self._add_movie(item, reload=reload)
            elif item.ref.type == 'show':  # show, season, episode
                self._add_show(item, reload=reload)
            else:
                fflog(f'Unsupported type {item.ref!r}')
        if settings.getBool('library.check'):
            self.clear_cache()

    def add_single(self, item: Union[MediaRef, FFItem], *, reload: bool = True) -> None:
        if isinstance(item, MediaRef):
            if found := ffinfo.find_item(item, progress=ffinfo.Progress.NO, tv_episodes=True, crew_limit=0):
                item = found
            else:
                return
        if item.ref.is_movie:
            self._add_movie(item, reload=reload)
        elif item.ref.type == 'show':  # show, season, episode
            self._add_show(item, reload=reload)
        else:
            fflog(f'Unsupported type {item.ref!r}')
        if settings.getBool('library.check'):
            self.clear_cache()

    def add_multiple(self, items) -> None:
        """Add multiple media items to library"""

        raise NotImplementedError('\nNOT implemented yet\n')

        heading = L(30124, 'Add to library')
        choices = Dialog().multiselect(heading, [item for item in items if item])
        if choices:
            for idx in choices:
                ffitem = items[idx]
                # make sure ffitem and ffid exist
                if ffitem:
                    ffid = ffitem.ffid
                    if ffid:
                        self.add_single(ffid, ffitem, reload=False)

            # update kodi library
            executebuiltin("UpdateLibrary(video)", True)


library = LibTools()


if __name__ == '__main__':
    from .cmdline import DebugArgumentParser, parse_ref
    from cdefs import constdef
    from ..service.client import service_client

    p = DebugArgumentParser(dest='cmd')
    p.add_argument('--media-dir', help='override media folder')
    p.add_argument('--service', action='store_true', help='start service')
    p.add_argument('--no-service', action='store_false', dest='service', help='skip service (default)')
    p.add_argument('--dry-run', action='store_true', help='dry run, do not write anything')
    with p.with_subparser('add') as pp:
        # pp.add_argument('ref', type=parse_ref, help='ref to media')
        pp.add_argument('ref', nargs='+', type=parse_ref, help='media ref')
    args = p.parse_args()
    # print(args); exit()

    if args.dry_run:
        LibTools._DRY_RUN = True
    if args.service:
        pass
        # service = start_service()
    else:
        constdef._locked = False  # type: ignore
        const.tune.service.http_server.try_count = 1
        constdef._locked = True  # type: ignore
        service = None
        service_client.__class__.LOG_EXCEPTION = False
    if args.media_dir:
        LibTools._DEBUG_FOLDER = args.media_dir
    # if args.cmd == 'add':
    #     library.add_single(args.ref, reload=False)
    if args.cmd == 'add':
        library.add(args.ref, reload=False)
