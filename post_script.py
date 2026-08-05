import os
import json
from datetime import datetime, timezone
import requests
import time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import cv2

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

def publish_reel(video_url, caption, thumb_offset_ms=None):
    # Step 1: Create Container
    container_url = f"https://graph.facebook.com/v21.0/{IG_USER_ID}/media"
    payload = {
        'media_type': 'REELS',
        'video_url': video_url,
        'caption': caption,
        'access_token': ACCESS_TOKEN
    }
    if thumb_offset_ms:
        payload['thumb_offset'] = str(thumb_offset_ms)
        
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

def publish_youtube_short(local_filename, caption, thumbnail_path=None):
    if not YOUTUBE_CLIENT_ID or not YOUTUBE_CLIENT_SECRET or not YOUTUBE_REFRESH_TOKEN:
        raise Exception("YouTube credentials are missing.")

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
        video_id = response.get("id")
        
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path)
                ).execute()
            except Exception as e:
                print(f"Could not set YouTube thumbnail: {e}")
                
        return video_id
    finally:
        pass

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
                local_filename = f"temp_vid_{int(time.time())}.mp4"
                thumb_filename = f"thumb_{int(time.time())}.jpg"
                thumb_offset_ms = None
                
                print("Downloading video for processing...")
                try:
                    r = requests.get(item["video_url"], stream=True)
                    with open(local_filename, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=1024*1024):
                            if chunk:
                                f.write(chunk)
                                
                    cap = cv2.VideoCapture(local_filename)
                    if cap.isOpened():
                        fps = cap.get(cv2.CAP_PROP_FPS)
                        total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                        if fps > 0 and total_frames > 0:
                            duration_ms = (total_frames / fps) * 1000
                            thumb_offset_ms = int(duration_ms / 2)
                            
                            cap.set(cv2.CAP_PROP_POS_MSEC, thumb_offset_ms)
                            ret, frame = cap.read()
                            if ret:
                                cv2.imwrite(thumb_filename, frame)
                    cap.release()
                except Exception as e:
                    print("Error processing video for thumbnail:", e)

                # Instagram
                if not ig_posted:
                    print(f"Publishing post ID {item['id']} to Instagram...")
                    try:
                        publish_reel(item["video_url"], item["caption"], thumb_offset_ms=thumb_offset_ms)
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
                        publish_youtube_short(local_filename, item["caption"], thumbnail_path=thumb_filename)
                        item["youtube_posted"] = True
                        updated = True
                        print(f"Successfully posted item {item['id']} to YouTube!")
                    except Exception as e:
                        print(f"Error posting item {item['id']} to YouTube: {e}")
                        
                if os.path.exists(local_filename):
                    os.remove(local_filename)
                if os.path.exists(thumb_filename):
                    os.remove(thumb_filename)

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
