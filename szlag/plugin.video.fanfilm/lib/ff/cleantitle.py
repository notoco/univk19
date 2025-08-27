# -*- coding: utf-8 -*-

"""
    Fanfilm Add-on

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

import re
from typing import TypeVar
import unicodedata

from lib.ff.utils import convert

StrOnNone = TypeVar('StrOnNone', str, None)


def get(title):
    if title is None:
        return

    title = re.sub(r"&#(\d+);", "", title)
    title = re.sub(r"(&#[0-9]+)([^;^0-9]+)", "\\1;\\2", title)
    title = (
        title.replace(r"&quot;", '"')
        .replace(r"&amp;", "&")
        .replace(r"–", "-")
        .replace(r"!", "")
    )
    title = re.sub(
        r'\n|([\[].+?[\]])|([\(].+?[\)])|\s(vs|v[.])\s|(:|;|-|–|"|,|\'|\_|\.|\?)|\s',
        "",
        title,
    ).lower()
    return title


def get_title(title):
    if title is None:
        return
    from urllib.parse import unquote

    title = unquote(title)
    title = re.sub("[^A-Za-z0-9 ]+", " ", title)
    title = re.sub(" {2,}", " ", title)
    title = title.strip().lower()
    return title


def geturl(title):
    if title is None:
        return
    title = title.lower()
    title = title.translate(str.maketrans("", "", ":*?\"'\\.<>|&!,#=%;"))
    title = title.replace("/", "-")
    title = title.replace(" ", "-")
    title = title.replace("–", "-")
    title = title.replace("---", "-")

    return title


def get_simple(title):
    if title is None:
        return
    title = title.lower()
    title = re.sub(r"(\d{4})", "", title)
    title = re.sub(r"&#(\d+);", "", title)
    title = re.sub("(&#[0-9]+)([^;^0-9]+)", "\\1;\\2", title)
    title = title.replace("&quot;", '"').replace("&amp;", "&")
    title = re.sub(r"\n|\(|\)|\[|\]|\{|\}|\s(vs|v[.])\s|(:|;|-|–|\"|,|'|\_|\.|\?)|\s", "", title).lower()
    return title


def getsearch(title, preserve=""):
    if title is None:
        return
    title = title.lower()
    title = re.sub(r"&#(\d+);", "", title)
    title = re.sub("(&#[0-9]+)([^;^0-9]+)", "\\1;\\2", title)
    title = title.replace("&quot;", '"').replace("&amp;", "&")
    title = re.sub(r"\\|!|\[|\]|–|;|,|\*|\?|\"|'|<|>|\|", " ", title).lower()
    title = title.replace("'", "") if "'" not in preserve else title  # film "Mr. Holland's Opus"
    title = title.replace(":", " ") if ":" not in preserve else title
    # title = title.replace(".", " ")  # psuje wyszukiwanie filmu "E.T."
    title = title.replace("-", " ") if "-" not in preserve else title
    title = title.replace("⁄", "/") if "⁄" not in preserve else title  # ułamki mogą być tak zapisywane
    title = title.replace("/", " ") if "/" not in preserve else title  # ułamki mogą być tak zapisywane
    title = title.replace("   ", " ")
    title = title.replace("  ", " ")
    title = title.strip()
    return title


def query(title: StrOnNone) -> StrOnNone:
    if title is None:
        return
    title = (
        title.replace("'", "").rsplit(":", 1)[0].rsplit(" -", 1)[0].replace("-", " ")
    )
    return title


def clean_from_unicategories(title, cat="Mn"):
    # https://pypi.org/project/unicategories
    return str(
        "".join(
            c
            for c in title
            if unicodedata.category(c) not in cat
        )
    )


def normalize(title):
    try:
        return str(
            "".join(
                c
                for c in unicodedata.normalize("NFKD", convert(title))
                if unicodedata.category(c) != "Mn"
            )
        ).replace("ł", "l")
    except Exception:
        title = (
            convert(title)
            .replace("ą", "a")
            .replace("ę", "e")
            .replace("ć", "c")
            .replace("ź", "z")
            .replace("ż", "z")
            .replace("ó", "o")
            .replace("ł", "l")
            .replace("ń", "n")
            .replace("ś", "s")
        )
        return title


def clean_search_query(url):
    url = url.replace("-", "+")
    url = url.replace(" ", "+")
    return url


def scene_title(title, year):
    title = normalize(title)
    try:
        title = title
    except Exception:
        pass
    title = (
        title.replace("&", "and")
        .replace("-", " ")
        .replace("–", " ")
        .replace("/", " ")
        .replace("*", " ")
        .replace(".", " ")
    )
    title = re.sub("[^A-Za-z0-9 ]+", "", title)
    title = re.sub(" {2,}", " ", title).strip()
    if title.startswith("Birdman or") and year == "2014":
        title = "Birdman"
    if (
        title == "Birds of Prey and the Fantabulous Emancipation of One Harley Quinn"
        and year == "2020"
    ):
        title = "Birds of Prey"
    if title == "Roald Dahls The Witches" and year == "2020":
        title = "The Witches"
    return title, year


def scene_tvtitle(title, year, season, episode):
    # Normalizacja i czyszczenie tytułu
    title = re.sub("[^A-Za-z0-9 ]+", "", title)
    title = re.sub(" {2,}", " ", title).strip()

    # Zamiana znaków specjalnych na czytelne formaty
    replacements = {
        "&": "and",
        "-": " ",
        "–": " ",
        "/": " ",
        "*": " ",
        ".": " "
    }
    for key, value in replacements.items():
        title = title.replace(key, value)

    # Obsługa specjalnych przypadków dla tytułów i sezonów
    if title in ["The Haunting", "The Haunting of Bly Manor", "The Haunting of Hill House"] and year == "2018":
        if season == "1":
            title = "The Haunting of Hill House"
        elif season == "2":
            title, year, season = "The Haunting of Bly Manor", "2020", "1"

    if title in ["Cosmos", "Cosmos A Spacetime Odyssey", "Cosmos Possible Worlds"] and year == "2014":
        if season == "1":
            title = "Cosmos A Spacetime Odyssey"
        elif season == "2":
            title, year, season = "Cosmos Possible Worlds", "2020", "1"

    if "Special Victims Unit" in title:
        title = title.replace("Special Victims Unit", "SVU")

    if title == "Cobra Kai" and year == "1984":
        year = "2018"

    if title == "The End of the F ing World":
        title = "The End of the Fucking World"

    if title == "M A S H":
        title = "MASH"

    if title == "Lupin" and year == "2021":
        if season == "1" and int(episode) > 5:
            season, episode = "2", str(int(episode) - 5)

    return title, year, season, episode
