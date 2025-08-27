# -*- coding: utf-8 -*-

"""
    FanFilm Project
"""

from __future__ import annotations
from typing import ClassVar, Sequence, TYPE_CHECKING
import xbmcaddon
from urllib.parse import urlencode, parse_qsl, urlsplit
from lib.ff.kodidb import load_strm_file
from lib.ff.log_utils import fflog, fflog_exc
from lib.ff import control, source_utils
if TYPE_CHECKING:
    from .. import SourceItem


def ensure_str(s, encoding='utf-8', errors='strict'):
    if type(s) is str:
        return s
    if isinstance(s, bytes):
        return s.decode(encoding, errors)
    return s


ensure_text = ensure_str
plugin_id: str = control.plugin_id


class source:
    # This class has support for *.sort.order setting
    has_sort_order: ClassVar[bool] = False
    # This class has support for *.color.identify2 setting
    has_color_identify2: ClassVar[bool] = True
    # Mark sources with prem.color.identify2 setting
    use_premium_color: ClassVar[bool] = True
    # Supported languages
    # TODO: use const?
    language: ClassVar[Sequence[str]] = ("en", "de", "fr", "gr", "ko", "pl", "pt", "ru")
    # Provider priority.
    priority: ClassVar[int] = 1
    # Supported domains (not used here).
    domains: ClassVar[Sequence[str]] = ()

    def movie(self, imdb, title, localtitle, aliases, year):
        try:
            return urlencode({"imdb": imdb, "title": title, "localtitle": localtitle, "year": year})
        except Exception:
            return

    def tvshow(self, imdb, tmdb, tvshowtitle, localtvshowtitle, aliases, year):
        try:
            return urlencode({"imdb": imdb, "tmdb": tmdb, "tvshowtitle": tvshowtitle, "localtvshowtitle": localtvshowtitle, "year": year})
        except Exception:
            return

    def episode(self, url, imdb, tmdb, title, premiered, season, episode):
        if url is None:
            return
        try:
            url = dict(parse_qsl(url))
            url.update({"premiered": premiered, "season": season, "episode": episode})
            return urlencode(url)
        except Exception:
            return

    def sources(self, url, hostDict, hostprDict) -> list[SourceItem]:
        from lib.ff.libtools import LibTools
        if url is None:
            return []

        library = LibTools()
        data = dict(parse_qsl(url))
        content_type = "episode" if "tvshowtitle" in data else "movie"
        lib = {}
        if content_type == "movie":
            lib = library.check_in_library(imdb_id=data['imdb'], year=data["year"], include_streamdetails=True)
        elif content_type == "episode":
            lib = library.check_in_library(imdb_id=data["imdb"], year=data["year"], season=data["season"], episode=data["episode"],
                                           include_streamdetails=True)
        else:
            return []
        fflog(f"DEBUG: r from check_in_library: {lib}")

        if not isinstance(lib, dict) or "file" not in lib:
            return []

        url = lib["file"]
        qual = -1  # Initialize qual to a default value
        try:
            fflog(f"DEBUG: streamdetails: {lib.get('streamdetails')}")
            if "streamdetails" in lib and lib["streamdetails"] and "video" in lib["streamdetails"] and lib["streamdetails"]["video"]:
                qual = int(lib["streamdetails"]["video"][0]["width"])
        except Exception:
            fflog_exc()  # Log the exception for debugging

        if qual >= 2160:
            quality = "4K"
        elif 1920 <= qual < 2000:
            quality = "1080p"
        elif 1280 <= qual < 1900:
            quality = "720p"
        else:  # qual < 1280:
            quality = "SD"

        info = []
        name = ''
        icon = ''
        size = ''
        try:
            f = control.openFile(url)
            try:
                if '://' not in url and url.lower().endswith('.strm'):
                    strm = load_strm_file(url)
                    if strm.startswith('plugin://'):
                        u = urlsplit(strm)
                        if u.hostname == plugin_id:
                            return []
                        try:
                            addon = xbmcaddon.Addon(u.hostname)
                            icon, name = addon.getAddonInfo('icon'), addon.getAddonInfo('name')
                        except Exception:
                            name = u.hostname or ''
                        url = strm
                    else:
                        strm = load_strm_file(url)
                        name = strm
                        url = strm
                else:
                    size = source_utils.convert_size(f.size())
            finally:
                f.close()
        except Exception:
            pass

        try:
            c = lib["streamdetails"]["video"][0]["codec"]
            if c == "avc1":
                c = "h264"
            if c == "h265":
                c = "hevc"
            info.append(c)
        except Exception:
            pass

        try:
            ac = lib["streamdetails"]["audio"][0]["codec"]
            if ac == "eac3":
                ac = "dd+"
            if ac == "dca":
                ac = "dts"
            if ac == "dtshd_ma":
                ac = "dts-hd ma"
            info.append(ac)
        except Exception:
            pass

        try:
            ach = lib["streamdetails"]["audio"][0]["channels"]
            if ach == 1:
                ach = "mono"
            if ach == 2:
                ach = "2.0"
            if ach == 6:
                ach = "5.1"
            if ach == 7:
                ach = "6.1"
            if ach == 8:
                ach = "7.1"
            info.append(ach)
        except Exception:
            pass

        info = " ".join(info)
        lang = source_utils.get_lang_by_type(url)[0]  # ja dodałem detekcję

        return [{
            "source": name,
            "quality": quality,
            "language": lang,
            "url": url,
            "info": info,
            "size": size,
            "local": True,
            "direct": True,
            "debridonly": False,
            "icon": icon,
        }]

    def resolve(self, url):
        return url
