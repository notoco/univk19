# -*- coding: utf-8 -*-
# *  Credits:
# *
# *  original Audio Profiles code by Regss
# *  updates and additions through v1.4.1 by notoco and CtrlGy
# *  updates and additions since v1.4.2 by pkscout
# *  2.3.0: settings diffed before writing, switch on Player.OnAVStart (notoco)

import json
import queue
import sys
import time
import xbmc
from resources.lib.xlogger import Logger
from resources.lib.apsettings import loadSettings, POPUP, PROFILE_COUNT
from resources.lib.approfiles import Profiles, jsonrpc

EVENT_POLL = 0.2  # seconds between checks of the event queue
GUI_DELAY = 1.0  # seconds after Player.OnStop before the GUI profile, so a next playlist item can start first
CONTENT_ONLY = ('auto_music', 'auto_pvr_radio', 'auto_pvr_tv')
# Kodi codec name prefix -> setting; longest first (dtshd_ma before dts, eac3 before ac3)
CODECS = (('truehd', 'auto_truehd'), ('dtshd', 'auto_dtshd'), ('dts', 'auto_dts'), ('dca', 'auto_dts'),
          ('eac3', 'auto_eac3'), ('ac3', 'auto_ac3'))
MAPTYPE = {'video': 'auto_videos', 'episode': 'auto_tvshows', 'musicvideo': 'auto_musicvideo', 'song': 'auto_music'}


def _upgrade(settings):
    if settings['version_upgrade'] != settings['ADDONVERSION']:
        settings['ADDON'].setSetting('version_upgrade', settings['ADDONVERSION'])


class apManual:

    def __init__(self):
        """Runs the audio profile switcher manually."""
        settings = loadSettings()
        logger = Logger(preamble='[Audio Profiles]', logdebug=settings['debug'])
        logger.log(['SYS.ARGV: %s' % str(sys.argv)])
        mode = sys.argv[1] if len(sys.argv) > 1 else False
        Profiles(settings, logger).changeProfile(mode)


class apMonitor(xbmc.Monitor):

    def __init__(self):
        """Background service for automatic audio profile switching."""
        xbmc.Monitor.__init__(self)
        self.EVENTS = queue.Queue()
        self.PLAYER = xbmc.Player()
        self._init_vars()
        _upgrade(self.SETTINGS)
        self.LW.log(['background monitor version %s started' % self.SETTINGS['ADDONVERSION']], xbmc.LOGINFO)
        if not self.PLAYER.isPlaying():
            self._apply(self.SETTINGS['auto_default'])
        self._run()
        self.LW.log(['background monitor version %s stopped' % self.SETTINGS['ADDONVERSION']], xbmc.LOGINFO)

    # Kodi callbacks only queue the event: the work runs in _run(), so a slow switch or
    # an open select menu never holds up Kodi's notification thread

    def onNotification(self, sender, method, data):
        if method in ('Player.OnAVStart', 'Player.OnStop', 'System.OnWake'):
            self.EVENTS.put((method, data))

    def onSettingsChanged(self):
        self.EVENTS.put(('settings', None))

    def _init_vars(self):
        self.SETTINGS = loadSettings()
        self.LW = Logger(preamble='[Audio Profiles Service]', logdebug=self.SETTINGS['debug'])
        self.PROFILES = Profiles(self.SETTINGS, self.LW, auto=True)

    def _run(self):
        gui_due = None
        # Changing passthrough makes Kodi reopen the playing file, which sends Player.OnAVStart
        # again: the file stays "handled" until playback really stops, so the switch runs once
        handled_file = None
        # Kodi runs this script's callbacks only while it waits inside waitForAbort()/sleep()
        while not self.waitForAbort(EVENT_POLL):
            try:
                method, data = self.EVENTS.get_nowait()
            except queue.Empty:
                if gui_due is not None and time.monotonic() >= gui_due:
                    gui_due = None
                    if not self.PLAYER.isPlaying():
                        handled_file = None
                        self._apply(self.SETTINGS['auto_gui'])
                continue
            self.LW.log(['event %s %s' % (method, data)])
            try:
                if method == 'settings':
                    self._init_vars()
                elif method == 'Player.OnStop':
                    gui_due = time.monotonic() + GUI_DELAY
                elif method == 'Player.OnAVStart':
                    gui_due = None
                    playing = self._playing_file()
                    if playing and playing == handled_file:
                        self.LW.log(['%s already handled - Kodi reopened it' % playing], xbmc.LOGINFO)
                        continue
                    handled_file = playing
                    self._auto_switch(json.loads(data))
                elif method == 'System.OnWake':
                    self._apply(self.SETTINGS['auto_default'])
            except Exception as exc:  # keep the service alive whatever one event does
                self.LW.log(['error handling %s: %r' % (method, exc)], xbmc.LOGERROR)

    def _apply(self, value):
        if 1 <= value <= PROFILE_COUNT:
            self.PROFILES.load(value)
        elif value == POPUP:
            self.PROFILES.changeProfile('popup')

    def _auto_switch(self, data):
        if self.SETTINGS['player_show']:
            if self.PROFILES.changeProfile('popup') is not None:
                return
        content = self._content(data)
        if content in CONTENT_ONLY:
            the_setting = self.SETTINGS[content]
        else:
            playerid = (data.get('player') or {}).get('playerid', 1)
            codec_setting, channels_setting = self._stream_settings(playerid)
            if codec_setting:
                the_setting = codec_setting
            elif channels_setting:
                the_setting = channels_setting
            elif self.SETTINGS['aggressive_music_match'] and content == 'auto_unknown':
                the_setting = self.SETTINGS['auto_music']
            else:
                the_setting = self.SETTINGS[content]
        self.LW.log(['content %s -> profile setting %s' % (content, the_setting)])
        self._apply(the_setting)

    def _stream_settings(self, playerid):
        """Return the (codec, channels) auto-switch settings of the playing audio stream. On
        Player.OnAVStart the stream is normally known at once; codec_delay is only the most to wait."""
        deadline = time.monotonic() + max(self.SETTINGS['codec_delay'], 0)
        stream = {}
        while True:
            response = jsonrpc('Player.GetProperties', {'playerid': playerid, 'properties': ['currentaudiostream']})
            stream = (response.get('result') or {}).get('currentaudiostream') or {}
            if stream.get('codec') or time.monotonic() >= deadline or self.waitForAbort(0.25):
                break
        codec = (stream.get('codec') or '').lower()
        channels = stream.get('channels') or 0
        self.LW.log(['audio stream codec %r, %s channels' % (codec, channels)])
        codec_setting = 0
        if codec:
            codec_key = next((key for prefix, key in CODECS if codec.startswith(prefix)), 'auto_othercodec')
            codec_setting = self.SETTINGS[codec_key]
        channels_setting = 0
        if channels:
            channels_setting = self.SETTINGS['auto_multichannel' if channels > 2 else 'auto_stereo']
        return codec_setting, channels_setting

    def _content(self, data):
        item = data.get('item') or {}
        item_type = item.get('type')
        if item_type in MAPTYPE:
            return MAPTYPE[item_type]
        if item_type == 'movie':
            if self._playing_file().startswith('pvr://'):
                return 'auto_pvr_tv'  # PVR recording
            return 'auto_movies' if 'id' in item else 'auto_videos'
        if item_type and 'channel' in item_type:
            channel_type = item.get('channeltype', '')
            if 'tv' in channel_type:
                return 'auto_pvr_tv'
            if 'radio' in channel_type:
                return 'auto_pvr_radio'
        if item_type == 'unknown' and self._playing_file().startswith('cdda://'):
            return 'auto_music'
        return 'auto_unknown'

    def _playing_file(self):
        try:
            return self.PLAYER.getPlayingFile()
        except RuntimeError:
            return ''
