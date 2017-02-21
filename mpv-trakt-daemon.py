#!/usr/bin/env python3

from guessit import guessit
import json


def main():
    f = open(r'\\.\pipe\mpv', 'r+b')
    # why r+b? http://stackoverflow.com/a/30566011/2634932
    print("opened mpv pipe")

    f.write(str.encode('{ "command": ["get_property", "filename"] }\n'))
    filename = json.loads(f.readline())
    print(guessit(filename["data"]))

    while True:
        pipe_line = f.readline()
        print(pipe_line)


if __name__ == '__main__':
    main()
