
# from contextlib import closing
from contextlib import contextmanager
from datetime import datetime, date as dt_date, timezone
from typing import Optional, Union, Tuple, Dict, Set, Sequence, Iterable, Iterator, TypeVar, TYPE_CHECKING
from typing_extensions import Self, TypeAlias

from .db import db_manager, Lock, sql_dump, update_db_version, DbCursor, PrimaryKey, SQL
from .orm import OrmDatabase, DbTable, field as db_field, select, update, AND, OR, IN, MISSING
from ...defs import MediaType, MainMediaType, MediaRef, XMediaRef, MediaProgressItem, MediaProgress
from ..tricks import MissingType
from ..item import FFItem, FFItemDict
from ..calendar import utc_timestamp, utc_from_timestamp, datestamp as make_datestamp, DateTime
from ..log_utils import fflog
from ..debug.timing import logtime  # DEBUG
from const import const
if TYPE_CHECKING:
    from ..kodidb import KodiVideoInfo

# to avoid collision with "def set()"
# TODO: reanme function
from builtins import set as _set


T = TypeVar('T')

#: State DB version.
DB_VERSION: int = 3


class MediaPlayInfo(DbTable):
    """Trakt playback row."""

    __tablename__ = 'trakt_playback'
    # UNIQUE(type, ffid)
    __table_args__ = ('UNIQUE("xref::type", "xref::ffid", "xref::season", "xref::episode")',)

    id: PrimaryKey = None
    xref: XMediaRef = MISSING
    ffid: int = 0
    tmdb: Optional[int] = None
    imdb: Optional[str] = None
    trakt: Optional[int] = None
    tvdb: Optional[int] = None
    slug: Optional[str] = None
    tv_slug: Optional[str] = None
    playback_id: Optional[int] = None
    progress: Optional[float] = None    # 0 .. 100
    progress_map: Optional[str] = None  # episode progress bar, ex. 100101110
    paused_at: Optional[int] = None
    play_count: Optional[int] = None
    last_watched_at: Optional[int] = None
    duration: Optional[int] = None
    aired_at: Optional[int] = None
    next_aired_at: Optional[int] = None  # use only in tv-show or season
    # meta_updated_at: int = 0
    meta_updated_at: Optional[int] = db_field(on_update=SQL("strftime('%s', 'now', 'utc')"), auto_generated=True)

    # cache for MediaRef
    _ref: Optional[MediaRef] = None

    def __init__(self, *, id: PrimaryKey = None, ref: MediaRef = MISSING, xref: Union[XMediaRef, MissingType] = MISSING, ffid: int = 0,
                 tmdb: Optional[int] = None, imdb: Optional[str] = None, trakt: Optional[int] = None, tvdb: Optional[int] = None,
                 slug: Optional[str] = None, tv_slug: Optional[str] = None, playback_id: Optional[int] = None,
                 progress: Optional[float] = None, progress_map: Optional[float] = None, paused_at: Optional[int] = None,
                 play_count: Optional[int] = None, last_watched_at: Optional[int] = None, duration: Optional[int] = None,
                 aired_at: Optional[int] = None, next_aired_at: Optional[int] = None, meta_updated_at: Optional[int] = None) -> None:

        def timestamp(val):
            if not val:
                return None
            if isinstance(val, str):
                val = utc_timestamp(val)
            return int(val)

        def datestamp(val):
            if not val:
                return None
            return make_datestamp(val)

        _xref, _ref = xref, ref
        if xref is MISSING:
            xref = ref  # type: ignore  (hack)
        elif ref is not MISSING:
            raise ValueError('cannot specify both `ref` and `xref`')
        if xref is MISSING:
            raise ValueError('have to specify one of `ref` or `xref`')

        self.id               = id                               # noqa: E221
        self.xref             = xref.sql_ref                     # noqa: E221  # type: ignore  (hack, XMediaRef = MediaRef)
        self.ffid             = int(ffid or 0)                   # noqa: E221
        self.tmdb             = int(tmdb or 0) or None           # noqa: E221
        self.imdb             = imdb                             # noqa: E221
        self.trakt            = int(trakt or 0) or None          # noqa: E221
        self.tvdb             = tvdb                             # noqa: E221
        self.slug             = slug                             # noqa: E221
        self.tv_slug          = tv_slug                          # noqa: E221
        self.playback_id      = int(playback_id or 0) or None    # noqa: E221
        self.progress         = None if progress is None else float(progress)  # noqa: E221
        self.progress_map     = str(progress_map or '') or None  # noqa: E221
        self.paused_at        = timestamp(paused_at)             # noqa: E221
        self.play_count       = None if play_count is None else int(play_count)     # noqa: E221
        self.last_watched_at  = timestamp(last_watched_at)       # noqa: E221
        self.duration         = int(duration or 0) or None       # noqa: E221
        self.aired_at         = datestamp(aired_at)              # noqa: E221
        self.next_aired_at    = datestamp(next_aired_at)         # noqa: E221
        self.meta_updated_at  = timestamp(meta_updated_at)       # noqa: E221
        self._ref = None

        # if self.xref.type not in get_typing_args(MediaType):
        #     allowed = ', '.join(get_typing_args(MediaType))
        #     raise ValueError(f'MediaPlayInfo: incorrect type {type!r}, should be one of: {allowed}')

    @property
    def has_progress(self) -> bool:
        return self.progress is not None and 0 < self.progress < 100

    @property
    def has_play_count(self) -> bool:
        return self.play_count is not None

    @property
    def ref(self) -> MediaRef:
        """Return media reference."""
        if self._ref is None:
            self._ref = MediaRef.from_sql_ref(self.xref)
        return self._ref

    @ref.setter
    def ref(self, ref: MediaRef) -> None:
        self._ref = ref
        self.xref = ref.sql_ref  # type: ignore  (hack)

    @property
    def denormalized_ref(self) -> Optional[MediaRef]:
        """Return denormalized reference (eg. episode)."""
        # vid = VideoIds(tmdb=self.tmdb, imdb=self.imdb, tvdb=self.tvdb)
        if self.ffid:
            return MediaRef(self.ref.real_type, self.ffid)
        return None

    def refs(self) -> Iterator[MediaRef]:
        """Iterate over refs (normalized and denormalized)."""
        yield self.ref
        if self.ffid and (de_ref := MediaRef(self.ref.real_type, self.ffid)) and de_ref != self._ref:
            yield de_ref

    def as_item(self) -> FFItem:
        """Return pb as (simplified) FFItem."""
        item = FFItem(self.ref)
        if time := max(self.paused_at or 0, self.last_watched_at or 0):
            item.vtag.setLastPlayed(str(utc_from_timestamp(time)))
        return item

    def as_media_progress_item(self, *, no_progress: bool = False) -> MediaProgressItem:
        """Return MediaProgressItem."""
        if self.last_watched_at and (self.play_count or not no_progress):
            last_watched_at = utc_from_timestamp(self.last_watched_at)
        else:
            last_watched_at = datetime.min
        if no_progress:
            return MediaProgressItem(self.ref, progress=0, play_count=self.play_count or 0, last_watched_at=last_watched_at.date())
        return MediaProgressItem(self.ref, progress=self.progress or 0, play_count=self.play_count or 0, last_watched_at=last_watched_at.date())

    def as_media_progress(self) -> MediaProgress:
        """Return MediaProgressItem."""
        if self.last_watched_at:
            last_watched_at = utc_from_timestamp(self.last_watched_at)
        else:
            last_watched_at = datetime.min
        if self.ref.real_type in ('show', 'season'):
            # fake progress items
            bar = tuple(MediaProgressItem(ref=MediaRef('', 0), play_count=int(c == '1')) for c in self.progress_map or '')
        else:
            bar = ()
        return MediaProgress(self.ref, progress=self.progress or 0, play_count=self.play_count or 0, last_watched_at=last_watched_at.date(), bar=bar)

    def update_playback(self, pb: 'MediaPlayInfo') -> Self:
        """Update playback (progress) from another MediaPlayInfo."""
        if pb and pb is not self:
            self.progress = pb.progress
            self.progress_map = pb.progress_map
            self.playback_id = pb.playback_id
            self.paused_at = pb.paused_at
        return self

    def update_by_ffitem(self, item: Optional[FFItem], *, now: Optional[Union[dt_date, str, int]] = None) -> None:

        def int_or_none(v):
            return int(v) if v else None

        def timestamp(val):
            if not val:
                return None
            return int(utc_timestamp(val))

        def datestamp(val):
            if not val:
                return None
            return make_datestamp(val)

        if item is None:
            return

        vtag = item.vtag
        ids = vtag.getUniqueIDs()

        if (tmdb := int_or_none(ids.get('tmdb'))):
            self.tmdb = tmdb
        if (imdb := ids.get('imdb')):
            self.imdb = imdb
        if (trakt := int_or_none(ids.get('trakt'))):
            self.trakt = trakt
        if (tvdb := int_or_none(ids.get('tvdb'))):
            self.tvdb = tvdb
        if (slug := ids.get('slug')):
            self.slug = slug
        if (duration := int_or_none(vtag.getDuration())):
            self.duration = duration
        if (aired_at := datestamp(item.date)):
            self.aired_at = aired_at
        if now:
            self.meta_updated_at = timestamp(now)

    def update_new_episodes(self, count: int, *, now: Optional[Union[dt_date, str, int]] = None) -> None:
        """Update playback with new episodes count."""
        if count < 0:
            raise ValueError(f'count must be >= 0, not {count}')
        self.progress_map = (self.progress_map or '') + '0' * count
        self.progress = 100 * self.progress_map.count('1') / (len(self.progress_map) or 1)
        if now:
            self.meta_updated_at = int(utc_timestamp(now))

    def clear_progress(self, *, progress: Optional[float] = None) -> None:
        """Clears progress."""
        self.playback_id = None
        self.progress = progress
        self.progress_map = None
        self.paused_at = None

    @classmethod
    def from_ffitem(cls, item: FFItem, *, now: Optional[Union[dt_date, str, int]] = None) -> Self:

        def int_or_none(v):
            return int(v) if v else None

        def timestamp(val):
            if not val:
                return None
            return int(utc_timestamp(val))

        def datestamp(val):
            if not val:
                return None
            return make_datestamp(val)

        vtag = item.vtag
        ids = vtag.getUniqueIDs()

        return cls(ref=item.ref,
                   ffid=item.ffid or 0,
                   tmdb=int_or_none(ids.get('tmdb')),
                   imdb=ids.get('imdb'),
                   trakt=int_or_none(ids.get('trakt')),
                   tvdb=int_or_none(ids.get('tvdb')),
                   slug=ids.get('slug'),
                   duration=int_or_none(vtag.getDuration()),
                   aired_at=datestamp(item.date),
                   meta_updated_at=timestamp(now),
                   )

    @classmethod
    def from_kodi(cls, info: 'KodiVideoInfo', *, now: Optional[Union[dt_date, str, int]] = None) -> Self:
        """Return media progress build from Kodi video info (Kodi DB)."""
        if info.time_s and not info.play_count:
            last_watched_at = None
            paused_at = info.played_at
        else:
            last_watched_at = info.played_at
            paused_at = None
        if info.ref.season is None:
            ffid = 0  # hmmm, we have no direct ffid (for season and episode)
        else:
            ffid = info.ref.ffid
        return cls(ref=info.ref,
                   ffid=ffid,
                   tmdb=info.tmdb,
                   imdb=info.imdb,
                   last_watched_at=last_watched_at,
                   paused_at=paused_at,
                   meta_updated_at=int(utc_timestamp(now)) if now else None,
                   )


MediaPlayInfoDict: TypeAlias = Dict[MediaRef, MediaPlayInfo]


# class TraktHistoryItem(NamedTuple):
#     """Trakt history row."""
#     history_id: int
#     ffid: int
#     action: str
#     watched_at: str
#     trakt_id: int
#     imdb: str
#     tmdb: int
#     slug: str
#     type: str
#     episode: Optional[int] = None
#     season: Optional[int] = None
#     tv_trakt_id: Optional[int] = None
#     tv_imdb: Optional[str] = None
#     tv_tmdb: Optional[int] = None
#     v_slug: Optional[str] = None


#: Global playback DB.
db = OrmDatabase('playback', MediaPlayInfo, version=DB_VERSION)


#: WHERE IN VALUES (type, main_ffid, season, episode)
MediaInfoWhereValue = Union[Tuple[str, int, int, int], Tuple[str, int, int], Tuple[str, int]]


def get_playback_info(refs: Iterable[MediaRef]) -> MediaPlayInfoDict:
    """Get media info rows as dict."""
    def make_where(ref: MediaRef) -> Iterator[MediaInfoWhereValue]:
        if ref.type == 'show':
            yield ref.type, ref.ffid, -1, -1
            if ref.season:
                yield ref.type, ref.ffid, ref.season, -1
                # yield 'season', ref.ffid, ref.season, -1
                if ref.episode:
                    yield ref.type, ref.ffid, ref.season, ref.episode
                    # yield 'episode', ref.ffid, ref.season, ref.episode
                else:
                    yield ref.type, ref.ffid, ref.season
            else:
                yield ref.type, ref.ffid
        else:
            # movies and anything else
            yield ref.type, ref.ffid, -1, -1

    keys: Set[MediaInfoWhereValue] = {key for ref in refs for key in make_where(ref)}
    if not keys:
        return {}
    names = ('"xref::type"', '"xref::ffid"', '"xref::season"', '"xref::episode"')
    wheres = (f'({",".join(names[:size])}) IN (VALUES {values})' for size in (4, 3, 2)
              if (values := ','.join(f'({",".join(sql_dump(x) for x in key)})' for key in keys if len(key) == size)))
    where = ' OR '.join(wheres)
    print(f'{where=}')
    with db.cursor() as cur:
        return {ref: m for m in cur.exec(select(MediaPlayInfo).where(where)).iter() for ref in m.refs()}


@logtime
def _get_playback(cur: DbCursor, type: Optional[MediaType] = None, *, in_progress: Optional[bool] = None, sort: bool = False) -> MediaPlayInfoDict:
    """Get all trakt playback videos."""
    query = select(MediaPlayInfo)
    if type == 'episode':
        query = query.where(AND(MediaPlayInfo.xref.type == 'show', MediaPlayInfo.xref.season != -1, MediaPlayInfo.xref.episode != -1))
    elif type == 'season':
        query = query.where(AND(MediaPlayInfo.xref.type == 'show', MediaPlayInfo.xref.season != -1, MediaPlayInfo.xref.episode == -1))
    elif type:
        query = query.where(MediaPlayInfo.xref.type == type)
    if in_progress is True:
        # "where" could be used many times: select().where(A).where(B) means select.where(AND(A, B))
        query = query.where(AND(MediaPlayInfo.progress > 0, MediaPlayInfo.progress < 100))  # type: ignore  -- SQL column with NULL could be compared to number
    elif in_progress is False:
        # MediaPlayInfo.progress == None is indeted to build SQL WHERE statment
        query = query.where(OR(MediaPlayInfo.progress == None, MediaPlayInfo.progress <= 0, MediaPlayInfo.progress >= 100))  # type: ignore  -- SQL column with NULL could be compared to number
    if sort:
        query = query.order_by('MAX(IFNULL(paused_at,0), IFNULL(last_watched_at, 0)) DESC')
    fflog(f'_get_playback(): q: {query}')
    with logtime(name='_get_playback(): select'):
        return {m.ref: m for m in cur.exec(query).iter()}


def get_playback(type: Optional[MediaType] = None, *, in_progress: Optional[bool] = None, sort: bool = False) -> MediaPlayInfoDict:
    """Get all trakt playback videos."""
    with db.cursor() as cur:
        return _get_playback(cur, type, in_progress=in_progress, sort=sort)


def get_playback_item(ref: MediaRef) -> Optional[MediaPlayInfo]:
    """Get single trakt playback video."""
    with db.cursor() as cur:
        if ref.is_normalized:
            query = select(MediaPlayInfo).where(MediaPlayInfo.xref == ref.sql_ref)
        elif ref.type == 'episode':
            query = select(MediaPlayInfo).where(AND(MediaPlayInfo.xref.type == 'show', MediaPlayInfo.xref.season != -1, MediaPlayInfo.xref.episode != -1, MediaPlayInfo.ffid == ref.ffid))
        elif ref.type == 'season':
            query = select(MediaPlayInfo).where(AND(MediaPlayInfo.xref.type == 'show', MediaPlayInfo.xref.season != -1, MediaPlayInfo.xref.episode == -1, MediaPlayInfo.ffid == ref.ffid))
        else:
            raise ValueError(f'Unsupported denormalized ref {ref}')
        return cur.exec(query).first()


def update_track_playback(new: Iterable[MediaPlayInfo], *, info: Optional[FFItemDict] = None, timestamp: Optional[Union[datetime, float]] = None) -> bool:
    """Update trakt playback & watched DB by new playback data."""
    # `info` is not used, it's ok
    changed = False
    with db.cursor() as cur:
        old = _get_playback(cur)
        for pb in new:
            media = old.get(pb.ref, pb)
            media.playback_id = pb.playback_id
            media.progress = pb.progress
            media.progress_map = pb.progress_map
            media.paused_at = pb.paused_at
            # new row or update -> insert or update
            changed |= cur.add(media)
    return changed


def set_playback(media: MediaPlayInfo, /) -> bool:
    """Update trakt playback & watched DB by new playback data."""
    with db.cursor() as cur:
        # new row or update -> insert or update
        return cur.add(media)


@logtime
def _get_shows_info(refs: Iterable[MediaRef]) -> FFItemDict:
    """Returns shows and seasons info."""
    # get shows and seasons info (import here to avoid circular imports)
    from ..info import ffinfo
    shows = {show for ref in refs if ref.type == 'show' and (show := ref.show_ref)}
    return ffinfo.get_item_dict(tuple(shows), progress=ffinfo.Progress.NO, tv_episodes=True)


def _handle_update_show_episodes(new: Sequence[MediaPlayInfo],
                                 old: MediaPlayInfoDict,
                                 *,
                                 info: Optional[FFItemDict] = None,
                                 ) -> Tuple[Sequence[MediaPlayInfo], Optional[FFItemDict]]:
    """Helper. Handle show and episode (only single item), set play_count and reset progress for all its episodes."""
    if not new or len(new) > 1:
        fflog(f'WARNING, _update_track_watched() for supports only single show or season not {len(new)}')
        return new, info
    one = new[0]
    one_ref = one.ref
    # set watched show / season
    if one.play_count:
        if info is None:
            info = _get_shows_info((one_ref, *one_ref.parents()))
        item = info.get(one_ref)
        if not item:
            return new, info
        if one_ref.is_show:
            to_change = [m for sz in item.season_iter() if sz.season for ep in sz.episode_iter()
                         if (m := old.get(ep.ref) or MediaPlayInfo.from_ffitem(ep))]
        else:
            to_change = [old.get(ep.ref, MediaPlayInfo.from_ffitem(ep)) for ep in item.episode_iter()]
    # unset watched show / season
    else:
        if one_ref.is_show:
            to_change = [m for m in old.values() if m.ref.show_ref == one_ref]
        else:
            to_change = [m for m in old.values() if m.ref.season_ref == one_ref]
    # copy media items, then set play_count and reset progress
    new = []
    for media in to_change:
        m = MediaPlayInfo(**media.model_dump())
        m.play_count = one.play_count
        m.progress = 0
        m.last_watched_at = None
        new.append(m)
    return new, info


@logtime
def _update_track_watched(new: Sequence[MediaPlayInfo],
                          *,
                          media_type: Optional[MainMediaType],
                          mark_missing: bool = True,
                          today: Optional[dt_date] = None,
                          info: Optional[FFItemDict] = None,
                          timestamp: Optional[Union[datetime, float]] = None,
                          ) -> bool:
    """Update trakt playback & watched DB by new watched data. Return True on any change"""

    if not new:
        return False

    changed = False
    with db.cursor() as cur:
        cur.execute('BEGIN IMMEDIATE')
        # cur.execute('BEGIN DEFERRED')
        old = _get_playback(cur, type=media_type)
        watched: Set[MediaRef] = {ref for ref, media in old.items() if media.play_count}
        reset: Set[MediaRef] = _set()

        # handle show and episode (only single item), set play_count and reset progress for all its episodes
        if any(m.ref.is_container for m in new):
            new, info = _handle_update_show_episodes(new, old, info=info)
            if not new:
                return False

        # udpate video (movie or episode)
        for pb in new:
            # last_updated_at = pb.meta_updated_at or 0
            media = old.get(pb.ref, pb)
            if media.ref.real_type in ('movie', 'episode'):
                media.playback_id = pb.playback_id
                media.play_count = pb.play_count
                media.last_watched_at = pb.last_watched_at
                media.progress = pb.progress
                if pb.play_count:
                    media.progress_map = '1'
                    watched.add(media.ref)
                else:
                    media.progress_map = '0'
                    watched.discard(media.ref)
                if cur.add(media):
                    changed = True
                    reset.update(media.ref.parents())

        # missing (removed, play_count set to zero)
        if mark_missing:
            for ref in old.keys() - {m.ref for m in new}:
                media = old[ref]
                # reset play_count if exists
                if media.play_count is not None and ref.real_type in ('movie', 'episode'):
                    media.playback_id = None
                    media.play_count = 0
                    media.last_watched_at = None
                    media.progress = 0
                    media.progress_map = '0'
                    watched.discard(ref)
                    if cur.add(media):
                        changed = True
                        reset.update(media.ref.parents())

        # reset progress of changed shows and episodes
        if reset:
            # add new to old, to make searching easier
            for pb in new:
                old.setdefault(pb.ref, pb)
            # recalculate seasons and shows
            changed |= _fix_shows_progress(cur, reset, today=today, playbacks=old, watched=watched, info=info)
        cur.execute('COMMIT')

    return changed


@logtime
def _fix_shows_progress(cur: DbCursor,
                        reset: Iterable[MediaRef],
                        *,
                        today: Optional[dt_date] = None,
                        playbacks: Optional[MediaPlayInfoDict] = None,
                        watched: Optional[Set[MediaRef]] = None,
                        info: Optional[FFItemDict] = None,
                        timestamp: Optional[Union[datetime, float]] = None,
                        ) -> bool:
    """
    Recalculate season and show progress and map for given episodes ref `reset`.

    `playbacks` and `watched` are optional, but could be providet for performace reason.
    Those values are known in trakt episode update already.
    """

    if today is None:
        today = datetime.now(timezone.utc)
    if not const.indexer.episodes.progress_if_aired:
        today = dt_date.max
    if isinstance(today, DateTime):
        today = today.date()

    changed = False

    # reset progress of changed shows and episodes
    reset = tuple(reset)
    if reset:
        # get all current DB playbacks (progress anf watched)
        if playbacks is None:
            # TODO: limit _get_playback() to reset shows and seasons
            playbacks = _get_playback(cur, type='show')
        # set of watched episodes
        if watched is None:
            watched = {media.ref for media in playbacks.values() if media.ref.is_episode and media.play_count}

        # slug for new createded seasons and shows
        tv_slugs = {pb.ref.show_ref: pb.tv_slug for pb in playbacks.values() if pb.ref.is_episode}

        # get shows and seasons info (import here to avoid circular imports)
        if info is None:
            info = _get_shows_info(reset)
        # all MediaPlayInfo shows and seasons needs to be recalculated
        groups = {ref: media for ref in reset if (media := playbacks.get(ref)) or ((it := info.get(ref)) and (media := MediaPlayInfo.from_ffitem(it)))}
        for ref, media in groups.items():
            if not media.tv_slug:
                media.tv_slug = tv_slugs.get(ref.show_ref)
            if ref.is_show and not media.slug:
                media.slug = media.tv_slug
            media.update_by_ffitem(info.get(ref))

        # recalcualte seasons
        for ref, media in groups.items():
            if ref.is_season:
                it = info.get(ref)
                if it:
                    media.progress_map = ''.join('1' if ep.ref in watched else '0'
                                                 for ep in it.episode_iter() if ep.aired_before(today))
                    media.progress = 100 * media.progress_map.count('1') / (len(media.progress_map) or 1)
                    media.play_count = 0 if '0' in media.progress_map else 1
                    changed |= cur.add(media)

        # recalcualte shows
        for ref, media in tuple(groups.items()):
            if ref.is_show:
                it = info.get(ref)
                if it:
                    def get_seasons(seasons: Iterable[Optional[int]]) -> MediaPlayInfoDict:
                        where = AND(MediaPlayInfo.xref.type == ref.type, MediaPlayInfo.xref.ffid == ref.ffid, MediaPlayInfo.xref.episode == -1,
                                    IN(MediaPlayInfo.xref.season, seasons))
                        return {ref: m for m in cur.exec(select(MediaPlayInfo).where(where)).iter() for ref in m.refs()}

                    # try to load missing seasons from db, useful when single item is updating
                    groups.update(get_seasons(sz.ref.season for sz in it.season_iter() if sz.ref not in groups))
                    # add missing seasons to `groups` but NOT to the DB
                    # - no eny episode is watched then no season need to be reset
                    # - but we need those unwatched episodes count to calcultate show progress
                    for sz in it.season_iter():
                        if sz.ref not in groups:
                            groups[sz.ref] = sz_media = MediaPlayInfo.from_ffitem(sz)
                            sz_media.progress_map = ''.join('0' for ep in sz.episode_iter() if ep.aired_before(today))
                            sz_media.progress = 0
                            sz_media.tv_slug
                            # NOTE: Do NOT add sz_media to DB!
                    # recalculate shows based on seasons' progress_map
                    media.progress_map = ''.join(sz_media.progress_map or '' for sz in it.season_iter() if (sz_media := groups.get(sz.ref)))
                    media.progress = 100 * media.progress_map.count('1') / (len(media.progress_map) or 1)
                    media.play_count = 0 if '0' in media.progress_map else 1
                    changed |= cur.add(media)

    return changed


def update_track_watched_movies(new: Sequence[MediaPlayInfo], *, info: Optional[FFItemDict] = None, timestamp: Optional[Union[datetime, float]] = None) -> bool:
    """Update trakt playback & watched DB by new watched movies data."""
    return _update_track_watched(new, media_type='movie', timestamp=timestamp)


def update_track_watched_episodes(new: Sequence[MediaPlayInfo], *, info: Optional[FFItemDict] = None, timestamp: Optional[Union[datetime, float]] = None) -> bool:
    """Update trakt playback & watched DB by new watched episodes data and recalculate show progress."""
    return _update_track_watched(new, media_type='show', timestamp=timestamp)


# def update_track_watched_all(new: Sequence[MediaPlayInfo], *, info: FFItemDict) -> bool:
#     """Update trakt playback & watched DB by new watched all data (movies & shows)."""
#     return _update_track_watched(new, media_type=None)


def update_track_watched_item(new: MediaPlayInfo, *, timestamp: Optional[Union[datetime, float]] = None, info: Optional[FFItemDict] = None) -> bool:
    """Update single trakt playback & watched DB item by its data."""
    ref = new.ref
    if ref.type in ('movie', 'show'):
        return _update_track_watched([new], media_type=ref.type, mark_missing=False, timestamp=timestamp, info=info)
    return False


def set_track_watched_item(new: Union[MediaPlayInfo, MediaRef], *, timestamp: Optional[Union[datetime, float]] = None) -> bool:
    """Set as watched single trakt DB item by its data."""
    info: Optional[FFItemDict] = None
    if isinstance(new, MediaPlayInfo):
        ref = new.ref
        if media := get_playback_item(ref):  # get old to make update possible
            new = media
    else:
        ref = new
        if media := get_playback_item(ref):
            new = media
        else:
            reset = {ref, *ref.parents()}
            info = _get_shows_info(reset)
            if it := info.get(ref):
                new = MediaPlayInfo.from_ffitem(it)
            else:
                new = MediaPlayInfo(ref=ref)
    new.clear_progress()
    new.play_count = 1
    new.last_watched_at = int(utc_timestamp(timestamp))
    return update_track_watched_item(new, timestamp=timestamp, info=info)


def unset_track_watched_item(new: Union[MediaPlayInfo, MediaRef], *, timestamp: Optional[Union[datetime, float]] = None) -> bool:
    """Update single trakt playback & watched DB item by its data."""
    info: Optional[FFItemDict] = None
    if isinstance(new, MediaPlayInfo):
        ref = new.ref
        if media := get_playback_item(ref):  # get old to make update possible
            new = media
    else:
        ref = new
        if media := get_playback_item(ref):
            new = media
        else:
            reset = {ref, *ref.parents()}
            info = _get_shows_info(reset)
            if it := info.get(ref):
                new = MediaPlayInfo.from_ffitem(it)
            else:
                new = MediaPlayInfo(ref=ref)
    new.clear_progress(progress=0)
    new.play_count = 0
    new.last_watched_at = None
    return update_track_watched_item(new, timestamp=timestamp, info=info)

    # if isinstance(new, MediaPlayInfo):
    #     ref = new.ref
    # else:
    #     ref = new

    # if ref.type == 'show':
    #     reset = {ref, *ref.parents()}
    #     info = _get_shows_info(reset)
    #     with db.cursor() as cur:
    #         # it is tv-show, unset the show and its known seasons and theirs known episodes
    #         if ref.is_show:
    #             cur.exec(update(MediaPlayInfo).set(progress=None, play_count=0, last_watched_at=None).where(
    #                 AND(MediaPlayInfo.xref.type == ref.type, MediaPlayInfo.xref.ffid == ref.ffid)))
    #             if it := info.get(ref):
    #                 reset.update(sz.ref for sz in it.season_iter())
    #         elif ref.is_season:
    #             # it is season, unset only the season and its known episodes
    #             cur.exec(update(MediaPlayInfo).set(progress=None, play_count=0, last_watched_at=None).where(
    #                 AND(MediaPlayInfo.xref.type == ref.type, MediaPlayInfo.xref.ffid == ref.ffid, MediaPlayInfo.xref.season == ref.season)))
    #         else:
    #             # it is episode, unset only the episode
    #             cur.exec(update(MediaPlayInfo).set(progress=None, play_count=0, last_watched_at=None).where(MediaPlayInfo.xref == ref.xref))
    #         changed = bool(cur.rowcount)
    #         # update progress
    #         old = {m.ref: m
    #                for m in cur.exec(select(MediaPlayInfo).where(AND(MediaPlayInfo.xref.type == ref.type, MediaPlayInfo.ffid == ref.ffid))).iter()}
    #         changed |= _fix_shows_progress(cur, reset=reset, playbacks=old, info=info)
    #         return changed
    # else:
    #     with db.cursor() as cur:
    #         cur.exec(update(MediaPlayInfo).set(progress=None, play_count=0, last_watched_at=None).where(MediaPlayInfo.xref == ref.xref))
    #     return bool(cur.rowcount)


# def update_track_shows_progress() -> None:
#     """Update trakt playback & watched shows and episodes."""
#     with db.cursor() as cur:
#         _update_track_shows_progress(cur)


def remove_all_track_watched_items() -> None:
    """Remove all items, clear trakt_playback table."""
    with db.cursor() as cur:
        cur.execute('DELETE FROM trakt_playback')


# def _history_merge(old: List[TraktHistoryItem], new: List[TraktHistoryItem]) -> List[TraktHistoryItem]:
#     """Merge old and new history. Take new with removeing support."""
#     oldd: Dict[int, TraktHistoryItem] = {m.ffbid: m for m in old}
#     newd: Dict[int, TraktHistoryItem] = {m.ffid: m for m in new}
#     keep = set(oldd.keys()) - set(newd.keys())
#     return tuple(chain((v._replace(history_id=None) for k, v in old.itms() if k in keep), newd.values()))


# def update_history(rows: List[TraktHistoryItem]) -> None:
#     """Replace trakt playback content."""
#     with db.cursor() as cur:
#         cur.execute('SELECT * FROM trakt_history')
#         old = [TraktHistoryItem(*row[1:]) for row in cur.fetchall()]
#         rows = _history_merge(old, rows)
#         cur.execute('DELETE FROM trakt_history')
#         cur.executemany('INSERT INTO trakt_history ('
#                         ' history_id, ffid, action, watched_at, trakt_id, imdb, tmdb, slug, type,'
#                         ' episode, season, tv_trakt_id, tv_imdb, tv_tmdb, tv_slug'
#                         ') VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', rows)


if __name__ == '__main__':
    from ...ff.cmdline import DebugArgumentParser
    p = DebugArgumentParser(dest='cmd')
    with p.with_subparser('x1'):
        pass
    with p.with_subparser('playback'):
        pass
    with p.with_subparser('shows') as pp:
        pp.add_argument('-e', '--episode', action='store_true', help='show episodes with ffid')
    with p.with_subparser('movies'):
        pass
    args = p.parse_args()

    if args.cmd == 'x1':
        # print(get_playback())
        # print(get_playback().keys())
        # m1 = get_playback_item(MediaRef('show', 84958, 2, 5))
        # m2 = get_playback_item(MediaRef('episode', 4447780))
        m1 = get_playback_item(MediaRef('show', 100_127_235, 2, 5))
        m2 = get_playback_item(MediaRef('episode', 104_557_662))
        assert m1 == m2
        print(m1)
    elif args.cmd == 'playback':
        from cProfile import Profile
        from pstats import Stats
        with Profile(builtins=False) as pr:
            get_playback('show')
            st = Stats(pr).sort_stats('cumtime', 'ncalls')
            # st = Stats(pr).sort_stats('ncalls', 'tottime', 'cumtime')
            # pr.print_stats(('ncalls', 'tottime', 'cumtime'))
            st.print_stats()
    elif args.cmd in ('movies', 'shows'):
        for pb in get_playback(args.cmd[:-1]).values():
            if not args.episode or (pb.ref.is_episode and pb.ffid):
                print(pb)
