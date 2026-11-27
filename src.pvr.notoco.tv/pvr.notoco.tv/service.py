"""The |<< and >>| keys of Notoco TV in live TV.

Kodi reads keymaps only from its own folders, so the service writes one there and handles the keys:
live TV: |<< plays the running programme from its start (from the archive), >>| goes back to the
broadcast after a pause or a rewind; a programme from the archive: the previous / next programme.
"""

from __future__ import annotations

import json
from typing import Any

import xbmc
import xbmcvfs

ADDON_ID = 'pvr.notoco.tv'
KEYMAP_PATH = 'special://profile/keymaps/pvr.notoco.tv.xml'
KEYMAP = '''<keymap>
  <fullscreenlivetv>
    <keyboard>
      <key id="221">NotifyAll(pvr.notoco.tv,from_start)</key>
      <key id="223">NotifyAll(pvr.notoco.tv,skip_next)</key>
      <prev_track>NotifyAll(pvr.notoco.tv,from_start)</prev_track>
      <next_track>NotifyAll(pvr.notoco.tv,skip_next)</next_track>
    </keyboard>
    <remote>
      <skipminus>NotifyAll(pvr.notoco.tv,from_start)</skipminus>
      <skipplus>NotifyAll(pvr.notoco.tv,skip_next)</skipplus>
    </remote>
  </fullscreenlivetv>
</keymap>
'''
LIVE_EDGE_SECONDS = 15  # a live position further behind than this is time shifted


def jsonrpc(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """The result of a Kodi JSON-RPC call, empty on an error."""
    request: dict[str, Any] = {'jsonrpc': '2.0', 'id': 1, 'method': method}
    if params is not None:
        request['params'] = params
    return json.loads(xbmc.executeJSONRPC(json.dumps(request))).get('result') or {}


def playing_live_channel() -> int:
    """The id of the channel playing live (not a programme from the archive), 0 otherwise."""
    item = jsonrpc('Player.GetItem', {'playerid': 1}).get('item') or {}
    if item.get('type') != 'channel' or xbmc.getCondVisibility('PVR.IsPlayingEpgTag'):
        return 0
    return item.get('id') or 0


def from_start() -> None:
    """Live TV: the running programme from its start; otherwise Kodi's own skip back."""
    channel = playing_live_channel()
    if channel:
        details = jsonrpc('PVR.GetChannelDetails', {'channelid': channel, 'properties': ['broadcastnow']})
        broadcast = (details.get('channeldetails') or {}).get('broadcastnow') or {}
        if broadcast.get('broadcastid'):
            jsonrpc('Player.Open', {'item': {'broadcastid': broadcast['broadcastid']}})
            return
    xbmc.executebuiltin('PlayerControl(Previous)')


def skip_next() -> None:
    """Live TV: back to the broadcast (Kodi's own skip forward stops a live stream that can seek);
    otherwise Kodi's own skip forward (the next programme of an archive)."""
    if playing_live_channel():
        player = xbmc.Player()
        total = player.getTotalTime()
        if total - player.getTime() > LIVE_EDGE_SECONDS:
            player.seekTime(total - 5)
        return
    xbmc.executebuiltin('PlayerControl(Next)')


def install_keymap() -> None:
    """Writes the keymap when it differs, then Kodi reloads its keymaps."""
    with xbmcvfs.File(KEYMAP_PATH) as current:
        if current.read() == KEYMAP:
            return
    xbmcvfs.mkdirs('special://profile/keymaps/')
    with xbmcvfs.File(KEYMAP_PATH, 'w') as keymap:
        keymap.write(KEYMAP)
    xbmc.executebuiltin('Action(reloadkeymaps)')


class Monitor(xbmc.Monitor):
    """Receives the keys sent by the keymap (NotifyAll)."""

    def onNotification(self, sender: str, method: str, data: str) -> None:
        if sender != ADDON_ID:
            return
        action = method.split('.', 1)[-1]
        if action == 'from_start':
            from_start()
        elif action == 'skip_next':
            skip_next()


if __name__ == '__main__':
    install_keymap()
    Monitor().waitForAbort()
