# -*- coding: utf-8 -*-
"""
FanFilm - źródło: vod.tvp.pl
Copyright (C) 2025 :)

Dystrybuowane na licencji GPL-3.0.
"""
from lib.ff import requests
import json
import random
from lib.ff import cleantitle, source_utils
from lib.ff.log_utils import fflog
from urllib.parse import urlencode


class source:
    def __init__(self):
        self.priority = 1
        self.language = ['pl']
        self.show_payable = False
        self.base_url = 'https://vod.tvp.pl'
        self.api_url = 'https://vod.tvp.pl/api/'
        self.search_url = 'products/vods/search/VOD'
        self.tvshow_search_url = 'products/vods/search/SERIAL'
        self.episode_api_url = 'products/vods/serials/{show_id}/seasons/{season_id}/episodes'
        self.platform = 'BROWSER'  # BROWSER seems to provide more quality options
        self.UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0'

        self.baseurl_temp = 'https://apps.vod.tvp.pl/'
        self.hea_temp = {
            'User-Agent': self.UA,
            'Referer': self.baseurl_temp,
            'X-Redge-VOD': 'true',
            'API-DeviceInfo': 'HbbTV;2.0.1 (ETSI 1.4.1);Chrome +DRM Samsung;Chrome +DRM Samsung;HbbTV;2.0.3'
        }
        self.session = requests.Session()

    def heaGen(self):
        CorrelationID = 'smarttv_'+self.code_gen(32)
        h = self.hea_temp.copy()  # Start with the base headers from __init__
        h.update({'API-CorrelationID': CorrelationID})  # Add CorrelationID
        # Assuming DeviceUid, API-Authentication, API-ProfileUid are handled elsewhere or not strictly necessary for basic playback
        # For now, let's just add CorrelationID and use the base headers.

        # Original headers that might still be needed
        h['User-Agent'] = self.UA  # Ensure UA is from self.UA
        h['Referer'] = self.base_url  # Ensure Referer is from self.base_url
        h['Accept'] = 'application/json, text/plain, */*'  # Keep this if needed

        return h

    def paramsGen(self):
        p = {
            'lang': 'PL',
            'platform': self.platform
        }
        return p

    def code_gen(self, x):
        base = '0123456789abcdef'
        code = ''
        for i in range(0, x):
            code += base[random.randint(0, 15)]
        return code

    def search(self, query, item_type):
        """Search for movies or TV shows using TVP VOD API"""
        try:
            params = self.paramsGen()
            params['keyword'] = cleantitle.geturl(query)

            if item_type == 'movie':
                search_endpoint = self.search_url
            elif item_type == 'tvshow':
                search_endpoint = self.tvshow_search_url
            else:
                fflog(f"tvp_vod: Invalid item_type: {item_type}")
                return []

            full_search_url = f'{self.api_url}{search_endpoint}'

            fflog(f"tvp_vod: Searching {item_type} with URL: {full_search_url}")
            fflog(f"tvp_vod: Search params: {params}")

            response = self.session.get(full_search_url,
                                        headers=self.heaGen(),
                                        params=params)

            fflog(f"tvp_vod: Search response status: {response.status_code}")

            if response.status_code == 200:
                try:
                    search_data = response.json()
                    fflog(f"tvp_vod: Search response: {search_data}")
                    items = search_data.get('items', [])
                    if not self.show_payable:
                        items = [item for item in items if not item.get('payable')]
                    return items
                except json.JSONDecodeError:
                    fflog("tvp_vod: Search response is not JSON")
                    return []
            else:
                fflog(f"tvp_vod: Search failed with status {response.status_code}")
                return []

        except Exception:
            fflog_exc()
            return []

    def get_video_playlist(self, product_id, video_type, tenant_uid=None, show_id=None, season_id=None):
        """Get video playlist data"""
        try:
            playlist_url = f'{self.api_url}products/{product_id}/videos/playlist'

            params = {
                'videoType': video_type,
                'platform': self.platform
            }

            if tenant_uid:
                params['tenant'] = tenant_uid

            fflog(f"tvp_vod: Getting playlist from: {playlist_url}")
            fflog(f"tvp_vod: Playlist params: {params}")

            response = self.session.get(playlist_url,
                                        headers=self.heaGen(),
                                        params=params)

            fflog(f"tvp_vod: Playlist response status: {response.status_code}")

            try:
                response.raise_for_status()
                return response.json()
            except (requests.exceptions.RequestException, json.JSONDecodeError):
                return None

        except Exception:
            fflog_exc()
            return None

    def get_best_quality_stream(self, sources_list, protocol_name):
        """Helper function to get the best quality stream from a list"""
        if not sources_list:
            return None

        fflog(f"tvp_vod: Analyzing {len(sources_list)} {protocol_name} sources")

        # Log all available streams for debugging
        for i, source in enumerate(sources_list):
            bitrate = source.get('totalBitrate', source.get('bitrate', 0))
            resolution = source.get('label', source.get('quality', 'unknown'))
            fflog(f"tvp_vod: {protocol_name} stream {i}: bitrate={bitrate}, resolution={resolution}, url={source.get('src', '')[:50]}...")

        # Try multiple sorting strategies to ensure we get the best quality
        best_stream = None

        # Strategy 1: Sort by totalBitrate
        if any('totalBitrate' in s for s in sources_list):
            sources_by_bitrate = sorted([s for s in sources_list if 'totalBitrate' in s and s['totalBitrate'] > 0],
                                        key=lambda x: x['totalBitrate'], reverse=True)
            if sources_by_bitrate:
                best_stream = sources_by_bitrate[0]
                fflog(f"tvp_vod: Selected by totalBitrate: {best_stream['totalBitrate']}")

        # Strategy 2: Sort by bitrate if totalBitrate didn't work
        if not best_stream and any('bitrate' in s for s in sources_list):
            sources_by_bitrate = sorted([s for s in sources_list if 'bitrate' in s and s['bitrate'] > 0],
                                        key=lambda x: x['bitrate'], reverse=True)
            if sources_by_bitrate:
                best_stream = sources_by_bitrate[0]
                fflog(f"tvp_vod: Selected by bitrate: {best_stream['bitrate']}")

        # Strategy 3: Look for quality/label indicators (1080p, 720p, etc.)
        if not best_stream:
            quality_priority = ['1080p', '720p', '480p', '360p', '240p']
            for quality in quality_priority:
                for source in sources_list:
                    label = source.get('label', '').lower()
                    quality_field = source.get('quality', '').lower()
                    if quality in label or quality in quality_field:
                        best_stream = source
                        fflog(f"tvp_vod: Selected by quality label: {quality}")
                        break
                if best_stream:
                    break

        # Strategy 4: Just take the first one as fallback
        if not best_stream and sources_list:
            best_stream = sources_list[0]
            fflog(f"tvp_vod: Using first stream as fallback")

        return best_stream

    def movie(self, imdb, title, localtitle, aliases, year):
        fflog(f"tvp_vod: searching for {localtitle} ({year}) as movie")

        try:
            search_results = self.search(cleantitle.geturl(localtitle), 'movie')
            if not search_results:
                fflog("tvp_vod: No search results found for movie")
                return []

            sources = []
            for item in search_results:
                if not isinstance(item, dict) or item.get('type') != 'VOD':
                    continue

                item_title = item.get('title', '')
                item_year = int(item.get('year', 0))
                item_id = item.get('id', '')
                tenant_info = item.get('tenant', {})
                tenant_uid = tenant_info.get('uid', '') if isinstance(tenant_info, dict) else ''

                if not item_title or not item_id:
                    continue

                normalized_item_title = cleantitle.normalize(item_title)
                normalized_search_title = cleantitle.normalize(localtitle)

                if normalized_search_title in normalized_item_title and abs(item_year - int(year)) <= 1:
                    fflog(f"tvp_vod: found movie match: {item_title} ({item_year})")

                    is_audiodescription = 'audiodeskrypcja' in item_title.lower()
                    quality = '1080p'  # Default, TVP might offer better qualities, needs further API investigation
                    info = 'Lektor'
                    if is_audiodescription:
                        info += ' - Audiodescription'

                    source_info = {
                        'source': '',
                        'quality': quality,
                        'language': 'pl',
                        'url': f"DRMCDA|{item_id}|{tenant_uid}|MOVIE",
                        'info': info,
                        'info2': '',
                        'direct': False,
                        'debridonly': False
                    }
                    sources.append(source_info)
                    fflog(f"tvp_vod: Appending movie source_info: {source_info}")

            return sources
        except Exception:
            fflog_exc()
            return []

    def tvshow(self, imdb, tmdb, tvshowtitle, localtvshowtitle, aliases, year):
        return (tvshowtitle, localtvshowtitle, aliases), year

    def episode(self, url, imdb, tmdb, title, premiered, season, episode):
        fflog(f"tvp_vod: episode called - S{season}E{episode} for '{title}' premiered on {premiered}")

        try:
            show_info, year = url
            tvshowtitle, localtvshowtitle, aliases = show_info
            sources = []
            fflog(f"tvp_vod: searching for show '{localtvshowtitle}' ({year})")

            search_results = self.search(cleantitle.geturl(localtvshowtitle), 'tvshow')
            if not search_results:
                fflog("tvp_vod: No search results found for tvshow")
                return []

            fflog(f"tvp_vod: Found {len(search_results)} search results")

            matched_show = None
            for item in search_results:
                if not isinstance(item, dict) or item.get('type') != 'SERIAL':
                    continue

                item_title = item.get('title', '')
                item_year = item.get('year', 0)
                if not item_year:
                    since_date = item.get('since', '')[:4]
                    item_year = int(since_date) if since_date.isdigit() else 0

                item_id = item.get('id', '')
                if not item_title or not item_id:
                    continue

                simple_item_title = ''.join(c.lower() for c in item_title if c.isalnum())
                simple_search_title = ''.join(c.lower() for c in localtvshowtitle if c.isalnum())
                title_match = simple_search_title == simple_item_title
                year_match = abs(item_year - int(year)) <= 2

                if title_match and year_match:
                    matched_show = item
                    fflog(f"tvp_vod: Found matching show: {item_title} (ID: {item_id})")
                    break

            if not matched_show:
                fflog("tvp_vod: No matching show found")
                return []

            show_id = matched_show['id']
            seasons_url = f'{self.api_url}products/vods/serials/{show_id}/seasons'
            fflog(f"tvp_vod: Fetching seasons from: {seasons_url}")
            seasons_response = self.session.get(seasons_url, headers=self.heaGen(), params=self.paramsGen())
            seasons_response.raise_for_status()
            seasons_data = seasons_response.json()
            fflog(f"tvp_vod: Found {len(seasons_data)} seasons for show ID {show_id}")

            found_episode = None

            # First attempt: direct season/episode matching
            target_season_num = int(season)
            target_season = next((s for s in seasons_data if s.get('number') == target_season_num), None)

            if target_season:
                season_id = target_season.get('id')
                episodes_url = f'{self.api_url}products/vods/serials/{show_id}/seasons/{season_id}/episodes'
                episodes_response = self.session.get(episodes_url, headers=self.heaGen(), params=self.paramsGen())
                episodes_response.raise_for_status()
                episodes_data = episodes_response.json()

                target_episode_index = int(episode) - 1
                if 0 <= target_episode_index < len(episodes_data):
                    found_episode = episodes_data[target_episode_index]
                    fflog(f"tvp_vod: Found episode with direct matching: {found_episode.get('title')}")
            # else:
                fflog(f"tvp_vod: Season {target_season_num} not found directly. Available seasons: {[s.get('number') for s in seasons_data]}")

            # Fallback: absolute episode numbering
            if not found_episode:
                fflog(f"tvp_vod: Direct match failed or skipped. Trying absolute numbering for S{season}E{episode}.")
                try:
                    _, absolute_episode_number = source_utils.get_absolute_number_tmdb(tmdb, season, episode)
                except Exception:
                    fflog_exc()
                    absolute_episode_number = None

                if absolute_episode_number:
                    fflog(f"tvp_vod: Calculated absolute episode number: {absolute_episode_number}")
                    current_episode_count = 0
                    sorted_seasons = sorted(seasons_data, key=lambda s: s.get('number', 0))

                    for s in sorted_seasons:
                        season_id = s.get('id')
                        episodes_url = f'{self.api_url}products/vods/serials/{show_id}/seasons/{season_id}/episodes'
                        episodes_response = self.session.get(episodes_url, headers=self.heaGen(), params=self.paramsGen())
                        episodes_response.raise_for_status()
                        episodes_in_season = episodes_response.json()

                        num_episodes_in_season = len(episodes_in_season)

                        if current_episode_count + num_episodes_in_season >= absolute_episode_number:
                            target_episode_index = absolute_episode_number - current_episode_count - 1
                            if 0 <= target_episode_index < num_episodes_in_season:
                                found_episode = episodes_in_season[target_episode_index]
                                fflog(f"tvp_vod: Found episode with absolute numbering: {found_episode.get('title')}")
                                break

                        current_episode_count += num_episodes_in_season
                # else:
                    fflog("tvp_vod: Could not determine absolute episode number.")

            if not found_episode:
                fflog(f"tvp_vod: Episode S{season}E{episode} not found on TVP VOD after all attempts.")
                return []

            fflog(f"tvp_vod: Found matching episode: {found_episode.get('title')}")

            if found_episode.get('payable') and not self.show_payable:
                fflog(f"tvp_vod: Skipping payable episode: {found_episode.get('title')}")
                return []

            tenant_uid = ''
            if 'tenant' in found_episode:
                tenant_info = found_episode['tenant']
                if isinstance(tenant_info, dict):
                    tenant_uid = tenant_info.get('uid', '')

            # Reverted quality part as per user request
            is_audiodescription = 'audiodeskrypcja' in found_episode.get('title', '').lower()
            quality = '1080p'  # Changed from 'SD' to indicate expected quality
            info = 'Lektor'
            if is_audiodescription:
                info += ' - Audiodescription'

            source_info = {
                'source': 'TVP VOD',
                'quality': quality,
                'language': 'pl',
                'url': f"DRMCDA|{found_episode['id']}|{tenant_uid}|EPISODE",
                'info': info,
                'info2': '',
                'direct': False,
                'debridonly': False
            }

            sources.append(source_info)
            fflog(f"tvp_vod: Appending episode source_info: {source_info}")

            return sources
        except Exception:
            fflog_exc()
            return []

    def sources(self, url, hostDict, hostprDict):
        return url

    def resolve(self, url):
        """Resolve video URL - following ninateka pattern"""
        fflog(f"tvp_vod: resolving url: {url}")

        if not url.startswith('DRMCDA|'):
            return url

        try:
            parts = url.split('|')
            product_id = None
            video_type = None
            tenant_uid = None

            if len(parts) == 4:  # For MOVIE and EPISODE types
                _, product_id, tenant_uid, video_type = parts
            else:
                fflog(f"tvp_vod: Unknown DRMCDA URL format: {url}")
                return None

            # For episodes, videoType in the API call is MOVIE, not EPISODE
            api_video_type = 'MOVIE' if video_type == 'EPISODE' else video_type
            playlist_data = self.get_video_playlist(product_id, api_video_type, tenant_uid)

            if not playlist_data or not isinstance(playlist_data, dict):
                fflog("tvp_vod: No valid playlist data received or it's not a dictionary.")
                return None

            # Log the full playlist response for debugging
            fflog(f"tvp_vod: Full playlist response: {json.dumps(playlist_data, indent=2)}")

            # Handle paid content error
            if 'code' in playlist_data and playlist_data['code'] == 'ITEM_NOT_PAID':
                fflog("tvp_vod: Material is not paid.")
                return None

            stream_url = None
            protocol = None

            # --- SMART QUALITY SELECTION LOGIC (DRM-aware) ---
            if 'sources' in playlist_data:
                fflog(f"tvp_vod: Available source types: {list(playlist_data['sources'].keys())}")

                # Check if content has DRM - if yes, we MUST use DASH
                has_drm = ('drm' in playlist_data and 'WIDEVINE' in playlist_data['drm'] and playlist_data['drm']['WIDEVINE'].get('src'))

                if has_drm:
                    fflog("tvp_vod: DRM detected - using DASH")
                    if 'DASH' in playlist_data['sources'] and playlist_data['sources']['DASH']:
                        dash_sources = playlist_data['sources']['DASH']
                        fflog(f"tvp_vod: Found {len(dash_sources)} DASH sources")
                        for i, source in enumerate(dash_sources):
                            bitrate = source.get('totalBitrate', source.get('bitrate', 0))
                            fflog(f"tvp_vod: DASH stream {i}: bitrate={bitrate}, url={source.get('src', '')[:50]}...")

                        protocol = 'mpd'
                        stream_url = dash_sources[0]['src']
                        fflog(f"tvp_vod: Selected DASH stream for DRM: {stream_url}")
                    else:
                        fflog("tvp_vod: DRM content but no DASH source available!")
                        return None
                else:
                    # No DRM - prefer HLS for better adaptive quality
                    fflog("tvp_vod: No DRM detected - preferring HLS")
                    if 'HLS' in playlist_data['sources'] and playlist_data['sources']['HLS']:
                        hls_sources = playlist_data['sources']['HLS']
                        fflog(f"tvp_vod: Found {len(hls_sources)} HLS sources")
                        for i, source in enumerate(hls_sources):
                            bitrate = source.get('totalBitrate', source.get('bitrate', 0))
                            fflog(f"tvp_vod: HLS stream {i}: bitrate={bitrate}, url={source.get('src', '')[:50]}...")

                        protocol = 'hls'
                        stream_url = hls_sources[0]['src']
                        fflog(f"tvp_vod: Selected HLS stream: {stream_url}")

                    # Fallback to DASH if no HLS
                    elif 'DASH' in playlist_data['sources'] and playlist_data['sources']['DASH']:
                        dash_sources = playlist_data['sources']['DASH']
                        fflog(f"tvp_vod: Found {len(dash_sources)} DASH sources (fallback)")
                        for i, source in enumerate(dash_sources):
                            bitrate = source.get('totalBitrate', source.get('bitrate', 0))
                            fflog(f"tvp_vod: DASH stream {i}: bitrate={bitrate}, url={source.get('src', '')[:50]}...")

                        protocol = 'mpd'
                        stream_url = dash_sources[0]['src']
                        fflog(f"tvp_vod: Selected DASH stream (fallback): {stream_url}")
            # --- END SMART QUALITY SELECTION LOGIC ---

            if not stream_url:
                fflog("tvp_vod: no suitable source found in response")
                return None

            if stream_url.startswith('//'):
                stream_url = 'https:' + stream_url

            # Check for DRM - return adaptive data structure for DRM content
            if 'drm' in playlist_data and 'WIDEVINE' in playlist_data['drm'] and playlist_data['drm']['WIDEVINE'].get('src'):
                lic_headers = self.heaGen()
                lic_headers.pop('Accept', None)
                lic_headers['Content-Type'] = ''

                adaptive_data = {
                    'protocol': 'mpd',
                    'mimetype': 'application/dash+xml',
                    'manifest': stream_url,
                    'licence_type': 'com.widevine.alpha',
                    'licence_url': playlist_data['drm']['WIDEVINE']['src'],
                    'licence_header': urlencode(lic_headers),
                    'post_data': 'R{SSM}',
                    'response_data': '',
                    # Dodaj te kluczowe właściwości dla VOD
                    'content_lookup': False,
                    'is_playable': True,
                    'stream_headers': f"User-Agent={self.UA}&Referer={self.base_url}",
                    'manifest_headers': f"User-Agent={self.UA}&Referer={self.base_url}"
                }
                fflog(f"tvp_vod: Returning DRM-protected VOD stream with manifest: {stream_url}")
                return f"DRMCDA|{repr(adaptive_data)}"
            elif protocol:
                # Dla streamów bez DRM - użyj struktury adaptive_data z pustymi polami DRM
                adaptive_data = {
                    'protocol': protocol,
                    'mimetype': 'application/dash+xml' if protocol == 'mpd' else 'application/x-mpegURL',
                    'manifest': stream_url,
                    # Puste pola DRM dla streamów bez DRM (wymagane przez FanFilm)
                    'licence_type': '',
                    'licence_url': '',
                    'licence_header': '',
                    'post_data': '',
                    'response_data': '',
                    # Kluczowe właściwości dla VOD
                    'content_lookup': False,
                    'is_playable': True,
                    'stream_headers': f"User-Agent={self.UA}&Referer={self.base_url}",
                    'manifest_headers': f"User-Agent={self.UA}&Referer={self.base_url}"
                }
                fflog(f"tvp_vod: Returning non-DRM VOD stream with adaptive_data: {stream_url}")
                return f"DRMCDA|{repr(adaptive_data)}"
            else:
                # Ostateczny fallback - zwróć zwykły URL (ale to może nie działać dobrze z przewijaniem)
                fflog(f"tvp_vod: Returning fallback stream: {stream_url}")
                return stream_url

        except Exception:
            fflog_exc()
            return None
