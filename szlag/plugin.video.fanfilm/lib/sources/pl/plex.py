"""
    FanFilm Add-on  2021
    Źródło Plex
    Wymagany plugin composite z repozytorium Kodi
"""

import pickle
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, quote, urlencode

from lib.ff import requests
import xbmcaddon
import xbmcvfs

from lib.ff import control, source_utils
from lib.ff.log_utils import fflog

composite_plugin = "plugin.video.composite_for_plex"
composite_enabled = control.condVisibility("System.AddonIsEnabled(%s)" % composite_plugin)
if composite_enabled:
    COMPOSITE_ADDON = xbmcaddon.Addon(id=composite_plugin)
    icon = xbmcaddon.Addon(composite_plugin).getAddonInfo('icon')
COMPOSITE_PATH = f"special://profile/addon_data/{composite_plugin}/cache/servers/"
CACHE_NAME = "plexhome_user.pcache"


def get_composite_cache(cache=""):
    cache_path = xbmcvfs.translatePath(COMPOSITE_PATH)
    try:
        cache = xbmcvfs.File(cache_path + CACHE_NAME)
    except FileNotFoundError:
        return False, None

    try:
        cache_data = cache.readBytes()
    except Exception as error:
        print(f"CACHE [{cache}]: read error [{error}]")
        cache_data = False
    finally:
        cache.close()
    if cache_data:
        if isinstance(cache_data, str):
            cache_data = cache_data.encode("utf-8")
        print(f"CACHE [{cache}]: read")
        try:
            cache_object = pickle.loads(cache_data)
        except (ValueError, TypeError):
            return False, None
        return True, cache_object


class source:

    # This class has support for *.color.identify2 setting
    has_color_identify2: bool = True
    # Mark sources with prem.color.identify2 setting
    use_premium_color: bool = True

    def __init__(self):
        self.priority = 1
        self.language = ["pl"]
        self.domains = ["plex.tv"]
        self.base_link = "https://plex.tv"
        self.server_url = "{scheme}://{IP}:{port}{path}"
        self.search_link = "{scheme}://{IP}:{port}/{path}?query={query}"
        self.plex_API = "https://plex.tv//api/resources?includeHttps=1"
        self.composite_pattern = (
            "plugin://plugin.video.composite_for_plex/?url={uri}{key}&mode=5"
        )
        self.session = requests.session()
        self.UUID = str(uuid.uuid4())

        if composite_enabled:
            cache_data = get_composite_cache(CACHE_NAME)
            if cache_data is None:
                self.cache_status = False
                return

            self.cache_status, self.cache_token = cache_data
            if not self.cache_status:
                return
            self.token = self.cache_token["myplex_user_cache"].split("|")[1]
            self.headers = {
                "X-Plex-Client-Identifier": self.UUID,
                "X-Plex-Product": COMPOSITE_ADDON.getAddonInfo("name"),
                "X-Plex-Token": self.token,
            }

            r = self.session.get(self.plex_API, headers=self.headers)
            self.servers = []
            server_list = ET.fromstring(r.text)
            devices = server_list.iter("Device")
            for device in devices:
                try:
                    server = {}
                    server["name"] = device.get("name")
                    server["accessToken"] = device.get("accessToken")
                    server.update(device.find('./Connection[@local="0"]').attrib)
                    self.servers.append(server)
                except Exception:
                    continue

            fflog(
                f"Plex enabled - found: {len(server_list)} servers"
            )

        else:
            self.cache_status = False

    def movie(self, imdb, title, localtitle, aliases, year):
        try:
            if not composite_enabled:
                return
            if not self.cache_status:
                return
            url = {"imdb": imdb, "title": title, "localtitle": localtitle, "year": year}
            url = urlencode(url)
            return url
        except Exception:
            return

    def tvshow(self, imdb, tmdb, tvshowtitle, localtvshowtitle, aliases, year):
        try:
            if not composite_enabled:
                return
            if not self.cache_status:
                return
            url = {
                "imdb": imdb,
                "tmdb": tmdb,
                "tvshowtitle": tvshowtitle,
                "localtvshowtitle": localtvshowtitle,
                "year": year,
            }
            url = urlencode(url)
            return url
        except Exception:
            return

    def episode(self, url, imdb, tmdb, title, premiered, season, episode):
        try:
            if url is None:
                return
            url = parse_qs(url)
            url = dict([(i, url[i][0]) if url[i] else (i, "") for i in url])
            url["title"], url["premiered"], url["season"], url["episode"] = (
                title,
                premiered,
                season,
                episode,
            )
            url = urlencode(url)
            return url
        except Exception:
            return

    def parse_source_data(self, server, xml):
        src = server
        src["key"] = xml.get("key")
        src.update(xml.find("./Media").attrib)
        src["file"] = xml.find(".//Part").get("file").split("/")[-1]
        src["videoinfo"] = (
            src["videoCodec"] + " " + src["videoFrameRate"] + " " + src["container"]
        )
        src["audioinfo"] = src["audioCodec"] + " " + src["audioChannels"] + "CH "
        src["language"], src["lang_type"] = self.get_lang_by_type(src["file"])

        return src

    def sources(self, url, hostDict, hostprDict):
        try:
            sources = []
            if url is None:
                return sources
            url = parse_qs(url)
            url = dict([(i, url[i][0]) if url[i] else (i, "") for i in url])

            if not composite_enabled:
                return sources
            if not self.cache_status:
                return sources
            for server in self.servers:
                if "tvshowtitle" in url:
                    titles = [url["tvshowtitle"], url["localtvshowtitle"]]
                    try:
                        self.headers["X-Plex-Token"] = server["accessToken"]
                        for title in titles:
                            try:
                                build_url = self.search_link.format(
                                    scheme=server["protocol"],
                                    IP=server["address"],
                                    port=server["port"],
                                    path="search",
                                    query=quote(title),
                                )
                                r = self.session.get(
                                    build_url,
                                    headers=self.headers,
                                    verify=False,
                                    timeout=3,
                                )
                                show = ET.fromstring(r.text)
                                shows = [s.get('key') for s in show.findall("./Directory")]
                                kategories = [s.get('librarySectionTitle') for s in show.findall("./Directory")]
                                fflog(f'Znaleziono {len(shows)} pasujące Kategorie {kategories!r}')
                                #show = show.find("./Directory").get("key")
                                if isinstance(show[0], str):
                                    break
                            except AttributeError:
                                continue
                            except requests.Timeout:
                                fflog(
                                    f'Plex connection timeout for server: {server["name"]} ',
                                )
                        ##
                        for show in shows:
                            seas_url = self.server_url.format(
                                scheme=server["protocol"],
                                IP=server["address"],
                                port=server["port"],
                                path=show,
                            )
                            seas_list = self.session.get(
                                seas_url, headers=self.headers, verify=False, timeout=3
                            )
                            seas = ET.fromstring(seas_list.text)
                            try:
                                ep_path = seas.find(
                                    f'./Directory[@title="Season {url["season"]}"]'
                                ).get("key")
                            except AttributeError:
                                fflog(f'Sezon {url["season"]} nie znaleziony')
                                continue

                        ep_url = self.server_url.format(
                            scheme=server["protocol"],
                            IP=server["address"],
                            port=server["port"],
                            path=ep_path,
                        )
                        ep_list = self.session.get(
                            ep_url, headers=self.headers, verify=False, timeout=3
                        )
                        episodes = ET.fromstring(ep_list.text)
                        episodes = episodes.findall(
                            f'./Video[@type="episode"][@index="{url["episode"]}"]'
                            f'[@parentTitle="Season {url["season"]}"]'
                        )

                        for episode in episodes:
                            src = self.parse_source_data(server, episode)

                            sources.append(
                                {
                                    "source": src["name"],
                                    "quality": source_utils.get_quality(
                                        src["videoResolution"]
                                    ),
                                    "language": src["language"],
                                    "url": self.composite_pattern.format(
                                        uri=src["uri"], key=src["key"]
                                    ),
                                    "info": src["videoinfo"]
                                    + " | "
                                    + src["audioinfo"]
                                    + "| "
                                    + src["lang_type"],
                                    "direct": True,
                                    "debridonly": False,
                                    "icon": icon,
                                }
                            )

                    except Exception as e:
                        fflog("Plex Series parse error:")
                        fflog(e)
                        pass
                else:
                    titles = [url["title"], url["localtitle"]]
                    self.headers["X-Plex-Token"] = server["accessToken"]
                    for title in titles:
                        try:
                            build_url = self.search_link.format(
                                scheme=server["protocol"],
                                IP=server["address"],
                                port=server["port"],
                                path="search",
                                query=quote(title),
                            )

                            r = self.session.get(
                                build_url, headers=self.headers, verify=False, timeout=3
                            )

                            results = ET.fromstring(r.text)
                            results = results.findall(
                                f'./Video[@type="movie"][@year="{url["year"]}"]'
                            )
                            if not results:
                                continue
                            for result in results:
                                src = self.parse_source_data(server, result)

                                sources.append(
                                    {
                                        "source": src["name"],
                                        "quality": source_utils.get_quality(
                                            src["videoResolution"]
                                        ),
                                        "language": src["language"],
                                        "url": self.composite_pattern.format(
                                            uri=src["uri"], key=src["key"]
                                        ),
                                        "info": src["videoinfo"]
                                        + " | "
                                        + src["audioinfo"]
                                        + "| "
                                        + src["lang_type"],
                                        "direct": True,
                                        "debridonly": False,
                                    }
                                )

                        except requests.Timeout:
                            print(
                                f'Plex connection timeout for server {server["name"]}'
                            )
                            pass

        except Exception as e:
            fflog("Plex source:")
            fflog(e)
            return

        return sources

    def resolve(self, url):
        return url

    def get_lang_by_type(self, lang_type):
        if "dubbing" in lang_type.lower():
            if "kino" in lang_type.lower():
                return "pl", "Dubbing Kino"
            return "pl", "Dubbing"
        elif "lektor pl" in lang_type.lower():
            return "pl", "Lektor"
        elif ".dual" in lang_type.lower():
            return "pl", "multi"
        elif ".multi" in lang_type.lower():
            return "pl", "multi"
        elif ".pldub" in lang_type.lower():
            return "pl", "Dubbing"
        elif ".pl." in lang_type.lower():
            return "pl", ""
        elif ".sub" in lang_type.lower():
            return "pl", "Napisy"
        elif "lektor" in lang_type.lower():
            return "pl", "Lektor"
        elif "napisy pl" in lang_type.lower():
            return "pl", "Napisy"
        elif "napisy" in lang_type.lower():
            return "pl", "Napisy"
        elif "POLSKI" in lang_type.lower():
            return "pl", ""
        elif "pl" in lang_type.lower():
            return "pl", ""
        return "en", ""
