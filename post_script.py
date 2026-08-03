import os
import json
from datetime import datetime
import requests

# Load secrets from GitHub environment variables
ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN")
IG_USER_ID = os.environ.get("IG_USER_ID")
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

from datetime import datetime, timezone

def main():
    schedule = load_schedule()
    now = datetime.now(timezone.utc)
    updated = False

    for item in schedule:
        if not item["posted"]:
            target_time = datetime.fromisoformat(item["scheduled_time"])
            if target_time.tzinfo is None:
                from datetime import timedelta
                target_time = target_time.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
            
            # If current time has reached or passed the scheduled time
            if now >= target_time:
                print(f"Publishing post ID {item['id']}...")
                try:
                    publish_reel(item["video_url"], item["caption"])
                    item["posted"] = True
                    updated = True
                    print(f"Successfully posted item {item['id']}!")
                except Exception as e:
                    print(f"Error posting item {item['id']}: {e}")

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
