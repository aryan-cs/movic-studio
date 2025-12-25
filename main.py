import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os
import shutil
import uuid

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class MovicStudio(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Movic Studio")
        self.geometry("1200x850")

        self.project_dir = os.path.join(os.getcwd(), "movic_project")
        self.ensure_project_dir()
        
        self.panels_data = [] 
        self.current_step = 1

        self.original_image = None
        self.CANVAS_PAD = 50 

        self.cutter_scale = 1.0
        self.cutter_ox = 0
        self.cutter_oy = 0
        
        self.editor_scale = 1.0
        self.editor_ox = 0
        self.editor_oy = 0

        self.rectangles = [] 
        self.start_x = None
        self.start_y = None
        self.current_rect = None

        self.current_editing_index = -1
        self.swap_source_index = None 

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        self.nav_bar = ctk.CTkFrame(self, height=60, fg_color="transparent")
        self.nav_bar.pack(fill="x", side="bottom", padx=20, pady=20)

        self.btn_back = ctk.CTkButton(self.nav_bar, text="< Back", command=self.go_back, width=120, fg_color="gray")
        self.btn_back.pack(side="left")

        self.btn_next = ctk.CTkButton(self.nav_bar, text="Next >", command=self.go_next, width=120, fg_color="green")
        self.btn_next.pack(side="right")

        self.frames = {}
        
        self.frames[1] = ctk.CTkFrame(self.container, fg_color="transparent")
        self.setup_panel_cutter_ui(self.frames[1])

        self.frames[2] = ctk.CTkFrame(self.container, fg_color="transparent")
        self.setup_text_selector_ui(self.frames[2])

        self.frames[3] = ctk.CTkFrame(self.container, fg_color="transparent")
        self.setup_animator_ui(self.frames[3])

        self.show_step(1)

        self.bind("<Control-z>", lambda event: self.handle_undo())

    def ensure_project_dir(self):
        if os.path.exists(self.project_dir):
            try:
                shutil.rmtree(self.project_dir)
            except:
                pass
        os.makedirs(self.project_dir, exist_ok=True)

    def show_step(self, step_num):
        for f in self.frames.values():
            f.pack_forget()
        
        self.frames[step_num].pack(fill="both", expand=True)
        self.current_step = step_num
        
        if step_num == 1:
            self.btn_back.configure(state="disabled", fg_color="#333")
            self.btn_next.configure(text="Next >")
        else:
            self.btn_back.configure(state="normal", fg_color="gray")
            
        if step_num == 3:
            self.btn_next.configure(text="Finish")
        else:
            self.btn_next.configure(text="Next >")

    def go_next(self):
        if self.current_step == 1:
            success = self.save_panels()
            if success:
                self.show_step(2)
        elif self.current_step == 2:
            self.show_step(3)
        elif self.current_step == 3:
            messagebox.showinfo("Done", "Project Finished! (Placeholder)")

    def go_back(self):
        if self.current_step > 1:
            self.show_step(self.current_step - 1)

    def handle_undo(self):
        if self.current_step == 1:
            self.undo_selection(self.canvas_cutter, self.rectangles)
        elif self.current_step == 2 and self.text_editor_frame.winfo_viewable():
            self.undo_selection(self.canvas_text, self.text_rects)

    def undo_selection(self, canvas, rect_list):
        if rect_list:
            item = rect_list.pop()
            rect_id = item[0] 
            canvas.delete(rect_id)

    def setup_panel_cutter_ui(self, parent):
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        self.pc_sidebar = ctk.CTkFrame(parent, width=200, corner_radius=0)
        self.pc_sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        ctk.CTkLabel(self.pc_sidebar, text="Step 1: Panelize", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 10))
        ctk.CTkButton(self.pc_sidebar, text="Load Image", command=self.load_image).pack(padx=20, pady=10)
        ctk.CTkButton(self.pc_sidebar, text="Undo (Ctrl+Z)", command=lambda: self.undo_selection(self.canvas_cutter, self.rectangles), fg_color="transparent", border_width=2).pack(padx=20, pady=10)
        

        self.status_label = ctk.CTkLabel(self.pc_sidebar, text="No image loaded", text_color="gray")
        self.status_label.pack(side="bottom", pady=20)

        self.canvas_frame = ctk.CTkFrame(parent)
        self.canvas_frame.grid(row=0, column=1, sticky="nsew")
        self.canvas_cutter = tk.Canvas(self.canvas_frame, bg="#2b2b2b", highlightthickness=0)
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
            self.cutter_scale = scale
            self.cutter_ox = offset_x
            self.cutter_oy = offset_y
        else:
            self.editor_scale = scale
            self.editor_ox = offset_x
            self.editor_oy = offset_y

        canvas.create_rectangle(0, 0, cw, ch, fill="#2b2b2b", outline="") 
        canvas.create_image(offset_x, offset_y, anchor="nw", image=tk_image)
        canvas.create_rectangle(offset_x, offset_y, offset_x + new_w, offset_y + new_h, outline="#444", width=1)

    def on_press(self, event, canvas):
        self.start_x = canvas.canvasx(event.x)
        self.start_y = canvas.canvasy(event.y)
        self.current_rect = canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline="cyan", width=2, dash=(4, 2))

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
        """Processes panels. Returns True if successful, False if failed."""
        if not self.rectangles:
            messagebox.showwarning("Empty", "Please cut at least one segment.")
            return False

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
                save_path = os.path.join(self.project_dir, filename)
                crop.save(save_path)
                
                previous_entry = existing_data_map.get(unique_id)
                
                panel_entry = {
                    "id": unique_id,
                    "path": save_path,
                    "text_regions": previous_entry['text_regions'] if previous_entry else []
                }
                new_panels_data.append(panel_entry)
                
            except Exception as e:
                print(f"Error saving {i}: {e}")

        self.panels_data = new_panels_data
        
        self.status_label.configure(text=f"Saved {len(self.panels_data)} panels!")
        self.refresh_text_selector_ui()
        return True

    def setup_text_selector_ui(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        self.text_grid_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.text_grid_frame.grid(row=0, column=0, sticky="nsew")
        self.text_grid_frame.grid_columnconfigure(0, weight=1)
        self.text_grid_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self.text_grid_frame, text="Step 2: Reorder & Select Text", font=("Arial", 18, "bold")).grid(row=0, column=0, pady=10)
        
        self.scroll_frame = ctk.CTkScrollableFrame(self.text_grid_frame, orientation="horizontal", height=320, label_text="Panels")
        self.scroll_frame.grid(row=1, column=0, sticky="new", padx=20, pady=10)
        

        self.text_editor_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.text_editor_frame.grid_columnconfigure(1, weight=1)
        self.text_editor_frame.grid_rowconfigure(0, weight=1)

        self.te_sidebar = ctk.CTkFrame(self.text_editor_frame, width=200, corner_radius=0)
        self.te_sidebar.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(self.te_sidebar, text="Edit Panel", font=("Arial", 16, "bold")).pack(pady=20)
        ctk.CTkButton(self.te_sidebar, text="Undo (Ctrl+Z)", command=lambda: self.undo_selection(self.canvas_text, self.text_rects), fg_color="transparent", border_width=2).pack(pady=10)
        
        ctk.CTkButton(self.te_sidebar, text="Save & Back", command=self.save_text_regions, fg_color="green").pack(pady=20)

        self.canvas_text = tk.Canvas(self.text_editor_frame, bg="#2b2b2b", highlightthickness=0)
        self.canvas_text.grid(row=0, column=1, sticky="nsew")
        
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
        self.current_rect = None

    def refresh_text_selector_ui(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        if not self.panels_data:
            ctk.CTkLabel(self.scroll_frame, text="No panels.").pack()
            return

        for idx, panel in enumerate(self.panels_data):
            self.create_panel_card(idx, panel)

    def create_panel_card(self, idx, panel):
        path = panel['path']
        has_text = len(panel['text_regions']) > 0
        
        is_swap_source = (self.swap_source_index == idx)
        
        border_color = "orange" 
        border_width = 3 if is_swap_source else 0 
        
        card = ctk.CTkFrame(self.scroll_frame, width=220, border_color=border_color, border_width=border_width)
        card.pack(side="left", padx=10, fill="y")
        
        inner_pad = 8 

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", pady=(inner_pad, 0), padx=inner_pad) 
        ctk.CTkLabel(header, text=f"Panel {idx+1}", font=("Arial", 12, "bold")).pack()

        try:
            img = Image.open(path)
            ratio = 200 / img.height
            pw = int(img.width * ratio)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(pw, 200))
            
            ctk.CTkLabel(card, image=ctk_img, text="").pack(pady=5, padx=inner_pad)
        except:
            ctk.CTkLabel(card, text="Error").pack(pady=20, padx=inner_pad)

        status_text = f"Text Regions: {len(panel['text_regions'])}"
        status_color = "green" if has_text else "gray"
        ctk.CTkLabel(card, text=status_text, text_color=status_color, font=("Arial", 10)).pack(padx=inner_pad)

        controls = ctk.CTkFrame(card, fg_color="transparent")
        controls.pack(pady=(10, inner_pad), padx=inner_pad) 

        if self.swap_source_index is None:
            btn_text = "Reorder"
            btn_fg = "gray"
            cmd = lambda i=idx: self.toggle_swap_mode(i)
        elif self.swap_source_index == idx:
            btn_text = "Cancel"
            btn_fg = "orange"
            cmd = lambda i=idx: self.toggle_swap_mode(i)
        else:
            btn_text = "Swap Here" 
            btn_fg = "#1f6aa5" 
            cmd = lambda i=idx: self.execute_swap(i)

        ctk.CTkButton(controls, text=btn_text, fg_color=btn_fg, width=90, command=cmd).pack(side="left", padx=2)
        ctk.CTkButton(controls, text="Select Text", width=90, command=lambda i=idx: self.open_text_editor(i)).pack(side="left", padx=2)

    def toggle_swap_mode(self, index):
        if self.swap_source_index == index:
            self.swap_source_index = None 
        else:
            self.swap_source_index = index 
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
        
        self.btn_next.configure(state="disabled")
        self.btn_back.configure(state="disabled")

        self.reset_canvas(self.canvas_text, self.text_rects)
        img = Image.open(panel['path'])
        self.after(50, lambda: self.display_editor_image_and_rects(img, panel['text_regions']))

    def display_editor_image_and_rects(self, img, saved_regions):
        self.display_image_on_canvas(img, self.canvas_text, context="editor")
        
        for (rx1, ry1, rx2, ry2) in saved_regions:
            cx1 = (rx1 * self.editor_scale) + self.editor_ox
            cy1 = (ry1 * self.editor_scale) + self.editor_oy
            cx2 = (rx2 * self.editor_scale) + self.editor_ox
            cy2 = (ry2 * self.editor_scale) + self.editor_oy
            
            rect_id = self.canvas_text.create_rectangle(cx1, cy1, cx2, cy2, outline="cyan", width=2, dash=(4, 2))
            self.text_rects.append((rect_id, (cx1, cy1, cx2, cy2)))

    def save_text_regions(self):
        regions = []
        for _, (cx1, cy1, cx2, cy2) in self.text_rects:
            ix1 = (cx1 - self.editor_ox) / self.editor_scale
            iy1 = (cy1 - self.editor_oy) / self.editor_scale
            ix2 = (cx2 - self.editor_ox) / self.editor_scale
            iy2 = (cy2 - self.editor_oy) / self.editor_scale
            regions.append((ix1, iy1, ix2, iy2)) 
            
        self.panels_data[self.current_editing_index]['text_regions'] = regions
        
        self.text_editor_frame.grid_forget()
        self.text_grid_frame.grid(row=0, column=0, sticky="nsew")
        
        self.btn_next.configure(state="normal")
        self.btn_back.configure(state="normal")
        
        self.refresh_text_selector_ui()

    def setup_animator_ui(self, parent):
        ctk.CTkLabel(parent, text="Step 3: Animation Timeline", font=("Arial", 20)).pack(expand=True)

if __name__ == "__main__":
    app = MovicStudio()
    app.mainloop()