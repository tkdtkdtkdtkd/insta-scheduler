import os
os.environ["IMAGEMAGICK_BINARY"] = "/opt/homebrew/bin/magick"
import json
import random
import numpy as np
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS

from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, ColorClip
import moviepy.video.fx.all as vfx

def create_lyric_video(audio_path, timestamps_json, beats_json, output_video, aspect_ratio="16:9", max_duration=40.0, logger=None):
    # Ensure dependencies are available (imagemagick)
    if not os.path.exists(timestamps_json) or not os.path.exists(beats_json):
        print("Missing JSON files.")
        return

    with open(timestamps_json, "r") as f:
        words_data = json.load(f)
        
    with open(beats_json, "r") as f:
        beats_data = json.load(f)

    # Resolution and Safe Zones (Margins)
    if aspect_ratio == "16:9":
        W, H = 1920, 1080 # Horizontal video 16:9
        margin_top = 150
        margin_bottom = 150
        margin_left = 200
        margin_right = 200
    else:
        W, H = 1080, 1920 # Vertical video 9:16
        # Instagram Reels / YouTube Shorts safe zones
        # Accounting for UI elements at the bottom (captions, user info) and right (like/share icons)
        margin_top = 300
        margin_bottom = 750
        margin_left = 150
        margin_right = 250

    from moviepy.audio.io.AudioFileClip import AudioFileClip
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration

    text_clips = []
    
    # Styles for premium look - user approved fonts
    # Styles for premium look - user approved fonts with specific percentage weights
    fonts = [
        {'name': 'Impact', 'path': '/System/Library/Fonts/Supplemental/Impact.ttf', 'type': 'caps', 'weight': 50},
        {'name': 'Chalkduster', 'path': '/System/Library/Fonts/Supplemental/Chalkduster.ttf', 'type': 'normal', 'weight': 30},
        {'name': 'Trattatello', 'path': '/System/Library/Fonts/Supplemental/Trattatello.ttf', 'type': 'normal', 'weight': 20}
    ]
    # Highly vibrant colors with strong contrast against white background
    colors = ['#FF0000', '#0000FF', '#00AA00', '#AA00FF', '#FF6600', '#E60073', '#0088FF', '#000000']
    
    from moviepy.audio.io.AudioFileClip import AudioFileClip
    if max_duration:
        audio_clip = AudioFileClip(audio_path).subclip(0, min(max_duration, AudioFileClip(audio_path).duration))
    else:
        audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration

    # Base background (White)
    bg = ColorClip(size=(W, H), color=(255, 255, 255)).set_duration(duration)
    
    
    # Fix zero-duration or invalid timestamps from Whisper (usually dropped first words of sentences)
    for i in range(len(words_data)):
        w = words_data[i]
        if w['end'] <= w['start']:
            # Interpolate start from previous word
            if i > 0:
                w['start'] = words_data[i-1]['end']
            else:
                w['start'] = 0.0
                
            # Interpolate end from next word
            if i < len(words_data) - 1 and words_data[i+1]['start'] > w['start']:
                w['end'] = words_data[i+1]['start']
            else:
                w['end'] = w['start'] + 0.3
                
    # Filter words for duration
    valid_words = [w for w in words_data if w['start'] < duration and w['end'] > w['start']]
    
    # --- BSP Algorithm to split a rectangle into N rectangles ---
    def generate_blocks(num_blocks, start_x, start_y, width, height):
        rects = [{'x': start_x, 'y': start_y, 'w': width, 'h': height}]
        
        while len(rects) < num_blocks:
            # Pick a random rectangle to split (preferably a large one)
            # Weight choice by area so we don't get tiny slivers
            areas = [r['w'] * r['h'] for r in rects]
            idx = random.choices(range(len(rects)), weights=areas, k=1)[0]
            rect = rects.pop(idx)
            
            # Split direction based on aspect ratio
            if rect['w'] > rect['h'] * 1.5:
                # Force vertical split
                split = 'v'
            elif rect['h'] > rect['w'] * 1.5:
                # Force horizontal split
                split = 'h'
            else:
                split = random.choice(['v', 'h'])
                
            # Random split point between 30% and 70%
            split_ratio = random.uniform(0.3, 0.7)
            
            if split == 'v': # Vertical cut, splits into left and right
                cut_w = int(rect['w'] * split_ratio)
                rects.append({'x': rect['x'], 'y': rect['y'], 'w': cut_w, 'h': rect['h']})
                rects.append({'x': rect['x'] + cut_w, 'y': rect['y'], 'w': rect['w'] - cut_w, 'h': rect['h']})
            else: # Horizontal cut, splits into top and bottom
                cut_h = int(rect['h'] * split_ratio)
                rects.append({'x': rect['x'], 'y': rect['y'], 'w': rect['w'], 'h': cut_h})
                rects.append({'x': rect['x'], 'y': rect['y'] + cut_h, 'w': rect['w'], 'h': rect['h'] - cut_h})
                
        return rects

        # Group words into natural scenes (sentences) based on pauses and impact words
    scenes = []
    i = 0
    while i < len(valid_words):
        w = valid_words[i]
        
        # Impact word gets its own full screen (very rare, only for extremely long holds > 0.8s)
        if (w['end'] - w['start']) > 0.8:
            scenes.append([w])
            i += 1
            continue
            
        current_scene = [w]
        i += 1
        while i < len(valid_words):
            next_w = valid_words[i]
            
            # Break if next word is an extreme impact word
            if (next_w['end'] - next_w['start']) > 0.8:
                break
                
            # Break if previous word ended a sentence
            if current_scene[-1]['word'].strip().endswith(('.', '?', '!')):
                break
                
            # Break if large gap (new sentence)
            if (next_w['start'] - current_scene[-1]['end']) > 1.0:
                break
                
            current_scene.append(next_w)
            i += 1
            
            # Max words per scene
            if len(current_scene) >= 12:
                break
                
        scenes.append(current_scene)
        
    for scene_idx, scene_words in enumerate(scenes):
        scene_words = [w for w in scene_words if w['word'].replace(',', '').replace('.', '').replace(';', '').strip()]
        scene_size = len(scene_words)
        if scene_size == 0:
            continue
            
        blocks = generate_blocks(scene_size, margin_left, margin_top, W - margin_left - margin_right, H - margin_top - margin_bottom)
        random.shuffle(blocks)
        
        font_weights = [f.get('weight', 1) for f in fonts]
        
        # Determine the end time for this entire scene
        if scene_idx + 1 < len(scenes):
            next_start = scenes[scene_idx + 1][0]['start']
            last_end = scene_words[-1]['end']
            # If the instrumental gap to the next word is more than 1.0 seconds, clear the screen after a 0.4 second pause!
            if next_start - last_end > 1.0:
                scene_end_t = last_end + 0.4
            else:
                scene_end_t = next_start
        else:
            scene_end_t = scene_words[-1]['end'] + 0.5
            
        # Ensure scene_end_t does not overlap with the 3-second outro
        scene_end_t = min(scene_end_t, max(0, duration - 3.0))
            
        word_clips = []
        for word_data in scene_words:
            clean_w = word_data['word'].replace(',', '').replace('.', '').replace(';', '').strip().upper()
                
            chosen_font = random.choices(fonts, weights=font_weights, k=1)[0]
            font = chosen_font['path']
            is_bold = chosen_font.get('bold', False)
                
            if is_bold:
                dummy = TextClip(clean_w, fontsize=100, color='white', font=font, stroke_color='white', stroke_width=2)
            else:
                dummy = TextClip(clean_w, fontsize=100, color='white', font=font)
                
            word_clips.append({
                'word_data': word_data,
                'clean_w': clean_w,
                'dummy_w': dummy.w,
                'dummy_h': dummy.h,
                'ar': dummy.w / dummy.h,
                'font': font,
                'is_bold': is_bold
            })
            
        # Sequence words to appear in adjacent spatial blocks
        def block_center(b):
            return (b['x'] + b['w']/2, b['y'] + b['h']/2)
        def dist(b1, b2):
            c1, c2 = block_center(b1), block_center(b2)
            return (c1[0]-c2[0])**2 + (c1[1]-c2[1])**2
            
        unassigned_blocks = blocks.copy()
        current_block = min(unassigned_blocks, key=lambda b: b['x']**2 + b['y']**2)
        ordered_blocks = [current_block]
        unassigned_blocks.remove(current_block)
        
        while unassigned_blocks:
            next_block = min(unassigned_blocks, key=lambda b: dist(current_block, b))
            ordered_blocks.append(next_block)
            unassigned_blocks.remove(next_block)
            current_block = next_block
            
        for b in ordered_blocks:
            b['ar'] = b['w'] / b['h']
            
        for i in range(scene_size):
            w_obj = word_clips[i]
            block = ordered_blocks[i]
            w_obj['block'] = block
            
            # If word is wide but forced into a tall vertical block, rotate it 90 degrees to fit!
            if w_obj['ar'] > 1.2 and block['ar'] < 0.8:
                w_obj['angle'] = random.choice([90, -90])
            else:
                w_obj['angle'] = 0
                
        last_color = None
        for w_obj in word_clips: # Iterate in original chronological order
            block = w_obj['block']
            clean_w = w_obj['clean_w']
            
            # Since we now use VAD (Voice Activity Detection), the timestamps accurately track vocals
            start_t = w_obj['word_data']['start']
            end_t_word = w_obj['word_data']['end']
            
            # (Removed the start_t clamping fix that was skipping first words)
                
            end_t = scene_end_t
            angle = w_obj['angle']
            
            # Ensure every consecutive word gets a NEW random color
            available_colors = [c for c in colors if c != last_color]
            txt_color = random.choice(available_colors)
            last_color = txt_color

            
            try:
                target_w = block['w']
                target_h = block['h']
                
                if angle != 0:
                    # If rotated 90 degrees, swap the target dimensions for uniform scale math
                    target_w = block['h']
                    target_h = block['w']
                    
                # Calculate exact uniform font size needed to perfectly fill either width or height
                ratio = min(target_w / w_obj['dummy_w'], target_h / w_obj['dummy_h'])
                exact_fontsize = max(int(100 * ratio), 10)
                
                # Render at 2x resolution to act as Supersampling Anti-Aliasing (SSAA)
                exact_fontsize_hq = exact_fontsize * 2
                
                word_font = w_obj['font']
                word_is_bold = w_obj['is_bold']
                
                if word_is_bold:
                    # Stroke width scales slightly with font size to keep it proportional
                    sw = max(1, int(exact_fontsize_hq * 0.03))
                    txt_clip = TextClip(clean_w, fontsize=exact_fontsize_hq, color=txt_color, font=word_font, stroke_color=txt_color, stroke_width=sw)
                else:
                    txt_clip = TextClip(clean_w, fontsize=exact_fontsize_hq, color=txt_color, font=word_font)
                
                if angle in [90, -90]:
                    frame = txt_clip.get_frame(0)
                    mask_frame = txt_clip.mask.get_frame(0)
                    k = 1 if angle == 90 else 3
                    rot_frame = np.rot90(frame, k=k).copy()
                    rot_mask = np.rot90(mask_frame, k=k).copy()
                    from moviepy.editor import ImageClip
                    txt_clip = ImageClip(rot_frame).set_mask(ImageClip(rot_mask, ismask=True))
                    
                # Kinetic Easing and Micro-movements
                def kinetic_scale(t):
                    if t < 0.15:
                        p = t / 0.15
                        ease = 1 - (1 - p)**3 # Ease out cubic
                        base = 0.7 + 0.3 * ease
                    else:
                        # Micro-movement (Scale Bob)
                        base = 1.0 + 0.02 * np.sin((t - 0.15) * 5)
                    # Divide by 2 because the clip is rendered at 2x resolution!
                    return base * 0.5
                        
                txt_clip = txt_clip.fx(vfx.resize, kinetic_scale)
                    
                # NO STRETCHING! We are back to uniform scaling to keep words perfectly readable
                # Center dynamically inside a transparent block composite
                txt_clip = txt_clip.set_position('center')
                panel = CompositeVideoClip([txt_clip], size=(block['w'], block['h']))
                panel = panel.set_position((block['x'], block['y'])).set_start(start_t).set_end(end_t)
                text_clips.append(panel)
                
            except Exception as e:
                print(f"Failed to create block for word '{clean_w}': {e}")
                pass
            
    # Add Watermark
    wm_color = random.choice(colors)
    # Using one of the loaded fonts, small size
    watermark = TextClip("tkdprotocol", fontsize=40, color=wm_color, font=fonts[0]['path'])
    # Low opacity, positioned in the bottom right with a small offset (done via margin or relative position)
    watermark_end = max(0, duration - 3.0)
    watermark = watermark.set_opacity(0.3).set_position((W - watermark.w - 30, H - watermark.h - 30)).set_start(0).set_end(watermark_end)

    outro_text = TextClip("tkdprotocol", fontsize=100, color='black', font=fonts[0]['path'])
    outro_text = outro_text.set_position('center').set_start(watermark_end).set_end(duration)

    # Combine everything
    final_video = CompositeVideoClip([bg] + text_clips + [watermark, outro_text]).set_duration(duration)
    # final_video = final_video.set_audio(audio_clip)
    
    try:
        temp_video = output_video.replace('.mp4', '_temp.mp4')
        # Render silent video first to prevent MoviePy buffer starvation/broken pipes
        final_video.write_videofile(temp_video, fps=24, codec="libx264", audio=False, logger=logger)
        
        print("Muxing audio and video natively via FFMPEG...")
        import subprocess
        subprocess.run([
            "ffmpeg", "-y",
            "-i", temp_video,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            output_video
        ], check=True)
        
        # Clean up the silent temp video
        if os.path.exists(temp_video):
            os.remove(temp_video)
            
    finally:
        print(f"Rendering video to {output_video}...")

if __name__ == "__main__":
    # Render the FULL length lyric video
    create_lyric_video("audio.mp3", "aligned_timestamps.json", "beats.json", "full_lyric_video.mp4", max_duration=None)
