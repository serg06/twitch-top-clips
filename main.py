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
CHUNK_SIZE = 1024*1024  # 1MB

# TODO: Do it by week, not by day. Not enough for 10 mins worth of clips every day.


# CLIPS_URL = 'https://api.twitch.tv/helix/clips?id=WrongAnnoyingSalamanderOpieOP'

def get_clip_file_name(clip):
    clip_id = clip['tracking_id']
    return '{}/{}.mp4'.format(OUTPUT_FOLDER_NAME, clip_id)


def convert_preview_url_to_clip_url(preview_url: str):
    idx = preview_url.find('-preview')
    assert (idx >= 0)
    url = preview_url[:idx]
    url = '{}.mp4'.format(url)
    return url


def extract_clip_preview_url(clip):
    if 'vod' in clip:
        vod = clip['vod']
        if 'preview_image_url' in vod:
            return vod['preview_image_url']

    if 'thumbnails' in clip:
        thumbnails = clip['thumbnails']
        if 'tiny' in thumbnails:
            return thumbnails['tiny']
        if 'small' in thumbnails:
            return thumbnails['small']
        if 'medium' in thumbnails:
            return thumbnails['medium']

    return None


def get_clip_download_url(clip):
    clip_url = None
    preview_url = extract_clip_preview_url(clip)
    if preview_url is not None:
        clip_url = convert_preview_url_to_clip_url(preview_url)
    else:
        # backup method, might not work
        clip_id = clip['tracking_id']
        clip_url = 'https://clips-media-assets2.twitch.tv/AT-cm%7C{}.mp4'.format(clip_id)

    assert (clip_url is not None)
    return clip_url


def to_rfc3339(dt: datetime):
    s = dt.astimezone(timezone.utc).isoformat()
    ending = '+00:00'
    assert (s.endswith(ending))
    return s[:-len(ending)] + 'Z'


async def get_clips_legacy_v5(session, access_token, channel_name, max_clips=10, period='day'):
    url = CLIPS_URL_LEGACY_V5
    url += '?channel={}'.format(channel_name)
    url += '&limit={}'.format(max_clips)
    url += '&period={}'.format(period)

    async with session.get(url, headers={
        'Authorization': 'Bearer ' + access_token,
        'client-id': CLIENT_ID,
        'Accept': 'application/vnd.twitchtv.v5+json'
    }) as response:
        return await response.text()


async def get_clips(session, access_token, broadcaster_id, max_clips=20, start_time=datetime.now() - timedelta(days=1),
                    end_time=datetime.now()):
    url = CLIPS_URL
    url += '?broadcaster_id={}'.format(broadcaster_id)
    url += '&first={}'.format(max_clips)
    url += '&started_at={}'.format(to_rfc3339(start_time))
    url += '&ended_at={}'.format(to_rfc3339(end_time))

    async with session.get(url,
                           headers={'Authorization': 'Bearer ' + access_token, 'client-id': CLIENT_ID}) as response:
        return await response.text()


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


def write_clips_info(clips):
    with open('{}/{}'.format(OUTPUT_FOLDER_NAME, CLIPS_INFO_FILE_NAME), 'w') as f:
        json.dump(clips, f, indent=4)


async def stream_active_response_to_file(response, file_name):
    async with aiofiles.open(file_name, 'wb') as f:
        while True:
            chunk = await response.content.read(CHUNK_SIZE)
            if not chunk:
                break
            await f.write(chunk)


async def download_clip(session, clip):
    clip_id = clip['tracking_id']
    download_url = get_clip_download_url(clip)
    print('{}.mp4: started'.format(clip_id))
    async with session.get(download_url) as response:
        status_code = response.status
        is_ok = 200 <= status_code <= 299
        if is_ok:
            await stream_active_response_to_file(response, get_clip_file_name(clip))
        else:
            print('ERROR: Cannot download clip: {}.mp4'.format(clip_id))

    print('{}.mp4: done!'.format(clip_id))
    return '{}.mp4'.format(clip_id)


async def download_clips(session, clips):
    results = await asyncio.gather(
        *[
            download_clip(session, clip) for clip in clips
        ]
    )


async def combine_clips(session, access_token, clips):
    # TODO: Sort by real_start_time (which I should've created earlier), then combine in that order
    # TODO: Put title of the clip at the top of the video somehow. Not sure. Maybe the MoviePy library allows
    #   that, or maybe I'll have to automate the usage of some Adobe program that supports automation.
    pass


async def main():
    load_auth()
    async with aiohttp.ClientSession() as session:
        access_token = await get_access_token(session)
        # html = await get_clips(session, access_token, POKE_BROADCASTER_ID, 1)
        html = await get_clips_legacy_v5(session, access_token, POKE_CHANNEL_NAME, 100)

        print(html)

        js = json.loads(html)
        clips = js['clips']
        # TODO: Before filtering by time, first make sure no clips collide, and if they do collide, prefer the clips
        #   with more views.
        # Note: Will probably need to assign each clip a real_start_time and real_end_time here, and then
        #   perform a DP algorithm to find collisions. I believe the algorithm was earliest end time first?
        #   And that gives you an O(n) greedy algorithm, where you simply check if the current interval begins
        #   before the last one ends? And then I need an outer O(n) loop to do it again and again. Or if I want
        #   to be cool about it, I can do it in O(n) by having it in a linked list, removing the lower one right
        #   there and then (so if next has less views, remove next and next = next.next(), and if prev has less
        #   views, remove prev and prev = prev.prev().)
        clips = get_timedelta_worth_of_clips(clips, timedelta(minutes=10))
        recreate_output_folder()
        write_clips_info(clips)
        await download_clips(session, clips)
        await combine_clips(clips)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
