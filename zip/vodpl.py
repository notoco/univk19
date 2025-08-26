# -*- coding: utf-8 -*-
from lib.ff import requests
import re
import json
import random
from lib.ff import cleantitle
from lib.ff.log_utils import fflog
from urllib.parse import urlencode

class source:
    def __init__(self):
        fflog("vodpl: Initializing scraper")
        self.priority = 1
        self.language = ['pl']
        self.base_url = 'https://player.pl/'
        self.api_url = 'https://player.pl/playerapi/'
        self.platform = 'ANDROID_TV'
        self.UA = 'playerTV/2.2.2 (455) (Linux; Android 8.0.0; Build/sdk_google_atv_x86) net/sdk_google_atv_x86userdebug 8.0.0 OSR1.180418.025 6695156 testkeys'
        self.device_uid = self._code_gen(16)
        self.uid = self._code_gen(32)

    def _code_gen(self, x):
        base = '0123456789abcdef'
        code = ''
        for i in range(0, x):
            code += base[random.randint(0, 15)]
        return code

    def heaGen(self):
        CorrelationID = 'androidTV_' + self._code_gen(8) + '-' + self._code_gen(4) + '-' + self._code_gen(4) + '-' + self._code_gen(4) + '-' + self._code_gen(12)
        hea = {
            'User-Agent': self.UA,
            'accept-encoding': 'gzip'
        }
        hea.update({
            'api-correlationid': CorrelationID,
            'api-deviceuid': self.device_uid,
            'api-deviceinfo': 'sdk_google_atv_x86;unknown;Android;8.0.0;Unknown;2.2.2 (455);',
        })
        return hea

    def cookiesGen(self):
        c = {
            'uid': self.uid,
        }
        return c

    def _get_series_episodes(self, series_id):
        episodes_list = []
        try:
            seasons_url = self.api_url + f'product/vod/serial/{series_id}/season/list'
            seasons_params = {
                '4K': 'true',
                'platform': self.platform
            }
            seasons_response = requests.get(seasons_url, headers=self.heaGen(), cookies=self.cookiesGen(), params=seasons_params)
            if seasons_response.status_code != 200:
                fflog(f"vodpl: failed to get seasons for series {series_id} with status code {seasons_response.status_code}")
                return []

            seasons_data = seasons_response.json()

            for season in seasons_data:
                season_id = season.get('id')
                if season_id:
                    episodes_url = self.api_url + f'product/vod/serial/{series_id}/season/{season_id}/episode/list'
                    episodes_params = {
                        '4K': 'true',
                        'platform': self.platform
                    }
                    episodes_response = requests.get(episodes_url, headers=self.heaGen(), cookies=self.cookiesGen(), params=episodes_params)
                    if episodes_response.status_code != 200:
                        fflog(f"vodpl: failed to get episodes for season {season_id} of series {series_id} with status code {episodes_response.status_code}")
                        continue

                    episodes_data = episodes_response.json()
                    for episode in episodes_data:
                        if not episode.get('payable', False):
                            episodes_list.append(episode)
        except Exception as e:
            fflog(f"vodpl: exception during _get_series_episodes: {e}")
        return episodes_list

    def movie(self, imdb, title, localtitle, aliases, year):
        fflog(f"vodpl: movie method called for {localtitle} ({year})")
        sources = []

        search_url = self.api_url + 'item/search'
        params = {
            '4K': 'true',
            'platform': self.platform,
            'keyword': localtitle,
            'episodes': 'true'
        }

        try:
            response = requests.get(search_url, headers=self.heaGen(), cookies=self.cookiesGen(), params=params)
            if response.status_code != 200:
                fflog(f"vodpl: search request failed with status code {response.status_code}")
                return []

            results = response.json()
            # fflog(f"vodpl: API response for {localtitle}: {json.dumps(results, indent=2)}") # Log the full JSON response

            normalized_localtitle = cleantitle.normalize(localtitle)

            for item in results:
                if 'element' in item:
                    item_data = item['element']

                    if item_data.get('payable', False):
                        fflog(f"vodpl: skipping payable content: {item_data.get('title')} ({item_data.get('year')})")
                        continue

                    item_type = item_data.get('type')
                    item_id = item_data.get('id')
                    item_title = item_data.get('title')
                    item_year = item_data.get('year')
                    item_image = item_data.get('images', {}).get('pc', [{}])[0].get('mainUrl')

                    if item_image and item_image.startswith('//'):
                        item_image = 'https:' + item_image

                    normalized_item_title = cleantitle.normalize(item_title)

                    if normalized_localtitle != normalized_item_title:
                        fflog(f"vodpl: title mismatch: '{localtitle}' vs '{item_title}'")
                        continue

                    if year:
                        try:
                            item_year_int = int(item_year)
                            if abs(int(year) - item_year_int) > 1:
                                fflog(f"vodpl: year mismatch: '{year}' vs '{item_year}' for '{item_title}'")
                                continue
                        except (ValueError, TypeError):
                            fflog(f"vodpl: skipping item '{item_title}' due to invalid or missing year '{item_year}' when year filter is active.")
                            continue

                    if item_type == 'VOD':
                        fflog(f"vodpl: found playable movie: {item_title} ({item_year})")

                        quality = 'SD'
                        if item_data.get('uhd'):
                            quality = '4K'
                        else:
                            image_types = ['android_tv', 'pc', 'smart_tv', 'playstation', 'mobile', 'apple_tv']
                            for img_type in image_types:
                                image_data_list = item_data.get('images', {}).get(img_type)
                                if image_data_list and len(image_data_list) > 0 and 'mainUrl' in image_data_list[0]:
                                    main_url = image_data_list[0]['mainUrl']
                                    match = re.search(r'dstw=(\d+)&dsth=(\d+)', main_url)
                                    if match:
                                        width = int(match.group(1))
                                        height = int(match.group(2))
                                        if height >= 1080:
                                            quality = '1080p'
                                            break
                                        elif height >= 720:
                                            quality = '720p'
                                            break
                                        elif height >= 480:
                                            quality = 'SD'
                                            break
                                        elif height >= 360:
                                            quality = 'SD'
                                            break
                                        elif height >= 240:
                                            quality = 'SD'
                                            break
                                if quality != 'SD':
                                    break

                        source_info = {
                            'source': 'VOD.pl',
                            'quality': quality,
                            'language': 'pl',
                            'url': f"DRMCDA|{item_id}|{item_type}",
                            'info': '',
                            'info2': '',
                            'direct': False,
                            'debridonly': False,
                            'image': item_image
                        }
                        sources.append(source_info)
                    elif item_type == 'SERIAL':
                        fflog(f"vodpl: found serial: {item_title} ({item_year}). Adding as TV show folder.")
                        source_info = {
                            'source': 'VOD.pl',
                            'quality': 'SD',
                            'language': 'pl',
                            'url': f"CDADRM|{item_id}|SERIAL",
                            'info': '',
                            'info2': '',
                            'direct': False,
                            'debridonly': False,
                            'image': item_image,
                            'mediatype': 'tvshow'
                        }
                        sources.append(source_info)
            return sources
        except Exception as e:
            fflog(f"vodpl: exception during search: {e}")
            return []

    def sources(self, url, hostDict, hostprDict):
        return url

    def resolve(self, url):
        fflog(f"vodpl: resolving url: {url}")
        if url.startswith('DRMCDA|'):
            try:
                _, item_id, item_type = url.split('|')

                playlist_type = 'MOVIE'
                if item_type == 'SERIAL' or item_type == 'EPISODE':
                    playlist_type = 'MOVIE'

                playlist_url = self.api_url + f'item/{item_id}/playlist'
                params = {
                    'type': playlist_type,
                    '4K': 'true',
                    'platform': self.platform,
                    'version': '3.1'
                }

                response = requests.get(playlist_url, headers=self.heaGen(), cookies=self.cookiesGen(), params=params)
                if response.status_code != 200:
                    fflog(f"vodpl: resolve request failed with status code {response.status_code}")
                    return None

                data = response.json()

                if 'code' in data and data['code'] == 'ITEM_NOT_PAID':
                    fflog("vodpl: Item not paid, cannot resolve.")
                    return None

                stream_url = None
                drm_config = None

                if 'movie' in data and 'video' in data['movie']:
                    video_data = data['movie']['video']
                    if 'sources' in video_data and 'dash' in video_data['sources']:
                        stream_url = video_data['sources']['dash']['url']

                    if 'protections' in video_data and 'widevine' in video_data['protections']:
                        lic_url = video_data['protections']['widevine']['src']
                        heaLic = {
                            'User-Agent': self.UA,
                            'Referer': self.base_url,
                            'Content-Type': ''
                        }
                        drm_config = {
                            "com.widevine.alpha": {
                                "license": {
                                    "server_url": lic_url,
                                    "req_headers": urlencode(heaLic)
                                }
                            }
                        }

                if stream_url:
                    if drm_config:
                        adaptive_data = {
                            'protocol': 'mpd',
                            'mimetype': 'application/dash+xml',
                            'manifest': stream_url,
                            'licence_type': 'com.widevine.alpha',
                            'licence_url': lic_url,
                            'licence_header': urlencode(heaLic),
                            'post_data': 'R{SSM}',
                            'response_data': ''
                        }
                        return f"DRMCDA|{repr(adaptive_data)}"
                    else:
                        return stream_url
                else:
                    fflog("vodpl: no DASH source found in response")
                    return None
            except Exception as e:
                fflog(f"vodpl: exception during resolve: {e}")
                return None
        return url

    def episode(self, url, imdb, tmdb, title, premiered, season, episode):
        fflog(f"vodpl: episode method called for {title} S{season:02d}E{episode:02d}")
        sources = []

        # Extract series_id from the URL passed by Fanfilm
        series_id = None
        if url.startswith('CDADRM|'):
            try:
                # Assuming the URL for a series might be CDADRM|{series_id}|SERIAL
                # This is a guess based on how movie() constructs its URLs
                _, series_id, _ = url.split('|')
            except ValueError:
                fflog(f"vodpl: Invalid URL format for episode method: {url}")
                return []

        if not series_id:
            fflog("vodpl: Series ID not found in URL for episode method.")
            return []

        # Fetch all episodes for the series (reusing _get_series_episodes logic)
        all_episodes = self._get_series_episodes(series_id)

        for ep_data in all_episodes:
            ep_season = ep_data.get('season', {}).get('number')
            ep_episode = ep_data.get('episode')

            if ep_season == season and ep_episode == episode:
                # Found the matching episode
                item_id = ep_data.get('id')
                item_title = ep_data.get('title')
                item_image = ep_data.get('images', {}).get('pc', [{}])[0].get('mainUrl')
                if item_image and item_image.startswith('//'):
                    item_image = 'https:' + item_image

                quality = 'SD'
                if ep_data.get('uhd'):
                    quality = '4K'
                else:
                    image_types = ['android_tv', 'pc', 'smart_tv', 'playstation', 'mobile', 'apple_tv']
                    for img_type in image_types:
                        image_data_list = ep_data.get('images', {}).get(img_type)
                        if image_data_list and len(image_data_list) > 0 and 'mainUrl' in image_data_list[0]:
                            main_url = image_data_list[0]['mainUrl']
                            match = re.search(r'dstw=(\d+)&dsth=(\d+)', main_url)
                            if match:
                                height = int(match.group(2))
                                if height >= 1080:
                                    quality = '1080p'
                                    break
                                elif height >= 720:
                                    quality = '720p'
                                    break
                                elif height >= 480:
                                    quality = '480p'
                                    break
                                elif height >= 360:
                                    quality = '360p'
                                    break
                                elif height >= 240:
                                    quality = '240p'
                                    break
                        if quality != 'SD':
                            break

                source_info = {
                    'source': 'VOD.pl',
                    'quality': quality,
                    'language': 'pl',
                    'url': f"DRMCDA|{item_id}|EPISODE",
                    'info': f"S{season:02d}E{episode:02d} - {item_title}",
                    'info2': '',
                    'direct': False,
                    'debridonly': False,
                    'image': item_image
                }
                sources.append(source_info)
                break # Found the episode, no need to continue

        return sources

    def sources(self, url, hostDict, hostprDict):
        return url

    # Removed series and tvshow methods

    def resolve(self, url):
        fflog(f"vodpl: resolving url: {url}")
        if url.startswith('DRMCDA|'):
            try:
                _, item_id, item_type = url.split('|')

                playlist_type = 'MOVIE'
                if item_type == 'SERIAL' or item_type == 'EPISODE':
                    playlist_type = 'MOVIE'

                playlist_url = self.api_url + f'item/{item_id}/playlist'
                params = {
                    'type': playlist_type,
                    '4K': 'true',
                    'platform': self.platform,
                    'version': '3.1'
                }

                response = requests.get(playlist_url, headers=self.heaGen(), cookies=self.cookiesGen(), params=params)
                if response.status_code != 200:
                    fflog(f"vodpl: resolve request failed with status code {response.status_code}")
                    return None

                data = response.json()

                if 'code' in data and data['code'] == 'ITEM_NOT_PAID':
                    fflog("vodpl: Item not paid, cannot resolve.")
                    return None

                stream_url = None
                drm_config = None

                if 'movie' in data and 'video' in data['movie']:
                    video_data = data['movie']['video']
                    if 'sources' in video_data and 'dash' in video_data['sources']:
                        stream_url = video_data['sources']['dash']['url']

                    if 'protections' in video_data and 'widevine' in video_data['protections']:
                        lic_url = video_data['protections']['widevine']['src']
                        heaLic = {
                            'User-Agent': self.UA,
                            'Referer': self.base_url,
                            'Content-Type': ''
                        }
                        drm_config = {
                            "com.widevine.alpha": {
                                "license": {
                                    "server_url": lic_url,
                                    "req_headers": urlencode(heaLic)
                                }
                            }
                        }

                if stream_url:
                    if drm_config:
                        adaptive_data = {
                            'protocol': 'mpd',
                            'mimetype': 'application/dash+xml',
                            'manifest': stream_url,
                            'licence_type': 'com.widevine.alpha',
                            'licence_url': lic_url,
                            'licence_header': urlencode(heaLic),
                            'post_data': 'R{SSM}',
                            'response_data': ''
                        }
                        return f"DRMCDA|{repr(adaptive_data)}"
                    else:
                        return stream_url
                else:
                    fflog("vodpl: no DASH source found in response")
                    return None
            except Exception as e:
                fflog(f"vodpl: exception during resolve: {e}")
                return None
        return url