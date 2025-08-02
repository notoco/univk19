# -*- coding: utf-8 -*-
import xbmc
import xbmcgui
import subprocess

class CountdownDialog(xbmcgui.WindowDialog):
    def __init__(self):
        super().__init__()
        self.setCoordinateResolution(0)

        # Tło okna
        self.background = xbmcgui.ControlImage(450, 250, 380, 180, 'special://xbmc/media/white.png')
        self.addControl(self.background)
        self.background.setColorDiffuse('0xCC000000')

        # Nagłówek
        self.label_heading = xbmcgui.ControlLabel(460, 260, 360, 40, 'Restart Kodi', font='font14_title', alignment=2)
        self.addControl(self.label_heading)

        # Tekst odliczania
        self.label_countdown = xbmcgui.ControlLabel(460, 300, 360, 40, '', font='font14', alignment=2)
        self.addControl(self.label_countdown)

        # Przyciski
        self.button_cancel = xbmcgui.ControlButton(460, 350, 160, 50, 'Przerwij')
        self.addControl(self.button_cancel)

        self.button_restart = xbmcgui.ControlButton(660, 350, 160, 50, 'Restartuj teraz')
        self.addControl(self.button_restart)

        self.setFocus(self.button_cancel)

        self.canceled = False
        self.restart_now = False

    def onControl(self, control):
        if control == self.button_cancel:
            self.canceled = True
            self.close()
        elif control == self.button_restart:
            self.restart_now = True
            self.close()

def show_restart_dialog():
    dialog = CountdownDialog()
    dialog.show()

    # Odliczanie 30 sekund
    for i in range(30, 0, -1):
        dialog.label_countdown.setLabel(f"Kodi zrestartuje się za {i} sek...")
        xbmc.sleep(1000)
        if dialog.canceled or dialog.restart_now:
            break

    dialog.close()

    # Logika restartu
    if dialog.restart_now or (not dialog.canceled and not dialog.restart_now):
        xbmcgui.Dialog().notification("CoreELEC", "🔄 Restartuję Kodi...", xbmcgui.NOTIFICATION_INFO, 3000)
        subprocess.Popen(["systemctl", "restart", "kodi"])
    else:
        xbmcgui.Dialog().notification("CoreELEC", "⛔ Restart przerwany", xbmcgui.NOTIFICATION_INFO, 3000)

if __name__ == "__main__":
    show_restart_dialog()
