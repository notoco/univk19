"""
Simple TV scrappers.

Now supports:
- filmweb.pl
- programtv.onet.pl
"""

from typing import Optional, Union, Any, List, Dict, Sequence, Iterator, Iterable, ClassVar
from typing_extensions import Literal, TypeAlias
import re
from html import unescape
from itertools import chain
import json
from attrs import define

from ..defs import Pagina, ItemList
from ..ff.item import FFItem
from .tmdb import TmdbApi
from ..ff.tmdb import tmdb
from ..ff.control import max_thread_workers
from ..ff import requests
from ..ff.requests import RequestsPoolExecutor


TvServiceName: TypeAlias = Literal['filmweb', 'onet']


@define(kw_only=True)
class TvMovie:
    #: FilmWeb ID
    id: str
    #: Title (PL)
    title: str
    #: Movie year
    year: int
    #: TV air time.
    time: str
    #: TV channel.
    channel: str
    #: Image URL.
    image: str
    #: URL to media details.
    url: str = ''
    #: Description
    descr: str = ''

    def role(self) -> str:
        if self.time and self.channel:
            return f'{self.time:0>5}, {self.channel}'
        if self.time:
            return f'{self.time:0>5}'
        return self.channel


class TvProgram:
    """Base for TV scrappers."""

    SERVICES: ClassVar[Dict[str, 'TvProgram']] = {}

    def __init__(self, *, tmdb: TmdbApi) -> None:
        self.tmdb: TmdbApi = tmdb
        self.cache: Dict[str, TvMovie] = {}

    @classmethod
    def tv_service(cls, service: TvServiceName) -> Optional['TvProgram']:
        """Get tv program service by name."""
        return cls.SERVICES.get(service)

    def _tv_movie_iter(self) -> Iterator[TvMovie]:
        raise NotImplementedError(f'class {self.__class__.__name__} has no _tv_movie_iter()')

    def _tv_items(self, tv: TvMovie) -> Sequence[FFItem]:
        """Get items for single TV movie."""
        def select(items: Iterable[FFItem]) -> Iterator[FFItem]:
            role = tv.role()
            for it in items:
                if not it.year or it.year in range(tv.year - 1, tv.year + 2):
                    if role:
                        it.role = role
                    yield it
        return list(select(self.tmdb.search(query=tv.title, type='movie', year=tv.year)))

    def _get_info(self, items: Pagina[TvMovie]) -> Pagina[TvMovie]:
        return items

    def tv_movies(self, *, page: int = 1, limit: int = 20) -> Pagina[TvMovie]:
        """Get today in TV movies (filmweb info)."""
        tv_list = tuple(self._tv_movie_iter())
        self.cache = {tv.id: tv for tv in tv_list}
        return self._get_info(Pagina(tv_list, page=page, limit=limit))

    def tv_movie_all_items(self, *, page: int = 1, limit: int = 20) -> Sequence[FFItem]:
        """Get today in TV movies."""
        tv_list = Pagina(self._tv_movie_iter(), page=page, limit=limit)
        with RequestsPoolExecutor(max_thread_workers()) as ex:
            list_of_items = ex.map(self._tv_items, tv_list)
        return ItemList((it for items in list_of_items for it in items), page=page, total_pages=tv_list.total_pages)

    def tv_movie_items(self, id: str) -> Sequence[FFItem]:
        """Get movies for single (TV) movie."""
        if id not in self.cache:
            self.tv_movies(page=1, limit=1_000_000_000)
        if tv := self.cache.get(id):
            return self._tv_items(tv)
        return []

    def tv_movie_mixed_items(self, *, page: int = 1, limit: int = 20) -> Sequence[Union[FFItem, TvMovie]]:
        """Get today in TV movies."""
        tv_list = self.tv_movies(page=page, limit=limit)
        with RequestsPoolExecutor(max_thread_workers()) as ex:
            list_of_items = ex.map(self._tv_items, tv_list)
        return ItemList((items[0] if len(items) == 1 else tv for tv, items in zip(tv_list, list_of_items) if items),
                        page=page, total_pages=tv_list.total_pages)


class FilmWebTv(TvProgram):
    """Tiny filmweb.pl TV scraper."""

    _rx_in_tv_item = re.compile(r'src="(?P<image>[^"]*)" loading="lazy".*?'
                                r'<a\b[^>]*class="[^"]*\bname\b[^"]*"[^>]*href="[^"]*-(?P<year>\d+)-(?P<id>\d+)"[^>]*>\s*(?P<title>[^<]+?)\s*</a>'
                                r'(?:\s*<div class="top-5 maxlines-2 cap">(?P<time>\d+:\d+)[^<]*<a[^>]*>(?P<chan>[^<]*)</a>)?')

    def __init__(self, *, tmdb: TmdbApi) -> None:
        super().__init__(tmdb=tmdb)
        self.url: str = 'https://www.filmweb.pl/program-tv'

    @requests.netcache('search')
    def _tv_movie_iter(self) -> Iterator[TvMovie]:
        """Get today in TV movies."""
        page = requests.get(self.url).text
        start = page.find('<div class="entitiesList inTv pageBox')
        if (box := page[start:page.find('</div></div></div></div></div></div></div>', start)]):
            for mch in self._rx_in_tv_item.finditer(box):
                title, year = mch['title'], mch['year']
                yield TvMovie(id=mch['id'], title=unescape(title), year=int(year),
                              time=mch['time'] or '', channel=mch['chan'] or '',
                              image=mch['image'])


class OnetTv(TvProgram):
    """Tiny programtv.onet.pl TV scraper."""

    _rx_in_tv_descr = re.compile(r'\s*((?P<genre>[^<,]*),)?\s*(?P<country>[^<]*)\s+(?P<year>\d{4})\s*')

    def __init__(self, *, tmdb: TmdbApi) -> None:
        super().__init__(tmdb=tmdb)
        self.tv_url = 'https://programtv.onet.pl/ajax/kategoria/film?dzien=0&godzina={hour}&format=json'
        self.entry_url = 'https://programtv.onet.pl/tv/{entry_url}'

    @requests.netcache('search')
    def _tv_movie_iter(self) -> Iterator[TvMovie]:
        """Get today in TV movies."""
        def get(hour: int) -> List[Dict[str, Any]]:
            data = requests.get(self.tv_url.format(hour=hour)).json()
            return data.get('entries', ())

        with RequestsPoolExecutor(max_thread_workers()) as ex:
            list_of_entries = ex.map(get, chain(range(3, 24), range(0, 3)))
        for entries in list_of_entries:
            for it in entries:
                if (eid := it.get('entry_url', '').partition('?')[0].rpartition('/')[2]):
                    year = int(m['year']) if (m := self._rx_in_tv_descr.search(it.get('info', ''))) else 0
                    yield TvMovie(id=eid, title=it.get('title', ''), year=year, time=it.get('time', ''),
                                  channel=it.get('channel_name', ''), image='', url=it.get('entry_url', ''))

    @requests.netcache('search')
    def _get_info(self, items: Pagina[TvMovie]) -> Pagina[TvMovie]:
        def get(it: TvMovie) -> None:
            page = requests.get(self.entry_url.format(entry_url=it.url)).text
            starter = '<script type="application/ld+json">'
            start = page.find(starter)
            end = page.find('</script>', start)
            if start != -1 and end != -1:
                start += len(starter)
                data = next((d for d in json.loads(page[start:end]) if d.get('@type') == 'BroadcastEvent'), {})
                work = data.get('workPerformed', {})
                # print(json.dumps(data, indent=2))
                it.descr = data.get('description', '')
                it.image = work.get('thumbnailUrl', '')

        with RequestsPoolExecutor(max_thread_workers()) as ex:
            ex.map(get, items)
        return items


TvProgram.SERVICES['filmweb'] = filmweb = FilmWebTv(tmdb=tmdb)
TvProgram.SERVICES['onet'] = onet = OnetTv(tmdb=tmdb)


if __name__ == '__main__':
    from ..ff.cmdline import DebugArgumentParser
    p = DebugArgumentParser()
    p.add_argument('service', nargs='?', choices=('filmweb', 'onet'), default='filmweb', help='tv service')
    args = p.parse_args()
    service = TvProgram.SERVICES[args.service]
    for x in service._tv_movie_iter():
        print(x)
    # for it in filmweb.tv_movie_all_items():
    #     print(it)
