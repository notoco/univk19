import xbmcaddon
import xbmcgui
import requests

# Stałe
HEADERS = {'Content-Type': 'application/json'}
URL = 'http://127.0.0.1:8090/json-rpc'
addon = xbmcaddon.Addon()
ICON = addon.getAddonInfo('icon')

def get_setting(name):
    return addon.getSetting(name)

def set_setting(name, value):
    addon.setSetting(name, value)

def send_request(command, payload):
    """Wysyła żądanie do serwera Ambilight."""
    data = {"command": command, **payload, "tan": 1}
    try:
        response = requests.post(URL, headers=HEADERS, json=data)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        xbmcgui.Dialog().notification("Błąd", str(e), icon=ICON)
        return None

def set_setting_and_notify(name, value, message=None):
    """Ustawia wartość i wyświetla powiadomienie."""
    set_setting(name, str(value))
    if message:
        send_notification("Ambilight", message)

def send_notification(komponent, message):
    xbmcgui.Dialog().notification(komponent, message, icon=ICON)

# Funkcje Ambilight
def ambilight_turn_off():
    send_request("componentstate", {"componentstate": {"component": "LEDDEVICE", "state": False}})
    set_setting_and_notify('state', 'false')

def ambilight_turn_on():
    send_request("componentstate", {"componentstate": {"component": "LEDDEVICE", "state": True}})
    set_setting_and_notify('state', 'true')

def adjust_brightness(change):
    bright = int(get_setting('bright')) + change
    bright = max(0, min(100, bright))  # Ograniczenie do przedziału 0-100
    send_request("adjustment", {"adjustment": {"brightness": bright}})
    set_setting_and_notify('bright', bright, f"Jasność: {bright}")

def ambilight_bright_up():
    adjust_brightness(10)

def ambilight_bright_down():
    adjust_brightness(-10)

def cpu():
    """Wyświetla informacje o CPU i RAM."""
    info = ("[B]CPU:[/B] $INFO[System.CPUUsage] [CR]"
            "[B]Temperatura:[/B] $INFO[System.CPUTemperature] "
            "[B]RAM:[/B] $INFO[System.memory(used.percent)] "
            "[B]Up:[/B] $INFO[System.Uptime]")
    send_notification("", info)
