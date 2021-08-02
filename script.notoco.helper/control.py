# -*- coding: utf-8 -*-
import xbmcaddon
import xbmcgui
import subprocess

addon = xbmcaddon.Addon()
state = addon.getSetting('state')
icon = addon.getAddonInfo('icon')

def turn_off():
    subprocess.Popen("hyperion-remote -D GRABBER", shell=True)
    addon.setSetting('state', 'false')

def turn_on():
    subprocess.Popen("hyperion-remote -E GRABBER", shell=True)
    addon.setSetting('state', 'true')

def cpu():
    send_notification("", "[B]CPU:[/B] $INFO[System.CPUUsage]  [B]Temperatura:[/B] $INFO[System.CPUTemperature]   [B]RAM:[/B] $INFO[System.memory(used.percent)] [B]Up:[/B] $INFO[System.Uptime]")

def send_notification(komponent, message):
    xbmcgui.Dialog().notification(komponent, message, icon=icon)

def get_setting(name):
    return addon.getSetting(name)

def set_setting(name, value):
    addon.setSetting(name, value)

