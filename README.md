# mpv trakt sync daemon

This project is able to monitor what files you are currently watching within mpv, figure out exact meta information about the tv show or movie (using [guessit](https://github.com/guessit-io/guessit)) and send this information to [trakt](https://trakt.tv/). This daemon is supposed to always be running in the background and, when mpv is started, starts the sync process. It uses the [mpv's JSON IPC](https://mpv.io/manual/master/#json-ipc) to extract data from the running mpv instance.

## mpv setup
You need to set the `--input-ipc-server` (see [docs](https://mpv.io/manual/master/#options-input-ipc-server)) in every mpv instance you want to be tracked. This is done most easily inside the [`mpv.conf`](https://mpv.io/manual/master/#files) file by adding the line

    input-ipc-server=/tmp/mpv-socket

Or on Windows with:

    input-ipc-server=\\.\pipe\mpv

The daemon will look for the `input-ipc-server` option in the config file.

## Config parameters
All adjustable options are exposed via the [config.json](config.json) file.

| Parameter                                           | Explanation  |
| --------------------------------------------------- |--------------|
| `monitored_directories`                             | List of strings \| Default: [] <br> Fill in which directories you want the daemon scan for shows or movies. If empty, all files played in mpv are scanned. You can prevent the daemon from scanning all played files if your shows and movies are located in fixed directories. If possible you should use this option to minimize traffic on the trakt API. On Windows, you need to use `\\` instead of `\`. |
| `excluded_directories`                              | List of strings \| Default: [] <br> Fill in which directories should be ignored by the daemon when scanning for shows or movies. If empty, no files played in mpv are ignored. This option overrides `monitored_directories`, meaning if one directory is monitored and ignored, it will be ignored. On Windows, you need to use `\\` instead of `\`. |
| `seconds_between_mpv_running_checks`                | Integer or float \| Default: 30.0 <br> The time in seconds the daemon sleeps between checking if mpv is running. The bigger the number the less load on your machine, but also the longer the daemon potentially takes to find a new running mpv instance. |
| `seconds_between_mpv_event_and_trakt_sync`          | Integer or float \| Default: 10.0 <br> Used as a cooldown timer to prevent too many requests to the trakt API, when changing the playback position rapidly. x seconds need to pass between your last playback change action and synchronization call to trakt. Needs to be less than `seconds_between_regular_get_property_commands` otherwise sync only happens when mpv was closed. |
| `seconds_between_regular_get_property_commands`     | Integer or float \| Default: 30.0 <br> Number of seconds between regular requests to mpv to keep track of playback state. See 'Limitations' section. |
| `factor_must_watch_before_scrobble`                 | Integer or float \| Default: 0.1 <br> How much of a video file do you need to watch before it counts as a valid 'view' as a factor between 0.0 and 1.0. Implemented to prevent 'Have I seen this episode?'-fast-fowards to create a duplicate history item in trakt. Set to 0.0 to disable the feature. |
| `percent_minimal_playback_position_before_scrobble` | Integer or float \| Default: 90.0 <br> At what playback position percentage does a view session count as finished? This in combination with the `factor_must_watch_before_scrobble` parameter controls, when a view session is considered as finished. |


## Setup
I recommend to setup a Python virtual environment instead of installing the dependencies globally.

### Windows

#### First-time use
1. Download and install Python 3.7.x from their [website](https://www.python.org/downloads/). Make sure to check the 'Add to PATH' option in the install wizard.
1. [Download this repository as a zip](../../archive/master.zip) and extract it to a static install location (maybe `%APPDATA%\mpv-trakt-sync-daemon`?)
1. Open command prompt (Win+R > cmd > Enter)
1. `pip install virtualenv` (virtualenv is installed globally)
1. `cd %APPDATA%\mpv-trakt-sync-daemon` (Changes directory to your install location)
1. `virtualenv venv` (Virtual environment created in `venv` folder)
1. `venv\Scripts\activate.bat` (Virtual environment activated)
1. `pip install -r requirements-win.txt` (Dependencies installed in virtualenv)
1. `python sync_daemon.py` (Start daemon manually)
1. Follow the printed instructions to grant this daemon permission to your trakt account.
1. Start watching files in mpv and monitor correct operation (Output is also written to `sync_daemon.log`)

#### Install as an autostart background service
I recommend using [win-launch.bat](win-launch.bat) over [win-hidden-launch.vbs](win-hidden-launch.vbs) because of less complications with virus scanners. The only downside of `win-launch.bat` over `win-hidden-launch.vbs` is a very brief flash of a command prompt.

1. Win+R > `shell:startup` > Enter (Opens autostart directory for current user)
1. Win+R > `%APPDATA%\mpv-trakt-sync-daemon` > Enter (Opens install location)
1. Hold the `Alt` key down and drag `win-launch.bat` from the install location to the autostart folder to create a shortcut
1. The daemon now starts automatically on login

### Unix

#### First-time use
1. Install `python3`, `pip` and `git` from your package manager of choice 
1. `pip install virtualenv`
1. `cd` into install location
1. `git clone https://github.com/StareInTheAir/mpv-trakt-sync-daemon.git`
1. `cd mpv-trakt-sync-daemon`
1. `virtualenv venv`
1. `source venv/bin/activate`
1. `pip install -r requirements.txt`
1. `./sync_daemon.py`
1. Follow the printed instructions to grant this daemon permission to your trakt account.
1. Start watching files in mpv and monitor correct operation (Output is also written to `sync_daemon.log`)


#### Install as an autostart background service
If your OS has `systemd`:

1. Put the correct path to the cloned repository into `mpv-trakt-sync@.service`
1. `sudo cp mpv-trakt-sync@.service /etc/systemd/system/`
1. `sudo systemctl daemon-reload`
1. `sudo systemctl enable mpv-trakt-sync@$USER`
1. `systemd` will now launch the daemon on boot

### macOS

#### First-time use
1. Setup [brew](https://brew.sh/)
1. `brew install python3`
1. `pip install virtualenv`
1. `cd` into install location
1. `git clone https://github.com/StareInTheAir/mpv-trakt-sync-daemon.git`
1. `cd mpv-trakt-sync-daemon`
1. `virtualenv venv`
1. `source venv/bin/activate`
1. `pip install -r requirements.txt`
1. `./sync_daemon.py`

#### Install as an autostart background service
Contributed by [Sameer Jain](https://github.com/SJ50). Thank you.

1. Put the correct path to the cloned repository into `mpv-trakt-sync.plist`
1. `cp mpv-trakt-sync.plist ~/Library/LaunchAgents/`
1. `launchctl load ~/Library/LaunchAgents/mpv-trakt-sync.plist`
1. `launchctl list | grep com.github.stareintheair.mpv-trakt-sync-daemon` (shows output if mpv-trakt-sync-daemon is running)

## Limitations

- Only one mpv instance can be tracked (because only one mpv process can write to the socket / named pipe)
- Once mpv is closing, requests can no longer be sent to it. To keep track of your playback position requests need to be sent in regular intervals, so that when mpv quits the last known state can be used for determining your playback state.

## Why not as as a mpv Lua plugin?

- When mpv quits, I imagine, sending out a blocking http request to the trakt API isn't the best. When you want mpv to quit, it should quit instantly. A separate daemon is better suited to accomplish this task.
- [guessit](https://github.com/guessit-io/guessit) is really good at parsing release names and it's also written in Python
- I don't know Lua :)

## useful resources
- https://mpv.io/manual/master/#json-ipc
- https://mpv.io/manual/master/#protocol
- https://mpv.io/manual/master/#list-of-input-commands
- https://mpv.io/manual/master/#property-list
- http://docs.trakt.apiary.io/#reference/scrobble
- http://www.launchd.info/