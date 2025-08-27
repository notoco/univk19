# -*- coding: utf-8 -*-
"""
    FanFilm Add-on
    Copyright (C) 2025 :)

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

import base64
import re
from typing import Dict, List, Optional
from urllib.parse import quote, quote_plus, unquote_plus
from html import unescape

# import json
from lib.ff import requests

from lib.sources import single_call
from lib.ff import source_utils, control, cache, cleantitle, utils
from lib.ff.source_utils import setting_cookie
from lib.ff.client import parseDOM
from lib.ff.settings import settings
from lib.ff.log_utils import fflog, fflog_exc


class source:
    def __init__(self):
        self.priority = 1
        self.language = ["pl"]
        self.domains = ["filman.cc"]  # niewykorzystywane obecnie
        self.initialized = False

    @single_call
    def init(self):
        self.base_link = "https://filman.cc"
        self.login_link = "https://filman.cc/logowanie"
        self.search_link = "https://filman.cc/item?phrase={title}"
        self.username = settings.getString("filman.username")
        self.password = settings.getString("filman.password")

        self.year = 0

        # Mnożniki jednostek czasu w sekundach
        self.TIME_UNITS = {
            "minutę": 60,
            "minuty": 60,
            "minut": 60,
            "godzinę": 3600,
            "godziny": 3600,
            "godzin": 3600,
            "dzień": 86400,
            "dni": 86400,
            "tydzień": 604800,
            "tygodnie": 604800,
            "tygodni": 604800,
            "miesiąc": 2592000,
            "miesiące": 2592000,
            "miesięcy": 2592000,
            "rok": 31536000,
            "lata": 31536000,
            "lat": 31536000
        }

        if USER_AGENT := settings.getString("filman.user_agent").strip(' "\''):
            # fflog('będzie użyty UserAgent użytkownika')
            pass
        else:
            USER_AGENT = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                # "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0"  # navigator.userAgent
            )
        self.USER_AGENT = USER_AGENT

        self.HEADERS = {
            "Host": "filman.cc",
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "pl,en-US;q=0.7,en;q=0.3",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
        }

        cookies = ''
        if bkd_remember := setting_cookie(setting_name='filman.cookies', cookie_name='BKD_REMEMBER'):  # document.cookie
            # fflog('będzie użyta sesja użytkownika')
            self.USER_SESSION = True
            cookies = f'BKD_REMEMBER={bkd_remember}'
            # ciasteczko od Cloudflare
            if cf := setting_cookie(setting_name='filman.cookies_cf', cookie_name='cf_clearance'):
                cookies = f'{cookies}; cf_clearance={cf}'
        else:
            self.USER_SESSION = False
        if cookies:
            # fflog('wstawienie ciasteczek użytkownika do bazy cache')
            # fflog(f'{cookies=}')
            cache.cache_insert("filman_cookie", cookies, control.providercacheFile)  # wstawienie jej do bazy

        self.session = requests.Session()
        self.session.cookies = requests.cookies.RequestsCookieJar()
        self.initialized = False

        self.initialize_session()

    def initialize_session(self):
        """Initialize the session by fetching the home and login pages."""
        # fflog('Initialize the session')
        try:
            self.session.headers.update(self.HEADERS)
            if not self.USER_SESSION:
                # fflog('request do strony głównej i logowania')
                response, _ = self.get_response(self.base_link)  # Initialize session
                if not response:
                    fflog(f'{response=}')
                    return
                self.get_response(self.login_link)  # Get login page
            self.initialized = True
        except Exception:
            fflog_exc()

    def login(self):
        """Login to the service."""
        # fflog('try login to website')
        self.init()
        try:
            if not self.initialized:
                self.initialize_session()

            if not self.username or not self.password:
                msg = "brak danych do zalogowania"
                fflog(f'{msg}')
                return None

            login_data = {"login": self.username, "password": self.password, "remember": "on", "submit": ""}
            response_text, cookies_str = self.get_response(self.login_link, data=login_data, method="post")
            # fflog(f'{cookies_str=}')
            # fflog(f'{response_text=}')

            if "yloguj" in response_text:
                fflog("Zalogowano poprawnie")
                cookies = "; ".join([f"{x}={y}" for x, y in self.session.cookies.get_dict().items()])
                cache.cache_insert("filman_cookie", cookies, control.providercacheFile)
                return True
            if "nieprawidłowy kod Cap" in response_text:  # w <div id="flash">
                msg = "nieprawidłowa Captcha"
                fflog(msg)
            else:
                fflog('wystąpił jakiś problem')
                # fflog(f'{response_text=}')
                pass
            fflog("Nie zalogowano")
            return False
        except Exception:
            fflog_exc()

    def is_logged_in(self):
        """Check if user is logged in."""
        try:
            cookies_str = cache.cache_get("filman_cookie", control.providercacheFile)
            if cookies_str:
                cookies_str = cookies_str.get("value")
                # fflog(f'{cookies_str=}')
                cookies = dict(cookie.split("=") for cookie in cookies_str.split("; "))
                # fflog(f'{cookies=}')
                self.session.cookies.update(cookies)
                login_status = self.check_login_status()
                if login_status:
                    # może uaktualnić ciasteczka w bazie jak sesja użytkownika ?
                    return True
                elif login_status is False:
                    # Clear the cookies if the login status check fails
                    # fflog('usunięcie zapisanego ciasteczka z bazy cache')
                    cache.remove_partial_key("filman_cookie")
                    self.session.cookies.clear()
                    # Attempt to login again
                    return self.login()
            return None
        except Exception:
            fflog_exc()

    def check_login_status(self):
        """Check login status."""
        self.init()
        try:
            response = self.session.get(self.base_link, headers=self.HEADERS, verify=False)
            if not response:
                fflog(f'{response=}')
                return None
            # fflog(f'{self.HEADERS=}')
            # fflog(f'{response.text=}')
            if "yloguj" in response.text:
                fflog('zalogowany')
                if False:  # opcjonalnie
                    user = parseDOM(response.text, "a", attrs={"id": "dropdown"})[0]
                    user = re.sub("<[^>]+>", "", user).strip()
                    fflog(f'{user}')
                # może uaktualnić ciasteczka w bazie jak sesja użytkownika ?
                return True
            else:
                fflog('niezalogowany')
                return False
        except Exception:
            fflog_exc()
            return False

    def search(self, title, localtitle, year, results=None):  # zrezygnować z rekurencji
        """Search for a movie."""
        self.init()
        # fflog(f'{title=}, {localtitle=}, {year=}')
        try:
            # if not self.login():
            if not self.is_logged_in():
                fflog("Login failed")
                return None

            # fflog("user is logged in")

            # Cache normalized titles to avoid redundant processing
            normalized_titles = set()  # a jak będzie list, co źle ?

            for t in [title, localtitle]:
                normalized_titles.add(t)  # bez przekształceń
                normalized_titles.add(cleantitle.normalize(t))  # polskie diakrytyczne
                normalized_titles.add(cleantitle.getsearch(t))
                normalized_titles.add(cleantitle.getsearch(t.split("–")[0].replace("-", " ")))

            normalized_titles = [t.lower() for t in normalized_titles]
            normalized_titles = list(dict.fromkeys(normalized_titles))
            fflog(f'{normalized_titles=}')

            if results is None:

                results = []

                for normalized_title in normalized_titles:

                    url = self.search_link.format(title=quote_plus(normalized_title))
                    fflog(f'{url=}   ({unquote_plus(url)})')
                    content, _ = self.get_response(url)
                    # results.append((normalized_title, content))
                    results = [(normalized_title, content)]  # dla kompatybilności z istniejącym kodem

                    films = []
                    # fflog(f'{len(results)=}')
                    for title, content in results:
                        # fflog(f'{title=}')
                        try:
                            posters = re.findall(r'<div class="poster">(.*?)</div>', content, re.DOTALL)  # nie zawiera w sobie roku
                            films_year = re.findall(r'<div class="film_year">(.*?)</div>', content, re.DOTALL)
                            # films_title = re.findall(r'<div class="film_title">(.*?)</div>', content, re.DOTALL)

                            for i,result in enumerate(posters):
                                src = re.findall(r'<img src="(.*?)"', result)[0].replace("thumb", "big")
                                href = re.findall(r'<a href="(.*?)"', result)[0]
                                if "/m/" not in href:
                                    continue
                                film_title = re.findall(r' (?:title|alt)="(.*?)"', result)[0]
                                film_year = films_year[i]  # jeśli idzie to w parze z posters, to będzie ok

                                if src.startswith("//"):
                                    src = "https:" + src

                                for title in normalized_titles:

                                    film = {
                                        # "href": href.replace("/movies/", "/m/"),
                                        "href": href,
                                        "title": unescape(utils.decode_title_from_latin1(utils.escape_special_characters(film_title))),
                                        # "title": film_title,
                                        "year": film_year,
                                    }
                                    title_parts = film["title"].split(" / ")
                                    # fflog(f'\n{title_parts=}')

                                    primary_words = cleantitle.normalize(title_parts[0].strip()).lower()
                                    # fflog(f'{title=}  {primary_words=}')
                                    ratio_primary = utils.calculate_similarity_ratio(title, primary_words)
                                    levenshtein_primary = utils.calculate_levenshtein_distance(title, primary_words)
                                    film.update(
                                        {
                                            "ratio": ratio_primary,
                                            "levenshtein": levenshtein_primary,
                                        }
                                    )
                                    # fflog(f'{film=}')
                                    films.append(film)

                                    if len(title_parts) > 1:
                                        words = cleantitle.normalize(title_parts[1].strip()).lower()
                                        # fflog(f'{title=}  {words=}')
                                        secondary_film = film.copy()
                                        secondary_film.update(
                                            {
                                                "ratio": utils.calculate_similarity_ratio(title, words),
                                                "levenshtein": utils.calculate_levenshtein_distance(title, words),
                                            }
                                        )
                                        # fflog(f'{secondary_film=} \n')
                                        films.append(secondary_film)
                        except Exception:
                            fflog_exc()
                            # fflog(f'{result=}')

                    films = sorted(films, key=lambda x: (x["ratio"], -x["levenshtein"]), reverse=True)

                    for film in films:
                        # fflog(f'{film=}')
                        try:
                            if 0.94 < film["ratio"] <= 1.0 and film["levenshtein"] <= 4:
                                # if "/m/" in film["href"] and str(year) in film["href"]:
                                if "/m/" in film["href"] and str(year) in film["year"]:  # rozszerzyć zakres roku
                                    fflog(f'dopasowano {film=} {year=}')
                                    # return film["href"]
                                    return (film["href"], film["title"])
                                else:
                                    fflog(f'1 nie pasuje {year=}  {film=}')
                                    pass
                            else:
                                fflog(f'1 chyba nie ten film {film=}')
                                pass
                        except Exception:
                            fflog_exc()
                    """
                    for film in films:
                        # fflog(f'{film=}')
                        try:
                            normalized_search_title = cleantitle.normalize(utils.decode_title_from_latin1(title)).lower()
                            normalized_film_title = cleantitle.normalize(film["title"]).lower()
                            if normalized_film_title.startswith(normalized_search_title):
                                # if "/m/" in film["href"] and str(year) in film["href"]:
                                if "/m/" in film["href"] and str(year) in film["year"]:  # rozszerzyć zakres roku
                                    fflog(f'pasuje {film=} {year=}')
                                    # return film["href"]
                                    return (film["href"], film["title"])
                                else:
                                    # fflog(f'2 nie pasuje {film=} {year=}')
                                    pass
                            else:
                                # fflog(f'2 chyba nie ten film {film=}')
                                pass
                        except Exception as e:
                            fflog_exc(e, title="Error processing startswith check")
                    """
            fflog('nic nie dopasowano')
            """
            if int(self.year) - int(year) < 1:
                previous_year = str(int(year) - 1)
                fflog(f'bedzie powtórka na {previous_year=}')
                control.sleep(500)
                return self.search(title, localtitle, previous_year, results=results)  # rekurencja może się zapętlić
            """
        except Exception:
            fflog_exc()
            return None

    def movie(self, imdb, title, localtitle, aliases, year):
        """Search for a movie."""
        # return self.sources( ('https://filman.cc/m/IQMza4W5RVPhE8jfpsK2XvHxA', 'Matrix / The Matrix'), [], [])  # do testów tylko
        self.init()
        self.year = int(year)
        # fflog(f'szukanie filmu {title=} {localtitle=} {year=} {aliases=}')
        return self.search(title, localtitle, year)

    def tvshow(self, imdb, tmdb, tvshowtitle, localtvshowtitle, aliases, year):
        """Search for a TV show."""
        self.init()
        pl_alias = next((alias for alias in aliases if alias.get("country") == "original"), None)
        pl_title = pl_alias.get("originalname", "") if pl_alias else ""
        return (tvshowtitle, localtvshowtitle, pl_title), year

    def episode(self, url, imdb, tmdb, title, premiered, season, episode):
        """Search for a TV show episode."""
        self.init()
        # Extract title components from the URL
        original_title = url[0][0]
        local_title = url[0][1]
        pl_alias = url[0][2]

        # Extract the year from the URL
        self.year = int(url[1])

        # Format the episode number to the standard format "sXXeXX"
        ep_no = self._format_episode_number(season, episode)

        # Perform the episode search with the extracted and formatted parameters
        return self.search_ep(original_title, local_title, self.year, pl_alias, ep_no)

    def _format_episode_number(self, season, episode):
        """Format season and episode numbers to the standard 'sXXeXX' format."""
        season_str = str(season).zfill(2)
        episode_str = str(episode).zfill(2)
        return f"s{season_str}e{episode_str}"

    def search_ep(
        self, title: str, localtitle: str, year: int, pl_alias: str, ep_no: str, year_flag: bool = False, results=None
    ) -> Optional[str]:
        """Search for a TV show episode."""
        try:
            # if not self.login():
            if not self.is_logged_in():
                fflog("Login failed")
                return None

            # fflog("user is logged in")

            normalized_titles = self._get_normalized_titles([title, localtitle, pl_alias])

            if results is None:
                # results = self._fetch_search_results(normalized_titles)  # wczytywanie na zaś
                # fflog(f'{results=}')
                pass

            # _fetch_search_results
            results = []
            for normalized_title in normalized_titles:

                url = self.search_link.format(title=quote_plus(normalized_title))
                fflog(f'{url=}   {unquote_plus(url)}')
                content, _ = self.get_response(url)
                # results.append((normalized_title, content))
                results = [(normalized_title, content)]  # dla kompatybilności z istniejącym kodem

                tvshows = self._process_search_results(results, title, year)  # tu ewentualnie rozszerzyć zakres roku
                # fflog(f'{tvshows=}')
                for tvshow in tvshows:
                    url = self._extract_episode_url(tvshow, ep_no)
                    if url:
                        return url

                for tvshow in tvshows:
                    url = self._extract_episode_url(tvshow, ep_no, check_startswith=True, search_title=title)
                    if url:
                        return url

            fflog('nic nie znaleziono')
            """
            if not year_flag:
                pass
                # fflog(f'będzie powtórka dla roku {str(int(year) - 1)}')
                # return self.search_ep(title, localtitle, str(int(year) - 1), pl_alias, ep_no, year_flag=True, results=results)  # rekurencja
            """
            return None
        except Exception:
            fflog_exc()
            return None

    def _get_normalized_titles(self, raw_titles: List[str]) -> set:
        normalized_titles = {cleantitle.normalize(t).lower() for t in raw_titles if t}
        normalized_titles.update({cleantitle.getsearch(t).lower() for t in raw_titles if t})
        normalized_titles.update({cleantitle.getsearch(t.split("–")[0].replace("-", " ")).lower() for t in raw_titles if t})
        normalized_titles = [t.lower() for t in normalized_titles]
        normalized_titles = list(dict.fromkeys(normalized_titles))  # czy może być list zamiast set ?
        fflog(f'{normalized_titles=}')
        return normalized_titles

    def _fetch_search_results(self, normalized_titles: set) -> List[tuple]:
        results = []
        for normalized_title in normalized_titles:
            url = self.search_link.format(title=quote_plus(normalized_title))
            fflog(f'{url=}')
            content, _ = self.get_response(url)  # wczytywanie na zaś
            results.append((normalized_title, content))
        return results

    def _process_search_results(self, results: List[tuple], title: str, year: int) -> List[Dict[str, str]]:
        tvshows = []
        should_break = False
        title = title.lower()

        for normalized_title, content in results:
            if should_break:
                break

            try:
                # Wzór wyrażenia regularnego do wyciągnięcia bloków "poster" wraz z rokiem
                pattern = r'(<div class="poster">.*?</div>)\s*<div class="film_year">(\d{4})</div>'

                # Znajdź wszystkie pasujące bloki wraz z rokiem
                matches = re.findall(pattern, content, re.DOTALL)

                # Przetwarzaj wyniki
                tvshow = {}
                for result, film_year in matches:

                    tvshow = self._extract_tvshow_info(result)

                    if "/s/" not in tvshow['href']:
                        continue

                    tvshow.update({"year": film_year})

                    if not tvshow or str(year) != self._fix_year(normalized_title, film_year):  # ewentualnie rozszerzyć zakres roku
                        fflog(f'rok nie pasuje {tvshow=}')
                        continue

                    primary_words, ratio_primary, levenshtein_primary = self._calculate_similarity(
                        tvshow["title"].split("/")[0].strip().lower(), normalized_title
                    )
                    tvshow.update({"ratio": ratio_primary, "levenshtein": levenshtein_primary})

                    tvshows.append(tvshow)

                    if ratio_primary == 1 or levenshtein_primary == 0:
                        should_break = True
                        break

                    if len(tvshow["title"].split("/")) > 1:
                        secondary_tvshow = self._process_secondary_title(tvshow, normalized_title)
                        tvshows.append(secondary_tvshow)

                        if secondary_tvshow["ratio"] == 1 or secondary_tvshow["levenshtein"] == 0:
                            should_break = True
                            break

                    fflog(f'to nie ten serial {tvshow=}')
            except Exception:
                fflog_exc()

        tvshows = sorted(tvshows, key=lambda x: (x["ratio"], -x["levenshtein"]), reverse=True)
        fflog(f'{tvshows=}')
        return tvshows

    def _fix_year(self, title: str, year: str):
        if "gra o tron" in title.lower():
            fflog(f'korekta roku na 2011 dla {title=}')
            return "2011"
        if "mr. robot" in title.lower():
            fflog(f'korekta roku na 2015 dla {title=}')
            return "2015"
        else:
            return year

    def _extract_tvshow_info(self, result: str) -> Dict[str, str]:
        try:
            src = re.findall(r'<img src="(.*?)"', result)[0].replace("thumb", "big")
            href = re.findall(r'<a href="(.*?)"', result)[0]
            tvshow_title = re.findall(r' (?:title|alt)="(.*?)"', result)[0]

            if src.startswith("//"):
                src = "https:" + src

            tvshow = {
                "href": href,
                "title": utils.decode_title_from_latin1(utils.escape_special_characters(tvshow_title)),
                # "year": ,
            }
            return tvshow
        except IndexError:
            return {}

    def _calculate_similarity(self, tvshow_title: str, search_title: str) -> tuple:
        search_title = cleantitle.normalize(search_title)
        title_parts = tvshow_title.split("/")
        primary_words = cleantitle.normalize(title_parts[0].strip().lower())
        ratio_primary = utils.calculate_similarity_ratio(search_title, primary_words)
        levenshtein_primary = utils.calculate_levenshtein_distance(search_title, primary_words)
        return primary_words, ratio_primary, levenshtein_primary

    def _process_secondary_title(self, tvshow: Dict[str, str], search_title: str) -> Dict[str, str]:
        search_title = cleantitle.normalize(search_title)
        words = cleantitle.normalize(tvshow["title"].split("/")[1].strip().lower())
        secondary_tvshow = tvshow.copy()
        secondary_tvshow.update(
            {
                "ratio": utils.calculate_similarity_ratio(search_title, words),
                "levenshtein": utils.calculate_levenshtein_distance(search_title, words),
            }
        )
        return secondary_tvshow

    def _extract_episode_url(
        self, tvshow: Dict[str, str], ep_no: str, check_startswith: bool = False, search_title: str = ""
    ) -> Optional[str]:
        try:
            if check_startswith:
                normalized_search_title = cleantitle.normalize(utils.decode_title_from_latin1(search_title)).lower()
                normalized_tvshow_title = cleantitle.normalize(tvshow["title"]).lower()
                if not normalized_tvshow_title.startswith(normalized_search_title):
                    return None

            # fflog(f'{tvshow["href"]=}')
            if "/s/" in tvshow["href"]:
                content2, _ = self.get_response(tvshow["href"])
                pattern = re.compile(r"<span>Sezon (\d+)</span>.*?<ul>(.*?)</ul>", re.DOTALL)
                episode_pattern = re.compile(r'<a href="(.*?)">\[s(\d+)e(\d+)\] (.*?)</a>')

                seasons = pattern.findall(content2)
                episodes_dict = {}
                for season, episodes_html in seasons:
                    for match in episode_pattern.findall(episodes_html):
                        url, season_number, episode_number, title = match
                        season_number = int(season_number)
                        episode_number = int(episode_number)
                        epno = f"s{season_number:02d}e{episode_number:02d}"
                        episodes_dict[epno] = {"url": url}

                if ep_no in episodes_dict.keys():
                    # return episodes_dict[ep_no]["url"]
                    return (episodes_dict[ep_no]["url"], tvshow["title"]+ f"  {ep_no}")
        except Exception:
            fflog_exc()
        return None

    def sources(self, url, hostDict, hostprDict):
        """Get movie sources."""
        self.init()
        try:
            # fflog(f'{url=}')
            if isinstance(url, tuple):
                url, title = url
            else:
                title = year = ""

            sources = []
            headers = {"referer": "https://filman.cc/", "user-agent": "Mozilla"}

            # Funkcja do tworzenia linku Kodi
            def create_kodi_link(url, headers):
                # Kodowanie wartości nagłówków
                encoded_headers = {key: quote(value, safe="") for key, value in headers.items()}
                # Łączenie zakodowanych nagłówków w format Kodi
                options = "&".join([f"{key}={value}" for key, value in encoded_headers.items()])
                kodi_link = f"{url}|{options}"
                # fflog(f'{kodi_link=}')
                return kodi_link

            if not url:
                return sources

            if not self.is_logged_in():
                fflog("Login failed")
                return sources

            results = self.get_videos(url)
            # fflog(f'{results=}')
            # fflog(f'{len(results)=} results={json.dumps(results, indent=2)}')
            results = self.sort_by_ago(results)
            # fflog(f'{len(results)=} results={json.dumps(results, indent=2)}')

            for result in results:
                # fflog(f'{result=}')
                valid, host = source_utils.is_host_valid(result["url"], hostDict)
                if valid or "wolfstraam" in host:
                    if result.get("host"):
                        host = result["host"]
                    host = host.rsplit(".", 1)[0]
                    sources.append(
                        {
                            "source": host,   # + (f'  ({result["ago"]})')
                            "url": create_kodi_link(result["url"], headers) if "wolfstraam" in host else result["url"],
                            "quality": result["quality"],
                            "language": result["lang"],
                            "info": result["sound"],
                            "filename": result["ago"],   # title
                            "direct": False,
                            "debridonly": False,
                        }
                    )
                else:
                    pass
                    fflog(f'not valid {valid=} {host=} {result=}')
            # fflog(f'{len(sources)=} sources={json.dumps(sources, indent=2)}')
            fflog(f'przekazano źródeł: {len(sources)}')
            return sources
        except Exception:
            fflog_exc()
            return sources

    def resolve(self, url):
        """Resolve URL."""
        return url

    def get_response(self, url, headers=None, data=None, method="get") -> 'tuple[str, str]':
        """Make HTTP request."""
        if headers is None:
            headers = self.HEADERS
        try:
            response = (
                self.session.post(url, headers=headers, data=data, verify=False)
                if method == "post"
                else self.session.get(url, headers=headers, verify=False)
            )
            if not response:
                fflog(f'błąd {response=} {url=}')
                pass
                return '', ''
            cookies_str = "; ".join([f"{c.name}={c.value}" for c in self.session.cookies])
            return response.text, cookies_str
        except Exception:
            fflog_exc()
            return '', ''

    def get_videos(self, url: str) -> List[Dict[str, str]]:
        """Get list of videos from the URL."""
        # fflog(f'{url=}')
        content, _ = self.get_response(url)
        out = []

        try:
            table_content = parseDOM(content, "table", attrs={"id": "links"})
            if not table_content:
                fflog(f'{table_content=}')
                fflog(f'{content=}')
                return out

            result = parseDOM(table_content[0], "tbody")
            if not result:
                fflog(f'{result=}')
                return out

            rows = self._get_rows(result[0])
            for row in rows:
                # fflog(f'{row=}')
                try:
                    video_info = self._extract_video_info(row)
                    if video_info:
                        out.append(video_info)
                    else:
                        fflog(f'{video_info=}')
                        pass
                except Exception:
                    fflog_exc()
        except Exception:
            fflog_exc()

        return out

    def _get_rows(self, content: str) -> List[str]:
        row_pattern = re.compile(r'<tr class="[^"]*version[^"]*">(.+?)</tr>', re.DOTALL)
        return row_pattern.findall(content)

    def _extract_video_info(self, row: str) -> Dict[str, str]:
        iframe_pattern = re.compile(r'data-iframe="([^"]+)"')
        href_pattern = re.compile(r'<a href="([^"]+)" target="_blank" data-mp4="true">')
        td_pattern = re.compile(r"<td[^>]*>(.*?)</td>")

        iframe_match = iframe_pattern.findall(row)
        href_match = href_pattern.findall(row)
        td_values = td_pattern.findall(row)
        # fflog(f'{td_values=}')

        if iframe_match:
            hrefok = self._decode_base64_url(iframe_match[0])
            sound, quality = self._extract_td_values(td_values, 1, 2)
        elif href_match:
            hrefok = self._decode_base64_url(href_match[0])
            sound, quality = self._extract_td_values(td_values, -3, -2)
        else:
            hrefok = None
            fflog(f'{hrefok=} {iframe_match=} {href_match=}')

        if hrefok:
            sound, lang = self._process_sound(sound)
            ago = re.sub(".*dodane (.*?temu).*", r"\1", td_values[0])
            host = re.search(r' alt="(.*?)"', td_values[0]);  host = host[1] if host else ""
            return {"host": host, "url": hrefok, "quality": quality, "sound": sound, "lang": lang, "ago": ago}

        return {}

    def _decode_base64_url(self, encoded_url: str) -> str:
        decoded_iframe = base64.b64decode(encoded_url).decode("utf-8").replace("\\/", "/")
        # fflog(f'{decoded_iframe=}')
        if "wolfstraam" in decoded_iframe:
            return decoded_iframe
        else:
            iframe = re.findall(r"src['\"]:['\"](.+?)['\"]", decoded_iframe)
            if iframe:
                iframe = iframe[0]
                return iframe
            else:
                return decoded_iframe

    def _extract_td_values(self, td_values: List[str], sound_idx: int, quality_idx: int) -> (str, str):
        sound = td_values[sound_idx].strip()
        quality = source_utils.check_sd_url(td_values[quality_idx].strip())
        return sound, quality

    def _process_sound(self, sound: str) -> (str, str):
        sound = sound.replace("Napisy_Tansl", "napisy").replace("ENG", "en")
        sound = sound.replace("_", " ").replace("ENG", "en")
        lang = "en" if "en" in sound else "pl"
        sound = " " if lang == "en" else sound
        sound = sound.replace("PL", "").strip()
        return sound, lang

    def get_url_req(self, url, ref, allow=True):  # niewykorzystywana
        """Make HTTP request with cookies."""
        try:
            cookies_str = cache.cache_get("filman_cookie", control.providercacheFile)
            if cookies_str:
                cookies_str = cookies_str.get("value")
                cookies = dict(cookie.split("=") for cookie in cookies_str.split("; "))
                self.session.cookies.update(cookies)

            headers = {
                "Host": "filman.cc",
                "User-Agent": self.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "pl,en-US;q=0.7,en;q=0.3",
                "Referer": ref,
                "Upgrade-Insecure-Requests": "1",
            }

            self.session.headers.update(headers)
            response = self.session.get(url, verify=False, allow_redirects=allow)

            if "Security Check" in response.text:
                response = self.session.get(url, headers=headers)
                cookies = "; ".join([f"{x}={y}" for x, y in self.session.cookies.get_dict().items()])
                cache.cache_insert("filman_cookie", cookies, control.providercacheFile)

            return response.text if allow else response.content
        except Exception:
            fflog_exc()

    # stworzone przez ChatGPT
    def parse_time_string(self, time_str):
        """
        Przekształca słowny opis czasu w liczbę sekund temu.
        Obsługuje zarówno "1 rok temu", jak i "rok temu".
        """
        match = re.match(r"(?:\b(\d+)\b\s+)?(\w+)", time_str)
        if not match:
            return float('inf')  # Nieznany format – wrzucamy na koniec
        value, unit = match.groups()
        value = int(value) if value else 1  # Domyślnie 1, jeśli brak liczby
        multiplier = self.TIME_UNITS.get(unit, None)
        if multiplier is None:
            return float('inf')
        return value * multiplier

    def sort_by_ago(self, data, key="ago"):
        """
        Sortuje listę słowników według czasu w polu 'key' (np. 'ago').
        """
        return sorted(data, key=lambda x: self.parse_time_string(x[key]))
