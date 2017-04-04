#!/usr/bin/env python3
import json
import threading
import time

import guessit
import os
import requests

import mpv
import trakt_v2_oauth

TRAKT_CLIENT_ID = '24c7a86d0a55334a9575734decac760cea679877fcb60b0983cbe45996242dd7'
TRAKT_ID_CACHE_JSON = 'trakt_ids.json'

MPV_WINDOWS_NAMED_PIPE_PATH = r'\\.\pipe\mpv'
MPV_POSIX_SOCKET_PATH = '/tmp/mpv-socket'

SECONDS_BETWEEN_MPV_RUNNING_CHECKS = 5.0
SECONDS_BETWEEN_MPV_EVENT_AND_TRAKT_SYNC = 2.0
SECONDS_BETWEEN_REGULAR_GET_PROPERTY_COMMANDS = 10.0
FACTOR_MUST_WATCH_BEFORE_SCROBBLE = 0.1
PERCENT_MINIMAL_PLAYBACK_POSITION_BEFORE_SCROBBLE = 90.0

monitored_directories = []

last_is_paused = None
last_playback_position = None
last_path = None
last_duration = None
last_file_start_timestamp = None

is_local_state_dirty = True

next_sync_timer = None
next_regular_timer = None


def on_command_response(monitor, command, response):
    global last_is_paused, last_playback_position, last_path, last_duration, last_file_start_timestamp
    global next_sync_timer, next_regular_timer
    global is_local_state_dirty

    last_command_elements = command['command']
    if last_command_elements[0] == 'get_property':
        if last_command_elements[1] == 'pause':
            last_is_paused = response['data']
            if not last_is_paused and last_file_start_timestamp is None:
                last_file_start_timestamp = time.time()
        elif last_command_elements[1] == 'percent-pos':
            last_playback_position = response['data']
        elif last_command_elements[1] == 'path':
            last_path = response['data']
        elif last_command_elements[1] == 'duration':
            last_duration = response['data']

            if is_local_state_dirty \
                    and last_is_paused is not None \
                    and last_playback_position is not None \
                    and last_path is not None \
                    and last_duration is not None:
                if next_sync_timer is not None:
                    next_sync_timer.cancel()
                next_sync_timer = threading.Timer(SECONDS_BETWEEN_MPV_EVENT_AND_TRAKT_SYNC, sync_to_trakt,
                                                  (last_is_paused, last_playback_position, last_path, last_duration,
                                                   last_file_start_timestamp, False))
                next_sync_timer.start()


def on_event(monitor, event):
    event_name = event['event']

    # when a new file starts, acts as a new mpv instance got connected
    if event_name == 'start-file':
        on_disconnected()
        on_connected(monitor)

    if event_name == 'pause' or event_name == 'unpause' or event_name == 'seek':
        global is_local_state_dirty
        is_local_state_dirty = True
        issue_scrobble_commands(monitor)


def on_connected(monitor):
    issue_scrobble_commands(monitor)


def on_disconnected():
    global last_is_paused, last_playback_position, last_path, last_duration, last_file_start_timestamp
    global next_sync_timer, next_regular_timer
    global is_local_state_dirty

    if next_sync_timer is not None:
        next_sync_timer.cancel()

    if next_regular_timer is not None:
        next_regular_timer.cancel()

    if last_is_paused is not None \
            and last_playback_position is not None \
            and last_path is not None \
            and last_duration is not None:
        sync_to_trakt(last_is_paused, last_playback_position, last_path, last_duration, last_file_start_timestamp, True)

    last_is_paused = None
    last_playback_position = None
    last_path = None
    last_duration = None
    last_file_start_timestamp = None
    is_local_state_dirty = True


def issue_scrobble_commands(monitor):
    monitor.send_get_property_command('path')
    monitor.send_get_property_command('percent-pos')
    monitor.send_get_property_command('pause')
    monitor.send_get_property_command('duration')
    schedule_regular_timer(monitor)


def schedule_regular_timer(monitor):
    global next_regular_timer
    if next_regular_timer is not None:
        next_regular_timer.cancel()
    next_regular_timer = threading.Timer(SECONDS_BETWEEN_REGULAR_GET_PROPERTY_COMMANDS, issue_scrobble_commands,
                                         [monitor])
    next_regular_timer.start()


def is_finished(playback_position, duration, start_time):
    if start_time is not None:
        watch_time = time.time() - start_time
        # only consider a session finished if
        #   at least a minimal playback position is reached
        # and
        #   the session is running long enough
        if playback_position >= PERCENT_MINIMAL_PLAYBACK_POSITION_BEFORE_SCROBBLE \
                and watch_time >= duration * FACTOR_MUST_WATCH_BEFORE_SCROBBLE:
            return True
    return False


def sync_to_trakt(is_paused, playback_position, path, duration, start_time, mpv_closed):
    print('sync_to_trakt')
    do_sync = False

    for monitored_directory in monitored_directories:
        if path.startswith(monitored_directory):
            do_sync = True
            break

    # empty monitored_directories means: always sync
    if len(monitored_directories) == 0:
        do_sync = True

    if do_sync:
        guess = guessit.guessit(path)

        # load cached ids
        if os.path.isfile(TRAKT_ID_CACHE_JSON):
            with open(TRAKT_ID_CACHE_JSON) as file:
                id_cache = json.load(file)
        else:
            id_cache = {
                'movies': {},
                'shows': {}
            }

        # constructing data to be sent to trakt
        # if show or movie name is not found in id_cache, request trakt id from trakt API and cache it
        # then assign dict to data, which has the structure of the json trakt expects for a scrobble call
        data = None
        if guess['type'] == 'episode':
            if guess['title'].lower() not in id_cache['shows']:
                print('requesting trakt id for show', guess['title'])
                req = requests.get('https://api.trakt.tv/search/show?field=title&query=' + guess['title'],
                                   headers={'trakt-api-version': '2', 'trakt-api-key': TRAKT_CLIENT_ID})
                if req.status_code == 200 and len(req.json()) > 0:
                    id_cache['shows'][guess['title'].lower()] = req.json()[0]['show']['ids']['trakt']
                else:
                    print('trakt request failed or unknown show', guess)
            data = {'show': {'ids': {'trakt': id_cache['shows'][guess['title'].lower()]}},
                    'episode': {'season': guess['season'], 'number': guess['episode']}}
        elif guess['type'] == 'movie':
            print('requesting trakt id for movie', guess['title'])
            if guess['title'].lower() not in id_cache['movies']:
                req = requests.get('https://api.trakt.tv/search/movie?field=title&query=' + guess['title'],
                                   headers={'trakt-api-version': '2', 'trakt-api-key': TRAKT_CLIENT_ID})
                if 200 <= req.status_code < 300 and len(req.json()) > 0:
                    id_cache['movies'][guess['title'].lower()] = req.json()[0]['movie']['ids']['trakt']
                else:
                    print('trakt request failed or unknown movie', guess)
            data = {'movie': {'ids': {'trakt': id_cache['movies'][guess['title'].lower()]}}}
        else:
            print('Unknown guessit type', guess)

        # update cached ids file
        with open(TRAKT_ID_CACHE_JSON, mode='w') as file:
            json.dump(id_cache, file)

        if data is not None:
            data['progress'] = playback_position
            data['app_version'] = '0.5.0'

            finished = is_finished(playback_position, duration, start_time)

            # closed  finished  paused  trakt action
            # False   False     False   start
            # False   False     True    pause
            # False   True      False   start
            # False   True      True    pause
            # True    False     False   pause
            # True    False     True    pause
            # True    True      False   stop
            # True    True      True    stop

            # is equal to:

            if mpv_closed:
                if finished:
                    # trakt is closing and finished watching
                    # trakt action: stop
                    url = 'https://api.trakt.tv/scrobble/stop'
                else:
                    # closed before finished watching
                    # trakt action: pause
                    url = 'https://api.trakt.tv/scrobble/pause'
            elif is_paused:
                # paused, while still open
                # trakt action: pause
                url = 'https://api.trakt.tv/scrobble/pause'
            else:
                # watching right now
                # trakt action: start
                url = 'https://api.trakt.tv/scrobble/start'

            req = requests.post(url,
                                json=data,
                                headers={'trakt-api-version': '2', 'trakt-api-key': TRAKT_CLIENT_ID,
                                         'Authorization': 'Bearer ' + trakt_v2_oauth.get_access_token()})
            print(url, req.status_code, req.text)
            if 200 <= req.status_code < 300:
                global is_local_state_dirty
                is_local_state_dirty = False


def main():
    monitor = mpv.MpvMonitor.create(MPV_POSIX_SOCKET_PATH, MPV_WINDOWS_NAMED_PIPE_PATH,
                                    on_connected, on_event, on_command_response, on_disconnected)
    trakt_v2_oauth.get_access_token()  # prompts authentication, if necessary
    while True:
        if monitor.can_open():
            monitor.run()
            print('mpv closed')
            # If run() returns, mpv was closed.
            # If we try to instantly check for via can_open() and open it again, mpv crashes (at least on Windows).
            # So we need to give mpv some time to close gracefully.
            time.sleep(1)
        else:
            # sleep before next attempt
            try:
                # mpv not open. sleeping
                time.sleep(SECONDS_BETWEEN_MPV_RUNNING_CHECKS)
            except KeyboardInterrupt:
                print('terminating')
                quit(0)


if __name__ == '__main__':
    main()
