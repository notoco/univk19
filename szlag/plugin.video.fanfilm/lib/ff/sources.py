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

import datetime
import json
import random
import re
import sys
from contextlib import suppress
from threading import Lock
from ast import literal_eval
from enum import Enum, IntEnum
from html import unescape
from pathlib import Path
from sqlite3 import dbapi2 as database, Cursor as SqlCursor, OperationalError
from typing import Optional, Union, Any, Dict, List, Set, Sequence, Type, TypeVar, Iterable, Iterator, Tuple, TYPE_CHECKING
from typing_extensions import TypedDict, NotRequired, Unpack, Protocol, Literal, Self
from urllib.parse import parse_qsl, quote_plus, unquote
from attrs import asdict

# import requests
import xbmc
from xbmcgui import DialogProgress, DialogProgressBG

import PTN
from ..ff import (
    apis,
    cache,
    cleantitle,
    client,
    control,
    debrid,
    source_utils,
)
from lib.windows.sources import SourceDialog, RescanSources, EditDialog
from ..ff.info import ffinfo
from ..ff.item import FFItem
from ..ff.kotools import get_platform
from ..defs import MediaRef, MediaType
from ..ff import player
from ..ff.db import state
from ..sources import SourceModule, scan_source_modules, clear_source_modules, SourceMeta, Source, SourceResolveKwargs, ProviderProtocol
from .log_utils import fflog, fflog_exc, log
from .workers import Thread
from .settings import settings
from .kotools import xsleep
from .. import FAKE
from ..kolang import L
from cdefs import SourcePattern, SourceAttribute
from const import const
if TYPE_CHECKING:
    from typing_extensions import LiteralString

try:
    import resolveurl
except Exception as e:
    print(e)
    resolveurl = None


Item = SourceMeta


#: Type of resolver object.
class ResolverClass(Protocol):
    name: str
    domains: Sequence[str]
    pattern: Optional[str] = None


# 1 GiB
GB = 1024**3


class SourceSearchQuery(TypedDict):
    localtitle: str
    title: str
    originalname: str
    year: int
    premiered: str
    imdb: str
    tmdb: str
    tvshowtitle: str
    season: Optional[int]
    episode: Optional[int]
    ffitem: FFItem


#: Link to default color.
DEFAULT_COLOR_LINK: str = "00000000"


class SortElem(Enum):  # NOTE: MUST be in the "hosts.sort.elemN" setting option order
    SERVICE = 0
    LANGUAGE = 1
    QUALITY = 2
    SIZE = 3
    NONE = 4


class Quality(IntEnum):  # NOTE: values in setting "hosts.quality.max" / "hosts.quality.min" values
    """Quality (video resolution)."""
    SD = 0
    HD = 1
    FHD = 2
    QHD = 3
    UHD = 4

    H_480 = SD
    H_720 = HD
    H_1080 = FHD
    H_1440 = QHD
    H_2160 = UHD


class ProgressDialogMode(Enum):
    """Mode of progerss dialog in values od `progress.dialog` setting."""
    MODAL = 0
    BACKGROUND = 1


class GetSourcesKwargs(TypedDict):
    title: str
    localtitle: str
    year: int
    imdb: str
    tmdb: str
    season: Optional[int]
    episode: Optional[int]
    tvshowtitle: str
    premiered: str
    originalname: NotRequired[str]
    quality: NotRequired[str]
    timeout: NotRequired[int]
    ffitem: FFItem
    progress_dialog: NotRequired[Union[DialogProgress, DialogProgressBG, None]]


class ProvidersSetting(dict):
    """
    Simple setting cache, for mass prviders query.

    >>> so = ProvidersSetting('sort.order', default=0, source_mods=mods)
    >>> so['cda']  # value of 'cda.sort.order'
    """

    def __init__(self, name: str, *, default: Any, source_mods: List[SourceModule]) -> None:
        var_name: str = f'has_{name.replace(".", "_")}'
        super().__init__()
        #: Settings name (suffix).
        self.name: str = name
        #: Default valur if settings is not found.
        self.default: Any = default
        #: Providers with settings enabled.
        self._enabled: Set[str] = {srcmod.name for srcmod in source_mods if getattr(srcmod.provider, var_name, False)}

    def _get_settings(self, name: str) -> Any:
        return settings.getString(name)

    def __missing__(self, key: str) -> Any:
        key = key.lower()
        if key in self._enabled:
            value = self._get_settings(f'{key}.{self.name}')
        else:
            value = self.default  # default no-order
        self[key] = value
        return value


class SortOrderSettings(ProvidersSetting):
    """Simple setting cache, for mass query (sorting in filters)."""

    def __init__(self, *, source_mods: List[SourceModule]) -> None:
        super().__init__(name='sort.order', default=None, source_mods=source_mods)

    def _get_settings(self, name: str) -> int:
        return settings.getInt(name)


class ColorSettings(ProvidersSetting):
    """Simple setting cache, for mass query (sorting in filters)."""

    def __init__(self, *, source_mods: List[SourceModule]) -> None:
        super().__init__(name='color.identify2', default=None, source_mods=source_mods)


class LibraryColorSettings(ProvidersSetting):
    """Simple setting cache, for mass query (sorting in filters)."""

    def __init__(self, *, source_mods: List[SourceModule]) -> None:
        super().__init__(name='library.color.identify2', default=None, source_mods=source_mods)


class sources:
    QUALITIES = {
        Quality.UHD: {"4K", "8K"},
        Quality.QHD: {"1440p"},
        Quality.FHD: {"1080p", "1080i", "FHD"},
        Quality.HD: {"720p", "HD"},
        Quality.SD: {"480p", "SD"},
    }

    TOTAL_FORMAT = "[COLOR {color}][B]{count}[/B][/COLOR]"
    PDIAG_NORM_FORMAT = [sect.split("|") for sect in "4K: %s | 1440: %s | 1080: %s | 720: %s | SD: %s || %s: %s".split("||")]
    PDIAG_PREM_FORMAT = [sect.split("|") for sect in "%s:|| 4K: %s | 1440: %s | 1080: %s | 720: %s | SD: %s || %s: %s".split("||")]
    PDIAG_BG_FORMAT = [sect.split("|") for sect in "4K:%s(%s)|1440:%s(%s)|1080:%s(%s)|720:%s(%s)|SD:%s(%s)||%s(%s)".split("||")]

    # Priorytet typu języka
    language_type_priority = const.sources_dialog.language_type_priority

    def __init__(self):
        self.lock = Lock()
        self.sourceFile = control.providercacheFile
        self.selectedSource = None
        self.itemProperty = None
        self.metaProperty = None
        self.source_mods: List[SourceModule] = None
        self.host_list: List[str] = []
        self.pr_host_list: List[str] = []
        self.hq_host_list: List[str] = []
        self.sources: List[Source] = []
        self.test = {}
        self.lang = control.apiLanguage()["tmdb"] or "en"
        self.exts = ("avi", "mkv", "mp4", ".ts", "mpg")  # dozwolone rozszerzenia filmów

    def play(self,
             media_type: MediaType,
             ffid: int,
             season: Optional[int] = None,
             episode: Optional[int] = None,
             *,
             edit_search: bool = False,
             ) -> None:
        # show progress window to make placebo effect
        progress_dialog_mode = ProgressDialogMode(settings.getInt('progress.dialog'))
        progress_dialog: Union[DialogProgress, DialogProgressBG, None] = None
        with suppress(Exception):
            if progress_dialog_mode is ProgressDialogMode.BACKGROUND:
                progress_dialog = DialogProgressBG()
            else:
                progress_dialog = DialogProgress()
            progress_dialog.create(control.addonInfo('name'), '')
            self.initial_progress_update(progress_dialog)
        try:
            # state.delete_all(module='player')
            with state.with_var('ff.play', module='player'):
                return self._play(media_type=media_type, ffid=ffid, season=season, episode=episode, edit_search=edit_search)
        except Exception:
            fflog_exc()
            raise
        finally:
            if progress_dialog is not None:
                with suppress(Exception):
                    progress_dialog.close()
            clear_source_modules()

    def _play(self,
              media_type: MediaType,
              ffid: int,
              season: Optional[int] = None,
              episode: Optional[int] = None,
              *,
              edit_search: bool = False,
              progress_dialog: Union[DialogProgress, DialogProgressBG, None] = None,
              ) -> None:
        # mark playing state
        state.multi_set(module='player', values=(
            ('playing.run', False),
        ))

        # TODO:  -----------------------------------------------------------------
        # TODO:  ---  refaktor, bez sensu odzyskuje pewne dane, zanim użyć ffinfo
        # TODO:  -----------------------------------------------------------------

        ref: MediaRef = MediaRef(media_type, ffid, season, episode)
        ffitem: Optional[FFItem] = ffinfo.find_item(ref)
        if ffitem is None:
            return
        ffitem.copy_from(ffitem.season_item, ffitem.show_item)

        if ref.type == 'show' and (sh_item := ffitem.show_item):
            vtag = sh_item.getVideoInfoTag()
            premiered = sh_item.date
            show_title = vtag.getEnglishTvShowTitle() or sh_item.title
        else:
            vtag = ffitem.getVideoInfoTag()
            premiered = ffitem.date
            show_title = ''
        # get aliases (new way)
        ffinfo.title_aliases(ffitem)

        self.getConstants(ffitem=ffitem)
        self.sources = []
        fflog(f"play(ffid={ffid!r}) #srcmods={len(self.source_mods)}")

        # `title` and `show_title` should be in English.
        title = vtag.getTitle()
        data_dict: SourceSearchQuery = {
            "title": vtag.getEnglishTitle() or vtag.getOriginalTitle() or title,
            "localtitle": title,  # title is in api locale
            "year": vtag.getYear(),
            "imdb": vtag.getUniqueID('imdb'),
            "tmdb": vtag.getUniqueID('tmdb'),
            "season": ffitem.season,
            "episode": ffitem.episode,
            "tvshowtitle": show_title,
            "premiered": str(premiered or ''),
            "originalname": vtag.getOriginalTitle(),
            "ffitem": ffitem,
        }

        with state.with_var('sources', module='player'):
            while True:
                source_to_play: Optional[Source] = None
                if edit_search:
                    sources = []
                else:
                    sources = self.get_sources(**data_dict, progress_dialog=progress_dialog) or []
                    if progress_dialog is not None:
                        with suppress(Exception):
                            progress_dialog.close()
                            progress_dialog = None
                try:
                    if edit_search:
                        # edit search without source-dialog in background
                        win = EditDialog(query=data_dict)
                        win.doModal()
                        del win
                        break
                    elif FAKE:
                        from lib.fake.fake_source_dialog import fake_source_list_dialog
                        source_to_play = fake_source_list_dialog(source_manager=self, item=ffitem, items=sources)
                        break
                    else:
                        if len(sources) > 0 or const.sources_dialog.show_empty or edit_search:
                            with state.with_var('sources.window', module='player'):
                                win = SourceDialog(sources=self, item=ffitem, items=sources, query=data_dict, edit_search=edit_search)
                                source_to_play = win.doModal()
                                del win
                        else:
                            control.Notification('FanFilm', L(30250, 'No sources found')).show()
                        break
                except RescanSources as rescan:
                    if rescan.query:
                        fflog(f'[SOURCES] rescan request (edit={data_dict != rescan.query})')
                        if data_dict == rescan.query:  # the same means RESCAN, clear cache
                            from .cache import cache_clear_sources
                            self.sources.clear()
                            cache_clear_sources()
                        data_dict = rescan.query
                        data_dict['ffitem'] = ffitem
                except Exception:
                    fflog_exc()
                    break
                edit_search = False  # skip only first sources scan
        fflog(f'source to play {source_to_play!r}')
        with state.with_var('playing.prepare', module='player'):
            if source_to_play:
                player.play(source=source_to_play)
            else:
                player.cancel(ffitem)

    def get_sources(self, **kwargs: Unpack[GetSourcesKwargs]) -> List[Source]:
        with state.with_var('sources.scan', module='player'):
            return self._get_sources(**kwargs)

    def src_format(self, fmt: 'list[list[LiteralString]]', *, qrange: Optional[range]) -> Iterator[str]:
        if qrange is None:
            qmax = settings.getInt("hosts.quality.max")
            qmin = settings.getInt("hosts.quality.min")
            qrange = range(qmin, qmax + 1)
        for f in fmt:
            if len(f) > 2:  # sources
                inc = f[::-1]
                for i in reversed(qrange):  # no reversed(), because pdiag_*_format has already reverted order
                    yield inc[i]
            else:
                yield from f

    def initial_progress_update(self, progress_dialog: Union[DialogProgress, DialogProgressBG, None]) -> None:
        """Initial progress dialog update."""
        if progress_dialog is None:
            return
        string_total = L(32601, 'Total')
        qmax = settings.getInt("hosts.quality.max")
        qmin = settings.getInt("hosts.quality.min")
        qrange = range(qmin, qmax + 1)
        TOTAL = len(self.QUALITIES)
        source_qq = [0] * (TOTAL + 1)    # +1 for [TOTAL]
        source_labels = [self.TOTAL_FORMAT.format(color=("lime" if sq > 0 else "red"), count=sq) for sq in source_qq]
        line = "|".join(self.src_format(self.PDIAG_NORM_FORMAT, qrange=qrange)) % (
            *(source_labels[i] for i in reversed(qrange)),
            str(string_total),
            source_qq[TOTAL],
        )
        progress_dialog.update(0, line)
        # progress_dialog.update(0, L(32600, 'Preparing sources\nQWE'))

    def _get_sources(self, *,
                     title: str,
                     localtitle: str,
                     year: int,
                     imdb: str,
                     tmdb: str,
                     season: Optional[int],
                     episode: Optional[int],
                     tvshowtitle: str,
                     premiered: str,
                     originalname: str = "",
                     quality: str = "HD",
                     timeout: int = 30,
                     ffitem: FFItem,
                     progress_dialog: Union[DialogProgress, DialogProgressBG, None] = None,
                     ) -> List[Source]:
        # fflog("get_sources")
        fflog(f"\033[91mget_sources\033[0m({title=}, {localtitle=}, {year=}, {imdb=}, {tmdb=}, {season=}, {episode=}, {tvshowtitle=}, {premiered=}, {originalname=} ---------")
        # return []

        progress_dialog_mode = ProgressDialogMode(settings.getInt("progress.dialog"))
        if progress_dialog is None:
            if progress_dialog_mode is ProgressDialogMode.BACKGROUND:
                progress_dialog = DialogProgressBG()
            else:
                progress_dialog = DialogProgress()
            progress_dialog.create(control.addonInfo("name"), "")

        # progress_dialog.update(50, L(32600, 'Preparing sources\nQWE'))
        self.initial_progress_update(progress_dialog)

        self.prepareSources()

        # -------------------------------------------------------------------------------------------------------- XXX XXX XXX
        def log_source_mods(title='source_mods'):  # TODO: Rremove it  (DEBUG)
            from pprint import pformat
            nonlocal source_mods
            source_mods = list(source_mods)  # support for generators
            fflog(f'{title}\n{pformat(source_mods, indent=2, width=240, compact=False)}')

        source_mods: Iterable[SourceModule] = self.source_mods
        srcmod: SourceModule
        genres: Set[str]
        log_source_mods('start')
        for srcmod in source_mods:
            srcmod.provider.canceled = False

        # filtrowanie po dozowlonych providerach, tzn. takich, które włączył użytkownik w ustawieniach
        try:
            source_mods = filter(lambda srcmod: settings.getBool(f"provider.{srcmod.name}"), source_mods)
        except (TypeError, ValueError):
            fflog_exc()
        log_source_mods('enabled')

        content = "movie" if not season else "episode"
        if content == "movie":
            # filtrowanie po providerach, które posiadają metodę `movie()`
            source_mods = (srcmod for srcmod in source_mods if hasattr(srcmod.provider, "movie"))
            # TODO: TRAKT  genres = set(trakt.getGenre("movie", "imdb", imdb))
        else:
            # filtrowanie po providerach, które posiadają metodę `tvshow()`
            source_mods = (srcmod for srcmod in source_mods if hasattr(srcmod.provider, "tvshow"))
            # TODO: TRAKT  genres = set(trakt.getGenre("show", "tmdb", tmdb))
        log_source_mods('method')

        # filtrowanie po obsługiwanych gatunkach – ŻADEN provider tego nie dostarcza
        source_mods = filter(lambda srcmod: (not getattr(srcmod.provider, "genre_filter", ())
                                             or set(srcmod.provider.genre_filter) & genres),
                             source_mods)
        log_source_mods('genres')

        # filtrowanie po języku, czy provider dostarcza treści w jakimkowiek akceptowalnym dla nas języku
        langs: Set[str] = set(self.getLanguage())
        source_mods = filter(lambda srcmod: set(srcmod.provider.language) & langs, source_mods)
        log_source_mods('langs')

        # sortowanie po priorytecie
        if False:
            source_mods = list(source_mods)  # generator → list, for random.shuffle()
            random.shuffle(source_mods)
        # od tej pory `source_mods` jest listą nie generatorem, można wielokrotnie przeglądać
        source_mods = sorted(source_mods, key=lambda srcmod: srcmod.provider.priority)
        log_source_mods('sorted')

        # pozyskiwanie źródeł (linków) od providerów (w wątkach)
        threads: List[Thread] = []
        fake = str

        if content == "movie":
            # title = self.getTitle(title)  # niszczy polskie znaki diakrytyczne
            # localtitle = self.getTitle(localtitle)  # niszczy polskie znaki diakrytyczne
            # originalname = self.getTitle(originalname)  # niszczy polskie znaki diakrytyczne
            # aliases = self.getTMDBAliasTitles(tmdb, localtitle, content)
            aliases = self.getAliasTitles(imdb, localtitle, content, ffitem=ffitem)
            if originalname:
                aliases = [
                    {"originalname": originalname, "country": "original"},
                    *aliases,
                ]
            for srcmod in source_mods:
                threads.append(
                    Thread(
                        target=self.getMovieSource,
                        args=(title, localtitle, aliases, fake(year), imdb, srcmod.name, srcmod.provider),
                        kwargs={'ffitem': ffitem},
                        name=f'{srcmod.name} movie sources',
                    )
                )
            localtvshowtitle = ''
        else:
            # tvshowtitle = self.getTitle(tvshowtitle)  # niszczy polskie znaki diakrytyczne
            localtvshowtitle = self.getLocalTitle(tvshowtitle, imdb, tmdb, content)
            # aliases = self.getTMDBAliasTitles(tmdb, localtvshowtitle, content)
            aliases = self.getAliasTitles(imdb, localtvshowtitle, content, ffitem=ffitem)
            if originalname:
                aliases = [
                    {"originalname": originalname, "country": "original"},
                    *aliases,
                ]

            # Disabled on 11/11/17 due to hang. Should be checked in the future and possible enabled again.
            # season, episode = thexem.get_scene_episode_number(tvdb, season, episode)

            for srcmod in source_mods:
                threads.append(
                    Thread(
                        target=self.getEpisodeSource,
                        args=(
                            title,
                            localtitle,
                            fake(year),
                            imdb,
                            fake(tmdb),
                            fake(season),
                            fake(episode),
                            tvshowtitle or originalname,
                            localtvshowtitle,
                            aliases,
                            premiered,
                            srcmod.name,
                            srcmod.provider,
                        ),
                        kwargs={
                            'ffitem': ffitem,
                        },
                        name=f'{srcmod.name} episode sources',
                    )
                )

        # -------------------------------------------------------------------------------------------------------- XXX XXX XXX

        s_cholera_wie_co = [(th.name, srcmod.name, srcmod.provider.priority) for srcmod, th in zip(source_mods, threads)]

        mainsourceDict_który_nie_jest_dict_tylko_list = [i[0] for i in s_cholera_wie_co if i[2] == 0]
        sourcelabelDict = dict((i[0], i[1].upper()) for i in s_cholera_wie_co)

        for th in threads:
            th.start()

        string_remaining = L(32406, 'Remaining providers: %s')
        string_total = L(32601, 'Total')
        string_premium = L(32606, 'Prem')
        string_normal = L(32607, 'Normal')

        timeout = settings.getInt("scrapers.timeout.1")
        qmax = settings.getInt("hosts.quality.max")
        qmin = settings.getInt("hosts.quality.min")
        qrange = range(qmin, qmax + 1)

        line1 = line2 = line3 = ""
        # debrid_only = settings.getBool("debrid.only")  -- NOT USED

        pre_emp = settings.getBool("preemptive.termination")
        pre_emp_limit = settings.getInt("preemptive.limit")

        TOTAL = len(self.QUALITIES)
        source_qq = [0] * (TOTAL + 1)    # +1 for [TOTAL]
        d_source_qq = [0] * (TOTAL + 1)  # +1 for [TOTAL]

        debrid_list = debrid.debrid_resolvers
        debrid_status = debrid.status()

        total_format = self.TOTAL_FORMAT
        pdiag_norm_format = self.PDIAG_NORM_FORMAT
        pdiag_prem_format = self.PDIAG_PREM_FORMAT
        pdiag_bg_format = self.PDIAG_BG_FORMAT

        i = 0
        # 4 * timeout: timeout in sec, sleep: 1/2 sec, postpone: 2 x (???)
        for i in range(0, 4 * timeout):
            if pre_emp and pre_emp_limit:
                if sum(source_qq) + sum(d_source_qq) >= pre_emp_limit:
                    fflog(f"osiągnięto limit ilości źródeł ({pre_emp_limit})")
                    break

            try:
                if xbmc.Monitor().abortRequested():
                    return sys.exit()

                with suppress(AttributeError):
                    if progress_dialog.iscanceled():
                        break

                for q in qrange:
                    qq = self.QUALITIES[Quality(q)]
                    source_qq[q] = sum(1 for e in self.sources if e["quality"] in qq and not e["debridonly"])
                source_qq[TOTAL] = sum(source_qq[0:TOTAL])

                if debrid_status:
                    for q in qrange:
                        for d in debrid_list:
                            qq = self.QUALITIES[Quality(q)]
                            d_source_qq[q] = sum(1 for e in self.sources if e["quality"] in qq and d.valid_url("", e["hosting"]))
                d_source_qq[TOTAL] = sum(d_source_qq[0:TOTAL])

                source_labels = [total_format.format(color=("lime" if sq > 0 else "red"), count=sq) for sq in source_qq]
                d_source_labels = [total_format.format(color=("lime" if sq > 0 else "red"), count=sq) for sq in d_source_qq]

                if (i / 2) < timeout:
                    line2 = ''
                    try:
                        mainleft = [
                            sourcelabelDict[x.name]
                            for x in threads
                            if x.is_alive() and x.name in mainsourceDict_który_nie_jest_dict_tylko_list
                        ]
                        info = [
                            sourcelabelDict[x.name]
                            for x in threads
                            if x.is_alive()
                        ]

                        if not debrid_status:
                            line1 = "|".join(self.src_format(pdiag_norm_format, qrange=qrange)) % (
                                *(source_labels[i] for i in reversed(qrange)),
                                str(string_total),
                                source_qq[TOTAL],
                            )
                        elif progress_dialog_mode is ProgressDialogMode.MODAL:
                            line1 = "|".join(self.src_format(pdiag_prem_format, qrange=qrange)) % (
                                string_premium,
                                *(d_source_labels[i] for i in reversed(qrange)),
                                str(string_total),
                                d_source_qq[TOTAL],
                            )
                            line2 = "|".join(self.src_format(pdiag_prem_format, qrange=qrange)) % (
                                string_normal,
                                *(source_labels[i] for i in reversed(qrange)),
                                str(string_total),
                                source_qq[TOTAL],
                            )
                        else:  # debrid_status and bg dialog
                            line1 = "|".join(self.src_format(pdiag_bg_format, qrange=qrange)) % (
                                *(v for i in reversed(qrange) for v in (source_labels[i], d_source_labels[i])),
                                str(string_total), source_qq[TOTAL],
                            )

                        percent = int(100 * i / (2 * timeout) + 0.5)
                        if debrid_status:
                            if len(info) > 6:
                                line3 = string_remaining % (str(len(info)))
                            elif len(info) > 0:
                                line3 = string_remaining % (", ".join(info))
                            else:
                                break
                            if line2:
                                progress_dialog.update(max(1, percent), line1 + "\n" + line2 + "\n" + line3)
                            else:
                                progress_dialog.update(max(1, percent), line1 + "\n" + line3)
                        else:
                            if len(info) > 6:
                                line2 = string_remaining % (str(len(info)))
                            elif len(info) > 0:
                                line2 = string_remaining % (", ".join(info))
                            else:
                                break
                            progress_dialog.update(max(1, percent), line1 + "\n" + line2)
                    except Exception:
                        fflog_exc()
                else:
                    fflog(f"przerwanie wyszukiwania - przekroczenie ustalonego czasu ({i//2} s.)")
                    try:
                        mainleft = [
                            sourcelabelDict[x.name]
                            for x in threads
                            if x.is_alive() and x.name in mainsourceDict_który_nie_jest_dict_tylko_list
                        ]
                        info = mainleft
                        if debrid_status:
                            if len(info) > 6:
                                line3 = "Waiting for: %s" % (str(len(info)))
                            elif len(info) > 0:
                                line3 = "Waiting for: %s" % (", ".join(info))
                            else:
                                break
                            percent = min(100, int(100 * i / (2 * timeout) + 0.5))
                            if progress_dialog_mode is ProgressDialogMode.MODAL:
                                progress_dialog.update(max(1, percent), line1 + "\n" + line2 + "\n" + line3)
                            else:
                                progress_dialog.update(max(1, percent), line1 + "\n" + line3)
                        else:
                            if len(info) > 6:
                                line2 = "Waiting for: %s" % (str(len(info)))
                            elif len(info) > 0:
                                line2 = "Waiting for: %s" % (", ".join(info))
                            else:
                                break
                            percent = int(100 * float(i) / (2 * timeout) + 0.5) % 100
                            progress_dialog.update(max(1, percent), line1 + "\n" + line2)
                    except Exception:
                        break

                from threading import current_thread
                fflog(f'[SOURCES] current threads: {current_thread().name}')
                xsleep(.5)
            except Exception:
                pass
        try:
            progress_dialog.close()
        except Exception:
            pass

        # all threads should stops as soon as possible
        if alive_threads := [th for th in threads if th.is_alive()]:
            fflog(f'[SOURCES] {len(alive_threads)} threads not finished at get_sources() exit')
            for th in alive_threads:
                th.stop()
            # for srcmod in source_mods:
            #     srcmod.source.canceled = True

        self.sourcesFilter(ffitem=ffitem)
        return self.sources

    def prepareSources(self):
        fflog("prepareSources")
        if settings.getBool("enableSourceCache"):
            if not control.existsPath(control.dataPath):
                control.make_dir(control.dataPath)
            self.sourceFile = control.sourcescacheFile
        else:
            self.sourceFile = ':memory:'

    def _init_sources_db(self, dbcur: SqlCursor) -> None:
        try:
            dbcur.execute(
                "CREATE TABLE IF NOT EXISTS rel_url ("
                "source TEXT, "
                "imdb_id TEXT, "
                "season TEXT, "
                "episode TEXT, "
                "rel_url TEXT, "
                "UNIQUE(source, imdb_id, season, episode)"
                ");"
            )
            dbcur.execute(
                "CREATE TABLE IF NOT EXISTS rel_src ("
                "source TEXT, "
                "imdb_id TEXT, "
                "season TEXT, "
                "episode TEXT, "
                "hosts TEXT, "
                "added TEXT, "
                "UNIQUE(source, imdb_id, season, episode)"
                ");"
            )
        except OperationalError:
            fflog_exc()

    def getMovieSource(self, title, localtitle, aliases, year, imdb, source, call: ProviderProtocol, from_cache=False, *, ffitem: FFItem):
        fflog(f'getMovieSource {source=}')

        sources = []
        try:
            call.ffitem = ffitem  # XXX, tylko roboczo
            with database.connect(self.sourceFile) as dbcon:
                dbcur = dbcon.cursor()
                self._init_sources_db(dbcur)

                """ Fix to stop items passed with a 0 IMDB id pulling old unrelated sources from the database. """
                if imdb == "0":
                    try:
                        dbcur.execute(
                            "DELETE FROM rel_src WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                            % (source, imdb, "", "")
                        )
                        dbcur.execute(
                            "DELETE FROM rel_url WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                            % (source, imdb, "", "")
                        )
                        dbcon.commit()
                    except Exception:
                        pass
                """ END """
                if source in const.sources_dialog.library_cache:
                    # fix pokazania już pobranych przy włączonym cache
                    try:
                        dbcur.execute(
                            "DELETE FROM rel_src WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                            % (source, imdb, "", "")
                        )
                        dbcur.execute(
                            "DELETE FROM rel_url WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                            % (source, imdb, "", "")
                        )
                        dbcon.commit()
                    except Exception:
                        pass
                try:
                    dbcur.execute(
                        "SELECT * FROM rel_src WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                        % (source, imdb, "", "")
                    )
                    match = dbcur.fetchone()
                    t1 = int(re.sub("[^0-9]", "", str(match[5])))
                    t2 = int(datetime.datetime.now().strftime("%Y%m%d%H%M"))
                    update = abs(t2 - t1) > 60
                    if not update:
                        with fflog_exc():
                            sources = [Source.from_json(it, ffitem=ffitem) for it in literal_eval(match[4])]
                        with fflog_exc():
                            if check_and_add_on_account_sources := getattr(call, 'check_and_add_on_account_sources', None):
                                check_and_add_on_account_sources(sources, ffitem, source)
                        with self.lock:
                            return self.sources.extend(sources)
                except Exception:
                    pass

                url = None
                try:
                    dbcur.execute(
                        "SELECT * FROM rel_url WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                        % (source, imdb, "", "")
                    )
                    url = dbcur.fetchone()
                    url = literal_eval(url[4])
                except Exception:
                    pass

                try:
                    if url is None and not from_cache:
                        # fflog(f'call({call}).movie({imdb=}, {title=}, {localtitle=}, {aliases=}, {year=})')
                        url = call.movie(imdb, title, localtitle, aliases, year)
                    if url is None and from_cache:
                        results_cache = cache.cache_get(
                            f"{source}_results", control.sourcescacheFile
                        )
                        if results_cache:  # może w ogóle nie być
                            results_cache = literal_eval(results_cache["value"])
                            if results_cache:  # bo może być pusty
                                url = [results_cache[k] for k in results_cache][0]
                                fflog(f"dla {source} odczytano z cache rekordów: {len(url)}")
                    if url is not None:
                        dbcur.execute(
                            "DELETE FROM rel_url WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                            % (source, imdb, "", "")
                        )
                        dbcur.execute(
                            "INSERT INTO rel_url Values (?, ?, ?, ?, ?)",
                            (source, imdb, "", "", repr(url)),
                        )
                        dbcon.commit()
                except Exception:
                    pass

                try:
                    with fflog_exc():
                        if from_cache:
                            # fflog(f'call({call}).sources({url=}, {self.host_list=}, {self.pr_host_list=}, {from_cache=})')
                            sources = call.sources(url, self.host_list, self.pr_host_list, from_cache=from_cache)
                        else:
                            # fflog(f'call({call}).sources({url=}, {self.host_list=}, {self.pr_host_list=})')
                            sources = call.sources(url, self.host_list, self.pr_host_list)
                    if sources is None:
                        raise Exception()
                    # remove duplicates
                    sources = [json.loads(t) for t in set(json.dumps(d, sort_keys=True) for d in sources)]
                    with fflog_exc():
                        sources = [Source.from_provider_dict(provider=source, ffitem=ffitem, item=it) for it in sources]
                    with self.lock:
                        self.sources.extend(sources)
                    dbcur.execute(
                        "DELETE FROM rel_src WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                        % (source, imdb, "", "")
                    )
                    dbcur.execute(
                        "INSERT INTO rel_src Values (?, ?, ?, ?, ?, ?)",
                        (
                            source,
                            imdb,
                            "",
                            "",
                            repr([src.as_json() for src in sources]),
                            datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                        ),
                    )
                    dbcon.commit()
                except Exception:
                    pass
        except OperationalError:
            pass

    def getEpisodeSource(
        self,
        title,
        localtitle,
        year,
        imdb,
        tmdb,
        season,
        episode,
        tvshowtitle,
        localtvshowtitle,
        aliases,
        premiered,
        source,
        call: ProviderProtocol,
        from_cache=False,
        *,
        ffitem: FFItem,
    ):
        fflog("getEpisodeSource")

        try:
            call.ffitem = ffitem  # XXX, tylko roboczo
            with database.connect(self.sourceFile) as dbcon:
                dbcur = dbcon.cursor()
                self._init_sources_db(dbcur)
                if source in const.sources_dialog.library_cache:
                    # fix pokazania już pobranych przy włączonym cache
                    try:
                        dbcur.execute(
                            "DELETE FROM rel_src WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                            % (source, imdb, season, episode)
                        )
                        dbcur.execute(
                            "DELETE FROM rel_url WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                            % (source, imdb, season, episode)
                        )
                        dbcon.commit()
                    except Exception:
                        pass
                try:
                    sources = []
                    dbcur.execute(
                        "SELECT * FROM rel_src WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                        % (source, imdb, season, episode)
                    )
                    match = dbcur.fetchone()
                    t1 = int(re.sub("[^0-9]", "", str(match[5])))
                    t2 = int(datetime.datetime.now().strftime("%Y%m%d%H%M"))
                    update = abs(t2 - t1) > 60
                    if not update:
                        with fflog_exc():
                            sources = [Source.from_json(it, ffitem=ffitem) for it in literal_eval(match[4])]
                        with fflog_exc():
                            if check_and_add_on_account_sources := getattr(call, 'check_and_add_on_account_sources', None):
                                check_and_add_on_account_sources(sources, ffitem, source)
                        with self.lock:
                            return self.sources.extend(sources)
                except Exception:
                    pass

                url = None
                try:
                    dbcur.execute(
                        "SELECT * FROM rel_url WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                        % (source, imdb, "", "")
                    )
                    url = dbcur.fetchone()
                    url = literal_eval(url[4])
                except Exception:
                    pass

                try:
                    if url is None and not from_cache:
                        tvshowtitle, localtvshowtitle = title, localtitle
                        # fflog(f'call({call}).tvshow({imdb=}, {tmdb=}, {tvshowtitle=}, {localtvshowtitle=}, {aliases=}, {year=})')
                        url = call.tvshow(imdb, tmdb, tvshowtitle, localtvshowtitle, aliases, year)
                    if url is None and from_cache:
                        results_cache = cache.cache_get(
                            f"{source}_results", control.sourcescacheFile
                        )
                        if results_cache:  # może w ogóle nie być
                            results_cache = literal_eval(results_cache["value"])
                            if results_cache:  # może być pusty
                                url = [results_cache[k] for k in results_cache][0]
                                fflog(f"dla {source} odczytano z cache rekordów: {len(url)}")
                    if url is None:
                        raise Exception()
                    dbcur.execute(
                        "DELETE FROM rel_url WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                        % (source, imdb, "", "")
                    )
                    dbcur.execute(
                        "INSERT INTO rel_url Values (?, ?, ?, ?, ?)",
                        (source, imdb, "", "", repr(url)),
                    )
                    dbcon.commit()
                except Exception:
                    pass

                ep_url = None
                try:
                    dbcur.execute(
                        "SELECT * FROM rel_url WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                        % (source, imdb, season, episode)
                    )
                    ep_url = dbcur.fetchone()
                    ep_url = literal_eval(ep_url[4])
                except Exception:
                    pass

                try:
                    if url is None:
                        raise Exception()
                    if ep_url is None and not from_cache:
                        # fflog(f'call({call}).episode({url=}, {imdb=}, {tmdb=}, {title=}, {premiered=}, {season=}, {episode=})')
                        ep_url = call.episode(url, imdb, tmdb, title, premiered, season, episode)
                    if url is None and from_cache:
                        results_cache = cache.cache_get(
                            f"{source}_results", control.sourcescacheFile
                        )
                        if results_cache:  # może w ogóle nie być
                            results_cache = literal_eval(results_cache["value"])
                            if results_cache:  # może być pusty
                                url = [results_cache[k] for k in results_cache][0]
                                fflog(f"dla {source} odczytano z cache rekordów: {len(url)}")
                    if ep_url is None:
                        raise Exception()
                    dbcur.execute(
                        "DELETE FROM rel_url WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                        % (source, imdb, season, episode)
                    )
                    dbcur.execute(
                        "INSERT INTO rel_url Values (?, ?, ?, ?, ?)",
                        (source, imdb, season, episode, repr(ep_url)),
                    )
                    dbcon.commit()
                except Exception:
                    pass

                try:
                    sources = []
                    if from_cache:
                        # fflog(f'call({call}).sources({ep_url=}, {self.host_list=}, {self.pr_host_list=}, {from_cache=})')
                        sources = call.sources(ep_url, self.host_list, self.pr_host_list, from_cache=from_cache)
                    else:
                        # fflog(f'call({call}).sources({ep_url=}, {self.host_list=}, {self.pr_host_list=})')
                        sources = call.sources(ep_url, self.host_list, self.pr_host_list)
                    if sources is None:
                        raise Exception()
                    # remove duplicates
                    sources = [json.loads(t) for t in set(json.dumps(d, sort_keys=True) for d in sources)]
                    sources = [Source.from_provider_dict(provider=source, ffitem=ffitem, item=it) for it in sources]
                    with self.lock:
                        self.sources.extend(sources)
                    dbcur.execute(
                        "DELETE FROM rel_src WHERE source = '%s' AND imdb_id = '%s' AND season = '%s' AND episode = '%s'"
                        % (source, imdb, season, episode)
                    )
                    dbcur.execute(
                        "INSERT INTO rel_src Values (?, ?, ?, ?, ?, ?)",
                        (
                            source,
                            imdb,
                            season,
                            episode,
                            repr([src.as_json() for src in sources]),
                            datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                        ),
                    )
                    dbcon.commit()
                except Exception:
                    pass
        except OperationalError:
            pass

    def alterSources(self, url):
        fflog("alterSources")

        try:
            if settings.getInt("hosts.mode") == 2:
                url += "&select=1"
            else:
                url += "&select=2"
            control.run_plugin(url)
        except Exception:
            pass

    def sourcesFilter(self, *, ffitem: FFItem):
        fflog("sourcesFilter")
        # cache na odczyt ustawień PROVIDER.sort.order
        so = SortOrderSettings(source_mods=self.source_mods)
        # cache na odczyt ustawień PROVIDER.library.color.identify2
        libcolors = LibraryColorSettings(source_mods=self.source_mods)
        # cache na odczyt ustawień PROVIDER.color.identify2
        colors = ColorSettings(source_mods=self.source_mods)
        # Set of src mods with premium color items.
        premium_src_mods: Set[str] = {srcmod.name for srcmod in self.source_mods
                                      if getattr(srcmod.provider, "use_premium_color", False)}

        debrid_only = settings.getBool("debrid.only")
        qmax = Quality(settings.getInt("hosts.quality.max"))
        qmin = Quality(settings.getInt("hosts.quality.min"))
        qrange = range(qmin, qmax + 1)
        HEVC = settings.getBool("HEVC")
        allowed_source_lang = settings.getInt("source.sound.lang")

        # random.shuffle(self.sources)

        # filtrowanie po zabronionym host (source)
        self.sources = [i for i in self.sources if i["hosting"].lower() not in const.sources_dialog.disabled_hosts]

        for i in self.sources:
            if "checkquality" in i and i["checkquality"]:
                if i["hosting"].lower() not in self.hq_host_list and i["quality"] not in [
                    "SD",
                    "SCR",
                    "CAM",
                ]:
                    i.update({"quality": "SD"})

        local = [i for i in self.sources if "local" in i and i["local"]]
        for i in local:
            i.update({"language": self._getPrimaryLang() or "en"})
        self.sources = [i for i in self.sources if i not in local]

        filter = []
        filter += [i for i in self.sources if i["direct"]]
        filter += [i for i in self.sources if not i["direct"]]
        self.sources = filter

        filter = []

        for d in debrid.debrid_resolvers:
            valid_hoster = set([i["hosting"] for i in self.sources])
            valid_hoster = [i for i in valid_hoster if d.valid_url("", i)]
            filter += [
                dict(list(i.items()) + [("debrid", d.name)])
                for i in self.sources
                if i["hosting"] in valid_hoster
            ]
        if not debrid_only or not debrid.status():
            filter += [
                i
                for i in self.sources
                if i["hosting"].lower() not in self.pr_host_list and not i["debridonly"]
            ]

        self.sources = filter

        for i in range(len(self.sources)):
            q = self.sources[i]["quality"]
            if q == "HD":
                self.sources[i].update({"quality": "720p"})

        filter = []
        filter += local

        for i in reversed(qrange):
            qq = self.QUALITIES[Quality(i)]
            filter.extend(s for s in self.sources if s["quality"] in qq)

        CAM_disallowed = settings.getBool("CAM.disallowed")
        if CAM_disallowed:
            filter += [i for i in self.sources if i["quality"] in ["SCR"]]
        else:
            filter += [i for i in self.sources if i["quality"] in ["SCR", "CAM"]]

        # Filtrowanie po dostępności transferu
        if settings.getBool("source.premium.no_transfer"):
            filter = [
                i for i in filter
                if not i.get("no_transfer", False) or i.get("on_account", False)
            ]

        self.sources = filter

        # filter_out = {
        #     id(i)
        #     for i in self.sources
        #     if i["source"].lower() in self.hostblockDict and "debrid" not in i
        # }
        # self.sources = [i for i in self.sources if id(i) not in filter_out]

        # filtrowanie po wielkości pliku
        size_min = settings.getInt('source.size.min') * GB
        size_max = (settings.getInt('source.size.max') or 10**6) * GB
        size_range = range(size_min, size_max + 1)
        self.sources = [
            s for s in self.sources
            if s.get("source") in ("download", "library")
            or not (size := source_utils.convert_size_to_bytes(s.get("size", "")))
            or size in size_range
        ]

        multi = [i["language"] for i in self.sources]
        multi = [x for y, x in enumerate(multi) if x not in multi[:y]]
        multi = True if len(multi) > 1 else False

        if multi:
            self.sources = [i for i in self.sources if not i["language"] == "en"] + [
                i for i in self.sources if i["language"] == "en"
            ]

        # ograniczenie maksymalnej ilości źródeł
        self.sources = self.sources[:2000]

        # muszą być wszystkie pozycje, które zwraca source_utils.check_sd_url()
        # i które zostały "zassane" przez zmienną filter
        my_quality_order = ["4K", "1440p", "1080p", "1080i", "720p", "SD", "SCR", "CAM"]
        quality_order = {key: i for i, key in enumerate(my_quality_order)}

        # muszą być wszystkie możliwości wypisane jakie chcemy obsługiwać
        language_order = {key: i for i, key in enumerate(const.sources.language_order)}

        priority = self.language_type_priority

        def normalize_language_type(text: str) -> Tuple[Tuple[int, ...], bool]:
            parts = text.lower().replace("|", " ").replace(",", " ").split()
            is_kino = "kino" in parts
            prioritized = tuple(
                priority[p]
                for p in parts
                if p in priority
            )
            return (prioritized, is_kino)

        # ustalenie kolejności dla nazw serwisów
        # z ustawień sort.order
        my_provider_order: List[Union[str, int]] = [
            1,
            2,
            3,
            4,
            5,
        ]

        premium_providers = sorted(
            {i["provider"] for i in self.sources if i.get("premium", False)}  # Domyślnie False, jeśli "premium" brak
        )
        my_provider_order.extend(premium_providers)
        provider_order = {key: i for i, key in enumerate(my_provider_order)}

        # --- wpólne funkcje pomocne przy sortowaniu ---
        def order_provider(src: Source) -> int:
            provider: str = src['provider']
            return provider_order.get(so[provider] or provider, len(my_provider_order))

        def order_size(src: Source) -> int:
            size = src.get("size")
            if not size:
                size = (src.get("info") or "").rpartition("|")[2]
            return source_utils.convert_size_to_bytes(size) * -1

        def order(src: Source, *, by_provider: bool = True) -> int:
            if (order := src.attr.order) is None:
                order = 0
                for i, name in enumerate(reversed(('download', 'library', 'plex', 'jellyfin', 'external')), 1):
                    if src.provider.startswith(name):  # TODO, why not provider == name?
                        order += 2000 + i
                if src.get('on_account', 0):
                    order += 1000
                if by_provider:
                    order += 999 - min(999, order_provider(src))
            # d['_order'] = order  # DEBUG order
            return -order
        # wybór wariantu
        sort_source = settings.getInt("hosts.sort")
        if sort_source == 0:
            fflog("Sortuję wg dostawców")  # by providers
            self.sources = sorted(
                self.sources,
                key=lambda d: (
                    order(d),
                    language_order[d["language"]],
                    quality_order[d["quality"]],
                    d["provider"],  # provider (serwis internetowy www)
                    normalize_language_type(d.get("info", "")),
                    order_size(d),
                ),
            )
        if sort_source == 1:
            fflog("Sortuję wg źródeł (hostingów)")  # by hosting (hosting, server)
            self.sources = sorted(
                self.sources,
                key=lambda d: (
                    order(d),
                    language_order[d["language"]],
                    quality_order[d["quality"]],
                    d["hosting"],  # hosting (serwer, hosting)
                    normalize_language_type(d.get("info", "")),
                    order_size(d),
                ),
            )
        if sort_source == 2:
            fflog("Sortuję wg rozmiaru")  # by size
            self.sources = sorted(
                self.sources,
                key=lambda d: (
                    order(d),
                    order_size(d),
                    normalize_language_type(d.get("info", "")),
                ),
            )
        if sort_source == 3:
            custom_criterion = ' -> '.join(SortElem(settings.getInt(f"hosts.sort.elem{n+1}")).name
                                           for n in range(4))
            fflog(f'Sortuję wg ustawień użytkownika: {custom_criterion}')  # custom

            # funkcja pomocnicza
            def choose_criterium(d, n):
                crit = SortElem(settings.getInt(f"hosts.sort.elem{n+1}"))
                # fflog(f"choose_criterium {n}: {crit.name}")
                if crit == SortElem.SERVICE:
                    return order_provider(d)
                if crit == SortElem.LANGUAGE:
                    return language_order[d["language"]]
                if crit == SortElem.QUALITY:
                    return quality_order[d["quality"]]
                if crit == SortElem.SIZE:
                    return order_size(d)
                return ""

            # sortowanie
            self.sources = sorted(
                self.sources,
                key=lambda d: (
                    # zawsze na początku (pobrane,local ...) oraz na koncie online
                    order(d, by_provider=False),
                    # kryteria użytkownika
                    choose_criterium(d, 0),  # 1-wsze kryterium
                    choose_criterium(d, 1),  # 2-gie kryterium
                    choose_criterium(d, 2),  # 3-cie kryterium
                    choose_criterium(d, 3),  # 4-te kryterium
                    normalize_language_type(d.get("info", "")),
                ),
            )

        exts = self.exts
        extra_info = settings.getBool("sources.extrainfo")

        # Kompilacja wyrażeń regularnych dla pola 'audio'
        audio_re1 = re.compile(r"(?<!\d)([57]\.[124](?:\.[24])?)\.(ATMOS)\b", re.I)
        audio_re2 = re.compile(r"(?<=[DSPXAC3M])[.-]?([57261]\.[102])\b", re.I)
        audio_re3 = re.compile(r"\b(DTS)[.-]?(HD|ES|EX|X(?!26))[. ]?(MA)?", re.I)
        audio_re4 = re.compile(r"(TRUEHD|DDP)\.(ATMOS)\b", re.I)
        audio_re5 = re.compile(r"(custom|dual)\.(audio)", re.I)
        audio_re6 = re.compile(r"ddp(?!l)", re.I)

        # Kompilacja wyrażeń regularnych dla pola 'codec'
        codec_re1 = re.compile(r"(\d{2,3})(fps)", re.I)
        codec_re2 = re.compile(r"plus", re.I)
        codec_re3 = re.compile(r"\bDoVi\b", re.I)
        codec_re4 = re.compile(r"\s*/\s*DolbyVision", re.I)
        codec_re5 = re.compile(r"DolbyVision", re.I)

        # Kompilacja wyrażeń regularnych dla pola 'quality'
        quality_re1 = re.compile(r"\b(\w+)\.(\w+)\b", re.I)

        for i in range(len(self.sources)):
            url2: str = ''
            if extra_info:
                try:
                    if "filename" in self.sources[i] and self.sources[i]["filename"]:
                        url2 = self.sources[i]["filename"]
                    else:
                        url2 = (
                            self.sources[i]["url"]
                            .replace(" / ", " ")
                            .replace("_/_", "_")
                            .rstrip("/")
                            .split("/")[-1]
                        )
                        url2 = url2.rstrip("\\").split("\\")[
                            -1
                        ]  # dla plików z własnej biblioteki na dysku lokalnym
                        # fflog(f' {[i]} {url2=!r}')
                        url2 = re.sub(
                            r"(\.(html?|php))+$", "", url2, flags=re.I
                        )  # na przypadki typu "filmik.mkv.htm"
                        if url2.lower()[-3:] not in exts:
                            # próba pozyskanie nazwy z 2-giej linijki lub opisu
                            if (
                                "info2" in self.sources[i]
                                and self.sources[i]["info2"]
                                and self.sources[i]["info2"].lower()[-3:] in exts
                            ):
                                url2 = self.sources[i]["info2"]
                            else:
                                """
                                # to raczej nie będzie już wykorzystywane, bo okazało się, że info może mieć juz swoje oznaczenia, więc mogą się dublować
                                url2 = self.sources[i]["info"] if self.sources[i]["info"] else ''
                                # próba odfiltrowania nazwy
                                url2 = url2.split("|")[-1].strip().lstrip("(").rstrip(")")
                                """
                                url2 = ""

                    url2 = unquote(
                        url2
                    )  # zamiana takich tworów jak %nn (np. %21 to nawias)
                    url2 = unescape(url2)  # pozbycie się encji html-owych

                    t = PTN.parse(url2)  # proces rozpoznawania
                    t3d = (
                        t["3d"] if "3d" in t else ""
                    )  # zapamiętanie informacji pod inną zmienną czy wersja 3D
                    textended = (
                        t["extended"] if "extended" in t else ""
                    )  # informacja o wersji rozszerzonej
                    tremastered = (
                        t["remastered"] if "remastered" in t else ""
                    )  # informacja o wersji zremasterowanej

                    # poniżej korekty wizualne
                    if "audio" in t:
                        t["audio"] = audio_re1.sub(r"\1 \2", t["audio"])
                        t["audio"] = audio_re2.sub(r" \1", t["audio"])
                        t["audio"] = audio_re3.sub(r"\1-\2 \3", t["audio"]).rstrip()
                        t["audio"] = audio_re4.sub(r"\1 \2", t["audio"])
                        t["audio"] = audio_re5.sub(r"\1 \2", t["audio"])
                        t["audio"] = audio_re6.sub("DD+", t["audio"])
                    if "codec" in t:
                        t["codec"] = codec_re1.sub(r"\1 \2", t["codec"])
                        t["codec"] = codec_re2.sub("+", t["codec"])
                        t["codec"] = codec_re3.sub("DV", t["codec"])
                        if "DV".lower() in t["codec"].lower():
                            t["codec"] = codec_re4.sub("", t["codec"])
                        else:
                            t["codec"] = codec_re5.sub("DV", t["codec"])
                    if "quality" in t:
                        t["quality"] = quality_re1.sub(r"\1-\2", t["quality"])

                    t = [
                        t[j]
                        for j in t
                        if "quality" in j or "codec" in j or "audio" in j
                    ]
                    t = " | ".join(t)

                    if not t:
                        t = source_utils.getFileType(
                            url2
                        )  # taki fallback dla PTN.parse()
                        t = t.strip()

                    """
                    # pozbycie się tych samych oznaczeń ze zmiennej info
                    if t:
                        self.sources[i]["info"] = re.sub(fr'(\b|[ ._|/]+)({"|".join(t.split(" / "))})\b', '', self.sources[i]["info"], flags=re.I)
                    """

                    # dodanie dodatkowych informacji (moim zdaniem ważnych)
                    if t3d:
                        if "3d" in url2.lower() and "3d" not in t.lower():
                            t = f"[3D] | {t}"
                        else:
                            t = t.replace("3D", "[3D]")
                    # dodatkowe oznaczenie pliku z wieloma sciezkami audio
                    if (
                        re.search(
                            r"\bMULTI\b", url2, re.I
                        )  # szukam w adresie, który powinien zawierać nazwę pliku
                        and "mul" not in self.sources[i]["language"].lower()
                        # and "PL" not in self.sources[i]["language"].upper()  # założenie, że jak wykryto język PL, to nie ma potrzeby o dodatkowym ozaczeniu
                        and "multi"
                        not in self.sources[i][
                            "info"
                        ].lower()  # sprawdzenie, czy przypadkiem już nie zostało przekazane przez plik źródła
                        and "multi"
                        not in t.lower()  # sprawdzenie, czy nie ma tej frazy już w opisie
                    ):
                        t += " | MULTI"
                    if (
                        "multi" in t.lower()
                        or "multi" in self.sources[i]["info"].lower()
                    ) and self.sources[i]["language"] != "pl":
                        self.sources[i]["language"] = "multi"  # wymiana języka
                        t = re.sub(
                            r"[/| ]*multi\b", "", t, flags=re.I
                        )  # wywalenie z opisu, aby nie było dubli
                        self.sources[i]["info"] = re.sub(
                            r"[/| ]*multi\b", "", self.sources[i]["info"], flags=re.I
                        )  # wywalenie z opisu, aby nie było dubli

                    if textended:
                        if textended is True:
                            t += " | EXTENDED"
                        else:
                            textended = re.sub(
                                "(directors|alternat(?:iv)?e).(cut)",
                                r"\1 \2",
                                textended,
                                flags=re.I,
                            )
                            t += f" | {textended}"

                    # długi napis i czy aż tak istotny?
                    if tremastered:
                        if tremastered is True:
                            t += " | REMASTERED"
                        else:
                            if "rekonstrukcja" not in t.lower():
                                tremastered = re.sub(
                                    "(Rekonstrukcja).(cyfrowa)",
                                    r"\1 \2",
                                    tremastered,
                                    flags=re.I,
                                )
                                t += f" | {tremastered}"

                    if (
                        "imax" in url2.lower() and "imax" not in t.lower()
                    ):  # sprawdzenie czy dodać info IMAX
                        t += " | [IMAX]"

                    if (
                        "avi" in url2.lower()[-3:] and "avi" not in t.lower()
                    ):  # aby nie bylo zdublowań
                        t += " | AVI"  # oznaczenie tego typu pliku, bo nie zawsze dobrze odtwarza sie "w locie"

                    t = t.lstrip(
                        " | "
                    )  # przydaje się, jak ani PTN.parse() ani getFileType() nic nie znalazły
                    t += " "

                    self.sources[i]['info2'] = t
                except Exception:
                    t = None
            else:
                t = None

            # u = self.sources[i]["url"]  -- NOT USED

            src = self.sources[i]
            p = src.provider  # serwis, strona www
            lng = src["language"]
            s = src.hosting  # serwer / hosting / dawne "source"
            q = src["quality"]  # rozdzielczość

            s = s.rsplit(".", 1)[
                0
            ]  # wyrzucenie ostatniego człona domeny (np. ".pl", ".com")

            try:  # f to info (tu może być też rozmiar pliku na końcu)
                f = " | ".join(
                    [
                        "[I]%s [/I]" % info.strip()
                        for info in src["info"].split("|")
                    ]
                )
            except Exception:
                f = ""

            d = src.meta.setdefault('debrid', '')
            if d.lower() == "real-debrid":
                d = "RD"

            if not d == "":
                label = "%02d | [B]%s | %s[/B] | " % (int(i + 1), d, p)
            else:
                label = "%02d | [LIGHT][B]%s[/B][/LIGHT] | " % (int(i + 1), p)

            # oznaczenie, czy źródło jest w tzw. bibliotece danego serwisu
            if src.get('on_account'):
                if expires := src.get('on_account_expires'):
                    label += f'[I]konto ({expires})[/I]  | '
                else:
                    label += "[I]konto[/I]  | "

            # oznaczenie języka
            if lng:
                if (
                    multi
                    and lng != "en"  # nie rozumiem, kiedy ten warunek zachodzi
                    or not multi
                    and lng != "en"  # dałem ten warunek
                ):
                    label += "[B]%s[/B] | " % lng

            if t:  # extra_info
                if q in ["4K", "1440p", "1080p", "1080i", "720p"]:
                    label += "%s | [B][I]%s [/I][/B] | [I]%s[/I] | %s" % (s, q, t, f)
                elif q == "SD":
                    # label += "%s | %s | [I]%s[/I]" % (s, f, t)
                    # moja propozycja (wielkość pliku na końcu - dla spójności)
                    label += "%s | [I]%s[/I] | %s" % (s, t, f)
                else:
                    # label += "%s | %s | [I]%s [/I] | [I]%s[/I]" % (s, f, q, t)
                    # moja propozycja (wielkość pliku na końcu - dla spójności)
                    # label += "[LIGHT]%s | [B][I]%s [/I][/B] | [I]%s[/I] | %s[/LIGHT]" % (s, q, t, f)
                    label += "[LIGHT]%s | [I]%s[/I] | %s[/LIGHT]" % (s, t, f)
            else:
                if q in ["4K", "1440p", "1080p", "1080i", "720p"]:
                    label += "%s | [B][I]%s [/I][/B] | %s" % (s, q, f)
                elif q == "SD":
                    label += "%s | %s" % (s, f)
                else:
                    # label += "%s | %s | [I]%s [/I]" % (s, f, q)
                    # moja propozycja (wielkość pliku na końcu - dla spójności)
                    # label += "[LIGHT]%s | [B][I]%s [/I][/B] | %s[/LIGHT]" % (s, q, f)
                    label += "[LIGHT]%s | %s[/LIGHT]" % (s, f)

            # korekty wizualne
            label = label.replace("| 0 |", "|").replace(" | [I]0 [/I]", "")
            label = re.sub(r"\[I\]\s+\[/I\]", " ", label)
            label = re.sub(r"\|\s+\|", "|", label)
            label = re.sub(
                r"\|\s+\|", "|", label
            )  # w pewnych okolicznościach ponowne wykonanie takiej samej linijki kodu jak wyżej pomaga
            label = re.sub(r"\|(?:\s+|)$", "", label)
            label = re.sub(
                r"(\d+(?:[.,]\d+)?\s*[GMK]B)", r"[B]\1[/B]", label, flags=re.I
            )  # wyróżnienie rozmiaru pliku
            label = re.sub(
                r"(?<=\d)\s+(?=[GMK]B\b)", "\u00A0", label, flags=re.I
            )  # aby nie rodzielal cyfr od jednostek
            # aby np. 1080i było bardziej widoczne
            # label = re.sub(r"\s?((\[\w\])*(?:1080|720|1440)[pi])\s?", r"[LOWERCASE]\1[/LOWERCASE]", label,flags=re.I)
            label = re.sub(
                "((?:1080|720|1440)[pi])",
                r"[LOWERCASE]\1[/LOWERCASE]",
                label,
                flags=re.I,
            )

            # To źródło jest w biliotece, używamy specjalnego koloru dla biblioteki tego providera
            color: str = libcolors[p]
            if not color or not src.get("on_account"):
                # -- No nie jest, lecimy dalej...
                # Bierzemy kolor dla tego providera
                color = colors[p]
                # Jeśli nie ma koloru (lub jest domyślny), a jest do ptovider z premium, to wybieramy kolor premium
                if (not color or color == DEFAULT_COLOR_LINK) and p.lower() in premium_src_mods:
                    color = settings.getString("prem.color.identify2")
            # Jeśli jest kolor, ale jest to kolor domyślny, to jawnie bierzemy jego wartość.
            if color == DEFAULT_COLOR_LINK:
                color = settings.getString("default.color.identify2")
            # Ręczne nadpisywanie kolorów
            src.attr_update()
            color = src.attr.color or color
            # Jeśli mamy kolor, to kolorujemy
            if color:
                src["color_identify"] = color
                src["label"] = f"[COLOR {color}]{label.upper()}[/COLOR]"
            else:
                # custom-lista musi mieć jakiś kolor, bierzemy domyślny (niejawnie)
                src["color_identify"] = settings.getString("default.color.identify2")
                src["label"] = label.upper()

            if (
                settings.getBool("sources.filename_in_2nd_line")
                and "info2" not in src
            ):
                if url2 and url2.lower()[-3:] in exts:  # zmienna 'exts' jest definiowana po 'url2'
                    src["info2"] = url2
                if filename := src.get("filename"):
                    src["info2"] = filename

            if text := src.get("info2"):
                src["info2"] = unescape(unquote(text))  # mam nadzieję, kolejność odkodowywania nie ma znaczenia
                src["label"] += f"[LIGHT][CR]  {text}[/LIGHT]"

        # czy mogą być pozycje bez "label" ?
        self.sources = [i for i in self.sources if "label" in i]

        """to już w dzisiejszych czasach chyba nie ma znaczenia
        if not HEVC:
            self.sources = [
                i
                for i in self.sources
                if "HEVC" not in i["label"] or "265" not in i["label"]
            ]
        """

        if not settings.getBool("HDR.allowed"):
            self.sources = [
                i
                for i in self.sources
                if "HDR" not in i["label"]
            ]

        if not settings.getBool("DV.allowed"):
            self.sources = [
                i
                for i in self.sources
                if "DV" not in i["label"]
            ]

        if not settings.getBool("AV1.allowed"):
            self.sources = [
                i
                for i in self.sources
                if "AV1" not in i["label"]
            ]

        if not settings.getBool("HEVC.allowed"):
            self.sources = [
                i
                for i in self.sources
                if "HEVC" not in i["label"] or "265" not in i["label"]
            ]

        if not settings.getBool("F3D.allowed"):
            self.sources = [
                i
                for i in self.sources
                if "[3D]" not in i["label"]
            ]

        if CAM_disallowed:
            CAM_format = ["camrip", "tsrip", "hdcam", "hqcam", "dvdcam", "dvdts", "cam", "telesync", " ts"]
            if settings.getBool("HDTS.disallowed"):
                CAM_format += ["hdts", "hd-ts"]
            self.sources = [
                i
                for i in self.sources
                # if "CAM" not in i["label"]
                if not any(x in i["label"].lower() for x in CAM_format)
            ]

        if settings.getBool("SUBTITLES.disallowed"):
            self.sources = [i for i in self.sources
                            if any(x in i["label"].lower() for x in [
                                " lektor ",
                                "]lektor",
                                "dubbing & napisy",
                                "dubbing",
                            ]) or not any(x in i["label"].lower() for x in [
                                "napisy",
                                "subbed",
                                "subtitles",
                                " sub ",
                                "]sub",
                            ])]

        if settings.getBool("LEKTORAI.disallowed"):
            self.sources = [
                i
                for i in self.sources
                if "lektor ai" not in i["label"].lower()
            ]

        if settings.getBool("MD.sound.disallowed"):
            self.sources = [
                i
                for i in self.sources
                if not re.search(r"\b(md|dubbing[ _.-]kino)\b", i["label"], re.I)
            ]

        if allowed_source_lang:
            langs: Dict[int, Set[str]] = {
                1: {'pl'},
                2: {'pl', 'multi'},
                3: {'en', ''},  # puste to podobno EN
                4: {'en', 'multi', ''},  # puste to podobno EN
            }
            allowed = langs[allowed_source_lang]
            self.sources = [i for i in self.sources
                            if set(i.get("language", "").lower().split()) & allowed]

        # return all sources
        return self.sources

    def resolve_source(self, item: Source, /, info: bool = False, for_resolve: Optional[SourceResolveKwargs] = None, **kwargs) -> Optional[str]:
        fflog("sourcesResolve")
        if for_resolve is None:
            for_resolve = {}
        try:
            if item is None:
                raise ValueError('No source item')
            if item.get('fake'):
                if resolve_to := item.get('resolve_to'):
                    return str(resolve_to)
                raise ValueError('Fake source item')

            u = url = item["url"]

            d = item["debrid"]
            direct = item["direct"]
            local = item.get("local", False)

            provider = item["provider"]
            src_mod: SourceModule = next(iter(sm for sm in self.source_mods if sm.name == provider))
            u = url = src_mod.provider.resolve(url, **for_resolve)

            if url is None:
                raise ValueError(L(30337, 'Selected link is not working'))

            if "://" not in str(url) and not local:
                # if provider in ('netflix', 'external'):
                #    return url
                raise ValueError(f'Invlaid URL {url!r} in provider {provider!r}')

            if not local:
                url = url[8:] if url.startswith("stack:") else url

                urls = []
                for part in url.split(" , "):
                    u = part
                    if not d == "":
                        part = debrid.resolver(part, d)

                    elif not direct:
                        hmf = resolveurl.HostedMediaFile(url=u, include_disabled=True, include_universal=False)
                        if hmf.valid_url():
                            part = hmf.resolve()
                    urls.append(part)

                url = "stack://" + " , ".join(urls) if len(urls) > 1 else urls[0]

            if not url:
                raise ValueError(f'Empty URL in provider {provider!r}')

            ext = (
                url.split("?")[0]
                .split("&")[0]
                .split("|")[0]
                .rsplit(".")[-1]
                .replace("/", "")
                .lower()
            )
            if ext == "rar":
                raise ValueError(f'RAR in URL in provider {provider!r}')

            drm_url, _, headers = url.partition('|')
            if " " in headers:
                headers = quote_plus(headers).replace("%3D", "=")
            headers = dict(parse_qsl(headers))

            if url.startswith("http") and ".m3u8" in url:
                result = client.request(drm_url, headers=headers, output="geturl", timeout=20)
                if result is None:
                    raise ValueError(f'Resolve m3u8 failed in provider {provider!r}')
            # elif url.startswith("http"):
            #     return url

            fflog(f'[SOURCES] resolve to {url!r} in provider {provider!r}')
            return url
        except Exception as e:
            fflog_exc()
            error_info = L(32401, 'No stream available')
            if str(e):
                import xbmcgui
                xbmcgui.Dialog().notification('FanFilm', f'{error_info}: {e}')
            if info:
                # player.cancel()
                control.infoDialog(f'{error_info}: {e}', sound=False, icon='INFO')
            return

    # def sourcesDirect(self, items):
    #     fflog("sourcesDirect")

    #     filter = [
    #         i
    #         for i in items
    #         if i["source"].lower() in self.hostblockDict and i["debrid"] == ""
    #     ]
    #     items = [i for i in items if i not in filter]

    #     items = [
    #         i
    #         for i in items
    #         if ("autoplay" in i and i["autoplay"]) or "autoplay" not in i
    #     ]

    #     if settings.getBool("autoplay.sd"):
    #         items = [
    #             i
    #             for i in items
    #             if i["quality"] not in ["4K", "1440p", "1080p", "1080i", "HD"]
    #         ]

    #     u = None

    #     header = control.addonInfo("name")
    #     header2 = header.upper()

    #     try:
    #         control.sleep(1000)

    #         progress_dialog_mode = ProgressDialogMode(settings.getInt("progress.dialog"))
    #         if progress_dialog_mode is ProgressDialogMode.BACKGROUND:
    #             progressDialog = control.progressDialogBG()
    #         else:
    #             progressDialog = control.progressDialog()
    #         progressDialog.create(header, "")
    #         progressDialog.update(0)
    #     except Exception:
    #         pass

    #     for i in range(len(items)):
    #         try:
    #             if progressDialog.iscanceled():
    #                 break
    #             progressDialog.update(
    #                 int((100 / float(len(items))) * i),
    #                 str(items[i]["label"]) + "\n" + str(" "),
    #             )
    #         except Exception:
    #             progressDialog.update(
    #                 int((100 / float(len(items))) * i),
    #                 str(header2) + "\n" + str(items[i]["label"]),
    #             )

    #         try:
    #             if xbmc.Monitor().abortRequested():
    #                 return sys.exit()

    #             url = self.sourcesResolve(items[i])
    #             if u is None:
    #                 u = url
    #             else:
    #                 break
    #         except Exception:
    #             pass

    #     try:
    #         progressDialog.close()
    #     except Exception:
    #         pass

    #     return u

    def getLanguage(self):
        fflog("getLanguage")

        langDict = {
            "English": ["en"],
            "German": ["de"],
            "German+English": ["de", "en"],
            "French": ["fr"],
            "French+English": ["fr", "en"],
            "Portuguese": ["pt"],
            "Portuguese+English": ["pt", "en"],
            "Polish": ["pl"],
            "Polish+English": ["pl", "en"],
            "Korean": ["ko"],
            "Korean+English": ["ko", "en"],
            "Russian": ["ru"],
            "Russian+English": ["ru", "en"],
            "Spanish": ["es"],
            "Spanish+English": ["es", "en"],
            "Greek": ["gr"],
            "Italian": ["it"],
            "Italian+English": ["it", "en"],
            "Greek+English": ["gr", "en"],
        }
        name = settings.getString("providers.lang")
        return langDict.get(name, ["pl"])

    def getLocalTitle(self, title, imdb, tmdb, content):
        fflog("getLocalTitle")

        lang = self._getPrimaryLang()
        if not lang:
            return title

        # TODO: TRAKT
        t = ''
        # if content == "movie":
        #     t = trakt.getMovieTranslation(imdb, lang)
        # else:
        #     t = trakt.getTVShowTranslation(imdb, lang)

        return t or title

    def getAliasTitles(self, imdb, localtitle, content, *, ffitem: FFItem) -> List[Dict[Literal['title', 'country'], str]]:
        return [{'title': a.title, 'country': a.country} for a in ffitem.aliases_info]
        # fflog("getAliasTitles")
        # lang = self._getPrimaryLang()

        # try:
        #     t = (ffinfo.trakt.aliases('movie', imdb) if content == "movie" else ffinfo.trakt.aliases('show', imdb))
        #     return [i for i in t if (i.get("country", "").lower() in [lang, "", "us"]
        #                              and i.get("title", "").lower() != localtitle.lower())]
        # except:
        #     return []

    def getTMDBAliasTitles(self, tmdb, localtitle, content):
        fflog("getTMDBAliasTitles")

        try:
            api_key = settings.getString("tmdb.api_key") or apis.tmdb_API
            base_url = "https://api.themoviedb.org/3/"

            if content == "movie":
                url = f"{base_url}movie/{tmdb}/alternative_titles?api_key={api_key}"
            else:
                url = f"{base_url}tv/{tmdb}/alternative_titles?api_key={api_key}"

            response = client.request(url, output="json")

            if content == "movie":
                titles = response.get("titles", [])
            else:
                titles = response.get("results", [])

            aliases = []
            added_titles = set()

            for title in titles:
                key = title["title"]
                if key not in added_titles:
                    aliases.append(
                        {
                            "title": title["title"],
                            "country": title["iso_3166_1"].lower(),
                        }
                    )
                    added_titles.add(key)

            # Usuwanie duplikatów
            reduce_dupes = {i["title"]: i for i in aliases}
            aliases = [i for i in reduce_dupes.values()]

            return aliases
        except Exception as e:
            print(f"Wystąpił błąd: {e}")
            return []

    def _getPrimaryLang(self):
        fflog("_getPrimaryLang")

        langDict = {
            "English": "en",
            "German": "de",
            "German+English": "de",
            "French": "fr",
            "French+English": "fr",
            "Portuguese": "pt",
            "Portuguese+English": "pt",
            "Polish": "pl",
            "Polish+English": "pl",
            "Korean": "ko",
            "Korean+English": "ko",
            "Russian": "ru",
            "Russian+English": "ru",
            "Spanish": "es",
            "Spanish+English": "es",
            "Italian": "it",
            "Italian+English": "it",
            "Greek": "gr",
            "Greek+English": "gr",
        }
        name = settings.getString("providers.lang")
        lang = langDict.get(name)
        return lang

    def getTitle(self, title):
        fflog("getTitle")

        title = cleantitle.normalize(title)
        return title

    def getConstants(self, *, ffitem: FFItem) -> None:
        fflog("getConstants")

        self.itemProperty = f"{control.plugin_id}.container.items"
        self.metaProperty = f"{control.plugin_id}.container.meta"
        self.source_mods = scan_source_modules(ffitem=ffitem)
        fflog(f"getConstants scan_sources ({len(self.source_mods)})")

        self.host_list = []
        if resolveurl is not None:
            try:
                # wszyskie demeny (hosty) z wszystkich klas resolvera (z pominięciem generycznego '*'), bez duplikatów
                host_list: List[ResolverClass] = resolveurl.relevant_resolvers(order_matters=True)
                self.host_list = list(dict.fromkeys(domain.lower()
                                                    for cls in host_list
                                                    for domain in cls.domains if domain != '*'))
            except Exception:
                fflog_exc()

        self.pr_host_list = [
            "1fichier.com",
            "rapidgator.net",
            "rg.to",
            "filefactory.com",
            "nitroflare.com",
            "turbobit.net",
        ]
        self.hq_host_list = [
            "gvideo",
            "google.com",
        ]
