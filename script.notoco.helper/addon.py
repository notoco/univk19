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
    """Przełącza stan dodatku."""
    xbmc.executeJSONRPC(json.dumps({
        "jsonrpc": "2.0",
        "method": "Addons.SetAddonEnabled",
        "id": 7,
        "params": {"addonid": addon_id, "enabled": enabled}
    }))

def restart_addon(addon_id, delay=2):
    """Restartuje dodatek z opcjonalnym opóźnieniem."""
    toggle_addon(addon_id, False)
    time.sleep(delay)
    toggle_addon(addon_id, True)

def handle_ambilight_command(arg):
    """Obsługuje polecenia Ambilight."""
    commands = {
        "amb_on": control.ambilight_turn_on,
        "amb_off": control.ambilight_turn_off,
        "amb_up": control.ambilight_bright_up,
        "amb_down": control.ambilight_bright_down,
        "amb_start": lambda: restart_addon('script.service.hyperion-control')
    }
    if arg in commands:
        commands[arg]()
    elif arg == "amb_switch":
        if state == 'true':
            control.ambilight_turn_off()
            control.send_notification("Ambilight", "Wyłączono podświetlenie")
        else:
            control.ambilight_turn_on()
            control.send_notification("Ambilight", "Włączono podświetlenie")

def handle_esc_command():
    """Obsługuje polecenie ESC."""
    if xbmc.getCondVisibility('Window.IsActive(seekbar)'):
        xbmc.executebuiltin("Action(Info)")
    else:
        xbmc.executebuiltin("PlayerControl(Stop)")
    if xbmc.getCondVisibility('Player.Paused'):
        xbmc.executebuiltin("PlayerControl(Play)")
        xbmc.executebuiltin("Action(Info)")

def handle_close_command():
    """Obsługuje polecenie CLOSE."""
    if xbmc.getCondVisibility('Window.Is(SourcesDialog.xml)'):
        xbmc.executebuiltin("Action(Close)")
    else:
        xbmc.executebuiltin("Action(Back)")

def handle_epg_command():
    """Obsługuje polecenie EPG."""
    xbmc.executebuiltin('ActivateWindow(12005)' if xbmc.getCondVisibility('Player.Playing') else "Action(Back)")

def handle_hyperion_reset():
    """Obsługuje restart Hyperiona."""
    restart_addon("service.hyperion.ng")
    restart_addon("script.service.hyperion-control")

def handle_fanfilm_restart():
    """Obsługuje restart Fanfilm."""
    restart_addon("plugin.video.fanfilm", delay=180)

# Obsługa argumentów
if __name__ == '__main__':
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else None
    command_handlers = {
        "esc": handle_esc_command,
        "close": handle_close_command,
        "epg": handle_epg_command,
        "cpu": control.cpu,
        "hypereset": handle_hyperion_reset,
        "fanfilmrestart": handle_fanfilm_restart
    }
    
    if arg:
        if arg.startswith("amb"):
            handle_ambilight_command(arg)
        elif arg in command_handlers:
            command_handlers[arg]()
