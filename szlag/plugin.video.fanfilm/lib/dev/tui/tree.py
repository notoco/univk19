from __future__ import annotations
from typing import TYPE_CHECKING
import re
import sys
from attrs import define, field
import sty
from ..main import parse_args, sty_stdout, apply_args
if TYPE_CHECKING:
    from ...fake.xbmcplugin import _Item


def get_folder_tree():
    """Return full tree of FF3 folders. Skip media calls."""


def tui():
    from ...service.client import service_client
    from ...ff.item import FFItem
    from ...api.trakt import TraktApi
    from ...api.tmdb import TmdbApi
    from ...api.imdb import ImdbScraper
    from ...fake.fake_api import reset as fake_reset, url_at_index, get_directory, print_last_directory, set_print_list_callback
    from ...fake.xbmcplugin import _Item

    @define
    class Folder:
        name: str
        url: str
        media: bool = field(default=False, kw_only=True)
        folder: bool = field(default=False, kw_only=True)
        items: list[Folder] = field(factory=list, kw_only=True)

    def print_dir(items: list[_Item]) -> None:
        pass

    def skip_folder(url: str, *, parent: str) -> bool:
        if not url or 'page=' in url:
            return True
        if not parent:
            return False
        if re.sub(r'/[12]\>', '', url) == parent:
            return True
        # if re.search(r'/\d{1,3}($|\?)', url):
        if re.search(r'/\d+($|\?)', url):
            return True
        return False

    # def scan(name: str, url: str) -> Folder:
    def scan(item: _Item) -> Folder:
        url = item.url
        print(f'{sty.ef.bold}{sty.fg.yellow}scan {url} ...{sty.rs.all}')
        if url in visited:
            return Folder(f'{item.item.getLabel()} […]', item.url)
        if not item.folder:
            return Folder(item.item.getLabel(), item.url)
        visited.add(url)
        u0, sep, u2 = url.partition('?')
        sys.argv = [u0, args.handle, sep+u2, args.resume]
        try:
            from ...main import main
            main(sys.argv)
        except EOFError as exc:
            return Folder(f'EXC: {exc!r}', url)
        items = list(get_directory())
        fake_reset()
        return Folder(item.item.getLabel(), item.url, folder=True,
                      items=[scan(it) for it in items if not skip_folder(it.url, parent=url)])

    def print_folder(folder: Folder, *, level: int = 0) -> None:
        indent = '  ' * level
        # slash = '/' if folder.folder else ''
        # print(f'{indent}{folder.name:40s} {slash:1s}')
        print(f'{indent}{folder.name}')
        for it in folder.items:
            print_folder(it, level=level+1)

    args = parse_args()
    sty_stdout()
    service_client.__class__.LOG_EXCEPTION = False
    TraktApi._FAKE = True
    TmdbApi._FAKE = True
    ImdbScraper._FAKE = True
    set_print_list_callback(print_dir)

    visited: set[str] = set()

    url = args.url
    folder = scan(_Item(url, FFItem('/'), True))
    print_folder(folder)
