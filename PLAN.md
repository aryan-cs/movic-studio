# Project: Comic-to-Life (Hybrid Generative Engine)

## 1. Project Overview
**Goal:** Create a Python-based application that brings static comics to life by leveraging Google's image to video Veo model.

**Core Features:**
* **Intelligent Parsing:** Uses `Gemini 1.5 Flash` (Vision) to extract panel layouts and speech bubble coordinates.
* **Generative Animation:** Uses `Gemini Veo` (via API) to generate short videos to blend each panel together, resulting in on longer, animated video comic.  
* **Audio Synthesis:** Uses `Edge-TTS` to generate distinct voices for characters.
* **Hybrid Compositing:** Uses `MoviePy` to overlay the original, high-resolution speech bubbles on top of the generated video, masking any "AI blurring" of the text.

---

## 2. System Architecture

The pipeline consists of four distinct phases.

### Phase 1: The "Eyes" (Vision & Extraction)
* **Input:** Raw Image File.
* **Engine:** Google Gemini 1.5 Flash (Vision).
* **Responsibility:**
    * Detect individual panels.
    * **CRITICAL:** Detect speech bubble bounding boxes (we need these to "save" the text later).
    * Extract text via OCR for the audio script.
* **Output:** A JSON "Script" containing coordinates and text.

### Phase 2: The "Dream" (Generative Animation)
* **Input:** Cropped Panel Images (from Phase 1).
* **Engine:** Google Gemini Veo (`veo-3.1-generate-preview` or equivalent).
* **Responsibility:**
    * Take the static panel and prompt it: *"Cinematic shot, stick figures talking and gesturing, stable line art."*
    * Generate a short video clip of the panel.
    * *Note:* The text in this video will likely be garbled/blurry. This is expected.
* **Output:** A video file (`.mp4`) for each panel.

### Phase 3: The "Voice" (Audio Synthesis)
* **Input:** JSON Script text.
* **Engine:** `edge-tts` (Neural).
* **Responsibility:**
    * Generate `.mp3` files for every speech bubble.
    * Calculate durations to match the video speed.

### Phase 4: The "Director" (Compositing & Fixing)
* **Input:** Veo Videos (Phase 2) + Original Bubble Crops (Phase 1) + Audio (Phase 3).
* **Engine:** `moviepy`.
* **Responsibility:**
    * **The Masking Trick:** Place the generated Veo video as the background.
    * **The Overlay:** Cut out the *original, sharp* speech bubble from the source image and paste it exactly on top of the garbled video text.
    * **Sync:** Pop the bubbles in when the audio plays.
    * **Render:** Export final `.mp4`.

---

## 3. Technology Stack

* **Language:** Python 3.10+
* **Vision/Video API:** `google-generativeai` (Accessing `gemini-1.5-flash` for vision and `veo-3.1-generate-preview` for video).
* **Audio:** `edge-tts` (Free neural voices).
* **Video Editing:** `moviepy` (Wrapper around FFMPEG).
* **UI:** `gradio`.

---

## 5. Implementation Details

### Phase 1: Vision Prompting

We need to ask Gemini to not only find the bubbles but ensuring the bounding boxes are tight so we can crop them cleanly.

* **Prompt:** "Identify all panels. For each panel, identify all speech bubbles with bounding boxes. Return JSON."

### Phase 2: Veo Prompting Strategy

Veo can be chaotic. We need strict prompts to keep the style consistent. For reference, see the [docs](https://ai.google.dev/gemini-api/docs/video?example=dialogue#generate-from-images).

### Phase 4: The Overlay Logic (The "Fix")

This is the most complex code logic.

1. **Coordinate Mapping:** Transform the normalized (0-1000) coordinates from Gemini into pixel coordinates for the *cropped panel*.
2. **Cropping:** Use Pillow (PIL) to crop the bubble from the *original static image*.
3. **Layering:** In MoviePy, create a `CompositeVideoClip`.
* Layer 0: `VideoFileClip("veo_output.mp4")`
* Layer 1: `ImageClip("bubble_crop.png").set_position((x,y))`
* *Result:* The character moves behind the bubble, but the text remains perfectly sharp.



---

## 6. Project Structure

```text
comic-to-life/
├── main.py              # Entry point (Gradio UI)
├── config.py            # API Keys
├── plan.md              # This file
├── src/
│   ├── vision.py        # Gemini 1.5 Flash (Coords extraction)
│   ├── generation.py    # Gemini Veo (Video generation)
│   ├── audio.py         # edge-tts
│   └── compositor.py    # MoviePy (The overlay logic)
└── out/                 # Results go here

```

## 7. Development Roadmap

1. **Veo Access Check:** Write a script `test_veo.py` to confirm your API key can trigger `veo-3.1-generate-preview`.
2. **Vision Pipeline:** Build `vision.py` to reliably get coordinates.
3. **The "Stack" Test:** Manually generate one Veo clip, manually crop one bubble, and use `compositor.py` to stack them. Verify the "Masking Trick" looks good.
4. **Automation:** Connect the pipes so the JSON script drives the whole process automatically.
5. **UI:** Add Gradio frontend.
