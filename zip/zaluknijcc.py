# -*- coding: UTF-8 -*-
import re
from lib.ff.client import parseDOM
from lib.ff import source_utils, control
from lib.ff.log_utils import fflog, fflog_exc
# from lib.ff.debug import log_exception
from requests.compat import urlparse
from urllib.parse import quote_plus
from lib.ff import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class source:
    def __init__(self):
        self.priority = 1
        self.language = ["pl"]
        # self.domains = ["zaluknij.cc"]  # nie uzywane nigdzie
        self.base_link = "https://zaluknij.cc"
        self.search_link = "https://zaluknij.cc/wyszukiwarka?phrase="
        self.useragent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:141.0) Gecko/20100101 Firefox/141.0"
        self.headers2 = {
            'Referer': 'https://zaluknij.cc/',
            'user-agent': self.useragent,
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'accept-language': 'pl,en-US;q=0.7,en;q=0.3', }
        # self.headers2 = {}
        self.sess = requests.Session()


    def movie(self, imdb, title, localtitle, aliases, year):
        # fflog(f'{title=} {localtitle=} {year=}')
        return self.search(title, localtitle, year, 'movie', aliases)


    def tvshow(self, imdb, tvdb, tvshowtitle, localtvshowtitle, aliases, year):
        # fflog(f'{tvshowtitle=} {localtvshowtitle=} {year=}')
        return self.search(tvshowtitle, localtvshowtitle, year, 'tvshow', aliases)


    def episode(self, url, imdb, tvdb, title, premiered, season, episode):
        # fflog(f'{url=} {season=} {episode=}')
        return self.search_ep(url, season, episode)


    def search(self, title, localtitle, year, type_, aliases=None):
        try:
            if not title:
                return

            # przeważnie jest tylko polski tytuł, więc zamianka
            title, localtitle = localtitle, title

            title = title.lower()
            localtitle = localtitle.lower()

            if title == localtitle and aliases:
                originalname = [a for a in aliases if "originalname" in a]
                originalname = originalname[0]["originalname"] if originalname else ""
                originalname = "" if source_utils.czy_litery_krzaczki(originalname) else originalname
                if originalname:
                    title = originalname

            # pierwsze szukanie
            url = self.do_search(title, year, type_)

            # kolejne szukanie, jeśli poprzednie nie przyniosło rezultatu
            if not url and localtitle and localtitle != title:
                control.sleep(500)
                url = self.do_search(localtitle, year, type_)

            # i kolejne szukania, jeśli dalej brak wyniku
            # '.' na ':'
            if not url and "." in title:
                title1 = title.replace(".", ":")
                control.sleep(500)
                url = self.do_search(title1, year, type_)
            if not url and "." in localtitle and localtitle != title:
                localtitle1 = localtitle.replace(".", ":")
                control.sleep(500)
                url = self.do_search(localtitle1, year, type_)

            # "–" na "-"  i  '-' na ''
            if not url and any(m in title for m in ["–", "-"]):
                title1 = title.replace("–", "-").replace(" - ", " ")
                control.sleep(500)
                url = self.do_search(title1, year, type_)
            if not url and any(m in localtitle for m in ["–", "-"]) and localtitle != title:
                localtitle1 = localtitle.replace("–", "-").replace(" - ", " ")
                control.sleep(500)
                url = self.do_search(localtitle1, year, type_)

            # i kolejne szukania, jeśli dalej brak wyniku
            # '.' na ''
            if not url and "." in title:
                title1 = title.replace(".", "")
                control.sleep(500)
                url = self.do_search(title1, year, type_)
            if not url and "." in localtitle and localtitle != title:
                localtitle1 = localtitle.replace(".", "")
                control.sleep(500)
                url = self.do_search(localtitle1, year, type_)

            return url
        except Exception:
            # log_exception(1)
            fflog_exc()
            pass

    def do_search(self, title, year, type_):
        fflog(f"search_title: {title!r} {type_=}")

        if not title:
            return

        fout = []
        sout = []
        results = []
        out_url = ''
        original_title = title

        # Normalizacja spacji
        title = re.sub(r'\s+', ' ', title).strip()

        # Usuwamy TYLKO prefix na początku: "gwiezdne wojny:" lub "star wars:" (do wyszukiwarki)
        prefix_patterns = [
            r'(?i)^\s*gwiezdne\s+wojny(?:\s*[:\-–—])?\s*',
            r'(?i)^\s*star\s+wars(?:\s*[:\-–—])?\s*',
        ]
        for p in prefix_patterns:
            if re.search(p, title, flags=re.IGNORECASE):
                title = re.sub(p, '', title, count=1, flags=re.IGNORECASE)
                break

        # Sprzątanie resztek z przodu
        title = re.sub(r'^[\s:–—-]+', '', title).strip()
        if not title:
            title = original_title

        search_url = f'{self.search_link}{quote_plus(title)}'

        req = self.sess.get(search_url, headers=self.headers2, timeout=60, verify=False)
        if req.status_code != 200:
            fflog(f'otrzymano niestandardowy kod odpowiedzi z serwera: {req.status_code}')
            if req.status_code == 403:
                fflog('prawdopodobnie włączona weryfikacja cloudflare')
            return

        html = req.text

        # Lista wszystkich znalezionych bloków z wynikami
        links_blocks = []

        # --- stary układ ---
        old_layout = parseDOM(html, 'div', attrs={'id': 'advanced-search'})
        if old_layout:
            inner = old_layout[0]
            cols = parseDOM(inner, 'div', attrs={'class': r'col-sm-\d+'})
            links_blocks.extend(cols)

        # --- nowy układ ---
        new_layout = parseDOM(html, 'div', attrs={'class': r'item\s+col-sm-\d+'})
        links_blocks.extend(new_layout)


        if not links_blocks:
            if "<body" not in html:
                fflog(f'{html=}', 1)
            else:
                fflog('wystąpił jakiś problem')
            return

        # Funkcja pomocnicza do obcięcia prefixów w porównaniach
        def strip_prefix(s):
            return re.sub(r'(?i)^\s*(gwiezdne\s+wojny|star\s+wars)\s*[:\-–—]?\s*', '', s).strip()

        # --- filtrowanie po tytule i typie ---
        search_key = strip_prefix(original_title.lower())
        for link in links_blocks:
            if 'href' in link:
                href = parseDOM(link, 'a', ret='href')[0]
                tytul = parseDOM(link, 'div', attrs={'class': 'title'}) or parseDOM(link, 'a')
                if not tytul:
                    continue
                tytul = tytul[0]

                # Dopasowanie ignorujące prefixy po obu stronach
                if search_key in strip_prefix(tytul.lower()):
                    if 'serial-online' in href or 'seasons' in href:
                        sout.append({'title': tytul, 'url': href})
                    else:
                        fout.append({'title': tytul, 'url': href})

        # wybór wyników
        results = fout if type_ == 'movie' else sout
        results.sort(key=lambda k: len(k['title']), reverse=True)

        # --- filtrowanie po roku ---
        if year:
            year = int(year)
            years = [year]
            if type_ == 'movie':
                years += [year - 1, year + 1]
            if type_ == 'tvshow':
                years += [year + 1]

        date = "0"
        for url in results:
            if type_ == 'movie':
                date = str(url['url'])[-4:]
            elif type_ == 'tvshow':
                html = self.sess.get(url['url'], headers=self.headers2, timeout=60, verify=False).text
                try:
                    date_info = parseDOM(html, 'div', attrs={'class': 'info'})
                    date = (parseDOM(date_info, 'li')[-1:])[0]
                except Exception:
                    date = "0"

            if year and date.isnumeric() and int(date):
                if int(date) in years:
                    out_url = url['url']
                    break
            else:
                out_url = url['url']
                break

        return out_url



    def search_ep(self, url, season, episode):
        # fflog(f'{url=} {season=} {episode=}')
        if not url:
            return

        html = self.sess.get(url, headers=self.headers2, timeout=60, verify=False)

        if html.status_code != 200:
            fflog(f'otrzymano niestandardowy kod odpowiedzi z serwera: {html.status_code}')
            if html.status_code == 403:
                fflog(f'prawdopodobnie włączona weryfikacja cloudflare')
                # fflog(f'{req.text=}')
                return

        html = html.text

        sesres = parseDOM(html, 'ul', attrs={'id': 'episode-list'})
        if sesres:
            sesres = sesres[0]
        else:
            return

        sezony = re.findall(r'(<span>.*?</ul>)', sesres, re.DOTALL)

        episode_url = ''
        for sezon in sezony:
            sesx = parseDOM(sezon, 'span')
            ses = ''
            if sesx:
                mch = re.search(r'(\d+)', sesx[0], re.DOTALL)
                ses = mch[1] if mch else '0'
            eps = parseDOM(sezon, 'li')
            for ep in eps:
                href = parseDOM(ep, 'a', ret='href')[0]
                tyt2 = parseDOM(ep, 'a')[0]
                epis = re.findall(r's\d+e(\d+)', tyt2)[0]
                if int(ses) == int(season) and int(epis) == int(episode):
                    episode_url = href
                    break
        # fflog(f'{episode_url=}')
        return episode_url


    def sources(self, url, hostDict, hostprDict):
        # fflog(f'{url=}')
        sources = []

        if not url:
            fflog('brak źródeł do przekazania')
            return sources

        filename = ''
        if isinstance(url, tuple):
            filename = url[1]
            url = url[0]

        out = []
        # fflog(f'{url=}')
        # control.sleep(500)
        html = self.sess.get(url, headers=self.headers2, timeout=60, verify=False).text
        result = parseDOM(html, 'tbody')
        if result:
            result = result[0]
            videos = parseDOM(result, 'tr')
            for vid in videos:
                hosthrefquallang = re.findall(r'href\s*=\s*"([^"]+).*?<td>([^<]+).*?<td>([^<]+)', vid, re.DOTALL)
                for href, lang, qual in hosthrefquallang:
                    host = urlparse(href).netloc
                    out.append({'href': href, 'host': host, 'lang': lang, 'qual': qual})
            if out:
                for x in out:
                    if (link := x.get('href')):
                        host = (x.get('host') or "").rsplit(".", 1)[0].rsplit(".", 1)[-1]
                        lang = x.get('lang')
                        qual = x.get('qual').lower()
                        # fflog(f'{link=}')
                        sources.append({'source': host,
                                        'quality': '720p' if qual == 'wysoka' else 'CAM' if qual == 'niska' else 'SD',
                                        'language': 'pl',
                                        'url': link,
                                        'info': lang,
                                        'direct': False,
                                        'debridonly': False,
                                        'filename': filename,
                                        'premium': False,
                                        })
        fflog(f'przekazano źródeł: {len(sources)}')
        return sources


    def resolve(self, url):
        link = str(url).replace('\\/', '/')
        link = link.replace("//", "/").replace(":/", "://")
        fflog(f'{link=}')
        return link
