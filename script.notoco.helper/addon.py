# -*- coding: utf-8 -*-
import xbmc
import xbmcaddon
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
        control.ambilight_turn_on()
    elif arg == "amb_off":
        control.ambilight_turn_off()
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
        time.sleep(5) 
        xbmcaddon.Addon('script.service.hyperion-control').setSetting('menuEnabled', 'false')     
#ESC
    elif arg == "esc":
        osd = xbmc.getCondVisibility('Window.IsActive(seekbar)')
        pause = xbmc.getCondVisibility('Player.Paused')
        if (osd == True):  
            xbmc.executebuiltin("Action(Info)")
        else:
            xbmc.executebuiltin("PlayerControl(Stop)")
        if (pause == True):  
            xbmc.executebuiltin("PlayerControl(Play)")
            xbmc.executebuiltin("Action(Info)")
     
#CLOSE
    elif arg == "close":
        ffdialog = xbmc.getCondVisibility('Window.Is(SourcesDialog.xml)')
        if (ffdialog == True):  
            xbmc.executebuiltin("Action(Close)")
        else:
            xbmc.executebuiltin("Action(Back)")
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
        time.sleep(2)
        xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"Addons.SetAddonEnabled","id":7,"params":{"addonid": "service.hyperion.ng","enabled":true}}')
        xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"Addons.SetAddonEnabled","id":7,"params":{"addonid": "script.service.hyperion-control","enabled":false}}')
        time.sleep(2)
        xbmc.executeJSONRPC('{"jsonrpc":"2.0","method":"Addons.SetAddonEnabled","id":7,"params":{"addonid": "script.service.hyperion-control","enabled":true}}')







