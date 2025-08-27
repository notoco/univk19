# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, unicode_literals, print_function

import sys

PY = sys.version_info[0]
PY2 = PY == 2
PY3 = PY == 3

try:
    import xbmcaddon
    addon_name = xbmcaddon.Addon().getAddonInfo("name")
except ModuleNotFoundError:
    addon_name = '???'
