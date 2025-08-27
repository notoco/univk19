"""
    FanFilm Add-on

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

from __future__ import annotations
from typing import Optional, ClassVar, overload
import json
from ast import literal_eval
from attrs import frozen

from xbmc import getCondVisibility, getInfoLabel, Player as XbmcPlayer, PlayList, PLAYLIST_VIDEO
from xbmcplugin import setResolvedUrl
from xbmcgui import ListItem

from . import control
from .db import state
from .item import FFItem
from ..indexers.defs import VideoIds
from .log_utils import fflog, fflog_exc
from .control import close_busy_dialog, syshandle, resources_file
from .db import state
from .kotools import stop_playing
from .kodidb import video_db
from .settings import settings
from ..sources import Source
from const import const, PlayCancel, MediaWatchedMode


def server_file(fname: str) -> str:
    return resources_file(fname)  # HACK, use file from disk (resources/media/)
    url = state.get('url', module='service', mode=state.StateMode.DB)
    return f'{url}{fname}'


def fallback_path() -> str:
    """Falback for play movie/eposode FF3 URL."""
    from sys import argv
    if len(argv) >= 2:
        return argv[0] + argv[2]
    return ''


def cancel(ffitem: Optional[FFItem] = None) -> None:  # TODO: remove ffitem?
    """Cancel starting a video play."""
    # fflog(f'[PLAYER] CANCEL, {ffitem=}')
    try:
        # pli = get_player_item()
        if getInfoLabel('ListItem.Label') and getInfoLabel('ListItem.PercentPlayed') == '0' and not getCondVisibility('ListItem.IsResumable'):
            # has info and play from beggining
            cancel_mode = const.player.cancel_start  # typically PlayCancel.EMPTY
        else:
            # resume or missing info (we don't know if resume or not, resume is more safty)
            cancel_mode = const.player.cancel_resume  # typically PlayCancel.TT430

        if cancel_mode is PlayCancel.FALSE:
            item = ListItem()
        elif cancel_mode is PlayCancel.EMPTY:
            item = ListItem(path=server_file('media/empty.m3u8'))
        elif cancel_mode is PlayCancel.TT430:
            item = ListItem(path=server_file('media/tt430.mp4'))
        else:
            fflog.error(f'Unknown player cancel mode {cancel_mode!r}')
            item = ListItem()
        item.setContentLookup(False)  # we don't need HEAD
        fflog(f'[PLAYER] CANCEL, mode={cancel_mode.name}, {ffitem=}, path={item.getPath()!r}')
        if ffitem:
            fflog(f'[PLAYER] CANCEL, {ffitem.getPath()=}')
        state.multi_set(module='player', values=(
            ('playing.empty', True),
            ('playing.run', False),
            ('cancel.mode', cancel_mode.value),
            ('state', 'cancel'),
        ))
        setResolvedUrl(syshandle, cancel_mode != PlayCancel.FALSE, item)
        stop_playing()
        if cancel_mode == PlayCancel.TT430 and const.player.refresh_on_cancel_resume:
            control.refresh()

    except Exception:
        fflog_exc()


@overload
def play(*, source: Source) -> None: ...

@overload
def play(*, ffitem: FFItem, url: str) -> None: ...

def play(*, source: Optional[Source] = None, ffitem: Optional[FFItem] = None, url: Optional[str] = None) -> None:
    """Resolve and start a video play."""

    if source is None:
        if not url:
            return cancel(ffitem)
        if ffitem is None or url is None:
            raise ValueError(f'Use `source` or (`ffitem` and `url`): got nothing')
        source = Source(url=url, provider='', hosting='', ffitem=ffitem)
    elif ffitem is not None or url is not None:
        raise ValueError(f'Use `source` or (`ffitem` and `url`) not both')
    ffitem = source.ffitem
    url = source.url

    fflog(f'[PLAYER] {url=}, ref={ffitem.ref:a}, {ffitem=}, ffid={ffitem.ffid}', stack_depth=2)
    if not url or url == 'empty':
        return cancel(ffitem)
    try:
        fflog(f'[PLAYER] {url=}')
        item = ffitem.clone()
        vtag = ffitem.vtag

        imdb = vtag.getUniqueID('imdb') or ''
        tmdb = int(vtag.getUniqueID('tmdb') or 0)
        ids = VideoIds(tmdb=tmdb, imdb=imdb).ids()

        if const.player.set_dbid and (kodi_dbid := video_db.get_kodi_dbid(ffitem.ref)):
            vtag.setDbId(kodi_dbid)  # Kodi DBID
        elif const.core.media_watched_mode is not MediaWatchedMode.FAKE_DBID and ffitem.ffid not in VideoIds.KODI:
            vtag.setDbId(0)  # Reset Kodi DBID, seems it does NOT work

        # --- URL prefixes, pleas, don't use them ---
        play_mode = '...'
        if ia := url.startswith('ia://'):
            url = url[5:]  # remove 'ia://` prefix
        elif ia := (url.startswith('isa+') and '://' in url):
            url = url[4:]  # remove 'isa+ prefix
        elif ia := (url.startswith('direct+') and '://' in url):
            url = url[7:]  # remove 'direct+ prefix
        # --- play modes ---
        else:
            play_mode = source.attr.play
            if play_mode == 'isa':
                ia = True
            elif play_mode == 'direct':
                ia = False
            else:  # auto
                ia = settings.getBool('isa.enabled') and source.is_m3u8()

        fflog(f'Play mode {play_mode!r}: ISA = {ia}')
        if ia:
            import inputstreamhelper
            from lib import kodi

            if '.mpd' in url:
                protocol = 'mpd'
                mimetype = 'application/dash+xml'
            else:
                protocol = 'hls'
                mimetype = 'application/x-mpegURL'

            is_helper = inputstreamhelper.Helper(protocol)
            if not is_helper.check_inputstream():
                return cancel(ffitem)

            listitem = item
            listitem.setProperty('inputstream', is_helper.inputstream_addon)
            if kodi.version < 21:
                listitem.setProperty('inputstream.adaptive.manifest_type', protocol)
            listitem.setMimeType(mimetype)
            listitem.setContentLookup(False)
            if '|' in url:
                url, strhdr = url.split('|')
                listitem.setProperty('inputstream.adaptive.stream_headers', strhdr)
                if kodi.version > 19:
                    listitem.setProperty('inputstream.adaptive.manifest_headers', strhdr)
                listitem.setPath(url)

        if url.startswith('DRM'):
            item = get_drm_item(url, item=item)
            if not item:
                fflog('[DRM] could NOT resolve item')
        else:
            item.setPath(url)
            item.setContentLookup(const.player.head_lookup)
        if item is None:
            return cancel(ffitem)

        # item.setInfo(type="video", infoLabels=control.metadataClean(meta))
        fflog(f'setResolvedUrl(url={url!r})')

        state.multi_set(module='player', values=(
            ('media.ref', ffitem.ref),
            ('media.imdb', imdb),
            ('media.tmdb', tmdb),
            ('media.season', ffitem.season),
            ('media.episode', ffitem.episode),
            ('media.ffid', ffitem.ffid),
            ('media.real_type', ffitem.ref.real_type),
            ('media.duration', ffitem.vtag.getDuration()),
            ('media.url', ffitem.getPath() or fallback_path()),
            ('playing.empty', False),
            ('playing.run', True),
            ('cancel_mode', None),
            ('state', 'play'),
        ))
        control.window().setProperty("script.trakt.ids", json.dumps(ids))
        setResolvedUrl(syshandle, True, item)
        # close_busy_dialog()

    except Exception:
        fflog_exc()


def get_drm_item(url: str, *, item: Optional[FFItem] = None) -> Optional[FFItem]:
    """
    DRM support by Lantash.

    InputStream old properties – deprecated (Kodi 18-22).
    See: https://github.com/xbmc/inputstream.adaptive/wiki/Integration-DRM
    """
    import inputstreamhelper
    from lib import kodi
    stream_data = url.split('|')[-1]
    stream_data = literal_eval(stream_data)

    is_helper = inputstreamhelper.Helper(stream_data["protocol"])
    if not is_helper.check_inputstream():
        return None

    if item is None:
        item = FFItem(path=stream_data['manifest'], offscreen=True)
    else:
        item.setPath(stream_data['manifest'])
        item.vtag.setPath(stream_data['manifest'])
    item.setContentLookup(False)

    item.setProperty('inputstream', is_helper.inputstream_addon)
    item.setMimeType(f'{stream_data["mimetype"]}')
    if kodi.version < 21:
        item.setProperty('inputstream.adaptive.manifest_type', stream_data['protocol'])
    if kodi.version <= 21:
        item.setProperty('inputstream.adaptive.license_type', stream_data['licence_type'])
        if stream_data.get('licence_url'):
            license_config = {'license_server_url': stream_data['licence_url'],
                              'headers': stream_data['licence_header'],
                              'post_data': stream_data['post_data'],
                              'response_data': stream_data['response_data']
                              }
            item.setProperty('inputstream.adaptive.license_key', '|'.join(license_config.values()))
    if kodi.version >= 22:
        drm_configs = {
            "com.widevine.alpha": {
                "license": {
                    "server_url": stream_data['licence_url'],
                    "req_headers": stream_data['licence_header'],
                }
            }
        }
        item.setProperty('inputstream.adaptive.drm', json.dumps(drm_configs))
    item.setProperty('IsPlayable', 'true')
    return item
