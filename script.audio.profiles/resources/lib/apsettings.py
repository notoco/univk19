
import xbmcaddon
import xbmcvfs

PROFILE_COUNT = 10
POPUP = PROFILE_COUNT + 1  # value of an auto-switch setting that shows the select menu instead of a profile

_BOOLS = {'aggressive_music_match': False, 'volume': False, 'player': False, 'video': False,
          'player_show': False, 'force_auto_default': False, 'use_custom_skin_menu': True,
          'include_skin_mods': True, 'player_autoclose': False, 'notify': True, 'notify_auto': True,
          'notify_manual': True, 'notify_maintenance': True, 'debug': False}
_INTS = {'codec_delay': 2, 'player_autoclose_delay': 10, 'notify_time': 5}
_AUTO = ['auto_gui', 'auto_movies', 'auto_videos', 'auto_tvshows', 'auto_pvr_tv', 'auto_music',
         'auto_musicvideo', 'auto_pvr_radio', 'auto_unknown', 'auto_ac3', 'auto_eac3', 'auto_dts',
         'auto_dtshd', 'auto_truehd', 'auto_othercodec', 'auto_stereo', 'auto_multichannel', 'auto_default']


def _int(addon, name, default):
    try:
        return int(addon.getSetting(name))
    except ValueError:
        return default


def loadSettings():
    """Read the add-on settings into a dict; a fresh Addon object, so values changed in the GUI are seen"""
    addon = xbmcaddon.Addon()
    path = addon.getAddonInfo('path')
    settings = {'ADDON': addon,
                'ADDONNAME': addon.getAddonInfo('id'),
                'ADDONLONGNAME': addon.getAddonInfo('name'),
                'ADDONVERSION': addon.getAddonInfo('version'),
                'ADDONPATH': path,
                'ADDONDATAPATH': xbmcvfs.translatePath(addon.getAddonInfo('profile')),
                'ADDONICON': xbmcvfs.translatePath('%s/icon.png' % path),
                'ADDONLANGUAGE': addon.getLocalizedString,
                'version_upgrade': addon.getSetting('version_upgrade')}
    for name, default in _BOOLS.items():
        value = addon.getSetting(name).lower()
        settings[name] = value == 'true' if value in ('true', 'false') else default
    for name, default in _INTS.items():
        settings[name] = _int(addon, name, default)
    for name in _AUTO:
        settings[name] = _int(addon, name, 0)
    # profiles are numbered 1..PROFILE_COUNT
    settings['enabled'] = {}
    settings['names'] = {}
    settings['cec'] = {}
    for number in range(1, PROFILE_COUNT + 1):
        settings['enabled'][number] = addon.getSetting('profile%d' % number).lower() == 'true'
        settings['names'][number] = addon.getSetting('name%d' % number) or 'Profile %d' % number
        settings['cec'][number] = _int(addon, 'profile%d_cec' % number, 0)
    return settings
