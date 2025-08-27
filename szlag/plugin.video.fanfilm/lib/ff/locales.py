"""Simple locale tools."""

from pathlib import Path
import json
from typing import Optional, Dict
import requests
from const import const

import xbmc
import xbmcaddon
import xbmcvfs

from ..kolang import kodi_locale
from .log_utils import fflog_exc, fflog

#: Base URL for languages translate.
LANG_URL = 'https://raw.githubusercontent.com/umpirsky/locale-list/master/data/{lang}/locales.json'
# 'https://raw.githubusercontent.com/umpirsky/language-list/master/data/{lang}/language.json'
# 'https://raw.githubusercontent.com/ihmpavel/all-iso-language-codes/master/data/{lang}/639-1.json'
#: Base URL for countries translate.
COUNTRY_URL = 'https://raw.githubusercontent.com/umpirsky/country-list/master/data/{lang}/country.json'
# 'https://raw.githubusercontent.com/stefangabos/world_countries/master/data/countries/{lang}/world.json'
# 'https://raw.githubusercontent.com/stefangabos/world_countries/master/data/countries/{lang}/countries.json

# -- for stefangabos/world_countries
# jdata = requests.get(COUNTRY_URL.format(lang=lang), timeout=5).json()
# trans = {e['alpha2'].upper(): e['name'] for e in jdata}


TranslationTable = Dict[str, Dict[str, str]]

#: Already readed language translations to speed up.
_all_lang_translations: TranslationTable = {}

#: Already readed country translations to speed up.
_all_country_translations: TranslationTable = {}

#: Path to cached locale files.
locale_path = Path(xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo('profile'))) / 'locale'


def _translations(table: TranslationTable, fname: str, url: str, *, lang: Optional[str] = None) -> Dict[str, str]:
    """Return translatrions dict [lang]=name for given lang. Use kodi locale if None."""

    def save(path: Path) -> None:
        tmp_path = path.with_suffix('.new.json')
        try:
            tmp_path.write_text(json.dumps(trans, indent=2))
        except IOError:
            fflog_exc()
        else:
            try:
                tmp_path.replace(path)
            except IOError:
                fflog_exc()

    if not lang:
        lang = kodi_locale()
    lang, _, lngcountry = lang.replace('-', '_').partition('_')
    lang = lang.lower()
    if lngcountry:
        locales = [f'{lang}_{lngcountry.upper()}', lang]
    else:
        locales = [lang]
    trans = None
    path = None
    loc = ''
    for loc in locales:
        trans = table.get(loc)
        if trans is None:
            path = locale_path / loc / fname
            path.parent.mkdir(parents=True, exist_ok=True)
            trans = {}
            downlaoded = False
            try:
                if path.exists() and (data := path.read_text()):
                    trans = json.loads(data)
                else:
                    fflog(f'Download countries for locale {loc}')
                    trans = requests.get(url.format(lang=loc), timeout=5).json()
                    downlaoded = True
            except requests.JSONDecodeError:
                pass
            else:
                table[loc] = trans
                if downlaoded:
                    save(path)
                break
    if not trans:
        fflog.warning(f'No country name for locale {locales[0]!r}')
        table[loc] = {}
    return trans or {}


def language_translations(lang: Optional[str] = None) -> Dict[str, str]:
    """Return language translatrions dict [lang]=name for given lang. Use kodi locale if None."""
    return _translations(_all_lang_translations, 'languages.json', LANG_URL, lang=lang)


def country_translations(lang: Optional[str] = None) -> Dict[str, str]:
    """Return language translatrions dict [lang]=name for given lang. Use kodi locale if None."""
    return _translations(_all_country_translations, 'countries.json', COUNTRY_URL, lang=lang)


if __name__ == '__main__':
    from .cmdline import DebugArgumentParser
    p = DebugArgumentParser()
    p.add_argument('code', help='lang (pl) or country (PL) code')
    p.add_argument('-L', '--lang', help='local language (pl_PL)')
    p.add_argument('-t', '--type', choices=('lang', 'country'), help='code type')
    a = p.parse_args()

    if not a.type:
        if a.code.islower():
            a.type = 'lang'
        elif a.code.isupper():
            a.type = 'country'
    if a.type == 'lang':
        print(f'Language {a.code!r}: {language_translations(lang=a.lang).get(a.code.lower())!r}')
    elif a.type == 'country':
        print(f'Country {a.code!r}: {country_translations(lang=a.lang).get(a.code.upper())!r}')
