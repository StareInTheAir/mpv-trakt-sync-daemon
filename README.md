# mpv trakt sync daemon

This project should at some point be able to monitor what files you are currently watching within mpv, figure out exact meta information about the tv show or movie and send this information to trakt. This daemon is supposed to always be running in the background and, when mpv is started, starts the sync process.

This project is currently in development. It's not in working condition.

## mpv setup
You need to set the `--input-ipc-server` (see [docs](https://mpv.io/manual/master/#options-input-ipc-server)) in every mpv instance you want to be tracked. This is done most easily inside the [`mpv.conf`](https://mpv.io/manual/master/#files) file by adding the line

    input-ipc-server=/tmp/mpv-pipe

Or on windows with:

    input-ipc-server=\\.\pipe\mpv

## daemon setup
1. Install Python 3 and pip
1. `pip install virtualenv`
1. `git clone https://github.com/StareInTheAir/mpv-trakt-sync-daemon`
1. `cd mpv-trakt-sync-daemon`
1. `virtualenv venv`
1. `venv/Scripts/activate`
1. `pip install requirements.txt`
1. `python mpv-trakt-daemon.py`

## useful resources
- https://mpv.io/manual/master/#json-ipc
- https://mpv.io/manual/master/#protocol
- https://mpv.io/manual/master/#list-of-input-commands
- https://mpv.io/manual/master/#property-list
