import json
import socket
import sys
import threading
import logging
from time import sleep

import os

log = logging.getLogger('mpvTraktSync')


class MpvMonitor:
    @staticmethod
    def create(on_connected=None, on_event=None, on_command_response=None, on_disconnected=None,
               mpv_ipc_path='auto-detect'):

        if mpv_ipc_path == 'auto-detect':
            if os.name == 'posix':
                config_path = os.path.expanduser('~/.config/mpv/mpv.conf')
            elif os.name == 'nt':
                config_path = os.path.expandvars('%APPDATA%\\mpv\\mpv.conf')
            else:
                log.critical('Unknown operating system: ' + os.name)
                sys.exit(11)
            lines = open(config_path).readlines()
            for line in lines:
                stripped_line = line.strip()
                if stripped_line.startswith('input-ipc-server='):
                    mpv_ipc_path = stripped_line[stripped_line.index('=') + 1:]
                    break
            if mpv_ipc_path == 'auto-detect':
                log.critical('Could not auto-detect mpv IPC path. '
                      'Make sure you have a input-ipc-server=<path> entry in your mpv.conf')
                sys.exit(22)

        if os.name == 'posix':
            return PosixMpvMonitor(mpv_ipc_path, on_connected, on_event, on_command_response, on_disconnected)
        elif os.name == 'nt':
            return WindowsMpvMonitor(mpv_ipc_path, on_connected, on_event, on_command_response, on_disconnected)
        else:
            log.critical('Unknown operating system: ' + os.name, file=sys.stderr)
            sys.exit(11)

    def __init__(self, on_connected, on_event, on_command_response, on_disconnected):
        self.lock = threading.Lock()
        self.command_counter = 1
        self.sent_commands = {}
        self.on_connected = on_connected
        self.on_event = on_event
        self.on_command_response = on_command_response
        self.on_disconnected = on_disconnected

    def run(self):
        pass

    def write(self, data):
        pass

    def on_line(self, line):
        try:
            mpv_json = json.loads(line)
        except json.JSONDecodeError:
            log.warning('invalid JSON received. skipping. ' + line)
            return
        log.debug(mpv_json)
        if 'event' in mpv_json:
            if self.on_event is not None:
                self.on_event(self, mpv_json)
        elif 'request_id' in mpv_json:
            with self.lock:
                request_id = mpv_json['request_id']
                if request_id not in self.sent_commands:
                    log.warning('got response for unsent command request ' + mpv_json)
                else:
                    if self.on_command_response is not None:
                        self.on_command_response(self, self.sent_commands[request_id], mpv_json)
                    del self.sent_commands[request_id]
        else:
            log.warning('Unknown mpv output: ' + line)

    def fire_connected(self):
        if self.on_connected is not None:
            self.on_connected(self)

    def fire_disconnected(self):
        if self.on_disconnected is not None:
            self.on_disconnected()

    def send_command(self, elements):
        command = {'command': elements, 'request_id': self.command_counter}
        with self.lock:
            self.sent_commands[self.command_counter] = command
            self.command_counter += 1
            self.write(str.encode(json.dumps(command) + '\n'))

    def send_get_property_command(self, property_name):
        self.send_command(['get_property', property_name])


class PosixMpvMonitor(MpvMonitor):
    def __init__(self, socket_path, on_connected, on_event, on_command_response, on_disconnected):
        super().__init__(on_connected, on_event, on_command_response, on_disconnected)
        self.socket_path = socket_path
        self.sock = None

    def can_open(self):
        sock = socket.socket(socket.AF_UNIX)
        errno = sock.connect_ex(self.socket_path)
        sock.close()
        return errno == 0

    def run(self):
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.connect(self.socket_path)

        log.info('POSIX socket connected')
        self.fire_connected()

        buffer = ''
        while True:
            data = self.sock.recv(512)
            if len(data) == 0:
                break
            buffer = buffer + data.decode('utf-8')
            if buffer.find('\n') == -1:
                log.warning('received partial line: ' + buffer)
            while True:
                line_end = buffer.find('\n')
                if line_end == -1:
                    break
                else:
                    self.on_line(buffer[:line_end])  # doesn't include \n
                    buffer = buffer[line_end + 1:]  # doesn't include \n

        log.info('POSIX socket closed')
        self.sock.close()
        self.sock = None

        self.fire_disconnected()

    def write(self, data):
        # no closed check is available, so just send it
        self.sock.send(data)


class WindowsMpvMonitor(MpvMonitor):
    def __init__(self, named_pipe_path, on_connected, on_event, on_command_response, on_disconnected):
        super().__init__(on_connected, on_event, on_command_response, on_disconnected)
        self.named_pipe_path = named_pipe_path
        self.pipe = None

    def can_open(self):
        return os.path.isfile(self.named_pipe_path)

    def run(self):
        while self.pipe is None:
            try:
                self.pipe = open(self.named_pipe_path, 'r+b')
                # Why r+b? We want rw access, no truncate and start from beginning of file.
                # (see http://stackoverflow.com/a/30566011/2634932)
            except OSError:
                # Sometimes Windows can't open the named pipe directly. I suspect a interaction between os.path.isfile()
                # and directly following open(). Sleeping for a short time and trying again seems to help.
                log.warning('OSError. Trying again')
                sleep(0.01)

        log.info('Windows named pipe connected')
        self.fire_connected()

        while True:
            line = self.pipe.readline()
            if len(line) == 0:
                break
            self.on_line(line)

        log.info('Windows named pipe closed')
        self.pipe.close()
        self.pipe = None

        self.fire_disconnected()

    def write(self, data):
        if self.pipe.closed:
            log.warning('Windows named pipe was closed. Can\'t send data: ' + str(data))
        else:
            self.pipe.write(data)
