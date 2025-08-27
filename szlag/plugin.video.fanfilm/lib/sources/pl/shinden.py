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

from datetime import datetime
from urllib.parse import quote_plus
# from html import unescape
import re
from lib.ff import requests

from lib.ff import cleantitle, client, control, source_utils
from lib.ff.log_utils import fflog, fflog_exc
from lib.ff.settings import settings
from lib.ff.item import FFItem
from const import const


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3578.75 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl,en-US;q=0.7,en;q=0.3",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
    "TE": "Trailers",
}


class source:

    # set in ff/sources.py
    ffitem: FFItem

    def __init__(self):
        self.priority = 1
        self.language = ["pl"]
        self.domains = ["shinden.pl"]

        self.base_link = "https://shinden.pl"
        self.search_link = "https://shinden.pl/series?search=%s"
        self.user_name = settings.getString("shinden.username")
        self.user_pass = settings.getString("shinden.password")
        self.session = requests.Session()
        self.cookies = ""


    def levenshtein_distance(self, s1, s2):
        if len(s1) > len(s2):
            s1, s2 = s2, s1

        distances = range(len(s1) + 1)
        for index2, char2 in enumerate(s2):
            new_distances = [index2 + 1]
            for index1, char1 in enumerate(s1):
                if char1 == char2:
                    new_distances.append(distances[index1])
                else:
                    new_distances.append(
                        1
                        + min(
                            (
                                distances[index1],
                                distances[index1 + 1],
                                new_distances[-1],
                            )
                        )
                    )
            distances = new_distances

        return distances[-1]


    def contains_word(self, str_to_check, word, max_distance=2):
        words_in_str = str_to_check.split()
        for w in words_in_str:
            if self.levenshtein_distance(w, word) <= max_distance:
                return True
        return False


    def contains_all_words(self, str_to_check, words, allowed_missing=0, max_distance=2):
        missing_count = 0
        for word in words:
            if not self.contains_word(str_to_check, word, max_distance):
                missing_count += 1
                # Check the length of the words list
                if len(words) > 2 and missing_count > allowed_missing:
                    return False
                elif len(words) <= 2:
                    return False
        return True


    def movie(self, imdb, title, localtitle, aliases, year):
        premiered = self.ffitem.vtag.getPremieredAsW3C()
        # fflog(f'szukanie filmu {title=} {localtitle=} {imdb=} {year=} {premiered=} {aliases=}', 1)
        if const.sources.check_anime not in self.ffitem.keywords:
            fflog('Szukany film nie jest anime - wyszukiwanie pominięte')
            return
        return self.search_ep_or_movie((title, localtitle), None, None, None, year, premiered, aliases)


    def tvshow(self, imdb, tvdb, tvshowtitle, localtvshowtitle, aliases, year):
        # fflog(f'szukanie serialu {tvshowtitle=} {localtvshowtitle=} {year=} {imdb=} {tvdb=}')
        return (tvshowtitle, localtvshowtitle), year, aliases


    def episode(self, url, imdb, tmdb, title, premiered, season, episode):
        premiered = self.ffitem.vtag.getFirstAiredAsW3C()
        # fflog(f'szukanie odcinka {url=} {imdb=} {season=} {episode=} {premiered=} {title=}')
        if self.ffitem.show_item is None:  # dla odcinka serial musi być, więc sprawdzenie „na zaś”
            return None
        if const.sources.check_anime in self.ffitem.show_item.keywords:
            return self.search_ep_or_movie(url[0], season, episode, tmdb, url[1], premiered, url[2])
        fflog('Szukany serial nie jest anime - wyszukiwanie pominięte')
        return None


    def get_normalized_title(self, title):
        return cleantitle.normalize(title)


    def get_originaltitle(self, aliases):
        """ wyłuskuje oryginalny tytuł z aliasów """
        if aliases:
            originalname = [a for a in aliases if "originalname" in a]
            originalname = originalname[0]["originalname"] if originalname else ""
            # fflog(f'{originalname=}')
            # originalname = "" if source_utils.czy_litery_krzaczki(originalname) else originalname  # odrzuca, gdy tytuł oryginalny nie jest zapisany literami łacińskimi
            return originalname


    def prepared_titles(self, titles, aliases):
        # Extract Japanese titles from the aliases list
        jp_titles_from_aliases = [alias["title"] for alias in aliases if alias["country"] == "jp"]
        # fflog(f'{jp_titles_from_aliases=}')

        # Concatenate them with the original titles
        # combined_titles = jp_titles_from_aliases + list(titles)
        combined_titles = list(titles) + jp_titles_from_aliases + [self.get_originaltitle(aliases)]
        # fflog(f'{combined_titles=}')

        # cleaning
        combined_titles = list(filter(None, combined_titles))  # usunięcie pustych
        combined_titles = [t.lower() for t in combined_titles]  # może pomóc pozbyć się duplikatów
        combined_titles = list(dict.fromkeys(combined_titles))  # pozbycie się duplikatów

        return combined_titles


    def get_search_results(self, titles, headers, aliases, episode):
        # fflog(f'{titles=}')
        # fflog(f'{aliases=}')
        results = []

        combined_titles = self.prepared_titles(titles, aliases)
        fflog(f'{combined_titles=}')

        page = 1
        for title in combined_titles:

            if isinstance(title, str):
                normalized_title = self.get_normalized_title(title)
                search_title = normalized_title.replace(" ", "+").replace("shippuden", "shippuuden")

                filtr = ""
                # filtr += "&type=equals"  # mało to daje
                if episode:
                    filtr += "&series_type[0]=TV&series_type[1]=ONA&series_type[2]=OVA"
                else:
                    filtr += "&series_type[0]=Movie"
                    # filtr += "&series_number[0]=only_1"  # nie wiem, czy jest sens
                    # filtr += "&series_length[0]=over_48"
                filtr += "&series_status[0]=Currently+Airing&series_status[1]=Finished+Airing&one_online=true"

                filtr = quote_plus(filtr, "&=")
                # fflog(f' {search_title=}')
                adres = self.search_link % search_title + filtr
            else:
                adres = title[0]  # jak z rekurencji

            # fflog(f'{adres=}')
            r = self.session.get(adres, headers=headers)
            if not r:
                fflog(f'błąd {r=}')
                control.sleep(200)
                continue
            else:
                r = r.text

            res = client.parseDOM(r, "li", attrs={"class": "desc-col"})
            # fflog(f' {len(res)=}')
            res = [rs for rs in res if rs.startswith("<h3>")]
            # fflog(f' {len(res)=}')
            for rs in res:
                if rs not in results:
                    results.append(rs)
                else:
                    # fflog(f'taki tytuł już zarejestrowano')
                    pass
            if page < 2:  # ograniczenie
                link_next = client.parseDOM(r, "li", attrs={"class": "pagination-next"})
                if link_next:
                    # fflog(f'{link_next=}')
                    link_next = link_next[0]
                    # fflog(f'{link_next=}')
                    link_next = client.parseDOM(link_next, "a", ret="href")
                    if link_next:
                        # link_next = unescape(link_next[0])
                        # fflog(f'{link_next=}')
                        # link_next = re.sub(r"\&r\d+?=\d", "", link_next)  # jakieś r307=1 dokleja, chyba, gdy nie ma aktywnego JS
                        # fflog(f'{link_next=}')
                        link_next = adres.replace(f"&page={page}", "")
                        page += 1
                        link_next += f"&page={page}"
                        # fflog(f'{link_next=}')
                        combined_titles.append([link_next])

        # fflog(f'{len(results)=}  {results=}')
        # fflog(f'{len(results)=}')
        return results


    def search_ep_or_movie(self, titles, season, episode, tmdb, year, premiered, aliases, tvdb=0):
        # fflog(f'{titles=} {season=} {episode=} {tmdb=} {year=} {premiered=} {aliases=}')
        try:
            # fflog(f'{premiered=}')
            if not premiered:
                fflog(f'brak daty premiery - rozpoznanie właściwego odcinka nie będzie możliwe')
                return
            data_premiered = None
            try:
                data_premiered = datetime.strptime(premiered, "%Y-%m-%d").date()
            except Exception:
                try:
                    data_premiered = datetime.strptime(premiered, "%d.%m.%Y").date()
                except Exception:
                    fflog(f'błąd przy parsowaniu daty premiery  {premiered=}')
                    fflog_exc()
                    return

            cookies = client.request("https://shinden.pl/", output="cookie")
            if not cookies:
                # fflog(f'{cookies=}')
                pass

            if self.user_name and self.user_pass:  # Logowanie
                headers = {
                    "authority": "shinden.pl",
                    "cache-control": "max-age=0",
                    "origin": "https://shinden.pl",
                    "upgrade-insecure-requests": "1",
                    "dnt": "1",
                    "content-type": "application/x-www-form-urlencoded",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/73.0.3683.27 Safari/537.36",
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3",
                    "referer": "https://shinden.pl/",
                    "accept-encoding": "gzip, deflate, br",
                    "accept-language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
                }
                headers.update({"Cookie": cookies})
                data = {
                        "username": self.user_name,
                        "password": self.user_pass,
                        "login": "",
                }

                cookie = requests.post("https://shinden.pl/main/0/login", headers=headers, data=data)
                if not cookie:
                    # fflog(f'{cookie=}')
                    pass

                kuki = cookie.cookies.items()
                self.cookies = "; ".join([str(x) + "=" + str(y) for x, y in kuki])
                if not cookie:
                    self.cookies = cookies

            HEADERS["Cookie"] = self.cookies

            if season is not None:
                total_episodes, absolute_number = 0, 0
                if tmdb:
                    total_episodes, absolute_number = source_utils.get_absolute_number_tmdb(tmdb, season, episode)
                    # fflog(f'{total_episodes=} {absolute_number=} {season=} {episode=} {tmdb=}')
                    fflog(f'{absolute_number=}  {total_episodes=} (TMDB)')
                elif tvdb:
                    absolute_number = source_utils.absoluteNumber(tvdb, episode, season)
                    total_episodes = 0  # nie wiem, co przyjąć, ale to chyba nie będzie już potrzebne, bo i tak nie zawsze pokrywa się to z tym, co na stronie (szczególnie dla kręconych jeszcze odcinków)
                    fflog(f'{absolute_number=}  (TVDb)')
                else:
                    fflog(f'nie można określić bezwględnego numeru odcinka, bo brak identyfikatorów {tmdb=} {tvdb=}')
                    return
            else:
                total_episodes, absolute_number = 1, 1

            # zapytanie do serwera o tytuły
            results = self.get_search_results(titles, HEADERS, aliases, episode)

            # if season is None:
            #     if results:
            #         self.meta = self.get_meta()
            #         fflog(f'{self.meta.get("duration")=}')
            #         duration = self.meta.get("duration") or 0
            #         self.duration = int( int(duration) / 60)
            #         pass

            combined_titles = self.prepared_titles(titles, aliases)
            # fflog(f'{combined_titles=}')

            pasujace_wyniki = []
            for result in results:
                if not result.startswith("<h3>"):  # h3 to nagłówek tabeli chyba zawsze
                    # fflog(f'skip because result not start with <h3>')
                    continue

                try:
                    link, tytul = self.process_result_row(result)
                except Exception:
                    # fflog('error for "process_result_row"')
                    fflog_exc()
                    continue

                if not link or not tytul:
                    fflog('not link or not tytul')
                    continue

                for combined_title in combined_titles:

                    # fflog(f'{combined_title=}')  # to jest podpętla tylko
                    normalized_title = self.get_normalized_title(combined_title)
                    words = normalized_title.split(" ")
                    if self.contains_all_words(tytul, words, allowed_missing=1):  # słabo to działa, szczególnie dla krótkich, jednowyrazowych tytułów
                        fflog(f'{link=}')
                        if link in pasujace_wyniki:
                            # fflog('ten link był już sprawdzany')
                            continue
                        pasujace_wyniki.append(link)
                        episode_link = self.get_episode_link(
                            link,
                            data_premiered,  # po tym sprawdza
                            HEADERS,
                            total_episodes,
                            absolute_number,
                        )
                        if episode_link:
                            # fflog(f'{episode_link=}')
                            return episode_link
                        else:
                            # fflog(f'problem z odcinkiem')
                            pass
                            # return

            fflog(f'nic nie znaleziono (pasującego)')

        except Exception as e:
            fflog_exc()
            print(e)
            return


    def process_result_row(self, result):
        link = next(
            (
                item
                for item in client.parseDOM(result, "a", ret="href")
                if item.startswith(("/titles", "/series"))
            ),
            None,
        )
        # fflog(f'{link=}')
        tytul_matches = re.findall(r"<a href.*?>(.*?)</a>", result)

        if not tytul_matches:
            fflog(f'not tytul_matches')
            return None, None

        tytul = tytul_matches[0].replace("<em>", "").replace("</em>", "")
        # fflog(f'{tytul=}')
        return link, self.get_normalized_title(tytul)


    def get_episode_link(self, link, data_premiered, headers, total_episodes, absolute_number):
        try:
            full_link = self.base_link + link + "/all-episodes"
            result = self.session.get(full_link, headers=headers)  # odpytanie serwera
            if not result:
                fflog(f'błąd {result=}')
                return
            else:
                result = result.text
            episodes = client.parseDOM(
                result, "tbody", attrs={"class": "list-episode-checkboxes"}
            )
            episodes = client.parseDOM(episodes, "tr")
            # fflog(f'{len(episodes)=}')
            aired_date_exception = False
            znaleziony = False
            # opcja_porownywania_numerow_odcinkow = False
            # opcja_porownywania_numerow_odcinkow = True if len(episodes) == total_episodes else False  # tylko, że te total_episodes to nie zawsze się zgadzają z tym, co na stronie jest
            # opcja_porownywania_numerow_odcinkow = True  # a co jak numery nie będą się pokrywać? To może wówczas lepiej daty emisji jednak sprawdzać
            # fflog(f'{opcja_porownywania_numerow_odcinkow=}')
            for episode in episodes:
                try:
                    try:
                        odc = client.parseDOM(episode, "td")[0]
                    except Exception:
                        odc = ""
                    # fflog(f'{odc=}')
                    aired_date = client.parseDOM(episode, "td")[4]
                    # fflog(f'{aired_date=}')
                    if not aired_date:
                        # fflog(f'brakuje informacji o dacie emisji na stronie dla {odc=}')
                        if str(absolute_number) == odc:
                            pass
                            # continue  # jak nie chcę ryzykować
                            # fflog(f'ale numery odcinków pasują, więc ryzykujemy, że to pasujący  {odc=} == {absolute_number=}')
                            # znaleziony = True
                        else:
                            continue
                            pass
                    if not znaleziony:
                        aired_date = datetime.strptime(aired_date, "%Y-%m-%d").date()
                        # fflog(f'{aired_date=}')
                        difference = abs((aired_date - data_premiered).days)
                        # fflog(f'{difference=}  {aired_date=}  {data_premiered=}')
                        if difference <= 2:
                            znaleziony = True
                            fflog(f'{odc=}')
                        elif total_episodes == 1:
                            raise Exception()

                    if znaleziony:
                        link = (
                            self.base_link
                            + client.parseDOM(episode, "a", ret="href")[0]
                        )
                        # fflog(f'{link=}')
                        return link
                except Exception:
                    aired_date_exception = True
                    # fflog(f'{aired_date_exception=}')
                    # fflog(f'{odc=}')
                    continue

            if aired_date_exception:
                if total_episodes == 1:  # film
                    duration_match = re.search(
                        r"Długość odcinka:<\/dt>.*?(\d{1,3})\s?min<\/dd>",
                        result,
                        re.M | re.S | re.I,
                    )
                    # fflog(f'{duration_match=}')
                    if duration_match:
                        # fflog(f'{duration_match[1]=}')
                        pass

                start_date_match = re.search(
                    r"Data emisji:<\/dt>.*?(\d{2}\.\d{2}\.\d{4})<\/dd>",
                    result,
                    re.M | re.S | re.I,
                )
                end_date_match = re.search(
                    r"Koniec emisji:<\/dt>.*?(\d{2}\.\d{2}\.\d{4})<\/dd>",
                    result,
                    re.M | re.S | re.I,
                )
                # fflog(f'{start_date_match=}  {end_date_match=}')
                if start_date_match:  # and end_date_match:
                    start_date_match = datetime.strptime(start_date_match.group(1), "%d.%m.%Y").date()
                    if end_date_match:
                        end_date_match = datetime.strptime(end_date_match.group(1), "%d.%m.%Y").date()
                    else:
                        if absolute_number == 1:
                            end_date_match = start_date_match

                    # fflog(f'{start_date_match=}  {end_date_match=}  {data_premiered=}')
                    if (start_date_match and end_date_match
                        and data_premiered >= start_date_match
                        and data_premiered <= end_date_match
                        # and len(episodes) == total_episodes
                    ):
                        # fflog(f"daty sie zgadzają.")
                        for episode in episodes:
                            if client.parseDOM(episode, "td")[0] == str(absolute_number):
                                # fflog(f'{absolute_number=}')
                                lnk = client.parseDOM(episode, "a", ret="href")
                                if lnk:
                                    return self.base_link + lnk[0]
                                else:
                                    fflog(f'brak źródeł dla tego odcinka')
                                    return
                        """
                        return (
                            self.base_link
                            + [
                                x
                                for x in client.parseDOM(episodes, "a", ret="href")
                                if "view" in x
                            ][len(episodes) - absolute_number]
                        )
                        """
                    else:
                        fflog(f"daty lub numery odcinków NIE zgadzają się")
                        # fflog(f"{start_date_match=}  {end_date_match=}  {len(episodes)=}  {total_episodes=}  {absolute_number=}")
                        pass
                else:
                    fflog(f'nie dopasowano zadanej daty premiery z datą podaną na stronie')
                    pass
            else:
                # fflog(f'brak szukanego odcinka na tej podstronie')
                pass
            return None
        except Exception as e:
            fflog_exc()
            print(e)
            return


    def sources(self, url, hostDict, hostprDict):
        # fflog(f'{url=}')
        if not url:
            return
        sources = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/71.0.3578.75 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pl,en-US;q=0.7,en;q=0.3",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "TE": "Trailers",
            "Cookie": self.cookies,
        }

        try:
            content = requests.get(url, headers=headers)
            if not content:
                fflog(f'błąd {content=}')
                return
            else:
                content = content.text

            results = client.parseDOM(content, "section", attrs={"class": "box episode-player-list"})
            results = client.parseDOM(results, "tr")

            for item in results:
                try:
                    # fflog(f'{item=}')
                    item_elems = client.parseDOM(item, "td")
                    if not item_elems:
                        continue
                    # fflog(f'{item_elems=}')

                    host = "VIDOZA" if "vidoza" in item_elems[0].lower() else item_elems[0]

                    quality = source_utils.check_sd_url(item_elems[1])

                    audio = client.parseDOM(item_elems[2], "span", attrs={"class": "mobile-hidden"})[0]

                    jezyk = "pl" if "Polski" in audio else ""

                    napisy = (
                        client.parseDOM(
                            item_elems[3], "span", attrs={"class": "mobile-hidden"}
                        )[0]
                        if jezyk == ""
                        else ""
                    )
                    # fflog(f'{napisy=}')
                    info = (
                        "Polskie Audio"
                        if "Polski" in audio
                        else (napisy + "e" + " Napisy" if napisy and "--" not in napisy else "")
                    )
                    if "aszynowy" in info:
                        # info += " (AI)"
                        pass
                    if "olski" in info:
                        jezyk = "pl"
                        info = "napisy" if "apisy" in info else ""
                    # info = f"({info})" if info else ""

                    vid_id = re.findall('''data_(.*?)\"''', str(item_elems[5]))[0]
                    code = re.findall(r"""_Storage\.basic.*=.*'(.*?)'""", content)[0]
                    video_link = f"https://api4.shinden.pl/xhr/{vid_id}/player_load?auth={code}"

                    filename = client.parseDOM(item_elems[-1], "form", ret="action")[0]
                    filename = filename.split("/report-player/")[0].strip("/")
                    filename = filename.partition("-")[-1]

                    source_data = {
                        "source": host,
                        "quality": quality,
                        "language": jezyk,
                        "url": video_link,
                        "info": info,
                        "filename": filename,
                        "direct": False,
                        "debridonly": False,
                        "premium": False,
                    }
                    sources.append(source_data)
                except Exception as e:
                    fflog_exc()
                    print(str(e))

            fflog(f'przekazano źródeł: {len(sources)}')
            return sources

        except Exception as e:
            fflog_exc()
            print(str(e))
            return sources


    def resolve(self, url):
        # fflog(f'{url=}')
        # import time
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:63.0) Gecko/20100101 Firefox/63.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pl,en-US;q=0.7,en;q=0.3",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
            "TE": "Trailers",
        }
        if str(url).startswith("//"):
            url = "http://" + url
        cookies = client.request(url, headers=headers, output="cookie")
        headers.update({"Cookie": cookies})
        # time.sleep(5)
        control.sleep(5000)  # na stronie też jest timer na 5 sekund
        video = client.request(url.replace("player_load", "player_show") + "&width=508", headers=headers)
        try:
            video = client.parseDOM(video, "iframe", ret="src")[0]
        except Exception:
            video = client.parseDOM(video, "a", ret="href")[0]
        if str(video).startswith("//"):
            video = "https:" + video
        # fflog(f'{video=}')
        return str(video)
