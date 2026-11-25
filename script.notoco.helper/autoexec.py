# -*- coding: utf-8 -*-
import threading
import time
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import control

SPINNER_SIZE = 48
SPINNER_MARGIN = 48  # from the top right corner
SPINNER = xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo('path') + '/resources/media/spinner.gif')


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

    def set_hdr(self, hdr):
        if hdr != self.hdr and control.ambilight_hdr(hdr):
            self.hdr = hdr

    def show_spinner(self, visible):
        # Kodi sends Player.OnResume right when a TV channel switch starts, while the old
        # stream is still closing (inputstream.ffmpegdirect may take several seconds).
        # A plain image, a modal busy dialog delays the new channel. An animated GIF,
        # an animation set from Python does not run on the fullscreen video window.
        self.busy_until = time.monotonic() + 15 if visible else 0.0
        try:
            window = xbmcgui.Window(12005)
            x, y = window.getWidth() - SPINNER_SIZE - SPINNER_MARGIN, SPINNER_MARGIN
            # Every run of a script numbers its controls from 3000 again, so the spinner is
            # found by its place and size: also the one left by a previous run of this service.
            for control_id in range(3000, 3010):
                try:
                    image = window.getControl(control_id)
                except Exception:
                    continue
                if (image.getX(), image.getY(), image.getWidth()) == (x, y, SPINNER_SIZE):
                    window.removeControl(image)
            if visible:
                window.addControl(xbmcgui.ControlImage(x, y, SPINNER_SIZE, SPINNER_SIZE, SPINNER))
        except Exception as exc:
            xbmc.log('[notoco.helper] spinner: %s' % exc, xbmc.LOGWARNING)

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
player.show_spinner(False)  # the one a previous run left, e.g. killed during a channel switch
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
player.show_spinner(False)  # a control added from Python would outlive this script
