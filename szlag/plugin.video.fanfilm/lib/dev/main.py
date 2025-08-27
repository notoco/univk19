
from __future__ import annotations
import signal
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Optional
    from argparse import Namespace


class AlarmIterrupt(RuntimeError):
    pass


class Alarm:

    def __init__(self) -> None:
        self.prev = ...

    def _handle(self, sig, frame):
        if self.prev is not ...:
            signal.signal(signal.SIGALRM, self.prev)
        raise AlarmIterrupt()

    def __call__(self, seconds: int) -> None:
        prev = signal.signal(signal.SIGALRM, self._handle)
        if self.prev is ...:
            self.prev = prev
        signal.alarm(seconds)

    def cancel(self) -> None:
        if self.prev is not ...:
            signal.signal(signal.SIGALRM, self.prev)
        signal.alarm(0)


alarm = Alarm()


def _service_process():
    from time import sleep
    works = None

    def _start_service():
        from ..ff.threads import Event
        from ..service.http_server import HttpProxy
        from ..service.tracking.trakt import TraktSync
        from ..service.misc import VolatileFfid
        from ..service.main import Works
        from ..service.http_server import RequestHandler
        from ..service.client import service_client

        nonlocal works
        RequestHandler.DEFAULT_PORT = 8123
        service_client._url = f'http://127.0.0.1:{RequestHandler.DEFAULT_PORT}/'
        works = Works()
        works.trakt_sync = TraktSync()
        works.http = HttpProxy(works=works)
        works.trakt_sync.start()
        works.http.start()
        return works

    def _stop_service(sig=0, frame=None):
        nonlocal works
        assert works
        # print('SSTTTOOOOOOOOOOOOOOPPPP !!!!', file=sys.stderr)
        works.trakt_sync.stop()
        works.http.stop()
        sys.exit(0)

    pid = os.fork()
    if pid == 0:  # child (service)
        works = _start_service()
        signal.signal(signal.SIGTERM, _stop_service)
        while True:
            try:
                alarm(3600)
                sleep(1)
            except (KeyboardInterrupt, AlarmIterrupt):
                _stop_service()
            except Exception:
                ...
    return pid


def start_service():
    from time import sleep
    import requests
    from ..service.http_server import RequestHandler
    from ..service.client import service_client
    RequestHandler.DEFAULT_PORT = 8123
    service_client._url = f'http://127.0.0.1:{RequestHandler.DEFAULT_PORT}/'
    pid = _service_process()
    for i in range(10):
        try:
            if requests.get(f'{service_client._url}info').status_code == 200:
                print('Service HTTP is ready')
                break
        except OSError:
            pass
        if not i:
            print('Waiting for service HTTP...')
        sleep(.1)
    return pid


def stop_service(service):
    print('stopping service...')
    os.kill(service, signal.SIGINT)
    try:
        alarm(1)
        os.waitpid(service, 0)
        alarm.cancel()
    except AlarmIterrupt:
        os.kill(service, signal.SIGTERM)
        try:
            alarm(1)
            os.waitpid(service, 0)
            alarm.cancel()
        except AlarmIterrupt:
            print(f'Waiting too long for service stop ({service}), kill em all')
            os.kill(service, signal.SIGKILL)


def parse_args():
    # from argparse import ArgumentParser
    # from .. import cmdline_argv
    from ..ff.cmdline import DebugArgumentParser
    from os import pathsep

    # p = ArgumentParser()
    p = DebugArgumentParser(add_help=False)
    p.add_argument('url', nargs='?', default='/', help='plugin url (or just path) [plugin://host]/path[?query]')
    p.add_argument('handle', nargs='?', default='1', help='plugin handle')
    p.add_argument('query', nargs='?', default='', help='plugin query, if not in url')
    p.add_argument('resume', nargs='?', default='resume:false', help='plugin resume?')
    p.add_argument('--lang', help='language (default: pl_PL)')
    p.add_argument('--api-lang', help='override override media API language (default from settings)')
    p.add_argument('--info-label', metavar='NAME=VALUE', action='append', help='override global info label (`Container.PluginName=X` for emulate widget)')
    p.add_argument('--setting', metavar='ID=VALUE', action='append', help='override settings value')
    p.add_argument('--readonly-settings', action='store_true', help='do not write the settings')
    p.add_argument('--import-path', metavar='PATH', action='append', help='add python import path')
    p.add_argument('--import-addon', metavar='ADDON_ID', action='append', help='add kodi addon import path')
    p.add_argument('-T', '--tui', choices=('simple', 'main', 'tree'), default='simple', help='TUI variant')
    p.add_argument('-r', '--run', action='store_true', help='run in loop')
    p.add_argument('-S', '--no-service', action='store_false', dest='service', help='skip service')
    p.add_argument('--video-db', nargs='?', metavar='PATH', const=True,
                   help='path to kodi MyVideos.db or without path to use default')
    p.add_argument('-K', '--kodi-path', metavar=f'PATH[{pathsep}PATH]...',
                   help='path to KODI user data and optional additional installation paths')
    args, _ = p.parse_known_args()
    # print(f'Parsed args: {args}  !!!', file=sys.stderr)

    pp = DebugArgumentParser(parents=[p], description='FF3 console')
    if args.tui == 'simple':
        pp.add_argument('-m', '--menu', metavar='INDEX|*', type=lambda s: -1 if s == '*' else int(s),
                        help='show context menu at given index (old), use `*` for all')
        pp.add_argument('-i', '--info', metavar='INDEX', type=int, help='show info at given index (old)')
        pp.add_argument('-x', '--extra-info', metavar='INDEX', type=int, help='show extra debug info at given index (old)')
        pp.add_argument('-X', '--xxx', action='store_true', help='tmp debug test xxx...')
        # print(pp.parse_args()); exit()
    return pp.parse_args()
    # return p.parse_args(cmdline_argv[1:])


def predefine():
    """Check options on startup and patch FF (set dome defaults)."""
    args = parse_args()

    if args.import_path:
        from sys import path
        for p in args.import_path:
            if p not in path:
                path.append(p)
    if args.lang or args.api_lang:
        from lib.fake.fake_api import set_locale
        set_locale(args.lang, api=args.api_lang)
    if args.info_label:
        from lib.fake.fake_api import INFO_LABEL
        INFO_LABEL.update({k: v for k, _, v in (x.partition('=') for x in args.info_label)})
    if args.readonly_settings:
        from lib.fake import fake_api
        fake_api.SETTINGS_READONLY = True
    if args.setting:
        from lib.fake.fake_api import SETTINGS
        SETTINGS.update({k: v for k, _, v in (x.partition('=') for x in args.setting)})
    if args.video_db:
        from pathlib import Path
        from ..ff.kodidb import video_db, vdb_ver
        from lib.fake.fake_api import KODI_PATH
        if args.video_db is True:
            args.video_db = KODI_PATH / 'userdata' / 'Database' / f'MyVideos{vdb_ver}.db'
        video_db.path = Path(args.video_db)
    if not args.service:
        from .. import service
        # No service, fake service client (base direct support)
        from ..service.fake_client import FakeServiceClient
        from ..service import client
        service.SERVICE = True  # direct access, like in the service
        client.service_client = FakeServiceClient()
        # constdef._locked = False  # type: ignore
        # const.tune.service.http_server.try_count = 1
        # constdef._locked = True  # type: ignore


def sty_stdout() -> None:
    import sty
    if not sys.stdout.isatty():
        for k in dir(sty):
            o = getattr(sty, k)
            if isinstance(o, sty.Register):
                o.mute()


def apply_lang(lang: Optional[str]) -> None:
    if lang:
        from xbmcaddon import Addon
        Addon.LANG = lang


def apply_args(args: Namespace) -> None:
    if hasattr(args, 'url'):
        if not args.url:
            args.url = '/'
        if '://' not in args.url:
            assert args.url.startswith('/')
            args.url = f'plugin://plugin.video.fanfilm{args.url or "/"}'  # DEBUG (terminal)
        if args.query:
            args.query = args.query.removeprefix('?')
            if '?' in args.url:
                args.url = f'{args.url}&{args.query}'
            else:
                args.url = f'{args.url}?{args.query}'
    apply_lang(args.lang)


def main():
    """Main console app."""
    args = parse_args()
    if args.tui == 'main':
        from .tui.main import tui
        tui()
    elif args.tui == 'tree':
        from .tui.tree import tui
        tui()
    else:
        from .tui.simple import tui
        tui()
