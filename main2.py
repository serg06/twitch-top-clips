import asyncio
import json
import os
import shutil
from datetime import datetime, timezone, timedelta

import aiofiles
import aiohttp

CLIENT_ID = ''
CLIENT_SECRET = ''
POKE_CHANNEL_NAME = 'pokelawls'
POKE_BROADCASTER_ID = 12943173
BROADCASTER_URL = 'https://api.twitch.tv/helix/search/channels?query={}'.format(POKE_CHANNEL_NAME)
CLIPS_URL = 'https://api.twitch.tv/helix/clips'
CLIPS_URL_LEGACY_V5 = 'https://api.twitch.tv/kraken/clips/top'
OUTPUT_FOLDER_NAME = 'output'
CLIPS_INFO_FILE_NAME = 'clips.json'
CHUNK_SIZE = 4096


# TODO: Do it by week, not by day. Not enough for 10 mins worth of clips every day.


# CLIPS_URL = 'https://api.twitch.tv/helix/clips?id=WrongAnnoyingSalamanderOpieOP'


def to_rfc3339(dt: datetime):
    s = dt.astimezone(timezone.utc).isoformat()
    ending = '+00:00'
    assert (s.endswith(ending))
    return s[:-len(ending)] + 'Z'


async def fetch_from_api(session, access_token, url):
    async with session.get(url, headers={
        'Authorization': 'Bearer ' + access_token,
        'client-id': CLIENT_ID,
        'Accept': 'application/vnd.twitchtv.v5+json'
    }) as response:
        return await response.text()


async def fetch_from_api_v2(session, access_token, url):
    async with session.get(url, headers={
        'client-id': CLIENT_ID,
        'Accept': 'application/vnd.twitchtv.v5+json'
    }) as response:
        await stream_active_response_to_file(response, '{}/response.json'.format(OUTPUT_FOLDER_NAME))


def load_auth():
    global CLIENT_ID
    global CLIENT_SECRET

    with open('env.json') as f:
        js = json.load(f)
        CLIENT_ID = js['CLIENT_ID']
        CLIENT_SECRET = js['CLIENT_SECRET']


def gen_access_token_url():
    return "https://id.twitch.tv/oauth2/token?client_id={}&client_secret={}&grant_type=client_credentials".format(
        CLIENT_ID, CLIENT_SECRET)


async def get_access_token(session):
    async with session.post(gen_access_token_url()) as response:
        text = await response.text()
        js = json.loads(text)
        access_token = js['access_token']
        return access_token


async def fetch(session, access_token, url):
    async with session.get(url,
                           headers={'Authorization': 'Bearer ' + access_token, 'client-id': CLIENT_ID}) as response:
        return await response.text()


def get_timedelta_worth_of_clips(clips, td: timedelta):
    result = []
    total_duration = timedelta(seconds=0)
    for clip in clips:
        result.append(clip)
        duration_str = clip['duration']
        duration = float(duration_str)
        total_duration += timedelta(seconds=duration)

        if total_duration >= td:
            break

    return result


def recreate_output_folder():
    if os.path.exists(OUTPUT_FOLDER_NAME) and os.path.isdir(OUTPUT_FOLDER_NAME):
        shutil.rmtree(OUTPUT_FOLDER_NAME)

    os.mkdir(OUTPUT_FOLDER_NAME)


async def stream_active_response_to_file(response, file_name):
    async with aiofiles.open(file_name, 'wb') as f:
        i = 0
        while True:
            chunk = await response.content.read(CHUNK_SIZE)
            if not chunk:
                break
            await f.write(chunk)
            i += 1
            if i >= 10:
                return


async def main():
    load_auth()
    async with aiohttp.ClientSession() as session:
        access_token = await get_access_token(session)
        recreate_output_folder()
        await fetch_from_api_v2(session, access_token, 'https://api.twitch.tv/kraken/chat/emoticons')


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
