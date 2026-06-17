from __future__ import (
    division, absolute_import, print_function, unicode_literals
)

import json

import requests
import xbmc
import xbmcaddon
from kodi_six.utils import py2_decode

from .utils import get_device_id, get_version, load_user_details, save_user_details
from .lazylogger import LazyLogger

log = LazyLogger(__name__)


class API:
    def __init__(self, server=None, user_id=None, token=None):
        self.server = server
        self.user_id = user_id
        self.token = token

        self.settings = xbmcaddon.Addon()

        self.headers = {}
        self.create_headers()
        self.verify_cert = settings.getSetting('verify_cert') == 'true'
        self._token_cleared = False

    def get(self, path):
        if 'Authorization' not in self.headers or self.token not in self.headers:
            self.create_headers(True)

        # Fixes initial login where class is initialized before wizard completes
        if not self.server:
            self.settings = xbmcaddon.Addon()
            self.server = self.settings.getSetting('server_address')

        url = '{}{}'.format(self.server, path)

        r = None
        try:
            r = requests.get(url, headers=self.headers, verify=self.verify_cert, timeout=(5, 60))
            r.raise_for_status()
            try:
                '''
                The requests library defaults to using simplejson to handle
                json decoding.  On low power devices and using Py3, this is
                significantly slower than the builtin json library.  Skip that
                and just parse the json ourselves.  Fall back to using
                requests/simplejson if there's a parsing error.
                '''
                response_data = json.loads(r.text)
            except ValueError:
                response_data = r.json()
        except requests.exceptions.HTTPError as e:
            if r is not None and r.status_code == 401:
                self._handle_auth_expired()
            else:
                log.error('GET HTTP error: {} | url={}'.format(e, path))
            response_data = {}
        except Exception as e:
            log.error('GET failed: {} | url={}'.format(e, path))
            response_data = {}
        return response_data

    def post(self, url, payload={}):
        if 'Authorization' not in self.headers or self.token not in self.headers:
            self.create_headers(True)

        url = '{}{}'.format(self.server, url)

        r = None
        try:
            r = requests.post(url, json=payload, headers=self.headers, verify=self.verify_cert, timeout=5)
            r.raise_for_status()
            try:
                # Much faster on low power devices, see above comment
                response_data = json.loads(r.text)
            except ValueError:
                response_data = r.json()
        except requests.exceptions.HTTPError as e:
            log.error('POST HTTP error: {} | url={}'.format(e, url))
            response_data = {}
        except Exception as e:
            log.error('POST failed: {} | url={}'.format(e, url))
            response_data = {}
        return response_data

    def delete(self, url):
        if 'Authorization' not in self.headers or self.token not in self.headers:
            self.create_headers(True)

        url = '{}{}'.format(self.server, url)

        try:
            requests.delete(url, headers=self.headers, verify=self.verify_cert, timeout=5)
        except Exception:
            pass

    def authenticate(self, auth_data):
        # Always force create fresh headers during authentication
        self.create_headers(True)
        response = self.post('/Users/AuthenticateByName', auth_data)
        token = response.get('AccessToken')
        if token:
            self.token = token
            self.user_id = response.get('User').get('Id')
            # Create headers again to include auth token
            self.create_headers()
            return response
        else:
            log.error('Unable to authenticate to Jellyfin server')
            return {}

    def create_headers(self, force=False):

        # If the headers already exist with an auth token, return unless we're regenerating
        if self.headers and 'Authorization' in self.headers.get('Authorization', '') and force is False:
            return

        headers = {}
        device_name = self.settings.getSetting('deviceName')
        if len(device_name) == 0:
            device_name = "JellyCon"
        # Ensure ascii and remove invalid characters
        device_name = py2_decode(device_name).replace('"', '_').replace(',', '_')
        device_id = get_device_id()
        version = get_version()

        authorization = (
            'MediaBrowser Client="Kodi JellyCon", Device="{device}", '
            'DeviceId="{device_id}", Version="{version}"'
        ).format(
            device=device_name,
            device_id=device_id,
            version=version
        )

        headers['Authorization'] = authorization

        # If we have a valid token, ensure it's included in the headers unless we're regenerating
        if self.token and force is False:
            headers['Authorization'] += ", Token={}".format(self.token)
        else:
            # Check for updated credentials since initialization
            user_details = load_user_details()
            token = user_details.get('token')
            if token:
                self.token = token
                headers['Authorization'] += ", Token={}".format(self.token)

        # Kodi doesn't support br or zstd compression, exclude them
        headers['Accept-Encoding'] = 'gzip, deflate'

        # Make headers available to api calls
        self.headers = headers

    def _handle_auth_expired(self):
        log.error('Authentication token expired (401) - attempting silent re-authentication')
        settings = xbmcaddon.Addon()
        username = settings.getSetting('username')

        # Try silent re-auth using saved password before touching auth.json
        user_details = load_user_details()
        saved_password = user_details.get('password')
        if username and saved_password is not None:
            self.token = None
            self.create_headers(True)
            auth = self.authenticate({'username': username, 'pw': saved_password})
            if auth:
                log.info('Silent re-authentication successful for {}'.format(username))
                self._token_cleared = False
                return

        # No saved password or re-auth failed — clear token and prompt user
        self.token = None
        if username and self.user_id:
            save_user_details(username, self.user_id, None)
        if not self._token_cleared:
            self._token_cleared = True
            xbmc.executebuiltin(
                'Notification(JellyCon,Session expired. Please re-open the addon to log in again.,8000,DefaultIconError.png)'
            )

    def post_capabilities(self):
        url = '/Sessions/Capabilities/Full'

        data = {
            'SupportsMediaControl': True,
            'PlayableMediaTypes': ["Video", "Audio"],
            'SupportedCommands': ["MoveUp",
                                  "MoveDown",
                                  "MoveLeft",
                                  "MoveRight",
                                  "Select",
                                  "Back",
                                  "ToggleContextMenu",
                                  "ToggleFullscreen",
                                  "ToggleOsdMenu",
                                  "GoHome",
                                  "PageUp",
                                  "NextLetter",
                                  "GoToSearch",
                                  "GoToSettings",
                                  "PageDown",
                                  "PreviousLetter",
                                  "TakeScreenshot",
                                  "VolumeUp",
                                  "VolumeDown",
                                  "ToggleMute",
                                  "SendString",
                                  "DisplayMessage",
                                  "SetAudioStreamIndex",
                                  "SetSubtitleStreamIndex",
                                  "SetRepeatMode",
                                  "Mute",
                                  "Unmute",
                                  "SetVolume",
                                  "PlayNext",
                                  "Play",
                                  "Playstate",
                                  "PlayMediaSource"]
        }

        self.post(url, data)

    def speedtest(self, test_data_size):
        self.create_headers()

        url = '{}/playback/bitratetest?size={}'.format(self.server, test_data_size)
        # Because this needs the stream argument, this doesn't go through self.get()
        response = requests.get(url, stream=True, headers=self.headers, verify=self.verify_cert)

        return response


settings = xbmcaddon.Addon()
user_details = load_user_details()
api = API(
    settings.getSetting('server_address'),
    user_details.get('user_id'),
    user_details.get('token')
)
