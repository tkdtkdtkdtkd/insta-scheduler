import json
import stable_whisper

def generate_timestamps(audio_path, output_json, lyrics_path="lyrics.md", model_size="base"):
    print(f"Loading stable-ts Whisper model ({model_size})...")
    model = stable_whisper.load_model(model_size)
    print(f"Forced aligning {audio_path} with {lyrics_path}...")
    
    # Read lyrics
    with open(lyrics_path, "r") as f:
        lyrics_text = f.read()
        
    import re
    lyrics_text = re.sub(r'\[.*?\]', '', lyrics_text)
    lyrics_text = re.sub(r'\(.*?\)', '', lyrics_text)
        
    # Align text to audio (reverted to default robust settings)
    result = model.align(audio_path, lyrics_text, language='en')
    
    words_data = []
    
    for segment in result.segments:
        for word in segment.words:
            clean_word = word.word.strip()
            # The text is already pre-cleaned, but just in case
            if clean_word:
                words_data.append({
                    "word": clean_word,
                    "start": word.start,
                    "end": word.end
                })
                
    with open(output_json, "w") as f:
        json.dump(words_data, f, indent=4)
        
    print(f"Successfully wrote {len(words_data)} aligned words to {output_json}")

if __name__ == "__main__":
    generate_timestamps("audio.mp3", "aligned_timestamps.json", "lyrics.md", model_size="base")
