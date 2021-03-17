# -*- coding: utf-8 -*-
import xbmc
import control
import time
import json


state = control.get_setting('state')
if __name__ == '__main__':
    arg = None

    try:
       arg = sys.argv[1].lower()
    except Exception:
       pass
# AMBILIGHT
    if arg == "amb_on":
        control.turn_on()
    elif arg == "amb_off":
        control.turn_off()
    elif arg == "amb_switch":
        if state == 'true':
            control.turn_off()
            control.send_notification("Ambilight", "Wyłączono podświetlenie")
        else:
            control.turn_on()
            control.send_notification("Ambilight", "Włączono podświetlenie")

#ESC
    elif arg == "esc":
        osd = xbmc.getCondVisibility('Window.IsActive(seekbar)')
        pause = xbmc.getCondVisibility('Player.Paused')
        if (osd == True):  
            xbmc.executebuiltin("Action(Info)")
        else:
            xbmc.executebuiltin("Action(Stop)")
        if (pause == True):  
            xbmc.executebuiltin("Action(Play)")
            
#EPG
    elif arg == "epg":
        playing = xbmc.getCondVisibility('Player.Playing')
        if (playing == True):  
            xbmc.executebuiltin('ActivateWindow(12005)')
        else:
            xbmc.executebuiltin("Action(Back)")
#CPU
    elif arg == "cpu":
        control.cpu()
        
#Hyperion restart
    elif arg == "hypereset":
        xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"Addons.SetAddonEnabled","id":7,"params":{"addonid": "service.hyperion.ng","enabled":false}}')
        xbmc.sleep(2)
        xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"Addons.SetAddonEnabled","id":7,"params":{"addonid": "service.hyperion.ng","enabled":true}}')
        xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"Addons.SetAddonEnabled","id":7,"params":{"addonid": "script.service.hyperion-control","enabled":false}}')
        xbmc.sleep(2)
        xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"Addons.SetAddonEnabled","id":7,"params":{"addonid": "script.service.hyperion-control","enabled":true}}')






