#!/usr/bin/env python3
import os
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

    mpv_pipe.write(str.encode('{ "command": ["get_property", "path"] }\n'))
    path = json.loads(mpv_pipe.readline())
    print(guessit(path["data"]))

    mpv_pipe.write(str.encode('{ "command": ["get_property", "percent-pos"] }\n'))
    playback_position = json.loads(mpv_pipe.readline())
    print(playback_position)

    mpv_pipe.write(str.encode('{ "command": ["get_property", "pause"] }\n'))
    pause = json.loads(mpv_pipe.readline())
    print(pause)

    while True:
        line = mpv_pipe.readline()
        if len(line) == 0:
            print('mpv was closed')
            mpv_pipe.close()
            break
        mpv_json = json.loads(line)
        print(mpv_json)
        if 'event' in mpv_json:
            event_name = mpv_json['event']
            if event_name == 'pause':
                pass
                # TODO
            elif event_name == 'unpause' or event_name == 'seek' or event_name == 'start-file':
                mpv_pipe.write(str.encode('{ "command": ["get_property", "percent-pos"] }\n'))
                playback_position = json.loads(mpv_pipe.readline())
                print(playback_position)


if __name__ == '__main__':
    main()
