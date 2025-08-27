# -*- coding: utf-8 -*-
"""
    FanFilm Add-on
    Copyright (C) 2018 :)

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


from lib.ff import source_utils
from lib.ff import cleantitle
from lib.ff.debug import log_exception
from lib.ff.log_utils import fflog, fflog_exc

from lib.ff import requests
# czy poniższe w ogóle jest potrzebne? bo nie wiem
# import urllib3  # potrzebne, aby poniższa linijka zadziałała
# urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import re
from lib.ff.item import FFItem
from const import const

class source:

    # set in ff/sources.py
    ffitem: FFItem

    def __init__(self):
        self.priority = 1
        self.language = ["pl"]
        self.domains = ["filman.cc"]  # niewykorzystane
        self.base_link = "https://app.vodi.cc"
        self.search_link = "api/search"
        self.season_by_serie = 'api/season/by/serie'
        self.secure_key = "4F5A9C3D9A86FA54EACEDDD635185"
        self.ipc = "d506abfd-9fe2-4b71-b979-feff21bcad13" # item purchase code
        self.anime = False
        self.year = 0  # nie wiem po co to
        self.quality_allowed = ["4K", "1440p", "1080p", "1080i", "720p", "SD", "SCR", "CAM"]
        self.useragent = "Mozilla/5.0 (Linux; Android 8.0)"
        self.headers = {
                        'user-agent': self.useragent,
                        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                        'accept-language': 'pl,en-US;q=0.7,en;q=0.3',
                        'Upgrade-Insecure-Requests': '1',
                        'DNT': '1',
                        'Host': 'app.vodi.cc',
                        # "Referer": self.base_link,
                       }
        #self.sess = requests.Session()


    def movie(self, imdb, title, localtitle, aliases, year):
        # fflog(f'{title=} {localtitle=} {year=} {aliases=}')
        return self.search(title, localtitle, year, aliases)


    def tvshow(self, imdb, tvdb, tvshowtitle, localtvshowtitle, aliases, year):
        # fflog(f'{tvshowtitle=} {localtvshowtitle=} {aliases=} {year=} {imdb=}')
        # return (tvshowtitle, localtvshowtitle, aliases), year
        # powyższy sposób, choć może trochę mniej intuicyjny, pozwala wykorzystać zmienną "premiered",
        # i choć akurat w tym scraperze nie jest ona potrzebna, to w hostingach, gdzie są nazwy plików, może się przydać
        return self.search(tvshowtitle, localtvshowtitle, year, aliases, ep=True)


    def episode(self, url, imdb, tvdb, title, premiered, season, episode):
        fflog(f'{url=}')
        item = url
        self.year = int(url.get("year"))
        epNo = ""
        absoluteNumber = 0
        if const.sources.check_anime in self.ffitem.show_item.keywords:
            absoluteNumber = source_utils.absoluteNumber(tvdb, episode, season)
            fflog(f'{absoluteNumber=}')
            anime = True
            self.anime = anime
        if not epNo:
            epNo = "s" + season.zfill(2) + "e" + episode.zfill(2)
        return self.search_ep(item, epNo, absoluteNumber)


    def prepare_aliases(self, aliases, year):
        """ może się przydać do dopasowywania tytułów """
        # fflog(f'{len(aliases)}  {aliases=}')
        my_language_order = ["pl", "us", "en", "uk", "gb", "au", "it", "fr", "de" ]  # aby dać niektóre na początek
        language_order = {key: i for i, key in enumerate(my_language_order)}
        # aliases = sorted(aliases, key=lambda d:(language_order.get(d["country"], 99),) )  # bo nie zawsze pomaga, czasami jp romaji jest najlepsze
        # fflog(f'{len(aliases)}  {aliases=}')
        aliases1 = [
            (a.get("title") or a.get("originalname") or "")
            + " ("
            + a.get("country", "")
            + ")"
            for a in aliases
            # if a.get("country") in ("us", "en", "uk", "gb", "au", "pl", "jp", "original")
        ]
        # fflog(f'{len(aliases1)}  {aliases1=}')
        aliases2 = [a.rpartition(" (")[0] for a in aliases1]  # country out
        aliases2 = [a.replace(year, "").replace("()", "").rstrip() for a in aliases2]  # year out
        aliases2 = [a for a in aliases2 if not source_utils.czy_litery_krzaczki(a)]  # krzaczki out
        aliases2 = [alias for i, alias in enumerate(aliases2) if alias.lower() not in [x.lower() for x in aliases2[:i]]]  # kolejne duplikaty są usuwane niezależnie od wielkości liter
        # fflog(f'{len(aliases2)}  {aliases2=}')
        return aliases2


    def do_request(self, title, ep=False):
        # fflog(f'{title=}') if not ep else ""
        if not title:
            fflog(f'{title=}')
            return
        if not ep:
            query_link = f'{self.base_link}/{self.search_link}/{title}/{self.secure_key}/{self.ipc}'
        else:
            sid = title
            query_link = f'{self.base_link}/{self.season_by_serie}/{sid}/{self.secure_key}/{self.ipc}'
        # fflog(f'{query_link=}')
        response = requests.get(query_link, headers=self.headers, verify=False)  # zapytanie do serwera
        if not response:
            fflog(f'{response=}  {title=}')
            return
        result = {}
        try:
            result = response.json()
        except Exception as e:
            fflog(f'{response=}')
            fflog(f'{response.text=}', 0)
            if response.text.strip():
                log_exception()
        if not ep:
            result = result.get('posters')
        # fflog(f'{len(result)=}')
        # fflog(f'{len(result)=} {result=}')
        return result


    def search(self, title, localtitle, year, aliases=None, ep=False):

        # wyodrębnienie oryginalnego tytułu
        originalname = [a for a in aliases if "originalname" in a]
        originalname = originalname[0]["originalname"] if originalname else ""
        # fflog(f'{originalname=}')
        originalname = "" if source_utils.czy_litery_krzaczki(originalname) else originalname

        aliases2 = None

        titles = [localtitle, originalname]
        titles = list(filter(None, titles))  # usunięcie pustych
        titles = [t.lower() for t in titles]  # może pomóc pozbyć się duplikatów
        titles = [t.replace("&", "&amp;") for t in titles]
        titles = list(dict.fromkeys(titles))  # pozbycie się duplikatów
        # fflog(f'{titles=}')

        titles_r = []

        for title in titles:

            if len(titles_r) > 9:
                fflog(f'wyczerpano limit zapytań do serwera')
                break

            # stworzyć z tego funkcję, aby to samo wykorzystać przy serialach
            title_r = title.replace("#", "").replace("/", "／")
            # hash można też zamieniać na %23

            # title_r = title_r.replace("?", "%3F")  # ale czasami nie wstawiają znaku zapytania do tytułu, więc może szukać 2 wersji?
            # title_r = title_r.replace("%3F", "")
            # ewentualnie szukać to co jest przed znakiem zapytania

            title_r = title_r.partition("?")[0].rstrip()  # szukanie przed znakiem zapytania

            # title_r = title_r.replace("–", "-")  # na "Rebel Moon - Część 2", ale psuje "Bagażnik – uwięziona"
            # więc fix na powyższe
            if "–" in title_r:
                title_r_n = title_r.replace("–", "-")
                if title_r_n not in titles:
                    titles += [title_r_n]

            # są też tytuły, które " - " mają zapisane jako ":" np. "Trunk - Locked In" zapisane jako "Trunk: Locked In"
            if " - " in title_r and ": " not in title_r:
                title_r_n = title_r.replace(" - ", ": ")
                if title_r_n not in titles:
                    titles += [title_r_n]

            title_r = title_r.replace("'", "''").rstrip(".")  # to na końcu zmian musi być
            # fflog(f'{title_r=}')

            if len(title_r) < 2:
                fflog(f'za krótkie zapytanie do wyszukiwarki  {title_r=}')
                continue

            if title_r in titles_r:  # na wszelki wypadek, jakby po przekształceniach okazało się, że już takie powstało wcześniej
                fflog(f'zapytanie {title_r=} już było wysyłane')
                continue

            titles_r.append(title_r)
            fflog(f'wysłanie zapytania {title_r=}')
            result = self.do_request(title_r)  # zapytanie do serwera

            if result:
                return self.find_item({'title': title, 'url': result, 'year': year, 'quality': None, 'is_ep': ep})

            if len(titles) > 1 and len(titles[1]) < 3:  # to chyba dla krótkich tytułów
                break  # do przemyślenia
                pass

            if ( title == titles[-1]  # ostatni
                 and not aliases2
            ):
                aliases2 = self.prepare_aliases(aliases, year)
                i = 1
                for a in aliases2:
                    if a not in titles:
                        titles += [a]  # dodanie
                        if i >= 4:  # ograniczenie
                            break
                        i += 1
                # fflog(f'{i=} {len(titles)=}  {titles=}')

        if not result:
            fflog('brak wyników')


    def find_item(self, url):

        is_ep = url["is_ep"]

        year = int(url['year'])
        years = [year]
        if True:  # można dorobić przełącznik
            years += [year-1]
        # jeszcze korekty dla niektórych seriali (z powodu błędu w bazie Filmana)
        title = url["title"]
        if "gra o tron" in title or "game of thrones" in title:
            years += [2015]
        elif "mr. robot" in title:
            years += [2018]

        wanted = url['title']  # tytuł jaki był szukany
        wanted = wanted.lower().replace("–", "-")
        #wanted = cleantitle.normalize(wanted)
        wanted = cleantitle.getsearch(wanted, preserve="/").replace(".", "")  # poluzowanie dopasowania

        result = url['url']
        for item in result:
            # fflog(f'{item=}')

            if not is_ep and item.get("type") != "movie":
                continue

            found = item['title']  # tytuł znaleziony
            found = found.lower().replace("–", "-")
            #found = cleantitle.normalize(found)
            found = cleantitle.getsearch(found, preserve="/").replace(".", "")  # poluzowanie dopasowania

            # fflog(f"{item['year']=}  ({years=}) \n{wanted=} \n {found=}")
            if (
                    int(item['year']) in years
                and re.search(f'( / |^){re.escape(wanted)}( / |$)', found)
            ):
                fflog(f"pasuje  {item['title']=}  {item['year']=}")  # pasująca pozycja
                # fflog(f"pasuje, bo  {item['year']=}  ({years=}) \n{wanted=} \n {found=}")
                return item
            else:
                # fflog(f"nie pasuje, bo  {item['year']=}  ({years=}) \n{wanted=} \n {found=}")
                pass
        fflog(f'nic nie dopasowano')
        # fflog(f'{url=}')


    def search_ep(self, item, epNo, absoluteNumber=0):
        # fflog(f'{len(item)=}  {item=}')

        # źródła są już w odpowiedzi, ale może mogą być po więcej niż 1 źródło na odcinek ? - dlatego kolejne zapytanie do serwera
        results_ep = self.do_request(item["id"], ep=True)  # zapytanie do serwera o odcinki
        # fflog(f'{len(results_ep)=}  {results_ep=}')
        season = int(epNo.split('s')[1].split('e')[0]) - 1
        episode = int(epNo.split('s')[1].split('e')[1]) - 1
        # fflog(f'{season=}')
        # fflog(f'{len(results_ep)=}')
        if not results_ep or season < 0:
            fflog(f'brak danych')
            return
        if self.anime and len(results_ep) == 1 and season and season >= len(results_ep):
            fflog(f'próba spłaszczenia sezonów')
            season = 0
            episode = absoluteNumber - 1 if absoluteNumber else episode
            fflog(f'(numer odcinka: {episode+1})')
        if season >= len(results_ep) or not results_ep[season]:
            return
        else:
            # fflog(f'{results_ep[season]=}')
            ep = results_ep[season].get('episodes')
            # fflog(f'{len(ep)=}')
            if episode >= len(ep):
                return

            sources = []
            ep = ep[episode]
            description = ep.get('description')
            # fflog(f'{description=}')
            prop_quality = "HD" if description is None else "SD"  # nie wiem, czy to prawidłowość na dłuższą metę
            # fflog(f"{ep['sources']=}")
            for srcs in ep['sources']:
                quality = None
                quality = srcs['quality'] or (srcs['title'] if srcs['title'] in self.quality_allowed else None) or prop_quality
                sources.append({
                    'url': srcs['url'],
                    'quality': quality or srcs['quality'],
                    'title': srcs['title'],
                    'size': srcs['size'],
                    'filename': item['title'] + f" {epNo}",
                    'type': srcs.get('type'),
                    "premium": False,
                    })
            return {'url': sources, 'is_ep': True }


    def sources(self, url, hostDict, hostprDict):
        # fflog(f'{url}')
        try:
            sources = []

            if not url or not url.get('url') and not url.get('sources'):
                # fflog('{url=}')
                return sources

            data = []

            if url.get('is_ep'):  # odcinek
                for u in url['url']:
                    data.append({
                        #'quality': u['quality'] or 'SD',  # choć często są HD na nawet FullHD, tylko starsze mogą być SD
                        'quality': u['quality'] or (u['title'] if u['title'] in self.quality_allowed else None) or "SD",
                        'lang': 'pl',
                        'link': u['url'],
                        'info': '',
                        'size': u['size'] or '',
                        'filename': u.get('filename', ''),
                        'type': u.get('type'),
                    })
            else:  # film
                item = url
                for u in item['sources']:  # wyciąganie źródeł

                    link = u['url']
                    # fflog(f"{link=}")

                    quality = u['quality'] or (u['title'] if u['title'] in self.quality_allowed else None) or "SD"
                    # fflog(f'{quality=}')
                    if quality == "SD":
                        sublabel = item['sublabel']
                        # fflog(f'{sublabel=}')
                        # doświadczalnie dobierałem
                        if sublabel == "HD":
                            quality = "1080p"
                        elif sublabel == "Wysoka":
                            quality = "720p"
                        elif sublabel == "Niska":
                            quality = "CAM"

                    filename = f"{item['title']}"
                    # filename += f"({item['year']})"

                    data.append({
                        #'quality': item['sublabel'],
                        'quality': quality,
                        'lang': self.get_lang_by_type(item['label'])[0],
                        'info': item['label'],
                        'link': link,
                        'size': u.get('size') or '',
                        'filename': filename,
                        'type': u.get('type'),
                    })


            #filename_in_2nd_line = control.setting("sources.filename_in_2nd_line") == "true"

            for d in data:
                """
                if self.get_hosting(d['link']) == "vidguard":  # ta domena nie została przedłużona 8.11.2024
                    continue
                    pass
                """
                if self.get_hosting(d['link']) == "filesilver":  # dla tej domeny nie potwierdzili adresu email 24.11.2024
                    continue
                    pass

                info = d['info'] if d['info'].lower() != d['lang'].lower() else ''

                ext = d.get("type")
                filename = d.get("filename", "")
                # if filename_in_2nd_line:
                filename += f'.{ext}' if ext else ""

                if ext:
                    if ( ext not in filename
                    ):
                        # if d.get('type') == "mp4":
                        info += f" | ({ext})"
                        pass

                sources.append(
                    {
                        #"source": 'Filman',
                        "source": self.get_hosting(d['link']),
                        # "source": '',
                        "quality": d['quality'],
                        "language": d['lang'],
                        "url": d['link'],
                        "info": info,
                        "filename": filename,
                        "direct": True,
                        "debridonly": False,
                        "size": d.get("size", ""),
                        "premium": False,
                    }
                )

            fflog(f'przekazano źródeł: {len(sources)}')
            return sources

        except Exception as e:
            if str(e):
                fflog(f'Error: {e}')
                pass
            fflog_exc()
            #log_exception()
            return sources


    def get_lang_by_type(self, lang_type):
        """ ciekawe, czy są tu jakieś specyficzne oznaczenia
            bo jeśli nie, to może wykorzystać funkcję z source_utils """
        # fflog(f'{lang_type=}')
        if "dubbing" in lang_type.lower():
            if "kino" in lang_type.lower():
                return "pl", "Dubbing Kino"
            return "pl", "Dubbing"
        elif "napisy pl" in lang_type.lower():
            return "pl", "Napisy"
        elif "napisy" in lang_type.lower():
            return "pl", "Napisy"
        elif "lektor pl" in lang_type.lower():
            return "pl", "Lektor"
        elif "lektor" in lang_type.lower():
            return "pl", "Lektor"
        elif "POLSKI" in lang_type.lower():
            return "pl", None
        elif "pl" in lang_type.lower():
            return "pl", None
        return "en", None


    def get_hosting(self, url):
        hosting = re.search(r"^https?://(\w+\.)*(\w+)(\.\w+)/", url)  # wzór tylko dla schematu stosowanego przez filmana
        # fflog(f'{hosting[2]}')
        return hosting[2]

    def resolve(self, url):
        link = str(url).replace(r'\/', '/')
        # fflog(f'{link=}')
        link += '|User-Agent=KODI' if link else ""
        return str(link)
