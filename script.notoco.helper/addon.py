import xbmc
import xbmcaddon
import control
import time
import json
import sys

# Pobranie stanu początkowego
state = control.get_setting('state')

# Funkcje pomocnicze
def toggle_addon(addon_id, enabled):
    """Przełączanie dodatku."""
    xbmc.executeJSONRPC(json.dumps({
        "jsonrpc": "2.0",
        "method": "Addons.SetAddonEnabled",
        "id": 7,
        "params": {"addonid": addon_id, "enabled": enabled}
    }))

def handle_ambilight_command(arg):
    """Obsługuje polecenia Ambilight."""
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
        toggle_addon('script.service.hyperion-control', True)
        time.sleep(2)
        toggle_addon('script.service.hyperion-control', False)

def handle_esc_command():
    """Obsługuje polecenie ESC."""
    osd = xbmc.getCondVisibility('Window.IsActive(seekbar)')
    pause = xbmc.getCondVisibility('Player.Paused')
    if osd:
        xbmc.executebuiltin("Action(Info)")
    else:
        xbmc.executebuiltin("PlayerControl(Stop)")
    if pause:
        xbmc.executebuiltin("PlayerControl(Play)")
        xbmc.executebuiltin("Action(Info)")

def handle_close_command():
    """Obsługuje polecenie CLOSE."""
    ffdialog = xbmc.getCondVisibility('Window.Is(SourcesDialog.xml)')
    xbmc.executebuiltin("Action(Close)" if ffdialog else "Action(Back)")

def handle_epg_command():
    """Obsługuje polecenie EPG."""
    playing = xbmc.getCondVisibility('Player.Playing')
    xbmc.executebuiltin('ActivateWindow(12005)' if playing else "Action(Back)")

def handle_hyperion_reset():
    """Obsługuje restart Hyperiona."""
    toggle_addon("service.hyperion.ng", False)
    time.sleep(2)
    toggle_addon("service.hyperion.ng", True)
    toggle_addon("script.service.hyperion-control", False)
    time.sleep(2)
    toggle_addon("script.service.hyperion-control", True)

def handle_fanfilm_restart():
    """Obsługuje restart Fanfilm."""
    toggle_addon("plugin.video.fanfilm", False)
    time.sleep(180)
    toggle_addon("plugin.video.fanfilm", True)

# Obsługa argumentów
if __name__ == '__main__':
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else None

    if arg:
        if arg.startswith("amb"):
            handle_ambilight_command(arg)
        elif arg == "esc":
            handle_esc_command()
        elif arg == "close":
            handle_close_command()
        elif arg == "epg":
            handle_epg_command()
        elif arg == "cpu":
            control.cpu()
        elif arg == "hypereset":
            handle_hyperion_reset()
        elif arg == "fanfilmrestart":
            handle_fanfilm_restart()
