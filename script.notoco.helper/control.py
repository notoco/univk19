# -*- coding: utf-8 -*-
import xbmcaddon
import xbmcgui
import xbmc
import time
import json
import http.client


headers = {
    'Content-Type': 'application/json',
}
HYPERION_HOST = '127.0.0.1'
HYPERION_PORT = 8090
HYPERION_TIMEOUT = 2

addon = xbmcaddon.Addon()
state = addon.getSetting('state')
icon = addon.getAddonInfo('icon')

_hyperion_conn = None

def _hyperion_request(data):
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
        send_notification("Hyperion", "Brak połączenia z Hyperion")
        return None
    result = json.loads(response_body)
    if not result.get('success', True):
        send_notification("Hyperion", "Błąd Hyperion: " + str(result.get('error', '')))
        return None
    return result

def _get_bright():
    try:
        bright = int(addon.getSetting('bright'))
    except ValueError:
        bright = 50
    return max(0, min(100, bright))

def ambilight_turn_off():
    data = {"command":"componentstate", "componentstate":{"component": "LEDDEVICE", "state": False }, "tan":1}
    if _hyperion_request(data) is not None:
        addon.setSetting('state', 'false')

def ambilight_turn_on():
    data = {"command":"componentstate", "componentstate":{"component": "LEDDEVICE", "state": True }, "tan":1}
    if _hyperion_request(data) is not None:
        addon.setSetting('state', 'true')

def ambilight_bright_up():
    bright = min(_get_bright() + 10, 100)
    data = {"command":"adjustment", "adjustment":{"brightness": bright }, "tan":1}
    if _hyperion_request(data) is not None:
        addon.setSetting('bright', str(bright))
        send_notification("Ambilight", "Jasność: "+str(bright))

def ambilight_bright_down():
    bright = max(_get_bright() - 10, 0)
    data = {"command":"adjustment", "adjustment":{"brightness": bright }, "tan":1}
    if _hyperion_request(data) is not None:
        addon.setSetting('bright', str(bright))
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
        addon.setSetting('bright', str(bright))
        send_notification("Ambilight", "Jasność ustawiona na: "+str(bright)+"%")

def cpu():
    send_notification("", "[B]CPU:[/B] $INFO[System.CPUUsage] [CR][B]Temperatura:[/B] $INFO[System.CPUTemperature]   [B]RAM:[/B] $INFO[System.memory(used.percent)] [B]Up:[/B] $INFO[System.Uptime]")

def send_notification(komponent, message):
    xbmcgui.Dialog().notification(komponent, message, icon=icon)

def get_setting(name):
    return addon.getSetting(name)

def set_setting(name, value):
    addon.setSetting(name, value)
