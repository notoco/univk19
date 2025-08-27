import re
from lib.ff import requests
import urllib.parse
from lib.ff import cache, cleantitle, control, source_utils

from lib.ff.log_utils import fflog, fflog_exc
from lib.ff.debug import log_exception


class source:
    def __init__(self):
        self.priority = 1
        self.language = ["pl"]


    def sources(self, url, hostDict, hostprDict):
        # fflog(f'{url}')
        sources = []
        if not url:
            fflog(f'brak źródeł')
            return sources
        for u in url:
            sources.append({
                "source": u['host'],
                "quality": u['quality'].split("/ ")[-1],
                "language": "pl" if "pl" in u['lang'].lower() else "",
                "url": u['data_id'],
                "info": "lektor" if u['lang'].lower()=="pl" else "napisy" if "sub" in u['lang'].lower() else "dubbing" if "dubb" in u['lang'].lower() else "",
                "info2": u.get("title") or "",
                "direct": False,
                "debridonly": False,
                "for_resolve": {"content_type": u['content_type']},
                "premium": False,
            })
        fflog(f'przekazano źródeł: {len(sources)}')
        return sources


    def resolve(self, url, content_type=""):
        # fflog(f'{url=}')
        # fflog(f'{content_type=}')
        from ast import literal_eval

        some_data = cache.cache_get("zerion", control.providercacheFile)
        some_data = some_data["value"]
        some_data = literal_eval(some_data)

        csrf_token = some_data['csrf_token']
        if not content_type:
            content_type = some_data['content_type']

        cookies = cache.cache_value("zerion_cookie", control.providercacheFile, default="")

        session = None
        if not session:
            session = requests.Session()
            pass

        if not cookies:
            response = session.get('https://zeriun.cc')
            if not response:
                fflog(f'{response=}')
                return
            html_content = response.text
            csrf_token = re.search(r"var _csrf = '(.*?)';", html_content).group(1)
            cookies = ""

        embed_url = self.get_embed_url(session, url, csrf_token, content_type, cookies)

        # fflog(f'{embed_url=}')
        return embed_url


    def search_content(self, content_type, titles, aliases=None, year=""):
        """ szukanie elementów na podstawie podanej frazy """
        # fflog(f'{titles=} {content_type=} {year=}')
        # fflog(f'{aliases=}')
        if aliases is None:
            aliases = []

        if isinstance(titles, str):
            titles = [titles]  # dla pętli

        # query_titles = [cleantitle.normalize(cleantitle.getsearch(t)) for t in query_titles]
        titles = list(dict.fromkeys(titles))  # pozbycie się duplikatów (tylko, że wielkość liter ma znaczenie)
        # fflog(f'{titles=}')

        # Reduced Headers
        headers = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        }

        with requests.Session() as session:
            # put headers for session
            session.headers.update(headers)

            # Regular expression pattern based on content type (wynieść przed pętlę)
            if content_type == 'movie':
                pattern = re.compile(r'<div class="info">.*?<a href="(?P<link>https://zeriun\.cc/film/[^"]+)">.*?<h2 class="title">(?P<title>[^<]+)</h2>(?:.*?<h3 class="title-original">(?P<title2>[^<]+)</h3>)?', re.DOTALL)
            elif content_type == 'series':
                pattern = re.compile(r'<div class="info">.*?<a href="(?P<link>https://zeriun\.cc/serial/[^"]+)">.*?<h2 class="title">(?P<title>[^<]+)</h2>(?:.*?<h3 class="title-original">(?P<title2>[^<]+)</h3>)?', re.DOTALL)

            # all_results = []  # to chyba jednak nie będzie potrzebne
            query_titles = []
            for title in titles:
                # fflog(f'{title=}')
                if not title:
                    continue

                # encode title
                query = title
                query = cleantitle.normalize(cleantitle.getsearch(query))
                query = str.lower(urllib.parse.quote_plus(query))
                if query in query_titles:
                    fflog(f'już taki {query=} był wyszukiwany')
                    continue
                query_titles.append(query)

                # Base URL
                url = f'https://zeriun.cc/szukaj?query={query}'
                # fflog(f'{url=}')

                # Sending the request
                response = session.get(url)
                if not response:
                    fflog(f'{response=}')
                    return [], session
                html_content = response.text

                # fflog(f'{pattern.findall(html_content)=}')  # for debug
                matches = pattern.finditer(html_content)  # fishing

                # Collecting results
                results = [
                           {
                            'title': match.group('title'),
                            'title2': (titl2 := (tit2 := match.group('title2') or '').split(' / '))[0],  # może być w formacie "La chica de nieve / The Snow Girl"
                            'title3': titl2[1]  if len(titl2) > 1  else '',
                            'year': match.group('link').split('/')[-1].split('?')[0][-4:],
                            'link': match.group('link'),
                           }
                           for match in matches]
                # fflog(f'{len(results)=}  {results=}')
                # fflog(f'{(titles + aliases)=}')

                if year:
                    results = [r for r in results if r["year"]==year]
                # fflog(f'{len(results)=}  {results=}')

                # przydałaby się jeszcze jakaś weryfikacja tytułów
                # fflog( [any(t for t in [r["title"], r["title2"], r["title3"]] if t in titles + aliases) for r in results] )
                results = [r for r in results if (
                                                   any(t for t in [r["title"], r["title2"], r["title3"]] if t in titles + aliases)
                                                 )]
                # fflog(f'{len(results)=}  {results=}')
                if not results:
                    fflog(f'nic nie znaleziono (pasującego?) dla {title=}')
                    pass

                # all_results += results
                if results:
                    break  # bo jednak potrzebujemy tylko 1, ale za to konkretnego linku
                    pass

            """
            fflog(f'{len(all_results)=}  {all_results=}')
            if not all_results:
                # fflog(f'nic nie znaleziono (pasującego?)')
                pass
            """

            # potrzebne do funkcji resolve
            cookies = session.cookies
            cookies = "; ".join([str(x) + "=" + str(y) for x, y in cookies.items()])
            cache.cache_insert("zerion_cookie", cookies, control.providercacheFile)

            return results, session


    def get_video_sources(self, session, video_url):
        # Sending the request
        # fflog(f'{video_url=}')
        response = session.get(video_url)
        if not response:
            fflog(f'{response=}')
            return [], ""
        html_content = response.text
        # fflog(f'{html_content=}')

        # Extract CSRF token from HTML
        csrf_token = re.search(r"var _csrf = '(.*?)';", html_content).group(1)

        sources = []
        # Extracting lang using regular expressions
        pattern_l = re.compile(r'<table data-key="(?P<lang>[^"]+)".+?</table>', re.DOTALL)
        matches_l = pattern_l.finditer(html_content)

        # Extracting sources using regular expressions
        pattern = re.compile(r'<tr>\s*<td>(?P<host>[^<]+)</td>\s*<td>(?P<quality>[^<]+)</td>\s*<td>\s*<div class="btn no-select watch-btn" data-id="(?P<id>[^"]+)">', re.DOTALL)
        # matches = pattern.finditer(html_content)
        for m_l in matches_l:  # dla każdego języka osobno
            matches = pattern.finditer(m_l[0])
            # Collecting results
            sources += [{'lang': m_l.group("lang"), 'host': match.group('host').strip(), 'quality': match.group('quality').strip(), 'data_id': match.group('id').strip()} for match in matches]

        return sources, csrf_token


    def get_embed_url(self, session, data_id, csrf_token, content_type, cookies=""):
        if not content_type:
            fflog(f'brak {content_type=}')
            return
        # API URL
        api_url = f'https://zeriun.cc/api/{content_type}/get-embed'

        # Headers for API request
        headers = {
            'accept': '*/*',
            'accept-language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': 'https://zeriun.cc',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'x-csrf-token': csrf_token,
        }
        # cookies
        headers.update({"Cookie": cookies})
        # fflog(f'{headers=}')

        # Data payload
        data = {
            'id': data_id
        }

        # Sending the request
        # fflog(f'{api_url=}')
        # if not session:
            # session = requests.Session()
        response = session.post(api_url, headers=headers, data=data)
        if not response:
            fflog(f'{response=}')
            return
        response_json = response.json()
        # fflog(f'{response_json=}')

        # Extracting the URL
        if response_json.get('err') == False:
            if response_json['data'].get('captcha', False):
                fflog(f'{response_json=} !')
                return "captcha"
            return response_json['data']['url']
        else:
            fflog(f'{response_json=}')


    def generate_qr_code_url(self, data):
        """ nie wiem do czego to służy - tzn. co to daje? """
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?data={data}&size=200x200"
        return qr_url


    def get_sources(self, video_results, session, content_type):
        # video_sources = None
        if video_results:
            video_url = video_results[0]['link']  # czy może być sytuacja, że jest więcej pozycji niż pierwsza?
            # control.sleep(0.6 * 1000)
            # pobranie tabeli ze strony z dostępnymi źródłami (bez konkretnych adresów źródeł - te muszą być pozyskane poprzez dodatkowe api)
            fflog('sprawdzenie wykazu źródeł')
            video_sources, csrf_token = self.get_video_sources(session, video_url)
            # fflog(f'{len(video_sources)=}  {video_sources=}')

            # if csrf_token:
            cache.cache_insert("zerion", repr({"csrf_token": csrf_token, "content_type": content_type}), control.providercacheFile)
            # control.sleep(0.6 * 1000)

            # Updating sources with embed URLs or handling captcha
            # fflog('podjęcie próby "odkrycia" źródeł')
            for source in video_sources:
                source['content_type'] = content_type
                if content_type == 'series':
                    source['title'] = video_url.split('serial/')[-1].split('/s')[0]
                else:
                    source['title'] = video_url.split('/')[-1].split('?')[0]

        else:
            fflog('brak wyników')
            video_sources = None
        return video_sources


    def prepare_aliases(self, aliases, year):
        # fflog(f'{aliases=}')
        aliases1 = [
            (a.get("title") or a.get("originalname") or "")
            + " ("
            + a.get("country", "")
            + ")"
            for a in aliases
        ]
        aliases2 = [a.rpartition(" (")[0] for a in aliases1]  # country out
        aliases2 = [a.replace(year, "").replace("()", "").rstrip() for a in aliases2]  # year out
        aliases2 = [a for a in aliases2 if not source_utils.czy_litery_krzaczki(a)]  # krzaczki out
        aliases2 = [alias for i, alias in enumerate(aliases2) if alias.lower() not in [x.lower() for x in aliases2[:i]]]  # kolejne duplikaty są usuwane niezależnie od wielkości liter
        # fflog(f'{aliases2=}')
        return aliases2


    def get_originaltitle(self, aliases):
        if aliases:
            originalname = [a for a in aliases if "originalname" in a]
            originalname = originalname[0]["originalname"] if originalname else ""
            # fflog(f'{originalname=}')
            originalname = "" if source_utils.czy_litery_krzaczki(originalname) else originalname
            return originalname


    def movie(self, imdb, title, localtitle, aliases, year):
        # fflog(f'{title=} {localtitle=} {year=} {aliases=}')
        titles = [localtitle, self.get_originaltitle(aliases), title]  # może ten wariant będzie lepszy
        results, session = self.search_content('movie', titles, self.prepare_aliases(aliases, year), year)
        # fflog(f'{results=}')
        return self.get_sources(results, session, 'movie')


    def tvshow(self, imdb, tvdb, tvshowtitle, localtvshowtitle, aliases, year):
        # fflog(f'{tvshowtitle=} {localtvshowtitle=} {aliases=} {year=} {imdb=}')
        # tu można by szukać tytułu serialu, ale nie wiem, czy nie było by problemu ze zmienną session, która wskazuje na obiekt (chyba, że można potem ponownie zainicjować sesję, ale trzeba by mieć ciasteczko)
        return (tvshowtitle, localtvshowtitle, aliases), year


    def episode(self, url, imdb, tvdb, title, premiered, season, episode):
        # wpierw szukamy serialu
        localtvshowtitle = url[0][1]

        year = url[1]
        # year = ""

        tvshowtitle = url[0][0]
        aliases = url[0][2]
        originaltvshowtitle = self.get_originaltitle(aliases)
        titles = [localtvshowtitle, originaltvshowtitle, tvshowtitle]  # nie wiem, czy trzeba, bo zawsze jest chyba polski tytuł

        results, session = self.search_content('series', titles, self.prepare_aliases(aliases, year), year)  # znalezienie serialu
        # fflog(f'{results=}')
        # fflog(f'{session=}')  # object

        # teraz trzeba znaleźć sezon i odcinek
        if results:
            url = results[0]['link']
            # fflog(f'{url=}')

            video_results = []
            epNo = "s" + season.zfill(2) + "e" + episode.zfill(2)

            # control.sleep(0.6 * 1000)

            response = session.get(url)
            if not response:
                fflog(f'{response=}')
                return
            html_content = response.text

            pattern = re.compile(r'\s*href="(?P<href>[^"]+)"', re.DOTALL)
            matches = pattern.finditer(html_content)

            for match in matches:
                if epNo in match.group("href"):
                    # fflog(match.group("href"))
                    video_results = [{'link': match.group("href")}]
                    break

            # control.sleep(0.6 * 1000)

            return self.get_sources(video_results, session, 'series')
