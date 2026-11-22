
import json
import os
import time
import xbmc
import xbmcgui
from resources.lib import apdialog
from resources.lib.apsettings import PROFILE_COUNT

CEC_COMMANDS = ['', 'CECActivateSource', 'CECStandby', 'CECToggleState']
# what "save profile" stores: (section, category) of Settings.GetSettings
SAVE_FILTERS = [('system', 'audio'), ('player', 'videoplayer'), ('system', 'display')]
AUDIO_EXTRA = ('lookandfeel.soundskin', 'locale.audiolanguage')


def jsonrpc(method, params=None):
    request = {'jsonrpc': '2.0', 'id': 1, 'method': method}
    if params is not None:
        request['params'] = params
    return json.loads(xbmc.executeJSONRPC(json.dumps(request)))


def _typed(raw, current):
    """Convert a value from a profile file to the type of the current value (old versions saved text only)"""
    if not isinstance(raw, str) or isinstance(current, str):
        return raw
    if isinstance(current, bool):
        return raw.lower() == 'true'
    if isinstance(current, int):
        return int(raw)
    if isinstance(current, float):
        return float(raw)
    if isinstance(current, list):
        return json.loads(raw)
    return raw


class Profiles:

    def __init__(self, settings, lw, auto=False):
        """Handles audio profile switching."""
        self.LW = lw
        self.SETTINGS = settings
        self.AUTO = auto
        self.DATAPATH = settings['ADDONDATAPATH']
        self.ENABLED = [number for number in range(1, PROFILE_COUNT + 1) if settings['enabled'][number]]
        if not os.path.isdir(self.DATAPATH):
            os.makedirs(self.DATAPATH)

    # ---- public ----

    def changeProfile(self, mode):
        """mode: False = save the current settings to a profile, 'popup' = select menu,
        '0' = next profile, '1'..'10' = that profile. Returns the menu choice for 'popup'."""
        if not self.ENABLED:
            self._notification(self.SETTINGS['ADDONLANGUAGE'](32105), self.SETTINGS['notify_maintenance'])
            self.SETTINGS['ADDON'].openSettings()
            return None
        if mode is False:
            self._save()
            return None
        if mode == 'popup':
            choice = self._select(force_dialog=not xbmc.Player().isPlaying())
            if choice is not None:
                self.load(self.ENABLED[choice])
            return choice
        try:
            number = int(mode)
        except (TypeError, ValueError):
            number = -1
        if number == 0:
            self.load(self._next_profile())
        elif 1 <= number <= PROFILE_COUNT:
            self.load(number)
        else:
            self.LW.log(['Wrong argument used - use like RunScript("%s,x") x (x is the number of the profile)' %
                         self.SETTINGS['ADDONNAME']], xbmc.LOGERROR)
        return None

    def lastProfile(self):
        try:
            with open(self._path('profile')) as state_file:
                return int(state_file.read().strip())
        except (OSError, ValueError):
            return 0

    def load(self, number):
        """Apply a profile, changing only the Kodi settings that differ from it"""
        name = self.SETTINGS['names'].get(number, str(number))
        if number not in self.ENABLED:
            self._notification('%s (%s)' % (self.SETTINGS['ADDONLANGUAGE'](32103), name),
                               self.SETTINGS['notify_maintenance'])
            self.LW.log(['profile %s is disabled in addon settings' % number], xbmc.LOGINFO)
            return False
        try:
            with open(self._path('profile%d.json' % number)) as profile_file:
                profile = json.load(profile_file)
        except (OSError, ValueError) as exc:
            self._notification('%s %s (%s)' % (self.SETTINGS['ADDONLANGUAGE'](32104), number, name),
                               self.SETTINGS['notify_maintenance'])
            self.LW.log(['cannot read profile %s: %s' % (number, exc)], xbmc.LOGERROR)
            return False
        started = time.monotonic()
        changed = []
        for setting_id, raw_value in profile.items():
            if not self._wanted(setting_id):
                continue
            if setting_id == 'volume':
                if self._set_volume(raw_value):
                    changed.append(setting_id)
                continue
            current = jsonrpc('Settings.GetSettingValue', {'setting': setting_id})
            if 'result' not in current:
                self.LW.log(['setting %s does not exist in this Kodi - skipped' % setting_id])
                continue
            current_value = current['result'].get('value')
            try:
                value = _typed(raw_value, current_value)
            except ValueError:
                self.LW.log(['bad value %r for %s - skipped' % (raw_value, setting_id)])
                continue
            if value == current_value:
                continue
            result = jsonrpc('Settings.SetSettingValue', {'setting': setting_id, 'value': value})
            if 'error' in result:
                self.LW.log(['cannot set %s to %r: %s' % (setting_id, value, result['error'])])
                continue
            changed.append('%s=%r' % (setting_id, value))
        previous = self.lastProfile()
        self._write_state(number)
        self.LW.log(['profile %s (%s): %d setting(s) changed in %d ms %s' % (
            number, name, len(changed), (time.monotonic() - started) * 1000, ', '.join(changed))], xbmc.LOGINFO)
        if changed or previous != number:
            show = self.SETTINGS['notify_auto'] if self.AUTO else self.SETTINGS['notify_manual']
            self._notification(name, show)
        cec = self.SETTINGS['cec'].get(number, 0)
        if 0 < cec < len(CEC_COMMANDS):
            self.LW.log(['sending CEC command: %s' % CEC_COMMANDS[cec]], xbmc.LOGINFO)
            xbmc.executebuiltin(CEC_COMMANDS[cec])
        return True

    # ---- helpers ----

    def _path(self, filename):
        return os.path.join(self.DATAPATH, filename)

    def _wanted(self, setting_id):
        if setting_id == 'volume':
            return self.SETTINGS['volume']
        if setting_id.startswith('audiooutput.') or setting_id in AUDIO_EXTRA:
            return True
        if setting_id.startswith('videoplayer.'):
            return self.SETTINGS['player']
        return self.SETTINGS['video']  # System/Display: videoscreen.*, coreelec.amlogic.*, ...

    def _set_volume(self, raw_value):
        try:
            volume = int(raw_value)
        except (TypeError, ValueError):
            return False
        current = jsonrpc('Application.GetProperties', {'properties': ['volume']})
        if current.get('result', {}).get('volume') == volume:
            return False
        jsonrpc('Application.SetVolume', {'volume': volume})
        return True

    def _write_state(self, number):
        try:
            with open(self._path('profile'), 'w') as state_file:
                state_file.write(str(number))
        except OSError as exc:
            self.LW.log(['cannot write the last profile file: %s' % exc])

    def _next_profile(self):
        available = [number for number in self.ENABLED if os.path.exists(self._path('profile%d.json' % number))]
        if not available:
            return self.ENABLED[0]
        last = self.lastProfile()
        if last not in available:
            return available[0]
        return available[(available.index(last) + 1) % len(available)]

    def _notification(self, msg, display=True):
        if self.SETTINGS['notify'] and display:
            xbmcgui.Dialog().notification(self.SETTINGS['ADDONLONGNAME'], msg, icon=self.SETTINGS['ADDONICON'],
                                          time=self.SETTINGS['notify_time'] * 1000)

    def _select(self, force_dialog):
        buttons = [self.SETTINGS['names'][number] for number in self.ENABLED]
        choice, loglines = apdialog.Dialog().start(self.SETTINGS, title=self.SETTINGS['ADDONLANGUAGE'](32106),
                                                   buttons=buttons, force_dialog=force_dialog)
        self.LW.log(loglines)
        return choice

    def _save(self):
        choice = self._select(force_dialog=True)
        if choice is None:
            return False
        number = self.ENABLED[choice]
        values = {}
        for section, category in SAVE_FILTERS:
            response = jsonrpc('Settings.GetSettings', {'level': 'expert',
                                                        'filter': {'section': section, 'category': category}})
            for setting in response.get('result', {}).get('settings', []):
                if 'value' in setting:
                    values[setting['id']] = setting['value']
        volume = jsonrpc('Application.GetProperties', {'properties': ['volume']}).get('result', {}).get('volume')
        if volume is not None:
            values['volume'] = volume
        try:
            with open(self._path('profile%d.json' % number), 'w') as profile_file:
                json.dump(values, profile_file)
        except OSError as exc:
            self.LW.log(['cannot save profile %s: %s' % (number, exc)], xbmc.LOGERROR)
            return False
        self.LW.log(['saved %d settings to profile %s (%s)' % (
            len(values), number, self.SETTINGS['names'][number])], xbmc.LOGINFO)
        self._notification('%s %s (%s)' % (self.SETTINGS['ADDONLANGUAGE'](32102), number,
                                           self.SETTINGS['names'][number]), self.SETTINGS['notify_maintenance'])
        return True
