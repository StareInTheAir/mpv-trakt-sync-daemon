import json
import queue
import threading


class MpvMonitor:
    def __init__(self, mpv_pipe):
        self.lock = threading.Lock()
        self.command_queue = queue.Queue()
        self.mpv_pipe = mpv_pipe

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
                threading.Thread(target=self.on_command_response,
                                 kwargs={'command': self.command_queue.get(), 'response': mpv_json}).start()
            else:
                print('Unknown mpv output: ' + line)

    def on_event(self, event):
        print(event)

    def on_command_response(self, command, response):
        print(response)

    def issue_command(self, elements):
        command = {'command': elements}
        print(command)
        with self.lock:
            self.mpv_pipe.write(str.encode(json.dumps(command)))
            self.mpv_pipe.write(str.encode('\n'))
            self.command_queue.put(command)

    def issue_command_get_property(self, property_name):
        self.issue_command(['get_property', property_name])
