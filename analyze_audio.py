import librosa
import json
import os
import numpy as np

def analyze_audio(audio_path, output_json):
    print(f"Loading {audio_path}...")
    y, sr = librosa.load(audio_path)
    
    print("Extracting beats...")
    # Calculate beat frames
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    
    # Convert frames to time (seconds)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    
    # Extract energy (RMS) to identify strong beats
    rms = librosa.feature.rms(y=y)[0]
    
    # Map beats to their energy
    beats_data = []
    for t in beat_times:
        # find closest frame
        frame = librosa.time_to_frames(t, sr=sr)
        if frame < len(rms):
            energy = float(rms[frame])
        else:
            energy = 0.0
            
        beats_data.append({
            "time": float(t),
            "energy": energy
        })
        
    # Optional: Find global max energy to normalize
    if beats_data:
        max_energy = max(b["energy"] for b in beats_data)
        for b in beats_data:
            if max_energy > 0:
                b["energy"] = b["energy"] / max_energy
                
    with open(output_json, "w") as f:
        json.dump(beats_data, f, indent=4)
        
    print(f"Saved {len(beats_data)} beats to {output_json}")

if __name__ == "__main__":
    audio_file = "audio.mp3"
    output_file = "beats.json"
    if os.path.exists(audio_file):
        analyze_audio(audio_file, output_file)
    else:
        print(f"Error: {audio_file} not found.")
