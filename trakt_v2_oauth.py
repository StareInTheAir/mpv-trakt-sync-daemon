#! /usr/bin/env python3

import datetime
import json
import os
import sys

import requests

import client_secret_holder

client_id = '18313245490a6414e3f46e981e263f845d28c716cd24a6c58137e89a869dfdcb'
local_storage_json_file = './imdb_to_trakt_v2_sync_token.json'


def get_access_token(oauth_pin=None):
    if not os.path.isfile(local_storage_json_file) and oauth_pin is None:
        # no local token was found and no pin was supplied
        sys.exit('Please supply an OAuth trakt pin. See -h for instructions.')

    if oauth_pin is not None:
        # every time a PIN is supplied, try getting a new token
        token_request = requests.post('https://api-v2launch.trakt.tv/oauth/token', json={
            'code': oauth_pin,
            'client_id': client_id,
            'client_secret': client_secret_holder.get(),
            'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob',
            'grant_type': 'authorization_code'
        })

        if token_request.status_code == 200:
            print('Successfully got token from supplied PIN.')
            # save response to local json file
            json.dump(token_request.json(), open(local_storage_json_file, 'w'))
        else:
            sys.exit('Exchanging code for token failed with http code %d.\n%s' %
                     (token_request.status_code, token_request.text))

    tokens = json.load(open(local_storage_json_file))

    expire_date = datetime.datetime.utcfromtimestamp(tokens['created_at'] + tokens['expires_in'])
    remaining_time = expire_date - datetime.datetime.utcnow()

    # make sure the token is at least valid for the next 60 seconds (should be enough runtime for the script)
    if remaining_time < datetime.timedelta(seconds=60):
        print('Token expired')
        token_refresh_request = requests.post('https://api-v2launch.trakt.tv/oauth/token', json={
            'refresh_token': tokens['refresh_token'],
            'client_id': client_id,
            'client_secret': client_secret_holder.get(),
            'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob',
            'grant_type': 'refresh_token'
        })

        if token_refresh_request.status_code == 200:
            print('Successfully refreshed token')
            # save response to local json file
            json.dump(token_refresh_request.json(), open(local_storage_json_file, 'w'))

            # reload new token
            tokens = json.load(open(local_storage_json_file))
        else:
            sys.exit('Refreshing token failed with http code %d.\n%s' %
                     (token_refresh_request.status_code, token_refresh_request.text))
    return tokens['access_token']
