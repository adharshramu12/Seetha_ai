import tkinter as tk
from PIL import Image, ImageTk, ImageDraw
import os
import time
import random
import threading
from seetha.logger import setup_logger

logger = setup_logger()

class SeethaAvatar(tk.Frame):
    def __init__(self, parent, assets_dir):
        super().__init__(parent)
        self.parent = parent
        self.assets_dir = assets_dir
        
        # Load Images
        self.main_image_path = os.path.join(assets_dir, "seetha_main.png")
        self.talking_image_path = os.path.join(assets_dir, "seetha_talking.png")
        
        self.raw_main = None
        self.raw_talking = None

        # Pre-calculated resized frames (PIL) and ready-to-show Tk photos.
        # PhotoImages are built ONCE per size — swapping between prebuilt
        # photos is what makes the animation flicker-free.
        self.cached_frames = {}
        self.cached_photos = {}
        self.current_size_key = None
        
        self.load_images()
        
        self.label = tk.Label(self, bg='black') # High contrast background
        self.label.pack(expand=True, fill='both', padx=0, pady=0)
        
        # Animation State
        self.is_speaking = False
        self.is_blinking = False
        self.target_height = 450
        
        # Internal Logic
        self.blink_timer = 0
        self.next_blink = 100
        self.speech_phase = 0.0 # for sine wave
        self.last_frame_key = None # To prevent redundant updates
        
        # Pre-cache initial size
        self._cache_images_for_height(self.target_height)
        
        # Bind resize event to re-cache
        self.bind("<Configure>", self.on_resize)
        
        # Start Animation Loop
        self.animate()

    def load_images(self):
        try:
            if os.path.exists(self.main_image_path):
                self.raw_main = Image.open(self.main_image_path).convert("RGBA")
            else:
                logger.warning("seetha_main.png not found")

            if os.path.exists(self.talking_image_path):
                self.raw_talking = Image.open(self.talking_image_path).convert("RGBA")
            else:
                logger.warning("seetha_talking.png missing.")
                self.raw_talking = self.raw_main # Fallback
        except Exception as e:
            logger.error(f"Error loading images: {e}")

    def _cache_images_for_height(self, height):
        """Resizes and caches images ONLY when size changes, prevents flickering."""
        if not self.raw_main or height <= 0: return
        
        # Check cache
        if self.current_size_key == height: return
        
        try:
            aspect = self.raw_main.width / self.raw_main.height
            width = int(height * aspect)
            
            # High quality resize ONCE
            self.cached_frames['main'] = self.raw_main.resize((width, height), Image.Resampling.LANCZOS)
            if self.raw_talking:
                self.cached_frames['talking'] = self.raw_talking.resize((width, height), Image.Resampling.LANCZOS)
            
            # Pre-calculate closed eyes frame (to avoid drawing every frame)
            # Use 'main' as base
            closed_eyes = self.cached_frames['main'].copy()
            draw = ImageDraw.Draw(closed_eyes)
            
            # Enhanced Eye Logic
            # 1. Sample skin color more accurately
            # Positions are proportional
            w, h = width, height
            le_x, le_y = w * 0.38, h * 0.48
            
            try:
                # Sample from forehead area
                skin_color = self.cached_frames['main'].getpixel((int(w*0.5), int(h*0.4)))
            except:
                skin_color = "#8d5524" # Generic Indian skin tone
            
            # Draw Eyelids (Slightly darker line for lash)
            le_w, le_h = w * 0.12, h * 0.035
            re_x, re_y = w * 0.53, h * 0.48
            
            # Fill
            draw.ellipse([(le_x, le_y), (le_x + le_w, le_y + le_h)], fill=skin_color) 
            draw.ellipse([(re_x, re_y), (re_x + le_w, re_y + le_h)], fill=skin_color)
            
            # Lash line
            draw.line([(le_x, le_y + le_h/2), (le_x + le_w, le_y + le_h/2)], fill='black', width=2)
            draw.line([(re_x, re_y + le_h/2), (re_x + le_w, re_y + le_h/2)], fill='black', width=2)
            
            self.cached_frames['blink'] = closed_eyes

            # Build the Tk PhotoImages ONCE here (not per animation frame).
            # Creating a new PhotoImage every frame releases the one the
            # label is currently showing, which makes Tk paint a blank
            # frame for an instant = the talking flicker.
            self.cached_photos = {
                key: ImageTk.PhotoImage(img)
                for key, img in self.cached_frames.items()
            }

            self.current_size_key = height
            self.last_frame_key = None  # force a redraw with the new size
            # logger.debug(f"Cached avatar frames for height {height}")

        except Exception as e:
            logger.error(f"Cache error: {e}")

    def on_resize(self, event):
        # Only re-cache if height changes significantly
        if abs(event.height - self.target_height) > 10:
            self.target_height = event.height
            self._cache_images_for_height(self.target_height)

    def update_frame(self):
        if not self.cached_photos.get('main'):
            return

        frame_key = 'main'

        # 1. Speaking Logic (Sine Wave)
        if self.is_speaking and self.cached_photos.get('talking'):
            self.speech_phase += 0.4 # Speed of speech
            # Use sine to oscillate: > 0 means open mouth
            import math
            frame_key = 'talking' if math.sin(self.speech_phase) > 0 else 'main'

        # 2. Blinking Logic (Override speech if blinking)
        self.blink_timer += 1
        if self.blink_timer > self.next_blink:
            self.is_blinking = True
            if self.cached_photos.get('blink'):
                frame_key = 'blink'

            if self.blink_timer > self.next_blink + 3: # 150ms close
                self.is_blinking = False
                self.blink_timer = 0
                self.next_blink = random.randint(40, 150) # Natural variance

        # Only touch the label when the frame actually changes, and swap
        # between PRE-BUILT PhotoImages — never allocate during animation.
        if frame_key == self.last_frame_key:
            return
        self.last_frame_key = frame_key
        self.label.config(image=self.cached_photos[frame_key])

    def animate(self):
        try:
            self.update_frame()
            self.after(50, self.animate) # 20 FPS is smooth enough
        except Exception:
            pass 

    def start_speaking(self):
        self.is_speaking = True

    def stop_speaking(self):
        self.is_speaking = False
        self.speech_phase = 0

    def close(self):
        pass
