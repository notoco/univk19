"""
    FanFilm Add-on  2021
    Źródło w fazie testów
"""

from __future__ import annotations
from typing import Optional, Union, Any, List, Tuple, Sequence, Mapping, MutableMapping, Set, Container, Iterator, TYPE_CHECKING
import json
# For playermb mylist support
import re
from urllib.parse import parse_qs, urlencode, quote_plus
import xml.etree.ElementTree as ET

from lib.ff import requests
import xbmcaddon
from lib.ff import cleantitle, control, apis
from lib.ff.settings import settings
#from lib.ff.log_utils import LOGDEBUG, LOGERROR, LOGINFO, LOGWARNING, fflog
from const import const
from attr import frozen
from lib.ff.log_utils import fflog, fflog_exc
if TYPE_CHECKING:
    from jwgraph import jwgraph
    from lib.ff.item import FFItem


@frozen
class ExternalSource:
    id: str
    source: str
    addon: str
    packages: Set[str]

    @property
    def enabled(self) -> bool:
        # return True  # ALWAYS enabled – DEBUG only !!!
        if not settings.getBool(f'external.enable.{self.id}'):
            return False
        if self.addon.lower() != self.addon:  # incorrect addon id (has upper characters)
            from pathlib import Path
            path = Path(control.addonPath).parent / self.addon
            return path.exists()
        return control.condVisibility(f'System.AddonIsEnabled({self.addon})')

    def icon(self) -> Optional[str]:
        try:
            if icon := xbmcaddon.Addon(self.addon).getAddonInfo('icon'):
                return icon
        except RuntimeError:  # if no addon
            pass
        return None

    def offers(self, offers: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
        """Iterate over matchig platforms (clearName)."""
        # TODO: check: flatrate, buy, rent
        for item in offers['flatrate']:
            if item['package']['clearName'] in self.packages:
                yield item

    def links(self, offers: Mapping[str, Any]) -> Iterator[str]:
        """Iterate over matchig platforms' (clearName) link."""
        for item in self.offers(offers):
            yield item['standardWebURL']


external_sources: Mapping[str, ExternalSource] = {ext.id: ext for ext in (
    ExternalSource('netflix',      'Netflix',             'plugin.video.netflix',     {'Netflix'}),
    ExternalSource('prime',        'amazon prime',        'plugin.video.amazon-test', {'Amazon Prime Video'}),
    ExternalSource('max',          'max',                 'slyguy.max',               {'HBO Max'}),
    ExternalSource('disney',       'disney+',             'slyguy.disney.plus',       {'Disney Plus'}),
    ExternalSource('iplayer',      'bbc iplayer',         'plugin.video.iplayerwww',  {'bbc'}),  # no clearname
    ExternalSource('curstream',    'curiosity stream',    'slyguy.curiositystream',   {'Curiosity Stream'}),
    ExternalSource('hulu',         'hulu',                'slyguy.hulu',              {'Hulu'}),
    ExternalSource('paramount',    'paramount+',          'slyguy.paramount.plus',    {'Paramount'}),
    ExternalSource('playerpl',     'player pl',           'plugin.video.playermb',    {'Player'}),
    ExternalSource('playerpl_mtr', 'player pl (mtr)',     'plugin.video.player_pl',   {'Player'}),
    ExternalSource('viaplay',      'viaplay',             'plugin.video.viaplay',     {'Viaplay'}),
    ExternalSource('skyott',       'sky showtime',        'plugin.video.skyott',      {'SkyShowtime'}),
    ExternalSource('cda',          'cda premium',         'plugin.video.phantom',     {'CDA Premium'}),
    ExternalSource('cda_mb',       'cda premium (mbebe)', 'plugin.video.cdaplMB',     {'CDA Premium'}),
    ExternalSource('cda_mtr',      'cda premium (mtr)',   'plugin.video.cda_premium', {'CDA Premium'}),
)}


netflix_pattern = "plugin://plugin.video.netflix/play/movie/%s"
netflix_show_pattern = 'plugin://plugin.video.netflix/play/show/%s/season/%s/episode/%s/'
prime_pattern = "plugin://plugin.video.amazon-test/?asin=%s&mode=PlayVideo&name=None&adult=0&trailer=0&selbitrate=0"
max_pattern = "plugin://slyguy.max/?_=play&_play=1&id="
disney_pattern = "plugin://slyguy.disney.plus/?_=play&_play=1&content_id=%s&profile_id=%s"
disney_pattern_nocontentid = "plugin://slyguy.disney.plus/?_=play&_play=1&deeplink_id=%s&profile_id=%s"
iplayer_pattern = "plugin://plugin.video.iplayerwww/?url=%s&mode=202&name=null&iconimage=null&description=null&subtitles_url=&logged_in=False"
curstream_pattern = "plugin://slyguy.curiositystream/?_=play&_play=1&id="
hulu_pattern = "plugin://slyguy.hulu/?_=play&id="
paramount_pattern = "plugin://slyguy.paramount.plus/?_=play&id="
playerpl_pattern = "plugin://plugin.video.playermb/?mode=playvid&url={id}"
playerplmtr_pattern = "plugin://plugin.video.player_pl/?mode=playVid&profile={profile}&eid={id}"
viaplay_pattern = "plugin://plugin.video.viaplay/play?guid=%s&url=None&tve=false"
skyott_pattern = "plugin://plugin.video.skyott/?action=play&slug="
cda_pattern = (
    "plugin://plugin.video.phantom/?url=https://www.cda.pl/video/{id}/vfilm"
    "&mode=DecodeLink&param0={{\"id_stream\":+\"{id}/vfilm\",+\"url\":+\"https://www.cda.pl/video/{id}/vfilm\",+\"dursec\":+0,+\"savelvl\":0,"
    "+\"urlref\":+\"?mode=StreamBaseList\"}}"
)
cdamb_pattern = 'plugin://plugin.video.cdaplMB/?mode=playvid&url={id}&page=1&moviescount=0&title={title}&image={image}?t=1'
cdamtr_pattern = 'plugin://plugin.video.cda_premium/?mode=playVid&vid={id}'

scraper_init = any(ext.enabled for ext in external_sources.values())


class source:

    # This class has support for *.color.identify2 setting
    has_color_identify2: bool = True

    ffitem: 'FFItem'

    def __init__(self):
        self.priority = 1
        self.language = ["pl"]
        self.domains = []
        self.base_link = ""
        self.session = requests.Session()
        self.tm_user = settings.getString("tmdb.api_key") or apis.tmdb_API
        self.country = settings.getString("external.country") or "US"
        self.aliases = []
        self._justwatch: Optional[jwgraph.JustWatchAPI] = None
        self._justwatch_pl: Optional[jwgraph.JustWatchAPI] = None

    @property
    def justwatch(self) -> jwgraph.JustWatchAPI:
        from jwgraph import jwgraph
        if self._justwatch is None:
            self._justwatch = jwgraph.JustWatchAPI(country=self.country)
        return self._justwatch

    @property
    def justwatch_pl(self) -> jwgraph.JustWatchAPI:
        from jwgraph import jwgraph
        if self._justwatch_pl is None:
            self._justwatch_pl = jwgraph.JustWatchAPI(country=self.country, language=self.language[0])
        return self._justwatch_pl

    def movie(self, imdb, title, localtitle, aliases, year):
        if not scraper_init:
            return

        try:
            self.aliases.extend(aliases)
            url = {"imdb": imdb, "title": title, "localtitle": localtitle, "year": year}
            url = urlencode(url)
            return url
        except Exception:
            return

    def tvshow(self, imdb, tmdb, tvshowtitle, localtvshowtitle, aliases, year):
        if not scraper_init:
            return

        try:
            self.aliases.extend(aliases)
            url = {"imdb": imdb, "tmdb": tmdb, "tvshowtitle": tvshowtitle, "localtvshowtitle": localtvshowtitle, "year": year}
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

    def sources(self, url, hostDict, hostprDict):
        return self._sources(url, hostDict, hostprDict)

    def _sources(self, url, hostDict, hostprDict):

        def jget(url, params=None):
            return requests.get(url, params=params).json()

        sources = []
        if url is None:
            return sources

        data = parse_qs(url)
        data = dict([(i, data[i][0]) if data[i] else (i, "") for i in data])
        title = data["tvshowtitle"] if "tvshowtitle" in data else data["title"]
        localtitle = data["localtvshowtitle"] if "localtvshowtitle" in data else data["localtitle"]
        year = data["year"]
        content = "movie" if "tvshowtitle" not in data else "show"
        result = None
        r = self.justwatch.search_item(title.lower())
        r_pl = self.justwatch_pl.search_item(localtitle.lower())
        items = r['popularTitles']['edges']
        items = items + r_pl['popularTitles']['edges']
        jw_id = [x[1] for i in items for x in i.items()]

        for i in jw_id:
            if isinstance(i, dict):
                title = cleantitle.normalize(cleantitle.query(title)).lower()
                local_title = cleantitle.normalize(cleantitle.query(localtitle)).lower()
                content_title = cleantitle.normalize(cleantitle.query(i['content']['title'])).lower()
                if ((local_title == content_title and int(year) == int(i['content']['originalReleaseYear'])) or
                    (title == content_title and int(year) == int(i['content']['originalReleaseYear']))):
                    jw_id = i['content']['fullPath']

        r = self.justwatch.get_title(jw_id)

        if content == 'show':
            item = r["url"]["node"]["seasons"]
            item = [i for i in item if i['content']['seasonNumber'] == int(data["season"])][0]
            full_path = item['content']['fullPath']
            r = self.justwatch.get_title(full_path)
            item = r['url']['node']['episodes']
            id = [i['id'] for i in item if i['content']['episodeNumber'] == int(data['episode'])][0]
        else:
            id = r['url']['node']['id']

        result = self.justwatch.get_providers(id)

        if not result:
            raise Exception(f"{title!r} not found in jw database")
        # fflog(f'justwatch {result=}')

        offers = result['node']

        if not offers:
            raise Exception(f"{title!r} not available in {self.country!r}")

        services: Set[str] = set()
        try:
            services = {o['package']['clearName'] for o in offers['flatrate']}
        except KeyError:
            fflog_exc()
        fflog(f'[EXTERNAL] justwatch offers: {sorted(services)}')
        # fflog(f'[EXTERNAL] justwatch offers: {json.dumps(offers, indent=2)}')  # full JSON dump

        streams: List[Union[Tuple[ExternalSource, str], MutableMapping[str, Any]]] = []

        if (ext := external_sources.get('netflix')) and ext.enabled:
            try:
                for url in ext.links(offers):
                    nfx_id = url.rstrip("/").split("/")[-1]
                    if content == "movie":
                        netflix_id = nfx_id
                        streams.append((ext, netflix_pattern % netflix_id))
                    else:
                        netflix_id = self.netflix_ep_id(nfx_id, data["season"], data["episode"])
                        url = netflix_show_pattern % (nfx_id, netflix_id[1], netflix_id[0])
                        streams.append((ext, url))
            except Exception:
                pass

        if (ext := external_sources.get('prime')) and ext.enabled:
            try:
                for url in ext.links(offers):
                    prime_id = url.rstrip("/").split("gti=")[1]
                    streams.append((ext, prime_pattern % prime_id))
            except Exception:
                fflog_exc()
                pass

        if (ext := external_sources.get('max')) and ext.enabled:
            try:
                for url in ext.links(offers):
                    max_id = url.rstrip("/").split("/")[-1]
                    if content == "movie":
                        max_id = max_id.split("?")[0]
                    streams.append((ext, max_pattern + max_id))
            except Exception:
                pass

        if (ext := external_sources.get('skyott')) and ext.enabled:
            try:
                for url in ext.links(offers):
                    sott_id = url.split('https://www.skyshowtime.com/pl/stream')
                    streams.append((ext, skyott_pattern + sott_id[1]))
            except Exception:
                pass

        if (ext := external_sources.get('viaplay')) and ext.enabled:
            try:
                for url in ext.links(offers):
                    html = requests.get(url).text
                    if mch := re.search(r'<script\s+id="__NEXT_DATA__"\s+type="application/json"\s*>', html):
                        start = mch.end()
                        if (end := html.index('</script>', start)) > 0:
                            data = json.loads(html[start:end])
                            # fflog(json.dumps(data, indent=2))
                            raw = data['props']['pageProps']['storeState']['page']['raw']
                            guid = raw['_embedded']['viaplay:blocks'][0]['_embedded']['viaplay:product']['system']['guid']
                            streams.append((ext, viaplay_pattern % guid))
            except Exception:
                fflog_exc()
                pass

        if (ext := external_sources.get('disney')) and ext.enabled:
            try:
                profile_id = "default"  # wiem, że nie ma profilu "default" ale tym bardziej None
                content_id = None  # Initialize content_id here

                dnp = [o for o in offers['flatrate'] if o['package']['clearName'] in ext.packages]
                if dnp:
                    deeplinkRoku = dnp[0].get("deeplinkRoku")
                    if deeplinkRoku:
                        deeplinkRoku = deeplinkRoku.split('?')[-1]
                        deeplinkRoku = parse_qs(deeplinkRoku)
                        content_id = deeplinkRoku.get("contentID")[0] if deeplinkRoku.get("contentID") else ""

                if content_id:
                    streams.append((ext, disney_pattern % (content_id, profile_id)))
                else:
                    for url in ext.links(offers):
                        deeplink_id = None
                        # fflog(f'Disney processing Disney+ URL: {url}')

                        if 'disneyplus.bn5x.net' in url or 'u=' in url:
                            # Dekoduj URL z parametru u=
                            from urllib.parse import unquote
                            if 'u=' in url:
                                actual_url = unquote(url.split('u=')[1].split('&')[0])
                                # fflog(f'Disney decoded Disney+ URL: {actual_url}')
                                url = actual_url

                        if 'disneyplus.com' in url:
                            patterns = [
                                r'entity-([a-f0-9-]+)',      # /browse/entity-UUID
                                r'/movies/([^/?]+)',          # /movies/title-slug
                                r'/series/([^/?]+)',          # /series/title-slug
                                r'/video/([a-f0-9-]+)',      # /video/UUID
                            ]

                            for pattern in patterns:
                                match = re.search(pattern, url)
                                if match:
                                    deeplink_id = match.group(1)
                                    # fflog(f'Disney extracted deeplink_id: {deeplink_id} using pattern: {pattern}')
                                    break

                                    disney_pattern_nocontentid
                            streams.append((ext, disney_pattern_nocontentid % (deeplink_id, profile_id)))
                            break
                        # else:
                            # fflog(f'Disney could not extract deeplink_id from: {url}')

            except Exception:
                fflog_exc()
                pass

        # internal function, to allow access to streams, offers, jget...
        def playerpl_source(ext: ExternalSource, url_pattern: str, profile: Optional[str] = None):
            """notoco will add documentation here..."""

            def append(vod):
                # nonlocal count
                # count += 1
                quality = "4K" if vod.get("uhd") else "1080p"
                streams.append({
                    "external_source": ext,
                    "url": url_pattern.format(id=vod['id'], profile=profile),
                    "quality": quality,
                })

            try:
                plp = [o for o in offers['flatrate'] if o['package']['clearName'] in ext.packages]
                if plp:
                    plp_id = plp[0]["standardWebURL"]
                    # fflog(f'[EXTERNAL][{ext.id.upper()}] Processing URL: {plp_id}')

                    r = re.search((r"(?:/(?P<serial_slug>[^/]*)-odcinki,(?P<sid>\d+))?"
                                   r"/(?P<slug>[^/]+?)(?:,S(?P<season>\d+)E(?P<episode>\d+))?,(?P<id>\d+)$"),
                                  plp_id, )
                    slug = aid = sn = en = ''
                    if r:
                        slug, aid, sn, en = r.group("slug", "id", "season", "episode")
                        # fflog(f'[EXTERNAL][{ext.id.upper()}] Extracted: slug={slug}, aid={aid}, sn={sn}, en={en}')
                        if sn:
                            slug = r.group("serial_slug")
                            sn, en = int(sn), int(en)

                    params = {
                        'platform': 'BROWSER'
                    }
                    api = jget(f'https://player.pl/playerapi/item/translate?articleId={aid}', params=params)
                    # fflog(f'[EXTERNAL][{ext.id.upper()}] Translate API Response: {json.dumps(api, indent=2)}')

                    # count = 0
                    if api and api.get("id"):
                        internal_id = api["id"]
                        # fflog(f'[EXTERNAL][{ext.id.upper()}] Found internal ID: {internal_id}')
                        vod_details = jget(f"https://player.pl/playerapi/product/vod/{internal_id}", params=params)
                        # fflog(f'[EXTERNAL][{ext.id.upper()}] VOD Details Response (by internal ID): {json.dumps(vod_details, indent=2)}')
                        if vod_details:
                            append(vod_details)

                # if not count:
                #    fflog(f'[EXTERNAL][{ext.id.upper()}] no items found for {plp_id}')
                #    if const.sources.external.playerpl.fallback:
                #        fallback(plp_id)
            except Exception:
                fflog_exc()

        if (ext := external_sources.get('playerpl')) and ext.enabled:
            playerpl_source(ext, playerpl_pattern)

        if (ext := external_sources.get('playerpl_mtr')) and ext.enabled:
            try:
                profile = xbmcaddon.Addon('plugin.video.player_pl').getSetting('profile_uid')
            except RuntimeError:
                profile = ''
            playerpl_source(ext, playerplmtr_pattern, profile)

        if (ext := external_sources.get('iplayer')) and ext.enabled:
            try:
                for url in ext.links(offers):
                    streams.append((ext, iplayer_pattern % quote_plus(url)))
            except Exception:
                fflog_exc()
                pass

        if (ext := external_sources.get('curstream')) and ext.enabled:
            try:
                for url in ext.links(offers):
                    cts_id = url.rstrip("/").split("/")[-1]
                    streams.append((ext, curstream_pattern + cts_id))
            except Exception:
                pass

        if (ext := external_sources.get('hulu')) and ext.enabled:
            try:
                for url in ext.links(offers):
                    hulu_id = url.rstrip("/").split("/")[-1]
                    streams.append((ext, hulu_pattern + hulu_id))
            except Exception:
                pass

        if (ext := external_sources.get('paramount')) and ext.enabled:
            try:
                for url in ext.links(offers):
                    pmp_id = (url.split("?")[0].split("/")[-1] if content == "movie" else re.findall("/video/(.+?)/", url)[0])
                    streams.append((ext, paramount_pattern + pmp_id))
            except Exception:
                pass

        if (ext := external_sources.get('cda')) and ext.enabled:
            try:
                for url in ext.links(offers):
                    for variant, url in cda_alternatives(url):
                        streams.append({
                            'url': cda_pattern.format(id=cda_id(url)),
                            'external_source': ext,
                            'info': variant,
                        })
            except Exception:
                pass

        if (ext := external_sources.get('cda_mb')) and ext.enabled:
            try:
                for url in ext.links(offers):
                    for variant, url in cda_alternatives(url):
                        streams.append({
                            'url': cdamb_pattern.format(id=cda_id(url), title=self.ffitem.title, image=''),
                            'external_source': ext,
                            'info': variant,
                        })
            except Exception:
                # fflog_exc()
                pass

        if (ext := external_sources.get('cda_mtr')) and ext.enabled:
            try:
                for url in ext.links(offers):
                    for variant, url in cda_alternatives(url):
                        streams.append({
                            'url': cdamtr_pattern.format(id=cda_id(url)),
                            'external_source': ext,
                            'info': variant,
                        })
            except Exception:
                # fflog_exc()
                pass

        # -------

        if streams:
            default = {"quality": "1080p", "language": "pl", "direct": True, "debridonly": False, "external": True, "info2": ""}
            for s in streams:
                if isinstance(s, MutableMapping):
                    ss = s
                else:
                    ss = {"external_source": s[0], "url": s[1]}
                ext: Optional[ExternalSource] = ss.pop('external_source', None)
                if ext:
                    ss.setdefault('source', ext.source)
                    if quality := const.sources_dialog.external_quality_label.get(ext.source):
                        ss.setdefault('quality', quality)
                    if icon := ext.icon():
                        ss.setdefault('icon', icon)
                sources.append({**default, **ss})
            return sources

    def resolve(self, url):
        return url

    def is_match(self, name, title, hdlr=None, aliases=None):
        try:
            name = name.lower()
            t = re.sub(r"(\+|\.|\(|\[|\s)(\d{4}|s\d+e\d+|s\d+|3d)(\.|\)|]|\s|)(.+|)", "", name)
            t = cleantitle.get(t)
            titles = [cleantitle.get(title)]

            if aliases:
                if not isinstance(aliases, list):
                    from ast import literal_eval

                    aliases = literal_eval(aliases)
                try:
                    titles.extend([cleantitle.get(i["title"]) for i in aliases])
                except Exception:
                    pass

            if hdlr:
                return t in titles and hdlr.lower() in name
            return t in titles
        except Exception:
            #fflog("is_match exc")
            return True

    def normalize(self, title):
        import unicodedata

        try:
            return str(
                "".join(c for c in unicodedata.normalize("NFKD", title) if unicodedata.category(c) != "Mn")).replace(
                "ł", "l")
        except Exception:
            title = (
                title.replace("ą", "a").replace("ę", "e").replace("ć", "c").replace("ź", "z").replace("ż", "z").replace(
                    "ó", "o").replace("ł", "l").replace("ń", "n").replace("ś", "s"))
            return title

    def netflix_ep_id(self, show_id, season, episode):
        netflix_search_pattern = "http://unogs.com/api/title/episodes?netflixid=%s"

        user_id = {'user_name': '1683364584.456'}
        response = self.session.post('http://unogs.com/api/user', data=user_id)

        token = response.json()['token']['access_token']

        headers = {
            'Accept': 'application/json',
            'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
            'Authorization': f'Bearer {token}',
            'Connection': 'keep-alive',
            'REFERRER': 'http://unogs.com',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
        }

        r = self.session.get(netflix_search_pattern % show_id, headers=headers, timeout=5)
        r.raise_for_status()
        r.encoding = "utf-8"
        apianswer = r.json()
        apifetch = [s["episodes"] for s in apianswer if s["season"] == int(season)][0]
        ep_id = str([e["epid"] for e in apifetch if e["epnum"] == int(episode)][0])
        seas_id = str([e["seasid"] for e in apifetch if e["seasnum"] == int(season)][0])

        return ep_id, seas_id


def cda_id(url: str) -> str:
    """Return cda id from cda url."""
    return re.sub(r'^.*video/([^/]+)/vfilm$', r'\1', url)


def cda_alternatives(url: str) -> Sequence[Tuple[str, str]]:
    """
    Return sequence of (variant, url).
    Find CDA movie alternatives (lector, subtitles) and return all link, original too.
    """
    try:
        resp = requests.get(url, timeout=5)
    except OSError:
        # cda down, return original only
        return (('', url),)
    if resp.status_code == 200:
        if mch := re.search(r'<meta\s+name="description"\s+content="[^"]*Wersja z (?P<type>\w+):\s*(?P<url>http[^"\s]+)[^"]*"', resp.text):
            alt_type, alt_url = mch.group('type', 'url')
            # jeśli alt to lektor, to my jesteśmy napisami
            if alt_type == 'lektorem':
                return (('napisy', url), ('lektor', alt_url))
            # jeśli alt to napisy, to my jesteśmy lektorem
            if alt_type == 'napisami':
                return (('lektor', url), ('napisy', alt_url))
            # jeśli alt to nie-wiadomo-co, to my jesteśmy nie-jeżyk (https://www.czu.pl/jezyk/)
            return (('', url), ('', alt_url))
    # brak alt
    return (('', url),)
