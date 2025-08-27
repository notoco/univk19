
from __future__ import annotations
from typing import Optional, Union, Any, List, Dict, Iterable, Iterator, Sequence, TYPE_CHECKING
from typing_extensions import TypedDict
import re
import json
from pathlib import Path
from time import monotonic
from datetime import datetime, date as dt_date, time as dt_time
from attrs import define, frozen, field, Factory, asdict
from xbmc import Monitor
from ..defs import MediaRef, VideoIds
from ..ff.calendar import utc_timestamp
from ..ff.url import URL
from ..ff.item import FFItem
from ..ff.threads import Thread
from ..ff.kotools import xsleep
from ..ff.kodidb import video_db
from ..ff.threads import Condition, MAX_TIMESTAMP
# from ..ff.control import plugin_url
from ..ff.kodidb import KodiVideoInfo
from ..ff.db.playback import MediaPlayInfo, get_playback_item, update_track_watched_item
from ..ff.log_utils import fflog, fflog_exc
from .tracking import TrackingAction, TrackingActionType
from const import const

if TYPE_CHECKING:
    from ..ff.types import JsonData
    from ..ff.item import FFItem


def _parse_url(value) -> URL:
    if isinstance(value, str):
        return URL(value)
    return value


def _serialize(inst, field, value):
    if isinstance(value, (URL, Path)):
        return str(value)
    if serialize := getattr(value, '__to_json__', None):
        return serialize()
    return value


class JsonEncoder(json.JSONEncoder):
    def default(self, o):
        if serialize := getattr(o, '__to_json__', None):
            return serialize()
        if isinstance(o, (URL, Path, datetime, dt_date, dt_time)):
            return str(o)
        return super().default(o)


@define
class VolatileFfid:
    """Volatile FFID, defined for single kodi session only."""

    _refs: Dict[int, MediaRef] = Factory(dict)
    _ids: Dict[MediaRef, int] = Factory(dict)
    _generator: Iterator[int] = field(init=False, factory=VideoIds.VOLATILE.__iter__)

    def next_ffid(self) -> int:
        """Get next volatile ffid."""
        try:
            return next(self._generator)
        except StopIteration:
            self._generator = iter(VideoIds.VOLATILE)
        return next(self._generator)

    def register(self, ref: MediaRef) -> int:
        """Register new value."""
        if ffid := self._ids.get(ref):
            return ffid
        ffid = self.next_ffid()
        self._ids[ref] = ffid
        self._refs[ffid] = ref
        return ffid

    def get(self, ffid: int) -> Optional[MediaRef]:
        """Return ref by `ffid` or None if not exists."""
        return self._refs.get(ffid)


@frozen(kw_only=True)
class FolderEntry:
    #: Entry label.
    label: str
    #: Media Reference if any. If not MediaRef('', 0) is used.
    ref: MediaRef = field(factory=lambda: MediaRef('', 0))
    #: TMDB ID or zero.
    tmdb: int = 0
    #: IMDB ID or empty.
    imdb: str = ''
    #: Kodi playback data if any.
    kodi_data: Optional[KodiVideoInfo] = None


@define
class FolderHistoryItem:
    """One item if the folder history."""

    #: Folder URL.
    url: URL = field(converter=_parse_url)
    #: Folder enter UTC timestamp.
    enter_timestamp: float = 0
    #: Folder exit UTC timestamp.
    exit_timestamp: float = 0

    def __to_json__(self) -> JsonData:
        """Serialize object to JSON."""
        return asdict(self, value_serializer=_serialize)

    @classmethod
    def __from_json__(cls, data: 'JsonData') -> FolderHistoryItem:
        """Create object from JSON."""
        return FolderHistoryItem(**data)


@define(kw_only=True)
class TreeFolderInfo:
    """Folder info in plugin tree."""

    url: str
    label: str = ''
    parent: Optional[str] = None


@define(kw_only=True)
class PluginRequestInfo:
    """FF plugin URL enter info (folder, videos, scripts etc.)."""
    #: True, if refresh is detected (reloaded, stop playing, cancel playing, (un)watched set...).
    refresh: bool = False
    #: True, folder is locked (refresh is detected on stop playing).
    locked: bool = False
    #: True, if kodi folder is scaned (tree scan is detected).
    scan: bool = False
    #: True, if kodi folder tree scan is just detected.
    scan_started: bool = False
    #: True, if kodi folder tree scan is just stoped (enter to `scan_url`, folder before scan started)
    scan_finished: bool = False
    #: Keep URL, when scanning is detected (folder before scan started).
    scan_url: URL = field(default=URL(''), converter=_parse_url)
    #: Main media URL (e.g. tvshow).
    media_url: URL = field(default=URL(''), converter=_parse_url)
    #: Last folder info (not video or else).
    folder_url: URL = field(default=URL(''), converter=_parse_url)
    #: Folder history.
    history: List[FolderHistoryItem] = Factory(list)
    #: Current (last) folder content. Set on "exit".
    content: Optional[Sequence[FFItem]] = None
    #: Current (last) fodler kodi DB play info. Set on "exit".
    current_plays: Sequence[KodiVideoInfo] = ()
    #: Folder info in plugin tree folders. [url] -> TreeFolderInfo.
    folder_tree: Dict[str, TreeFolderInfo] = field(factory=dict)
    #: Parent folder info, if any.
    parent_path: List[TreeFolderInfo] = field(factory=list)

    @property
    def url(self) -> URL:
        """Current folder URL (first item from the history)."""
        if not self.history:
            return URL('')
        return self.history[0].url

    def __to_json__(self) -> JsonData:
        """Serialize object to JSON."""
        data = asdict(self, recurse=True, value_serializer=_serialize,
                      # skip `content`, `current_plays` and all private attributes
                      # filter=lambda attr, value: attr.name not in ('current_plays', 'folder_tree'),
                      filter=lambda attr, value: attr.name not in ('content', 'current_plays', 'folder_tree'),
                      )
        return data

    @classmethod
    def __from_json__(cls, data: 'JsonData') -> PluginRequestInfo:
        """Create object from JSON."""
        data = dict(data)
        data['history'] = [FolderHistoryItem.__from_json__(it) for it in data['history']]
        if (content := data.get('content')) is not None:
            data['content'] = [FFItem.__from_json__(it) for it in content]
        data['parent_path'] = [TreeFolderInfo(**parent) for parent in data.get('parent_path') or []]
        return PluginRequestInfo(**data)

    def enter(self, url: Union[URL, str], *, timestamp: Optional[float] = None) -> None:
        """Enter into folder, add new URL."""
        if isinstance(url, str):
            url = URL(url)
        if timestamp is None:
            timestamp = utc_timestamp()
        if self.history and not self.history[0].exit_timestamp:
            self.history[0].exit_timestamp = timestamp
        self.history.insert(0, FolderHistoryItem(url, enter_timestamp=timestamp))
        if len(self.history) > 10:
            self.history = self.history[:10]
        # simple refresh
        try:
            fflog(f'################## refresh? {self.history[0].url in (self.history[1].url, self.scan_url, self.folder_url)}: #{len(self.history)}, {self.history[0].url!r} in {(self.history[1].url, self.scan_url, self.folder_url)}')
        except IndexError:
            fflog(f'################## refresh? ?: #{len(self.history)}, {(self.scan_url, self.folder_url)}')
        self.locked = False
        self.refresh = len(self.history) >= 2 and self.history[0].url in (self.history[1].url, self.scan_url, self.folder_url)
        if self.refresh:
            from xbmc import getInfoLabel
            from ..ff.db import state
            ref = item = None

            # def find_item_by_path() -> Optional[FFItem]:
            #     if (path := getInfoLabel('ListItem.FilenameAndPath')).startswith(plugin_url):
            #         for it in self.content or ():
            #             if it.getPath() == path:
            #                 return it
            #     fflog(f'[SERVICE] CM PATH {path!r} in \n' + '\n'.join(f'    - {it.getPath()!r}' for it in self.content or ()))
            #     return None

            fflog(f"[SERVICE] STATE = {state.get('state', module='player')}")
            # playing is stopping?
            if (st := state.get('state', module='player')) in ('playing', 'played', 'stopping'):
                fflog(f'Refresh {self.history[0].url} in state {st}')
                self.locked = True
            # CM on FFITem, ex. set (un)watched
            # elif (ref := MediaRef.from_slash_string(getInfoLabel('ListItem.UniqueID(ffref)'))) and (item := find_item_by_path()):
            elif ref := MediaRef.from_slash_string(getInfoLabel('ListItem.UniqueID(ffref)')):
                plays = {pb.ref: pb for pb in self.current_plays}
                vi0 = plays.get(ref)
                vi1 = video_db.get_play(ref)
                fi0 = next(iter(item for item in self.content or () if item.ref == ref), None)
                pr0 = fi0 and fi0.progress
                fflog(f'Refresh {self.history[0].url} with ref {ref:a}\n   {pr0=}\n   {vi0=}\n   {vi1=}')
                if vi1 is not None:
                    if no_vi0 := vi0 is None:
                        vi0 = KodiVideoInfo(ref=ref)
                        fflog(f'Restore vi0 for ref {ref:a}\n ~ {vi0=}')
                    # if not current progress... all action (watched, unwatched, reset_progress) reset the progress
                    if not vi1.time_s:
                        cnt0, cnt1 = vi0.play_count or 0, vi1.play_count or 0
                        # increment by one – set as watched
                        if cnt0 + 1 == cnt1 or (no_vi0 and cnt1 > 0):
                            update_playback_db_by_kodi_info(vi1, action='watched')
                        # decrement to zero and now has no watched time – set as unwatched
                        elif (cnt0 > 0 or (pr0 and pr0.play_count > 0)) and not vi1.played_at and cnt1 == 0:
                            update_playback_db_by_kodi_info(vi1, action='unwatched')
                        # remove progress - reset resume point
                        elif (vi0.time_s or (pr0 and pr0.progress)) and cnt0 >= cnt1:
                            update_playback_db_by_kodi_info(vi1, action='reset_progress')
            fflog(f'[SERVICE] CM PATH {ref=}, {item=}')
            fflog(f'  --------->   {self.current_plays}')
                # self.locked = True
        # interval between folder exit and enter into next one
        interval = const.folder.max_scan_step_interval
        # scanning by kodi, detected when history is (from newwst):
        #   - [0] SHOW/2
        #   - [1] SHOW/1
        #   - [2] SHOW
        #   - [3] some list of shows
        if len(self.history) >= 4:
            hist = self.history
            path0 = self.history[0].url.path
            path1 = self.history[1].url.path
            path2 = self.history[2].url.path
            path3 = self.history[3].url.path
            if (not re.fullmatch(r'/tvshow/\d+/?.*', path3)                               # shows (no show / season view)
                    and '/tvshow' in path2 and path2.rpartition('/')[2].isdigit()         # show view
                    and path1 == f'{path2}/1'                                             # first season
                    and path0 == f'{path2}/2'                                             # second season
                    and hist[2].exit_timestamp - hist[1].enter_timestamp <= interval      # fast enter into first season
                    and hist[1].exit_timestamp - hist[0].enter_timestamp <= interval      # fast enter into second season
               ):
                self.scan_started = True
                self.scan = True
                self.scan_url = self.history[3].url  # folder before scan started
                self.media_url = self.history[2].url  # scanned folder
        # scan is stopped / aborted if more time to enter into current folder
        if self.scan and self.history[1].exit_timestamp - self.history[0].enter_timestamp > interval:
            self.scan = False
        if self.scan and self.refresh:
            self.scan = False
            self.scan_finished = True
        # Update folder tree with current folder info.
        if self.content:
            parent_url = str(self.folder_url)
            for item in self.content:
                if item.url:
                    self.folder_tree[item.url] = TreeFolderInfo(url=item.url, label=item.label, parent=parent_url)
        self.parent_path = []
        parent_url = str(url)
        for _ in range(10):
            if not (parent := self.folder_tree.get(parent_url)):
                break
            self.parent_path.insert(0, parent)
            if not (parent_url := parent.parent):
                break

    def exit(self, *, folder: Optional[Sequence[FFItem]] = None, focus: int = -1, timestamp: Optional[float] = None) -> None:
        """Exit from folder."""
        try:
            is_folder = folder is not None
            if self.history:
                if timestamp is None:
                    timestamp = utc_timestamp()
                self.history[0].exit_timestamp = timestamp
                if is_folder:
                    self.folder_url = self.history[0].url
            self.content = folder
            self.scan_started = False
            self.scan_finished = False
            fflog(f'EXIT FOLDER {-1 if folder is None else len(folder)}')
            if folder is not None:
                fflog(f'EXIT FOLDER refs: { {item.ref for item in folder} }')
                if refs := {item.ref for item in folder if item.ref.type in ('movie', 'show')}:
                    fflog(f'EXIT FOLDER PLAY DB: {list(video_db.get_plays_for(folder))}')
                    self.current_plays = tuple(pb for pb in video_db.get_plays_for(folder) if pb.ref in refs)
                else:
                    self.current_plays = ()
            if focus >= 0:
                Thread(target=self.focus_item, kwargs={'index': focus}).start()
        except Exception:
            fflog_exc()

    def focus_item(self, index: int) -> None:
        """Try to focus item on current list."""
        if index >= 0:
            xsleep(const.tune.service.focus_item_delay)
            import xbmcgui
            from ..ff.control import execute
            window = xbmcgui.Window(xbmcgui.getCurrentWindowId())
            container_id = window.getFocusId()
            execute(f'SetFocus({container_id},{index},absolute)')


@frozen(kw_only=True)
class StateVar:
    module: str
    key: str
    value: Any
    type: str
    updated_at: float


class StateVarDict(TypedDict):
    module: str
    key: str
    value: Any
    type: str
    updated_at: float


@define(kw_only=True)
class FFState:
    """General FF state, virtual DB."""

    state: Dict[str, Dict[str, StateVar]] = field(factory=dict)
    updated: Condition = field(factory=Condition)
    monitor: Optional[Monitor] = None

    def module(self, *, module: str) -> Dict[str, StateVar]:
        with self.updated:
            return self.state.get(module, {})

    def get(self, *, module: str, key: str, default: Optional[StateVar] = None) -> Optional[StateVar]:
        with self.updated:
            return self.state.get(module, {}).get(key, default)

    def get_all(self, *, module: str) -> Sequence[StateVar]:
        with self.updated:
            return tuple(self.state.get(module, {}).values())

    def set_variable(self, *, module: str, key: str, value: Any, type: str, updated_at: float) -> None:
        with self.updated:
            mod = self.state.setdefault(module, {})
            mod[key] = StateVar(module=module, key=key, value=value, type=type, updated_at=updated_at)
            self._emit()

    def set(self, var: Union[StateVar, StateVarDict], /) -> None:
        with self.updated:
            if not isinstance(var, StateVar):
                var = StateVar(**var)
            mod = self.state.setdefault(var.module, {})
            mod[var.key] = var
            self._emit()

    def multi_set(self, variables: Iterable[Union[StateVar, StateVarDict]], /) -> None:
        with self.updated:
            for var in variables:
                if not isinstance(var, StateVar):
                    var = StateVar(**var)
                mod = self.state.setdefault(var.module, {})
                mod[var.key] = var
            self._emit()

    def delete(self, *, module: str, key: str) -> Optional[StateVar]:
        with self.updated:
            res = self.state.get(module, {}).pop(key, None)
            if res is not None:
                self._emit()

    def delete_like(self, *, module: str, key: str) -> bool:
        def repl(mch: re.Match) -> str:
            return '.*' if mch.group() == '%' else '%'
        rx = re.compile(re.sub(r'(?:\\\\)?%', repl, re.escape(key)))
        with self.updated:
            if mod := self.state.get(module):
                prev_len = len(mod)
                self.state[module] = mod = {k: v for k, v in mod.items() if not rx.fullmatch(k)}
                if prev_len != len(mod):
                    self._emit()
                    return True
            return False

    def delete_all(self, *, module: str) -> bool:
        with self.updated:
            res = self.state.pop(module, None)
            if res is not None:
                self._emit()
            return bool(res)

    def wait_for(self, *, module: str, key: str, value: Any, timeout: Optional[float] = None) -> bool:
        def hit():
            var = self.state.get(module, {}).get(key)
            return var.value == value if var else False

        if hit():
            return True
        monitor = Monitor() if self.monitor is None else self.monitor
        end = MAX_TIMESTAMP if timeout is None else monotonic() + timeout
        with self.updated:
            while True:
                if (delta := end - monotonic()) <= 0 or monitor.abortRequested():
                    return False
                if self.updated.wait_for(hit, min(delta, const.tune.event_step)):
                    return True

    def _emit(self):
        self.updated.notify_all()


def update_playback_db_by_kodi_info(kodi: KodiVideoInfo, *, action: Optional[TrackingActionType] = None) -> bool:
    """Update playback DB play count using kodi DB info, used after set (un)watched detection."""
    if (pb := get_playback_item(kodi.ref)) is None:
        pb = MediaPlayInfo.from_kodi(kodi)  # first time?
    if action is None:
        old, new = pb.play_count or 0, kodi.play_count
        if old == new:
            action = 'reset_progress'
            pb.progress = 0
        elif new > old:
            action = 'watched'
            pb.play_count = old + 1
        elif new == 0:
            action = 'unwatched'
            pb.play_count = 0
    elif action == 'watched':
        pb.play_count = (pb.play_count or 0) + 1
    elif action == 'unwatched':
        pb.play_count = 0
    elif action == 'reset_progress':
        pb.progress = 0
    return update_playback_db(pb, action=action)


def update_playback_db(playback: MediaPlayInfo, *, play_count: Optional[int] = None, action: Optional[TrackingActionType] = None) -> bool:
    """Update playback DB play count."""
    from ..ff.trakt import trakt
    from .main import works

    fflog(f'[playback] {playback=}, {play_count=}, {action=}')

    if action is None:
        if playback.play_count:
            action = 'watched'
        else:
            action = 'unwatched'
    if action in ('watched', 'unwatched', 'reset_progress'):
        playback.clear_progress()
    if play_count is not None:
        playback.play_count = play_count
    result = update_track_watched_item(playback)

    if trakt.credentials():
        if result:
            trakt.updated()

    if works.tracking_service is not None:
        works.tracking_service.action(TrackingAction.from_playback(action, playback))

    return result
