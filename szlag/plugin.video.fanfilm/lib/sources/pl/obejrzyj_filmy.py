"""
    FanFilm Add-on
    Copyright (C) 2025 :)

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    See MIT License, see <https://mit-license.org>.
"""


from __future__ import annotations
from typing import Optional, Union, Sequence, Iterator, ClassVar, List, Dict, TYPE_CHECKING
from typing_extensions import Literal
from urllib.parse import urlparse
import re
# import json
from base64 import b64encode
from lib.ff import requests
from lib.ff.log_utils import fflog, fflog_exc
from lib.sources import Provider
if TYPE_CHECKING:
    from lib.ff.item import FFItem
    from lib.ff.types import JsonData
    from lib.ff.sources import SourceItem
    from lib.sources import SourceModule

R = re.compile


class _source(Provider):
    """Base scraper for sites like obejrzyj.to, filmyonline.cc, etc."""

    # --- scraper api ---
    priority: ClassVar[int] = 1
    language: ClassVar[Sequence[str]] = ['pl']

    # --- internal ---
    PROVIDER: ClassVar[str]
    URL: ClassVar[str]

    # what info get from video name
    INFO_HIT: ClassVar[Dict[Union[str, re.Pattern[str]], str]] = {
        # cam video: remove, sources.py add it itself
        R(r'\b(cam\d*|camrip|tsrip|hdcam|hqcam|dvdcam|dvdts|telesync)\b'): '',
        # audio type
        'lektor': 'lektor',
        'napisy': 'napisy',
        'dubbing': 'dubbing',
        # AI flag (audio or subtitles)
        R(r'\bai\b', flags=re.IGNORECASE): 'AI',
        # audio CAM
        R(r'\b(md|(dubbing|lektor|audio)[ _.-]+(kino|cam\d*))\b', flags=re.IGNORECASE): 'kino',
    }

    def __init__(self) -> None:
        self._sess: Optional[requests.Session] = None
        self._found: JsonData = {}

    @property
    def sess(self) -> requests.Session:
        """Return request session."""
        if self._sess is None:
            self._sess = requests.Session()
            self._sess.get(self.URL)  # to get session "active" (cookies)
        return self._sess

    def request(self, url) -> JsonData:
        """Site get request."""
        resp = self.sess.get(url, headers={
            'accept': 'application/json',
            'referer': self.URL,
        })
        if resp.status_code == 200:
            return resp.json()
        return {}

    def make_id(self, tid: Union[int, str],
                *,
                type: Optional[Literal['movie', 'series', 'person']] = None,
                service: Optional[Literal['tmdb', 'imdb']] = None,
                ) -> str:
        """Make tmdb/imdb id/"""
        if type and service:
            tid = b64encode(f'{service}|{type}|{tid}'.encode()).decode('ascii')
        return str(tid)

    def source_name(self, item: JsonData) -> str:
        """Retrun source (service) name."""
        return urlparse(item['src']).hostname or ''

    @fflog_exc
    def _videos(self, data: JsonData) -> Iterator[SourceItem]:
        """Retrun list of found videos in movie() or episode(), agruments don't matter."""
        data = self._found
        if not data:
            data = {}
        media_id = data.get('id')
        videos = data.get('videos', ())
        fflog(f'[{self.PROVIDER.upper()}] {media_id=}, process {len(videos)} video(s)')
        if not videos:
            return
        # vtag = self.ffitem.vtag
        # titles = '|'.join(re.escape(t) for t in (self.ffitem.title, vtag.getEnglishTitle(), vtag.getOriginalTitle(),
        #                                          *data.get('titles', ())) if t)
        # rx_title = re.compile(fr'^({titles})\s*', flags=re.IGNORECASE)
        # known_sources = 'booster'  # '|'-separated list of well known sources
        for item in videos:
            # fflog(f'[{self.PROVIDER}][VIDEO]  video = {json.dumps(item, indent=2)}')
            if item.get('category') == 'full':
                name: str = item['name']
                lower_name = name.lower()
                quality: str = item['quality']
                lang: str = item['language']
                src: str = item['src']
                info = ' '.join(v for k, v in self.INFO_HIT.items() if (k in lower_name if isinstance(k, str) else k.search(lower_name)) and v)
                fflog(f'[{self.PROVIDER.upper()}] id={media_id} video={src!r}, {info=}')
                yield {
                    'source': self.source_name(item) or '?',
                    'quality': quality.lower() if quality[:3].isdigit() else quality.upper(),  # 1080p.. but 4K, HD...
                    'language': lang,
                    'url': src,
                    # 'info': re.sub(fr'\b(?:((?:lektor|dubb?ing|napisy)\s?)?{lang})\b', r'\1', rx_title.sub('', name), flags=re.IGNORECASE).split(None, 1)[-1],
                    'info': info,
                    'direct': False,
                    'debridonly': False,
                    'filename': name,
                    'premium': False,
                }

    @fflog_exc
    def movie(self, imdb: str, title: str, localtitle: str, aliases: str, year: str) -> Optional[str]:
        ids = self.ffitem.ids
        # get movie details
        for meta_service in ('tmdb', 'imdb'):
            if meta_id := ids.get(meta_service):
                media_id = self.make_id(meta_id, type='movie', service=meta_service)
                if data := self.request(f'{self.URL}api/v1/titles/{media_id}?loader=titlePage'):
                    data = data['title']
                    self._found = {
                        'id': data['id'],
                        'titles': [v for k in ('title', 'original_title') if (v := data.get(k))],
                        'videos': [v for v in data['videos'] if v.get('category') == 'full'],
                    }
                    # return json.dumps(self._found)
                    return data['id']
        fflog(f'[{self.PROVIDER.upper()}] movie {self.ffitem} not found')
        return None  # movie not found

    def tvshow(self, imdb, tvdb, tvshowtitle, localtvshowtitle, aliases, year) -> Optional[str]:
        return '_'  # not needed, search episode is enough

    @fflog_exc
    def episode(self, url, imdb, tvdb, title, premiered, season, episode) -> Optional[str]:
        ref = self.ffitem.ref
        if (show_item := self.ffitem.show_item) is None:
            return None
        ids = show_item.ids
        titles = []

        # only movie and series work with tmbd.imdb. For episode we have to get internal show id first.
        for meta_service in ('tmdb', 'imdb'):
            if meta_id := ids.get(meta_service):
                media_id = self.make_id(meta_id, type='series', service=meta_service)
                if data := self.request(f'{self.URL}api/v1/titles/{media_id}?loader=titlePage'):
                    data = data['title']
                    media_id = data['id']
                    titles = [v for k in ('name', 'original_title') if (v := data.get(k))]
                    break
        else:
            fflog(f'[{self.PROVIDER.upper()}] show {self.ffitem} not found')
            return None  # show not found

        # get episde details
        if data := self.request(f'{self.URL}api/v1/titles/{media_id}/seasons/{ref.season}/episodes/{ref.episode}?loader=episodePage'):
            data = data['episode']
            if name := data.get('name'):
                titles.append(name)  # add episode name
            self._found = {
                'id': media_id,
                'titles': titles,
                'videos': [v for v in data['videos'] if v.get('category') == 'full']
            }
            # return json.dumps(self._found)
            return media_id
        fflog(f'[{self.PROVIDER.upper()}] episode {self.ffitem} / {ref.season} / {ref.episode} not found')
        return None  # episode not found

    def sources(self, url: str, hostDict, hostprDict, from_cache: bool = False) -> Sequence[SourceItem]:
        if not url:
            return []
        # data = json.loads(url)
        # return list(self._videos(data))
        return list(self._videos({}))

    def resolve(self, url: str, *, buy_anyway: bool = False) -> str:
        return url


class ObejrzyjTo(_source):
    """Scraper for obejrzyj.to."""
    PROVIDER: ClassVar[str] = 'obejrzyjto'
    URL: ClassVar[str] = 'https://obejrzyj.to/'

    def source_name(self, item: JsonData) -> str:
        """Retrun source (service) name."""
        return item['name'].split(None, 1)[0] or super().source_name(item)


class FilmyOnlineCc(_source):
    """Scraper for filmyonline.cc."""
    PROVIDER: ClassVar[str] = 'filmyonline'
    URL: ClassVar[str] = 'https://filmyonline.cc/'


def register(sources: List[SourceModule], group: str) -> None:
    """Register all scrapers."""
    from lib.sources import SourceModule
    for src in (ObejrzyjTo, FilmyOnlineCc):
        sources.append(SourceModule(name=src.PROVIDER, provider=src(), group=group))
