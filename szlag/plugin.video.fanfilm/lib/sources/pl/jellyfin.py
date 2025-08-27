"""
    FanFilm Add-on  2021
    Źródło Jellyfin
    Wymagany plugin plugin.video.jellycon lub plugin.video.jellyfin
    z repozytorium https://kodi.jellyfin.org
"""


import xml.etree.ElementTree as ET
from urllib.parse import urlencode, parse_qs
import json
from lib.ff import requests
import xbmcaddon
import xbmcvfs

from lib.ff import control, source_utils
from lib.ff.settings import settings
from lib.ff.log_utils import fflog, log_exc
from lib.ff.source_utils import convert_size


jellycon_plugin = "plugin.video.jellycon"
jellycon_enabled = control.condVisibility(f"System.AddonIsEnabled({jellycon_plugin})")
jellyfin_plugin = "plugin.video.jellyfin"
jellyfin_enabled = control.condVisibility(f"System.AddonIsEnabled({jellyfin_plugin})")
if jellycon_enabled:
    CACHE_NAME = "auth.json"
    jelly_pattern = f"plugin://{jellycon_plugin}/?item_id={{}}&mode=PLAY"
    jelly_plugin = jellycon_plugin
    plugin_active = True
    icon = xbmcaddon.Addon(jellycon_plugin).getAddonInfo('icon')

elif jellyfin_enabled:
    CACHE_NAME = "data.json"
    jelly_pattern = f'plugin://{jellyfin_plugin}/?id={{}}&mode=play&server=None'
    jelly_plugin = jellyfin_plugin
    plugin_active = True
    icon = xbmcaddon.Addon(jellyfin_plugin).getAddonInfo('icon')
else:
    CACHE_NAME = '---'
    jelly_pattern = '---'
    jelly_plugin = '---'
    plugin_active = False

JELLYFIN_PATH = f"special://profile/addon_data/{jelly_plugin}/"


class source:
    # This class has support for *.sort.order setting
    has_sort_order: bool = False
    # This class has support for *.color.identify2 setting
    has_color_identify2: bool = True
    # Mark sources with prem.color.identify2 setting
    use_premium_color: bool = True

    def __init__(self):
        self.priority = 1
        self.language = ["pl"]
        self.domains = ["jellyfin"]
        self.search_url = "{server}/Search/Hints?searchTerm={query}"
        self.item_info_url = '{server}/Items/{ItemID}/PlaybackInfo?userId={User_ID}'
        self.jellyfin_pattern = jelly_pattern
        self.session = requests.session()
        if jellycon_enabled or jellyfin_enabled:
            self.servers = self.get_jellyfin_cache()
            if not self.servers:
                return
            fflog(f"Jellyfin enabled")

    def movie(self, imdb, title, localtitle, aliases, year):

        try:
            if not self.cache_status:
                return
            url = {"imdb": imdb, "title": title, "localtitle": localtitle, "year": year}
            url = urlencode(url)
            return url
        except Exception:
            return

    def tvshow(self, imdb, tmdb, tvshowtitle, localtvshowtitle, aliases, year):

        try:
            if not self.cache_status:
                return
            url = {"imdb": imdb, "tmdb": tmdb, "tvshowtitle": tvshowtitle, "localtvshowtitle": localtvshowtitle,
                "year": year, }
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
            url["title"], url["premiered"], url["season"], url["episode"] = (title, premiered, season, episode,)
            url = urlencode(url)
            return url
        except Exception:
            return

    def get_jellyfin_cache(self):

        cache_path = xbmcvfs.translatePath(JELLYFIN_PATH) or JELLYFIN_PATH
        self.cache_status = False

        try:
            cache = xbmcvfs.File(cache_path + CACHE_NAME)
        except FileNotFoundError:
            fflog('Niezalogowany do wtyczki Jellycon')
            return None
        cached_data = cache.read()
        cached_data = json.loads(cached_data)
        cache.close()
        if jellycon_enabled:
            try:
                settings = ET.parse(cache_path + 'settings.xml')
                user = settings.find('./setting[@id="username"]').text
                server = settings.find('./setting[@id="server_address"]').text
            except Exception:
                fflog('Brak Danych użytkownika lub serwera - sprawdż ustawienia Jellycon')
                return None
            cache_data = cached_data.get(user)
            server_name = self.session.get(f'{server}/System/Info',
                                           headers={"X-Emby-Token": cache_data['token']}).json()
            cache_data.update({'server_address': server,
                               'server_name': server_name['ServerName']})
            cache_data = [cache_data]
        elif jellyfin_enabled:
            try:
                cache_data = [{'server_address': i['address'],
                               'token': i['AccessToken'],
                               'user_id': i['UserId'],
                               'server_name': i['Name']}
                              for i in cached_data['Servers'] if 'AccessToken' in i]
            except IndexError:
                print('Brak Danych użytkownika lub serwera - sprawdż ustawienia Jellyfin')
                return None
        self.cache_status = True
        return cache_data

    def sources(self, url, hostDict, hostprDict):
        try:
            sources = []
            if url is None:
                return sources
            url = parse_qs(url)
            url = dict([(i, url[i][0]) if url[i] else (i, "") for i in url])

            if not plugin_active:
                return sources

            if not self.cache_status:
                return sources
            for server in self.servers:
                headers = {"X-Emby-Token": server['token'],
                           "content-type": "aplication/json"
                           }
                if "tvshowtitle" in url:
                    titles = [url["tvshowtitle"], url["localtvshowtitle"]]
                    try:
                        for title in titles:
                            search_url = self.search_url.format(server=server['server_address'],
                                                                query=title)
                            res = self.session.get(search_url, headers=headers).json()
                            results = res.get('SearchHints')
                            match_id = [i.get('ItemId') for i in results if
                                        (i.get('ProductionYear') == int(url['year'])
                                        and i.get('Type') == 'Series'
                                        and i.get('Name') == title)]
                            if not match_id:
                                continue
                            for id in match_id:
                                tvshow_url = f'''{server['server_address']}/Shows/{{}}/Episodes?season={url['season']}'''
                                src = self.session.get(tvshow_url.format(id), headers=headers).json()
                                if not src['Items']:
                                    continue
                                episode = [i.get('Id') for i in src['Items'] if i['IndexNumber'] == int(url['episode'])][0]
                                info_url = self.item_info_url.format(server=server['server_address'],
                                                                     ItemID=episode,
                                                                     User_ID=server['user_id'])
                                src = self.session.get(info_url, headers=headers).json()

                                src = src.get('MediaSources')[0]
                                v_info = [s for s in src.get('MediaStreams')
                                          if s.get('Type') == 'Video'][0]
                                a_info = [s for s in src.get('MediaStreams')
                                          if s.get('Type') == 'Audio'][0]
                                size = convert_size(src.get('Size'))
                                sources.append(
                                    {"source": server['server_name'],
                                     "quality": source_utils.get_release_quality(v_info.get('DisplayTitle'))[0],
                                     "language": source_utils.get_lang_by_type(src['Name'])[0],
                                     "url": self.jellyfin_pattern.format(episode),
                                     "size": size,
                                     "info2": v_info["Codec"] + " | " + a_info["Codec"] + " / " + a_info["ChannelLayout"],
                                     "direct": True, "debridonly": False,
                                     "icon": icon,})
                                print('w')
                    except Exception as e:
                        fflog("Jellyfin Series parse error:")
                        log_exc()
                else:
                    titles = [url["title"], url["localtitle"]]
                    for title in titles:
                        search_url = self.search_url.format(server=server['server_address'],
                                                            query=title)
                        try:
                            res = self.session.get(search_url, headers=headers).json()
                            results = res.get('SearchHints')
                            match_id = [i.get('ItemId') for i in results if
                                        (i.get('ProductionYear') == int(url['year'])
                                        and i.get('Type') == 'Movie'
                                        and i.get('Name') == title)]
                            if not match_id:
                                continue
                            for id in match_id:
                                info_url = self.item_info_url.format(server=server['server_address'],
                                                                     ItemID=id,
                                                                     User_ID=server['user_id'])
                                src = self.session.get(info_url, headers=headers).json()
                                src = src.get('MediaSources')[0]
                                size = convert_size(src.get('Size'))
                                v_info = [s for s in src.get('MediaStreams')
                                         if s.get('Type') == 'Video'][0]
                                a_info = [s for s in src.get('MediaStreams')
                                          if s.get('Type') == 'Audio'][0]
                                sources.append(
                                    {"source": server['server_name'],
                                     "quality": source_utils.get_release_quality(v_info.get('DisplayTitle'))[0],
                                     "language": source_utils.get_lang_by_type(src['Name'])[0],
                                     "url": self.jellyfin_pattern.format(id),
                                     "info2": v_info["Codec"] + " | " + a_info["Codec"] + " / " + a_info["ChannelLayout"],
                                     "size": size,
                                     "direct": True, "debridonly": False,
                                     "icon": icon, })

                        except requests.Timeout:
                            fflog(f'Jellyfin connection timeout')

        except Exception:
            fflog("Jellyfin source: failed")
            log_exc()
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
