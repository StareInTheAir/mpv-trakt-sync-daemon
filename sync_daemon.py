#!/usr/bin/env python3
import json
import logging
import sys
import threading
import time
import urllib.parse

import guessit
import os
import requests

import mpv
import trakt_key_holder
import trakt_v2_oauth

log = logging.getLogger('mpvTraktSync')

TRAKT_ID_CACHE_JSON = 'trakt_ids.json'

config = None

last_is_paused = None
last_playback_position = None
last_working_dir = None
last_path = None
last_duration = None
last_file_start_timestamp = None

is_local_state_dirty = True

next_sync_timer = None
next_regular_timer = None


def on_command_response(monitor, command, response):
    global last_is_paused, last_playback_position, last_working_dir, last_path, last_duration, last_file_start_timestamp
    global next_sync_timer

    last_command_elements = command['command']
    if last_command_elements[0] == 'get_property':
        if response['error'] != 'success':
            log.warning('Command %s failed: %s', command, response)
        else:
            if last_command_elements[1] == 'pause':
                last_is_paused = response['data']
                if not last_is_paused and last_file_start_timestamp is None:
                    last_file_start_timestamp = time.time()
            elif last_command_elements[1] == 'percent-pos':
                last_playback_position = response['data']
            elif last_command_elements[1] == 'working-directory':
                last_working_dir = response['data']
            elif last_command_elements[1] == 'path':
                last_path = response['data']
            elif last_command_elements[1] == 'duration':
                last_duration = response['data']

            # log.debug('lasts:\n\t%s\n\t%s\n\t%s\n\t%s\n\t%s\n\t%s', is_local_state_dirty, last_is_paused,
            #           last_playback_position, last_working_dir, last_path, last_duration)
            if is_local_state_dirty \
                    and last_is_paused is not None \
                    and last_playback_position is not None \
                    and last_working_dir is not None \
                    and last_path is not None \
                    and last_duration is not None:
                if next_sync_timer is not None:
                    next_sync_timer.cancel()
                next_sync_timer = threading.Timer(config['seconds_between_mpv_event_and_trakt_sync'], sync_to_trakt,
                                                  (last_is_paused, last_playback_position, last_working_dir, last_path,
                                                   last_duration, last_file_start_timestamp, False))
                next_sync_timer.start()


def on_event(monitor, event):
    event_name = event['event']

    # when a new file starts, acts as a new mpv instance got connected
    if event_name == 'start-file':
        on_disconnected()
        on_connected(monitor)

    elif event_name == 'pause' or event_name == 'unpause' or event_name == 'seek':
        global is_local_state_dirty
        is_local_state_dirty = True
        issue_scrobble_commands(monitor)


def on_connected(monitor):
    global is_local_state_dirty
    is_local_state_dirty = True
    issue_scrobble_commands(monitor)


def on_disconnected():
    global last_is_paused, last_playback_position, last_working_dir, last_path, last_duration, last_file_start_timestamp
    global next_sync_timer, next_regular_timer
    global is_local_state_dirty

    if next_sync_timer is not None:
        next_sync_timer.cancel()

    if next_regular_timer is not None:
        next_regular_timer.cancel()

    if last_is_paused is not None \
            and last_playback_position is not None \
            and last_working_dir is not None \
            and last_path is not None \
            and last_duration is not None:
        threading.Thread(target=sync_to_trakt, args=(
            last_is_paused, last_playback_position, last_working_dir, last_path, last_duration,
            last_file_start_timestamp, True)).start()

    last_is_paused = None
    last_playback_position = None
    last_working_dir = None
    last_path = None
    last_duration = None
    last_file_start_timestamp = None
    is_local_state_dirty = True


def issue_scrobble_commands(monitor):
    monitor.send_get_property_command('working-directory')
    monitor.send_get_property_command('path')
    monitor.send_get_property_command('percent-pos')
    monitor.send_get_property_command('pause')
    monitor.send_get_property_command('duration')
    schedule_regular_timer(monitor)


def schedule_regular_timer(monitor):
    global next_regular_timer
    if next_regular_timer is not None:
        next_regular_timer.cancel()
    next_regular_timer = threading.Timer(config['seconds_between_regular_get_property_commands'],
                                         issue_scrobble_commands, [monitor])
    next_regular_timer.start()


def is_finished(playback_position, duration, start_time):
    if start_time is not None:
        watch_time = time.time() - start_time
        # only consider a session finished if
        #   at least a minimal playback position is reached
        # and
        #   the session is running long enough
        if playback_position >= config['percent_minimal_playback_position_before_scrobble'] \
                and watch_time >= duration * config['factor_must_watch_before_scrobble']:
            return True
    return False


def is_url(url):
    try:
        return urllib.parse.urlparse(url).scheme != ''
    except SyntaxError:
        return False


def sync_to_trakt(is_paused, playback_position, working_dir, path, duration, start_time, mpv_closed):
    do_sync = False
    print('url: %s abs: %s' % (is_url(path), os.path.isabs(path)))
    if not is_url(path) and not os.path.isabs(path):
        # If mpv is not started via double click from a file manager, but rather from a terminal,
        # the path to the video file is relative and not absolute. For the monitored_directories thing
        # to work, we need an absolute path. that's why we need the working dir
        path = os.path.join(working_dir, path)

    for monitored_directory in config['monitored_directories']:
        if path.startswith(monitored_directory):
            do_sync = True
            break

    # empty monitored_directories means: always sync
    if len(config['monitored_directories']) == 0:
        do_sync = True

    for excluded_directory in config['excluded_directories']:
        if path.startswith(excluded_directory):
            do_sync = False
            break

    if do_sync:
        guess = guessit.guessit(path)
        log.debug(guess)

        data = get_cached_trakt_data(guess)

        if data is not None:
            data['progress'] = playback_position
            data['app_version'] = '1.0.0'

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
                                headers={'trakt-api-version': '2', 'trakt-api-key': trakt_key_holder.get_id(),
                                         'Authorization': 'Bearer ' + trakt_v2_oauth.get_access_token()})
            log.info('%s %s %s', url, req.status_code, req.text)
            if 200 <= req.status_code < 300:
                global is_local_state_dirty
                is_local_state_dirty = False


def get_cached_trakt_data(guess):
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
    # if show or movie name is not found in id_cache, request trakt id from trakt API and cache it.
    # then assign dict to data, which has the structure of the json trakt expects for a scrobble call
    data = None
    if guess['type'] == 'episode':
        if guess['title'].lower() not in id_cache['shows']:
            log.info('requesting trakt id for show ' + guess['title'])
            req = requests.get('https://api.trakt.tv/search/show?field=title&query=' + guess['title'],
                               headers={'trakt-api-version': '2', 'trakt-api-key': trakt_key_holder.get_id()})
            if 200 <= req.status_code < 300 and len(req.json()) > 0:
                trakt_id = req.json()[0]['show']['ids']['trakt']
            else:
                # write n/a into cache, so that unknown shows are only requested once.
                # without n/a unknown shows would be requested each time get_cached_trakt_data_from_guess() is called
                trakt_id = 'n/a'
                log.warning('trakt request failed or unknown show ' + str(guess))
            id_cache['shows'][guess['title'].lower()] = trakt_id
        trakt_id = id_cache['shows'][guess['title'].lower()]
        if trakt_id != 'n/a':
            data = {'show': {'ids': {'trakt': id_cache['shows'][guess['title'].lower()]}},
                    'episode': {'season': guess['season'], 'number': guess['episode']}}
    elif guess['type'] == 'movie':
        if guess['title'].lower() not in id_cache['movies']:
            log.info('requesting trakt id for movie ' + guess['title'])
            req = requests.get('https://api.trakt.tv/search/movie?field=title&query=' + guess['title'],
                               headers={'trakt-api-version': '2', 'trakt-api-key': trakt_key_holder.get_id()})
            if 200 <= req.status_code < 300 and len(req.json()) > 0:
                trakt_id = req.json()[0]['movie']['ids']['trakt']
            else:
                # write n/a into cache, so that unknown movies are only requested once.
                # without n/a unknown movies would be requested each time get_cached_trakt_data_from_guess() is called
                trakt_id = 'n/a'
                log.warning('trakt request failed or unknown movie ' + str(guess))
            id_cache['movies'][guess['title'].lower()] = trakt_id
        trakt_id = id_cache['movies'][guess['title'].lower()]
        if trakt_id != 'n/a':
            data = {'movie': {'ids': {'trakt': id_cache['movies'][guess['title'].lower()]}}}
    else:
        log.warning('Unknown guessit type ' + str(guess))

    # update cached ids file
    with open(TRAKT_ID_CACHE_JSON, mode='w') as file:
        json.dump(id_cache, file)

    return data


def main():
    log.info('launched')

    with open('config.json') as file:
        global config
        config = json.load(file)

    monitor = mpv.MpvMonitor.create(on_connected, on_event, on_command_response, on_disconnected)
    try:
        trakt_v2_oauth.get_access_token()  # prompts authentication, if necessary
        while True:
            if monitor.can_open():
                # call monitor.run() as a daemon thread, so that all SIGTERMs are handled here
                # Daemon threads die automatically, when the main process ends
                thread = threading.Thread(target=monitor.run, daemon=True)
                thread.start()
                thread.join()
                # If thread joins, mpv was closed.
                log.info('mpv closed')
            else:
                # mpv not open
                # sleep before next attempt
                time.sleep(config['seconds_between_mpv_running_checks'])
    except KeyboardInterrupt:
        log.info('terminating')
        logging.shutdown()


def register_exception_handler():
    def error_catcher(*exc_info):
        log.critical("Unhandled exception", exc_info=exc_info)

    sys.excepthook = error_catcher

    # from http://stackoverflow.com/a/31622038
    """
    Workaround for `sys.excepthook` thread bug from:
    http://bugs.python.org/issue1230540

    Call once from the main thread before creating any threads.
    """

    init_original = threading.Thread.__init__

    def init(self, *args, **kwargs):
        init_original(self, *args, **kwargs)
        run_original = self.run

        def run_with_except_hook(*args2, **kwargs2):
            try:
                run_original(*args2, **kwargs2)
            except Exception:
                sys.excepthook(*sys.exc_info())

        self.run = run_with_except_hook

    threading.Thread.__init__ = init


if __name__ == '__main__':
    import logging.config

    logging.config.fileConfig('log.conf')
    register_exception_handler()

    main()
