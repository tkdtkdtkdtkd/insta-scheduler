import os
os.environ["IMAGEMAGICK_BINARY"] = "/opt/homebrew/bin/magick"
import random
import numpy as np
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS

from moviepy.editor import TextClip, CompositeVideoClip, ColorClip

def create_lyric_image(sentence, output_image, aspect_ratio="16:9"):
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
        margin_top = 300
        margin_bottom = 750
        margin_left = 150
        margin_right = 250

    text_clips = []
    
    # Styles for premium look - user approved fonts with specific percentage weights
    fonts = [
        {'name': 'Impact', 'path': '/System/Library/Fonts/Supplemental/Impact.ttf', 'type': 'caps', 'weight': 50},
        {'name': 'Chalkduster', 'path': '/System/Library/Fonts/Supplemental/Chalkduster.ttf', 'type': 'normal', 'weight': 30},
        {'name': 'Trattatello', 'path': '/System/Library/Fonts/Supplemental/Trattatello.ttf', 'type': 'normal', 'weight': 20}
    ]
    # Extreme neon colors for fonts
    colors = ['#FF0055', '#00FFCC', '#FFFF00', '#FF3300', '#9900FF', '#0066FF', '#FF00CC', '#FFFFFF']
    
    # Base background (Dark grey, mostly covered by blocks)
    bg = ColorClip(size=(W, H), color=(10, 10, 10)).set_duration(1)
    
    words = [w for w in sentence.split() if w.strip()]
    scene_size = len(words)
    
    if scene_size == 0:
        bg.save_frame(output_image, t=0)
        return
    
    # --- BSP Algorithm to split a rectangle into N rectangles ---
    def generate_blocks(num_blocks, start_x, start_y, width, height):
        rects = [{'x': start_x, 'y': start_y, 'w': width, 'h': height}]
        
        while len(rects) < num_blocks:
            areas = [r['w'] * r['h'] for r in rects]
            idx = random.choices(range(len(rects)), weights=areas, k=1)[0]
            rect = rects.pop(idx)
            
            if rect['w'] > rect['h'] * 1.5:
                split = 'v'
            elif rect['h'] > rect['w'] * 1.5:
                split = 'h'
            else:
                split = random.choice(['v', 'h'])
                
            split_ratio = random.uniform(0.3, 0.7)
            
            if split == 'v':
                cut_w = int(rect['w'] * split_ratio)
                rects.append({'x': rect['x'], 'y': rect['y'], 'w': cut_w, 'h': rect['h']})
                rects.append({'x': rect['x'] + cut_w, 'y': rect['y'], 'w': rect['w'] - cut_w, 'h': rect['h']})
            else:
                cut_h = int(rect['h'] * split_ratio)
                rects.append({'x': rect['x'], 'y': rect['y'], 'w': rect['w'], 'h': cut_h})
                rects.append({'x': rect['x'], 'y': rect['y'] + cut_h, 'w': rect['w'], 'h': rect['h'] - cut_h})
                
        return rects

    blocks = generate_blocks(scene_size, margin_left, margin_top, W - margin_left - margin_right, H - margin_top - margin_bottom)
    random.shuffle(blocks)
    
    font_weights = [f.get('weight', 1) for f in fonts]
    
    word_clips = []
    for word in words:
        clean_w = word.replace(',', '').replace('.', '').replace(';', '').strip().upper()
            
        chosen_font = random.choices(fonts, weights=font_weights, k=1)[0]
        font = chosen_font['path']
        is_bold = chosen_font.get('bold', False)
            
        if is_bold:
            dummy = TextClip(clean_w, fontsize=100, color='white', font=font, stroke_color='white', stroke_width=2)
        else:
            dummy = TextClip(clean_w, fontsize=100, color='white', font=font)
            
        word_clips.append({
            'clean_w': clean_w,
            'dummy_w': dummy.w,
            'dummy_h': dummy.h,
            'ar': dummy.w / dummy.h,
            'font': font,
            'is_bold': is_bold
        })
        
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
        
        if w_obj['ar'] > 1.2 and block['ar'] < 0.8:
            w_obj['angle'] = random.choice([90, -90])
        else:
            w_obj['angle'] = 0
            
    for w_obj in word_clips:
        block = w_obj['block']
        clean_w = w_obj['clean_w']
        angle = w_obj['angle']
        txt_color = random.choice(colors)
        
        try:
            target_w = block['w']
            target_h = block['h']
            
            if angle != 0:
                target_w = block['h']
                target_h = block['w']
                
            ratio = min(target_w / w_obj['dummy_w'], target_h / w_obj['dummy_h'])
            exact_fontsize = max(int(100 * ratio), 10)
            
            exact_fontsize_hq = exact_fontsize * 2
            
            word_font = w_obj['font']
            word_is_bold = w_obj['is_bold']
            
            if word_is_bold:
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
                
            # No kinetic scaling needed for static image, just base scale
            import moviepy.video.fx.all as vfx
            # 0.5 because rendered at 2x
            txt_clip = txt_clip.fx(vfx.resize, 0.5)
                
            txt_clip = txt_clip.set_position('center')
            # Use duration 1 for static image
            panel = CompositeVideoClip([txt_clip], size=(block['w'], block['h'])).set_duration(1)
            panel = panel.set_position((block['x'], block['y']))
            text_clips.append(panel)
            
        except Exception as e:
            print(f"Failed to create block for word '{clean_w}': {e}")
            pass
        
    final_image = CompositeVideoClip([bg] + text_clips).set_duration(1)
    
    print(f"Rendering image to {output_image}...")
    final_image.save_frame(output_image, t=0)

if __name__ == "__main__":
    create_lyric_image("THIS IS A TEST SENTENCE", "test_image.png")
