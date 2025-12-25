import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class ImageCutterApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Image Segment Cutter")
        self.geometry("1000x700")

        # Data State
        self.original_image = None  # The full-res PIL image
        self.display_image = None   # The resized PIL image for display
        self.tk_image = None        # The ImageTk object for the canvas
        self.scale_factor = 1.0
        self.rectangles = []        # Stores (rect_id, coords)
        self.start_x = None
        self.start_y = None
        self.current_rect = None

        # GUI Layout configuration
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Sidebar ---
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.logo_label = ctk.CTkLabel(self.sidebar, text="Panel Cutter", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.pack(padx=20, pady=(20, 10))

        self.btn_load = ctk.CTkButton(self.sidebar, text="Load Image", command=self.load_image)
        self.btn_load.pack(padx=20, pady=10)

        self.btn_undo = ctk.CTkButton(self.sidebar, text="Undo Last Box", command=self.undo_last_selection, fg_color="transparent", border_width=2)
        self.btn_undo.pack(padx=20, pady=10)

        self.btn_save = ctk.CTkButton(self.sidebar, text="Save Segments", command=self.save_segments, fg_color="green")
        self.btn_save.pack(padx=20, pady=(30, 10))
        
        self.status_label = ctk.CTkLabel(self.sidebar, text="No image loaded", text_color="gray")
        self.status_label.pack(side="bottom", pady=20)

        # --- Main Area (Canvas) ---
        # We use a standard tk.Canvas because drawing distinct shapes is easier than on CTk widgets
        self.canvas_frame = ctk.CTkFrame(self)
        self.canvas_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="#2b2b2b", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Bind Mouse Events
        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)

    def load_image(self):
        file_path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.webp")])
        if not file_path:
            return

        # Load and keep original reference
        self.original_image = Image.open(file_path)
        self.reset_canvas()
        self.display_image_on_canvas()
        self.status_label.configure(text="Draw boxes to cut")

    def reset_canvas(self):
        self.canvas.delete("all")
        self.rectangles.clear()

    def display_image_on_canvas(self):
        # Calculate scaling to fit the canvas while maintaining aspect ratio
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        img_w, img_h = self.original_image.size
        
        # Calculate scale factor
        ratio = min(canvas_width / img_w, canvas_height / img_h)
        new_w = int(img_w * ratio)
        new_h = int(img_h * ratio)
        
        self.scale_factor = ratio

        # Resize for display only
        self.display_image = self.original_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(self.display_image)

        # Draw image centered
        self.canvas.create_image(canvas_width//2, canvas_height//2, anchor="center", image=self.tk_image)

    def on_button_press(self, event):
        if not self.original_image:
            return
        # Save start coordinates
        self.start_x = self.canvas.canvasx(event.x)
        self.start_y = self.canvas.canvasy(event.y)

        # Create a rectangle (initially size 0)
        self.current_rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y, 
            outline="cyan", width=2, dash=(4, 2)
        )

    def on_move_press(self, event):
        if not self.current_rect:
            return
        cur_x = self.canvas.canvasx(event.x)
        cur_y = self.canvas.canvasy(event.y)
        
        # Update rectangle size as mouse drags
        self.canvas.coords(self.current_rect, self.start_x, self.start_y, cur_x, cur_y)

    def on_button_release(self, event):
        if not self.current_rect:
            return
        
        # Finalize coordinates
        cur_x = self.canvas.canvasx(event.x)
        cur_y = self.canvas.canvasy(event.y)
        
        # Normalize coords (handle dragging left/up)
        x1, x2 = sorted([self.start_x, cur_x])
        y1, y2 = sorted([self.start_y, cur_y])

        # Ignore tiny accidental clicks
        if (x2 - x1) < 5 or (y2 - y1) < 5:
            self.canvas.delete(self.current_rect)
        else:
            self.rectangles.append((self.current_rect, (x1, y1, x2, y2)))
        
        self.current_rect = None

    def undo_last_selection(self):
        if self.rectangles:
            rect_id, _ = self.rectangles.pop()
            self.canvas.delete(rect_id)

    def save_segments(self):
        if not self.rectangles:
            return
        
        # Ask where to save
        save_dir = filedialog.askdirectory(title="Select Output Folder")
        if not save_dir:
            return

        # Get Canvas offset (because image is centered)
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        img_w_disp, img_h_disp = self.display_image.size
        
        offset_x = (canvas_width - img_w_disp) // 2
        offset_y = (canvas_height - img_h_disp) // 2

        count = 0
        for _, (x1, y1, x2, y2) in self.rectangles:
            # 1. Adjust for canvas offset (remove the gray padding area)
            rel_x1 = x1 - offset_x
            rel_y1 = y1 - offset_y
            rel_x2 = x2 - offset_x
            rel_y2 = y2 - offset_y

            # 2. Map back to original image coordinates using scale factor
            orig_x1 = int(rel_x1 / self.scale_factor)
            orig_y1 = int(rel_y1 / self.scale_factor)
            orig_x2 = int(rel_x2 / self.scale_factor)
            orig_y2 = int(rel_y2 / self.scale_factor)

            # 3. Clamp coordinates to image bounds (prevent crashing if box goes outside)
            orig_x1 = max(0, orig_x1)
            orig_y1 = max(0, orig_y1)
            orig_x2 = min(self.original_image.width, orig_x2)
            orig_y2 = min(self.original_image.height, orig_y2)

            # 4. Crop and Save
            try:
                crop = self.original_image.crop((orig_x1, orig_y1, orig_x2, orig_y2))
                filename = f"segment_{count + 1}.png"
                crop.save(os.path.join(save_dir, filename))
                count += 1
            except Exception as e:
                print(f"Error saving crop {count}: {e}")

        self.status_label.configure(text=f"Saved {count} segments!")
        tk.messagebox.showinfo("Success", f"Successfully saved {count} image segments.")

if __name__ == "__main__":
    app = ImageCutterApp()
    app.mainloop()