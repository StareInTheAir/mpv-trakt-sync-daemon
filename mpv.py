import json
import threading


class MpvMonitor:
    def __init__(self, mpv_pipe):
        self.lock = threading.Lock()
        self.mpv_pipe = mpv_pipe
        self.command_counter = 1
        self.sent_commands = {}

    def run(self):
        while True:
            line = self.mpv_pipe.readline()
            if len(line) == 0:
                print('mpv was closed')
                self.mpv_pipe.close()
                break
            mpv_json = json.loads(line)
            print(mpv_json)
            if 'event' in mpv_json:
                threading.Thread(target=self.on_event,
                                 kwargs={'event': mpv_json}).start()
            elif 'data' in mpv_json:
                request_id = mpv_json['request_id']
                threading.Thread(target=self.on_command_response,
                                 kwargs={'command': self.sent_commands[request_id], 'response': mpv_json}).start()
                del self.sent_commands[request_id]
            else:
                print('Unknown mpv output: ' + line)

    def on_event(self, event):
        print(event)

    def on_command_response(self, command, response):
        print(response)

    def issue_command(self, elements):
        if self.mpv_pipe.closed:
            print('mpv_pipe was closed. Can\'t send command: ' + str(elements))
        else:
            command = {'command': elements, 'request_id': self.command_counter}
            print(command)
            with self.lock:
                self.mpv_pipe.write(str.encode(json.dumps(command)))
                self.mpv_pipe.write(str.encode('\n'))
                self.sent_commands[self.command_counter] = command
                self.command_counter += 1

    def issue_command_get_property(self, property_name):
        self.issue_command(['get_property', property_name])
