#!/usr/bin/env python3
import json
import threading
from time import sleep

import guessit
import os
import requests

import mpv

TRAKT_CLIENT_ID = '24c7a86d0a55334a9575734decac760cea679877fcb60b0983cbe45996242dd7'
TRAKT_ID_CACHE_JSON = 'trakt-ids.json'
MPV_WINDOWS_NAMED_PIPE_PATH = r'\\.\pipe\mpv'
MPV_POSIX_SOCKET_PATH = '/tmp/mpv-socket'
SECONDS_BETWEEN_MPV_RUNNING_CHECKS = 5
SECONDS_BETWEEN_MPV_EVENT_AND_TRAKT_SYNC = 1

monitored_directories = ['/mnt/sybefra/', '/run/media/hans/wde/',
                         'http://syncthing-hub-becker-frankfurt-odroid:1113/']

last_pause_state = None
last_playback_position = None
last_path = None

last_timer = None


def on_command_response(monitor, command, response):
    global last_pause_state, last_playback_position, last_path
    global last_timer

    last_command_elements = command['command']
    if last_command_elements[0] == 'get_property':
        if last_command_elements[1] == 'pause':
            last_pause_state = response['data']
        elif last_command_elements[1] == 'percent-pos':
            last_playback_position = response['data']
        elif last_command_elements[1] == 'path':
            last_path = response['data']
        if last_pause_state is not None \
                and last_playback_position is not None \
                and last_path is not None:
            if last_timer is not None:
                last_timer.cancel()
            last_timer = threading.Timer(SECONDS_BETWEEN_MPV_EVENT_AND_TRAKT_SYNC, sync_to_trakt,
                                         (last_pause_state, last_playback_position, last_path))
            last_timer.start()
            last_pause_state = None
            last_playback_position = None
            last_path = None


def on_event(monitor, event):
    print(event)
    event_name = event['event']
    if event_name == 'pause' or event_name == 'unpause' or event_name == 'seek' or event_name == 'start-file':
        issue_scrobble_commands(monitor)


def issue_scrobble_commands(monitor):
    monitor.send_get_property_command('path')
    monitor.send_get_property_command('percent-pos')
    monitor.send_get_property_command('pause')


def sync_to_trakt(pause_state, playback_position, path):
    for monitored_directory in monitored_directories:
        if path.startswith(monitored_directory):
            guess = guessit.guessit(path)

            # load cached ids
            if os.path.exists(TRAKT_ID_CACHE_JSON):
                with open(TRAKT_ID_CACHE_JSON) as file:
                    id_cache = json.load(file)
            else:
                id_cache = {
                    'movies': {},
                    'shows': {}
                }

            if guess['type'] == 'episode':
                if guess['title'].lower() not in id_cache['shows']:
                    req = requests.get('https://api.trakt.tv/search/show?field=title&query=%s' % guess['title'],
                                       headers={'trakt-api-version': '2', 'trakt-api-key': TRAKT_CLIENT_ID})
                    if req.status_code == 200 and len(req.json()) > 0:
                        id_cache['shows'][guess['title'].lower()] = req.json()[0]['show']['ids']['trakt']
                    else:
                        print('trakt request failed or unknown show', guess)
                print('scrobbling show', id_cache['shows'][guess['title'].lower()])
            elif guess['type'] == 'movie':
                if guess['title'].lower() not in id_cache['movies']:
                    req = requests.get('https://api.trakt.tv/search/movie?field=title&query=%s' % guess['title'],
                                       headers={'trakt-api-version': '2', 'trakt-api-key': TRAKT_CLIENT_ID})
                    if req.status_code == 200 and len(req.json()) > 0:
                        id_cache['movies'][guess['title'].lower()] = req.json()[0]['movie']['ids']['trakt']
                    else:
                        print('trakt request failed or unknown movie', guess)
                print('scrobbling movie', id_cache['movies'][guess['title'].lower()])
            else:
                print('Unknown guessit type', guess['type'])

            # update cached ids file
            with open(TRAKT_ID_CACHE_JSON, mode='w') as file:
                json.dump(id_cache, file)

            return


def on_disconnected():
    if last_timer is not None:
        last_timer.cancel()


def main():
    monitor = mpv.MpvMonitor.create(MPV_POSIX_SOCKET_PATH, MPV_WINDOWS_NAMED_PIPE_PATH, issue_scrobble_commands,
                                    on_event, on_command_response, on_disconnected)
    while True:
        if monitor.can_open():
            monitor.run()
            print('mpv closed')
            # If run() returns, mpv was closed.
            # If we try to instantly check for via can_open() and open it again, mpv crashes (at least on Windows).
            # So we need to give mpv some time to close gracefully.
            sleep(1)
        else:
            # sleep before next attempt
            try:
                print('mpv not open sleeping')
                sleep(SECONDS_BETWEEN_MPV_RUNNING_CHECKS)
            except KeyboardInterrupt:
                print('terminating')
                break


if __name__ == '__main__':
    main()
