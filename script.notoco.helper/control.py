# -*- coding: utf-8 -*-
import xbmcaddon
import xbmcgui
import requests
import xbmc
import time


headers = {
    'Content-Type': 'application/json',
}
addon = xbmcaddon.Addon()
state = addon.getSetting('state')
icon = addon.getAddonInfo('icon')

def ambilight_turn_off():
    data = {"command":"componentstate", "componentstate":{"component": "LEDDEVICE", "state": False }, "tan":1}
    response = requests.post('http://127.0.0.1:8090/json-rpc', headers=headers, json=data)
    addon.setSetting('state', 'false')

def ambilight_turn_on():
    data = {"command":"componentstate", "componentstate":{"component": "LEDDEVICE", "state": True }, "tan":1}
    response = requests.post('http://127.0.0.1:8090/json-rpc', headers=headers, json=data)
    addon.setSetting('state', 'true')

def ambilight_bright_up():
    bright = int(addon.getSetting('bright'))
    if bright < 100:
        bright = bright+10
        data = {"command":"adjustment", "adjustment":{"brightness": bright }, "tan":1}
        response = requests.post('http://127.0.0.1:8090/json-rpc', headers=headers, json=data)
        addon.setSetting('bright', str(bright))
        send_notification("Ambilight", "Jasność: "+str(bright))

def ambilight_bright_down():
    bright = int(addon.getSetting('bright'))
    if bright > 10:
        bright = bright-10
        data = {"command":"adjustment", "adjustment":{"brightness": bright }, "tan":1}
        response = requests.post('http://127.0.0.1:8090/json-rpc', headers=headers, json=data)
        addon.setSetting('bright', str(bright))
        send_notification("Ambilight", "Jasność: "+str(bright))

def cpu():
    send_notification("", "[B]CPU:[/B] $INFO[System.CPUUsage] [CR][B]Temperatura:[/B] $INFO[System.CPUTemperature]   [B]RAM:[/B] $INFO[System.memory(used.percent)] [B]Up:[/B] $INFO[System.Uptime]")

def send_notification(komponent, message):
    xbmcgui.Dialog().notification(komponent, message, icon=icon)

def get_setting(name):
    return addon.getSetting(name)

def set_setting(name, value):
    addon.setSetting(name, value)
