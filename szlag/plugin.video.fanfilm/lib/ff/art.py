
from enum import Enum
from typing import Optional, Dict, Tuple, Sequence, Iterator, NamedTuple
from .types import JsonData
from attrs import frozen

from ..defs import MediaRef
from .settings import settings
from const import const


class ArtLang(Enum):
    NO = 0
    YES = 1
    FANART = 2
    EMPTY = 3


class ArtSortByKey(NamedTuple):
    """Sort images by key SettingsEnum. Must match to setting `image.sort_by`."""

    vote_average: Sequence[str]
    vote_count: Sequence[str]


class ArtQuality(NamedTuple):
    """An image quality SettingsEnum. Must match to setting `image.quality`."""

    low: str
    high: str
    best: str


@frozen
class ArtName:
    key: str
    quality: ArtQuality


@frozen
class ArtDef:
    lang_type: ArtLang
    sources: Sequence[ArtName]

    def langs(self, *, yes: Sequence[Optional[str]], no: Sequence[Optional[str]] = (None,), skip_fanart: bool = False) -> Sequence[Optional[str]]:
        """Get list of languages for this art definition."""
        if self.lang_type is ArtLang.NO:
            return no
        if self.lang_type is ArtLang.YES:
            return yes
        if self.lang_type is ArtLang.FANART:
            return [] if skip_fanart else no
        # ArtLang.EMPTY
        return []


@frozen(kw_only=True)
class ArtSettings:
    """Cache for settings for TMDB."""
    lang: str
    quality: int
    sort_by: int


class Art:

    def __init__(self) -> None:
        #: Setting cache.
        self._settings: Optional[ArtSettings] = None

    def reset(self) -> None:
        """Reset settings."""
        self._settings = None

    @property
    def settings(self, lang: Optional[str] = None) -> ArtSettings:
        """Get settings."""
        if self._settings is None:
            from .control import apiLanguage
            self._settings = ArtSettings(
                lang=apiLanguage().get('tmdb', 'pl-PL'),
                quality=settings.getInt('image.quality'),
                sort_by=settings.getInt('image.sort_by'),
            )
        return self._settings

    @settings.deleter
    def settings(self) -> None:
        self._settings = None

    def parse_art(self, *,
                  images: Optional[JsonData] = None,
                  item: Optional[JsonData] = None,
                  translate_order: Optional[Sequence[str]],
                  ref: Optional[MediaRef] = None,
                  ) -> Dict[str, str]:
        """Parse TMDB images and retrun kodi art dict."""

        def img_sort_key(im: JsonData):
            return tuple(-float(im[key]) for key in sort_by)

        # def filter_images(img_list: Sequence[JsonData]) -> Iterator[JsonData]:
        #     for ielem in img_list:
        #         if ielem.get('iso_639_1') == lng and ielem['file_path']:
        #             yield ielem

        is_episode = bool(ref and ref.is_episode)
        if images is None:
            if item is None:
                return {}
            images = item.get('images') or {}
        if translate_order is None:
            translate_order = (self.settings.lang, 'en')
        art_langs = (*dict.fromkeys(loc.partition('-')[0] for loc in translate_order), *(None,))
        no_langs = TmbdArtService.no_langs
        sort_by = TmbdArtService.sort_by[self.settings.sort_by]
        quality = self.settings.quality
        art: Dict[str, str] = {}
        image_url = 'https://image.tmdb.org/t/p/{width}{path}'
        lang_key = TmbdArtService.lang_key
        for aname, artdef in TmbdArtService.art_names.items():
            for src in artdef.sources:
                width = src.quality[quality]
                ilist = images.get(src.key)
                if ilist:
                    ilist = [item for item in ilist if not item['file_path'].endswith('.svg')]
                    # Przeglądając **po kolei** języki sortujemy po głosowaniu i wielkości (o ile klucze podane).
                    # reversed() daje nam ostatni z pasujących obrazów (oczywiście wśród `sort_by`), bo liczymy, że ten będzie lepszy.
                    best = [img for lang in artdef.langs(yes=art_langs, no=no_langs, skip_fanart=is_episode)
                            for img in sorted((im for im in reversed(ilist) if im[lang_key] == lang), key=img_sort_key)]
                    if best:
                        im = best[0]
                        art[aname] = image_url.format(width=width, path=im['file_path'])
                        break
        # see issue #132 (fake thumb)
        if const.indexer.art.fake_thumb and 'thumb' not in art:
            if img := art.get('landscape' if is_episode else 'poster'):
                art['thumb'] = img
        if item and 'poster' not in art and (poster := item.get('poster_path')):
            art['poster'] = image_url.format(width='w780', path=poster)
        if item and (backdrop := item.get('backdrop_path')):
            backdrop = image_url.format(width='w1280', path=backdrop)
            art.setdefault('fanart', backdrop)
            art.setdefault('landscape', backdrop)
        return art


class ArtService:
    pass


class TmbdArtService(ArtService):
    """The Movie Database service."""

    # Opisy zmiennych są w ArtService

    movies_url = "https://api.themoviedb.org/3/movie/{media_id}/images?api_key={tm_user}"
    tvshows_url = "https://api.themoviedb.org/3/tv/{media_id}/images?api_key={tm_user}"
    image_url: str = "https://image.tmdb.org/t/p/{quality}{path}"

    lang_key = 'iso_639_1'
    no_langs = ('00', 'xx', None)
    sort_by = ArtSortByKey(['vote_average'], ['vote_count'])
    art_names = {
        'fanart':    ArtDef(ArtLang.FANART, (  # no-lang
            ArtName('backdrops', ArtQuality('w780', 'w1280', 'w1280')),
            ArtName('stills', ArtQuality('w780', 'w1280', 'w1280')),
        )),
        'landscape': ArtDef(ArtLang.YES, (
            ArtName('backdrops', ArtQuality('w780', 'w1280', 'original')),
            ArtName('stills', ArtQuality('w780', 'w1280', 'original')),
        )),
        'poster':    ArtDef(ArtLang.YES, (
            ArtName('posters', ArtQuality('w500', 'w780', 'w780')),
        )),
        'clearlogo': ArtDef(ArtLang.YES, (
            ArtName('logos', ArtQuality('w500', 'w780', 'original')),
        )),
    }
