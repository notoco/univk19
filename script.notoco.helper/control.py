import xbmcaddon
import xbmcgui
import requests

# Konfiguracja
headers = {'Content-Type': 'application/json'}
addon = xbmcaddon.Addon()
icon = addon.getAddonInfo('icon')

def send_request(command, payload):
    """Wysyła żądanie do serwera Ambilight."""
    url = 'http://127.0.0.1:8090/json-rpc'
    data = {"command": command, **payload, "tan": 1}
    requests.post(url, headers=headers, json=data)

def set_setting_and_notify(name, value, message=None):
    """Ustawia wartość i wyświetla powiadomienie."""
    addon.setSetting(name, str(value))
    if message:
        send_notification("Ambilight", message)

def send_notification(komponent, message):
    xbmcgui.Dialog().notification(komponent, message, icon=icon)

# Funkcje Ambilight
def ambilight_turn_off():
    send_request("componentstate", {"componentstate": {"component": "LEDDEVICE", "state": False}})
    set_setting_and_notify('state', 'false')

def ambilight_turn_on():
    send_request("componentstate", {"componentstate": {"component": "LEDDEVICE", "state": True}})
    set_setting_and_notify('state', 'true')

def adjust_brightness(change):
    bright = int(addon.getSetting('bright')) + change
    if 0 <= bright <= 100:
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
