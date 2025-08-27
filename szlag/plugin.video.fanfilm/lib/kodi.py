
from typing import NamedTuple
import xbmc


#: Kodi Version tuple type.
class version_info_type(NamedTuple):
    major: int
    minor: int = 0
    build: int = 0


def get_kodi_version_info() -> version_info_type:
    """Return major kodi version as int."""
    default = '21'
    ver = xbmc.getInfoLabel('System.BuildVersion') or default
    ver = ver.partition(' ')[0].split('.', 3)[:3]
    return version_info_type(*(int(v.partition('-')[0]) for v in ver))


#: Kodi Version tuple (always 3 elements)
#: See: `version_info_type`
version_info: version_info_type = get_kodi_version_info()

# Major version of Kodi
version: int

if version_info < (18, 9, 701):
    version = version_info.major
elif version_info < (19, 90):
    version = 19
else:
    version = version_info.major + (version_info.minor >= 90)

# Major version of Kodi
K: int = version
#: True if Kodi 18
K18: bool = (version == 18)
#: True if Kodi 19
K19: bool = (version == 19)
#: True if Kodi 20
K20: bool = (version == 20)
#: True if Kodi 21
K21: bool = (version == 21)
#: True if Kodi 22
K22: bool = (version == 22)
