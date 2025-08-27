# -*- coding: utf-8 -*-
"""
FanFilm ‑ źródło: cda.pl
Copyright (C) 2018 :)

Dystrybuowane na licencji GPL‑3.0.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from ast import literal_eval
from typing import Any, Dict, List, Set, cast

from difflib import SequenceMatcher
from urllib.parse import urlencode

from lib.ff import cache, cleantitle, control, requests, source_utils
from lib.ff.item import FFItem
from lib.ff.log_utils import fflog, fflog_exc
from lib.ff.settings import settings
from lib.ff.source_utils import convert_size
from const import const

try:  # RapidFuzz jest ~10× szybszy od difflib, ale add‑on działa także bez niego
    from rapidfuzz import fuzz  # type: ignore
except ImportError:  # pragma: no cover
    fuzz = None


# -----------------------------------------------------------------------------
#  KONFIGURACJA
# -----------------------------------------------------------------------------
USER_AGENT: str = (
    "pl.cda 1.0 "
    "(version 1.2.255 build 21541; Android 11; Google sdk_gphone_x86)"
)
HASH_SALT: bytes = (
    b"s01m1Oer5IANoyBXQETzSOLWXgWs01m1Oer5bMg5xrTMMxRZ9Pi4fIPeFgIVRZ9PeXL8mPf"
    b"XQETZGUAN5StRZ9P"
)
BASIC_AUTH: str = (
    "Basic YzU3YzBlZDUtYTIzOC00MWQwLWI2NjQtNmZmMWMxY2Y2YzVlOklBTm95QlhRRVR6"
    "U09MV1hnV3MwMW0xT2VyNWJNZzV4clRNTXhpNGZJUGVGZ0lWUlo5UGVYTDhtUGZaR1U1U3Q"
)
BASE_LINK: str = "https://api.cda.pl"
SEARCH_LINK: str = f"{BASE_LINK}/video/search"

TITLE_STOPWORDS: Set[str] = {
    "lektor",
    "dubbing",
    "napisy",
    "zwiastun",
    "trailer",
    "recenzja",
    "omowienie",
    "podsumowanie",
    "gameplay",
    "nazywo",
    "walktrough",
    "stream",
    "opis",
    "newsy",
}
TITLE_EXCLUDE_WORDS: Set[str] = {
    "cały sezon",
    "kolekcja",
    "box",
    "pakiet",
    "antologia",
    "zwiastun",
    "trailer",
    "recenzja",
    "omowienie",
    "podsumowanie",
    "omówienie",
    "gameplay",
    "nazywo",
    "walktrough",
    "stream",
    "opis",
    "newsy",
    "online",
    "playstation",
    "xbox",
    "ps3",
    "ps4",
    "ps5",
    "xbox360",
    "xboxone",
    "xboxone s",
    "xboxone x",
    "xbox series s",
    "xbox series x",
    "nintendo",
    "switch",
    "soundtrack",
}
YEAR_REGEX = re.compile(r"\b(?:19|20)\d{2}\b")


# -----------------------------------------------------------------------------
#  GŁÓWNA KLASA ŹRÓDŁA
# -----------------------------------------------------------------------------
class source:  # noqa: N801  (nazwa utrzymywana ze względów zewnętrznych)

    # FF sources korzysta z tych pól – nie zmieniamy
    has_sort_order: bool = True
    has_color_identify2: bool = True
    ffitem: FFItem  # ↓ przypisany dynamicznie przez FanFilm

    # ---------------------------------------------------------------------
    #  INIT
    # ---------------------------------------------------------------------
    def __init__(self) -> None:
        self.priority: int = 1
        self.language: List[str] = ["pl"]
        self.domains: List[str] = ["cda.pl"]

        # dane logowania z ustawień add‑ona
        self.email: str = settings.getString("cda.username")
        self.passwd_ctrl: str = settings.getString("cda.password")
        self.passwd: str = self._hash_password(self.passwd_ctrl)

        # sesja HTTP
        self.session: requests.Session = requests.Session()
        self.headers: Dict[str, str] = {
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.cda.public+json",
        }
        self.headers_basic: Dict[str, str] = {"Authorization": BASIC_AUTH}

        # meta
        self.anime: bool = False
        self.year: int = 0
        self.duration: int = 20 * 60  # domyślny limit (sekundy)

    # ------------------------------------------------------------------ #
    #  NARZĘDZIA  (hash, normalizacja, fuzzy‑matching, rok, itp.)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _hash_password(passwd: str) -> str:
        """PBKDF–like hash używany przez API CDA przy logowaniu."""
        md5 = hashlib.md5(passwd.encode("utf-8")).hexdigest().encode("utf-8")
        digest = hmac.new(HASH_SALT, md5, hashlib.sha256).digest()
        return (
            base64.b64encode(digest).decode("utf-8").replace("/", "_")
            .replace("+", "-")
            .replace("=", "")
        )

    @staticmethod
    def _levenshtein(a: str, b: str) -> int:
        """Iteracyjny Levenshtein (Wikipedia)."""
        if a == b:
            return 0
        if not a:
            return len(b)
        if not b:
            return len(a)

        v0 = list(range(len(b) + 1))
        v1 = [0] * (len(b) + 1)

        for i, ca in enumerate(a):
            v1[0] = i + 1
            for j, cb in enumerate(b):
                cost = 0 if ca == cb else 1
                v1[j + 1] = min(v1[j] + 1, v0[j + 1] + 1, v0[j] + cost)
            v0, v1 = v1, v0
        return v0[len(b)]

    @staticmethod
    def _similar(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()

    # ------------------------------------------------------------------ #
    #  NORMALIZACJA I MATCHING TYTUŁÓW
    # ------------------------------------------------------------------ #
    def _normalize_title(self, txt: str) -> str:
        """Czysty, małymi literami, bez stop słów i roku w nawiasach."""
        if not txt:
            return ""
        txt = cleantitle.normalize(txt)
        txt = re.sub(r"[\(\[]\s*\d{4}\s*[\)\]]", "", txt)
        txt = re.sub(r"\bpl\b", "", txt, flags=re.I)
        txt = re.sub(r"[^0-9a-ząćęłńóśźż]+", " ", txt.lower())
        return " ".join(
            w for w in txt.split() if w and w not in TITLE_STOPWORDS
        )

    # — token‑ratio (opcjonalnie RapidFuzz) —
    def _token_set_ratio(self, a: str, b: str) -> float:
        if fuzz:
            return fuzz.token_set_ratio(a, b) / 100.0
        return self._similar(" ".join(sorted(a.split())),
                             " ".join(sorted(b.split())))

    # — fuzzy‑porównanie słowo‑po‑słowie + pokrycie —
    def _all_words_match(
        self,
        expected: str,
        candidate: str,
        *,
        rel_tol: float = 0.25,
        abs_tol_short: int = 1,
        abs_tol_long: int = 2,
        min_coverage: float = 0.40,
    ) -> bool:
        exp_words: List[str] = self._normalize_title(expected).split()
        cand_words: List[str] = self._normalize_title(candidate).split()
        if not exp_words or not cand_words:
            return False

        # 1. Każde słowo z expected musi się znaleźć (z literówką)
        for w in exp_words:
            if len(w) <= 2:
                continue
            if not any(
                self._words_similar(w, c, rel_tol,
                                    abs_tol_short, abs_tol_long)
                for c in cand_words
            ):
                return False

        # 2. Pokrycie – odsetek słów kandydata, które udało się sparować
        matched = sum(
            1
            for c in cand_words
            if any(
                self._words_similar(w, c, rel_tol,
                                    abs_tol_short, abs_tol_long)
                for w in exp_words
            )
        )
        return matched / len(cand_words) >= min_coverage

    def _words_similar(
        self,
        w: str,
        c: str,
        rel_tol: float,
        abs_tol_short: int,
        abs_tol_long: int,
    ) -> bool:
        """Czy dwa pojedyncze słowa są podobne wg zadanego progu."""
        dist: int = cast(int, self._levenshtein(w, c))
        if (len(w) <= 4 and dist <= abs_tol_short) or (
            len(w) > 4 and dist <= abs_tol_long
        ):
            return True
        return dist / max(len(w), len(c)) <= rel_tol

    # — rok —
    def _year_matches(
        self,
        candidate: str,
        expected_year: int,
        tolerance: int = 1,
    ) -> bool:
        if expected_year <= 0:
            return True
        years = [int(y) for y in YEAR_REGEX.findall(candidate)]
        if not years:
            return True
        return any(abs(y - expected_year) <= tolerance for y in years)

    # ------------------------------------------------------------------ #
    #  LOGOWANIE / TOKENY
    # ------------------------------------------------------------------ #
    def _check_email(self, email: str) -> bool:
        self.headers.update(self.headers_basic)
        resp = self.session.post(
            f"{BASE_LINK}/register/check-email",
            data={"email": email},
            headers=self.headers,
        )
        return bool(resp.json())

    def oauth(self, email: str, passwd: str) -> None:  # nazwa wymagana
        """Uzyskaj token dostępu i zapisz w cache’u."""
        self.headers.update(self.headers_basic)
        if not self._check_email(email):
            return

        payload = {"grant_type": "password", "login": email, "password": passwd}
        user = self.session.post(
            f"{BASE_LINK}/oauth/token", data=payload, headers=self.headers
        ).json()
        if user.get("access_token") and user.get("refresh_token"):
            cache.cache_insert("cda_token", user["access_token"],
                               control.providercacheFile)
            cache.cache_insert("cda_ref_token", user["refresh_token"],
                               control.providercacheFile)

    # ------------------------------------------------------------------ #
    #  INTERFEJS FANFILM (movie / tvshow / episode)
    # ------------------------------------------------------------------ #
    def movie(self, imdb, title, localtitle, aliases, year):
        return self.search(title, localtitle, year, True)

    def tvshow(self, imdb, tmdb, tvshowtitle, localtvshowtitle, aliases, year):
        return (tvshowtitle, localtvshowtitle), year

    def episode(
        self, url, imdb, tmdb, title, premiered, season, episode
    ):
        self.year = int(url[1])
        ep_no = f"s{season.zfill(2)}e{episode.zfill(2)}"
        return self.search_ep(url[0][0], url[0][1], self.year, ep_no)

    # ------------------------------------------------------------------ #
    #  WYSZUKIWANIE
    # ------------------------------------------------------------------ #
    def search(
        self,
        title: str,
        localtitle: str,
        year: int,
        is_movie_search: bool,  # zachowujemy parametr, choć nieużywany
    ) -> List[str]:
        result_ids: List[str] = []
        search_terms = {
            cleantitle.normalize(cleantitle.getsearch(title)),
            cleantitle.normalize(cleantitle.getsearch(localtitle)),
        }
        for term in filter(None, search_terms):
            result_ids += self._search_single_term(term, year)
        return list(dict.fromkeys(result_ids))  # unikalne

    def _search_single_term(self, term: str, year: int) -> List[str]:
        q_term = term.replace("'", "").replace(":", "").replace("-", " ").lower()
        params = {
            "query": q_term,
            "duration": "medium",
            "page": 1,
            "limit": 100,
            "sort": "best",
        }

        # autoryzacja (raz na sesję)
        if self.email:
            self.oauth(self.email, self.passwd)
            self.headers["Authorization"] = f"Bearer {cache.cache_value('cda_token', control.providercacheFile)}"

        try:
            data = self.session.get(
                SEARCH_LINK, params=params, headers=self.headers
            ).json()
        except Exception:  # pragma: no cover
            fflog_exc()
            return []

        results: List[str] = []
        for item in data.get("data", []):
            cand_title = item["title"]
            if any(word in cand_title.lower() for word in TITLE_EXCLUDE_WORDS):
                continue
            if (
                self._all_words_match(term, cand_title)
                and self._year_matches(cand_title, int(year))
            ):
                results.append(item["id"])
        return results

    # —­­ odcinki —
    def search_ep(
        self,
        title: str,
        localtitle: str,
        year: int,
        ep_no: str,
    ) -> List[str]:
        result_ids: List[str] = []
        params = {
            "query": f"{localtitle.lower()} {ep_no}",
            "duration": "medium",
            "page": 1,
            "limit": 100,
            "sort": "best",
        }

        if self.email:
            self.oauth(self.email, self.passwd)
            self.headers["Authorization"] = f"Bearer {cache.cache_value('cda_token', control.providercacheFile)}"

        data = self.session.get(
            SEARCH_LINK, params=params, headers=self.headers
        ).json()

        name_norm = cleantitle.normalize(title).lower()
        local_norm = cleantitle.normalize(localtitle).lower()

        for item in data.get("data", []):
            cand_title = item["title"]
            if ep_no in cand_title.lower() and self._year_matches(
                cand_title, year
            ):
                if self._all_words_match(f"{name_norm} {ep_no}", cand_title) or (
                    self._all_words_match(f"{local_norm} {ep_no}", cand_title)
                ):
                    result_ids.append(item["id"])
        return result_ids

    # ------------------------------------------------------------------ #
    #  POZOSTAŁE NARZĘDZIA
    # ------------------------------------------------------------------ #
    def compare_duration(self, ffduration: int, duration: int | None) -> bool:
        duration = duration or 0
        return abs(ffduration - duration) <= ffduration * const.sources.cda.duration_epsilon

    # ------------------------------------------------------------------ #
    #  ŹRÓDŁA / ROZWIĄZYWANIE
    # ------------------------------------------------------------------ #
    def sources(self, ids, hostDict, hostprDict):
        sources = []
        try:
            if ids is None:
                return sources
            else:
                # Store all DRM sources to add them at the end
                drm_sources = []

                for url in ids:
                    if self.email:
                        self.headers.update({
                            'Authorization': f'Bearer {cache.cache_value("cda_token", control.providercacheFile)}'
                        })
                    query = self.session.get(f'{BASE_LINK}/video/{url}', headers=self.headers).json()
                    if not query.get('error'):
                        video = query.get('video')
                        if not self.compare_duration(self.ffitem.vtag.getDuration(), video.get("duration")):
                            continue

                        # Calculate quality score for prioritization
                        height = video.get('height', 0)
                        width = video.get('width', 0)

                        info_parts = []
                        # Handle LEKTOR, NAPISY, DUBBING - various formats
                        title = video['title']
                        title_lower = title.lower()

                        # Check for dubbing variants
                        if any(phrase in title_lower for phrase in ['dubbing pl', 'pldub', 'pl dub', 'dubbing']):
                            info_parts.append('DUBBING')
                        # Check for lektor variants
                        elif any(phrase in title_lower for phrase in ['lektor pl', 'pllek', 'pl lek', 'lektor']):
                            info_parts.append('LEKTOR')
                        # Check for napisy variants
                        elif any(phrase in title_lower for phrase in ['napisy pl', 'plsub', 'pl sub', 'napisy']):
                            info_parts.append('NAPISY')
                        # Handle PREMIUM.
                        if video.get('premium'):
                            if video.get('premium_free'):
                                info_parts.append(const.sources.cda.show_premium_free)
                            else:
                                info_parts.append('Premium')
                        # TODO: handle video['audio_51']
                        if video.get('audio_51'):
                            info_parts.append('5.1')
                        # build info
                        info = ' | '.join(e for e in info_parts if e)
                        premium = 'premium' in info.lower()

                        if const.sources_dialog.cda_drm:
                            # check adaptive stream
                            adaptive_data = video.get('quality_adaptive')
                            if adaptive_data:
                                highest_quality = self._get_highest_quality_direct(video)
                                adaptive_quality = source_utils.get_quality(highest_quality)

                                # fflog(f'[CDA][DRM] Video: {title}')
                                # fflog(f'[CDA][DRM] Quality: {highest_quality}, Dimensions: {width}x{height}')
                                # fflog(f'[CDA][DRM] Manifest: {adaptive_data.get("manifest")}')

                                # Add each DRM source to the list with unique identifier
                                drm_source_info = {
                                    'adaptive_data': adaptive_data,
                                    'video_info': {
                                        'title': title,
                                        'quality': highest_quality,
                                        'adaptive_quality': adaptive_quality,
                                        'info': info,
                                        'premium': premium,
                                        'url': url,
                                        'width': width,
                                        'height': height
                                    }
                                }
                                drm_sources.append(drm_source_info)

                        # Regular direct sources
                        qualities = {
                            '1080p': '1080p',
                            '720p': '720p',
                        }
                        for variant in video['qualities']:
                            if variant.get('file'):
                                variant_info = f'{info}' if info else ''
                                sources.append({
                                    "source": "CDA",
                                    "quality": qualities.get(variant['name'], 'SD'),
                                    "language": 'pl',
                                    "url": variant['file'],
                                    "info": variant_info,
                                    "filename": video['title'],
                                    "direct": True,
                                    "debridonly": False,
                                    "size": convert_size(variant['length']),
                                    "premium": premium,
                                })
                            else:
                                print('Brak linku Direct - Niezalogowany lub content Premium')

                # Now add ALL DRM sources
                if const.sources_dialog.cda_drm and drm_sources:
                    # fflog(f'[CDA][DRM] Adding {len(drm_sources)} DRM sources')

                    # Sort DRM sources by quality score first, then by width for same quality
                    for i, drm_source in enumerate(drm_sources):
                        adaptive_data = drm_source['adaptive_data']
                        video_info = drm_source['video_info']

                        # Create unique cache key for each DRM source
                        cache_key = f'DRMCDA_{video_info["url"]}_{i}'
                        cache.cache_insert(cache_key, repr(adaptive_data), control.providercacheFile)

                        # Build source info
                        source_info_parts = []
                        if video_info['info']:
                            source_info_parts.append(video_info['info'])
                        source_info_parts.append("DRM")
                        source_info = ' | '.join(source_info_parts)

                        # fflog(f'[CDA][DRM] Adding DRM source #{i+1}: {video_info["quality"]}')
                        # fflog(f'[CDA][DRM] Manifest: {adaptive_data.get("manifest")}')

                        sources.append({
                            "source": "CDA",
                            "quality": video_info['adaptive_quality'],
                            "language": 'pl',
                            "url": f'{cache_key}|{video_info["url"]}',
                            "info": source_info,
                            "filename": video_info['title'],
                            "direct": True,
                            "debridonly": False,
                            "premium": video_info['premium'],
                        })
            return sources
        except Exception:
            fflog_exc()
            return sources


    def _get_highest_quality_direct(self, video: Dict[str, Any]) -> str:
        """
        Directly determine the highest quality available.
        Check video dimensions first, then available quality variants.
        """
        height = video.get('height', 0)
        width = video.get('width', 0)

        # Get all available quality names from variants
        available_qualities = set()
        for variant in video.get('qualities', []):
            if variant.get('name'):
                available_qualities.add(variant['name'])

        # fflog(f'[CDA] Video dimensions: {width}x{height}, Available qualities: {available_qualities}')

        # Determine quality based on dimensions (most reliable)
        if height >= 1080 or width >= 1920:
            if '1080p' in available_qualities:
                return '1080p'
        elif height >= 720 or width >= 1280:
            if '720p' in available_qualities:
                return '720p'

        # If dimension-based detection fails, check available qualities in order
        quality_priority = ['1080p', '720p', '480p', '360p']
        for quality in quality_priority:
            if quality in available_qualities:
                # fflog(f'[CDA] Selected quality by priority: {quality}')
                return quality

        # Final fallback
        fallback = video.get('quality', '480p')
        # fflog(f'[CDA] Using fallback quality: {fallback}')
        return fallback

    # —­­ DRM / zwykłe linki —
    def resolve(self, url):
        # Data for InputStreamHelper.
        # InputStream old properties – deprecated (Kodi 18-22).
        # See: https://github.com/xbmc/inputstream.adaptive/wiki/Integration-DRM
        if 'DRMCDA' in str(url):
            from lib.service.client import service_client

            # Extract cache key from URL (format: cache_key|video_url)
            url_parts = url.split('|')
            cache_key = url_parts[0] if len(url_parts) > 1 else 'DRMCDA'

            # fflog(f'[CDA] DRM resolve using cache key: {cache_key}')

            if adaptive := literal_eval(cache.cache_value(cache_key, control.providercacheFile)):
                fflog(f'[CDA] DRM resolve: {adaptive=}')
            else:
                fflog(f'[CDA] DRM FAILED: no {cache_key}')
                raise ValueError(f'[CDA] DRM FAILED: no {cache_key}')

            PROTOCOL = 'mpd'
            DRM = 'com.widevine.alpha'
            manifest_url = adaptive.get('manifest')
            lic_url = adaptive.get('widevine_license')

            # fflog(f'[CDA] DRM manifest URL: {manifest_url}')
            # fflog(f'[CDA] DRM license URL: {lic_url}')

            # Sprawdź czy manifest URL jest prawidłowy
            if not manifest_url:
                fflog('[CDA] DRM FAILED: no manifest URL')
                raise ValueError('[CDA] DRM FAILED: no manifest URL')

            # Preferuj H264 manifest jeśli dostępny (lepiej wspierany)
            # Preferuj H264 manifest, ale z fallback
            manifest_url = adaptive.get('manifest')
            manifest_h264 = adaptive.get('manifest_h264')

            if manifest_h264:
                # Sprawdź czy H264 manifest jest stabilny/dostępny
                try:
                    # Możesz dodać szybki test dostępności manifestu
                    manifest_url = manifest_h264
                    fflog(f'[CDA] Using H264 manifest for higher quality')
                except Exception as e:
                    fflog(f'[CDA] H264 manifest failed, using default: {e}')
                    # Zostaje przy domyślnym manifest_url

            drm_header = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/116.0.0.0 Safari/537.36 Edg/116.0.1938.62',
                'X-Dt-Custom-Data': adaptive.get('drm_header_value'),
                'Content-Type': 'application/octet-stream',
            }

            # FF HTTP server (licence proxy), tunneling licence url
            if lic_url:
                lic_url = f'{service_client.url}drm={lic_url}'
            else:
                fflog('[CDA] Warning: No license URL found')

            adaptive_data = {
                'protocol': PROTOCOL,
                'licence_type': DRM,
                'mimetype': 'application/xml+dash',
                'manifest': manifest_url,
                'licence_url': lic_url,
                'licence_header': urlencode(drm_header) if lic_url else '',
                'post_data': 'R{SSM}' if lic_url else '',
                'response_data': '',  # InputStream example uses 'R' here
                'stream_headers': drm_header,
                # 'adaptive_max_bandwidth': '8000000'  # Limit bandwidth jeśli potrzeba
            }

            link = f'DRMCDA|{repr(adaptive_data)}'
            # fflog(f'[CDA] DRM final link: {link}')

            # Test deserializacji
            try:
                test = literal_eval(link.split('|')[-1])
                fflog(f'[CDA] DRM data validation successful: manifest={test.get("manifest")}')
            except Exception as e:
                fflog(f'[CDA] DRM data validation failed: {e}')

            return link
        else:
            link = str(url).replace('\\', '/')
        return str(link)
