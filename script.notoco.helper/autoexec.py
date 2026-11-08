# -*- coding: utf-8 -*-
import xbmc
import control


class AmbilightMonitor(xbmc.Monitor):
    restore = True  # Hyperion has the values of its database (Kodi started, Hyperion restarted)

    def onNotification(self, sender, method, data):
        if sender != 'script.notoco.helper':
            return
        action = method.split('.', 1)[-1]
        if action == 'amb_up':
            control.ambilight_bright_up()
        elif action == 'amb_down':
            control.ambilight_bright_down()
        elif action == 'amb_switch':
            control.ambilight_switch()
        elif action == 'amb_restore':
            self.restore = True


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
while not monitor.abortRequested():
    if monitor.restore and control.hyperion_ready():
        monitor.restore = False
        control.ambilight_restore()
        player.hdr = None
        if player.isPlayingVideo():
            player.onAVStarted()
    if monitor.waitForAbort(2):
        break
