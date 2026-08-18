# -*- coding: utf-8 -*-
import sys
import xbmc
import xbmcaddon
import control
import time


state = control.get_setting('state')
if __name__ == '__main__':
    arg = None
    brightness_percentage = None

    try:
       arg = sys.argv[1].lower()
       if len(sys.argv) > 2:
           brightness_percentage = int(sys.argv[2])
    except Exception:
       pass
# AMBILIGHT
    if arg == "amb_on":
        control.ambilight_turn_on()
    elif arg == "amb_off":
        control.ambilight_turn_off()
    elif arg == "amb_set_brightness":
        if brightness_percentage is not None:
            control.ambilight_set_brightness(brightness_percentage)
        else:
            control.send_notification("Ambilight", "Brak wartości procentowej jasności dla 'amb_set_brightness'")
    elif arg == "amb_switch":
        if state == 'true':
            control.ambilight_turn_off()
            control.send_notification("Ambilight", "Wyłączono podświetlenie")
        else:
            control.ambilight_turn_on()
            control.send_notification("Ambilight", "Włączono podświetlenie")
    elif arg == "amb_up":
        control.ambilight_bright_up()
    elif arg == "amb_down":
        control.ambilight_bright_down()
    elif arg == "amb_start":
        xbmcaddon.Addon('script.service.hyperion-control').setSetting('menuEnabled', 'true')
        time.sleep(2)
        xbmcaddon.Addon('script.service.hyperion-control').setSetting('menuEnabled', 'false')
#CPU
    elif arg == "cpu":
        control.cpu()

#Hyperion restart
    elif arg == "hypereset":
        xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"Addons.SetAddonEnabled","id":7,"params":{"addonid": "service.hyperion.ng","enabled":false}}')
        time.sleep(2)
        xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"Addons.SetAddonEnabled","id":7,"params":{"addonid": "service.hyperion.ng","enabled":true}}')
        xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"Addons.SetAddonEnabled","id":7,"params":{"addonid": "script.service.hyperion-control","enabled":false}}')
        time.sleep(2)
        xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"Addons.SetAddonEnabled","id":7,"params":{"addonid": "script.service.hyperion-control","enabled":true}}')
