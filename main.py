import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os
import shutil
import uuid
import threading
import sys
import time
import urllib.request
import numpy as np

# --- 1. RAPIDOCR IMPORT ---
try:
    from rapidocr_onnxruntime import RapidOCR
    OCR_AVAILABLE = True
    ocr_engine = RapidOCR()
except ImportError as e:
    print(f"DEBUG: RapidOCR import failed: {e}")
    OCR_AVAILABLE = False
    ocr_engine = None

# --- 2. LOCAL KOKORO TTS ---
try:
    import soundfile as sf
    from kokoro_onnx import Kokoro
    import pygame
    KOKORO_AVAILABLE = True
    pygame.mixer.init()
except ImportError as e:
    print(f"DEBUG: Kokoro/Soundfile import failed: {e}")
    KOKORO_AVAILABLE = False

# --- 3. VIDEO GENERATION ---
try:
    from gtts import gTTS
    from moviepy.editor import ImageClip, concatenate_videoclips, AudioFileClip, ColorClip
    VIDEO_LIB_AVAILABLE = True
except ImportError:
    try:
        from gtts import gTTS
        from moviepy import ImageClip, concatenate_videoclips, AudioFileClip, ColorClip
        VIDEO_LIB_AVAILABLE = True
    except ImportError as e:
        print(f"DEBUG: Video libraries failed: {e}")
        VIDEO_LIB_AVAILABLE = False

# --- THEME & FONT SETUP ---
ctk.set_appearance_mode("Dark")

BUTTON_HEIGHT = 40
BUTTON_PADDING = 15  # Global padding variable
THEME_COLOR = "#e80049" 

# 1. Load Local Font
font_path = os.path.abspath(os.path.join("assets", "font", "Archivo.ttf"))

if os.path.exists(font_path):
    print(f"Loading font from: {font_path}")
    try:
        ctk.FontManager.load_font(font_path)
    except Exception as e:
        print(f"Font loading warning: {e}")
else:
    print(f"Font not found at: {font_path}")

# 2. Load Custom Theme
theme_path = os.path.join("assets", "custom_theme.json")
try:
    if os.path.exists(theme_path):
        ctk.set_default_color_theme(theme_path)
    else:
        ctk.set_default_color_theme("blue")
except Exception as e:
    print(f"Theme load error: {e}. Falling back to blue.")
    ctk.set_default_color_theme("blue")


class MovicStudio(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Movic Studio")
        self.geometry("1400x900")

        self.project_dir = os.path.join(os.getcwd(), "cache")
        self.images_dir = os.path.join(self.project_dir, "images")
        self.audio_dir = os.path.join(self.project_dir, "audio")
        self.test_dir = os.path.join(self.project_dir, "test")
        
        self.models_dir = os.path.join(os.getcwd(), "models")
        
        self.ensure_dirs()
        
        self.panels_data = [] 
        self.current_step = 1
        
        self.kokoro = None
        self.model_path = os.path.join(self.models_dir, "kokoro-v1.0.int8.onnx")
        self.voices_path = os.path.join(self.models_dir, "voices-v1.0.bin")
        
        self.kokoro_voices = [
            "af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica", 
            "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
            "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", 
            "am_michael", "am_onyx", "am_puck", "am_santa",
            
            "bf_alice", "bf_emma", "bf_isabella", "bf_lily", 
            "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
            "gtts_robot"
        ]
        
        self.display_to_id = {self.get_voice_display_name(v): v for v in self.kokoro_voices}
        self.formatted_voice_list = list(self.display_to_id.keys())
        
        self.available_voices = ["Voice 1", "Voice 2"]
        self.voice_model_map = {
            "Voice 1": self.get_voice_display_name("am_michael"),
            "Voice 2": self.get_voice_display_name("af_bella")
        }

        if KOKORO_AVAILABLE:
            threading.Thread(target=self.init_kokoro, daemon=True).start()

        self.original_image = None
        self.CANVAS_PAD = 50 
        self.cutter_scale = 1.0; self.cutter_ox = 0; self.cutter_oy = 0
        self.editor_scale = 1.0; self.editor_ox = 0; self.editor_oy = 0
        self.rectangles = []; self.start_x = None; self.start_y = None; self.current_rect = None
        self.current_editing_index = -1; self.swap_source_index = None 
        self.editor_region_map = {} 

        # Main Container
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        # Nav Bar
        self.nav_bar = ctk.CTkFrame(self, height=60, fg_color="transparent")
        self.nav_bar.pack(fill="x", side="bottom", padx=20, pady=20)

        # --- REFACTORED NAV BUTTONS ---
        self.btn_back = self.create_btn(
            self.nav_bar, "Back", self.go_back, 
            mode="outline", width=120, state="disabled"
        )
        self.btn_back.pack(side="left", padx=BUTTON_PADDING)

        self.btn_next = self.create_btn(
            self.nav_bar, "Next", self.go_next, 
            mode="primary", width=120
        )
        self.btn_next.pack(side="right", padx=BUTTON_PADDING)

        self.frames = {}
        self.frames[1] = ctk.CTkFrame(self.container, fg_color="transparent")
        self.setup_panel_cutter_ui(self.frames[1])
        self.frames[2] = ctk.CTkFrame(self.container, fg_color="transparent")
        self.setup_text_selector_ui(self.frames[2])
        self.frames[3] = ctk.CTkFrame(self.container, fg_color="transparent")
        self.setup_animator_ui(self.frames[3])

        self.show_step(1)
        self.bind("<Control-z>", lambda event: self.handle_undo())

    # --- NEW HELPER FUNCTION ---
    def create_btn(self, parent, text, command, mode="primary", width=None, height=BUTTON_HEIGHT, **kwargs):
        """
        Abstracts button creation.
        Modes: 'primary' (solid color), 'outline' (transparent with border), 'ghost' (transparent no border)
        """
        cfg = {
            "text": text,
            "command": command,
            "height": height,
            "font": ("Archivo", 14),
            "corner_radius": 20
        }
        
        # Apply specific styling based on mode
        if mode == "primary":
            # Default theme color is automatic, but we can enforce text color
            cfg["text_color"] = "white"
        elif mode == "outline":
            cfg["fg_color"] = "transparent"
            cfg["border_width"] = 2
            cfg["border_color"] = kwargs.get("border_color", "#888") # Default gray border
            cfg["text_color"] = "white"
        elif mode == "ghost":
            cfg["fg_color"] = "transparent"
            cfg["hover_color"] = "#444"
            cfg["text_color"] = "white"
        
        if width:
            cfg["width"] = width
            
        # Merge extra kwargs (allows overriding any default)
        cfg.update(kwargs)
        
        return ctk.CTkButton(parent, **cfg)

    def get_voice_display_name(self, voice_id):
        try:
            if voice_id == "gtts_robot":
                return "[System] [Bot] Robot"
                
            parts = voice_id.split('_')
            prefix = parts[0]
            name = parts[1].capitalize()
            
            lang_map = {
                'a': 'US', 'b': 'UK', 'j': 'JP', 'z': 'ZH', 
                'e': 'ES', 'f': 'FR', 'h': 'HI', 'i': 'IT', 'p': 'BR'
            }
            gender_map = {'f': 'FEM', 'm': 'MALE'}
            
            lang = lang_map.get(prefix[0], '??')
            gender = gender_map.get(prefix[1], '?')
            
            return f"[{lang}] [{gender}] {name}"
        except:
            return voice_id

    def ensure_dirs(self):
        if os.path.exists(self.project_dir):
            try:
                shutil.rmtree(self.project_dir)
                print(f"Cleared cache at: {self.project_dir}")
            except Exception as e:
                print(f"Warning: Could not clear cache: {e}")
        
        os.makedirs(self.project_dir, exist_ok=True)
        os.makedirs(self.images_dir, exist_ok=True)
        os.makedirs(self.audio_dir, exist_ok=True)
        os.makedirs(self.test_dir, exist_ok=True)
        os.makedirs(self.models_dir, exist_ok=True)

    def init_kokoro(self):
        try:
            if not os.path.exists(self.model_path):
                print(f"Error: Model not found at {self.model_path}")
                return
            
            if not os.path.exists(self.voices_path):
                print(f"Error: Voices file not found at {self.voices_path}")
                return

            print("Loading Kokoro...")
            self.kokoro = Kokoro(self.model_path, self.voices_path)
            print("Kokoro Ready!")
        except Exception as e:
            print(f"Failed to load Kokoro: {e}")

    def generate_audio_clip_kokoro(self, text, voice_style, output_path):
        if not self.kokoro:
            raise Exception("Kokoro model not loaded yet.")
        audio, sample_rate = self.kokoro.create(text, voice=voice_style, speed=1.0, lang="en-us")
        sf.write(output_path, audio, sample_rate)
        return output_path

    def show_step(self, step_num):
        for f in self.frames.values(): f.pack_forget()
        self.frames[step_num].pack(fill="both", expand=True)
        self.current_step = step_num
        
        if step_num == 1:
            self.btn_back.configure(state="disabled", fg_color="transparent", text_color="gray", border_width=2, border_color="gray")
            self.btn_next.configure(text="Next", state="normal", command=self.go_next)
        else:
            self.btn_back.configure(state="normal", fg_color="transparent", text_color="white", border_color="#888")
            
        if step_num == 3:
            self.btn_next.configure(text="Generate Video", command=self.run_generation)
        else:
            self.btn_next.configure(text="Next", command=self.go_next)

    def go_next(self):
        if self.current_step == 1:
            if not self.rectangles:
                messagebox.showwarning("No Panels", "Please draw at least one panel box first.")
                return
            if self.save_panels():
                self.start_batch_processing()
        elif self.current_step == 2:
            self.refresh_animator_ui() 
            self.show_step(3)

    def go_back(self):
        if self.current_step > 1: self.show_step(self.current_step - 1)

    def handle_undo(self):
        if self.current_step == 1:
            self.undo_selection(self.canvas_cutter, self.rectangles)
        elif self.current_step == 2 and self.text_editor_frame.winfo_viewable():
            if self.text_rects:
                item = self.text_rects.pop()
                rect_id = item[0]
                self.canvas_text.delete(rect_id)
                if rect_id in self.editor_region_map:
                    self.editor_region_map[rect_id]['widget_frame'].destroy()
                    del self.editor_region_map[rect_id]

    def undo_selection(self, canvas, rect_list):
        if rect_list:
            item = rect_list.pop()
            canvas.delete(item[0])

    def start_batch_processing(self):
        if not OCR_AVAILABLE or ocr_engine is None:
            self.show_step(2)
            self.refresh_text_selector_ui()
            return

        self.loading_window = ctk.CTkToplevel(self)
        self.loading_window.title("Processing")
        self.loading_window.geometry("350x150")
        self.loading_window.attributes("-topmost", True)
        try:
            x = self.winfo_x() + (self.winfo_width() // 2) - 175
            y = self.winfo_y() + (self.winfo_height() // 2) - 75
            self.loading_window.geometry(f"+{x}+{y}")
        except: pass
        
        ctk.CTkLabel(self.loading_window, text="✨ Auto-Detecting Text...", font=("Archivo", 16, "bold")).pack(pady=20)
        self.progress_label = ctk.CTkLabel(self.loading_window, text="Initializing...", text_color="gray")
        self.progress_label.pack(pady=10)
        
        self.btn_next.configure(state="disabled")
        self.btn_back.configure(state="disabled")
        threading.Thread(target=self.batch_ocr_worker, daemon=True).start()

    def batch_ocr_worker(self):
        total = len(self.panels_data)
        for i, panel in enumerate(self.panels_data):
            self.after(0, lambda p=i+1, t=total: self.progress_label.configure(text=f"Scanning Panel {p} of {t}..."))
            if panel.get('text_regions'): continue
            try:
                result, _ = ocr_engine(panel['path'])
                if result:
                    merged_boxes = self.merge_close_boxes(result, vertical_threshold=1.0)
                    new_regions = []
                    for box in merged_boxes:
                        new_regions.append({
                            'coords': (box['xmin'], box['ymin'], box['xmax'], box['ymax']),
                            'text': box['text'],
                            'voice': "Voice 1"
                        })
                    panel['text_regions'] = new_regions
            except Exception as e: print(f"OCR Error: {e}")
        self.after(0, self.finish_batch_processing)

    def finish_batch_processing(self):
        if hasattr(self, 'loading_window') and self.loading_window.winfo_exists():
            self.loading_window.destroy()
        self.btn_next.configure(state="normal")
        self.btn_back.configure(state="normal")
        self.show_step(2)
        self.refresh_text_selector_ui()

    def merge_close_boxes(self, boxes, vertical_threshold=1.0):
        if not boxes: return []
        cleaned_boxes = []
        for b in boxes:
            points, text, score = b
            ys = [p[1] for p in points]; xs = [p[0] for p in points]
            height = max(ys) - min(ys)
            cleaned_boxes.append({'ymin': min(ys), 'ymax': max(ys), 'xmin': min(xs), 'xmax': max(xs), 'text': text, 'height': height})
        cleaned_boxes.sort(key=lambda x: x['ymin'])
        merged = []
        if not cleaned_boxes: return []
        current_group = cleaned_boxes[0]
        for i in range(1, len(cleaned_boxes)):
            next_box = cleaned_boxes[i]
            gap = next_box['ymin'] - current_group['ymax']
            if gap < (next_box['height'] * vertical_threshold):
                current_group['ymax'] = max(current_group['ymax'], next_box['ymax'])
                current_group['xmin'] = min(current_group['xmin'], next_box['xmin'])
                current_group['xmax'] = max(current_group['xmax'], next_box['xmax'])
                current_group['text'] += " " + next_box['text']
            else:
                merged.append(current_group)
                current_group = next_box
        merged.append(current_group)
        return merged

    def setup_panel_cutter_ui(self, parent):
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(0, weight=1)
        self.pc_sidebar = ctk.CTkFrame(parent, width=200, corner_radius=0)
        self.pc_sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        ctk.CTkLabel(self.pc_sidebar, text="Step 1: Panelize", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 10))
        
        # --- REFACTORED BUTTONS ---
        self.create_btn(
            self.pc_sidebar, "Load Image", self.load_image, mode="primary"
        ).pack(padx=BUTTON_PADDING, pady=10, fill="x")
        
        self.create_btn(
            self.pc_sidebar, "Undo (Ctrl+Z)", 
            lambda: self.undo_selection(self.canvas_cutter, self.rectangles), 
            mode="outline"
        ).pack(padx=BUTTON_PADDING, pady=20, fill="x")
        
        self.status_label = ctk.CTkLabel(self.pc_sidebar, text="No image loaded", text_color="gray")
        self.status_label.pack(side="bottom", pady=20)
        self.canvas_frame = ctk.CTkFrame(parent)
        self.canvas_frame.grid(row=0, column=1, sticky="nsew")
        
        self.canvas_cutter = tk.Canvas(self.canvas_frame, bg="#1a1a1a", highlightthickness=0)
        self.canvas_cutter.pack(fill="both", expand=True)
        self.canvas_cutter.bind("<ButtonPress-1>", lambda e: self.on_press(e, self.canvas_cutter))
        self.canvas_cutter.bind("<B1-Motion>", lambda e: self.on_drag(e, self.canvas_cutter))
        self.canvas_cutter.bind("<ButtonRelease-1>", lambda e: self.on_release_panel(e))

    def load_image(self):
        file_path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.webp")])
        if not file_path: return
        self.original_image = Image.open(file_path)
        self.reset_canvas(self.canvas_cutter, self.rectangles)
        self.after(50, lambda: self.display_image_on_canvas(self.original_image, self.canvas_cutter, context="cutter"))
        self.status_label.configure(text="Draw boxes to cut")

    def reset_canvas(self, canvas, rect_list):
        canvas.delete("all")
        rect_list.clear()

    def display_image_on_canvas(self, img_obj, canvas, context="cutter"):
        if not img_obj: return
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        if cw <= 1: 
            self.after(100, lambda: self.display_image_on_canvas(img_obj, canvas, context))
            return
        avail_w, avail_h = cw - (self.CANVAS_PAD * 2), ch - (self.CANVAS_PAD * 2)
        iw, ih = img_obj.size
        scale = min(avail_w / iw, avail_h / ih)
        new_w, new_h = int(iw * scale), int(ih * scale)
        display_image = img_obj.resize((new_w, new_h), Image.Resampling.LANCZOS)
        tk_image = ImageTk.PhotoImage(display_image)
        canvas.image_ref = tk_image 
        offset_x, offset_y = (cw - new_w) // 2, (ch - new_h) // 2
        if context == "cutter":
            self.cutter_scale, self.cutter_ox, self.cutter_oy = scale, offset_x, offset_y
        else:
            self.editor_scale, self.editor_ox, self.editor_oy = scale, offset_x, offset_y
        
        canvas.create_rectangle(0, 0, cw, ch, fill="#1a1a1a", outline="") 
        canvas.create_image(offset_x, offset_y, anchor="nw", image=tk_image)
        canvas.create_rectangle(offset_x, offset_y, offset_x + new_w, offset_y + new_h, outline="#444", width=1)

    def on_press(self, event, canvas):
        self.start_x = canvas.canvasx(event.x)
        self.start_y = canvas.canvasy(event.y)
        self.current_rect = canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline=THEME_COLOR, width=2, dash=(4, 2))

    def on_drag(self, event, canvas):
        if not self.current_rect: return
        canvas.coords(self.current_rect, self.start_x, self.start_y, canvas.canvasx(event.x), canvas.canvasy(event.y))

    def on_release_panel(self, event):
        if not self.current_rect: return
        x1, x2 = sorted([self.start_x, self.canvas_cutter.canvasx(event.x)])
        y1, y2 = sorted([self.start_y, self.canvas_cutter.canvasy(event.y)])
        if (x2 - x1) < 5 or (y2 - y1) < 5: 
            self.canvas_cutter.delete(self.current_rect)
        else: 
            unique_id = str(uuid.uuid4())
            self.rectangles.append((self.current_rect, (x1, y1, x2, y2), unique_id))
        self.current_rect = None

    def save_panels(self):
        if not self.rectangles: return False
        existing_data_map = {p['id']: p for p in self.panels_data}
        new_panels_data = []
        self.rectangles.sort(key=lambda r: (r[1][1], r[1][0])) 
        for i, (_, (cx1, cy1, cx2, cy2), unique_id) in enumerate(self.rectangles):
            ix1 = (cx1 - self.cutter_ox) / self.cutter_scale
            iy1 = (cy1 - self.cutter_oy) / self.cutter_scale
            ix2 = (cx2 - self.cutter_ox) / self.cutter_scale
            iy2 = (cy2 - self.cutter_oy) / self.cutter_scale
            fx1, fy1 = max(0, min(self.original_image.width, ix1)), max(0, min(self.original_image.height, iy1))
            fx2, fy2 = max(0, min(self.original_image.width, ix2)), max(0, min(self.original_image.height, iy2))
            if (fx2 - fx1) < 1 or (fy2 - fy1) < 1: continue
            try:
                crop = self.original_image.crop((fx1, fy1, fx2, fy2))
                filename = f"panel_{unique_id[:8]}.png" 
                save_path = os.path.join(self.images_dir, filename)
                crop.save(save_path)
                previous_entry = existing_data_map.get(unique_id)
                new_panels_data.append({
                    "id": unique_id,
                    "path": save_path,
                    "text_regions": previous_entry['text_regions'] if previous_entry else []
                })
            except Exception as e: print(f"Error saving {i}: {e}")
        self.panels_data = new_panels_data
        return True

    def setup_text_selector_ui(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)
        
        # --- 1. GRID FRAME (Panel Selector) ---
        self.text_grid_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.text_grid_frame.grid(row=0, column=0, sticky="nsew")
        self.text_grid_frame.grid_columnconfigure(0, weight=1)
        
        self.text_grid_frame.grid_rowconfigure(0, weight=0) # Label
        self.text_grid_frame.grid_rowconfigure(1, weight=1) # Scroll frame expands
        
        ctk.CTkLabel(self.text_grid_frame, text="Step 2: Reorder & Select Text", font=("Archivo", 18, "bold")).grid(row=0, column=0, pady=(40, 10))
        
        self.scroll_frame = ctk.CTkScrollableFrame(self.text_grid_frame, orientation="horizontal", height=320, label_text="Panels")
        self.scroll_frame.grid(row=1, column=0, sticky="ew", padx=20)
        
        # --- 2. EDITOR FRAME ---
        self.text_editor_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.text_editor_frame.grid_columnconfigure(1, weight=3) 
        self.text_editor_frame.grid_columnconfigure(2, weight=1) 
        self.text_editor_frame.grid_rowconfigure(0, weight=1)
        
        self.te_sidebar = ctk.CTkFrame(self.text_editor_frame, width=150, corner_radius=0)
        self.te_sidebar.grid(row=0, column=0, sticky="nsew")
        
        ctk.CTkLabel(self.te_sidebar, text="Tools", font=("Archivo", 14, "bold")).pack(pady=20)
        
        # --- REFACTORED SIDEBAR BUTTONS ---
        self.create_btn(
            self.te_sidebar, "Undo Box", self.handle_undo, mode="outline", height=32
        ).pack(pady=10, padx=BUTTON_PADDING, fill="x")

        self.btn_auto_detect = self.create_btn(
            self.te_sidebar, "✨ Auto Detect", self.run_auto_detect, mode="primary", height=32
        )
        self.btn_auto_detect.pack(pady=10, padx=BUTTON_PADDING, fill="x")
        
        self.create_btn(
            self.te_sidebar, "Save & Back", self.save_text_regions, mode="primary", height=32
        ).pack(pady=20, padx=BUTTON_PADDING, fill="x")
        
        self.lbl_ocr_status = ctk.CTkLabel(self.te_sidebar, text="OCR: Ready", text_color="gray")
        self.lbl_ocr_status.pack(side="bottom", pady=10)
        
        self.canvas_text = tk.Canvas(self.text_editor_frame, bg="#1a1a1a", highlightthickness=0)
        self.canvas_text.grid(row=0, column=1, sticky="nsew", padx=5)
        
        self.te_data_panel = ctk.CTkFrame(self.text_editor_frame, width=300, corner_radius=0)
        self.te_data_panel.grid(row=0, column=2, sticky="nsew", padx=(0,0))
        ctk.CTkLabel(self.te_data_panel, text="Detected Text", font=("Archivo", 16, "bold")).pack(pady=10)
        self.ocr_scroll = ctk.CTkScrollableFrame(self.te_data_panel, label_text="Text Regions")
        self.ocr_scroll.pack(fill="both", expand=True, padx=5, pady=5)
        self.text_rects = []
        self.canvas_text.bind("<ButtonPress-1>", lambda e: self.on_press(e, self.canvas_text))
        self.canvas_text.bind("<B1-Motion>", lambda e: self.on_drag(e, self.canvas_text))
        self.canvas_text.bind("<ButtonRelease-1>", lambda e: self.on_release_text(e))

    def on_release_text(self, event):
        if not self.current_rect: return
        x1, x2 = sorted([self.start_x, self.canvas_text.canvasx(event.x)])
        y1, y2 = sorted([self.start_y, self.canvas_text.canvasy(event.y)])
        if (x2 - x1) < 5 or (y2 - y1) < 5: 
            self.canvas_text.delete(self.current_rect)
        else: 
            self.text_rects.append((self.current_rect, (x1, y1, x2, y2)))
            ix1 = (x1 - self.editor_ox) / self.editor_scale
            iy1 = (y1 - self.editor_oy) / self.editor_scale
            ix2 = (x2 - self.editor_ox) / self.editor_scale
            iy2 = (y2 - self.editor_oy) / self.editor_scale
            current_panel = self.panels_data[self.current_editing_index]
            text_result = self.run_rapidocr_crop(current_panel['path'], (ix1, iy1, ix2, iy2))
            self.add_sidebar_entry(self.current_rect, text_result, "Voice 1")
        self.current_rect = None

    def run_single_panel_scan(self):
        if not OCR_AVAILABLE: return
        self.reset_canvas(self.canvas_text, self.text_rects)
        for w in self.ocr_scroll.winfo_children(): w.destroy()
        self.editor_region_map = {}
        current_panel = self.panels_data[self.current_editing_index]
        img = Image.open(current_panel['path'])
        self.display_image_on_canvas(img, self.canvas_text, context="editor")
        def _scan():
            res, _ = ocr_engine(current_panel['path'])
            self.after(0, lambda: self.apply_auto_detect_results(res))
        threading.Thread(target=_scan).start()

    def run_auto_detect(self):
        if not OCR_AVAILABLE or ocr_engine is None: return
        current_panel = self.panels_data[self.current_editing_index]
        self.lbl_ocr_status.configure(text="Scanning...", text_color=THEME_COLOR)
        self.loading_card = ctk.CTkFrame(self.ocr_scroll, fg_color="transparent")
        self.loading_card.pack(fill="x", pady=20)
        ctk.CTkLabel(self.loading_card, text="✨ Scanning...", text_color="gray", font=("Archivo", 14, "bold")).pack()
        def _scan():
            result, elapse = ocr_engine(current_panel['path'])
            self.after(0, lambda: self.apply_auto_detect_results(result))
        threading.Thread(target=_scan).start()

    def apply_auto_detect_results(self, results):
        self.lbl_ocr_status.configure(text="OCR: Ready", text_color="gray")
        self.reset_canvas(self.canvas_text, self.text_rects)
        for w in self.ocr_scroll.winfo_children(): w.destroy()
        self.editor_region_map = {}
        current_panel = self.panels_data[self.current_editing_index]
        img = Image.open(current_panel['path'])
        self.display_image_on_canvas(img, self.canvas_text, context="editor")
        if not results: return
        merged_boxes = self.merge_close_boxes(results)
        for box in merged_boxes:
            ix1, ix2 = box['xmin'], box['xmax']
            iy1, iy2 = box['ymin'], box['ymax']
            text = box['text']
            cx1 = (ix1 * self.editor_scale) + self.editor_ox
            cy1 = (iy1 * self.editor_scale) + self.editor_oy
            cx2 = (ix2 * self.editor_scale) + self.editor_ox
            cy2 = (iy2 * self.editor_scale) + self.editor_oy
            rect_id = self.canvas_text.create_rectangle(cx1, cy1, cx2, cy2, outline=THEME_COLOR, width=2)
            self.text_rects.append((rect_id, (cx1, cy1, cx2, cy2)))
            self.add_sidebar_entry(rect_id, text, "Voice 1")

    def run_rapidocr_crop(self, img_path, coords):
        if not OCR_AVAILABLE or ocr_engine is None: return "Library Missing"
        try:
            img = Image.open(img_path)
            crop = img.crop(coords)
            temp_path = os.path.join(self.project_dir, "temp_crop.png")
            crop.save(temp_path)
            res, _ = ocr_engine(temp_path)
            if res: return " ".join([r[1] for r in res])
            return ""
        except: return "Error"

    def add_sidebar_entry(self, canvas_id, text_content, voice_val):
        card = ctk.CTkFrame(self.ocr_scroll, fg_color="#333")
        card.pack(fill="x", pady=5, padx=5)
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", pady=2)
        ctk.CTkLabel(header, text="Speaker:", font=("Archivo", 10)).pack(side="left", padx=5)
        voice_var = ctk.StringVar(value=voice_val)
        menu_values = self.available_voices + ["Add new voice..."]
        def on_voice_change(choice):
            self.check_new_voice(choice, voice_var)
        dropdown = ctk.CTkOptionMenu(header, variable=voice_var, values=menu_values, command=on_voice_change, width=100, height=20)
        dropdown.pack(side="right", padx=5)
        txt_box = ctk.CTkTextbox(card, height=60, font=("Archivo", 12))
        txt_box.pack(fill="x", padx=5, pady=5)
        txt_box.insert("1.0", text_content)
        self.editor_region_map[canvas_id] = {'widget_frame': card, 'text_box': txt_box, 'voice_var': voice_var, 'dropdown': dropdown}

    def check_new_voice(self, choice, var):
        if choice == "Add new voice...":
            new_num = len(self.available_voices) + 1
            new_voice = f"Voice {new_num}"
            self.available_voices.append(new_voice)
            self.voice_model_map[new_voice] = self.formatted_voice_list[0]
            new_values = self.available_voices + ["Add new voice..."]
            for item in self.editor_region_map.values():
                item['dropdown'].configure(values=new_values)
            var.set(new_voice)

    def refresh_text_selector_ui(self):
        for widget in self.scroll_frame.winfo_children(): widget.destroy()
        if not self.panels_data:
            ctk.CTkLabel(self.scroll_frame, text="No panels.").pack()
            return
        self.scroll_frame.update_idletasks()
        for idx, panel in enumerate(self.panels_data):
            self.create_panel_card(idx, panel)

    def create_panel_card(self, idx, panel):
        path = panel['path']
        region_count = len(panel['text_regions'])
        is_swap_source = (self.swap_source_index == idx)
        border_color = THEME_COLOR if is_swap_source else "gray" # Theme match
        border_width = 3 if is_swap_source else 0 
        
        # Main Card Frame
        card = ctk.CTkFrame(self.scroll_frame, width=220, fg_color="#333", border_color=border_color, border_width=border_width)
        card.pack(side="left", padx=10, fill="y")
        
        ctk.CTkLabel(card, text=f"Panel {idx+1}", font=("Archivo", 12, "bold"), width=250).pack(pady=(5,0))
        try:
            img = Image.open(path)
            ratio = 200 / img.height
            pw = int(img.width * ratio)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(pw, 200))
            ctk.CTkLabel(card, image=ctk_img, text="").pack(pady=5, padx=8)
        except: ctk.CTkLabel(card, text="Error").pack(pady=20, padx=8)
        ctk.CTkLabel(card, text=f"Text Boxes: {region_count}", text_color="#D5D9DE" if region_count > 0 else "gray").pack()
        
        # --- FIXED HIGHLIGHT CUTOFF ---
        controls = ctk.CTkFrame(card, fg_color="transparent")
        controls.pack(pady=(10, 15)) 
        
        # --- REFACTORED CARD BUTTONS ---
        if self.swap_source_index is None:
            btn_text, btn_mode, btn_color_override, cmd = "Reorder", "outline", "gray", lambda i=idx: self.toggle_swap_mode(i)
        elif self.swap_source_index == idx:
            btn_text, btn_mode, btn_color_override, cmd = "Cancel", "primary", None, lambda i=idx: self.toggle_swap_mode(i)
        else:
            btn_text, btn_mode, btn_color_override, cmd = "Swap Here", "primary", None, lambda i=idx: self.execute_swap(i)
        
        btn_width = 175 if self.swap_source_index is not None else 80 
        
        # Create Reorder/Swap Button
        # We pass border_color explicitly if needed (for the gray reorder button)
        reorder_btn = self.create_btn(controls, btn_text, cmd, mode=btn_mode, width=btn_width, height=30)
        
        if btn_color_override:
            reorder_btn.configure(border_color=btn_color_override)
            
        reorder_btn.pack(side="left", padx=5)
        
        # Create Edit Button (only if not swapping)
        if self.swap_source_index is None:
            self.create_btn(
                controls, "Edit", lambda i=idx: self.open_text_editor(i), 
                mode="primary", width=80, height=30
            ).pack(side="left", padx=5)

    def toggle_swap_mode(self, index):
        self.swap_source_index = None if self.swap_source_index == index else index
        self.refresh_text_selector_ui()

    def execute_swap(self, target_index):
        if self.swap_source_index is not None:
            src = self.swap_source_index
            self.panels_data[src], self.panels_data[target_index] = self.panels_data[target_index], self.panels_data[src]
            self.swap_source_index = None
            self.refresh_text_selector_ui()

    def open_text_editor(self, index):
        self.current_editing_index = index
        panel = self.panels_data[index]
        self.text_grid_frame.grid_forget()
        self.text_editor_frame.grid(row=0, column=0, sticky="nsew")
        self.nav_bar.pack_forget() 
        self.reset_canvas(self.canvas_text, self.text_rects)
        for w in self.ocr_scroll.winfo_children(): w.destroy()
        self.editor_region_map = {}
        img = Image.open(panel['path'])
        self.after(50, lambda: self.display_editor_load(img, panel['text_regions']))

    def display_editor_load(self, img, saved_regions):
        self.display_image_on_canvas(img, self.canvas_text, context="editor")
        for region_data in saved_regions:
            coords = region_data['coords']
            text = region_data.get('text', "")
            voice = region_data.get('voice', "Voice 1")
            cx1, cy1 = (coords[0] * self.editor_scale) + self.editor_ox, (coords[1] * self.editor_scale) + self.editor_oy
            cx2, cy2 = (coords[2] * self.editor_scale) + self.editor_ox, (coords[3] * self.editor_scale) + self.editor_oy
            rect_id = self.canvas_text.create_rectangle(cx1, cy1, cx2, cy2, outline=THEME_COLOR, width=2, dash=(4, 2))
            self.text_rects.append((rect_id, (cx1, cy1, cx2, cy2)))
            self.add_sidebar_entry(rect_id, text, voice)

    def save_text_regions(self):
        new_regions_data = []
        for rect_id, (cx1, cy1, cx2, cy2) in self.text_rects:
            ix1, iy1 = (cx1 - self.editor_ox) / self.editor_scale, (cy1 - self.editor_oy) / self.editor_scale
            ix2, iy2 = (cx2 - self.editor_ox) / self.editor_scale, (cy2 - self.editor_oy) / self.editor_scale
            widget_data = self.editor_region_map.get(rect_id)
            if widget_data:
                text_val = widget_data['text_box'].get("1.0", "end-1c")
                voice_val = widget_data['voice_var'].get()
            else:
                text_val = ""; voice_val = "Voice 1"
            new_regions_data.append({'coords': (ix1, iy1, ix2, iy2), 'text': text_val, 'voice': voice_val})
        self.panels_data[self.current_editing_index]['text_regions'] = new_regions_data
        self.text_editor_frame.grid_forget()
        self.text_grid_frame.grid(row=0, column=0, sticky="nsew")
        self.nav_bar.pack(fill="x", side="bottom", padx=20, pady=20) 
        self.refresh_text_selector_ui()

    def setup_animator_ui(self, parent):
        parent.grid_columnconfigure(0, weight=3) 
        parent.grid_columnconfigure(1, weight=2) 
        parent.grid_rowconfigure(0, weight=1)

        self.script_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.script_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        ctk.CTkLabel(self.script_frame, text="Final Script Preview", font=("Archivo", 20, "bold")).pack(pady=10, anchor="w")
        self.script_scroll = ctk.CTkScrollableFrame(self.script_frame, label_text="Dialogue Lines")
        self.script_scroll.pack(fill="both", expand=True, padx=5, pady=5)

        self.settings_frame = ctk.CTkFrame(parent, fg_color="#333", corner_radius=10)
        self.settings_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        ctk.CTkLabel(self.settings_frame, text="Generation Settings", font=("Archivo", 20, "bold")).pack(pady=20)

        ctk.CTkLabel(self.settings_frame, text="Animation Style:", font=("Archivo", 14)).pack(anchor="w", padx=20, pady=(10, 5))
        self.anim_style_var = ctk.StringVar(value="Voiceover")
        self.anim_style_menu = ctk.CTkOptionMenu(self.settings_frame, variable=self.anim_style_var, values=["Voiceover", "Animated"], command=self.toggle_veo_input)
        self.anim_style_menu.pack(fill="x", padx=20, pady=5)

        self.veo_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        ctk.CTkLabel(self.veo_frame, text="Veo 3 Prompt / Instructions:", font=("Archivo", 14)).pack(anchor="w", pady=(15, 5))
        self.veo_input = ctk.CTkTextbox(self.veo_frame, height=100)
        self.veo_input.pack(fill="x", pady=5)
        self.veo_input.insert("1.0", "Describe the visual style, camera movement, or specific animation details...")

        self.timing_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.timing_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(self.timing_frame, text="Pause Duration (Between Panels):").pack(anchor="w")
        self.entry_panel_pause = ctk.CTkEntry(self.timing_frame)
        self.entry_panel_pause.pack(fill="x", pady=(0, 10))
        self.entry_panel_pause.insert(0, "0.5")

        ctk.CTkLabel(self.timing_frame, text="Pause Duration (Between Speech):").pack(anchor="w")
        self.entry_speech_pause = ctk.CTkEntry(self.timing_frame)
        self.entry_speech_pause.pack(fill="x", pady=(0, 10))
        self.entry_speech_pause.insert(0, "0.25")

        ctk.CTkLabel(self.settings_frame, text="Voice Models (Kokoro):", font=("Archivo", 14, "bold")).pack(anchor="w", padx=20, pady=(20, 5))
        self.voice_settings_scroll = ctk.CTkScrollableFrame(self.settings_frame, height=200, label_text="Configure Voices")
        self.voice_settings_scroll.pack(fill="x", padx=20, pady=5)

        self.status_container = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.status_container.pack(side="bottom", fill="x", padx=20, pady=20)
        
        self.gen_status_label = ctk.CTkLabel(self.status_container, text="Ready to generate.", text_color="gray")
        self.gen_status_label.pack(pady=(0, 5))
        
        self.progress_bar = ctk.CTkProgressBar(self.status_container, orientation="horizontal", mode="determinate")
        self.progress_bar.set(0)

    def toggle_veo_input(self, choice):
        if choice == "Animated":
            self.veo_frame.pack(fill="x", padx=20, pady=5)
        else:
            self.veo_frame.pack_forget()

    def refresh_animator_ui(self):
        for w in self.script_scroll.winfo_children(): w.destroy()
        for p_idx, panel in enumerate(self.panels_data):
            regions = panel.get('text_regions', [])
            if not regions: continue
            ctk.CTkLabel(self.script_scroll, text=f"Panel {p_idx+1}", font=("Archivo", 14, "bold"), anchor="w", text_color=THEME_COLOR).pack(fill="x", pady=(15, 5))
            for r_idx, region in enumerate(regions):
                row = ctk.CTkFrame(self.script_scroll, fg_color="#333")
                row.pack(fill="x", pady=4, padx=5)
                ctk.CTkLabel(row, text=f"{region.get('voice')}:", width=80, font=("Archivo", 12, "bold")).pack(side="left", padx=10, anchor="n", pady=5)
                ctk.CTkLabel(row, text=region.get('text'), wraplength=400, justify="left").pack(side="left", fill="x", padx=10, pady=5)

        for w in self.voice_settings_scroll.winfo_children(): w.destroy()
        for voice in self.available_voices:
            row = ctk.CTkFrame(self.voice_settings_scroll, fg_color="transparent")
            row.pack(fill="x", pady=5)
            ctk.CTkLabel(row, text=voice, width=60, anchor="w").pack(side="left")
            
            current_val = self.voice_model_map.get(voice, self.formatted_voice_list[0])
            model_var = ctk.StringVar(value=current_val)
            
            def update_map(choice, v=voice): self.voice_model_map[v] = choice
            
            dropdown = ctk.CTkOptionMenu(row, variable=model_var, values=self.formatted_voice_list, command=update_map, width=200)
            dropdown.pack(side="left", padx=10)
            
            # --- REFACTORED TEST BUTTON ---
            # Used 'outline' style for test buttons
            test_btn = self.create_btn(
                row, "Test", None, mode="outline", width=50, height=30
            )
            test_btn.configure(command=lambda v=voice, b=test_btn: self.test_voice(v, b))
            test_btn.pack(side="right", padx=BUTTON_PADDING)

    def test_voice(self, voice_name, btn_widget):
        if not KOKORO_AVAILABLE: messagebox.showerror("Error", "Kokoro not loaded.\n(Check console)"); return
        if not self.kokoro: messagebox.showerror("Error", "Kokoro model failed to initialize.\nCheck 'models' folder."); return
        
        display_name = self.voice_model_map.get(voice_name)
        style = self.display_to_id.get(display_name, "af_bella")
        
        btn_widget.configure(text="⏳", state="disabled")
        
        threading.Thread(target=self._run_test_gen, args=(style, btn_widget)).start()

    def _run_test_gen(self, style, btn_widget):
        temp_file = os.path.join(self.test_dir, "test_voice.wav")
        
        try:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
            try:
                pygame.mixer.music.unload()
            except AttributeError:
                pass
            
            time.sleep(0.1) 

            if style == "gtts_robot":
                 tts = gTTS(text="This is a test of the requested voice.", lang='en', slow=False)
                 tts.save(temp_file)
            else:
                 self.generate_audio_clip_kokoro("This is a test of the requested voice.", style, temp_file)
            
            pygame.mixer.music.load(temp_file)
            pygame.mixer.music.play()
            
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
                
        except Exception as e:
            print(f"Test Voice Error: {e}")
            try:
                unique_name = f"test_{uuid.uuid4().hex[:6]}.wav"
                alt_path = os.path.join(self.test_dir, unique_name)
                print(f"Retrying with unique filename: {unique_name}")
                if style == "gtts_robot":
                    tts = gTTS(text="This is a test of the requested voice.", lang='en', slow=False)
                    tts.save(alt_path)
                else:
                    self.generate_audio_clip_kokoro("This is a test of the requested voice.", style, alt_path)
                pygame.mixer.music.load(alt_path)
                pygame.mixer.music.play()
            except Exception as e2:
                print(f"Retry failed: {e2}")

        finally:
            self.after(0, lambda: btn_widget.configure(text="Test", state="normal"))

    def run_generation(self):
        if not VIDEO_LIB_AVAILABLE: messagebox.showerror("Error", "Install moviepy"); return
        self.gen_status_label.configure(text="Generating...", text_color="orange")
        self.progress_bar.pack(fill="x", pady=5)
        self.progress_bar.set(0) 
        self.btn_next.configure(state="disabled")
        threading.Thread(target=self._video_worker).start()

    def _video_worker(self):
        try:
            clips = []
            audio_path = self.audio_dir
            
            try:
                panel_pause = float(self.entry_panel_pause.get())
            except: panel_pause = 0.5
            
            try:
                speech_pause = float(self.entry_speech_pause.get())
            except: speech_pause = 0.25
            
            def get_safe_clip(path, duration):
                pil_img = Image.open(path)
                
                if pil_img.mode in ('RGBA', 'LA') or (pil_img.mode == 'P' and 'transparency' in pil_img.info):
                    pil_img = pil_img.convert('RGBA')
                    bg = Image.new('RGB', pil_img.size, (255, 255, 255))
                    bg.paste(pil_img, (0, 0), pil_img)
                    pil_img = bg
                else:
                    pil_img = pil_img.convert('RGB')

                w, h = pil_img.size
                new_w = w if w % 2 == 0 else w - 1
                new_h = h if h % 2 == 0 else h - 1
                if new_w != w or new_h != h:
                    pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                return ImageClip(np.array(pil_img)).set_duration(duration)
            
            total_panels = len(self.panels_data)

            for i, p in enumerate(self.panels_data):
                progress = (i) / total_panels
                self.after(0, lambda v=progress: self.progress_bar.set(v))
                
                regions = p['text_regions']
                img_path = p['path']
                
                if not regions:
                    clips.append(get_safe_clip(img_path, 2.0 + panel_pause))
                    continue

                for j, r in enumerate(regions):
                    text = r['text']; voice = r['voice']
                    
                    display_name = self.voice_model_map.get(voice)
                    style = self.display_to_id.get(display_name, "af_bella")
                    
                    aud_path = os.path.join(audio_path, f"p{i}_r{j}.wav")
                    success = False
                    
                    if os.path.exists(aud_path):
                        try: os.remove(aud_path)
                        except: pass
                    
                    if style == "gtts_robot":
                        try:
                            tts = gTTS(text=text, lang='en')
                            tts.save(aud_path)
                            success = True
                        except Exception as e:
                            print(f"Robot Voice Error: {e}")
                    elif KOKORO_AVAILABLE:
                        try:
                            self.generate_audio_clip_kokoro(text, style, aud_path)
                            success = True
                        except Exception as e:
                            print(f"Kokoro gen failed: {e}")
                    
                    if not success and style != "gtts_robot":
                        try:
                            tts = gTTS(text=text, lang='en')
                            tts.save(aud_path)
                            success = True
                        except Exception as e:
                            print(f"gTTS failed: {e}")

                    if success:
                        try:
                            ac = AudioFileClip(aud_path)
                            
                            is_last_bubble_in_panel = (j == len(regions) - 1)
                            extra_pause = panel_pause if is_last_bubble_in_panel else speech_pause
                            
                            total_duration = ac.duration + 0.1 + extra_pause
                            
                            ic = get_safe_clip(img_path, total_duration).set_audio(ac)
                            clips.append(ic)
                        except Exception as e:
                             print(f"Error creating clip: {e}")

            self.after(0, lambda: self.progress_bar.set(1.0))

            if not clips:
                self.after(0, lambda: messagebox.showwarning("Empty", "No clips generated."))
                return

            final = concatenate_videoclips(clips, method="compose")
            out = os.path.join(self.project_dir, "comic_voiceover.mp4")
            
            final.write_videofile(
                out, 
                fps=24, 
                codec="libx264", 
                audio_codec="aac",
                audio_bitrate="192k",
                ffmpeg_params=["-pix_fmt", "yuv420p"]
            )
            
            self.after(0, lambda: messagebox.showinfo("Done", f"Saved to {out}"))
            self.after(0, lambda: self.btn_next.configure(state="normal"))
            self.after(0, lambda: self.gen_status_label.configure(text="Done", text_color="green"))
            try: os.startfile(os.path.dirname(out))
            except: pass
            
        except Exception as e:
            print(f"Worker Error: {e}")
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.after(0, lambda: self.btn_next.configure(state="normal"))

if __name__ == "__main__":
    app = MovicStudio()
    app.mainloop()