"""
    FanFilm Project
"""

import os
import re
from urllib.parse import parse_qs, urlencode, quote_plus, unquote

from lib.ff import cleantitle, control, source_utils
from lib.ff.settings import settings
from lib.ff.log_utils import fflog, fflog_exc


class source:

    # Mark sources with prem.color.identify2 setting
    use_premium_color: bool = True

    def __init__(self):
        self.priority = 1
        self.language = ["pl"]
        self.ext = ["mp4", "mkv", "flv", "avi", "mpg"]
        self.movie_path = settings.getString("movie.download.path")
        self.tv_path = settings.getString("tv.download.path")
        self.other_folder = settings.getBool('download.other_folder')
        self.other_path = settings.getString('download.other_folder_path')
    def movie(self, imdb, title, localtitle, aliases, year):
        try:
            #fflog(f'{title=} {localtitle=} {year=} {aliases=}')
            originalname = [a for a in aliases if "originalname" in a]
            originalname = originalname[0]["originalname"] if originalname else ""
            """
            #title = re.sub(" ", "", title)  # why? downloader tego nie ma
            transname = title
            # transname = cleantitle.normalize(transname)  # polskie znaki diakrytyczne
            transname = re.sub(r"/|:|\*|\?|\"|<|>|\+|,|\.|", "", transname)
            transname += " (%s)" % year
            """
            dest = self.movie_path
            dest = control.transPath(dest)
            #dest = os.path.join(dest, transname)

            #return urlencode({"imdb": imdb, "title": title, "localtitle": localtitle, "year": year, "path": dest, "filename": transname, })
            return urlencode({"imdb": imdb, "title": title, "localtitle": localtitle, "originalname": originalname, "year": year, "path": dest, "aliases": aliases })
        except Exception:
            fflog_exc()


    def tvshow(self, imdb, tvdb, tvshowtitle, localtvshowtitle, aliases, year):
        try:
            # fflog(f'{tvshowtitle=} {localtvshowtitle=} {year=} {aliases=} {imdb=} {tvdb=}')
            originalname = [a for a in aliases if "originalname" in a]
            originalname = originalname[0]["originalname"] if originalname else ""
            url = {"imdb": imdb, "tvdb": tvdb, "tvshowtitle": tvshowtitle, "localtvshowtitle": localtvshowtitle, "originalname": originalname, "year": year}
            url = urlencode(url)
            return url
        except Exception:
            #log_utils.log("pobrane - Exception", "sources")
            fflog_exc()


    def episode(self, url, imdb, tvdb, title, premiered, season, episode):
        try:
            # fflog(f'{url=}  {imdb=} {tvdb=} {title=} {premiered=} {season=} {episode=}')
            if url is None:
                return

            url = parse_qs(url)
            url = dict([(i, url[i][0]) if url[i] else (i, "") for i in url])
            r"""
            transname = url["tvshowtitle"]
            transname = cleantitle.normalize(transname)  # polskie znaki diakrytyczne
            #transname = unquote(quote_plus(re.sub(r"/|:|\*|\?|\"|<|>|", "", transname, )))
            transname = re.sub(r"/|:|\*|\?|\"|<|>|", "", transname)
            transname += f' ({url.get("year")})' if url.get("year") else ''  # dodanie roku do nazwy folderu i pliku
            """
            #transname = ""
            dest = self.tv_path
            dest = control.transPath(dest)
            #dest = os.path.join(dest, transname)
            #dest = os.path.join(dest, "Season %01d" % int(season))  # przeniosłem do funkcji sources
            # fflog(f'{url}')
            (url["title"], url["localtitle"], url["year"], url["premiered"], url["season"], url["episode"], url["path"], url["originalname"],) = (
                url["tvshowtitle"], url["localtvshowtitle"], url["year"], premiered, season, episode, dest, url["originalname"] )
            # fflog(f'{url}')
            url = urlencode(url)
            return url
        except Exception:
            fflog_exc()


    def sources(self, url, hostDict, hostprDict):
        sources = []
        # fflog(f'{url=}')
        try:
            if url is None:
                return sources

            data = parse_qs(url)
            data = dict([(i, data[i][0]) if data[i] else (i, "") for i in data])
            # fflog(f'{data=}')

            paths = []
            base_path = data.get("path")
            if base_path:
                paths.append(base_path)

            if self.other_folder and self.other_path:
                dest = self.other_path
                dest = control.transPath(dest)
                if dest not in paths:
                    paths.append(dest)

            if not paths:
                return sources

            #filename = data.get("filename", "")  # wyeliminować
            filename1 = data["title"]
            filename2 = data["localtitle"]
            filename3 = data.get("originalname", "")
            #fflog(f'{filename1=} {filename2=} {filename3=}')
            filenames = [filename1, filename2, filename3]
            # fflog(f'{filenames=}')
            filenames = list(filter(None, filenames))  # usunięcie pustych
            filenames = list(dict.fromkeys(filenames))
            # fflog(f'{filenames=}')

            year = data["year"] or ""
            # fflog(f'{year=}')

            year_in_title = my[0] if (my := re.search(r'\b\d{4}\b', filename1)) else ""  # wykrycie, czy tytuł zawiera jakiś rok w swojej nazwie
            # fflog(f'{year_in_title=}')

            ep_in_title = my[0] if (my := re.search(r'\b\d{1,2}\b', filename1)) else ""  # wykrycie, czy tytuł zawiera jakiś numer w swojej nazwie
            # fflog(f'{ep_in_title=}')

            r"""
            if "tvshowtitle" in data:
                #filename = re.sub(r"\+", " ", data["filename"])  # pozbycie się plusów z nazwy ? a czemu nie przez zwykłe replace ?
                filename += " S%02dE%02d" % (int(data["season"]), int(data["episode"]),)
            else:
                #filename = data["filename"]
                pass
            """
            if "episode" in data:
                for f in filenames[:]:
                    f += " (%s)" % year if year else ""  # dodanie roku
                    # filenames += [f]  # czy to jest niezbędnę? Dla seriali ma (bo po roku występuje nr odcinka), a dla filmów z powodu sposobu dopasowywania nazwy, to bez znaczenia

            episodes_notations = []
            if "episode" in data:
                # filenames = [t+" S%02dE%02d" % (int(data["season"]), int(data["episode"]),) for t in filenames]
                #path = os.path.join(path, "Season %01d" % int(season))  # przeniosłem do pętli niżej
                episodes_notations += ["S%02dE%02d" % (int(data["season"]), int(data["episode"]),)]
                if int(data["season"]) == 1:
                    episodes_notations += ["E%02d" % (int(data["episode"]),)]
                    episodes_notations += ["ep%02d" % (int(data["episode"]),)]
                    episodes_notations += ["%02d" % (int(data["episode"]),)]
                    if int(data["episode"]) < 10:
                        episodes_notations += ["%d" % (int(data["episode"]),)]
                        pass
            # fflog(f'{episodes_notations=}')
            episodes_notations_pat = "|".join(episodes_notations)
            episodes_notations_pat = rf"\b({episodes_notations_pat})\b" if episodes_notations_pat else ""
            # fflog(f'{episodes_notations_pat=}')

            for f in filenames[:]:
                #f = re.sub(r"/|:|\*|\?|\"|<|>|\+|,|\.|", "", f)
                f = re.sub(r'\/:*?"<>|', "", f)  # niedozwolone znaki w systemie Windows
                #f = cleantitle.normalize(cleantitle.getsearch(file1))
                filenames += [f]
            """
            for f in filenames[:]:
                f = cleantitle.normalize(f)  # polskie znaki diakrytyczne
                filenames += [f]
            """

            filenames = [re.sub(" {2,}", " ", (
                            cleantitle.normalize(cleantitle.getsearch(t)).
                            replace(".", " ").replace("_", " ")
                        )).strip()
                        for t in filenames]  # aby było łatwiej porównywać

            filenames = list(dict.fromkeys(filenames))  # usunięcie duplikatów

            # filenames = filenames[::-1]  # opcjonalnie

            # fflog(f'{filenames=}')

            url = None
            urls = []

            for path in paths:
                # fflog(f'Checking path: {path}')
                if os.path.exists(path):
                    # fflog(f'wariant 1')
                    for r, d, f in os.walk(path):  # (folder nadrzędny, katalogi, pliki)
                        # fflog(f'{r=} {d=} {f=}')
                        for file in f:
                            # fflog(f' {file=}')
                            file1 = file
                            file1 = cleantitle.normalize(cleantitle.getsearch(file1))
                            file1 = file1.replace(".", " ").replace("_", " ")
                            file1 = re.sub(" {2,}", " ", file1).strip()
                            # fflog(f"Comparing: filenames={filenames}, file1='{file1}'")
                            # fflog(f'{file1=}')
                            # fflog(f'{filename=} {file=} {file1=}')
                            # if filename in file or filename1 in file or filename2 in file:
                            # if filename in file or filename in re.sub(r" \[.*\]", "", file):  # nie ma takiej potrzeby, bo te oznaczenia są na końcu nazwy
                            z = [f for f in filenames if f.lower() in file1.lower()]  # idealne to nie jest (idealnie, to byłoby tak, jak w tb7 czy rapideo)
                            if z:
                                # fflog(f'{z=}')  # kontrolnie
                                #file = z[0]  # nie można tego
                                # fflog(f' {file=}')
                                if year and (mr := re.search(r'\b\d{4}\b', file.replace(year_in_title, "", 1))):
                                    #if not f'({year})' in file:
                                    #if not f'{year}' in file:
                                    if not re.search(rf'\b{year}\b', file):
                                        # fflog(f'nie pasuje szukany {year=} do roku znalezionego w pliku ({mr[0]})')
                                        continue
                                if episodes_notations:
                                    #if not any(e.lower() in file.lower() for e in episodes_notations):
                                    if not re.search(episodes_notations_pat, file.replace(ep_in_title, "", 1), flags=re.I):
                                        # fflog(f'brak w nazwie pliku pasującego numeru odcinka  {file=}')
                                        continue
                                # fflog(f'{self.ext=}')
                                # fflog(f'{[file.endswith(ext) for ext in self.ext]=}')
                                if any(file.endswith(f".{ext}") for ext in self.ext):
                                    # fflog(f'{r=} {file=}')
                                    url = os.path.join(r, file)
                                    # fflog(f'OK 1')
                                    urls.append(url)
                                    #break  # tylko 1 szukamy
                                else:
                                    fext = file.rpartition(".")[-1]
                                    fflog(f'niedozwolone rozszerzenie pliku ({fext=})')
                                    pass
                            else:
                                # fflog(f'dupa 1')
                                pass
                else:
                    fflog(f'NIE MA takiego folderu {path=}')
                    pass
                """
                już nie trzeba tego, bo zmieniłem sposób szukania
                # dla kompatybilności z wcześniej pobranymi, gdzie rok nie był zapisywany
                if not url and os.path.exists(path.replace(f" ({year})", "")):
                    fflog(f'wariant 2')
                    filename = filename.replace(f" ({year})", "")
                    for r, d, f in os.walk(path.replace(f" ({year})", "")):
                        for file in f:
                            # fflog(f'{filename=} {file=}')
                            if filename in file.replace(f" ({year})", ""):  # tu trzeba, bo rok dla serialu jest w "środku" (przed numerem odcinka)
                                if [file.endswith(ext) for ext in self.ext]:
                                    url = os.path.join(r, file)
                                    #fflog(f'OK 2')
                                    break
                            else:
                                #fflog(f'dupa 2')
                                pass

                # jeszcze trzeba zrobić wariant, dla nazw, które mają na końcu identyfikator z bazy serwisu internetowego,
                # np. "/Blade Runner (2017) {tmdb=335984}/Blade Runner (2017) {tmdb=335984}.mkv"
                # https://kodi.wiki/view/Naming_video_files/Movies
                """

            if urls or url:
                for url in urls:
                    # fflog(f'{url=}')

                    # pewnie jest jakaś funkcja do tego, na razie tak
                    filename = url.rpartition("/")[-1]
                    filename = filename.rpartition("\\")[-1]

                    size = None
                    import xbmcvfs
                    try:
                        st = xbmcvfs.Stat(url)  # chyba to samo co os.stat(file_name with path)
                        size = st.st_size()
                        # fflog(f'w1 {size=}')
                    except Exception:
                        try:
                            with xbmcvfs.File(url) as f:
                                size = f.size()
                            # fflog(f'w2 {size=}')
                        except Exception:
                            pass
                    size = source_utils.convert_size(size)

                    quality = source_utils.check_sd_url(filename)
                    # fflog(f'{quality=}')

                    # info0 = m[1] if (m := re.search(r" \[(.*)\]", filename)) else ""  # pozyskane z nawiasów kwadratowych
                    # all_infos = re.findall(r"\s*\[(.*?)\]", filename)  # może też być każdy parametr w innym nawiasie
                    all_infos = []  # rezygnuje z powyższego, bo te parametry są wykrywane w sources.py
                    info0 = " / ".join(all_infos)
                    # fflog(f'{info0=}')

                    lang, lang_info = source_utils.get_lang_by_type(filename) or ("PL", "PL")

                    info = re.sub(rf"\s*({lang}|{quality})\b", "", info0,  flags=re.I)
                    info = re.sub(r"^\s[/|]\s|\s[/|]\s$|[/|]\s(?=[/|])", "", info)  # porządki
                    info += f" / {lang_info}" if lang_info and lang_info not in info else ""
                    info = info.lstrip(" / ")

                    sources.append({
                        # "source": "download",  # powtrzenie nazwy, ale po co?
                        "source": "",  # aby nie dublować słowa, bo "provider" będzie i tak "pobrane"
                        "quality": quality,
                        "language": "pl",
                        "url": url,
                        "info": info,
                        "size": size,
                        "direct": True,
                        "debridonly": False,
                        "filename": filename,
                        "local": True
                    })

            fflog(f'przekazano źródeł: {len(sources)}')
            return sources
        except Exception:
            # log_utils.log("pobrane - Exception", "sources")
            fflog_exc()
            return sources


    def resolve(self, url):
        # fflog(f'{url=}')
        return url
