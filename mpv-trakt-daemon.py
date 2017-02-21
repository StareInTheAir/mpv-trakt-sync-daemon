#!/usr/bin/env python3
import os
from queue import Queue
from threading import Lock
from time import sleep
from guessit import guessit
import json

MPV_PIPE_PATH = r'\\.\pipe\mpv'
SECONDS_BETWEEN_MPV_RUNNING_CHECKS = 5


def main():
    while True:
        if os.path.isfile(MPV_PIPE_PATH):
            start_mpv_monitoring(MPV_PIPE_PATH)
            # If start_mpv_monitoring() returns, mpv was closed.
            # If we try to instantly check for MPV_PIPE_PATH and open it again, mpv crashes.
            # So we need to give mpv some time to close gracefully.
            sleep(1)
        else:
            # sleep before next attempt
            try:
                sleep(SECONDS_BETWEEN_MPV_RUNNING_CHECKS)
            except KeyboardInterrupt:
                print('terminating')
                break


def start_mpv_monitoring(pipe_path):
    command_queue = Queue()
    lock = Lock()

    mpv_pipe = None
    while mpv_pipe is None:
        try:
            mpv_pipe = open(pipe_path, 'r+b')
            # Why r+b? We want rw access, no truncate and start from beginning of file.
            # (see http://stackoverflow.com/a/30566011/2634932)
        except OSError:
            # Sometimes Windows can't open MPV_PIPE_PATH directly. I suspect a interaction between os.path.isfile()
            # and directly following open(). Sleeping for a short time and trying again seems to help.
            print('OSError. Trying again')
            sleep(0.01)

    print("opened mpv pipe")

    issue_scrobble_commands(mpv_pipe, lock, command_queue)

    while True:
        line = mpv_pipe.readline()
        if len(line) == 0:
            print('mpv was closed')
            mpv_pipe.close()
            break
        mpv_json = json.loads(line)
        print(mpv_json)
        if 'event' in mpv_json:
            handle_event(mpv_pipe, lock, command_queue, mpv_json)
        elif 'data' in mpv_json:
            handle_command_response(mpv_pipe, lock, command_queue, mpv_json)
        else:
            print('Unknown mpv output: ' + mpv_json)


last_pause_state = last_playback_position = last_path = None


def handle_command_response(mpv_pipe, lock, command_queue, response):
    global last_pause_state, last_playback_position, last_path

    last_command_elements = command_queue.get()['command']
    if last_command_elements[0] == 'get_property':
        if last_command_elements[1] == 'pause':
            last_pause_state = response['data']
        elif last_command_elements[1] == 'percent-pos':
            last_playback_position = response['data']
        elif last_command_elements[1] == 'path':
            last_path = response['data']
        if last_pause_state is not None and last_playback_position is not None and last_path is not None:
            print('got everything for a scrobble', last_pause_state, last_playback_position, last_path)
            last_pause_state = None
            last_playback_position = None
            last_path = None


def handle_event(mpv_pipe, lock, command_queue, event):
    event_name = event['event']
    if event_name == 'pause' or event_name == 'unpause' or event_name == 'seek' or event_name == 'start-file':
        issue_scrobble_commands(mpv_pipe, lock, command_queue)


def issue_scrobble_commands(mpv_pipe, lock, command_queue):
    issue_command_get_property(mpv_pipe, lock, command_queue, 'path')
    issue_command_get_property(mpv_pipe, lock, command_queue, 'percent-pos')
    issue_command_get_property(mpv_pipe, lock, command_queue, 'pause')


def issue_command(mpv_pipe, lock, command_queue, elements):
    command = {'command': elements}
    with lock:
        mpv_pipe.write(bytes(json.dumps(command), 'utf-8'))
        mpv_pipe.write(str.encode('\n'))
        command_queue.put(command)


def issue_command_get_property(mpv_pipe, lock, command_queue, property_name):
    issue_command(mpv_pipe, lock, command_queue, ['get_property', property_name])


if __name__ == '__main__':
    main()
