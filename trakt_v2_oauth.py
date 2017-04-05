import datetime
import json
import sys
import time

import os
import requests

import client_key_holder

client_id = '24c7a86d0a55334a9575734decac760cea679877fcb60b0983cbe45996242dd7'
local_storage_json_file = './trakt_token.json'


def get_access_token():
    if not os.path.isfile(local_storage_json_file):
        prompt_device_authentication()

    tokens = json.load(open(local_storage_json_file))

    expire_date = datetime.datetime.utcfromtimestamp(tokens['created_at'] + tokens['expires_in'])
    remaining_time = expire_date - datetime.datetime.utcnow()

    # make sure the token is at least valid for the next day
    if remaining_time < datetime.timedelta(days=1):
        print('Token expired')
        token_refresh_request = requests.post('https://api.trakt.tv/oauth/token', json={
            'refresh_token': tokens['refresh_token'],
            'client_id': client_id,
            'client_secret': client_key_holder.get_secret(),
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


def prompt_device_authentication():
    code_request = requests.post('https://api.trakt.tv/oauth/device/code', json={
        'client_id': client_id
    })

    if code_request.status_code == 200:
        code_json = code_request.json()
        print('Please visit %s and enter code %s to grant this app permission to your trakt account.' %
              (code_json['verification_url'], code_json['user_code']))
        start_time = datetime.datetime.now()
        got_access_token = False

        while datetime.datetime.now() - start_time < datetime.timedelta(seconds=code_json['expires_in']):
            time.sleep(code_json['interval'])
            token_request = requests.post('https://api.trakt.tv/oauth/device/token', json={
                'code': code_json['device_code'],
                'client_id': client_id,
                'client_secret': client_key_holder.get_secret()
            })
            if token_request.status_code == 200:
                token_json = token_request.json()
                json.dump(token_json, open(local_storage_json_file, 'w'))
                print('\nSuccessfully established access to trakt account')
                got_access_token = True
                break
            else:
                print(str(token_request.status_code) + ' ', end='', flush=True)

        if not got_access_token:
            sys.exit('\nCould not get access token. Please try again.')

    else:
        sys.exit('POST request for generating device codes failed with HTTP code %d.\n%s' %
                 (code_request.status_code, code_request.text))


if __name__ == '__main__':
    get_access_token()
