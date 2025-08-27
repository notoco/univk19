# -*- coding: utf-8 -*-

"""
    FanFilm Add-on

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

from typing import Optional, Union
import re
from urllib.parse import quote_plus, unquote, urlparse
from threading import Event, current_thread

from . import requests
import xbmc

from lib.ff import apis, client, directstream, cleantitle
from .settings import settings
# TODO: TRAKT  from lib.ff import trakt
from lib.ff.debug import log_exception
from .log_utils import fflog, fflog_exc


RES_4K = [
    " 4k",
    " hd4k",
    " 4khd",
    " uhd",
    " ultrahd",
    " ultra hd",
    " 2160",
    " 2160p",
    " hd2160",
    " 2160hd",
]
RES_1080 = [
    " 1080",
    " 1080p",
    " 1080i",
    " hd1080",
    " 1080hd",
    " m1080p",
    " fullhd",
    " full hd",
    " fhd",
    " 1o8o",
    " 1o8op",
]
RES_720 = [" 720", " 720p", " 720i", " hd720", " 720hd", " 72o", " 72op"]
RES_SD = [
    " 576",
    " 576p",
    " 576i",
    " sd576",
    " 576sd",
    " 480",
    " 480p",
    " 480i",
    " sd480",
    " 480sd",
    " 360",
    " 360p",
    " 360i",
    " sd360",
    " 360sd",
    " 240",
    " 240p",
    " 240i",
    " sd240",
    " 240sd",
]
RES_SCR = [" scr", " screener", " dvdscr", " dvd scr", " r5", " r6"]
RES_CAM = [
    " camrip",
    " tsrip",
    " hdcam",  # czy to zaliczać też?
    " hqcam",  # czy to zaliczać też?
    " hd cam",  # czy to zaliczać też?
    " cam rip",
    " hdts",  # czy to zaliczać też?
    " hd-ts",  # czy to zaliczać też?
    " dvdcam",
    " dvdts",
    " cam",
    " telesync",
    " ts",
]
AVC = [" h 264 ", " h264 ", " x264 ", " avc "]

# ADDITIONAL FOR EN SOURCES INFOS
CODEC_H265 = ["hevc", "h265", "x265"]
CODEC_H264 = ["avc", "h264", "x264"]
CODEC_XVID = ["xvid"]
CODEC_DIVX = ["divx", "div2", "div3"]
CODEC_MPEG = [
    "mpeg",
    "m4v",
    "mpg",
    "mpg1",
    "mpg2",
    "mpg3",
    "mpg4",
    "msmpeg",
    "msmpeg4",
    "mpegurl",
]
CODEC_MP4 = ["mp4"]
CODEC_M3U = ["m3u8", "m3u"]
CODEC_AVI = ["avi"]
CODEC_MKV = ["mkv", "matroska"]

AUDIO_8CH = ["ch8", "8ch", "ch7", "7ch", "7 1", "ch7 1", "7 1ch"]
AUDIO_6CH = [
    "ch6",
    "6ch",
    "ch6",
    "6ch",
    "6 1",
    "ch6 1",
    "6 1ch",
    "5 1",
    "ch5 1",
    "5 1ch",
]
AUDIO_2CH = ["ch2", "2ch", "stereo", "dualaudio", "dual", "2 0", "ch2 0", "2 0ch"]
AUDIO_1CH = ["ch1", "1ch", "mono", "monoaudio", "ch1 0", "1 0ch"]

VIDEO_3D = [
    "3d",
    "sbs",
    "hsbs",
    "sidebyside",
    "side by side",
    "stereoscopic",
    "tab",
    "htab",
    "topandbottom",
    "top and bottom",
]

# EN sources tem workaround
# quick workaround
host_limit = True #control.setting("host.limit") or "true"  # XXX missing setting 'host.limit'
host_limit_count = 3  #int(control.setting('host.count')) or '3'  # XXX missing setting 'host.count'

TMDB_API_URL = "https://api.themoviedb.org/3"
TMDB_API_KEY = (
    settings.getString("tmdb.api_key") or apis.tmdb_API
)  # Używaj metody control.setting do uzyskania klucza


def check_host_limit(
    item, items
):  # lazy way to use less code and limit the sources a bit. could likely be coded better but oh well.
    try:
        if host_limit:
            items = [i["source"] for i in items if "source" in i] or [i for i in items]
            if items.count(item) == host_limit_count:
                return True
            else:
                return False
        else:
            return False
    except Exception:
        return False


def supported_video_extensions():  # ok
    supported_video_extensions = xbmc.getSupportedMedia("video").split("|")
    unsupported = [
        "",
        ".url",
        ".bin",
        ".zip",
        ".rar",
        ".001",
        ".disc",
        ".7z",
        ".tar.gz",
        ".tar.bz2",
        ".tar.xz",
        ".tgz",
        ".tbz2",
        ".gz",
        ".bz2",
        ".xz",
        ".tar",
    ]
    return [i for i in supported_video_extensions if i not in unsupported]


def get_host(url):  # EN Sources
    try:
        url = url.replace(r"\/", r"/").replace(r"///", r"//")
        elements = urlparse(url)
        domain = elements.netloc or elements.path
        domain = domain.split("@")[-1].split(":")[0]
        res = re.search(r"(?:www\.)?([\w\-]*\.[\w\-]{2,3}(?:\.[\w\-]{2,3})?)$", domain)
        if res:
            domain = res.group(1)
        domain = domain.lower()
    except Exception:
        elements = urlparse(url)
        host = elements.netloc
        domain = host.replace("www.", "")
    return domain


def checkHost(url, hostList):  # EN Sources
    host = get_host(url)
    validHost = False
    for i in hostList:
        if i.lower() in url.lower():
            host = i
            validHost = True
            return validHost, host
    return validHost, host


def get_codec(term):  # EN Sources
    if any(value in term for value in CODEC_H265):
        _codec = "HEVC | "
    elif any(value in term for value in CODEC_H264):
        _codec = "AVC | "
    elif any(value in term for value in CODEC_MKV):
        _codec = "MKV | "
    elif any(value in term for value in CODEC_DIVX):
        _codec = "DIVX | "
    elif any(value in term for value in CODEC_MPEG):
        _codec = "MPEG | "
    elif any(value in term for value in CODEC_MP4):
        _codec = "MP4 | "
    elif any(value in term for value in CODEC_M3U):
        _codec = "M3U | "
    elif any(value in term for value in CODEC_XVID):
        _codec = "XVID | "
    elif any(value in term for value in CODEC_AVI):
        _codec = "AVI | "
    else:
        _codec = "0"
    return _codec


def get_audio(term):  # EN Sources
    if any(value in term for value in AUDIO_8CH):
        _audio = "7.1 | "
    elif any(value in term for value in AUDIO_6CH):
        _audio = "5.1 | "
    elif any(value in term for value in AUDIO_2CH):
        _audio = "2.0 | "
    elif any(value in term for value in AUDIO_1CH):
        _audio = "Mono | "
    else:
        _audio = "0"
    return _audio


def get_size(term):  # EN Sources
    try:
        _size = re.findall(r"(\d+(?:\.|/,|)?\d+(?:\s+|)(?:gb|GiB|mb|MiB|GB|MB))", term)
        _size = _size[0].encode("utf-8")
        _size = _size + " | "
    except Exception:
        _size = "0"
    return _size


def get_3D(term):  # EN Sources
    if any(value in term for value in VIDEO_3D):
        _3D = "3D | "
    else:
        _3D = "0"
    return _3D


def get_quality(term1, term2=None):  # OK + workaround for en sources
    if not term2:
        term = term1
    else:
        term = term1
        term += term2

    term = " {} ".format(term).lower()
    if any(i in term for i in RES_SCR):
        return "SCR"
    elif any(i in term for i in RES_CAM):
        return "CAM"
    elif any(i in term for i in RES_4K) and not any(i in term for i in RES_1080):
        return "4K"
    elif any(i in term for i in RES_1080):
        return "1080p"
    elif any(i in term for i in RES_720):
        return "720p"
    elif any(i in term for i in RES_SD):
        return "SD"
    elif "remux " in term and any(i in term for i in AVC):
        return "1080p"
    elif "remux " in term:
        return "4K"
    else:
        return "SD"


def get_info(term1, term2=None):  # EN Sources
    if not term2:
        term = term1
    else:
        term = term1
        term += term2
    _codec = get_codec(term)
    if not _codec or _codec == "0":
        _codec = ""
    _audio = get_audio(term)
    if not _audio or _audio == "0":
        _audio = ""
    _size = get_size(term)
    if not _size or _size == "0":
        _size = ""
    _3D = get_3D(term)
    if not _3D or _3D == "0":
        _3D = ""
    _info = _codec + _audio + _size + _3D
    return _info


def cleanup(term):  # EN Sources
    try:
        _term = strip_domain(term)
        _term = unquote(_term)
        _term = _term.lower()
        _term = re.sub("[^a-z0-9 ]+", " ", _term)
    except Exception:
        _term = str(term.lower())
    return _term


def cleanupALT(term):  # EN Sources
    try:
        _term = strip_domain(term)
        _term = _term.upper()
        _term = re.sub(r"(.+)(\.|\(|\[|\s)(\d{4}|S\d*E\d*|S\d*)(\.|\)|\]|\s)", "", _term)
        _term = re.split(r"\.|\(|\)|\[|\]|\s|-", _term)
        _term = [i.lower() for i in _term]
    except Exception:
        _term = str(term.lower())
    return _term


def get_release_quality(release_name, release_link=None):  # EN Sources
    try:
        if not release_name:
            return "SD", []
        try:
            release_name = cleanup(release_name)
            if release_link:
                release_link = cleanup(release_link)
        except Exception:
            release_name = cleanupALT(release_name)
            if release_link:
                release_link = cleanupALT(release_link)
        if release_link and release_link == release_name:
            release_link = None
        quality = get_quality(release_name, release_link)
        info = get_info(release_name, release_link)
        return quality, info
    except Exception:
        return "SD", []


def getFileType(url):
    try:
        url = url.lower()
        url = url.replace(" ", ".")  # for easier detection
        url = url.replace("_", ".")  # the same as above
        url = url.replace(".1080", ".Full")  # for case ..1995.1080p.. for 5.1 channels
        url = url.replace(".1440", "..1440")  # for case ..1995.1440p.. for 5.1 channels
        url = url.replace(
            ".10bit", "..10bit"
        )  # for case ..265.10bit..  for 5.1 channels
        url = url.replace(
            ".12bit", "..12bit"
        )  # for case ..265.12bit..  for 5.1 channels
        url = url.replace(".x26", "..x26")  # for case dts.x264
        ext = re.search(r"\.\w{2,4}$", url)  # search extension
        ext = ext[0] if ext else ""  # remember extension
        url = re.sub(r"\.\w{2,4}$", ".", url)  # extension out
    except Exception:
        url = str(url)

    type = ""

    if "bluray" in url:
        type += " BLURAY /"
    if "blu-ray" in url:
        type += " BLU-RAY /"
    if ".web-dl" in url:
        type += " WEB-DL /"
    if ".webdl" in url:
        type += " WEB-DL /"
    if ".web." in url:
        type += " WEB /"
    if "dvdrip" in url:
        type += " DVDRip /"
    if "dvd-rip" in url:
        type += " DVD-Rip /"
    if "hdrip" in url:
        type += " HDRip /"
    if "bd-r." in url:
        type += " BD-R /"
    if "bd-rip" in url:
        type += " BD-RIP /"
    if "bd.r." in url:
        type += " BD-R /"
    if "bd.rip" in url:
        type += " BD-RIP /"
    if "bdr." in url:
        type += " BD-R /"
    if "bdrip" in url:
        type += " BDRIP /"
    if any(i in url for i in ["dcprip", "dcp-rip", "dcp.rip"]):
        type += " DCP-Rip /"
    if "hdtv" in url:
        type += " HDTV /"
    if "tvrip" in url:
        type += " TVRip /"
    if any(
        i in url
        for i in [
            "camrip",
            "tsrip",
            "hdcam",
            "hqcam",
            "hdts",
            "hd-ts",
            "dvdcam",
            "dvdts",
            "cam",
            "telesync",
            ".ts",
        ]
    ):
        type += " cam /"
    if any(i in url for i in [".scr.", "scr.", ".screener", "dvdscr", ".r5.", ".r6."]):
        type += " SCR /"
    if ".md" in url:
        type += " MD /"
    if any(
        i in url
        for i in ["custom audio", "custom.audio", "custom-audio", "custom_audio"]
    ):
        type += " custom audio /"
    if any(i in url for i in ["ac3", "ac-3"]):
        if any(i in url for i in ["eac3", "e-ac3", "eac-3", "e-ac-3"]):
            type += " E-AC3 /"
        else:
            type += " AC3 /"
    if ".dd" in url:
        if ".ddp" in url:
            type += " DD+ /"
        else:
            if any(i in url for i in ["dd-ex", "dd.ex"]):
                type += " DD-EX /"
            else:
                type += " DD /"
    if ".dts" in url:
        if any(i in url for i in ["dts-hd", "dts.hd."]):
            if any(i in url for i in ["dts-hd.ma", "dts.hd.ma"]):
                type += " DTS-HD MA /"
            else:
                type += " DTS-HD /"
        elif any(i in url for i in ["dts-es", "dts.es"]):
            type += " DTS-ES /"
        elif any(i in url for i in ["dts-ex", "dts.ex"]):
            type += " DTS-EX /"
        elif any(i in url for i in ["dts-x", "dts.x", "dtsx"]):
            type += " DTS-X /"
        else:
            type += " DTS /"
    if ".truehd" in url:
        type += " TrueHD /"
    if ".lpcm" in url:
        type += " LPCM /"
    if ".aac" in url:
        type += " AAC /"
    if "5.1" in url:
        type += " 5.1 /"
    if "6.1" in url:
        type += " 6.1 /"
    if "7.1" in url:
        type += " 7.1 /"
    if "2.0" in url:
        type += " 2.0 /"
    if "5.0" in url:
        type += " 5.0 /"
    if "1.0" in url:
        type += " 1.0 /"
    if "atmos" in url:
        type += " ATMOS /"
    if "hdr" in url:
        type += " HDR /"
    if ".dv." in url or "dolbyvision" in url or ".dovi." in url:
        type += " DV /"
    if ".imax." in url:
        type += " IMAX /"
    if ".3d." in url:
        type += " 3D /"
    if any(i in url for i in ["subbed", " subs ", " sub "]):
        if type != "":
            type = type.rstrip("/")
            type += "| SUBS |"
        else:
            type = " SUBS |"
    #    if ".multi." in url:
    #        type += " MULTI /"
    #    if ".dual." in url:
    #        type += " DUAL /"
    if ".xvid" in url:
        type += " XVID /"
    if ".h.264" in url:
        type += " H.264 /"
    if ".h.265" in url:
        type += " H.265 /"
    if ".h264" in url:
        type += " H264 /"
    if ".x264" in url:
        type += " x264 /"
    if ".x265" in url:
        type += " x265 /"
    if ".h265" in url:
        type += " h265 /"
    if ".hevc" in url:
        type += " hevc /"
    if ".avc." in url:
        type += " AVC /"
    if ".av1." in url:
        type += " AV1 /"
    if ".vc1." in url or ".vc-1." in url:
        type += " VC1 /"
    if any(i in url for i in ["mpeg2", "mpeg-2"]):
        type += " MPEG-2 /"
    if any(i in url for i in ["mpeg4", "mpeg-4"]):
        type += " MPEG-4 /"
    if any(i in url for i in ["mpeg1", "mpeg-1"]):
        type += " MPEG-1 /"
    if "48fps" in url:
        type += " 48 fps /"
    if "50fps" in url:
        type += " 50 fps /"
    if "60fps" in url:
        type += " 60 fps /"
    if "100fps" in url:
        type += " 100 fps /"
    if "120fps" in url:
        type += " 120 fps /"
    if "extended" in url:
        type += " extended /"
    if "directors.cut" in url:
        type += " directors cut /"
    if "remastered" in url:
        type += " REMASTERED /"
    if "rekonstrukcja" in url:
        type += " Rekonstrukcja cyfrowa /"
    if "remux" in url:
        type += " REMUX /"
    # if ".mp4" in ext:
    # type += " MP4 /"
    if ".avi" in ext:
        type += " AVI /"
    if ".ts" in ext:
        type += " .TS /"
    if "mpg" in ext:
        type += " MPG /"
    type = type.rstrip("/")
    return type


def check_sd_url(release_link):
    try:
        release_link = release_link.lower()
        release_link = re.sub(r"\.\w{2,4}$", "", release_link)  # extension out
        release_link = release_link.replace(" ", ".").replace("_", ".")
        if "2160" in release_link:
            return "4K"
        elif "1440" in release_link:
            return "1440p"
        elif "1080i" in release_link:
            quality = "1080i"
        elif "1080" in release_link:
            quality = "1080p"
        elif "720" in release_link:
            quality = "720p"
        elif ".hd." in release_link:
            quality = "720p"
        elif any(i in release_link for i in ["dvdscr", "r5", "r6"]):
            quality = "SCR"
        elif any(
            i in release_link
            for i in [
                "camrip",
                "tsrip",
                "hdcam",
                "hqcam",
                "hdts",  # czy to zaliczać też?
                "hd-ts",  # czy to zaliczać też?
                "dvdcam",
                "dvdts",
                "cam",
                "telesync",
                ".ts",
            ]
        ):
            quality = "CAM"
        else:
            quality = "SD"
        return quality
    except Exception:
        return "SD"


def label_to_quality(label):
    try:
        try:
            label = int(re.search(r"(\d+)", label).group(1))
        except Exception:
            label = 0

        if label >= 2160:
            return "4K"
        elif label >= 1440:
            return "1440p"
        elif label >= 1080:
            return "1080p"
        elif 720 <= label < 1080:
            return "720p"
        elif label < 720:
            return "SD"
    except Exception:
        return "SD"


def strip_domain(url):  # ok
    try:
        if url.lower().startswith("http") or url.startswith("/"):
            url = re.findall("(?://.+?|)(/.+)", url)[0]
        url = client.replaceHTMLCodes(url)
        url = url.encode("utf-8")
        return url
    except Exception:
        log_exception()


def is_host_valid(url, domains):  # ok
    try:
        host = __top_domain(url)
        hosts = [
            domain.lower() for domain in domains if host and host in domain.lower()
        ]

        if hosts and "." not in host:
            host = hosts[0]
        if hosts and any([h for h in ["google", "picasa", "blogspot"] if h in host]):
            host = "gvideo"
        if hosts and any([h for h in ["akamaized", "ocloud"] if h in host]):
            host = "CDN"
        return any(hosts), host
    except Exception:
        log_exception()
        return False, ""


def __top_domain(url):  # ok
    elements = urlparse(url)
    domain = elements.netloc or elements.path
    domain = domain.split("@")[-1].split(":")[0]
    regex = r"(?:www\.)?([\w\-]*\.[\w\-]{2,3}(?:\.[\w\-]{2,3})?)$"
    res = re.search(regex, domain)
    if res:
        domain = res.group(1)
    domain = domain.lower()
    return domain


def aliases_to_array(aliases, filter=None):  # ok
    try:
        if not filter:
            filter = []
        if isinstance(filter, str):
            filter = [filter]

        return [
            x.get("title") for x in aliases if not filter or x.get("country") in filter
        ]
    except Exception:
        log_exception()
        return []


def append_headers(headers):  # ok
    return "|%s" % "&".join(
        ["%s=%s" % (key, quote_plus(headers[key])) for key in headers]
    )


def get_size_url(url):
    try:
        size = client.request(url, output="file_size")
        if size == "0":
            size = False
        size = convert_size(size)
        return size
    except Exception:
        log_exception()
        return False


def convert_size(size_bytes: Optional[int]) -> str:
    import math

    if size_bytes is None:
        return ''
    if size_bytes == 0:
        return '0 B'
    units = ('B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB')
    exp = int(math.log(size_bytes, 1024))
    val: float = size_bytes / 1024 ** exp
    if val < 10:
        val = round(val, 2)
    elif val < 100:
        val = round(val, 1)
    else:
        val = int(val)
    return f'{val} {units[exp]}'


def check_directstreams(url, hoster="", quality="SD"):
    urls = []
    host = hoster

    if "google" in url or any(x in url for x in ["youtube.", "docid="]):
        urls = directstream.google(url)
        if not urls:
            tag = directstream.googletag(url)
            if tag:
                urls = [{"quality": tag[0]["quality"], "url": url}]
        if urls:
            host = "gvideo"
    elif "ok.ru" in url:
        urls = directstream.odnoklassniki(url)
        if urls:
            host = "vk"
    elif "vk.com" in url:
        urls = directstream.vk(url)
        if urls:
            host = "vk"
    elif any(x in url for x in ["akamaized", "blogspot", "ocloud.stream"]):
        urls = [{"url": url}]
        if urls:
            host = "CDN"

    direct = True if urls else False

    if not urls:
        urls = [{"quality": quality, "url": url}]

    return urls, host, direct


def get_lang_by_type(text):
    text = text.lower()
    text = re.sub(r"[\][._-]", " ", text)
    text = f" {text} "  # dla jednowyrazowców, jak w ekino
    if any(
        x in text
        for x in [" dubbing", "pldub", "pl dub", " dub "]
    ):
        if any(x in text for x in ["kino", "md"]):
            return "pl", "Dubbing Kino"
        return "pl", "Dubbing"
    elif "lektor pl" in text or "lektor" in text:
        return "pl", "Lektor"
    elif any(
        x in text for x in ["plsub", "napisy pl", "napisy", "nap pl"]
    ):
        return "pl", "Napisy"
    elif any(
        x in text
        for x in ["polski", "polish", " pl ", "pl ", " pol "]
    ):
        return "pl", ""
    # na podstawie obecności polskich znaków diakrytycznych
    if re.search(r"[ąęółśżźćń]", text, flags=re.I):
        return "pl", ""
    elif any(
        x in text for x in ["subbed", " subs ", " sub "]
    ):
        return "", "Napisy"
    # elif ".dual." in text:  # przenioslem wykrywanie do patterns.py
    # return "en", "dual"  # bo nie ma pewnosci, że jest pl
    elif any(
        x in text for x in [" multi ", " mul "]
    ):
        # return "en", "multi"  # bo nie ma pewnosci, że jest pl
        return "multi", ""  # a może tak?
    # return "en", ""
    # return "-", ""
    return "", ""


def convert_size_to_bytes(size: Union[str, int]) -> int:
    if isinstance(size, int):
        return size
    suffixes = ("", "k", "m", "g", "t")
    multipliers = {"{}b".format(l): 1024**i for i, l in enumerate(suffixes)}
    sre = re.compile(
        r"(\d+(?:[.,]\d+)?)\s?({})".format("|".join(x + "b" for x in suffixes)),
        re.IGNORECASE,
    )

    def subfunc(m):
        return str(
            float(m.group(1).replace(",", ".")) * multipliers[m.group(2).lower()]
        )

    bytes = sre.sub(subfunc, size)

    try:
        return int(float(bytes))
    except ValueError:
        return 0


def n2w(n):
    num2words = {
        0: "zero",
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
        9: "nine",
        10: "ten",
        11: "eleven",
        12: "twelve",
        13: "thirteen",
        14: "fourteen",
        15: "fifteen",
        16: "sixteen",
        17: "seventeen",
        18: "eighteen",
        19: "nineteen",
        20: "twenty",
        30: "thirty",
        40: "forty",
        50: "fifty",
        60: "sixty",
        70: "seventy",
        80: "eighty",
        90: "ninety",
    }
    n = int(n)
    try:
        return num2words[n]
    except KeyError:
        try:
            return f"{num2words[n - n % 10]} {num2words[n % 10].lower()}"
        except KeyError:
            return n


# print( re.sub(r'\b\d{1,2}\b', lambda n: n2w(n.group()) , filename) )


def numbers_in_pattern(pat, mode=0, prefix=""):
    numbers = (
        "zero",
        "one|jeden|i",
        "two|dwa|ii",
        "three|trzy|iii",
        "four|cztery|iv",
        "five|pięć|v",
        "six|sześć|vi",
        "seven|siedem|vii",
        "eight|osiem|viii",
        "nine|dziewięć|ix",
    )
    if mode != 2:
        pat = re.sub(
            r"(?<!\|)\b\d\b(?!\|)",
            lambda x: f"({prefix}{x.group()}|{numbers[int(x.group())-0]})",
            pat,
        )  # cyfry na słowa
    if mode != 1:
        pat = re.sub(
            r"(?<!\|)\b(\w{3,8}|[iIvVxX]{1,2})\b(?!\|)",
            lambda x: f"({prefix}{x.group()}|{[x.group().lower() in n.split('|') for n in numbers].index(True)+0})"
            if any(x.group().lower() in n.split('|') for n in numbers)
            else x.group(),
            pat,
        )  # słowa na cyfry
    return pat


def diakr_for_pat(L="", mode=0, prefix="[", postfix="]"):
    def _diakr(L):
        DIAKRYT = {
            "ą": "a",
            "ć": "c",
            "ę": "e",
            "ł": "l",
            "ń": "n",
            "ó": "o",
            "ś": "s",
            "ż": "z",
            "ź": "z",
        }
        DIAKRYT_rev = {DIAKRYT[d]: d for d in DIAKRYT}
        DIAKRYT_rev["z"] = "żź"  # korekta
        # if type(L) is not str:
        if isinstance(L, re.Match):
            L = L.group()
        l = L.lower()
        if l in DIAKRYT and mode != 2:
            return f"{prefix}{l}{DIAKRYT[l]}{postfix}" # ą -> [ąa]
        elif l in DIAKRYT_rev and mode != 1:
            return f"{prefix}{l}{DIAKRYT_rev[l]}{postfix}" # a -> [aą]
        else:
            return L

    if L:
        return _diakr(L)
    else:
        return _diakr


def diacritics_in_pattern(string, qm_in_out=True, dictio=None, mode=0, prefix="[", postfix="]"):
    most = (
        "the",
        "part",
        "movie",
        "film",
        "episode",
        "jeden",
        "dwa",
        "cztery",
        "siedem",
        "osiem",
    )
    numbers = (
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
        "thirty",
        "forty",
        "fifty",
        "sixty",
        "seventy",
        "eighty",
        "ninety",
    )
    if dictio is None:
        dictio = []
    dictio += numbers + most

    def _replace_diakryt1(string):
        pat = r"([lłżź]|\B[aąeę]|[oó]\B|(?<![cs])[cćsś](?![zis])|(?<![csr])z|\B[nń](?!i))"
        if qm_in_out:
            return re.sub(
                rf"(?<!\[){pat}(?![?\]])",
                lambda l: diakr_for_pat(l.group(), mode, prefix, postfix="?"+postfix),
                string,
            )  # a -> [aą?]  lub  ą -> [ąa?]
        else:
            return re.sub(
                rf"(?<!\[){pat}(?!\])", diakr_for_pat("", mode, prefix, postfix), string
            )  # a -> [aą]  lub  ą -> [ąa]

    def _check_if_replace_diakryt(word):
        if word.lower() not in dictio:
            return _replace_diakryt1(word)
        else:
            return word

    return re.sub(
        r"(?<!\[)(?:(?![\d_])\w)+", lambda w: _check_if_replace_diakryt(w.group()), string
    )


def normalize_unicode_in_pattern(pattern, prefix="[", postfix="]", qm="?"):
    t1 = pattern
    t2 = cleantitle.normalize(t1)
    if t1 != t2:
        if len(t1) == len(t2):
            t3 = ""
            for i, t in enumerate(t1):
                t3 += f"{prefix}{t}{t2[i]}{qm}{postfix}" if t != t2[i] else t
            t2 = t3.replace(prefix+prefix, prefix).replace(postfix+postfix, postfix)
            # dodatkowe czyszczenia
            # pr = re.escape(prefix)
            # po = re.escape(postfix)
            # t2 = re.sub(rf"(?<={pr})(\w*(?:{pr})?\w+{po}[\w\?]*)?(?={po})", lambda x: x.group().replace(prefix,"").replace(postfix,""), t2)
            # t2 = re.sub(fr"(?<={pr})(\w)(\w)(\2|\1)(?=\??{po})", r"\1\2", t2)
    return t2


def months_to_miesiace(text, short=0):
    months = {
        "monday": ["poniedziałek", "pon"],
        "tuesday": ["wtorek", "wt"],
        "wednesday": ["środa", "śr"],
        "thursday": ["czwartek", "czw"],
        "friday": ["piątek", "pt"],
        "saturday": ["sobota", "sob"],
        "sunday": ["niedziela", "ndz"],
    }
    months3 = {k[:3]: v for k, v in months.items()}
    return re.sub(
        r"[a-z]+",
        lambda w: months[w.group().lower()][short]
        if w.group().lower() in months
        else months3[w.group().lower()[:3]][1]
        if w.group().lower()[:3] in months3
        else w.group(),
        text,
        flags=re.I,
    )


def arabskie_na_rzymskie(liczba):
    liczby_arab_rzym = [(1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')]
    rzymska = ''
    while liczba > 0:
        for i, r in liczby_arab_rzym:
            while liczba >= i:
                rzymska += r
                liczba -= i
    return rzymska


# def get_trakt_id_from_tmdb(tmdb_id):
#     result = trakt.getTraktAsJson(f"/search/tmdb/{tmdb_id}?type=show")
#     if result:
#         return result[0]["show"]["ids"]["trakt"]
#     return None


# def get_absolute_number_trakt(tmdb, episode, season):
#     trakt_show_id = get_trakt_id_from_tmdb(tmdb)
#     if not trakt_show_id:
#         return None

#     seasons = trakt.getTraktAsJson(f"/shows/{trakt_show_id}/seasons")
#     if not seasons:
#         return None

#     # Convert to integers if they are strings
#     season = int(season)
#     episode = int(episode)

#     absolute_number = 0

#     for season_data in seasons:
#         if season_data["number"] < season:
#             absolute_number += season_data["aired_episodes"]
#         elif season_data["number"] == season:
#             absolute_number += episode
#             break

#     return absolute_number


def get_absolute_number_tmdb(tmdb_id, target_season, target_episode):
    # TODO: Use ffinfo
    response = requests.get(
        f"{TMDB_API_URL}/tv/{tmdb_id}", params={"api_key": TMDB_API_KEY}
    )
    data = response.json()

    # Convert to integers if they are strings
    target_season = int(target_season)
    target_episode = int(target_episode)

    absolute_number = 0

    for season in data["seasons"]:
        if season["season_number"] == 0:
            continue
        if season["season_number"] < target_season:
            absolute_number += season["episode_count"]
        elif season["season_number"] == target_season:
            absolute_number += target_episode
            break

    total_episodes = 0

    for season in data["seasons"]:
        if season["season_number"] == 0:  # Pomiń odcinki specjalne
            continue
        total_episodes += season["episode_count"]

    return total_episodes, absolute_number


def czy_litery_krzaczki(s, mode=0):
    from unicodedata import category

    def _czy_krzaczek(c):
        v = ord(c or ' ')
        # print(c, hex(v), v, (category(c)))  # debug
        if not (c and category(c)[0] == 'L'):  # if not a letter
            return ""
        if 0x20 <= v < 0x370:
            return False
        if 0x370 <= v <= 0x3ff:
            return 'gr'
        if 0x400 <= v <= 0x52f:
            return "rus"
        return True

    s = s.strip()
    if not len(s):
        return None

    if mode == 0:  # whole text (only letters)
        r = [_czy_krzaczek(l) for l in s if category(l)[0] == 'L']
    elif mode == 2:
        r = [_czy_krzaczek(s[i]) for i in [0, -1]]  # first and last letter
    if r.count("gr"):
        return "gr"
    if r.count("rus"):
        return "rus"
    return any(r)


def absoluteNumber(tvdb: int, episode: int, season: int) -> int:
    """Convert episode / number into absolute (continaous) episode number."""
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    tvdbapi = requests.post('https://api.thetvdb.com/login', headers=headers, data={
        'apikey': apis.tvdb_API,
        'userkey': '',
        'username': '',
    }).json()
    if 'token' in tvdbapi:
        tvdbapi = tvdbapi['token']
        headers = {'Authorization': 'Bearer ' + tvdbapi, 'Accept': 'application/json'}
        data = requests.get(f'https://api.thetvdb.com/series/{tvdb}/episodes/query?airedSeason={season}&airedEpisode={episode}', headers=headers).json()
        # fflog(f'{data=}')
        if 'data' in data:
            return data['data'][0]['absoluteNumber']
    return int(episode)
    # fflog('Error occured - no key "token" in response for https://api.thetvdb.com/login - check ApiKey, UserKey, Username in addon settings')


# można będzie dopisywać frazy, które mogą być pomijane przy szukaniu
antifalse_filter_exceptions = [
    "The TV Series",
]


def extract_cookie(cookie: str, cookie_name: str) -> str:
    """Get cookie value from string."""
    import json
    # replace all cookies to wanted one
    cookie_re = re.escape(cookie_name)
    cookie = re.sub(rf'^.*\b{cookie_re}=([^;]*)(?:;.*|$)', r'\1', cookie)
    # JSON, used by Copy Cookies web extension
    if re.search(rf'"name"\s*:\s*"{cookie_re}"', cookie):
        try:
            for cookies in json.loads(cookie):
                if cookies.get('name') == cookie_name:
                    return cookies.get('value', '')
        except json.JSONDecodeError:
            pass
        return ''
    return cookie.strip(' "\'')


def setting_cookie(setting_name: str, cookie_name: str) -> str:
    """Get cookie value from settings."""
    val = settings.getString(setting_name)
    return extract_cookie(val, cookie_name)
