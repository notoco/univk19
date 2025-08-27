"""
    Fanfilm Add-on

    Indexers' types.
"""

from typing import (
    Any,
    List, Dict,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from .super_info import SuperInfo


#: Generaic JSON Data item (dict).
DataItem = Dict[str, Any]

#: Media JSON Data item (dict). It's a DataItem for any video, music etc.
MediaItem = Dict[str, Any]

#: Dcit with meta data.
InfoItem = Dict[str, Any]
