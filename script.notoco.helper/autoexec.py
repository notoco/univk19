# -*- coding: utf-8 -*-
import xbmc
import control

state = control.get_setting('state')

if state == 'true':
    control.ambilight_turn_on()
else:
    control.ambilight_turn_off()

xbmc.executebuiltin('RunScript(script.notoco.helper,amb_start)')


class AmbilightMonitor(xbmc.Monitor):
    def onNotification(self, sender, method, data):
        if sender != 'script.notoco.helper':
            return
        action = method.split('.', 1)[-1]
        if action == 'amb_up':
            control.ambilight_bright_up()
        elif action == 'amb_down':
            control.ambilight_bright_down()
        elif action == 'amb_switch':
            if control.get_setting('state') == 'true':
                control.ambilight_turn_off()
                control.send_notification("Ambilight", "Wyłączono podświetlenie")
            else:
                control.ambilight_turn_on()
                control.send_notification("Ambilight", "Włączono podświetlenie")


class HdrPlayer(xbmc.Player):
    hdr = None  # unknown: Hyperion keeps its adjustment over a restart of Kodi

    def set_hdr(self, hdr):
        if hdr != self.hdr and control.ambilight_hdr(hdr):
            self.hdr = hdr

    def onAVStarted(self):
        self.set_hdr(bool(xbmc.getInfoLabel('VideoPlayer.HdrType')))

    def onPlayBackStopped(self):
        self.set_hdr(False)

    onPlayBackEnded = onPlayBackError = onPlayBackStopped


monitor = AmbilightMonitor()
player = HdrPlayer()
if player.isPlayingVideo():
    player.onAVStarted()
while not monitor.abortRequested():
    if monitor.waitForAbort(60):
        break
