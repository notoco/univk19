
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time as dt_time
from pathlib import Path
from datetime import date as dt_date
from random import randint
from typing import Optional, Union, Any, Tuple, List, Dict, Set, Iterator, Iterable, Sequence, Mapping, Callable
from typing_extensions import Literal, cast
from attrs import asdict

from ..api.trakt import TraktApi, TraktCredentials, JsonData, JsonResult, DialogId, TraktIds
from ..api.trakt import ScrobbleAction, WatchContentType, Activities, PlayContentType, Ids, ExtendedInfo, TraktUserProfile

from . import apis
from ..defs import MediaType, MediaRef, MediaProgress, MediaProgressItem, Pagina
from .settings import settings
from .item import FFItem, FFItemDict
from .db import state
from .db.playback import (
    MediaPlayInfo,
    get_playback, get_playback_item, update_track_watched_item,
    update_track_playback, update_track_watched_movies, update_track_watched_episodes,
    remove_all_track_watched_items,
)
from .calendar import utc_timestamp, fromisoformat
from .control import dataPath as DATA_PATH
from .tmdb import Tmdb, tmdb
from .control import max_thread_workers
from ..indexers.defs import VideoIds
from ..windows.site_auth import SiteAuthWindow
from ..service.client import service_client
from .log_utils import fflog, fflog_exc
from .debug import logtime
from ..kolang import L
from const import const


def item_watched_at(item: JsonData) -> Optional[int]:
    watched_at: Optional[str] = item.get('last_watched_at')
    return int(utc_timestamp(watched_at)) if watched_at else None


def item_paused_at(item: JsonData) -> Optional[int]:
    paused_at: Optional[str] = item.get('paused_at')
    return int(utc_timestamp(paused_at)) if paused_at else None


def filter_ids(ids: Mapping[str, Union[int, str]]) -> TraktIds:
    allowed = {'tmdb', 'imdb', 'trakt', 'tvdb', 'slug'}
    return cast(TraktIds, {k: v for k, v in ids.items() if k in allowed})


class Trakt(TraktApi):
    """Trakt.tv API with FF integration."""

    def __init__(self, tmdb: Tmdb) -> None:
        super().__init__()
        #: Tmdb api.
        self.tmdb: Tmdb = tmdb
        #: Trakt auth progreass dialog.
        self.progress_dialog: Optional[SiteAuthWindow] = None
        #: Path to generated auth QR-Code.
        self.auth_qrcode_path: Optional[Path] = None
        # restore trakt acrivites' timestamps
        self.activities = Activities(state.get('sync.activities', module='trakt') or {}, {})

    def credentials(self) -> TraktCredentials:
        """Return current credencials."""
        client = const.dev.trakt.client or settings.getString("trakt.client_key") or apis.trakt_API
        secret = const.dev.trakt.secret or settings.getString("trakt.secret_key") or apis.trakt_secret
        access_token = settings.getString('trakt.token')
        refresh_token = settings.getString('trakt.refresh')
        # tmdb_api_key = const.dev.tmdb.api_key or apis.tmdb_API
        # user = self._settings_manager.getString('trakt.user')
        return TraktCredentials(client=client, secret=secret, access_token=access_token, refresh_token=refresh_token)
        # tmdb_api_key=tmdb_api_key)

    def set_access_token(self, access: JsonData) -> TraktCredentials:
        """Save access token into settings and return new credentials."""
        settings.setString('trakt.token', access['access_token'])
        settings.setString('trakt.refresh', access['refresh_token'])
        if profile := self.user_profile():
            # Check id new user differs from old one (name in profile or name in settings).
            if (((old_profile := state.get('profile', module='trakt', cls=TraktUserProfile)) and old_profile.id and old_profile.id != profile.id)
                    or ((old_user := settings.getString('trakt.user')) and old_user != profile.id)):
                # New user, clear all stored trakt infoa and set new user in the settings.
                state.delete_all(module='trakt')
                remove_all_track_watched_items()
            # Store actual profile.
            settings.setString('trakt.user', profile.id)
            state.set('profile', asdict(profile), module='trakt')
        else:
            settings.setString('trakt.user', '')
            state.delete('profile', module='trakt')
        return self.credentials()

    def unauth(self) -> bool:
        """Drop device authentication."""
        ok = self.revoke_session()
        settings.setString('trakt.token', '')
        settings.setString('trakt.refresh', '')
        return ok

    def remove_access_token(self) -> None:
        """Remove access token from settings."""
        settings.setString('trakt.token', '')
        settings.setString('trakt.refresh', '')

    def dialog_create(self, user_code: str, verification_url: str) -> DialogId:
        """Create GUI dialog."""
        from urllib.parse import urlparse, urlunparse
        import segno
        if user_code not in verification_url:
            u = urlparse(verification_url)
            verification_url = urlunparse(u._replace(path=f'{u.path}/{user_code}'))
        if user_code.isalnum():
            code_hash = user_code
        else:
            code_hash = f'{randint(0, 0xffff_ffff):08x}'
        icon = Path(DATA_PATH) / f'tmp/trakt-auth-qrcode.{code_hash}.png'
        icon.parent.mkdir(parents=True, exist_ok=True)
        fflog(f'[TRAKT] Auth: enter {user_code!r} on site {verification_url}')
        qrcode = segno.make(verification_url)
        qrcode.save(str(icon), scale=const.trakt.auth.qrcode.size)
        self.auth_qrcode_path = icon
        self.progress_dialog = SiteAuthWindow(code=user_code, url=verification_url, icon=icon, modal=False,
                                              title=L(30117, '[B]Authorize Trakt[/B]'))
        self.progress_dialog.doModal()  # this dialog is modeless (!)

    def dialog_close(self, dialog: DialogId) -> None:
        """Close GUI dialog."""
        if self.auth_qrcode_path is not None:
            self.auth_qrcode_path.unlink(missing_ok=True)
            self.auth_qrcode_path = None
        if self.progress_dialog is not None:
            self.progress_dialog.destroy()
            self.progress_dialog = None  # works like "del X"

    def dialog_cancel(self, dialog: DialogId) -> None:
        """Cancel GUI dialog. Debug only."""
        if self.progress_dialog is not None:
            self.progress_dialog.close()

    def dialog_is_canceled(self, dialog: DialogId) -> bool:
        """Return True if GUI dialog is canceled."""
        if self.progress_dialog is not None:
            return self.progress_dialog.dialog_is_canceled()
        return False

    def dialog_update_progress(self, dialog: DialogId, progress: float) -> None:
        """Update GUI dialog progress-bar."""
        fflog(f'[TRAKT] auth {progress:5.1f}')
        if self.progress_dialog is not None:
            self.progress_dialog.update(int(progress))

    def update_media_play_info(self,
                               *items_list: Sequence[MediaPlayInfo],
                               info: Optional[FFItemDict] = None,
                               meta_updated_at: Optional[Union[int, dt_date]] = None,
                               ) -> Iterable[MediaPlayInfo]:
        """Update media playback/watched with FFItem (TMDB) info."""
        if info:
            now = int(utc_timestamp(meta_updated_at))
            for items in items_list:
                for item in items:
                    iti = info.get(item.ref)
                    if iti:
                        def id_int(name: Literal['trakt', 'tmdb', 'tvdb']) -> Optional[int]:
                            v = vtag.getUniqueID(name)
                            return int(v) if v else None
                        vtag = iti.vtag
                        if (duration := iti.duration):
                            item.duration = duration
                        if not item.tmdb:
                            item.tmdb = id_int('tmdb')
                        if not item.imdb:
                            item.imdb = vtag.getUniqueID('imdb') or None
                        if not item.trakt:
                            item.trakt = id_int('trakt')
                        if not item.tvdb:
                            item.tvdb = id_int('tvdb')
                        if not item.ffid:
                            item.ffid = iti.ffid or VideoIds(tmdb=item.tmdb, imdb=item.imdb, trakt=item.trakt).ffid
                        # if not item.slug:
                        #     item.slug = vtag.getUniqueID('slug') or None
                        if not item.aired_at:
                            item.aired_at = iti.date_timestamp
                        item.meta_updated_at = now
        return (it for items in items_list for it in items)

    def get_sync_progress(self, *, extended: ExtendedInfo = 'full', type: Optional[PlayContentType] = None) -> Sequence[MediaPlayInfo]:
        """Get sync data from trakt.tv."""
        def parse(items: Sequence[JsonData]) -> Iterator[MediaPlayInfo]:
            for it in items:
                progress = it['progress']
                paused_at = item_paused_at(it) or 0
                playback_id = it['id']
                if 'movie' in it:
                    mv = it['movie']
                    ids = mv['ids']
                    ref = MediaRef.movie(VideoIds.from_ids(ids).ffid)
                    duration = 60 * runtime if (runtime := mv.get('runtime')) else None
                    yield MediaPlayInfo(ref=ref, progress=progress, paused_at=paused_at, duration=duration,
                                        **filter_ids(ids), playback_id=playback_id)
                if 'episode' in it:
                    ep = it['episode']
                    ids = ep['ids']
                    tv_ids = it['show']['ids']
                    ref = MediaRef.tvshow(VideoIds.from_ids(tv_ids).ffid, ep['season'], ep['number'])
                    duration = 60 * runtime if (runtime := ep.get('runtime')) else None
                    yield MediaPlayInfo(ref=ref, progress=progress, paused_at=paused_at, duration=duration,
                                        tv_slug=tv_ids.get('slug'), **filter_ids(ids), playback_id=playback_id)

        data = self.get_playblack_list(extended=extended, type=type)
        # with open('/tmp/trakt_sync_playback.json', 'w') as f:  json.dump(data, f, indent=2)  # XXX XXX XXX
        if isinstance(data, Sequence):
            return tuple(parse(data))
        return ()

    def get_sync_watched_movies(self, *, extended: ExtendedInfo = '') -> Sequence[MediaPlayInfo]:
        """Get sync data from trakt.tv."""

        def parse(items: Sequence[JsonData]) -> Iterator[MediaPlayInfo]:
            for it in items:
                last_watched_at = item_watched_at(it) or 0
                mv = it['movie']
                ids = mv['ids']
                ref = MediaRef.movie(VideoIds.from_ids(ids).ffid)
                duration = 60 * runtime if (runtime := mv.get('runtime')) else None
                yield MediaPlayInfo(ref=ref, play_count=it['plays'], last_watched_at=last_watched_at, duration=duration,
                                    **filter_ids(ids), meta_updated_at=int(utc_timestamp(it['last_updated_at'])))

        data = self.get_watched_list('movies', extended=extended)
        # with open('/tmp/trakt_sync_movies.json', 'w') as f:  json.dump(data, f, indent=2)  # XXX XXX XXX
        if isinstance(data, Sequence):
            return tuple(parse(data))
        return ()

    def get_sync_watched_shows(self, *, extended: ExtendedInfo = '', parents: bool = False) -> Sequence[MediaPlayInfo]:
        """Get sync data from trakt.tv."""

        def parse(items: Sequence[JsonData]) -> Iterator[MediaPlayInfo]:
            for it in items:
                tv_ids = it['show']['ids']
                tv_slug = tv_ids.get('slug')
                tv_ref = MediaRef.tvshow(VideoIds.from_ids(tv_ids).ffid)
                for sz in it.get('seasons', ()):
                    sz_ref = tv_ref.with_season(sz['number'])
                    for ep in sz.get('episodes', ()):
                        ref = sz_ref.with_episode(ep['number'])
                        duration = 60 * runtime if (runtime := ep.get('runtime')) else None
                        # there is no episode ids in Trakt API
                        yield MediaPlayInfo(ref=ref, play_count=ep['plays'], tv_slug=tv_slug, duration=duration,
                                            last_watched_at=item_watched_at(ep) or 0,
                                            meta_updated_at=int(utc_timestamp(it['last_updated_at'])))
                    if parents:
                        yield MediaPlayInfo(ref=sz_ref, tv_slug=tv_slug)
                if parents:
                    yield MediaPlayInfo(ref=tv_ref, tv_slug=tv_slug, **filter_ids(tv_ids),
                                        last_watched_at=item_watched_at(it))

        data = self.get_watched_list('shows', extended=extended)
        # with open('/tmp/trakt_sync_shows.json', 'w') as f:  json.dump(data, f, indent=2)  # XXX XXX XXX
        if isinstance(data, Sequence):
            return tuple(parse(data))
        return ()

    def activities_changed(self, activities: Activities, *, timestamp: Optional[Union[datetime, float]] = None) -> bool:
        """Sync playback and watched. NOTE: it's called under lock."""

        def all_items(items: Iterable[Optional[FFItem]], *, normalized: bool = True) -> Iterator[Tuple[MediaRef, FFItem]]:
            for it in items:
                if it:
                    ref = it.ref
                    yield ref, it
                    if not normalized:
                        if it.ffid and (real_type := ref.real_type) != ref.type:
                            yield MediaRef(real_type, it.ffid), it
                    if it.children_items:
                        yield from all_items(it.children_items, normalized=normalized)

        last = activities.last
        fflog(f'Trakt activies changed ({last=}): {activities.changed}')
        if last:
            settings.setString('trakt.last_activity', str(last))
        # prepare getting data from trakt.tv
        todo = []
        if activities.playback:
            todo.append(self.get_sync_progress)
        if activities.watched_movies:
            todo.append(self.get_sync_watched_movies)
        if activities.watched_shows:
            todo.append(self.get_sync_watched_shows)
        if not todo:        # nothing to do
            return False
        print(f'act: {[t.__qualname__ if t else None for t in todo]}')
        if len(todo) == 1:  # only one thing to do
            result = [todo[0]()]
        else:               # many things to do
            with ThreadPoolExecutor(max_thread_workers()) as ex:
                def call(f):
                    try:
                        return f()
                    except Exception:
                        fflog_exc()
                        raise

                futures = [ex.submit(call, func) for func in todo]
            result = [fut.result() for fut in futures]

        playback: Sequence[MediaPlayInfo] = result.pop(0) if activities.playback else ()
        movies: Sequence[MediaPlayInfo] = result.pop(0) if activities.watched_movies else ()
        shows: Sequence[MediaPlayInfo] = result.pop(0) if activities.watched_shows else ()

        # get tmdb media info by theirs refs only for last updated items
        # import here to avoid circular imports
        # from .info import ffinfo
        # now = utc_timestamp()
        # activities.playback
        # refs = {p.ref for pack, last_updated_at in zip(_
        #         for p in chain(playback, movies, shows)}

        # info: FFItemDict = {it.ref: it for it in ffinfo.get_items(tuple(refs), progress=ffinfo.Progress.NO)
        #                     if it and (it.meta_updated_at or now)}
        info: Optional[FFItemDict] = None

        # merge progress and watched lists
        def update_playback(it: MediaPlayInfo) -> MediaPlayInfo:
            if pb := playback_dict.get(it.ref):
                pb.play_count = it.play_count
                pb.last_watched_at = it.last_watched_at
                # pb.meta_updated_at = max(pb.meta_updated_at, it.meta_updated_at)
                return pb
            return it

        playback_dict: Dict[MediaRef, MediaPlayInfo] = {it.ref: it for it in playback}
        movies = tuple(update_playback(it) for it in movies)
        shows = tuple(update_playback(it) for it in shows)
        playback = tuple(playback_dict.values())

        # update info
        self.update_media_play_info(playback, movies, shows, info=info)

        # create udpates (threads can not help here)
        changed = False
        if playback:
            changed |= update_track_playback(playback, info=info)
        if movies:
            changed |= update_track_watched_movies(movies, info=info)
        if shows:
            changed |= update_track_watched_episodes(shows, info=info)

        state.set('sync.activities', self.activities.data, module='trakt')
        # if changed:
        #     timestamp = utc_timestamp(timestamp)
        #     state.set('timestamp', timestamp, module='trakt')

        return changed

    # def history_sync(self) -> None:
    #     """Get and sync history with local DB."""
    #     rows: List[TraktHistoryItem] = [
    #         TraktHistoryItem(*row_from_item(item, ('action', 'watched_at')))
    #         for item in self.get_playblack_list()]
    #     state.replace_playback(rows)

    @logtime
    def sync_now(self, *, timestamp: Optional[Union[datetime, float]] = None) -> bool:
        """Sync all trakt.tv stuff. Returns True if DB is changed."""
        timestamp = utc_timestamp(timestamp)
        act = self.get_last_activities(timestamp=timestamp)
        state.set('sync.timestamp', timestamp, module='trakt')
        return act.db_changed

    @logtime
    def sync(self, *, timestamp: Optional[Union[datetime, float]] = None) -> Optional[bool]:
        """
        Calls remote trakt sync and waits for finish.
        Returns True on changes, False if nothing changed, None if falied.
        """
        return service_client.trakt_sync()

    def sync_start(self) -> None:
        """Start trakt.tv syncing (in background)."""
        state.add_job('service', 'trakt.sync', sender='plugin.trakt')

    def updated(self) -> float:
        """Trakt DB is updated, sets and returns timestamp."""
        now = utc_timestamp()
        state.set('db.timestamp', now, module='trakt')
        return now

    def media_in_progress(self,
                          type: MediaType,
                          *,
                          page: int = 1,
                          limit: Optional[int] = None,
                          sort: bool = False,
                          ) -> Sequence[FFItem]:
        """Return list of media data (old format)."""
        if limit:
            size = limit
        elif type == 'movie':
            size = const.indexer.trakt.progress.movies_page_size
        elif type == 'episode':
            size = const.indexer.trakt.progress.episodes_page_size
        else:
            size = const.indexer.trakt.progress.page_size
        items = (pb.as_item() for pb in get_playback(type, in_progress=True, sort=sort).values())
        if size:
            return Pagina(items, page=page, limit=size)
        return tuple(items)

    @logtime
    def progress_items(self, user: str = 'me', *, today: Optional[dt_date] = None, sort: bool = True) -> List[FFItem]:
        from .info import ffinfo  # local import to avoid import dependencies

        def make_watched(it: FFItem, wit: FFItem) -> FFItem:
            tv = it.ref.ffid
            watched_tree = {wsz['number']: {wep['number']: MediaProgressItem(MediaRef.tvshow(tv, wsz['number'], wep['number']),
                                                                             play_count=wep['plays'],
                                                                             last_watched_at=fromisoformat(wep['last_watched_at']))
                                            for wep in wsz.get('episodes', ()) if wep['plays']}
                            for wsz in (wit.source_data or {}).get('seasons', {})}
            bar_tree = [[watched_tree.get(ep.season, {}).get(ep.episode, MediaProgressItem(MediaRef.tvshow(tv, ep.season, ep.episode)))
                         for ep in sz.episode_iter() if ep.aired_before(today)]
                        for sz in it.season_iter() if sz.aired_before(today)]
            bar = [ep for sz in bar_tree for ep in sz]
            breakpoint()
            lst, nxt = ffinfo.find_last_next_episodes(it, watched_tree, today=today)
            pc = 100 * sum(bool(e) for e in bar) / (len(bar) or 1)
            it.progress = MediaProgress(ref=it.ref, next_episode=nxt, last_episode=lst, progress=pc, bar=bar)
            return it

        if today is None:
            today = dt_date.today()
        watched = self.user_generic_list('watched', media_type='show', sort=sort)
        items = ffinfo.get_items(watched, tv_episodes=True)
        return [make_watched(it, wt) if it else wt for it, wt in zip(items, watched)]

    def scrobble_ref(self,
                     action: ScrobbleAction,
                     ref: MediaRef,
                     progress: float = 0.0,
                     *,
                     db_save: bool = True,
                     ) -> bool:
        """Scrobble what a user is watching in a media center and update DB."""
        if self._scrobble_ref(action=action, ref=ref, progress=progress):
            if not db_save:
                return True
            media = get_playback_item(ref)
            if not media:
                from .info import ffinfo  # local import to avoid import dependencies
                item = ffinfo.find_item(ref)
                if not item:
                    return False
                media = MediaPlayInfo.from_ffitem(item)
            media.progress = progress
            update_track_watched_item(media)
            return True
        return False

    def scrobble_pause_ref(self, ref: MediaRef, progress: float = 0.0, *, db_save: bool = True) -> bool:
        """Pause watching in a media center and update DB."""
        return self.scrobble_ref('start', ref=ref, progress=progress, db_save=db_save)

    def scrobble_stop_ref(self, ref: MediaRef, progress: float = 0.0, *, db_save: bool = True) -> bool:
        """Stop watching in a media center and update DB."""
        return self.scrobble_ref('start', ref=ref, progress=progress, db_save=db_save)

    def scrobble_start_ref(self, ref: MediaRef, progress: float = 0.0, *, db_save: bool = True) -> bool:
        """Start watching in a media center and update DB."""
        return self.scrobble_ref('start', ref=ref, progress=progress, db_save=db_save)

    def add_history_ref(self, ref: MediaRef, *, db_save: bool = True) -> bool:
        """Add history item, increments watched play_count and write it to DB directly."""
        if super().add_history_ref(ref):
            if not db_save:
                return True
            media = get_playback_item(ref)
            if not media:
                from .info import ffinfo  # local import to avoid import dependencies
                item = ffinfo.find_item(ref)
                if not item:
                    return False
                media = MediaPlayInfo.from_ffitem(item)
            media.play_count = (media.play_count or 0) + 1
            update_track_watched_item(media)
            return True
        return False

    def remove_history_ref(self, ref: MediaRef, *, db_save: bool = True) -> bool:
        """Remove history item, reset watched play_count and write it to DB directly."""
        if super().remove_history_ref(ref):
            if not db_save:
                return True
            media = get_playback_item(ref)
            if media:
                media.progress = None
                media.playback_id = None
                media.play_count = 0
                media.last_watched_at = None
                update_track_watched_item(media)
                return True
        return False

    def remove_playback_ref(self, ref: MediaRef, *, db_save: bool = True) -> bool:
        """Remove a playback item (progress) by media ref."""
        if (media_type := ref.real_type) not in ('movie', 'episode'):
            return False
        media = get_playback_item(ref)
        if media is None or not media.playback_id:
            for media in self.get_sync_progress(type=media_type, extended=''):
                if media.ref == ref:
                    break
            else:
                return False
        if not media.playback_id:
            return False
        if not self.remove_playback(media.playback_id):
            return False
        if db_save:
            media.progress = None
            media.playback_id = None
            update_track_watched_item(media)
        return True


#: Global Trakt.tv support.
trakt = Trakt(tmdb=tmdb)


# --- DEBUG & TESTS ---

def make_console_trakt() -> Callable[[], None]:
    import sty

    the_code: str = ''
    canceled: bool = False
    code_color: str = f'{sty.fg.red}{sty.ef.bold}'

    def dialog_create(self, user_code: str, verification_url: str) -> DialogId:
        """Create GUI dialog."""
        from urllib.parse import urlparse, urlunparse
        import segno
        import sys
        if user_code not in verification_url:
            u = urlparse(verification_url)
            verification_url = urlunparse(u._replace(path=f'{u.path}/{user_code}'))
        print(f'[TRAKT] Auth: enter {code_color}{user_code!r}{sty.rs.all} on site {sty.ef.bold}{verification_url}{sty.rs.all}')
        qrcode = segno.make(verification_url)
        qrcode.terminal(out=sys.stderr, compact=True)
        nonlocal canceled, the_code
        canceled = False
        the_code = user_code
        return 1

    def dialog_close(self, dialog: DialogId) -> None:
        """Close GUI dialog."""

    def dialog_cancel(self, dialog: DialogId = None) -> None:
        """Cancel GUI dialog. Debug only."""
        nonlocal canceled
        canceled = True

    def dialog_is_canceled(self, dialog: DialogId) -> bool:
        """Return True if GUI dialog is canceled."""
        return canceled

    def dialog_update_progress(self, dialog: DialogId, progress: float) -> None:
        """Update GUI dialog progress-bar."""
        print(f'[TRAKT] auth {code_color}{the_code}{sty.rs.all} : {progress:5.1f}')

    Trakt.dialog_create = dialog_create
    Trakt.dialog_close = dialog_close
    Trakt.dialog_cancel = dialog_cancel
    Trakt.dialog_is_canceled = dialog_is_canceled
    Trakt.dialog_update_progress = dialog_update_progress

    def cancel() -> None:
        """Cancel GUI dialog. Debug only."""
        nonlocal canceled
        canceled = True

    return cancel


if __name__ == '__main__':
    import re
    import sys
    from itertools import islice
    from pprint import pprint
    from typing_extensions import get_args as get_typing_args
    from datetime import timezone
    import json
    import sty
    from .cmdline import DebugArgumentParser, parse_ref
    from ..api.trakt import SortType, MainMediaType, HistoryContentType

    def batched(iterable: str, n: int) -> Iterator[str]:  # batched('ABCDEFG', 3) --> ABC DEF G
        if n < 1:
            raise ValueError('n must be at least one')
        it = iter(iterable)
        while batch := ''.join(islice(it, n)):
            yield batch

    def bar(flat: Optional[str]) -> str:
        m = {
            '00': ' ',
            '01': '▐',
            '10': '▌',
            '11': '█',
            '0': ' ',
            '1': '▌',
        }
        bar = ''.join(m[ab] for ab in batched(flat or '', 2))
        if flat and len(flat) % 2:
            bar = f'{bar[:-1]}{sty.rs.bg}{bar[-1:]}'
        return f'{sty.fg.da_red}{sty.bg(235)}{bar}{sty.rs.all}'

    def print_plays(items: Iterable[MediaPlayInfo], *, title: str = '', flt: Optional[int] = None) -> None:
        if title:
            print(f'---[ {title} ] ---')
        for it in items:
            if not flt or it.ref.ffid == flt:
                prog = '----' if it.progress is None else f'{it.progress:3.0f}%'
                plays = '?' if it.play_count is None else str(it.play_count)
                slug = it.tv_slug or it.slug or '-'
                print(f' - {it.ref:16a} {prog} x{plays} {slug:<30.30} {bar(it.progress_map)}')

    def jprint(data: JsonResult) -> None:
        print(json.dumps(data, indent=2))

    def raw_user_list_items(list_id: Union[int, str],
                            user: str = 'me',
                            *,
                            page: Optional[int] = None,
                            media_type: Optional[MainMediaType] = None,
                            sort: Optional[SortType] = None,  # sort by X-Sort-By and X-Sort-How, has no sense if `page` is used
                            ) -> Sequence[JsonData]:
        """Return raw JSON of user (private too) lists."""
        ctype: str = trakt._ref2type.get(media_type, '')  # type: ignore
        extended = 'full' if sort is not None else None  # more datails are needed for sorting
        data, pages = trakt.get_with_pages(f'users/{user}/lists/{list_id}/items/{ctype}', page=page, extended=extended)
        if isinstance(data, Sequence):
            return trakt._sort_items_with_pages(data, sort=sort, pages=pages)
        return ()

    p = DebugArgumentParser(dest='cmd')
    with p.with_subparser('status') as pp:
        pass
    with p.with_subparser('sync'):
        pass
    with p.with_subparser('activities'):
        pass
    with p.with_subparser('watching') as pp:
        pass
    with p.with_subparser('watched') as pp:
        pp.add_argument('type', choices=('all', 'progress', 'history', 'movies', 'shows'))
        pp.add_argument('--filter', '-f', type=int, help='filter by movie/show id')
    with p.with_subparser('history') as pp:
        pp.add_argument('type', choices=get_typing_args(HistoryContentType))
        # pp.add_argument('--filter', '-f', type=int, help='filter by movie/show id')
    with p.with_subparser('list') as pp:
        pp.add_argument('list', choices=('likes', 'watchlist', 'favorites', 'history', 'watched'))
        pp.add_argument('type', nargs='?', choices=('movie', 'show', 'season', 'episode'))
        pp.add_argument('-s', '--sort', choices=get_typing_args(SortType), help='sort')
        # pp.add_argument('-f', '--filter', type=int, help='filter by movie/show id')
    with p.with_subparser('mine') as pp:
        pp.add_argument('list', nargs='?', help='own list name')
        pp.add_argument('type', nargs='?', choices=('movie', 'show', 'season', 'episode'))
        pp.add_argument('-s', '--sort', choices=get_typing_args(SortType), help='sort')
        pp.add_argument('-u', '--user', default='me', help='user name [me]')
        pp.add_argument('-L', '--list', dest='print_lists', action='store_true', help='print lists')
        pp.add_argument('-J', '--json', action='store_true', help='print raw JSON')
        pp.add_argument('-a', '--add', type=parse_ref, action='append', help='add to the list')
    with p.with_subparser('db', dest='cmd1') as pp:
        # g.add_argument('type', choices=('all', 'movies', 'shows'))
        with pp.with_subparser('all', aliases=('movies', 'shows')) as ppp:
            ppp.add_argument('-f', '--filter', type=int, help='filter by movie/show id')
        with pp.with_subparser('ref') as ppp:
            ppp.add_argument('ref', type=parse_ref, help='show only one ref')
        with pp.with_subparser('watch') as ppp:
            ppp.add_argument('ref', type=parse_ref, help='media ref: movie/ID, show/ID[/SEASON[/EPISODE]]')
        with pp.with_subparser('unwatch') as ppp:
            ppp.add_argument('ref', type=parse_ref, help='media ref: movie/ID, show/ID[/SEASON[/EPISODE]]')
        with pp.with_subparser('fix') as ppp:
            ppp.add_argument('ref', type=parse_ref, nargs='+', help='show and seasons refs fo fix: show/ID[/SEASON]')
    with p.with_subparser('profile'):
        pass
    with p.with_subparser('lookup') as pp:
        pp.add_argument('service', help='service to lookup id (tmdb, etc.)')
        pp.add_argument('id', help='id to lookup')
        pp.add_argument('type', nargs='?', help='media type (movie, show, episode, person)')
    with p.with_subparser('scrobble') as pp:
        pp.add_argument('action', choices=(*get_typing_args(ScrobbleAction), 'remove'), help='scrobble action')
        # pp.add_argument('type', choices=get_typing_args(PlayContentType), help='media type')
        pp.add_argument('ref', type=parse_ref, help='media ref: movie/ID, show/ID/SEASON/EPISODE')
        pp.add_argument('progress', nargs='?', type=float, help='scrobble action')
    with p.with_subparser('playback') as pp:
        pass
    args = p.parse_args()
    from .info import ffinfo

    ref: MediaRef
    if args.cmd == 'sync':
        trakt.sync_now()
    elif args.cmd == 'activities':
        trakt.get_last_activities()
    elif args.cmd == 'watching':
        data = trakt.get_watching()
        if data:
            jprint(data)
            start = fromisoformat(data['started_at']).timestamp()
            duration = fromisoformat(data['expires_at']).timestamp() - start
            current = datetime.now(tz=timezone.utc).timestamp() - start
            print(f'Progress: {100 * current / duration:.1f}%')
    elif args.cmd == 'watched':
        if args.type in ('all', 'progress'):
            print_plays(trakt.get_sync_progress(), title='progress', flt=args.filter)
        if args.type in ('all', 'movies'):
            print_plays(trakt.get_sync_watched_movies(), title='movies', flt=args.filter)
        if args.type in ('all', 'shows'):
            print_plays(trakt.get_sync_watched_shows(), title='shows', flt=args.filter)
    elif args.cmd == 'history':
        jprint(trakt.get_history_list(args.type))
    elif args.cmd == 'list':
        items = trakt.user_generic_list(args.list, media_type=args.type, user='me', sort=args.sort)
        for it in items:
            print(it)
    elif args.cmd == 'mine':
        if args.add:
            trakt.add_to_user_list(args.list, args.add)
        elif args.print_lists:
            for it in trakt.user_lists(user=args.user):
                print(f'- {it.title}')
        elif args.json:
            data = raw_user_list_items(args.list, user=args.user, media_type=args.type, sort=args.sort)
            text = json.dumps(data, indent=2)
            rx = re.compile(r'\s+', flags=re.DOTALL)
            text = re.sub(r'(?<="languages": \[)[^]]*(?=\])', lambda m: rx.sub(' ', m[0]), text, flags=re.DOTALL)
            text = re.sub(r'(?<="available_translations": \[)[^]]*(?=\])', lambda m: rx.sub(' ', m[0]), text, flags=re.DOTALL)
            print(text)
        else:
            for it in trakt.user_list_items(args.list, user=args.user, media_type=args.type, sort=args.sort):
                print(it)
    elif args.cmd == 'db':
        if args.cmd1 == 'all':
            print_plays(get_playback().values(), flt=args.filter)
        elif args.cmd1 == 'movies':
            print_plays(get_playback('movie').values(), flt=args.filter)
        elif args.cmd1 == 'shows':
            print_plays(get_playback('show').values(), flt=args.filter)
        if args.cmd1 == 'ref':
            print_plays([get_playback_item(args.ref)])
        elif args.cmd1 == 'watch':
            ref = args.ref
            m = get_playback_item(ref) or MediaPlayInfo.from_ffitem(ffinfo.find_item(ref))
            m.play_count = 1
            m.progress = None
            update_track_watched_item(m)
        elif args.cmd1 == 'unwatch':
            ref = args.ref
            m = get_playback_item(ref) or MediaPlayInfo.from_ffitem(ffinfo.find_item(ref))
            m.play_count = 0
            m.progress = None
            m.last_watched_at = None
            update_track_watched_item(m)
        elif args.cmd1 == 'fix':
            if all(ref.is_show or ref.is_season for ref in args.ref):
                from .db.playback import get_cursor as get_playblack_cursor, _fix_shows_progress
                with get_playblack_cursor(orm=True) as cur:
                    _fix_shows_progress(cur, args.ref)
            else:
                print(f'{sty.fg.red}ERROR:{sty.rs.all} expected show or season refs')
    elif args.cmd == 'status':
        print_plays(trakt.get_sync_progress(), title='progress')
        print_plays(trakt.get_sync_watched_movies(), title='movies')
        print_plays(trakt.get_sync_watched_shows(), title='shows')
    elif args.cmd == 'profile':
        if profile := trakt.user_profile():
            if (((old_profile := state.get('profile', module='trakt', cls=TraktUserProfile)) and old_profile.id and old_profile.id != profile.id)
                    or ((old_user := settings.getString('trakt.user')) and old_user != profile.id)):
                state.delete_all(module='trakt')
                settings.setString('trakt.user', profile.id)
            state.set('profile', asdict(profile), module='trakt')
        else:
            settings.setString('trakt.user', '')
            state.delete('profile', module='trakt')
    elif args.cmd == 'lookup':
        print(trakt.id_lookup(args.id, service=args.service, type=args.type))
    elif args.cmd == 'scrobble':
        if (ref := args.ref).real_type not in get_typing_args(PlayContentType):
            print('ERROR: `ref` must be movie or episode')
            ok = False
        elif args.action == 'remove':
            ok = trakt.remove_playback_ref(ref)
        else:
            progress = 50 if args.progress is None else args.progress
            ok = trakt.scrobble(args.action, ref.real_type, progress, ids=ref.video_ids.ids())
        print(f'Success: {ok}')
    elif args.cmd == 'playback':
        jprint(trakt.get('sync/playback/'))
    print('---', file=sys.stderr)
    print(f'  (( {trakt._DEBUG_STATS} ))', file=sys.stderr)
    print(f'  (( {ffinfo.tmdb._DEBUG_STATS} ))', file=sys.stderr)
    # print(get_playback_item(MediaRef.movie(968051)))

    # --- FF2 trakt manager ---
    # items = [(control.lang(32516), "/sync/collection")]
    # items += [(control.lang(32517), "/sync/collection/remove")]
    # items += [(control.lang(32518), "/sync/watchlist")]
    # items += [(control.lang(32519), "/sync/watchlist/remove")]
    # items += [(control.lang(32520), "/users/me/lists/%s/items")]
