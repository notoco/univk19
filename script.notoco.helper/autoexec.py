# -*- coding: utf-8 -*-
import threading
import time
import xbmc
import xbmcaddon
import xbmcgui
import control

SPINNER = xbmcgui.WindowXMLDialog('notoco-spinner.xml', xbmcaddon.Addon().getAddonInfo('path'), 'Default', '1080i')


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
    from_menu = True  # a start from the menu brightens the LEDs, a change of the TV channel does not
    paused = False
    busy_until = 0.0  # monotonic deadline of the channel switch spinner, 0 = not shown
    spinner = False  # the spinner dialog is shown

    def set_hdr(self, hdr):
        if hdr != self.hdr and control.ambilight_hdr(hdr):
            self.hdr = hdr

    def show_spinner(self, visible):
        # Kodi sends Player.OnResume right when a TV channel switch starts, while the old
        # stream is still closing (inputstream.ffmpegdirect may take several seconds).
        # Own small dialog, the modal busy dialog delays the new channel.
        self.busy_until = time.monotonic() + 15 if visible else 0.0
        if visible != self.spinner:
            self.spinner = visible
            if visible:
                SPINNER.show()
            else:
                SPINNER.close()

    def onPlayBackStarted(self):
        if self.from_menu:
            control.ambilight_fade_start()

    def onAVStarted(self):
        self.show_spinner(False)
        self.set_hdr(bool(xbmc.getInfoLabel('VideoPlayer.HdrType')))
        if self.from_menu:
            self.from_menu = False
            threading.Thread(target=control.ambilight_fade_in, args=(monitor, self), daemon=True).start()

    def onPlayBackPaused(self):
        self.paused = True
        control.ambilight_pause(True)

    def onPlayBackResumed(self):
        if not self.paused and xbmc.getCondVisibility('PVR.IsPlayingTV'):
            self.show_spinner(True)
        self.paused = False
        control.ambilight_pause(False)

    def onPlayBackStopped(self):
        self.paused = False
        self.show_spinner(False)
        control.ambilight_pause(False)
        self.from_menu = True
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
    if player.busy_until and time.monotonic() > player.busy_until:
        player.show_spinner(False)  # safety net when the new channel never starts
    if monitor.waitForAbort(2):
        break
player.show_spinner(False)
