#!/usr/bin/env python3
import os
from time import sleep

import mpv

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


if __name__ == '__main__':
    main()


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
    TraktMpvMonitor(mpv_pipe).run()


class TraktMpvMonitor(mpv.MpvMonitor):
    def __init__(self, mpv_pipe):
        super().__init__(mpv_pipe)
        self.last_pause_state = None
        self.last_playback_position = None
        self.last_path = None
        self.issue_scrobble_commands()

    def on_command_response(self, command, response):
        last_command_elements = command['command']
        if last_command_elements[0] == 'get_property':
            if last_command_elements[1] == 'pause':
                self.last_pause_state = response['data']
            elif last_command_elements[1] == 'percent-pos':
                self.last_playback_position = response['data']
            elif last_command_elements[1] == 'path':
                self.last_path = response['data']
            if self.last_pause_state is not None \
                    and self.last_playback_position is not None \
                    and self.last_path is not None:
                print('got everything for a scrobble', self.last_pause_state, self.last_playback_position,
                      self.last_path)
                self.last_pause_state = None
                self.last_playback_position = None
                self.last_path = None

    def on_event(self, event):
        print(event)
        event_name = event['event']
        if event_name == 'pause' or event_name == 'unpause' or event_name == 'seek' or event_name == 'start-file':
            self.issue_scrobble_commands()

    def issue_scrobble_commands(self):
        self.issue_command_get_property('path')
        self.issue_command_get_property('percent-pos')
        self.issue_command_get_property('pause')
