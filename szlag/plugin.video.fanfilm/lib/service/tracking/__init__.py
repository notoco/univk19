
from __future__ import annotations
from attrs import frozen, field
from typing import Optional, List, TYPE_CHECKING
from typing_extensions import Literal, Protocol, Self
from ...ff.calendar import utc_timestamp
if TYPE_CHECKING:
    from ...defs import MediaRef
    from ...ff.db.playback import MediaPlayInfo


TrackingActionType = Literal['start', 'pause', 'stop', 'watched', 'unwatched', 'reset_progress']


@frozen(kw_only=True)
class TrackingAction:
    action: TrackingActionType
    ref: MediaRef
    progress: Optional[float] = None  # 0..100
    play_count: Optional[int] = None
    timestamp: float = field(factory=utc_timestamp)

    @classmethod
    def from_playback(cls, action: TrackingActionType, playback: MediaPlayInfo, *, now: Optional[float] = None) -> Self:
        """Return TrackingAction with playback data."""
        if now is None:
            now = utc_timestamp()
        return cls(action=action, ref=playback.ref, progress=playback.progress, play_count=playback.play_count, timestamp=now)


class TrackingServiceProto(Protocol):
    def action(self, action: TrackingAction) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...


class TrackingService:

    def __init__(self) -> None:
        self.services: List[TrackingServiceProto] = []

    def append(self, service: TrackingServiceProto) -> None:
        self.services.append(service)

    def start(self) -> None:
        for service in self.services:
            service.start()

    def stop(self) -> None:
        for service in self.services:
            service.stop()

    def action(self, action: TrackingAction) -> None:
        """Send tracking action to all services."""
        for service in self.services:
            service.action(action)


tracking_service = TrackingService()
