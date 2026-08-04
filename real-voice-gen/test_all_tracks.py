import os
import requests

text = """Hello guys! I know no one asked, but I still want to talk about myself, so here I am.

My name is Tanmay. I am 20 years old, and I like to sing and dance. This is my faceless AI avatar with a girl's voice, and on this Instagram channel, I am going to post whatever I want, whenever I want. My content is going to be incredibly entertaining.

By the way, I am the wittiest and funniest person on the planet, so you better follow... well, actually, I don't even care whether or not you follow, because I have so many followers in real life. I don't care about social media, but I am the funniest and smartest person on the planet. Just wanted to let you know!

And my content is soon going to take over the space, and I am going to become so famous on Instagram and YouTube that you won't even see anything apart from my content on your feed.

By the way, this is a girls' voice, but I am a very masculine person in real life.

Anyways, bye, take care! I love you, but I love myself even more."""

music_dir = "music"
out_dir = "test_outputs"

os.makedirs(out_dir, exist_ok=True)
tracks = [f for f in os.listdir(music_dir) if f.endswith(".mp3")]

print(f"Found {len(tracks)} tracks. Generating audio...")

for track in tracks:
    print(f"Processing track: {track} ...")
    response = requests.post(
        "http://127.0.0.1:8001/api/generate",
        json={
            "text": text,
            "remove_silence": True,
            "music_track": track
        }
    )
    
    if response.status_code == 200:
        safe_name = track.replace(" ", "_").replace("/", "")
        out_path = os.path.join(out_dir, f"test_{safe_name}")
        with open(out_path, "wb") as f:
            f.write(response.content)
        print(f" -> Saved to {out_path}")
    else:
        print(f" -> Error: {response.text}")
        
print("Done! You can review all the generated tracks in the 'test_outputs' folder.")
