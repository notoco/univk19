# -*- coding: utf-8 -*- 

import threading
import xbmc
from xbmc import sleep
from . import control
from .info import ffinfo
from .log_utils import fflog, fflog_exc
from .item import FFItem
from . import player
from . import sources
import xbmcgui # Import xbmcgui for Dialog()




# Hardcoded settings
UPNEXT_TIME_SECONDS = 60  # Show window 60 seconds before the end

class PlayerMonitor: # No longer inherits from xbmc.Player
    def __init__(self, item: FFItem):
        self.item = item
        self.next_ep_item = None
        self.show_item = None # Add show_item attribute
        self.shown = False
        self.monitoring_thread = None
        self.get_next_episode()

    def get_next_episode(self):
        """Find the next episode by iterating through the show's structure."""
        if not self.item.ref.is_episode:
            fflog("[UPNEXT] Current item is not an episode.")
            return

        try:
            fflog("[UPNEXT] Searching for next episode (simple method)...")
            show_item = ffinfo.get_item(self.item.ref.show_ref, tv_episodes=True)
            if not show_item:
                fflog("[UPNEXT] Could not retrieve full show item.")
                return
            self.show_item = show_item # Store show_item as an attribute

            found_current = False
            for season in show_item.season_iter():
                for episode in season.episode_iter():
                    if found_current:
                        self.next_ep_item = episode
                        fflog(f"[UPNEXT] Found next episode: {self.next_ep_item.ref}")
                        return
                    if episode.ref == self.item.ref:
                        found_current = True
            
            if not self.next_ep_item:
                fflog("[UPNEXT] No next episode found (end of show?).")

        except Exception as e:
            fflog(f"[UPNEXT] Error getting next episode: {e}")
            fflog_exc()

    def monitor_loop(self):
        fflog("[UPNEXT] Monitoring loop started.")
        # Need to get the current player instance from xbmc
        player = xbmc.Player() # Get the active player instance
        while player.isPlayingVideo(): # Use the active player instance
            try:
                total_time = player.getTotalTime()
                current_time = player.getTime()

                if total_time > 0 and (total_time - current_time) <= UPNEXT_TIME_SECONDS:
                    if not self.shown:
                        self.shown = True
                        fflog("[UPNEXT] Triggering Up Next window.")
                        self.show_upnext_window()
                    break 
            except Exception as e:
                fflog(f"[UPNEXT] Error in monitoring loop: {e}")
                fflog_exc()
                break
            sleep(1000)
        fflog("[UPNEXT] Monitoring loop finished.")

    def clean_up(self):
        global _monitor_instance
        self.monitoring_thread = None
        _monitor_instance = None # Clear the global reference

    def show_upnext_window(self):
        """Shows the Up Next confirmation dialog."""
        try:
            dialog = xbmcgui.Dialog()
            title = "Następny odcinek" # Localized string for "Next Episode"
            message = ""
            if self.next_ep_item and self.show_item:
                message = f"{self.show_item.title}\nS{self.next_ep_item.season:02d}E{self.next_ep_item.episode:02d} - {self.next_ep_item.title}\n\nOdtworzyć następny odcinek?" # "Play next episode?"
            elif self.next_ep_item:
                message = f"{self.next_ep_item.title}\nS{self.next_ep_item.season:02d}E{self.next_ep_item.episode:02d}\n\nOdtworzyć następny odcinek?" # "Play next episode?"
            else:
                message = "Brak kolejnego odcinka." # "No next episode."

            if dialog.yesno(title, message):
                fflog("[UPNEXT] User chose to play next episode.")
                if self.next_ep_item:
                    sources.play(media_type=self.next_ep_item.ref.type, ffid=self.next_ep_item.ref.ffid, season=self.next_ep_item.ref.season, episode=self.next_ep_item.ref.episode)
            else:
                fflog("[UPNEXT] User chose not to play next episode.")

        except Exception as e:
            fflog(f"[UPNEXT] Error showing dialog: {e}")
            fflog_exc()


_monitor_instance = None

def handle_playback_started(item: FFItem):
    global _monitor_instance
    fflog("[UPNEXT] Handling playback started event.")
    if _monitor_instance:
        fflog("[UPNEXT] Clearing existing monitor instance.")
        _monitor_instance.clean_up() # Call clean_up on the old instance
    
    _monitor_instance = PlayerMonitor(item)
    _monitor_instance.monitoring_thread = threading.Thread(target=_monitor_instance.monitor_loop)
    _monitor_instance.monitoring_thread.start()

def handle_playback_stopped():
    global _monitor_instance
    fflog("[UPNEXT] Handling playback stopped event.")
    if _monitor_instance:
        fflog("[UPNEXT] Clearing monitor instance.")
        _monitor_instance = None