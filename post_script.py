import os
import json
from datetime import datetime, timezone
import requests
import time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Load secrets from GitHub environment variables
ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN")
IG_USER_ID = os.environ.get("IG_USER_ID")

YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN")

SCHEDULE_FILE = "schedule.json"

def load_schedule():
    if not os.path.exists(SCHEDULE_FILE):
        return []
    with open(SCHEDULE_FILE, "r") as f:
        return json.load(f)

def save_schedule(data):
    with open(SCHEDULE_FILE, "w") as f:
        json.dump(data, f, indent=2)

def publish_reel(video_url, caption):
    # Step 1: Create Container
    container_url = f"https://graph.facebook.com/v21.0/{IG_USER_ID}/media"
    payload = {
        'media_type': 'REELS',
        'video_url': video_url,
        'caption': caption,
        'access_token': ACCESS_TOKEN
    }
    response = requests.post(container_url, data=payload)
    result = response.json()
    if 'id' not in result:
        raise Exception(f"Container creation failed: {result}")
    
    creation_id = result['id']

    # Step 1.5: Wait for container to be ready
    print(f"Waiting for Meta to process the video (Container ID: {creation_id})...")
    status_url = f"https://graph.facebook.com/v21.0/{creation_id}?fields=status_code&access_token={ACCESS_TOKEN}"
    for _ in range(12): # Wait up to 3 minutes (12 * 15 seconds)
        status_res = requests.get(status_url).json()
        status = status_res.get("status_code")
        if status == "FINISHED":
            print("Video processed successfully!")
            break
        elif status == "ERROR":
            raise Exception("Meta video processing failed.")
        time.sleep(15)
    else:
        raise Exception("Timed out waiting for Meta to process the video.")

    # Step 2: Publish Container
    publish_url = f"https://graph.facebook.com/v21.0/{IG_USER_ID}/media_publish"
    pub_payload = {
        'creation_id': creation_id,
        'access_token': ACCESS_TOKEN
    }
    pub_response = requests.post(publish_url, data=pub_payload)
    pub_result = pub_response.json()
    if 'id' not in pub_result:
        raise Exception(f"Publish failed: {pub_result}")
    
    return pub_result['id']

def publish_youtube_short(video_url, caption):
    if not YOUTUBE_CLIENT_ID or not YOUTUBE_CLIENT_SECRET or not YOUTUBE_REFRESH_TOKEN:
        raise Exception("YouTube credentials are missing.")

    local_filename = f"temp_youtube_{int(time.time())}.mp4"
    r = requests.get(video_url, stream=True)
    with open(local_filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024*1024):
            if chunk:
                f.write(chunk)
    
    try:
        creds = Credentials(
            token=None,
            refresh_token=YOUTUBE_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=YOUTUBE_CLIENT_ID,
            client_secret=YOUTUBE_CLIENT_SECRET
        )

        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

        title = caption.split('\n')[0][:100]
        if not title.strip():
            title = "YouTube Short"
        
        body = {
            "snippet": {
                "title": title,
                "description": caption + "\n\n#Shorts",
                "tags": ["shorts", "video"],
                "categoryId": "22" # 22 is People & Blogs
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            }
        }

        media = MediaFileUpload(local_filename, chunksize=-1, resumable=True, mimetype="video/mp4")

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = request.execute()
        return response.get("id")
    finally:
        if os.path.exists(local_filename):
            os.remove(local_filename)

def main():
    schedule = load_schedule()
    now = datetime.now(timezone.utc)
    updated = False

    for item in schedule:
        ig_posted = item.get("instagram_posted", item.get("posted", False))
        yt_posted = item.get("youtube_posted", False)

        if not ig_posted or not yt_posted:
            target_time = datetime.fromisoformat(item["scheduled_time"])
            if target_time.tzinfo is None:
                from datetime import timedelta
                target_time = target_time.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
            
            # If current time has reached or passed the scheduled time
            if now >= target_time:
                # Instagram
                if not ig_posted:
                    print(f"Publishing post ID {item['id']} to Instagram...")
                    try:
                        publish_reel(item["video_url"], item["caption"])
                        item["instagram_posted"] = True
                        item["posted"] = True # For backwards compatibility
                        updated = True
                        print(f"Successfully posted item {item['id']} to Instagram!")
                    except Exception as e:
                        print(f"Error posting item {item['id']} to Instagram: {e}")
                
                # YouTube
                if not yt_posted:
                    print(f"Publishing post ID {item['id']} to YouTube...")
                    try:
                        publish_youtube_short(item["video_url"], item["caption"])
                        item["youtube_posted"] = True
                        updated = True
                        print(f"Successfully posted item {item['id']} to YouTube!")
                    except Exception as e:
                        print(f"Error posting item {item['id']} to YouTube: {e}")

    if updated:
        save_schedule(schedule)
        # Git commit the updated schedule back to the repo automatically
        os.system("git config --global user.name 'GitHub Action Bot'")
        os.system("git config --global user.email 'bot@users.noreply.github.com'")
        os.system("git add schedule.json")
        os.system("git commit -m 'Update post status to posted [skip ci]'")
        os.system("git push")

if __name__ == "__main__":
    main()
