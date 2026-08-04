import os
import json
import shutil
import subprocess
from datetime import datetime
from fastapi import FastAPI, Form, UploadFile, File, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import requests
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

UPLOAD_DIR = "uploads"
SCHEDULE_FILE = "schedule.json"
os.makedirs(UPLOAD_DIR, exist_ok=True)

GITHUB_PAT = os.environ.get("GITHUB_PAT")
GITHUB_REPO = os.environ.get("GITHUB_REPO")

def load_schedule():
    if not os.path.exists(SCHEDULE_FILE):
        return []
    with open(SCHEDULE_FILE, "r") as f:
        return json.load(f)

def save_schedule(data):
    with open(SCHEDULE_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_next_id(schedule):
    if not schedule:
        return 1
    return max(item["id"] for item in schedule) + 1

@app.get("/", response_class=HTMLResponse)
def read_root():
    schedule = load_schedule()
    # Sort so newest times are first or latest first
    schedule = sorted(schedule, key=lambda x: x["scheduled_time"], reverse=True)
    
    html_content = f"""
    <html>
    <head>
        <title>Insta-Scheduler Admin</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-50 p-8 min-h-screen font-sans">
        <div class="max-w-5xl mx-auto">
            <h1 class="text-4xl font-extrabold text-slate-800 mb-2">Insta-Scheduler Control Center</h1>
            <p class="text-slate-500 mb-8">Upload here, and let GitHub Actions do the background posting for free.</p>
            
            <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
                
                <!-- Upload Form -->
                <div class="md:col-span-1 bg-white p-6 rounded-2xl shadow-sm border border-slate-200 h-fit">
                    <h2 class="text-xl font-bold text-slate-800 mb-6">Schedule New Post</h2>
                    <form action="/schedule" method="post" enctype="multipart/form-data" class="space-y-5" onsubmit="document.getElementById('submit-btn').innerText = 'Uploading to GitHub...';">
                        <div>
                            <label class="block font-semibold text-sm text-slate-600 mb-2">Video File (.mp4)</label>
                            <input type="file" name="file" accept="video/mp4" required class="w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100">
                        </div>
                        <div>
                            <label class="block font-semibold text-sm text-slate-600 mb-2">Caption</label>
                            <textarea name="caption" class="w-full border border-slate-300 p-3 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none transition" rows="4" placeholder="Write your awesome caption..."></textarea>
                        </div>
                        <div>
                            <label class="block font-semibold text-sm text-slate-600 mb-2">Schedule Date & Time</label>
                            <input type="datetime-local" name="scheduled_time" required class="w-full border border-slate-300 p-3 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none transition">
                        </div>
                        <button id="submit-btn" type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold px-4 py-3 rounded-xl transition duration-200">Push to GitHub</button>
                    </form>
                </div>

                <!-- Schedule List -->
                <div class="md:col-span-2 bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                    <h2 class="text-xl font-bold text-slate-800 mb-6">Upcoming & Past Posts</h2>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-sm">
                            <thead>
                                <tr class="text-slate-500 border-b border-slate-200">
                                    <th class="pb-3 font-semibold">ID</th>
                                    <th class="pb-3 font-semibold">Scheduled For</th>
                                    <th class="pb-3 font-semibold">Caption</th>
                                    <th class="pb-3 font-semibold">Status</th>
                                </tr>
                            </thead>
                            <tbody>
    """
    for p in schedule:
        ig_posted = p.get("instagram_posted", p.get("posted", False))
        yt_posted = p.get("youtube_posted", False)

        ig_status_color = "text-green-600 bg-green-50" if ig_posted else "text-amber-600 bg-amber-50"
        ig_status_text = "IG: Posted" if ig_posted else "IG: Pending"

        yt_status_color = "text-blue-600 bg-blue-50" if yt_posted else "text-amber-600 bg-amber-50"
        yt_status_text = "YT: Posted" if yt_posted else "YT: Pending"
        
        # Truncate caption for display
        cap = p["caption"]
        cap_display = cap[:30] + '...' if len(cap) > 30 else cap

        html_content += f"""
                                <tr class="border-b border-slate-100 hover:bg-slate-50 transition">
                                    <td class="py-4 text-slate-600 font-medium">#{p['id']}</td>
                                    <td class="py-4 text-slate-800">{p['scheduled_time']}</td>
                                    <td class="py-4 text-slate-600">{cap_display}</td>
                                    <td class="py-4 flex flex-col gap-1">
                                        <span class="px-3 py-1 rounded-full text-xs font-bold w-fit {ig_status_color}">
                                            {ig_status_text}
                                        </span>
                                        <span class="px-3 py-1 rounded-full text-xs font-bold w-fit {yt_status_color}">
                                            {yt_status_text}
                                        </span>
                                    </td>
                                </tr>
        """
    html_content += """
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/schedule")
async def schedule_post(
    file: UploadFile = File(...),
    caption: str = Form(...),
    scheduled_time: str = Form(...)
):
    if not GITHUB_PAT or not GITHUB_REPO:
        return HTMLResponse("Error: GITHUB_PAT or GITHUB_REPO is not set in .env file.", status_code=500)

    # 1. Save file locally temporarily
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # 2. Create a unique tag for the GitHub Release
    tag_name = f"post-{datetime.now().strftime('%Y%md%H%M%S')}"
    
    # 3. Create GitHub Release
    headers = {
        "Authorization": f"token {GITHUB_PAT}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    release_payload = {
        "tag_name": tag_name,
        "name": f"Video Release {tag_name}",
        "body": "Automated video upload for Instagram scheduler"
    }
    
    create_rel_res = requests.post(f"https://api.github.com/repos/{GITHUB_REPO}/releases", json=release_payload, headers=headers)
    if create_rel_res.status_code != 201:
        return HTMLResponse(f"Error creating GitHub release: {create_rel_res.text}", status_code=500)
        
    release_data = create_rel_res.json()
    upload_url = release_data["upload_url"].split("{")[0] # clean URL template
    
    # 4. Upload the video asset to the Release
    with open(file_path, "rb") as f:
        video_data = f.read()
        
    upload_headers = {
        "Authorization": f"token {GITHUB_PAT}",
        "Content-Type": "video/mp4",
        "Accept": "application/vnd.github.v3+json"
    }
    
    upload_res = requests.post(f"{upload_url}?name={file.filename}", data=video_data, headers=upload_headers)
    if upload_res.status_code != 201:
        return HTMLResponse(f"Error uploading video to release: {upload_res.text}", status_code=500)
        
    asset_data = upload_res.json()
    download_url = asset_data["browser_download_url"]
    
    # 5. Update schedule.json
    schedule = load_schedule()
    new_id = get_next_id(schedule)
    local_time = datetime.fromisoformat(scheduled_time).astimezone()
    parsed_time = local_time.isoformat()
    
    schedule.append({
        "id": new_id,
        "video_url": download_url,
        "caption": caption,
        "scheduled_time": parsed_time,
        "posted": False,
        "instagram_posted": False,
        "youtube_posted": False
    })
    
    save_schedule(schedule)
    
    # 6. Commit and Push to GitHub
    try:
        subprocess.run(["git", "add", "schedule.json"], check=True)
        subprocess.run(["git", "commit", "-m", f"Schedule post #{new_id} via Local Admin UI"], check=True)
        subprocess.run(["git", "push"], check=True)
    except subprocess.CalledProcessError as e:
        return HTMLResponse(f"Error pushing to git: {e}", status_code=500)
    
    # Cleanup temp video
    os.remove(file_path)

    return RedirectResponse(url="/", status_code=303)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
