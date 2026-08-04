import os
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import edge_tts
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TextToSpeechRequest(BaseModel):
    text: str
    voice: str = "en-US-JennyNeural" # Highly realistic US English female voice
    remove_silence: bool = False
    music_track: str = None

@app.post("/api/generate")
async def generate_speech(request: TextToSpeechRequest):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text is empty")
        
    try:
        import io
        
        # Increase speed by ~5%
        communicate = edge_tts.Communicate(request.text, request.voice, rate="+5%")
        
        # Collect audio chunks in memory
        audio_data = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data.write(chunk["data"])
        
        audio_data.seek(0)
        
        # Post-process to aggressively remove silences using pydub
        from pydub import AudioSegment
        from pydub.silence import split_on_silence
        
        try:
            audio = AudioSegment.from_mp3(audio_data)
            
            if request.remove_silence:
                chunks = split_on_silence(audio, min_silence_len=100, silence_thresh=-45, keep_silence=40)
                if chunks:
                    audio = AudioSegment.empty()
                    for chunk in chunks:
                        audio += chunk
                    
            # --- BACKGROUND MUSIC OVERLAY ---
            MUSIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "music")
            if os.path.exists(MUSIC_DIR):
                import random
                music_files = [f for f in os.listdir(MUSIC_DIR) if f.endswith('.mp3')]
                if music_files:
                    if request.music_track and request.music_track in music_files:
                        chosen_music = request.music_track
                    else:
                        chosen_music = random.choice(music_files)
                        
                    music_path = os.path.join(MUSIC_DIR, chosen_music)
                    try:
                        bg_music = AudioSegment.from_mp3(music_path)
                        speech_len = len(audio)
                        music_len = len(bg_music)
                        
                        # Always start from the beginning of the track
                        if music_len > speech_len:
                            bg_chunk = bg_music[:speech_len]
                        else:
                            # If speech is longer than music, loop the music
                            bg_chunk = bg_music * (speech_len // music_len + 1)
                            bg_chunk = bg_chunk[:speech_len]
                            
                        # Dynamic Range Compression: This flattens the loud peaks and boosts the quiet parts.
                        # We apply this ONLY to the sliced chunk (not the whole 3 minute song!) to make generation instant.
                        from pydub.effects import compress_dynamic_range
                        bg_chunk = compress_dynamic_range(bg_chunk, threshold=-20.0, ratio=4.0)
                            
                        # Now dynamically normalize based on the AVERAGE loudness (dBFS)
                        # so every track feels equally loud in the background.
                        # Setting to -30 dBFS so it is VERY quiet in the background.
                        target_dbfs = -30.0
                        
                        # Custom override: Luminary tracks are naturally very dense
                        if "luminary" in chosen_music.lower():
                            target_dbfs = -35.0
                            
                        current_dbfs = bg_chunk.dBFS
                        if current_dbfs != float('-inf'):
                            gain = target_dbfs - current_dbfs
                            bg_chunk = bg_chunk + gain
                        
                        # Overlay the voice onto the background music
                        audio = bg_chunk.overlay(audio)
                    except Exception as music_err:
                        print(f"Warning: Failed to add music: {music_err}")
            
            out_data = io.BytesIO()
            audio.export(out_data, format="mp3")
            out_data.seek(0)
            return StreamingResponse(out_data, media_type="audio/mpeg")
                
        except Exception as pydub_error:
            # If ffmpeg is missing or pydub fails, just return original in-memory file
            print(f"Warning: Silence removal failed: {pydub_error}")
            audio_data.seek(0)
            return StreamingResponse(audio_data, media_type="audio/mpeg")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Serve static frontend securely
base_dir = os.path.dirname(os.path.abspath(__file__))
frontend_dir = os.path.join(os.path.dirname(base_dir), "frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8001, reload=True)
