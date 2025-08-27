"""
    FanFilm Add-on
    Copyright (C) 2024

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

# import json
import re

# from urllib.parse import urlparse
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from html import unescape

from lib.ff import requests
from lib.ff import source_utils, control, cache, cleantitle, client
from lib.ff.source_utils import setting_cookie
from lib.ff.settings import settings
from const import const
from lib.ff.log_utils import fflog, fflog_exc


class source:
    def __init__(self):
        self.priority = 1
        self.language = ["pl"]
        self.domains = ["cda-hd.cc"]
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "pl,en-US;q=0.7,en;q=0.3", "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            }
        if UA := settings.getString("cdahd.user_agent").strip(' "\''):
            self.headers.update({"User-Agent": UA})

        self.base_link = "https://cda-hd.cc"
        self.search_link = "/?s=%s"

    def movie(self, imdb, title, localtitle, aliases, year):
        return self.do_search(title, localtitle, year, aliases)

    def tvshow(self, imdb, tvdb, tvshowtitle, localtvshowtitle, aliases, year):
        return self.do_search(tvshowtitle, localtvshowtitle, year, aliases)

    def do_search(self, title, localtitle, year, aliases=None):
        try:
            if aliases:
                originalname = [a for a in aliases if "originalname" in a]
                originalname = originalname[0]["originalname"] if originalname else ""
                originalname = "" if source_utils.czy_litery_krzaczki(originalname) else originalname
            else:
                originalname = ""

            titles = [localtitle, originalname, title]
            titles = list(filter(None, titles))  # usuń puste
            titles = list(dict.fromkeys(titles))  # deduplikacja

            #  franczyzy: pobranie definicji + wzorców
            try:
                franchise_names = const.sources.franchise_names
            except Exception as e:
                fflog(f"[cdahd] franchise config not available: {e}")
                franchise_names = {}

            def build_patterns(names, sep):
                # Zamienia spacje na sep (wzorzec [ .]) i zwraca listę wzorców regex
                return [sep.join(map(re.escape, name.split())) for name in names]

            # Normalizacja porównawcza: usuń znaki nie-słowne i zrób lower()
            def normcmp(s: str) -> str:
                return re.sub(r"\W+", "", (s or ""), flags=re.UNICODE).lower()

            # Zbuduj lookup: baza -> pełne aliasy (pozwala trafić po samym "Akolita"/"Acolyte")
            fr_lookup = {}
            for base, variants in franchise_names.items():
                base_norm = normcmp(base)
                fr_lookup.setdefault(base_norm, set()).update(variants)
                for v in variants:
                    # dodaj klucz po ostatnim wyrazie aliasu, np. "Akolita" / "Acolyte"
                    last = (v.split()[-1] if v.split() else v)
                    fr_lookup.setdefault(normcmp(last), set()).update(variants)
                    # oraz po pełnym aliasie
                    fr_lookup.setdefault(normcmp(v), set()).update(variants)

            # Rozszerz zapytania o pełne tytuły franczyz, gdy użytkownik podał bazę/ostatni wyraz
            use_franchise_only = True
            extra_titles = []
            for t in titles:
                norm_t = normcmp(t)
                if norm_t in fr_lookup:
                    extra_titles.extend(list(fr_lookup[norm_t]))

            if extra_titles:
                if use_franchise_only:
                    titles = list(dict.fromkeys(extra_titles))  # zastępuje pierwotne tytuły
                else:
                    titles.extend(extra_titles)
                    titles = list(dict.fromkeys(titles))  # deduplikacja ponowna

            fflog(f'{titles=}')

            titles_for_compare = [normcmp(t) for t in titles]

            cookies = setting_cookie(setting_name='cdahd.cookies_cf', cookie_name='cf_clearance')
            if cookies:
                cache.cache_insert("cdahd_cookies", cookies, control.providercacheFile)
                self.headers.update({'Cookie': cookies})

            for title in titles:
                try:
                    if not title:
                        continue

                    data = {"s": title}
                    url = self.base_link
                    headers = self.headers
                    result = requests.post(url, headers=headers, data=data).text

                    if "rak wynik" in result:
                        fflog(f"Brak wyników dla {title=} ({data=})")
                        continue
                    elif "ykryto niezgodność wartości" in result:
                        fflog(f"Wykryto niezgodność wartości {title=} ({data=}) {url=}")
                        continue

                    try:
                        result = client.parseDOM(result, "div", attrs={"class": "peliculas"})[0]
                        res = client.parseDOM(result, "div", attrs={"class": "item_1 items"})[0]
                        rows = client.parseDOM(res, "div", attrs={"class": "item"})
                    except:
                        if "<title>Just a moment...</title>" in result:
                            fflog(f'strona schowana obecnie za Cloudflare')
                            return
                        fflog(f'wystąpił jakiś błąd')
                        fflog_exc()
                        continue

                    for row in rows:
                        rok = client.parseDOM(row, "span", attrs={"class": "year"})[0]
                        tytul = client.parseDOM(row, "h2")[0].replace(f" ({rok})", "").rstrip()
                        tytul = unescape(tytul)
                        tytuly = tytul.split(" / ")
                        title1 = normcmp(tytuly[0] if tytuly else tytul)
                        title2 = normcmp(tytuly[-1] if tytuly else tytul)

                        # dopasowanie: rok + którykolwiek z wariantów tytułu po normalizacji
                        if (
                            str(year) in str(rok)
                            and any(t in titles_for_compare for t in (title1, title2))
                           ):
                            url = client.parseDOM(row, "a", ret="href")[0]
                            fflog(f'pasuje {url=}')
                            return url
                except Exception:
                    fflog_exc()
                    continue
            fflog("nic nie znaleziono")
        except Exception:
            fflog_exc()
            return

    def episode(self, url, imdb, tvdb, title, premiered, season, episode):
        if not url:
            return
        cookies = cache.cache_get("cdahd_cookies", control.providercacheFile)
        cookies = cookies.get("value") if cookies else ""
        headers = self.headers
        if cookies:
            headers["Cookie"] = cookies

        result = requests.get(url, headers=headers)
        if not result:
            fflog(f'{result=}')
            return
        result = result.text

        seasons = client.parseDOM(result, "ul", attrs={"class": "episodios"})
        episodes = client.parseDOM(seasons, "a", ret="href")
        for episode_url in episodes:
            if f"sezon-{season}-odcinek-{episode}-" in episode_url:
                return episode_url
        fflog("brak pasującego odcinka")

    def sources(self, url, hostDict, hostprDict):
        sources = []
        if url is None:
            return sources
        url0 = url
        try:
            cookies = cache.cache_get("cdahd_cookies", control.providercacheFile)
            cookies = cookies.get("value") if cookies else ""
            headers = self.headers
            if cookies:
                headers["Cookie"] = cookies
                cookiesD = {x[0].strip() : x[1].strip() for x in [c.split("=") for c in cookies.strip("; ").split(";")]}

            result = requests.get(url, cookies=cookiesD, headers=headers)
            if not result:
                fflog(f'problem, bo {result=}')
                return
            try:
                result = result.text
            except:
                pass

            if "/episode/" in url:
                serial = True
                result = client.parseDOM(result, "div", attrs={"class": "player2"})
                results_player = client.parseDOM(result, "div", attrs={"class": "embed2"})
                results_player = client.parseDOM(results_player, "div")
                results_player = list(filter(None, results_player))
                results_navi = client.parseDOM(result, "div", attrs={"class": "navplayer2"})
                results_navi = client.parseDOM(results_navi, "a", attrs={"href": ""})
                results_navi = list(filter(None, results_navi))
            else:
                serial = False
                results_player = client.parseDOM(result, "div", attrs={"id": "player2"})
                results_player = client.parseDOM(results_player, "div", attrs={"class": "movieplay"})
                results_player = list(filter(None, results_player))
                results_navi = client.parseDOM(result, "div", attrs={"class": "player_nav"})
                results_navi = client.parseDOM(results_navi, "a")
                results_navi = list(filter(None, results_navi))

            if len(results_navi) != len(results_player):
                fflog(f'nie można kontynuować, bo {len(results_navi)=} != {len(results_player)=}')
                return sources

            try:
                quality = client.parseDOM(result, "span", attrs={"class": "calidad2"})[0]
            except:
                quality = ""

            i = -1
            for item in results_navi:
                try:
                    i += 1
                    lang = item
                    lang = re.sub("<[^>]+>", "", lang)
                    lang, info = self.get_lang_by_type(lang)
                    url = results_player[i]
                    try:
                        url = client.parseDOM(url, "a", ret="href")[0]
                    except:
                        try:
                            domain = client.parseDOM(url, "div", ret="domain")[0]
                            encoded_vid = client.parseDOM(url, "div", ret="id")[0]
                            decoded_vid = self.decode_id(encoded_vid)
                            url = f"https://{domain}/e/{decoded_vid}"
                        except Exception:
                            try:
                                url = client.parseDOM(url, "iframe", ret="src")[0]
                                url = url.replace("player.cda-hd.co/", "hqq.to/")
                            except Exception:
                                try:
                                    if not 'src="https://player.cda-hd.co/player/hash.php?hash=' in url:
                                        raise Exception()
                                    hash = re.search(r"hash=(\d+)", url)[1]
                                    url = f"https://hqq.to/e/{hash}"
                                except Exception:
                                    fflog(f"can't find proper url for this source  |  {url=}")
                                    continue

                    valid, host = source_utils.is_host_valid(url, hostDict)
                    # fflog(f'{host=}')

                    host = host.rsplit(".", 1)[0]

                    if "wysoka" in quality.lower() or quality == "HD":
                        qual = "1080p"
                    elif "rednia" in quality.lower():
                        qual = "SD"
                    elif "niska" in quality.lower() or quality == "CAM":
                        qual = "SD"
                        info = f"{info} | CAM"
                    else:
                        qual = "SD"
                        qual = "HD" if serial else qual

                    info2 = url0.rstrip("/").rsplit("/")
                    info2 = info2[-1]

                    sources.append({"source": host,
                                    "quality": qual,
                                    "language": lang,
                                    "url": url,
                                    "info": info,
                                    "filename": info2,
                                    "direct": False,
                                    "debridonly": False})
                except:
                    fflog_exc()
                    continue

            fflog(f'przekazano źródeł: {len(sources)}')
            return sources

        except Exception:
            fflog_exc()
            return sources

    def get_lang_by_type(self, lang_type):
        if "dubbing" in lang_type.lower():
            if "kino" in lang_type.lower():
                return "pl", "Dubbing Kino"
            return "pl", "Dubbing"
        elif "lektor pl" in lang_type.lower():
            return "pl", "Lektor"
        elif "lektor" in lang_type.lower():
            return "pl", "Lektor"
        elif "napisy pl" in lang_type.lower():
            return "pl", "Napisy"
        elif "napisy" in lang_type.lower():
            return "pl", "Napisy"
        elif "POLSKI" in lang_type.lower():
            return "pl", None
        elif "pl" in lang_type.lower():
            return "pl", None
        return "en", None

    def decode_id(self, id_hex: str) -> str:
        s1 = ''.join(chr(int(id_hex[i:i+2], 16) ^ 0x02) for i in range(0, len(id_hex), 2))
        return ''.join(format(ord(ch) ^ 0x04, 'x') for ch in s1)

    def resolve(self, url):
        return url
