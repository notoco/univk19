"""Test fake module."""

from typing import ClassVar, List
from .tools import getsetmethods, Factory, field
from .xbmc import InfoTagVideo


if False:
    @getsetmethods
    class InfoTagVideoX:

        class X:
            q: int

        a: int
        b: float = 0
        c: ClassVar[int]
        d: List[str] = Factory(list)
        Directors: List[str] = field(default='', default_factory=list, first_getter='getDirector')

        def x__init__(self):
            self.a = 42


    vtag = InfoTagVideo(1)
    # vtag = InfoTagVideo()

    print(vtag)
    print(vtag.getA())
    vtag.setA(3)
    print(vtag)
    vtag.setDirectors(['aaa', 'bbb', 'ccc'])
    print(vtag.getDirector(), vtag.getDirectors())
    print(vtag.__annotations__)
    print(vtag.__attributes__)
else:
    vtag = InfoTagVideo()
    print(vtag)
    print(vtag.getDbId())


# ListItem.getArt() = ''
# ListItem.getDateTime() = ''
# ListItem.getGameInfoTag() = <xbmc.InfoTagGame object at 0x7f267326c360>
# ListItem.getLabel() = ''
# ListItem.getLabel2() = ''
# ListItem.getMusicInfoTag() = <xbmc.InfoTagMusic object at 0x7f267326d470>
# ListItem.getPath() = ''
# ListItem.getPictureInfoTag() = <xbmc.InfoTagPicture object at 0x7f267326d500>
# ListItem.getProperty() = ''
# ListItem.getRating() = 0.0       # Please use InfoTagVideo.getRating().
# ListItem.getUniqueID() = ''      # Please use InfoTagVideo.getUniqueID().
# ListItem.getVideoInfoTag() = <xbmc.InfoTagVideo object at 0x7f267326cde0>
# ListItem.getVotes() = 0          # Please use InfoTagVideo.getVotesAsInt().
# InfoTagVideo.getActors() = []
# InfoTagVideo.getAlbum() = ''
# InfoTagVideo.getArtist() = []
# InfoTagVideo.getCast() = ''
# InfoTagVideo.getDbId() = -1
# InfoTagVideo.getDirector() = ''
# InfoTagVideo.getDirectors() = []
# InfoTagVideo.getDuration() = 0
# InfoTagVideo.getEpisode() = -1
# InfoTagVideo.getFile() = ''
# InfoTagVideo.getFilenameAndPath() = ''
# InfoTagVideo.getFirstAired() = '01.01.1970'    # Please use InfoTagVideo.getFirstAiredAsW3C().
# InfoTagVideo.getFirstAiredAsW3C() = '1970-01-01'
# InfoTagVideo.getGenre() = ''
# InfoTagVideo.getGenres() = []
# InfoTagVideo.getIMDBNumber() = ''
# InfoTagVideo.getLastPlayed() = '01.01.1970 0:00:00'   # Please use InfoTagVideo.getLastPlayedAsW3C().
# InfoTagVideo.getLastPlayedAsW3C() = '1970-01-01T01:00:00+01:00'
# InfoTagVideo.getMediaType() = ''
# InfoTagVideo.getOriginalTitle() = ''
# InfoTagVideo.getPath() = ''
# InfoTagVideo.getPictureURL() = ''
# InfoTagVideo.getPlayCount() = 0
# InfoTagVideo.getPlot() = ''
# InfoTagVideo.getPlotOutline() = ''
# InfoTagVideo.getPremiered() = '01.01.1970'      # Please use InfoTagVideo.getPremieredAsW3C().
# InfoTagVideo.getPremieredAsW3C() = '1970-01-01'
# InfoTagVideo.getRating() = 0.0
# InfoTagVideo.getResumeTime() = 0.0
# InfoTagVideo.getResumeTimeTotal() = 0.0
# InfoTagVideo.getSeason() = -1
# InfoTagVideo.getTVShowTitle() = ''
# InfoTagVideo.getTagLine() = ''
# InfoTagVideo.getTitle() = ''
# InfoTagVideo.getTrack() = -1
# InfoTagVideo.getTrailer() = ''
# InfoTagVideo.getUniqueID() = ''
# InfoTagVideo.getUserRating() = 0
# InfoTagVideo.getVotes() = '0'             # Please use InfoTagVideo.getVotesAsInt().
# InfoTagVideo.getVotesAsInt() = 0
# InfoTagVideo.getWriters() = []
# InfoTagVideo.getWritingCredits() = ''
# InfoTagVideo.getYear() = 0
