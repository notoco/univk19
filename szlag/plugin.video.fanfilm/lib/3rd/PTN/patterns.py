#!/usr/bin/env python
# -*- coding: utf-8 -*-

patterns = [
    (
        "season",
        r"[\. ]((?:Complete.)?s[0-9]{2}-s[0-9]{2}|"
        "s([0-9]{1,2})(?:e[0-9]{2})?|"
        r"([0-9]{1,2})x[0-9]{2})(?:[\. ]|$)",
    ),

    ("episode", "((?:[ex]|ep)([0-9]{2})(?:[^0-9]|$))"),
    ("year", r"([\[\(]?((?:19[0-9]|20[0-9])[0-9])[\]\)]?)"),
    ("resolution", "([0-9]{3,4}[pi]|1280x720)"),

    (
        "quality",
        (
            r"((?:PPV\.)?[HP]DTV|(?:PPV|VOD)(?:Rip)?|(?:HD|HQ)?CAM|CamRip|(?<!D)(?:HD[.-]?)?TS|tsrip|"
            "(?:PPV )?WEB[ .-]?(?:DL)?(?: DVDRip)?|HDRip|(?:HD)?TVRip|(?:HD|HQ)?DV[DB][.-]?Rip|DCP[.-]?Rip|"
            "WE?B[ .-]?Rip|Blu[.-]?Ray|B[DR]?[.-]?(?:Rip|Remux|R|D)|DvDScr|hdtv|telesync|telecine|screener|scr|R5)"
        ),
    ),

    ("codec", r"(mpeg-?[124]?|xvid|[hx]\.?26[45]|hevc|avc|(?:av|vc-?)1|HDR(?:10)?(?:plus|\+)?|Dolby[ .]?Vision|DoVi|DV(?!d)|\d{2,3}fps)"),

    ("audio",
        r"((?:WMA|FLAC|L?PCM|DDP?A?(?:[.-]?EX|\+)?|DTS(?:[.-]?(?:HD|ES|EX|X(?!26))(?:[. ]?MA)?)?|E?-?AC-?3|(?:HE-)?AAC(?:[ .-]LC|v2)?|TRUE[ .-]?HD(?:[ .]atmos)?|atmos)(?:[ .-]?[572461]\.[102])?(?:(?:\.[24])?[ .]atmos)?"
        r"|MD|MP3|Dual[ -]Audio|LiNE|(?:custom|dual)[. ]audio|dual|\dCH)"
    ),

    ("group", "(- ?([^-]+(?:-={[^-]+-?$)?))$"),
    ("region", "R[0-9]"),
    ("extended", "(EXTENDED(?=.CUT)?|(?:directors|alternat(?:iv)?e)(?:.CUT))"),
    ("remastered", "(REMASTERED|Rekonstrukcja(?:[. ]cyfrowa)?)"),
    ("hardcoded", "HC"),
    ("proper", "PROPER"),
    ("repack", "REPACK"),
    ("container", r"(?<=\.)\w{2,4}$"),  # the extension can be from 2 to 4 characters
    ("widescreen", "WS"),
    ("website", r"^(\[ ?([^\]]+?) ?\])"),
    ("language", r"(rus\.eng|ita\.eng|nordic|eng?|po?l|mul(?:ti)?|ita?|esp?|fra?|de|rus?)"),
    ("subtitles", "((?:DK|EN|PL)?(?:subs?|subbed|napisy))"),
    ("sbs", "(?:Half-)?SBS"),
    ("unrated", "UNRATED"),
    ("size", r"(\d+(?:\.\d+)?(?:GB|MB))"),
    ("3d", "3D"),
    ("imax", "IMAX"),
]

types = {
    "season": "integer",
    "episode": "integer",
    "year": "integer",
    #"extended": "boolean",
    #"remastered": "boolean",
    "hardcoded": "boolean",
    "proper": "boolean",
    "repack": "boolean",
    "widescreen": "boolean",
    "unrated": "boolean",
    "3d": "boolean",
    "imax": "boolean",
}

bt_sites = ["eztv", "ettv", "rarbg", "rartv", "ETRG"]
