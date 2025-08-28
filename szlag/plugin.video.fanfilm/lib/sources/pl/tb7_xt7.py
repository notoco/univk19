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
import threading
import time
import sys
import json
from ast import literal_eval
from html import unescape
from urllib.parse import unquote, quote
from difflib import SequenceMatcher
import xbmcgui
from lib.sources import SourceModule, Source

from lib.ff import requests
import urllib3

from lib.ff import (
    cache,
    cleantitle,
    client,
    control,
    source_utils,
)
from lib.ff.settings import settings
from lib.ff.log_utils import fflog, fflog_exc
from const import const
if TYPE_CHECKING:
    from lib.ff.item import FFItem

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class _source:
    """Base scraper for sites like tb7, xt7"""

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
        self.VIDEO_EXTENSIONS = ("avi", "mkv", "mp4", "mpg", "mov", ".ts", "mts", "2ts")  # trzymać 3 znaki długości dla każdego elementu ("2ts" to od "m2ts")
        self.lock = threading.Lock()
        self.raw_results = []
        self.results = []
        self.titles = []
        self.titles_requested = []
        self.pages = []
        # self.tit_val_filt_for_one_title = None
        self.dodatkowy_filtr = None
        self.dodatkowy_filtr2 = None
        self.domains = [f"{self.PROVIDER}.pl"]
        self.base_link = f"{self.URL}/"
        self.login_link = "login"
        self.mylibrary_link = "mojekonto/pliki"
        self.mynotepad_link = "mojekonto/notes"
        """
        if control.settings.getBool(f"{self.PROVIDER}.fullsearch"):
            self.search_link = "mojekonto/szukaj"
            self.support_search_link = "mojekonto/szukaj/{}"  # do paginacji wyników
        else:
            self.search_link = "mojekonto/szukajka"
            self.support_search_link = "mojekonto/szukajka/{}"  # do paginacji wyników
            """
        self.search_link = "mojekonto/szukaj"
        self.support_search_link = "mojekonto/szukaj/{}"  # do paginacji wyników

        self.session = requests.Session()
        self.user_name = settings.getString(f"{self.PROVIDER}.username")
        self.user_pass = settings.getString(f"{self.PROVIDER}.password")
        self.headers = {
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36+SOSNF-CS20.10.5/200R0CVLCI-2BDE4C4A6B67444C",
            "DNT": "1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
        }


    def movie(self, imdb, title, localtitle, aliases, year):
        fflog('szukanie żródeł filmu', 0)
        self.results = []
        return self.search(title, localtitle, year, aliases=aliases)

    def tvshow(self, imdb, tvdb, tvshowtitle, localtvshowtitle, aliases, year):
        """ jakaś proteza pomocnicza przed szukaniem odcinka """
        self.results = []
        return (tvshowtitle, localtvshowtitle, aliases), year

    def episode(self, url, imdb, tvdb, title, premiered, season, episode):
        self.results = []
        epNo = ""
        if not epNo:
            epNo = f"s{season.zfill(2)}e{episode.zfill(2)}"
        return self.search(url[0][0], url[0][1], year=url[1], episode=epNo, aliases=url[0][2], premiered=premiered)

    def search(self, title, localtitle, year="", episode="", aliases=None, premiered=""):
        if not title:
            fflog(f'Błąd - szukanie niemożliwe, bo {title=}')
            return

        self._fetch_remaining_limit()
        self.remaining_limit_mb = 0
        results = []

        if aliases is None:
            aliases = []

        year = str(year)

        try:
            aliases1 = [
                (a.get("title") or a.get("originalname") or "")
                + " (" + a.get("country", "") + ")"
                for a in aliases
            ]
            aliases2 = [a.rpartition(" (")[0] for a in aliases1]
            aliases2 = [a.replace(year, "").replace("()", "").rstrip() for a in aliases2]
            aliases2 = [a for a in aliases2
                        if not source_utils.czy_litery_krzaczki(a)]
            aliases2 = [alias for i, alias in enumerate(aliases2)
                        if alias.lower() not in [x.lower() for x in aliases2[:i]]]
            self.titles = aliases2

            log_text = f"tytuł: {title!r}"
            log_text += f", polski tytuł: {localtitle!r}" if localtitle != title else ""
            log_text += f", rok: {year!r}" if year else ""
            log_text += f", data premiery: {premiered!r}" if premiered else ""
            log_text += f", odcinek: {episode!r}" if episode else ""
            log_text += f', aliasy: {aliases2[::-1]}' if aliases else ''
            # fflog(log_text)

            base_titles = []

            titles_to_use = [title.lower()]
            if localtitle.lower() != title.lower():
                titles_to_use.append(localtitle.lower())

            season_str = ""
            if episode:
                match = re.search(r"s(\d{2})", episode, re.IGNORECASE)
                season_str = f"s{match.group(1)}" if match else ""

                for t in titles_to_use:
                    if const.sources.xtb7.space_before_season:
                        base_titles.append(f"{t} {season_str}")
                    if const.sources.xtb7.dot_before_season:
                        base_titles.append(f"{t}.{season_str}")

                if const.sources.xtb7.include_base_title_in_show_search:
                    for t in titles_to_use:
                        if t not in base_titles:
                            base_titles.append(t)
            else:
                base_titles.extend(titles_to_use)

            seen = set()
            unique_titles = []
            for t in base_titles:
                t_norm = t.lower()
                if t_norm not in seen:
                    seen.add(t_norm)
                    unique_titles.append(t)

            # fflog(f'BAZA TYTUŁÓW: {base_titles}')
            aliases_lower = [a.lower() for a in aliases2]
            all_titles = base_titles + aliases_lower
            # fflog(f'BAZA TYTUŁÓW i aliasów: {all_titles}')

            def unique_ignore_case(seq):
                seen = set()
                result = []
                for item in seq:
                    key = item.lower()
                    if key not in seen:
                        seen.add(key)
                        result.append(item)
                return result

            self.titles = unique_ignore_case(all_titles)

            final_titles = []
            for t in self.titles:
                cleaned = cleantitle.normalize(cleantitle.getsearch(t))
                final_titles.append(cleaned)

            # usuwanie duplikatów (bez różnicy wielkości liter)
            def unique_case_insensitive(lst):
                seen = set()
                unique_list = []
                for item in lst:
                    key = item.lower()
                    if key not in seen:
                        seen.add(key)
                        unique_list.append(item)
                return unique_list

            final_titles = unique_case_insensitive(final_titles)

            final_titles = [const.sources.xtb7.title_replacements.get(t.lower(), t) for t in final_titles]

            def korekty_dla_wyszukiwarki(title):
                title = title.replace(" - ", " ")
                title = title.replace("-", "_")
                title = title.replace(". ", ".")
                title = title.replace(" ", "_")
                title = title.replace(",", "")
                title = title.replace("#", "")
                title = re.sub(r'_?(\d)⁄', r'_\1_', title)  # np. 1⁄2 -> _1_
                title = title.replace("_", " ")
                title = title.replace("&", " and ")
                title = title.replace("  ", " ")
                return title

            self.login()
            biblio_cache, biblio_links = self.files_on_user_account(from_cache=False)[0:2]
            customTitles = "customTitles" in sys.argv[2]

            for search_title in final_titles:
                title_to_search = korekty_dla_wyszukiwarki(search_title) if not customTitles else search_title
                if search_title not in self.titles:
                    self.titles.insert(0, search_title)

                title_r = title_to_search
                if not customTitles:
                    # usuwanie "the", "a", "an" z początku
                    title_r = re.sub(r"^(the|an?) ", "", title_r, 1, flags=re.IGNORECASE)

                if len(title_r) < 3:
                    title_r += f' {episode}' if episode else f' {year}'

                # jeśli brak znaków specjalnych i nie kończy się na '%', dodaj '%'
                if not re.search(r"\W", title_r.rstrip("%")) and not title_r.endswith("%"):
                    title_r += "%"

                # fflog(f"WYSŁANIE zapytania: {title_r!r}")
                post = {"search": title_r, "type": "1"}
                pre_res = self.session.post(self.base_link+self.search_link, headers=self.headers, data=post).text
                pre_res = pre_res.replace("\r", "").replace("\n", "")

                page_block = re.search('class="page-list"(.+?)</div>', pre_res, re.IGNORECASE)
                if page_block is not None:
                    pages = len(re.findall("href=", page_block.group()))
                    self.pages.append({title_r: pages})
                    fflog(f" sprawdzanie otrzymanych wyników ({pages} podstr.)")
                    self.get_pages_content(range(pages), year, title, episode, premiered)
                    results = self.results
                    if not results:
                        fflog(' brak pasujących rekordów')
                else:
                    fflog(" nie otrzymano wyników")

                last_chance = False
                if search_title == final_titles[-1] and not results:
                    max_pages = max((val for page in self.pages for val in page.values()), default=0)
                    if episode and (not self.pages or max_pages == 1):
                        try:
                            title_phrases_exceptions = source_utils.antifalse_filter_exceptions
                        except Exception:
                            fflog_exc()
                            title_phrases_exceptions = []
                        fflog(f'{title_phrases_exceptions=}', 0)
                        titles_to_add = []
                        for ex in title_phrases_exceptions:
                            new_titles = [
                                re.sub(rf"([_\W]+{ex})", "", t, flags=re.I)  # usuwanie końcówek typu "_cz" z tytułu
                                for t in final_titles if isinstance(t, str)
                            ]
                            new_titles = [t for t in new_titles if t not in final_titles]
                            titles_to_add += new_titles
                        if titles_to_add:
                            final_titles += titles_to_add
                            fflog(f'skrócono tytuł')
                            continue

                    if not last_chance and re.search(r"s01(e\d+)", episode, flags=re.I):
                        for page in self.pages:
                            page_title = list(page)[0]
                            if re.search(r"s[0o]1(e\d+)?", page_title, flags=re.I):
                                base_title = re.sub(r"[\W_]s[0o]1(e\d+)?", "", page_title, flags=re.I)  # usuwanie sezonu z tytułu
                                ep_only = re.sub(r"s01(e\d+)", r"\1", episode, flags=re.I)  # s01e05 -> e05
                                sep = " " if " " in base_title else "."
                                new_variant = f"{base_title}{sep}{ep_only}"
                                if new_variant not in final_titles and (new_variant,) not in results:
                                    final_titles.append(new_variant)
                                    fflog(f'DODANO nową wariację {new_variant}')
                                last_chance = True
                                break
                    break

            return results

        except Exception as e:
            fflog_exc()
            fflog(f"Błąd wyszukiwania: {e}")
            return []

    def prepare_pattern_for_titles_v2(self, title):
        """alternatywna wersja (ma być prostsza, choć to się jeszcze okaże)"""

        title = title.lower()  # opcjonalnie, bo wcześniej to jest robione

        # pattern = re.sub(r'(((?!\\?\&)\W)+)', r"[\1 .–-]+", title)  # znaki nieliterowe, oprócz "&" (obsłużony jest niżej)
        pattern = re.sub(r'([^\w&]+)', r"[\1 .–-]+", title)  # prostszy zapis, ale nie można wówczas stosować re.escape
        pattern = re.sub(r'(\[[^ \w]+ \.–\-\])\+', r'\1*', pattern)  # korekta dla pojedynczych znaków, gdy nie ma po nich spacji
        # pattern = re.sub(r'\[ *([^ \w]+ \.–-])\+', r'[\1*', pattern)  # dla niektórych przypadków trochę lepsze od powyższego
        # poniższe 3 mogą być niezbędne, jak nie był robiony escape znaków
        pattern = pattern.replace("[^", r"[\^")
        pattern = pattern.replace("[]", r"[\]")
        pattern = pattern.replace("[[", r"[\[")
        # sprzątanie
        # pattern = re.sub(r" *(\\?\W)\1+", r"\1", pattern)  # sprzątanie zdublowanych znaków
        # pattern = re.sub(r"(\[) *(\W*?)( *\\?[.–-])+(?= )", r"\1\2", pattern)  # aby nie powielać znaków ".–-"
        # pattern = re.sub(r"(\[) *(\W*?)( *(\\\.|–|\\\-))+(?= )", r"\1\2", pattern)  # alternatywa powyższego zapisu
        pattern = re.sub(r"(?<=\[)\W+?(?= \.–-])", lambda x: "".join(list(dict.fromkeys(re.sub("[ .–-]", "", x[0])))), pattern)

        # nie wiem czy warto
        # pattern = pattern.replace("[ .–-]+", "[ .–-]")  # reprezentacja spacji

        # ampersand
        pattern = pattern.replace(r"&", r"(\&|and|i)")  # "Dungeons & Dragons: Złodziejski honor"
        # pattern = re.sub(r"\b(?<!\|)and(?!\|)\b" , r"(and|\&)", pattern)  # nie testowałem jeszcze

        # dla konkretnego zapisu ułamków jakie występują np. w "Naga broń 2 1⁄2"
        sp = "[ .–-]+"  # uważać na plus na końcu
        spe = re.escape(sp)
        pattern = re.sub(rf'(\d{spe})((\d){spe}(\d({spe})?))', rf'\1(i{sp})?\3[ .,/-]\4', pattern)  # "Naga broń 2 i 1-2"
        # poniższe związane jest z powyższym (może to "jednorazowa" akcja?)
        pattern = re.sub(rf'(\d)({spe})([a-zA-Z])', r'\1\2*\3', pattern)  # np."2 The" -> "2The"
        pattern = pattern.replace("+*", "*")

        # i inne jak:
        title_pat = pattern  # dla kompatybilności

        # cyfry na słowa lub słowa na cyfry (także rzymskie)
        title_pat = source_utils.numbers_in_pattern(title_pat)

        # obsługa znaków diakrytycznych ("akcentów")
        # title_pat = source_utils.diacritics_in_pattern(title_pat, mode=1)  # ą -> [ąa]
        title_pat = source_utils.normalize_unicode_in_pattern(title_pat)  # metoda uniwersalniejsza

        # if settings.getBool("sources.allow_numbers_instead_of_letters_in_titles"):  # może dorobić takie coś?
        # cyfry zamiast liter np. "Mira3ulum – Bied3onka i Cz3rny K3t"
        # title_pat = re.sub(r"(?<!\[)([^\W\d_])(?![?\]])", r"[\1\\d]", title_pat)
        # title_pat = title_pat.replace("?]", "?\d]")
        # do powyższego fix na np. "Noc7ne gr7affiti"
        # title_pat = title_pat.replace("][", "]\d?[")

        pattern = title_pat
        return pattern


    def get_pages_content(self, page, year, title="", episode="", premiered="", aliases=None, rows=None):
        """Funkcja filtruje wstępnie wyniki otrzymane z serwera
        sprawdzając czy pasują któreś z elementów: tytuł, rok, numer odcinka
        """
        # fflog(f'{title=} {year=} {episode=} {page=} {premiered=}')

        franchise_names = const.sources.franchise_names
        sep = const.sources.franchise_names_sep

        def build_patterns(names, sep):
            # Zamienia spacje na sep (wzorzec [ .]) i zwraca listę wzorców regex
            return [sep.join(map(re.escape, name.split())) for name in names]
        franchise_aliases = {k: build_patterns(v, sep) for k, v in franchise_names.items()}

        if not rows:
            if page:
                # if type(page) is range:
                if isinstance(page, range):
                    pages = page
                else:
                    pages = [page-1]
                rows = []
                for page in pages:
                    page += 1
                    # pobranie podstrony wyników
                    # fflog(f' pobranie ({page}) strony wyników')
                    res = self.session.get(
                        self.base_link + self.support_search_link.format(str(page)),
                        headers=self.headers,
                    ).text
                    row = client.parseDOM(res, "tr")[1:]
                    fflog(f' [{page}] strona: {len(row)} wyników')
                    rows += row
                fflog(f' Do przeanalizowania: {len(rows)}') if isinstance(pages, range) and page > 1 else ""
                self.raw_results += rows
                res = row = None  # czyszczenie ramu
        else:
            # to przeważnie dla pozycji z biblioteki
            # fflog(f' Analizuje zadane rekordy [{len(rows)}] {rows=}')
            pass

        if episode:
            # mógłbyć dołożony numer odcinka do zapytania
            #title = re.sub(r"(s\d{2})?e\d{2}$", "", title).rstrip("._ ")
            title = re.sub(r"(s[0o]?\d{1,2})?[ _.]?(e[\do]{2,4})?$", "", title).rstrip("._ ")
        if year:
            # mógłbyć dołożony rok do zapytania
            # title = title.replace(year, "", 1).rstrip("_ ")
            title = "".join(title.rsplit(year, 1)).rstrip("._ ")
            # ciekawe czy jest taki tytuł co ma rok taki sam jak data produkcji?
        title = title.rstrip("%")  # czy to nie popsuje nic ?
        # fflog(f'{title=}')
        #if " " not in title:
        title = title.replace(".", " ")

        # granice frazy (alternatywa dla \b)
        b1 = r"(?:^|(?<=[([ _.-]))"  # początkowa
        b2 = r"(?=[)\] _.-]|$)"  # końcowa

        # wzorzec roku
        # year_pat = r"([ ._]*[(\[]?(19\d[\dO]|[2-9][\dO]{3})[)\]]?)"
        yr_uni_pat = r"\b(19\d[\dOo]|2[Oo0][\dOo]{2})\b"  # (1900 - 2099)
        # yr_uni_pat = f"{b1}{yr_uni_pat}{b2}"
        # yr_uni_pat = f"[ ._([]*{yr_uni_pat}"
        if year:
            year_pat = f"{b1}{year}{b2}".replace("0", "[0Oo]")  # wzorzec dla konkretnej daty (roku)

        # wzorzec przydatny do sprawdzania, czy w ogóle jest taka sekwencja w nazwie pliku, sugerując jednocześnie, że to może być odcinek serialu
        ep_uni_pat = r"((S\d{1,2})?[.,-]?E\d{2,4}|\bcz\.|\bodc\.|\bep\.|episode|odcinek|[\(\[]\d{2,3}[\)\]]|\- \d{2,3} [([-]|\b\dx\d{2}\b)"
        ep_uni_pat = ep_uni_pat.replace(r"\d", r"[\dO]").replace("0", "[0O]")  # czasami zamiast 0 wstawiane jest O

        ep_uni_pat2 = r"(S\d{2})?[.,-]?(E(\d{2,4}))"
        ep_uni_pat2 = ep_uni_pat2.replace(r"\d", r"[\dO]")  # czasami zamiast 0 wstawiane jest O

        # zmienne do zapamiętania stworzonego raz filtru
        dodatkowy_filtr = self.dodatkowy_filtr
        dodatkowy_filtr2 = self.dodatkowy_filtr2

        allow_filename_without_year = True

        titles = self.titles  # zaczytanie wcześniej wybranych (m.in. aliasów)

        titles = [t.lower() for t in titles]
        titles = list(dict.fromkeys(titles))  # usunięcie duplikatów

        # Dodanie uproszczonych wersji tytułów (tylko do dopasowania, nie do zapytań)
        extra_titles = []
        for t in titles:
            # usuwanie przedrostków the, a, an
            if t.startswith(("the ", "a ", "an ")):
                stripped = re.sub(r"^(the|a|an) ", "", t, flags=re.IGNORECASE)
                if stripped not in titles:
                    extra_titles.append(stripped)

            # usunięcie .sXX z końca
            if re.search(r"\.s\d{1,2}$", t):
                base = re.sub(r"\.s\d{1,2}$", "", t)
                if base not in titles:
                    extra_titles.append(base)

        if extra_titles:
            titles += extra_titles
        # dodanie bieżącego tytułu do listy (jeśli go tam jeszce nie ma)
        if title and title not in titles:
            titles = [title] + titles

        # opcjonalnie (może pomóc)
        # "spirited away: w krainie bogów" -> "w krainie bogów - spirited away"
        tmp = []
        for t in titles:
            if ": " in t and "-" not in t:
                temp1 = " - ".join(t.split(": ")[::-1])
                if temp1 not in titles:
                    tmp += [temp1]
        if tmp:
            titles += tmp

        # fflog(f"titles (z aliasami): ({len(titles)}) \n" + "\n".join(titles), 0)  # kontrola

        # titles_pat_list = [self.prepare_pattern_for_titles(t) for t in titles]
        titles_pat_list = [self.prepare_pattern_for_titles_v2(t) for t in titles]

        titles_pat_list = list(dict.fromkeys(titles_pat_list))  # usunięcie duplikatów

        # fflog(f"titles_pat_list: ({len(titles_pat_list)}) \n" + "\n".join(titles_pat_list), 0)  # kontrola

        title_pat = f'({"|".join(titles_pat_list)})'  # połączenie w 1 string

        # czasami są jeszcze takie przed rokiem
        res_pat = r"[ ._]*[(\[]?(720|1080)[pi]?[)\]]?"

        if episode or allow_filename_without_year:
            # wzorzec dla rozdzielczości
            res_pat = r"\b(SD|HD|UHD|2k|4k|480p?|540p?|576p?|720p?|1080[pi]?|1440p?|2160p?)\b"

            # wzorzec czasami spotykanych fraz
            # custom_pat = '([ ._][a-z]{2,})'  # za duża tolerancja i trafić może na ostatnie słowo innego tytułu np. "Titans go" dla filmu "Titans"
            custom_pat = r"\b(lektor|subbed|napisy|dubbing|polish|po?l(dub|sub)?|us|fr|de|dual|multi|p2p|web[.-]?(dl)?|remux|3d|imax)\b"  # trudnosć polega na przewidzeniu wszystkich możliwości

        # nazwa jakiejś grupy ludzi (powinna być na samym początku)
        # tylko nie wiem jakie mogą być dozwolone kombinacje
        group_pat = r"^[.[][^.[\]]{3,}[.\]]"

        # rozszerzenia plików
        ext_pat = f'({"|".join(self.VIDEO_EXTENSIONS)})'.replace(".", "")

        if not episode:  # czyli dla filmów

            if allow_filename_without_year:
                after_pat = fr"(\[\w*?\]|{res_pat}|{custom_pat}|{ext_pat}$)"
            else:
                after_pat = yr_uni_pat

            # końcowy wzorzec do porównywania z nazwą pliku
            # if not self.tit_val_filt_for_one_title:  # to chyba już niepotrzebne
            if True:  # na razie tak
                dodatkowy_filtr = re.compile(
                    rf"^(\d{{1,2}}|{yr_uni_pat}|{group_pat})?[ .-]*(\W?{title_pat}((?<!\d)\d|[ .-]1)?[ ./()-]{{1,4}})+((?<=[(])\d[)])?[ .-]?[(\[]?({yr_uni_pat}|{after_pat})",
                    flags=re.I)
            # zapamiętanie na kolejne wywołaniu tej funkcji, która dotyczyć będzie i tak tego samego filmu
            # (tylko inna fraza idzie do wyszukiwarki), a wszystkie tytuły zostały na początku ustalone w self.titles
            self.dodatkowy_filtr = dodatkowy_filtr

        if episode:  # dla seriali

            # do DEBUGOWANIA, jak się nie mieści pattern w logu
            # res_pat = custom_pat = yr_uni_pat = '()'
            # title_pat = '()'

            # definiowałem wcześniej do odróżniania filmów od seriali
            ep_uni_pat = ep_uni_pat[:-1] + r"|\b\d{2,3}\b)"  # dodanie dodatkowego wzorca

            # końcowe wzorce do porównywania z nazwą pliku
            dodatkowy_filtr = re.compile(
                rf"(^({group_pat})?|[/-]|\d{{1,2}})[ .]?(\W?{title_pat}((?<!\d)\d|[ .-]1)?[ ./()-]{{1,4}})+((?<=[(])\d[)])?[ .-]?[([]?([ .-]*({res_pat}|{yr_uni_pat}|{custom_pat}))*[)\]]?[ .-]*[([]?{ep_uni_pat}",
                flags=re.I,
            )

            dodatkowy_filtr2 = re.compile(rf"(^\d{{1,2}}\.?\W?|[([]?{ep_uni_pat2}\W*){title_pat}([ .]*[/-]|[ .]{{2,}})", flags=re.I)
            # zmienna 'dodatkowy_filtr2' jest na przypadek, gdy na początku jest numer odcinka a potem tytuł
            self.dodatkowy_filtr = dodatkowy_filtr
            self.dodatkowy_filtr2 = dodatkowy_filtr2

        # poniższe zawsze musi być (niezależnie czy używany będzie filtr dopasowujący tytuły)
        # jeśli episode się nie zmienia, to może można to zapamiętać
        # jest po to, aby wybrać właściwy odcinek (którego szukamy)
        if episode:
            # wzorzec numerów odcinków
            episode_pat = re.sub(r"S0?(\d{1,2})(E(\d{2,4}))", r"s0?\1[.,-]?e(\\d{2,4}-?)?e?0?\3(?!\\d)", episode, flags=re.I)
            # jak próbowałem zrobić podobny numer dla odcinków, to z powodu dziwnego zapisu zakresu łapał mi e013 dla e3 - także na razie odpuszczam
            # na przypadek gdy nie ma innego sezonu
            # fflog(f'{episode_pat=}')
            episode_pat = re.sub(
                # r"(S01.*?)(E.*)",
                r"(S0\?1.*?)(E.*)",
                r"(\1\2|(?<![se]\\d{1}[.,-])(?<![se]\\d{1})(?<![se]\\d{2}[.,-])(?<![se]\\d{2})(?<!e\\d{3}[.,-])(?<!e\\d{3})(?<!e\\d{4}[.,-])(?<!e\\d{4})\2)",
                episode_pat,
                flags=re.I,
            )
            # fflog(f'{episode_pat=}')
            # zauważyłem, że czasami zamiast 0 jest O
            episode_pat = episode_pat.replace(r"\d", r"[\dO]").replace("0", "[0O]")

            # dla łączonych odcinków
            eps = (re.search(r"e(\d{2,4})", episode).group(1))  # string
            epn = int(eps)  # liczba (numer)
            sn = int(re.search(r"s(\d{2})", episode).group(1))
            rang_re = re.compile(r"(?:s([\dO]{2})-?)?e(\d{2,4})-e?(\d{2,4})(?!\w)", flags=re.I)
            def ep_is_in_range(filename):
                rang = rang_re.search(filename)
                if rang:
                    # fflog(f'{filename=}')
                    # fflog(f'{rang=}')
                    if not rang.group(1) and sn==1 or rang.group(1) and int(rang.group(1).replace('O','0'))==sn:
                        # fflog(f'{sn=} {epn=}')
                        return epn in range(int(rang.group(2)), int(rang.group(3)))
                return None

            if re.search(r"[sS]01", episode):
                episode2_pat = fr"(?<!\d[2-9])[ .](cz\.|odc\.|ep\.|episode|odcinek)[ .-]{{,3}}0{{,2}}{epn}\b|[([]0{{,2}}{epn}[)\]](?!\.[a-z]{{2,3}}$)|\- 0{{,2}}{epn} [([-]|\b0?{sn}x0{{,2}}{epn}\b|\b0{{,2}}{epn}\.[a-z]{{2,3}}$|[a-z][ .]0{{,2}}{epn}[ .][a-z]"
            else:
                episode2_pat = "niemozenicznalezc"
            # fflog(f'{episode2_pat=}')

        # sprawdzenie, czy tytuł serialu zawiera w sobię rok
        year_in_title = re.search(r"\b\d{4}\b", title)
        year_in_title = year_in_title[0] if year_in_title else ""

        # ustalenie bieżącego roku - a co jak ktoś ma złą datę na urządzeniu?
        current_year = int(time.strftime("%Y"))
        # fflog(f'{current_year=}', 0)

        def _check_base_or_premiered_year_in_filename(filename):
            if not premiered and not year:
                return
            filename = filename.replace(year_in_title, "")
            #year_in_filename = re.findall(r"\b\d{4}\b", filename)  # też może być
            year_in_filename = re.search(r"\b\d{4}\b", filename)
            if year_in_filename:
                year_in_filename = year_in_filename[0]
                if 1900 <= int(year_in_filename) <= int(current_year) + 1:
                    if premiered and (premiered.startswith(year_in_filename) or premiered.endswith(year_in_filename)) or year and str(year) == year_in_filename:
                        return True
                    else:
                        return False

        yr_uni_re = re.compile(yr_uni_pat)
        year_re = re.compile(year_pat) if year else None
        episode_re = re.compile(episode_pat, flags=re.I) if episode else ""
        episode2_re = re.compile(episode2_pat, flags=re.I) if episode else ""
        ep_uni_re = re.compile(ep_uni_pat, flags=re.I)
        ep_uni2_re = re.compile(ep_uni_pat2, flags=re.I)
        for row in rows:
            if row in self.results:  # pozbycie się takich samych pozycji
                continue
            size = client.parseDOM(row, "td")[3]  # rozmiar pliku (informacyjnie)
            filename0 = "".join(client.parseDOM(row, "a") or client.parseDOM(row, "label"))  # nazwa pliku
            # odrzucenie rozszerzeń niebędących plikami video
            if filename0[-3:] not in self.VIDEO_EXTENSIONS:
                # fflog(f"  - niepasujące rozszerzenie {filename0[-3:]!r} w {unescape(unquote(filename0))!r}")
                continue
            # funkcji unquote() oraz unescape() najlepiej używać tylko do koncowego wyświetlenia
            # !nie uzywać do porównań z oryginałem,
            # ponieważ raczej nie da się odtworzyć w 100% stringu pierwotnego
            filename = filename0
            filename = unquote(filename)
            filename = unescape(filename)
            filename = filename.replace("_", " ")  # dla uproszczenia, ale sprawdzić patterny, bo mogłobyć wcześniej założenie, że nie ma spacji tylko _
            filename = re.sub(r"\b[0-9a-f]{8}\b", "", filename, flags=re.I)  # wyrzucenie CRC32 z nazwy pliku
            # fflog(f"{filename=}")
            if (
                # (year and year in filename)
                (not episode and year and year_re.search(filename))
                or (not episode and year and re.search(str(int(year)-1), filename))  # przepuszcza filmy z rokiem o 1 mniejszym od bazowego
                or (not episode and (yp := "".join(re.findall(r"\d{4}", premiered))) and re.search(yp, filename))
                or (not episode and year and allow_filename_without_year and not yr_uni_re.search(filename) and not ep_uni_re.search(filename))  # gdy brak roku w tytule
                or (episode and episode_re.search(filename))
                or (episode and ep_is_in_range(filename))
                or (episode and not ep_uni2_re.search(filename) and episode2_re.search(filename))  # inne warianty zapisu odcinków (m.in. dla niektórych anime)
                or (not year and not episode)
            ):

                # sprawdzenie zgodności nazwy pliku z szukanym tytułem
                # (jeśli taki filtr nie jest wyłączony przez użytkownika w ustawieniach)
                if episode:
                    if premiered and re.search(r"\b\d{4}\b", filename):
                        if _check_base_or_premiered_year_in_filename(filename) is False:
                            continue

                if (
                    not dodatkowy_filtr
                    or dodatkowy_filtr.search(filename)
                    or (dodatkowy_filtr2 and dodatkowy_filtr2.search(filename))
                    or sum(1 for t in self.titles if t.lower() in filename.lower()) >= 2  #  fix for pl.en/en.pl titles
                    or any(
                        re.search(pat, filename, re.I)
                        for pat_list in franchise_aliases.values()
                        for pat in pat_list
                    )
                ):

                    # fflog(f'Dopuszczono: {unescape(unquote(filename0))}')
                    self.results.append(row)  # dodanie do listy zaakceptowanych
                    # fflog(f'  + przepuszczono {unescape(unquote(filename0))!r} {size}')
                    # fflog(f' bo {title=} {dodatkowy_filtr=} {year=} {episode=}\n')
                # else:
                    # fflog(f'Odrzucono (nie pasuje tytuł): {unescape(unquote(filename0))}')
            # else:
                # fflog(f'Odrzucono (nie pasuje rok/odcinek): {unescape(unquote(filename0))}')
                # nie ten rok, albo nie ten odcinek
                # fflog(f' nie dodano, bo {filename=} {size=}\n')
                pass


    def sources(self, rows, hostDict, hostprDict, from_cache=None):
        if not rows:
            fflog('Brak rekordów do przekazania')
            return []

        self.login()

        if from_cache or self.remaining_limit_mb == 0:
            self._fetch_remaining_limit()

        # fflog(f"sprawdzenie co jest na koncie (i notesie)")
        biblio_cache, biblio_links = self.files_on_user_account(from_cache=from_cache)[0:2]

        # fflog(f"parsing źródeł ({len(rows)})")
        sources = []
        try:
            for row in rows:
                try:
                    filename = client.parseDOM(row, "label")[0]
                    if "<a " in filename.lower():  # moze byc jeszcze tag a
                        filename = client.parseDOM(filename, "a")[0]

                    link = client.parseDOM(row, "input", ret="value")[0]
                    # fflog(f' ')
                    # fflog(f'analizowanie {link=}')

                    # sprawdzenie, czy wybrana pozycja może jest już na Koncie
                    on_account, on_account_link, case, on_account_expires = self.check_if_file_is_on_user_account(biblio_links, link, filename, biblio_cache)
                    # on_account = False  # test tylko

                    # uniknięcie zdublowań dla dołączonych z biblioteki
                    if 'dowalona_z_biblioteki' in row and on_account_link and any(on_account_link == s["on_account_link"] for s in sources):
                        # fflog(f'uniknięcie zdublowań dla dołączonych z biblioteki {on_account_link=}')
                        continue

                    hosting = client.parseDOM(row, "td")[1]  # hosting
                    size = client.parseDOM(row, "td")[3]  # rozmiar
                    # fflog(f'DEBUG: size={size!r}, transfer_left_bytes={self.remaining_limit_mb!r}')
                    no_transfer = False
                    if const.sources.premium.no_transfer:
                        if self.remaining_limit_mb == 0:
                            no_transfer = True
                        else:
                            source_size_mb = int(source_utils.convert_size_to_bytes(size) / (1024 * 1024))
                            if source_size_mb > self.remaining_limit_mb:
                                no_transfer = True

                    quality = source_utils.check_sd_url(filename)

                    info = source_utils.get_lang_by_type(filename)
                    language = info[0]
                    if not info[1]:
                        info1 = ""
                    else:
                        info1 = f"{info[1]}"
                    info = f"{info1}"

                    alt_links = []
                    alt_filenames = []  # (aby lepiej wykrywać, że jest na koncie)

                    reject = False

                    def filename_similarity(name1, name2):
                        """Porównuje podobieństwo nazw plików w skali 0.0 - 1.0."""
                        name1 = unescape(unquote(name1)).lower()
                        name2 = unescape(unquote(name2)).lower()
                        return SequenceMatcher(None, name1, name2).ratio()

                    if const.sources.xtb7.similarity_check:
                        # sprawdzenie, czy nie jest to duplikat źródła
                        # (jeśli jest podobne do już istniejącego)
                        for i in reversed(range(len(sources))):
                            s = sources[i]

                            if hosting in s["source"] and info == s["info"] and quality == s["quality"]:
                                filename1 = unescape(unquote(filename)).lower()
                                filename2 = unescape(unquote(s["filename"])).lower()
                                similarity = filename_similarity(filename1, filename2)
                                if similarity > const.sources.xtb7.similarity_threshold:
                                    # Duplikat - bardzo podobna nazwa (np. różni się jedną liczbą)
                                    # fflog(f'odrzucenie jako duplikat: {link=}')
                                    if link not in s["alt_links"]:
                                        s["alt_links"].append(link)
                                    if filename not in s["alt_filenames"]:
                                        s["alt_filenames"].append(filename)
                                    reject = True
                                else:
                                    # Nazwy znacznie się różnią — nie traktuj jako duplikat
                                    continue
                                break

                    if reject:
                        # fflog(f'dubel - {filename}')
                        continue

                    hosting += case  # dodanie ewentualnie gwiazdki
                    sources.append(
                        {
                            "source": hosting,
                            "quality": quality,
                            "language": language,
                            "url": link,
                            "info": info,
                            "size": size,
                            "direct": True,
                            "debridonly": False,
                            "filename": filename,
                            "on_account": on_account,
                            "on_account_expires": on_account_expires,
                            "on_account_link": on_account_link,
                            "alt_links": alt_links,
                            "alt_filenames": alt_filenames,
                            "premium": True,
                            "no_transfer": no_transfer,
                        }
                    )
                except Exception:
                    fflog_exc()
                    continue

            # zapisanie informacji w cache, aby potem wykorzystać w następnej funkcji,
            # gdyż instancja Klasy zostanie zniszczona (wada Kodi?)
            # src = {i['url']: i for i in sources}  # zrobienie z listy słownika, gdzie kluczem dla każdego źródła będzie jego link
            src = sources  # zostawiam jako listę
            # w bazie cache będzie key({self.PROVIDER}_src), value(słownik w formie stringa)

            fflog(f'Przekazano źródeł: {len(sources)}')
            return sources

        except Exception:
            fflog_exc()
            return sources

    def resolve(self, url, buy_anyway=False, specific_source_data=None):
        """Funkcja odsyła link do playera"""
        # przechowanie wartości zmiennej
        original_url = url
        if not specific_source_data:
            specific_source_data = {}

            # Pobranie hosts dla source = 'xt7' z tabeli rel_src
            hosts_data = cache.cache_value(
                "xt7",
                control.sourcescacheFile,
                table="rel_src",
                column="hosts",
                key_column="source"
            )
            if hosts_data:
                try:
                    from ast import literal_eval
                    if isinstance(hosts_data, str):
                        sources_data = literal_eval(hosts_data)
                    else:
                        sources_data = hosts_data

                    try:
                        specific_source_data = next(i for i in sources_data if i["url"] == url)
                    except (StopIteration, TypeError, KeyError):
                        pass

                except (ValueError, SyntaxError) as e:
                    fflog(f'Błąd parsowania hosts data: {e}')
                    pass
        # player_link_after_redirection = settings.getBool("player.link_after_redirection")
        player_link_after_redirection = True

        def _check_on_account_link_before_play(on_account_link):
            # test i ewentualna próba naprawy nieaktywnego linku
            link = on_account_link
            if '/sciagaj/' in link:
                response = self.session.get(link, headers=self.headers, verify=False, allow_redirects=False)
                if response.status_code == 200:
                    control.execute('Dialog.Close(notification,true)')
                    if 'dla podanego linka Premium' in response.text:
                        control.dialog.ok(f'{self.PROVIDER}', 'Wykorzystano limit połączeń dla tego źródła.')
                    else:
                        control.dialog.ok(f'{self.PROVIDER}', 'Ważność linku wygasła.')
                        control.window.clearProperty('imdb_id')  # aby odświeżyć listę źródeł
                        control.window.setProperty('clear_SourceCache_for', control.window.getProperty('clear_SourceCache_for') + f',{self.PROVIDER}')  # jak ktoś używa cache źródeł
                    # control.execute('Dialog.Close(notification,true)')
                    return None
                if response.status_code == 302:
                    link = response.headers['Location']
                    response = self.session.head(link, headers=self.headers, verify=False, allow_redirects=False)
                    if 'text' in response.headers['Content-Type']:
                        if 'download_token=' in link and '.wrzucaj.pl/' in link:  # tylko dla wrzucaj.pl
                            link = re.sub(r'(?<=//)\w+?\.(wrzucaj\.pl/)', r'\1file/', link)
                            link = re.sub(r'\&?download_token=[^&]*', '', link).rstrip('?')
                            try:
                                link = link.encode('latin1').decode('utf8')  # aby było czytelniej w logach
                            except Exception:
                                fflog_exc()
                                pass
                            on_account_link = link
                            response = self.session.head(link, headers=self.headers, verify=False, allow_redirects=False)
                        if response.status_code == 302:
                            link = response.headers['Location']
                            response = self.session.head(link, headers=self.headers, verify=False, allow_redirects=False)
                if response.status_code == 403:
                    control.execute('Dialog.Close(notification,true)')
                    control.dialog.ok('Dostęp został ograniczony', ' [CR] - sprawdź przyczynę na stronie internetowej')
                    return None  # choć VLC może odtworzyć, bo błąd 403 może w nim nie wystąpić

                elif response.status_code >= 400:
                    control.infoDialog(f'Serwer zwrócił błąd nr {response.status_code}', f'{self.PROVIDER}', 'ERROR', 4000)
                    control.sleep(4000)
                    return None  # choć np. VLC może czasami odtworzyć, bo błąd 403 może w nim nie wystąpić
                fflog(f"1 {response.status_code=}", 0)
            if player_link_after_redirection:
                on_account_link = link  # czy to nie będzie powodowało problemów z rozpoznawaniem przez Kodi linku do kontynuacji?
                pass
            fflog(f"(rozwiązany?) {on_account_link=}", 0)
            # return on_account_link
            # return str(on_account_link + "|User-Agent=VLC&verifypeer=false")  # VLC nie odtwarza tego
            return on_account_link + f"|User-Agent={quote(self.headers.get('User-Agent', ''))}&verifypeer=false"

        # sprawdzenie, czy wybrane źródło jest już może na koncie użytkownika
        if not buy_anyway and specific_source_data:
            on_account = specific_source_data.get('meta', {}).get('on_account', False)
            if on_account:
                on_account_link = specific_source_data.get('meta', {}).get('on_account_link', '')
                if on_account_link:
                    on_account_link = on_account_link.replace("%2F", "-")  # fix dla plików z "/" w nazwie
                    return _check_on_account_link_before_play(on_account_link)

        self.login()

        # pobranie informacji o plikach na koncie ("notes_list" może być dalej potrzebny)
        biblio_cache, biblio_links, notes_list = self.files_on_user_account(mode=2, from_cache=False)

        # odczytanie nazwy pliku związanego z wybranym url-em
        filename = specific_source_data.get('meta', {}).get('filename', '')
        fflog(f'{filename=}')
        if not buy_anyway:
            # Sprawdzenie czy wybrana pozycja jest już na koncie
            links = [original_url]
            links = list(dict.fromkeys(links))  # ewentualne pozbycie się duplikatów
            filenames = ([filename] if filename else [])
            filenames = list(dict.fromkeys(filenames))  # ewentualne pozbycie się duplikatów
            on_account, on_account_link, case = self.check_if_file_is_on_user_account(biblio_links, links, filenames, biblio_cache)[0:3]
            # jeśli tak, to zwróć link do niej
            if on_account:
                # fflog(f'{case=} {on_account=} {on_account_link=}')
                on_account_link = on_account_link.replace("%2F", "-")  # fix dla plików z "/" w nazwie
                return _check_on_account_link_before_play(on_account_link)

        auto_purchase = settings.getBool(f"{self.PROVIDER}.auto")
        if not auto_purchase:
            limit_info = self.session.get(self.base_link, headers=self.headers).text
            limit_info = client.parseDOM(limit_info, "div", attrs={"class": "textPremium"})
            remaining_limit = str(client.parseDOM(limit_info, "b")[-1])
            remaining_limit = re.sub(r"\s*\w+\s*=\s*([\"']?).*?\1(?=[\s>]|$)\s*", "", remaining_limit)
            remaining_limit = re.sub("<[^>]+>", "", remaining_limit)

            # przygotowanie nazwy pliku do wyświetlenia w okienku pytającym
            # if control.settings.getBool("sources.extrainfo"):
            if True:
                if not filename:
                    filename = url
                filename = unquote(filename)
                filename = unescape(filename)
                filename = self.prepare_filename_to_display(filename)

                filename = f"[LIGHT]{filename}[/LIGHT]"
            else:
                filename = ""
                pass

            size_info = specific_source_data.get('meta', {}).get('size', '')

            size_info = size_info.replace(" ", "\u00A0")
            hosting = specific_source_data.get('hosting', '')

            if control.condVisibility('Window.IsActive(notification)'):
                control.execute('Dialog.Close(notification,true)')

            user_accepts = xbmcgui.Dialog().yesno(
                "Czy chcesz pobrać ten plik?",
                (
                    f"[I]{filename}[/I]"
                    f"\nOd transferu zostanie odliczone: [B]{size_info}[/B]"
                    f"\nAktualnie posiadasz: [B]{remaining_limit}[/B]"
                ),
                yeslabel="Pobierz",
                nolabel="Anuluj"
            )
            if not user_accepts:  # rezygnacja
                return False

        # Ustalenie linku do filmu dla odtwarzacza

        links = [original_url] + specific_source_data.get("alt_links", [])
        # fflog(f'{links=}')
        links = list(dict.fromkeys(links))  # ewentualne pozbycie się duplikatów

        for link in links:
            # krok 1 - przesłanie adresu do sprawdzenia, czy aktywny
            data_step1 = {"step": "1", "content": link}
            response = self.session.post(f"{self.URL}/mojekonto/sciagaj", data=data_step1, headers=self.headers).text

            # srawdzenie, czy aktywny
            if ' value="Wgraj linki"' not in response:
                # control.window.clearProperty('imdb_id')  # aby odświeżyć listę źródeł
                fflog(f'nieaktywny {link=}')
                time.sleep(0.1)
                continue
            else:
                break

        if "ymagane dodatkowe" in response:
            control.dialog.ok('Brak środków', f'Brak wystarczającego transferu. \n[COLOR gray](aktualnie posiadasz [B]{remaining_limit}[/B])[/COLOR]')
            fflog(f'Brak wymaganego transferu')
            return None

        if ' value="Wgraj linki"' not in response:
            mnoga = len(links) > 1
            control.infoDialog((f"Wystąpił błąd. \nTa pozycja ma nieaktywn{'e' if mnoga else 'y'} link{'i' if mnoga else ''}."), f'{self.PROVIDER}', 'ERROR')
            fflog(f'żaden link dla tej pozycji nie działa')
            return None

        if buy_anyway:
            if '/wrzucaj.pl/' in link:
                if not '/file/' in link:
                    link = link.replace('/wrzucaj.pl/' , '/wrzucaj.pl/file/')
                    if "/" in filename:
                        l = list(link.partition('/file/'))
                        l[-1] = list(l[-1].partition('/'))
                        l[-1][-1] = l[-1][-1].replace('/', '%2F')
                        l[-1] = ''.join(l[-1])
                        link = ''.join(l)
                link = link.replace("%2F", "-")  # fix dla plików z "/" w nazwie
                if player_link_after_redirection:
                    response = self.session.head(link, headers=self.headers, verify=False, allow_redirects=False)
                    if response.status_code == 302:
                        link = response.headers['Location']
                # return link
                return link + f"|User-Agent={quote(self.headers.get('User-Agent', ''))}&verifypeer=false"

        active_url = link
        #fflog(f'   aktywny {link=}')

        # krok 2 - próba dodania źródła do biblioteki
        data_step2 = {"0": "on", "step": "2"}
        response = self.session.post(f"{self.URL}/mojekonto/sciagaj", data=data_step2, headers=self.headers).text

        # wydzielenie konkretnego fragmentu z odpowiedzi serwera
        div = client.parseDOM(response, "div", attrs={"class": "download"})
        try:
            link = client.parseDOM(div, "a", ret="href")[1]
            size = div[1].split("|")[-1].strip()
        except Exception:
            fflog_exc()
            if "Nieaktywne linki" in response:
                control.dialog.notification(f"{self.PROVIDER}", "Link okazał się nieaktywny")
                fflog(f'jednak zły {link=}')
            else:
                control.infoDialog("Wystąpił jakiś błąd. \nMoże brak wymaganego transferu?", f"{self.PROVIDER}", "ERROR")
            # control.dialog.ok('Brak środków', f'Brak wystarczającego transferu. \n[COLOR gray](aktualnie posiadasz [B]{remaining_limit}[/B])[/COLOR]')
            fflog_exc()
            return None

        # ewnentualne zapisanie informacji, aby następnym razem wiedzieć z jakim linkiem powiązać plik na koncie
        if settings.getBool(f"{self.PROVIDER}.use_web_notebook_for_history") and specific_source_data:
            # nazwa pliku
            filename = unescape(unquote(specific_source_data["filename"]))
            # link
            link1 = link.rpartition("/")[0] if "/sciagaj/" in link else link
            # data ważności
            short_day = re.compile(r"([a-z]{2,3})[a-z]*|0(\d)(?=:)", flags=re.I)
            from datetime import datetime, timedelta
            after = timedelta(1)  # 1 dzień
            expires = str((datetime.now() + after).strftime("%A %H:%M"))
            short_date = short_day.sub(r"\1\2", expires)

            notes_list = [{active_url: [link1, filename, size, short_date]}] + notes_list  # najnowszy na początek

            # zapisanie w Notesie na koncie
            while len(repr(notes_list)) >= 5000:  # limit narzucony przez serwis
                del notes_list[-1]
            now0 = int(time.time())
            self.session.post(
                self.base_link + self.mynotepad_link,
                data={"content": repr(notes_list)},
                headers=self.headers,
            )
            now1 = int(time.time())
            if (now1 - now0) > 5:
                fflog(f'!wysłanie historii plików do f"{self.PROVIDER}.pl/mojekonto/notes" zajęło {(now1 - now0)} sek.')

        # zwrócenie linku do odtwarzacza
        # fflog(f"link: {link!r}")
        link = link.replace("%2F", "-")  # fix dla plików z "/" w nazwie
        if player_link_after_redirection:
            return _check_on_account_link_before_play(link)
        else:
            # return str(link)
            # return str(link + "|User-Agent=vlc/3.0.0-git libvlc/3.0.0-git&verifypeer=false")  # VLC nie odtwarza tego
            return link + f"|User-Agent={quote(self.headers.get('User-Agent', ''))}&verifypeer=false"


    def prepare_filename_to_display(self, filename):
        # Pozwoli zawijać tekst (aby mieścił się w okienku)
        filename = filename[:-4].replace(".", " ").replace("_", " ") + filename[-4:]
        # Wywalenie ostatniego myślnika - zazwyczaj jest po nim nazwa "autora" pliku (uwzględniłem kod od TWOJPLIK)
        filename = re.sub(r"-(?=\w+( \(\d\))?( [0-9A-F]{3})?\.\w{2,4}$)", " ", filename, flags=re.I)
        # przywrócenie niezbędnych kropek i kresek dla niektórych fraz
        filename = self.replace_audio_format_in_filename(filename)
        return filename


    def replace_audio_format_in_filename(self, filename):
        replacements = [
            (r"(?<!\d)([57261]) ([10])\b", r"\1.\2"),  # ilość kanałów, np. 5.1 czy 2.0
            (r"\b([hx]) (26[45])\b", r"\1.\2", re.I),  # h264 x264 x265 h265
            (r"\b(DDP?) (EX)\b", r"\1-\2", re.I),  # np. DD-EX
            (r"\b(DTS) (HD(?!-?(?:TS|cam|TV))|ES|EX|X(?![ .]26))\b", r"\1-\2", re.I),  # DTS
            (r"\b(AAC) (LC)\b", r"\1-\2", re.I),  # AAC-LC
            (r"\b(AC) (3)\b", r"\1-\2", re.I),  # AC-3
            (r"\b(HE) (AAC)\b", r"\1-\2", re.I),  # HE-AAC
            (r"\b(WEB|Blu|DVD|DCP|B[DR]|HD) (DL|Ray|RIP|Rip|Rip|TS)\b", r"\1-\2", re.I),
        ]
        for pattern in replacements:
            if len(pattern) == 3:
                old, new, flags = pattern
                filename = re.sub(old, new, filename, flags=flags)
            else:
                old, new = pattern
                filename = re.sub(old, new, filename)
        return filename


    def extract_size_from_source_info(self, source_info):
        size_match = re.search(
            r"(?:^|\|)\s*(\d+(?:[.,]\d+)?)\s*([GMK]B)\b\s*(?:\||$)",
            source_info,
            flags=re.I,
        )
        size = f"{size_match[1]} {size_match[2]}" if size_match else ""
        return size


    def files_on_user_account(self, mode=1, from_cache=None):
        """Funkcja pobiera informacje z zakładki Notes oraz Historia,
        zwraca linki z Historii,
        dane z Notesu przerabia na tablicę,
        tworzy słownik o nazwie biblio_cache.
        """

        cache_key = f"{self.PROVIDER}.pl_{self.mynotepad_link}"
        notes_list = []
        biblio_cache = {}

        # Pobieranie notatek użytkownika
        if settings.getBool(f"{self.PROVIDER}.use_web_notebook_for_history"):
            biblio_links2 = []
            notes_page_content = self.session.get(self.base_link + self.mynotepad_link, headers=self.headers).text
            notes_value = client.parseDOM(notes_page_content, "textarea", attrs={"class": "notepad"})
            if notes_value:
                notes_value = notes_value[0]
                if notes_value.startswith("[") and notes_value.endswith("]"):
                    try:
                        notes_list = literal_eval(notes_value)
                    except Exception:
                        fflog("Uszkodzona struktura w Notesie!")
                else:
                    fflog("Uszkodzona struktura Notesu")

            # Rozpisanie danych pobranych z notesu
            for file_item in reversed(notes_list):  # zamiast [::-1]
                for url, data in file_item.items():
                    if url not in biblio_cache:
                        biblio_cache[url] = {}

                    try:
                        biblio_cache[url] = {
                            "filename": data[1],
                            "size": data[2],
                            "url": url,
                            "on_account_link": data[0],
                            "on_account_expires": data[3],
                            "source": re.sub(r"https?://(?:www\.)?([^.]+)\..+", r"\1", url, flags=re.I).upper(),
                        }
                    except Exception:
                        biblio_cache[url] = {}
                        fflog(f"Nie udało się pobrać wszystkich danych z notesu dla {url!r}")
                        fflog_exc()

        # Pobieranie historii biblioteki
        library_cache_key = f"{self.PROVIDER}.pl_{self.mylibrary_link}"

        html = self.session.get(self.base_link + self.mylibrary_link, headers=self.headers).text
        table = client.parseDOM(html, "table", attrs={"class": "list"})
        biblio_links = client.parseDOM(table, "input", ret="value") or []
        rows = client.parseDOM(table, "tr")[1:] if biblio_links else []

        biblio_links_exp = [client.parseDOM(row, "td")[3] for row in rows]
        biblio_links2 = list(zip(biblio_links, biblio_links_exp))

        # Synchronizacja Notesu z biblioteką
        if settings.getBool(f"{self.PROVIDER}.use_web_notebook_for_history"):
            # Skrócenie linków ???
            biblio_links1 = [(x.rpartition("/")[0] if "/sciagaj/" in x else x) for x in biblio_links]

            # "Synchronizacja" z biblioteką na stronie
            biblio_cache = {
                k: v
                for k, v in biblio_cache.items()
                if any(l in s for s in v.values() for l in biblio_links1)  # Szuka w stringu
            }

            # Odświeżenie Notesu
            notes_list = [
                n
                for n in notes_list
                if any(l in s for v in n.values() for s in v for l in biblio_links1)  # Szuka w stringu
            ]

            # Usunięcie linków, które są już w Notesie
            if notes_list:
                notepad_links = {i[0] for n in notes_list for v in n.values() for i in v}
                biblio_links2 = [l for l in biblio_links2 if l[0].rpartition("/")[0] not in notepad_links]

        return biblio_cache, biblio_links2, notes_list


    def check_if_file_is_on_user_account(self, biblio_links, links, filenames, biblio_cache=None):
        case = ""
        on_account = False
        on_account_expires = ""
        on_account_link = ""

        filename = filenames  # nie wiem czemu tu taki zapis (chyba tylko dla loga na końcu)
        ext_pat = f'({"|".join(self.VIDEO_EXTENSIONS)})'.replace(".", "")
        if isinstance(links, str):
            links = [links]
        # fflog(f'{len(links)=} {len(filenames)=} {filenames=}')
        for link in links:
            #fflog(f'{link=}')
            if biblio_cache:
                # na podstawie danych z notesu
                specific_biblio_cache = biblio_cache[link] if link in biblio_cache else None
                if not specific_biblio_cache:
                    if link.rpartition("/")[0] in biblio_cache:  # dla skracanych linków
                        specific_biblio_cache = biblio_cache[link.rpartition("/")[0]]
                if specific_biblio_cache:
                    on_account = True
                    on_account_link = specific_biblio_cache.get("on_account_link")
                    on_account_expires = specific_biblio_cache["on_account_expires"]
                    break

            if not on_account:
                # sprawdzenie starszą metodą
                # potrzebne, jak nie ma danych z cache lub są niekompletne (brak całej historii)
                # lub mimo wybrania opcj Notesu user "kupił" ze strony
                for i in range(len(biblio_links) - 1, -1, -1):
                    item_org = biblio_links[i]
                    item = item_org[0]
                    item = unescape(unquote(item.rstrip("/").split("/")[-1]))
                    item = item.replace('_', ' ')  # uproszczenie
                    # item = "".join(character for character in item if character.isalnum())
                    if "/twojplik.pl/" in link.lower():
                        item = re.sub(rf"\.[0-9A-F]{3}(\.{ext_pat})$", r".ZZZ\1", item)

                    url = unescape(unquote(link))  # badany oryginalny link
                    url = url.replace('_', ' ')  # uproszczenie
                    # url = "".join(character for character in url if character.isalnum())
                    if "/twojplik.pl/" in link.lower():
                        url = re.sub(rf"\.[0-9A-F]{3}(\.{ext_pat})$", r".ZZZ\1", url)

                    # fflog(f'{item=} {url=}')
                    if item in url:
                        on_account_link = item_org[0]
                        on_account_expires = item_org[1]
                        on_account = True
                        if on_account_link != link:
                            case += "*"  # bo można znaleźć nazwę z biblioteki w innym linku niż pierwotny, więc serwer też może być inny
                        del biblio_links[i]
                        break

            if on_account:
                break

        if not on_account:  # teraz test z nazwami plików

            if not on_account and filenames:  # porównanie z nazwą pliku widniejącą na liście
                for i in range(len(biblio_links) - 1, -1, -1):
                    item_org = biblio_links[i]
                    item = item_org[0]

                    if "/twojplik.pl/" in link.lower():  # serwery nie są mieszane, więc jakikolwiek z listy może być do wykrycia tegoż serwera
                        item = re.sub(rf"\.[0-9A-F]{3}(\.{ext_pat})$", r".ZZZ\1", item)  # najwyżej się nie wykona

                    filenames = [filenames] if isinstance(filenames, str) else filenames
                    for filename in filenames:
                        if not filename:
                            continue

                        if "/twojplik.pl/" in link.lower():
                            filename = re.sub(rf"\.[0-9A-F]{3}(\.{ext_pat})$", r".ZZZ\1", filename)  # ten sam pattern co wyżej

                        if unescape(unquote(filename)) in unescape(unquote(item)):
                            # dodatkowy warunek mogący pomóc, bo nie zawsze da się stwierdzić po url-u,
                            # gdyż np. linki do serwera "wplik" są zakodowane
                            # choć drobne ryzyko pomyłki istnieje, bo nie jest sprawdzany rozmiar czy serwer
                            # (strona nie podaje w tej zakładce ani serwera ani rozmiaru)
                            on_account_link = item_org[0]
                            on_account_expires = item_org[1]
                            on_account = True
                            case += "**"  # to co wyżej, tylko inny sposób porównywania
                            del biblio_links[i]
                            break
                    if on_account:
                        break

            if not on_account and filenames:
                for i in range(len(biblio_links) - 1, -1, -1):
                    item_org = biblio_links[i]
                    item = item_org[0]
                    if item[-3:] not in self.VIDEO_EXTENSIONS:  # gdy ucięty, jak dla "Flip i Flap Utopia"
                        # if "/twojplik.pl/" in link.lower():  # nie ma sensu, bo ucięty przecież jest
                            # item = re.sub(rf"\.[0-9A-F]{3}(\.{ext_pat})$", r"\1", item)
                        for filename in filenames:
                            if not filename:
                                continue
                            # if "/twojplik.pl/" in link.lower():  # też raczej nie ma sensu
                                # filename = re.sub(rf"\.[0-9A-F]{3}(\.{ext_pat})$", r"\1", filename)
                            if unquote(item.rpartition("/")[-1]) in filename:
                                on_account_link = item_org[0]
                                on_account_expires = item_org[1]
                                on_account = True
                                case += "***"  # ze względu na to, że to nie musi być ten serwer i ten link
                                del biblio_links[i]
                                break
                        if on_account:
                            break

        if on_account_expires:
            if case:
                try:
                    from datetime import datetime
                    on_account_expires = datetime.strptime(on_account_expires, "%H:%M %d.%m.%Y").strftime("%A %H:%M")
                except Exception:
                    fflog_exc()
                    pass
            on_account_expires = source_utils.months_to_miesiace(on_account_expires, short=1)
            on_account_expires = re.sub(r"0(\d)(?=:\d\d)", r"\1", on_account_expires)

        # fflog(f'koniec {on_account=} {on_account_link=} {case=} {link=} {filename=}')
        return on_account, on_account_link, case, on_account_expires

    def check_and_add_on_account_sources(self, sources: List[Source], ffitem: 'FFItem', source_name: str):
        fflog(f'Checking on-account status for cached sources from {source_name}')
        try:
            self.login()
            biblio_cache, biblio_links = self.files_on_user_account(from_cache=False)[:2]
            cached_links = set()
            for s in sources:
                urls = [s.url, *s.get('alt_links', ())]
                filenames = [s.get('filename')] + s.get('alt_filenames', [])
                on_account, link, case, expires = self.check_if_file_is_on_user_account(
                    biblio_links, urls, filenames, biblio_cache
                )
                if on_account:
                    s.update({
                        'on_account': True,
                        'on_account_link': link,
                        'on_account_expires': expires,
                    })
                    if case and case not in s['hosting']:
                        s['hosting'] += case
                    cached_links.add(link)

            for bc_item in biblio_cache.values():
                link = bc_item.get('on_account_link')
                if link and link not in cached_links:
                    filename = bc_item.get('filename')
                    quality = source_utils.check_sd_url(filename)
                    lang, info = source_utils.get_lang_by_type(filename)
                    new_source = {
                        'source': bc_item.get('source', source_name),
                        'quality': quality,
                        'language': lang,
                        'url': bc_item.get('url'),
                        'info': info,
                        'size': bc_item.get('size'),
                        'direct': True,
                        'debridonly': False,
                        'filename': filename,
                        'on_account': True,
                        'on_account_expires': bc_item.get('on_account_expires'),
                        'on_account_link': link,
                        'alt_links': [],
                        'alt_filenames': [],
                        'premium': True,
                    }
                    sources.append(Source.from_provider_dict(provider=source_name, ffitem=ffitem, item=new_source))
                    fflog(f"Added on-account source from notepad: {filename}")

        except Exception:
            fflog_exc(f'Failed to check/add on-account status for cached {source_name} sources')

    def login(self):
        fflog('sprawdzenie czy zalogowany', 0)

        try:
            var = cache.cache_get(f"{self.PROVIDER}_cookie", control.providercacheFile)
            cookies = '' if var is None else var["value"]
            cookie_time = 0 if var is None else int(var.get("date", 0))  # Pobranie czasu zapisu cookies
        except Exception:
            fflog_exc()
            cookies = ""
            cookie_time = 0

        # Sprawdzenie, czy cookies są aktualne (mniej niż 3 godziny)
        if cookies and (int(time.time()) - cookie_time) < (3 * 60 * 60):
            fflog('użytkownik jest już zalogowany', 0)
            self.headers.update({"Cookie": cookies})
            return

        # Logowanie użytkownika
        if self.user_name and self.user_pass:
            fflog("potrzeba zalogowania na konto", 0)
            self.session.post(
                self.base_link + self.login_link,
                verify=False,
                allow_redirects=False,
                data={"login": self.user_name, "password": self.user_pass},
            )
            result = self.session.get(self.base_link).text

            if self.user_name in result:
                fflog('zalogowano poprawnie', 0)
                cookies = self.session.cookies
                cookies = "; ".join([str(x) + "=" + str(y) for x, y in cookies.items()])
                cache.cache_insert(f"{self.PROVIDER}_cookie", cookies, control.providercacheFile)  # Bez ręcznego dodawania date
                self.headers.update({"Cookie": cookies})
            else:
                fflog("logowanie nieudane!")
                control.infoDialog('logowanie nieudane', f'{self.PROVIDER}', 'ERROR')
        else:
            fflog("BRAK danych do zalogowania! - sprawdź ustawienia")
            control.infoDialog('BRAK danych do zalogowania! - sprawdź ustawienia', f'{self.PROVIDER}', 'ERROR')

    def _fetch_remaining_limit(self):
        try:
            limit_info_html = self.session.get(self.base_link, headers=self.headers).text
            limit_info_div = client.parseDOM(limit_info_html, "div", attrs={"class": "textPremium"})
            limit_info_b = client.parseDOM(limit_info_div, "b")
            if limit_info_b:
                remaining_limit_str = str(limit_info_b[-1])
                remaining_limit_str = re.sub(r"\s*\w+\s*=\s*([\"']?).*?\1(?=[\s>]|$)\s*", "", remaining_limit_str)
                remaining_limit_str = re.sub("<[^>]+>", "", remaining_limit_str)
                # Zamiana przecinka na kropkę, jeśli występuje
                remaining_limit_str = remaining_limit_str.replace(",", ".")
                # Przelicz na MB
                self.remaining_limit_mb = int(source_utils.convert_size_to_bytes(remaining_limit_str) / (1024 * 1024))
                fflog(f"Dostępny limit: {self.remaining_limit_mb} MB")
        except Exception:
            fflog_exc("Nie udało się pobrać informacji o limicie")


class Tb7(_source):
    """Scraper for tb7."""
    PROVIDER: ClassVar[str] = 'tb7'
    URL: ClassVar[str] = 'https://www.tb7.pl'


class Xt7(_source):
    """Scraper for xt7."""
    PROVIDER: ClassVar[str] = 'xt7'
    URL: ClassVar[str] = 'https://www.xt7.pl'


def register(sources: List[SourceModule], group: str) -> None:
    """Register all scrapers."""
    from lib.sources import SourceModule
    for src in (Tb7, Xt7):
        sources.append(SourceModule(name=src.PROVIDER, provider=src(), group=group))
