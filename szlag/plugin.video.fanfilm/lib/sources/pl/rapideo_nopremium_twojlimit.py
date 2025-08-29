"""
    FanFilm Add-on
    Copyright (C) 2024 :)

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

from typing import Sequence, ClassVar, List, TYPE_CHECKING
import re
import math
from html import unescape
import unicodedata
from datetime import datetime
import xbmcgui
import PTN
from urllib.parse import unquote
from lib.ff import requests
from lib.sources import SourceModule, Source
from lib.ff import cache, cleantitle, control, source_utils
from lib.ff.settings import settings
from lib.ff.log_utils import fflog, fflog_exc
from const import const
if TYPE_CHECKING:
    from lib.ff.item import FFItem


class _source:
    """Base scraper for sites like rapideo, nopremium, twojlimit"""

    PROVIDER: ClassVar[str]
    URL: ClassVar[str]
    # --- scraper api ---
    priority: ClassVar[int] = 1
    language: ClassVar[Sequence[str]] = ['pl']

    # This class has support for *.sort.order setting
    has_sort_order: bool = True
    # This class has support for *.color.identify2 setting
    has_color_identify2: bool = True
    # This class has support for *.library.color.identify2 setting
    has_library_color_identify2: bool = True
    # Mark sources with prem.color.identify2 setting
    use_premium_color: bool = True

    def __init__(self):
        self.authtoken = None
        self.anime = None
        self.domains = [f"{self.PROVIDER}.pl"]
        self.login_url = f"{self.URL}/api/rest/login"
        self.search_url = f"{self.URL}/api/rest/search"
        self.check_url = f"{self.URL}/api/rest/files/check"
        self.files_url = f"{self.URL}/api/rest/files/get"
        self.download_url = f"{self.URL}/api/rest/files/download"
        self.req = requests
        self.user_name = settings.getString(f"{self.PROVIDER}.username")
        self.user_pass = settings.getString(f"{self.PROVIDER}.password")
        self.titles = []
        self.tit_val_filt_for_one_title = None
        self.transfer_left_bytes = 0

    def login(self):
        """ logowanie w serwisie """
        self.authtoken = ""
        get_auth = cache.cache_get(f"{self.PROVIDER}_authtoken", control.providercacheFile)
        if get_auth is not None:
            self.authtoken = get_auth["value"]
        if self.authtoken == "":
            if self.user_name and self.user_pass:
                req = self.req.post(
                    self.login_url,
                    data={"login": self.user_name, "password": self.user_pass},
                )
                response = req.json()
                if "authtoken" in response:
                    self.authtoken = response["authtoken"]
                    cache.cache_insert(f"{self.PROVIDER}_authtoken", self.authtoken, control.providercacheFile)
                    return True
                if "error" in response and response["message"] != "":
                    xbmcgui.Dialog().notification(f"{self.PROVIDER} - Błąd", str(response["message"]), xbmcgui.NOTIFICATION_ERROR)
            else:
                xbmcgui.Dialog().notification(f"{self.PROVIDER} - Błąd", "Brak danych logowania - sprawdź ustawienia", xbmcgui.NOTIFICATION_ERROR)
        return False

    def get_account_info(self):
        if not self.authtoken:
            return
        try:
            account_url = f"{self.URL}/api/rest/account"
            data = {"authtoken": self.authtoken}
            res = self.req.post(account_url, data=data)
            account_info = res.json()
            if "account" in account_info:
                account = account_info["account"]
                try:
                    transfer_left_gb = float(account.get('transfer_left_gb', 0))
                except ValueError:
                    transfer_left_gb = 0
                try:
                    premium_left_gb = float(account.get('premium_left_gb', 0))
                except ValueError:
                    premium_left_gb = 0
                self.transfer_left_bytes = (transfer_left_gb + premium_left_gb) * 1024 * 1024 * 1024
        except Exception:
            fflog_exc()

    def movie(self, imdb, title, localtitle, aliases, year):
        """ szukanie filmu """
        # fflog(f'{imdb=!r} {title=!r} {localtitle=!r} {year=!r} {aliases=!r}')
        return self.search(title, localtitle, year, aliases=aliases)

    def tvshow(self, imdb, tmdb, tvshowtitle, localtvshowtitle, aliases, year):
        # fflog(f'{imdb=!r} {tvshowtitle=!r} {localtvshowtitle=!r} {year=!r} {aliases=!r}')
        """ proteza pomocnicza przed szukaniem odcinka """
        return (tvshowtitle, localtvshowtitle, aliases), year

    def episode(self, url, imdb, tmdb, title, premiered, season, episode):
        """ szukanie odcinka """
        # fflog(f'{url=!r} {imdb=!r} {tmdb=!r} {title=!r} {premiered=!r} {season=!r} {episode=!r}')
        ep_number = ("s" + season.zfill(2) + "e" + episode.zfill(2))
        return self.search(url[0][0], url[0][1], aliases=url[0][2], year=url[1], episode=ep_number, premiered=premiered)

    def search(self, title, localtitle, year="", episode="", premiered="", aliases=None, recurrency=None):
        """ pobiera wyniki z API serwisu """
        try:
            # ustalenie bieżącego roku - a co jak ktoś ma złą datę na urządzeniu?
            title1 = title
            year = str(year)
            current_year = datetime.now().year

            if not recurrency:
                self.login()
                self.get_account_info()

                if aliases:
                    aliases1 = [
                        (a.get('title') or a.get('originalname') or '') + ' (' + a.get('country','') + ')'
                        for a in aliases
                    ]
                    aliases2 = [a.partition(' (')[0] for a in aliases1]
                    aliases2 = [a.replace(year, '').strip(' ()') for a in aliases2]
                    aliases2 = [a for a in aliases2 if not source_utils.czy_litery_krzaczki(a)]
                    aliases2 = list(dict.fromkeys(aliases2))

                    self.titles = aliases2 + self.titles
                    self.titles = [unicodedata.normalize("NFKC", t) for t in aliases2] + self.titles
                    self.titles = [re.sub(r' ?(\d)⁄', r' \1 ', t) for t in self.titles]
                    self.titles = list(dict.fromkeys(self.titles))

                    self.tit_val_filt_for_one_title = (title == localtitle)

            titles = [title, localtitle]

            if not recurrency:
                self.titles = titles + self.titles
                self.titles = list(filter(None, self.titles))
                self.titles = list(dict.fromkeys(self.titles))

            titles = [cleantitle.normalize(cleantitle.getsearch(t, preserve=(":"))) for t in titles]
            titles = [re.sub(r' ?(\d)⁄', r' \1 ', t) for t in titles]
            titles = [t.replace("&", "and") for t in titles]
            titles = list(filter(None, titles))
            titles = list(dict.fromkeys(titles))

            self.titles = titles + self.titles
            self.titles = list(dict.fromkeys(self.titles))

            tmp = []
            for t in self.titles:
                if ": " in t and "-" not in t:
                    temp1 = " - ".join(t.split(": ")[::-1])
                    if temp1 not in self.titles:
                        tmp += [temp1]
            self.titles += tmp

            franchise_names = const.sources.franchise_names
            sep = const.sources.franchise_names_sep

            def build_patterns(names, sep):
                return [sep.join(map(re.escape, name.split())) for name in names]
            franchise_aliases = {k: build_patterns(v, sep) for k, v in franchise_names.items()}

            episode_r = re.sub(r"(?<=\*).*", "", episode)
            episode = episode.replace("*", "")
            year_r = year if not episode else ""

            results = []

            release_tags_pattern = r"""
                \b(
                    lektor|subbed|napisy|dubbing|polish|po?l(dub|sub)?|
                    us|fr|de|es|it|nl|dual|multi|p2p|
                    bluray|blu-ray|bdrip|hdrip|dvdrip|hdtv|hddvd|uhd|
                    web[.-]?dl|webrip|webhdrip|remux|3d|imax|
                    cam(rip)?|ts|telesync|tc|telecine|scr|screener|r5|
                    fullhd|uhd|4k|2160p|1080p|720p|480p
                )\b
            """

            for title in titles:
                title = title.replace(":", "")
                title = cleantitle.normalize(title)
                zapytanie = f"{title} {year_r} {episode_r}".replace("  ", " ").strip()
                fflog(f"WYSŁANIE zapytania: {zapytanie!r}")
                data = {
                    "authtoken": self.authtoken,
                    "keyword": zapytanie,
                    "display": 500,
                    "video": True,
                    "mode": "ff",
                }

                res = self.req.post(self.search_url, data=data)
                search = res.json()

                if "error" in search and search["message"] != "":
                    cache.cache_insert(f"{self.PROVIDER}_authtoken", "", control.providercacheFile)
                    fflog("wystąpił błąd: " + search["message"])
                    return False

                if "search" in search:
                    search = search["search"]
                    fflog(f'otrzymano rekordów: {len(search["search_result"])}')

                    account_files_data = {"authtoken": self.authtoken, "video": True}
                    account_files_res = self.req.post(self.files_url, data=account_files_data)
                    account_files_json = account_files_res.json()

                    account_files_map = {}
                    if "files" in account_files_json and account_files_json["files"]:
                        for f in account_files_json["files"]:
                            if "url" in f:
                                f["on_account"] = True
                                account_files_map[f["url"]] = f

                    combined_results = []
                    if "search_result" in search and search["search_result"]:
                        for s_res in search["search_result"]:
                            if s_res["url"] in account_files_map:
                                combined_results.append(account_files_map.pop(s_res["url"]))
                            else:
                                combined_results.append(s_res)

                    for url in account_files_map:
                        combined_results.append(account_files_map[url])

                    if "search_result" in search and search["search_result"]:

                        title0 = title0_pat = ""

                        def _tit_pat_epis(title):
                            nonlocal title0, title0_pat
                            title0 = title
                            title0 = title0.replace(". ", " ").replace(".", " ")
                            title0 = title0.strip()
                            title0_pat = re.escape(title0)
                            title0_pat = re.sub(r'(\d\\ )(\d\\ \d(\\ )?)', r'\1(i\\ )?\2', title0_pat)
                            title0_pat = re.sub(r'(\d)(:?\\ )([a-zA-Z])', r'\1\2?\3', title0_pat)
                            title0_pat = title0_pat.replace(r"\ \-\ ", "[ ._-]+")
                            title0_pat = title0_pat.replace(r"\ ", "[ ._–-]+")
                            title0_pat = title0_pat.replace(':', '[ _]?[:–-]?')
                            title0_pat = source_utils.diacritics_in_pattern(title0_pat, mode=1)
                            return title0_pat

                        if "title2_pat" not in locals():
                            title2_pat = "(" + "|".join([_tit_pat_epis(t) for t in list(dict.fromkeys(map(str.lower, self.titles)))]) + ")"
                        _tit_pat_epis(title)

                        if episode:
                            episode_pat = re.sub(
                                r"(s\d{2})(e(\d{2,3}))",
                                r"\1[.,-]?e(\\d{2,3}-?)?e?0?\3(?!\\d)",
                                episode,
                                flags=re.I)

                            epn = int(re.search(r"e(\d{2,3})", episode).group(1)) if "e" in episode else 0
                            sn = int(re.search(r"s(\d{2})", episode).group(1)) if "s" in episode else 0
                            rang_pat = r"(?:s([\dO]{2})-?)?e(\d{2,3})-e?(\d{2,3})"
                            rang_re = re.compile(rang_pat, flags=re.I)

                            def ep_is_in_range(filename):
                                rang = rang_re.search(filename)
                                if rang:
                                    if not rang.group(1) and sn==1 or rang.group(1) and int(rang.group(1).replace('O','0'))==sn:
                                        return epn in range(int(rang.group(2)), int(rang.group(3)))
                                return None

                            year_in_title = re.search(r"\b\d{4}\b", title)
                            year_in_title = year_in_title[0] if year_in_title else ""

                            def _check_base_or_premiered_year_in_filename(filename):
                                if not premiered and not year:
                                    return
                                filename = filename.replace(year_in_title, "")
                                year_in_filename = re.search(r"\b\d{4}\b", filename)
                                if year_in_filename:
                                    year_in_filename = year_in_filename[0]
                                    if 1900 <= int(year_in_filename) <= int(current_year) + 1:
                                        if premiered and (premiered.startswith(year_in_filename) or premiered.endswith(year_in_filename)) or year and str(year) == year_in_filename:
                                            return True
                                        else:
                                            return False

                            for s in combined_results:
                                size = s["filesize"]
                                if premiered and re.search(r"\b\d{4}\b", s["filename"]):
                                    if _check_base_or_premiered_year_in_filename(s["filename"]) is False:
                                        continue

                                if "*" in episode_r:
                                    if re.search(episode_pat, s["filename"], flags=re.I) or ep_is_in_range(s["filename"]):
                                        s["filename"] = re.sub(episode_pat+"-?e?\\d{0,3}", episode, s["filename"], flags=re.I)
                                    else:
                                        continue

                                if not re.search(rf'\b({episode}|{episode.replace("s01","")})\b', unquote(s["filename"]), flags=re.I):
                                    continue

                                filename = s["filename"]
                                if (
                                    re.search(
                                        rf"^\d{{0,2}}\.?\W?({title2_pat}[ /-]{{0,3}})+[ -]?[0-9]?$",
                                        filename
                                    )
                                    or self.tit_val_filt_for_one_title and re.search(
                                        rf"(^|[/-]|  |\d{{1,2}})\W?{title0_pat}[1-9]?$",
                                        filename
                                    )
                                    or re.search(
                                        rf"^\W?{title0_pat}[ -]?[0-9]?($| [/-]|  )",
                                        filename
                                    )
                                    or re.search(
                                        rf"^\W?{re.escape(filename.strip())}$",
                                        title0
                                    )
                                    or sum(1 for t in self.titles if t.lower() in filename.lower()) >= 2
                                    or any(
                                        re.search(pat, filename, re.I)
                                        for pat_list in franchise_aliases.values()
                                        for pat in pat_list
                                    )
                                ):
                                    results.append(s)

                        else:
                            episode_pat = r"((S\d{1,2})?[.,-]?E\d{2,3}|\bcz\.|\bodc\.|\bep\.|episode|odcinek|[\(\[]\d{2,3}[\)\]]|\- \d{2,3} [([-]|\b\dx\d{2}\b)"
                            episode_pat = episode_pat.replace(r"\d", r"[\dO]").replace("0", "[0O]")
                            episode_uni_re = re.compile(episode_pat, flags=re.I)

                            for s in combined_results:
                                size = s["filesize"]
                                filename = s["filename"]
                                if (
                                    re.search(
                                        rf"^\d{{0,2}}\.?\W?({title2_pat}[ ()/-]{{0,4}})+[ -]?\d?$",
                                        filename
                                    )
                                    or sum(1 for t in self.titles if t.lower() in filename.lower()) >= 2
                                    or any(
                                        re.search(pat, filename, re.I)
                                        for pat_list in franchise_aliases.values()
                                        for pat in pat_list
                                    )
                                ):
                                    results.append(s)

                    else:
                        fflog(" Brak wyników")

            if not recurrency:
                ex_list = [re.escape(e) for e in source_utils.antifalse_filter_exceptions]
                ex_pat = f'(?:{"|".join(ex_list)})'
                if not results and re.search(ex_pat, " ".join([title1, localtitle])):
                    title2 = localtitle2 = ""
                    if re.search(rf"([_\W]+{ex_pat})", title1, flags=re.I):
                        title1 = title2 = re.sub(rf"([_\W]+{ex_pat})", "", title1, flags=re.I)
                    if re.search(rf"([_\W]+{ex_pat})", localtitle, flags=re.I):
                        localtitle = localtitle2 = re.sub(rf"([_\W]+{ex_pat})", "", localtitle, flags=re.I)
                    fflog("szukam ponownie po wycięciu pewnych fraz")
                    results = self.search(title2, localtitle2, year, episode, premiered, recurrency=True)

                episode0 = episode
                if not results and re.search("s01", episode):
                    fflog("!Podjęcie ponownej próby z pominięciem sezonu")
                    episode = re.sub("s01", "", episode)
                    title = title1
                    results = self.search(title, localtitle, year, episode, premiered, recurrency=True)

                if not results and re.search(r"e\d{2}(?!\d)", episode):
                    fflog("!Sprawdzenie, czy może numer odcinka jest zapisany jako 3-cyfrowy")
                    episode = re.sub(r"(s\d\d)?(e(\d\d))", r"\1e0\3", episode)
                    title = title1
                    results = self.search(title, localtitle, year, episode, premiered, recurrency=True)
                    if not results and not re.search(r"s\d{2}e\d{2,3}", episode):
                        results = self.search(title, localtitle, year, "s01"+episode, premiered, recurrency=True)

                if not results and episode and "*" not in episode:
                    fflog("!Sprawdzenie, czy może odcinek jest złączony z innym")
                    episode = re.sub(r"(s\d{2})(e(\d{2,3}))", r"\1*\2", episode0)
                    title = title1
                    results = self.search(title, localtitle, year, episode, premiered, recurrency=True)

                if not results and episode and "*" in episode:
                    fflog("!Sprawdzenie, czy może odcinek nie ma E, tylko sam numer")
                    episode = re.sub("s01e", "", episode0)
                    title = title1
                    results = self.search(title, localtitle, year, episode, premiered, recurrency=True)

                if not results:
                    originalname = [a for a in aliases if "originalname" in a]
                    originalname = originalname[0]["originalname"] if originalname else ""
                    if (
                        originalname
                        and originalname != title1
                        and originalname != localtitle
                        and not source_utils.czy_litery_krzaczki(originalname)
                    ):
                        fflog("sprawdzenie po tytule nieanglojęzycznym")
                        episode = re.sub(r"(s\d{2})(e(\d{2,3}))", r"\1*\2", episode0)
                        results = self.search(originalname, "", year, episode, premiered, recurrency=True)

                    if year and not episode:
                        fflog(f"!Podjęcie ponownej próby, lecz tym razem dla roku '{int(year)-1}'")
                        results = self.search(title1, localtitle, str(int(year) - 1), episode, premiered, recurrency=True)

            if not results:
                fflog("Nie znaleziono źródeł.")
            else:
                fflog(f'Zatwierdzono rekordów: {len(results)} ')

            return results
        except Exception:
            fflog_exc()

    # reszta klasy (_source) pozostaje bez zmian – sources(), recalculate(), resolve(), itd.

class Rapideo(_source):
    PROVIDER: ClassVar[str] = 'rapideo'
    URL: ClassVar[str] = 'https://www.rapideo.pl'


class TwojLimit(_source):
    PROVIDER: ClassVar[str] = 'twojlimit'
    URL: ClassVar[str] = 'https://www.twojlimit.pl'


class NoPremium(_source):
    PROVIDER: ClassVar[str] = 'nopremium'
    URL: ClassVar[str] = 'https://www.nopremium.pl'


def register(sources: List[SourceModule], group: str) -> None:
    from lib.sources import SourceModule
    for src in (Rapideo, TwojLimit, NoPremium):
        sources.append(SourceModule(name=src.PROVIDER, provider=src(), group=group))
