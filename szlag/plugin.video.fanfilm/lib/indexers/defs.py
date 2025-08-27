"""
Some object definitions for indexers.

Those classes are independent of rest of code.
Can be safety used in const.py.
"""

from typing import Optional, Union, Any, Sequence, NamedTuple, TypeVar, Generic
from ..defs import VideoIds  # noqa: F401  (TODO: remove and fix rest of imports)


T = TypeVar('T')

#: ID grupy (gatunku, języka itp.).
CodeId = Union[str, int]


class DirItemSource(NamedTuple):
    """Source data for group (genres, languages, etc.) data to sort and filter."""

    #: Source code
    #:  -  iso-631-1 for language (eg. "pl")
    #:  -  iso-3166-1 for country (eg. "PL")
    code: CodeId

    #: Translated name in current kodi/GUI language.
    name: str

    #: Name o URL to icon image.
    image: Optional[str] = None


class VideoSequenceMixin(Generic[T]):
    """Mixin for sequnece (ex. list) imdb/tmdb video items."""

    def find_video(self: Sequence[T], imdb: str, tmdb: int, trakt: Optional[int] = None) -> Optional[T]:
        """Find video by imdb/tmdb/trakt."""
        a_imdb = str(imdb) if imdb else None
        a_tmdb = int(tmdb) if tmdb else None
        a_trakt = int(trakt) if trakt else None
        for item in self:
            if a_imdb is not None and item.imdb == a_imdb:
                return item
            if a_tmdb is not None and item.tmdb == a_tmdb:
                return item
            if a_trakt is not None and getattr(item, 'trakt', None) == a_trakt:
                return item
        return None
