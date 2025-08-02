# -*- coding: utf-8 -*-
import xbmcgui
import subprocess

def restart_dialog():
    dialog = xbmcgui.Dialog()

    choice = dialog.yesno(
        heading="Restart Kodi",
        line1="Kodi zostanie automatycznie zrestartowane za 30 sekund.",
        line2="Kliknij 'Przerwij', aby anulować.",
        yeslabel="Restartuj teraz",
        nolabel="Przerwij",
        autoclose=30000  # 30 sekund (30 000 ms)
    )

    # choice:
    # True  -> kliknięto "Restartuj teraz" LUB minęło 30 sekund (autoclose traktuje to jak Yes)
    # False -> kliknięto "Przerwij"
    if choice:
        xbmcgui.Dialog().notification("CoreELEC", "🔄 Restartuję Kodi...", xbmcgui.NOTIFICATION_INFO, 3000)
        subprocess.Popen(["systemctl", "restart", "kodi"])
    else:
        xbmcgui.Dialog().notification("CoreELEC", "⛔ Restart przerwany", xbmcgui.NOTIFICATION_INFO, 3000)

restart_dialog()
