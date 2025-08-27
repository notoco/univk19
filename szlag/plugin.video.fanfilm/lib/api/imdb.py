import re
import json
from typing import Optional, Union, Any, Tuple, List, Dict, Sequence, Collection, ClassVar, Pattern
from typing_extensions import TypeAlias, Literal
from attrs import define

from ..ff import requests
from ..ff.log_utils import fflog
from ..ff.item import FFItem
from ..ff.types import JsonData
from ..defs import MediaRef, VideoIds, RefType, ItemList
from ..kolang import L

ImdbTitleType: TypeAlias = Literal['feature', 'tv_series', 'short', 'tv_episode', 'tv_miniseries',
                                   'tv_movie', 'tv_special', 'tv_short', 'video_game', 'video',
                                   'music_video', 'podcast_series', 'podcast_episode']

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


@define
class ImdbApiStats:
    request_count: int = 0


@requests.netcache('lists')
class ImdbScraper:

    PATTERN: ClassVar[Pattern[str]] = re.compile(r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)<\/script>', re.DOTALL)

    MEDIA_TYPES: ClassVar[Dict[str, RefType]] = {
        'movie': 'movie',
        'short': 'movie',
        'tvMovie': 'movie',
        'tvShort': 'movie',
        'tvSpecial': 'movie',
        'video': 'movie',
        'videoGame': 'movie',
        'musicVideo': 'movie',
        'tvSeries': 'show',
        'tvMiniSeries': 'show',
        'podcastSeries': 'show',
        'tvEpisode': 'episode',
        'podcastEpisode': 'episode',
    }

    TITLE_TYPES: ClassVar[Dict[RefType, Collection[ImdbTitleType]]] = {
        'movie':   ('feature', 'short', 'tv_movie', 'tv_short', 'tv_special'),
        'show':    ('tv_series', 'tv_miniseries'),
        'episode': ('tv_episode',),
        # 'movie':   ('feature', 'short', 'tv_movie', 'tv_short', 'tv_special', 'video', 'video_game', 'music_video'),
        # 'show':    ('tv_series', 'tv_miniseries', 'podcast_series'),
        # 'episode': ('tv_episode', 'podcast_episode'),
    }

    _DEBUG_STATS: ClassVar[ImdbApiStats] = ImdbApiStats()
    _FAKE: ClassVar[bool] = False

    def __init__(self) -> None:
        self.headers = {"User-Agent": UA}
        # title_type = feature, tv_series, short, tv_episode, tv_miniseries, tv_movie, tv_special, tv_short,
        #              video_game, video,music_video, podcast_series, podcast_episode
        self.url: str = 'https://www.imdb.com/'

    def get_html(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[str]:
        fflog(f'Get from {url}')
        self._DEBUG_STATS.request_count += 1
        if self._FAKE:
            return None
        req = requests.get(url, headers=self.headers, params=params)
        if req.status_code != 200:
            return None
        return req.text

    def get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> JsonData:
        html: Optional[str] = self.get_html(url, params=params)
        if html is not None:
            if mch := self.PATTERN.search(html):
                return json.loads(mch.group(1)).get("props", {}).get("pageProps", {})
        return {}

    @requests.netcache('discover')
    def last_oscars_refs(self,
                         name: str = 'oscar_winner',
                         *,
                         title_type: Union[ImdbTitleType, Collection[ImdbTitleType], None] = None,
                         ) -> List[MediaRef]:
        params = {
            'sort': 'year,desc',
            'count': 250,
            'groups': name,
        }
        if title_type:
            if isinstance(title_type, str):
                params['title_type'] = title_type
            else:
                params['title_type'] = ','.join(title_type)
        if json_object := self.get_json(f'{self.url}search/title/', params=params):
            data: List[JsonData] = json_object.get("searchResults", {}).get("titleResults", {}).get("titleListItems", [])
            return [VideoIds(imdb=it['titleId']).ref(ref_type) for it in data if (ref_type := self.MEDIA_TYPES.get(it['titleType']['id']))]
        return []

    def _get_list(self, url_path: str, *, data_key: str, media_type: Optional[RefType] = None, page: Optional[int] = 0) -> List[MediaRef]:
        def get(page: Optional[int] = 0) -> Tuple[Sequence[JsonData], int]:
            params = {'count': 250}
            if page:
                params['page'] = page
            if data := self.get_json(f'{self.url}{url_path}', params=params):
                if imdb_list := data.get('mainColumnData', {}).get(data_key, {}):
                    # imdb_list['id']
                    # imdb_list['createdDate']
                    # imdb_list['lastModifiedDate']
                    # imdb_list['author'] = {}
                    if items_data := imdb_list.get('titleListItemSearch', {}):
                        return [node for edge in items_data.get('edges', []) if (node := edge.get('listItem', {}))], items_data.get('total', 0)
            return [], 0

        items, total = get(page)
        return ItemList((MediaRef(media, VideoIds.make_ffid(imdb=node['id']))
                         for node in items
                         if (media := self.MEDIA_TYPES.get(node['titleType']['id'])) and (not media_type or media_type == media)),
                        page=page or 1, total_pages=(total + len(items) - 1) // max(1, len(items)), total_results=total)

    def watch_list(self, user: str, *, media_type: Optional[RefType] = None, page: Optional[int] = None) -> List[MediaRef]:
        return self._get_list(f'/user/{user}/watchlist/', data_key='predefinedList', media_type=media_type, page=page)

    def list(self, list_id: str, *, media_type: Optional[RefType] = None, page: Optional[int] = None) -> List[MediaRef]:
        return self._get_list(f'/list/{list_id}/', data_key='list', media_type=media_type, page=page)

    def user_lists(self, user: str) -> List[FFItem]:
        def make_item(node: JsonData) -> FFItem:
            name = node['name']['originalText']
            # ref = MediaRef('list', VideoIds.make_ffid(imdb=node['id']))
            ffitem = FFItem(name, mode=FFItem.Mode.Folder)
            ffitem.title = name
            ffitem.vtag.setUniqueID(node['id'], 'imdb')
            ffitem.vtag.setIMDBNumber(node['id'])
            if descr := node['description']:
                ffitem.vtag.setPlot(descr['originalText']['plainText'])
            if img := node.get('primaryImage', {}).get('image'):
                ffitem.setArt({'poster': img['url']})
            if count := node.get('items'):
                ffitem._children_count = count['total']
                ffitem.role = L(30331, '{n} title|||{n} titles', n=count['total'])
            # createdDate, lastModifiedDate
            return ffitem

        if data := self.get_json(f'{self.url}/user/{user}/lists/'):
            # print(json.dumps(data, indent=2))
            if imdb_list := data.get('mainColumnData', {}).get('userListSearch', {}):
                return [make_item(node)
                        for edge in imdb_list.get('edges', [])
                        if (node := edge.get('node', {}))]  # and node['listType']['id'] == 'TITLES']
        return []


if __name__ == '__main__':
    from ..ff.cmdline import DebugArgumentParser
    p = DebugArgumentParser()
    p.add_argument('-w', '--watchlist', help='IMDB user ID like ur123456789')
    p.add_argument('-u', '--user', help='IMDB user ID like ur123456789')
    p.add_argument('-l', '--list', help='IMDB list ID like ls123456789')
    p.add_argument('-p', '--page', type=int, help='IMDB list ID like ls123456789')
    p.add_argument('-d', '--depaginate', action='store_true', help='depaginate list')
    args = p.parse_args()

    imdb = ImdbScraper()
    if args.watchlist:
        for ref in imdb.watch_list(args.watchlist, page=page):
            print(ref)
    elif args.user:
        for ref in imdb.user_lists(args.user):
            print(ref)
    elif args.list:
        if args.depaginate:
            from . import depaginate
            with depaginate(imdb) as api:
                for ref in api.list(args.list, page=args.page):
                    print(ref)
        else:
            for ref in imdb.list(args.list, page=args.page):
                print(ref)
    else:
        for ref in imdb.last_oscars_refs():
            print(ref)
