# -*- coding: utf-8 -*-
import xbmcaddon
import xbmcgui
import xbmc
import json
import http.client


headers = {
    'Content-Type': 'application/json',
}
HYPERION_HOST = '127.0.0.1'
HYPERION_PORT = 8090
HYPERION_TIMEOUT = 2
# Hyperion.NG of CoreELEC canary (Kodi feeds the picture) is its own add-on
HYPERION_ADDONS = ('service.hyperion.canary', 'service.hyperion.ng')
HYPERION_DB = '/storage/.kodi/userdata/addon_data/%s/db/hyperion.db'
# Hyperion grabs an HDR picture before the HDR -> SDR conversion of the box (pale and dark), its own adjustment then
HDR_ADJUSTMENT = {'gammaRed': 3.5, 'gammaGreen': 3.5, 'gammaBlue': 3.5, 'saturationGain': 1.6, 'brightnessGain': 2.0}
# the saved calibration, if it can not be read from the database of Hyperion
SDR_ADJUSTMENT = {'gammaRed': 1.9, 'gammaGreen': 1.9, 'gammaBlue': 1.9, 'saturationGain': 1.15, 'brightnessGain': 1.0}

icon = xbmcaddon.Addon().getAddonInfo('icon')

_hyperion_conn = None

def _hyperion_request(data, notify=True):
    global _hyperion_conn
    body = json.dumps(data)
    response_body = None
    for attempt in (1, 2):
        try:
            if _hyperion_conn is None:
                _hyperion_conn = http.client.HTTPConnection(HYPERION_HOST, HYPERION_PORT, timeout=HYPERION_TIMEOUT)
            _hyperion_conn.request('POST', '/json-rpc', body=body, headers=headers)
            response_body = _hyperion_conn.getresponse().read()
            break
        except (OSError, http.client.HTTPException):
            try:
                _hyperion_conn.close()
            except Exception:
                pass
            _hyperion_conn = None
    if response_body is None:
        if notify:
            send_notification("Hyperion", "Brak połączenia z Hyperion")
        return None
    result = json.loads(response_body)
    if not result.get('success', True):
        send_notification("Hyperion", "Błąd Hyperion: " + str(result.get('error', '')))
        return None
    return result

def _get_bright():
    try:
        bright = int(get_setting('bright'))
    except ValueError:
        bright = 50
    return max(0, min(100, bright))

def ambilight_turn_off():
    data = {"command":"componentstate", "componentstate":{"component": "LEDDEVICE", "state": False }, "tan":1}
    if _hyperion_request(data) is not None:
        set_setting('state', 'false')

def ambilight_turn_on():
    data = {"command":"componentstate", "componentstate":{"component": "LEDDEVICE", "state": True }, "tan":1}
    if _hyperion_request(data) is not None:
        set_setting('state', 'true')

def ambilight_switch():
    if get_setting('state') == 'true':
        ambilight_turn_off()
        send_notification("Ambilight", "Wyłączono podświetlenie")
    else:
        ambilight_turn_on()
        send_notification("Ambilight", "Włączono podświetlenie")

def hyperion_ready():
    return _hyperion_request({"command":"sysinfo", "tan":1}, notify=False) is not None

def ambilight_restore():
    # Hyperion starts with the values of its database: the state and the brightness of the settings again
    if get_setting('state') == 'true':
        ambilight_turn_on()
    else:
        ambilight_turn_off()
    data = {"command":"adjustment", "adjustment":{"brightness": _get_bright() }, "tan":1}
    _hyperion_request(data)
    ambilight_idle_black()

# CoreELEC canary feeds only the playback: without any input Hyperion lets the LEDs show the last scene / white
# for a moment at the next start - a permanent black below every input instead
IDLE_PRIORITY = 250

def ambilight_idle_black():
    data = {"command": "color", "color": [0, 0, 0], "priority": IDLE_PRIORITY, "origin": "notoco helper idle", "tan": 1}
    _hyperion_request(data, notify=False)

def ambilight_bright_up():
    bright = min(_get_bright() + 10, 100)
    data = {"command":"adjustment", "adjustment":{"brightness": bright }, "tan":1}
    if _hyperion_request(data) is not None:
        set_setting('bright', str(bright))
        send_notification("Ambilight", "Jasność: "+str(bright))

def ambilight_bright_down():
    bright = max(_get_bright() - 10, 0)
    data = {"command":"adjustment", "adjustment":{"brightness": bright }, "tan":1}
    if _hyperion_request(data) is not None:
        set_setting('bright', str(bright))
        send_notification("Ambilight", "Jasność: "+str(bright))

def ambilight_set_brightness(percentage):
    try:
        bright = int(percentage)
    except (ValueError, TypeError):
        send_notification("Ambilight", "Nieprawidłowy format wartości jasności.")
        return
    if not (0 <= bright <= 100):
        send_notification("Ambilight", "Nieprawidłowa wartość jasności. Zakres 0-100.")
        return

    data = {"command":"adjustment", "adjustment":{"brightness": bright }, "tan":1}
    if _hyperion_request(data) is not None:
        set_setting('bright', str(bright))
        send_notification("Ambilight", "Jasność ustawiona na: "+str(bright)+"%")

def hyperion_addon():
    return next((addon for addon in HYPERION_ADDONS if xbmc.getCondVisibility('System.AddonIsEnabled(%s)' % addon)),
                HYPERION_ADDONS[-1])

def _saved_adjustment():
    import sqlite3
    try:
        db = sqlite3.connect('file:%s?mode=ro' % (HYPERION_DB % hyperion_addon()), uri=True, timeout=2)
        try:
            row = db.execute("SELECT config FROM settings WHERE type = 'color' AND hyperion_inst = 0").fetchone()
        finally:
            db.close()
        adjustment = json.loads(row[0])['channelAdjustment'][0]
        return {key: adjustment[key] for key in HDR_ADJUSTMENT}
    except Exception as exc:
        xbmc.log('[script.notoco.helper] Hyperion adjustment not read: %s' % exc, xbmc.LOGWARNING)
        return SDR_ADJUSTMENT

def ambilight_hdr(hdr):
    # off when Hyperion already gets an SDR picture (e.g. CoreELEC canary: Kodi sends the picture itself)
    adjustment = HDR_ADJUSTMENT if hdr and get_setting('hdr_fix') != 'false' else _saved_adjustment()
    data = {"command":"adjustment", "adjustment": adjustment, "tan":1}
    return _hyperion_request(data) is not None

def cpu():
    send_notification("", "[B]CPU:[/B] $INFO[System.CPUUsage] [CR][B]Temperatura:[/B] $INFO[System.CPUTemperature]   [B]RAM:[/B] $INFO[System.memory(used.percent)] [B]Up:[/B] $INFO[System.Uptime]")

def send_notification(komponent, message):
    xbmcgui.Dialog().notification(komponent, message, icon=icon)

# a new Addon each time: an Addon object keeps the settings of its creation (the service lives as long as Kodi)
def get_setting(name):
    return xbmcaddon.Addon().getSetting(name)

def set_setting(name, value):
    xbmcaddon.Addon().setSetting(name, value)
