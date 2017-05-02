import json
import logging
import sys
import threading
import queue
import time
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
            log.critical('Unknown operating system: ' + os.name)
            sys.exit(11)

    def __init__(self, on_connected, on_event, on_command_response, on_disconnected):
        self.lock = threading.Lock()
        self.buffer = ''
        self.command_counter = 1
        self.sent_commands = {}
        self.write_queue = queue.Queue()

        self.on_connected = on_connected
        self.on_event = on_event
        self.on_command_response = on_command_response
        self.on_disconnected = on_disconnected

    def run(self):
        pass

    def write(self, data):
        log.debug(data)
        self.write_queue.put(data)

    def on_data(self, data):
        self.buffer = self.buffer + data.decode('utf-8')
        while True:
            line_end = self.buffer.find('\n')
            if line_end == -1:
                # partial line received
                # self.on_line() is called in next data batch
                break
            else:
                self.on_line(self.buffer[:line_end])  # doesn't include \n
                self.buffer = self.buffer[line_end + 1:]  # doesn't include \n

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
                    log.warning('got response for unsent command request ' + str(mpv_json))
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
        with self.lock:
            command = {'command': elements, 'request_id': self.command_counter}
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
        import socket

        sock = socket.socket(socket.AF_UNIX)
        errno = sock.connect_ex(self.socket_path)
        sock.close()
        return errno == 0

    def run(self):
        import select
        import socket

        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.connect(self.socket_path)

        log.info('POSIX socket connected')
        self.fire_connected()

        while True:
            r, _, _ = select.select([self.sock], [], [], 1.0)
            if r == [self.sock]:
                # socket has data to read
                data = self.sock.recv(512)
                if len(data) == 0:
                    # EOF reached
                    break
                self.on_data(data)

            while not self.write_queue.empty():
                select.select([], [self.sock], [])  # blocks until self.sock can be written to
                self.sock.send(self.write_queue.get_nowait())

        log.info('POSIX socket closed')
        self.sock.close()
        self.sock = None

        self.fire_disconnected()


class WindowsMpvMonitor(MpvMonitor):
    def __init__(self, named_pipe_path, on_connected, on_event, on_command_response, on_disconnected):
        super().__init__(on_connected, on_event, on_command_response, on_disconnected)
        self.named_pipe_path = named_pipe_path
        self.file_handle = None

    def can_open(self):
        import win32file
        return win32file.GetFileAttributes((self.named_pipe_path)) == win32file.FILE_ATTRIBUTE_NORMAL

    def run(self):
        import win32file
        self.file_handle = win32file.CreateFile(self.named_pipe_path,
                                                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                                                0, None,
                                                win32file.OPEN_EXISTING,
                                                0, None)

        log.info('Windows named pipe connected')
        self.fire_connected()

        while True:
            # The following code is cleaner, than waiting for an exception while writing to detect pipe closing,
            # but causes mpv to hang and crash while closing when closed at the wrong time.

            # if win32file.GetFileAttributes(self.named_pipe_path) != win32file.FILE_ATTRIBUTE_NORMAL:
            #     # pipe was closed
            #     break

            try:
                while not self.write_queue.empty():
                    win32file.WriteFile(self.file_handle, self.write_queue.get_nowait())
            except win32file.error:
                log.warning('Exception while writing to Windows named pipe. Assuming pipe closed.')
                break

            size = win32file.GetFileSize(self.file_handle)
            if size > 0:
                while size > 0:
                    # pipe has data to read
                    data = win32file.ReadFile(self.file_handle, 512)
                    self.on_data(data[1])
                    size = win32file.GetFileSize(self.file_handle)
            else:
                time.sleep(1)

        log.info('Windows named pipe closed')
        win32file.CloseHandle(self.file_handle)
        self.file_handle = None

        self.fire_disconnected()
