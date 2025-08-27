"""Main module."""

# parse command-line (debug) args on TOP, to set global options first
if __name__ == '__main__':
    try:
        from .dev.main import predefine as tui_predefine
    except ModuleNotFoundError:
        import sys
        print('There is no module lib.dev, find a developer release.')
        sys.exit(0)
    tui_predefine()

import sys  # for exit()
from typing import Optional, Any, List, Dict, Set, TYPE_CHECKING
from typing_extensions import Literal
from time import monotonic

import xbmcgui

from const import const
from .ff.settings import settings
from .ff.routing import URL, dispatch, main_router
from .ff import control
from .ff.control import Finally
from .ff.db import state
from .ff.log_utils import fflog, fflog_exc
from .ff.routing import route, PathArg
from .ff.calendar import utc_timestamp
from .ff.menu import KodiDirectory, directory
from .ff.info import ffinfo
from .service.client import service_client
# from .defs import VideoIds
from .indexers import navigator
from .kolang import L

if TYPE_CHECKING:
    from .service.misc import PluginRequestInfo


nav = navigator.Navigator()
# main_router.add_route('/', router=nav)  -- Navigator is now MainRouteObject
main_router.set_default_route_object(nav)
main_router.url = URL(control.plugin_url)


def reset() -> None:
    """Reset all stuff for reuse code (re-run in the same Python interpreter)."""
    L.reset()
    settings.reset()  # force recreate settings proxy
    control.reset()
    navigator.reset()
    ffinfo.reset()
    # trakt.trakt_credentials_manager.reset()


#: Folders to bypass.
empty_folders: Set[str] = set()


def bypass_scanning(info: 'PluginRequestInfo') -> bool:
    if info.scan_finished:
        empty_folders.clear()
    try:
        root, path, show_id, *waste, num = info.url.path.split('/')
    except Exception:
        return False
    if not root and not waste and path == 'tvshow' and f'/tvshow/{show_id}' == info.media_url.path and num.isdigit() and show_id.isdigit():
        with directory() as kdir:
            if info.scan_started:  # return all episodes (starting from 2nd sezon) in single folder
                from .defs import MediaRef
                from .ff.info import ffinfo
                ffitem = ffinfo.find_item(MediaRef.tvshow(int(show_id)), progress=ffinfo.Progress.NO, tv_episodes=True)
                if ffitem:
                    for sz in ffitem.season_iter():
                        if sz.season and sz.season >= 2:
                            for ep in sz.episode_iter():
                                kdir.add(ep, url=kdir.no_op)
                        empty_folders.add(f'/tvshow/{show_id}/{sz.season}')
        return True
    return False


def main(argv: List[str]) -> None:
    """The main FF entry."""
    T = monotonic()
    url = URL(argv[0] + argv[2])
    if url.path in empty_folders:
        from xbmcplugin import endOfDirectory
        endOfDirectory(int(sys.argv[1]), updateListing=False, cacheToDisc=False)
        return
    Finally.clear()
    if control.is_plugin_folder():
        folder_info = service_client.plugin_request_enter(url, timestamp=utc_timestamp())
    else:
        from .service.misc import PluginRequestInfo
        folder_info = PluginRequestInfo()
    KodiDirectory.set_current_info(url, folder_info)
    master: bool = state.enter('plugin')
    state.delete_all(module='directory')
    state.multi_set((
        ('running', True),
        ('url', str(url)),
        ('path', url.path),
    ), module='directory')
    try:
        if folder_info.scan and bypass_scanning(folder_info):
            trakt_db_timestamp = state.get('db.timestamp', module='trakt', default=0)
        else:
            KodiDirectory.ready_for_data()
            trakt_db_timestamp = state.get('db.timestamp', module='trakt', default=0)
            dispatch(url)
    except Exception:
        fflog_exc()
        raise
    else:
        # handle queued jobs
        for job in state.jobs('plugin'):
            handle_job(job, argv)
        if KodiDirectory.INFO.refresh:
            new_timestamp = state.get('db.timestamp', module='trakt', default=0)
            fflog(f'!@#$!@#!@#!@#!@#!@#!@#!@#!@#!@#!@#!@#!@#!@#!@ {trakt_db_timestamp=}, {new_timestamp=}')
            if new_timestamp != trakt_db_timestamp:
                control.refresh()
    finally:
        if control.is_plugin_folder():
            service_client.plugin_request_exit(folder=KodiDirectory.CONTENT if KodiDirectory.CREATED else None,
                                               focus=KodiDirectory.FOCUS_INDEX, timestamp=utc_timestamp())
        state.set('running', False, module='directory', connect=False)
        state.exit('plugin')
        for fin in Finally.iter():
            fin()
        Finally.clear()
        T = monotonic() - T
        fflog(f'[FF] main finished in {T:.3f} seconds')


@route
def xplay(type: PathArg[Literal['movie', 'tvshow']], ffid: PathArg[int],
          season: Optional[PathArg[int]] = None, episode: Optional[PathArg[int]] = None) -> None:
    """Play video."""
    print(f'play({type=}, {ffid=}, {season=}, {episode=}) ...')


# XXX  ---( DEBUG )---   XXX
@route('/play430/movie')
def fake_play_movie(ffid: PathArg[int], *, edit: bool = False) -> None:
    from pathlib import Path
    from .defs import MediaRef
    from .ff import player
    from .ff.item import FFItem
    import sty
    item: Optional[FFItem] = ffinfo.find_item(MediaRef('movie', ffid))
    fflog(f'{sty.fg.cyan}######{sty.rs.all} {ffid=}, {item=}')
    with state.with_var('playing.prepare', module='player'):
        if item and control.yesnoDialog('play fake video'):
            player.play(item, str(Path('~/Videos/Agent 700 _ WYSOKA JAKOŚĆ -g-bbImiyuPQ.mkv').expanduser()))
        else:
            player.cancel(item)


@route
def rescan(ffid: Optional[PathArg[int]] = None) -> None:
    """Rescan sources in source window."""
    # from lib.ff import sources
    from lib.ff.cache import cache_clear_sources  # cache_clear_providers

    # `ffid` is ignored now. This method clear cache and emulate click in gui.

    cache_clear_sources()
    checkWin = xbmcgui.getCurrentWindowId()

    control.execute("Dialog.Close(all,true)")
    control.execute(f"ReplaceWindow({checkWin})")
    control.execute("Action(Select)")


@route
def crash() -> None:
    """Forces crash, raises en exception."""
    raise Exception('Devleper forced CRASH')


def handle_job(job: state.Job, argv: List[str]) -> None:
    """Handle pending job."""

    if const.debug.enabled:
        if const.debug.tty:
            fflog(f'[JOB] \033[96mjob\033[0m: {job}')
        else:
            fflog(f'[JOB] job: {job}')
    if job.command == 'update':
        if job.args and job.args[0]:
            path = job.args[0]
        else:
            path = ''  #f'{argv[0]}{argv[2]}'  # path to current plugin call
        control.update(path)
    elif job.command == 'refresh':
        control.refresh()
    elif job.command == 'builtin':
        control.execute(job.args[0])


# --- testy (konsola)  ---


if __name__ == '__main__':
    from .dev.main import main as tui
    tui()
