import json
import socket
import threading
from time import sleep

import os


class MpvMonitor:
    @staticmethod
    def create(posix_socket_path, windows_named_pipe_path, on_connected=None, on_event=None, on_command_response=None,
               on_disconnected=None):
        if os.name == 'posix':
            return PosixMpvMonitor(posix_socket_path, on_connected, on_event, on_command_response, on_disconnected)
        elif os.name == 'nt':
            return WindowsMpvMonitor(windows_named_pipe_path, on_connected, on_event, on_command_response,
                                     on_disconnected)

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
        mpv_json = json.loads(line)
        print(mpv_json)
        if 'event' in mpv_json:
            threading.Thread(target=self.on_event,
                             kwargs={'monitor': self, 'event': mpv_json}).start()
        elif 'data' in mpv_json:
            request_id = mpv_json['request_id']
            threading.Thread(target=self.on_command_response,
                             kwargs={'monitor': self, 'command': self.sent_commands[request_id],
                                     'response': mpv_json}).start()
            del self.sent_commands[request_id]
        else:
            print('Unknown mpv output: ' + line)

    def fire_connected(self):
        if self.on_connected is not None:
            threading.Thread(target=self.on_connected, kwargs={'monitor': self}).start()

    def fire_disconnected(self):
        if self.on_disconnected is not None:
            threading.Thread(target=self.on_disconnected).start()

    def send_command(self, elements):
        command = {'command': elements, 'request_id': self.command_counter}
        print(command)
        with self.lock:
            self.write(str.encode(json.dumps(command) + '\n'))
            self.sent_commands[self.command_counter] = command
            self.command_counter += 1

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

        self.fire_connected()

        while True:
            data = self.sock.recv(512)
            if len(data) == 0:
                print('POSIX socket closed')
                break
            for line in data.decode('utf-8').splitlines():
                self.on_line(line)
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
                print('OSError. Trying again')
                sleep(0.01)

        self.fire_connected()

        while True:
            line = self.pipe.readline()
            if len(line) == 0:
                print('Windows named pipe closed')
                break
            self.on_line(line)
        self.pipe.close()
        self.pipe = None

        self.fire_disconnected()

    def write(self, data):
        if self.pipe.closed:
            print('Windows named pipe was closed. Can\'t send data: ' + str(data))
        else:
            self.pipe.write(data)
