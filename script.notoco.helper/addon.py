# -*- coding: utf-8 -*-
import xbmc
import xbmcaddon
import xbmcgui
import control
import time
import json
import subprocess


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
        time.sleep(2)
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

    elif arg == "restart":
        dialog = xbmcgui.Dialog()

        choice = dialog.yesno(
            heading="Restart Kodi",
            message="Kodi zostanie automatycznie zrestartowane za 30 sekund.",
            yeslabel="Restartuj teraz",
            nolabel="Przerwij",
            autoclose=30000  # 30 sekund (30 000 ms)
        )

        # choice:
        # True  -> kliknięto "Restartuj teraz" LUB minęło 30 sekund (autoclose traktuje to jak Yes)
        # False -> kliknięto "Przerwij"
        if choice:
            control.send_notification("CoreELEC", "Restartuję Kodi...")
            subprocess.Popen(["systemctl", "restart", "kodi"])
        else:
            control.send_notification("CoreELEC", "Restart przerwany")
