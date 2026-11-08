# -*- coding: utf-8 -*-
import sys
import xbmc
import control
import time


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
        control.ambilight_switch()
    elif arg == "amb_up":
        control.ambilight_bright_up()
    elif arg == "amb_down":
        control.ambilight_bright_down()
#CPU
    elif arg == "cpu":
        control.cpu()

#Hyperion restart
    elif arg == "hypereset":
        addon = control.hyperion_addon()  # the one in use, the other one stays off (the same ports)
        xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"Addons.SetAddonEnabled","id":7,"params":{"addonid": "%s","enabled":false}}' % addon)
        time.sleep(2)
        xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"Addons.SetAddonEnabled","id":7,"params":{"addonid": "%s","enabled":true}}' % addon)
        # the service sets the state, the brightness and HDR again when Hyperion is up
        xbmc.executebuiltin('NotifyAll(script.notoco.helper,amb_restore)')
