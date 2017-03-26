#!/usr/bin/env python3
from time import sleep

import mpv

MPV_WINDOWS_NAMED_PIPE_PATH = r'\\.\pipe\mpv'
MPV_POSIX_SOCKET_PATH = '/tmp/mpv-socket'
SECONDS_BETWEEN_MPV_RUNNING_CHECKS = 5

last_pause_state = None
last_playback_position = None
last_path = None


def on_command_response(monitor, command, response):
    global last_pause_state, last_playback_position, last_path
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
            pass
            # print('got everything for a scrobble', last_pause_state, last_playback_position,
            #       last_path)
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


def main():
    monitor = mpv.MpvMonitor.create(MPV_POSIX_SOCKET_PATH, MPV_WINDOWS_NAMED_PIPE_PATH, issue_scrobble_commands,
                                    on_event, on_command_response)
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
