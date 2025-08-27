# -*- coding: utf-8 -*-
"""
FanFilm ‑ źródło: ninateka.pl
Copyright (C) 2025 :)

Dystrybuowane na licencji GPL‑3.0.
"""
from lib.ff import requests
import re
import json
from lib.ff import cleantitle
from lib.ff.log_utils import fflog
from urllib.parse import urlencode

class source:
    def __init__(self):
        self.priority = 1
        self.language = ['pl']
        self.base_url = 'https://ninateka.pl'
        self.api_url = 'https://ninateka.pl/api/'
        self.platform = 'BROWSER'
        self.UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0'

    def heaGen(self):
        h = {
            'User-Agent': self.UA,
            'Referer': self.base_url,
            'Accept': 'application/json, text/plain, */*'
        }
        return h

    def paramsGen(self):
        p = {
            'lang': 'POL',
            'platform': self.platform
        }
        return p

    def movie(self, imdb, title, localtitle, aliases, year):
        #fflog(f"ninateka: searching for {localtitle} ({year})")

        search_url = self.api_url + 'products/vods/search/VOD'
        params = self.paramsGen()
        params['keyword'] = cleantitle.geturl(localtitle)

        try:
            response = requests.get(search_url, headers=self.heaGen(), params=params)
            if response.status_code != 200:
                #fflog(f"ninateka: search request failed with status code {response.status_code}")
                return []

            results = response.json().get('items', [])
            #fflog(f"ninateka: found {len(results)} results")

            sources = []
            for item in results:
                if item.get('type') != 'VOD':
                    continue

                normalized_item_title = cleantitle.normalize(item['title'])
                item_year = int(item.get('year', 0))
                search_year = int(year)

                if cleantitle.normalize(localtitle) in normalized_item_title and abs(item_year - search_year) <= 1:
                    #fflog(f"ninateka: found match: {item['title']} ({item.get('year', '')})")

                    is_audiodescription = 'audiodeskrypcja' in item['title'].lower()

                    eid = item['id']
                    tenant = item['tenant']['uid']
                    play_url = self.api_url + f'products/{eid}/videos/playlist'
                    playlist_params = {
                        'videoType': 'MOVIE',
                        'platform': self.platform,
                        'tenant': tenant
                    }
                    playlist_response = requests.get(play_url, headers=self.heaGen(), params=playlist_params)
                    if playlist_response.status_code == 200:
                        playlist_data = playlist_response.json()
                        if 'sources' in playlist_data and 'DASH' in playlist_data['sources'] and playlist_data['sources']['DASH']:
                            for stream in playlist_data['sources']['DASH']:
                                stream_url = stream['src']
                                if stream_url.startswith('//'):
                                    stream_url = 'https:' + stream_url

                                quality = 'SD'
                                if '1080' in stream_url:
                                    quality = '1080p'
                                elif '720' in stream_url:
                                    quality = '720p'
                                elif '480' in stream_url:
                                    quality = '480p'

                                info = 'Lektor'
                                if is_audiodescription:
                                    info += ' - Audiodeskrypcja'

                                source_info = {
                                    'source': 'Ninateka',
                                    'quality': quality,
                                    'language': 'pl',
                                    'url': f"DRMCDA|{item['id']}|{item['tenant']['uid']}",
                                    'info': info,
                                    'info2': '',
                                    'direct': False, # Needs resolving
                                    'debridonly': False
                                }
                                sources.append(source_info)
            return sources
        except Exception as e:
            #fflog(f"ninateka: exception during search: {e}")
            return []

    def sources(self, url, hostDict, hostprDict):
        return url

    def resolve(self, url):
        #fflog(f"ninateka: resolving url: {url}")
        if url.startswith('DRMCDA|'):
            try:
                _, eid, tenant = url.split('|')

                play_url = self.api_url + f'products/{eid}/videos/playlist'
                params = {
                    'videoType': 'MOVIE',
                    'platform': self.platform,
                    'tenant': tenant
                }

                response = requests.get(play_url, headers=self.heaGen(), params=params)
                if response.status_code != 200:
                    fflog(f"ninateka: resolve request failed with status code {response.status_code}")
                    return None

                data = response.json()

                if 'sources' in data and 'DASH' in data['sources'] and data['sources']['DASH']:
                    stream_url = data['sources']['DASH'][0]['src']
                    if stream_url.startswith('//'):
                        stream_url = 'https:' + stream_url

                    adaptive_data = {
                        'protocol': 'mpd',
                        'mimetype': 'application/dash+xml',
                        'manifest': stream_url,
                        'licence_type': '' # Ensure licence_type always exists
                    }

                    if 'drm' in data and 'WIDEVINE' in data['drm']:
                        adaptive_data['licence_type'] = 'com.widevine.alpha'
                        adaptive_data['licence_url'] = data['drm']['WIDEVINE']['src']
                        heaLic = {
                            'User-Agent': self.UA,
                            'Referer': self.base_url,
                            'Content-Type': ''
                        }
                        adaptive_data['licence_header'] = urlencode(heaLic)
                        adaptive_data['post_data'] = 'R{SSM}'
                        adaptive_data['response_data'] = ''

                    return f"DRMCDA|{repr(adaptive_data)}"
                else:
                    #fflog("ninateka: no DASH source found in response")
                    return None
            except Exception as e:
                #fflog(f"ninateka: exception during resolve: {e}")
                return None
        return url
