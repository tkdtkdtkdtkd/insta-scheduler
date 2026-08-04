import os
import io
import asyncio
import uuid
import traceback
import json
import shutil
import subprocess
from datetime import datetime
from flask import Flask, request, render_template, send_file, jsonify, redirect, url_for
from werkzeug.utils import secure_filename
import edge_tts
from pydub import AudioSegment
from pydub.silence import split_on_silence
import requests
from dotenv import load_dotenv

from analyze_audio import analyze_audio
from generate_timestamps import generate_timestamps
from render_video import create_lyric_video
from proglog import ProgressBarLogger

load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['GENERATED_FOLDER'] = 'generated'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['GENERATED_FOLDER'], exist_ok=True)

SCHEDULE_FILE = "schedule.json"
GITHUB_PAT = os.environ.get("GITHUB_PAT")
GITHUB_REPO = os.environ.get("GITHUB_REPO")

# Global progress state
generation_progress = {
    "status": "Idle",
    "percent": 0
}

class MyBarLogger(ProgressBarLogger):
    def bars_callback(self, bar, attr, value, old_value=None):
        if bar == 't':
            total = self.bars[bar].get('total', 1)
            percent = int((value / total) * 70) + 30
            generation_progress['status'] = f"Rendering Video: {int((value/total)*100)}%"
            generation_progress['percent'] = percent

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

async def _generate_audio_bytes(text, voice, rate, remove_silence):
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    audio_data = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data.write(chunk["data"])
    audio_data.seek(0)
    
    try:
        audio = AudioSegment.from_mp3(audio_data)
        
        if remove_silence:
            chunks = split_on_silence(audio, min_silence_len=100, silence_thresh=-45, keep_silence=40)
            if chunks:
                audio = AudioSegment.empty()
                for chunk in chunks:
                    audio += chunk
                    
        # Overlay Background Music
        MUSIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "music")
        if os.path.exists(MUSIC_DIR):
            import random
            music_files = [f for f in os.listdir(MUSIC_DIR) if f.endswith('.mp3')]
            if music_files:
                chosen_music = random.choice(music_files)
                music_path = os.path.join(MUSIC_DIR, chosen_music)
                try:
                    bg_music = AudioSegment.from_mp3(music_path)
                    speech_len = len(audio)
                    music_len = len(bg_music)
                    
                    if music_len > speech_len:
                        bg_chunk = bg_music[:speech_len]
                    else:
                        bg_chunk = bg_music * (speech_len // music_len + 1)
                        bg_chunk = bg_chunk[:speech_len]
                        
                    from pydub.effects import compress_dynamic_range
                    bg_chunk = compress_dynamic_range(bg_chunk, threshold=-20.0, ratio=4.0)
                        
                    target_dbfs = -30.0
                    if "luminary" in chosen_music.lower():
                        target_dbfs = -35.0
                        
                    current_dbfs = bg_chunk.dBFS
                    if current_dbfs != float('-inf'):
                        gain = target_dbfs - current_dbfs
                        bg_chunk = bg_chunk + gain
                    
                    audio = bg_chunk.overlay(audio)
                except Exception as music_err:
                    print(f"Warning: Failed to add music: {music_err}")

        # Add silence buffer at the beginning and end so video text doesn't get cut off
        start_silence = AudioSegment.silent(duration=1000)
        end_silence = AudioSegment.silent(duration=1500)
        audio = start_silence + audio + end_silence
        
        out_data = io.BytesIO()
        audio.export(out_data, format="mp3")
        out_data.seek(0)
        return out_data
    except Exception as e:
        print(f"Warning: Audio processing failed: {e}")
        audio_data.seek(0)
        return audio_data

@app.route('/')
def index():
    schedule = load_schedule()
    schedule = sorted(schedule, key=lambda x: x["scheduled_time"], reverse=True)
    return render_template('index.html', schedule=schedule)

@app.route('/progress')
def progress():
    return jsonify(generation_progress)

@app.route('/generate', methods=['POST'])
def generate():
    global generation_progress
    try:
        generation_progress = {"status": "Starting...", "percent": 0}
        
        data = request.json
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
            
        text = data.get('text', '').strip()
        aspect_ratio = data.get('aspect_ratio', '9:16')
        remove_silence = data.get('remove_silence', False)
        
        if not text:
            return jsonify({'error': 'Text is required'}), 400
            
        # 0. Generate Audio from Text
        generation_progress = {"status": "Generating Audio (TTS)...", "percent": 2}
        voice = "en-US-JennyNeural"
        
        # Async run
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        audio_io = loop.run_until_complete(_generate_audio_bytes(text, voice, "+5%", remove_silence))
        
        audio_filename = f"generated_voice_{uuid.uuid4().hex[:8]}.mp3"
        audio_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename)
        with open(audio_path, 'wb') as f:
            f.write(audio_io.read())
            
        lyrics_path = os.path.join(app.config['UPLOAD_FOLDER'], 'lyrics.md')
        with open(lyrics_path, 'w') as f:
            f.write(text)
            
        timestamps_json = os.path.join(app.config['UPLOAD_FOLDER'], 'aligned_timestamps.json')
        beats_json = os.path.join(app.config['UPLOAD_FOLDER'], 'beats.json')
        output_video_filename = f"lyric_video_{aspect_ratio.replace(':', '_')}_{uuid.uuid4().hex[:8]}.mp4"
        output_video = os.path.join(app.config['GENERATED_FOLDER'], output_video_filename)
        
        # 1. Analyze Audio
        print("Analyzing audio...")
        generation_progress = {"status": "Analyzing Audio...", "percent": 5}
        analyze_audio(audio_path, beats_json)
        
        # 2. Generate Timestamps
        print("Generating timestamps...")
        generation_progress = {"status": "Generating Timestamps (Whisper AI)...", "percent": 15}
        generate_timestamps(audio_path, timestamps_json, lyrics_path)
        
        # 3. Render Video
        print("Rendering video...")
        generation_progress = {"status": "Preparing Video Renderer...", "percent": 30}
        logger = MyBarLogger()
        create_lyric_video(audio_path, timestamps_json, beats_json, output_video, aspect_ratio=aspect_ratio, max_duration=None, logger=logger)
        
        generation_progress = {"status": "Complete!", "percent": 100}
        
        return jsonify({
            'success': True, 
            'video_url': f"/download/{output_video_filename}",
            'audio_url': f"/download_audio/{audio_filename}",
            'filename': output_video_filename
        })
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/schedule', methods=['POST'])
def schedule_post():
    if not GITHUB_PAT or not GITHUB_REPO:
        return jsonify({"success": False, "error": "GITHUB_PAT or GITHUB_REPO is not set in .env file."}), 500

    data = request.json
    filename = data.get("filename")
    caption = data.get("caption")
    scheduled_time = data.get("scheduled_time")

    if not filename or not caption or not scheduled_time:
        return jsonify({"success": False, "error": "Missing parameters."}), 400

    file_path = os.path.join(app.config['GENERATED_FOLDER'], filename)
    if not os.path.exists(file_path):
        return jsonify({"success": False, "error": "Video file not found."}), 404

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
        return jsonify({"success": False, "error": f"Error creating GitHub release: {create_rel_res.text}"}), 500
        
    release_data = create_rel_res.json()
    upload_url = release_data["upload_url"].split("{")[0]
    
    # 4. Upload the video asset to the Release
    with open(file_path, "rb") as f:
        video_data = f.read()
        
    upload_headers = {
        "Authorization": f"token {GITHUB_PAT}",
        "Content-Type": "video/mp4",
        "Accept": "application/vnd.github.v3+json"
    }
    
    upload_res = requests.post(f"{upload_url}?name={filename}", data=video_data, headers=upload_headers)
    if upload_res.status_code != 201:
        return jsonify({"success": False, "error": f"Error uploading video to release: {upload_res.text}"}), 500
        
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
        return jsonify({"success": False, "error": f"Error pushing to git: {e}"}), 500
    
    return jsonify({"success": True})

@app.route('/delete_schedule/<int:post_id>', methods=['POST'])
def delete_schedule(post_id):
    schedule = load_schedule()
    
    post_index = next((index for (index, d) in enumerate(schedule) if d["id"] == post_id), None)
    
    if post_index is None:
        return jsonify({"success": False, "error": "Post not found."}), 404
        
    post = schedule[post_index]
    if post.get("posted") or (post.get("instagram_posted") and post.get("youtube_posted")):
        return jsonify({"success": False, "error": "Cannot delete a post that has already been published."}), 400
        
    del schedule[post_index]
    save_schedule(schedule)
    
    try:
        subprocess.run(["git", "add", "schedule.json"], check=True)
        subprocess.run(["git", "commit", "-m", f"Delete scheduled post #{post_id} via Local Admin UI"], check=True)
        subprocess.run(["git", "push"], check=True)
    except subprocess.CalledProcessError as e:
        return jsonify({"success": False, "error": f"Error pushing to git: {e}"}), 500
        
    return jsonify({"success": True})


@app.route('/download/<filename>')
def download(filename):
    safe_filename = secure_filename(filename)
    path = os.path.join(app.config['GENERATED_FOLDER'], safe_filename)
    return send_file(path, as_attachment=False)

@app.route('/download_audio/<filename>')
def download_audio(filename):
    safe_filename = secure_filename(filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
    return send_file(path, as_attachment=False)

if __name__ == '__main__':
    app.run(debug=True, port=5005)
