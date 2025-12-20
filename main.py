import gradio as gr

def process_comic(image):
    return image

with gr.Blocks(title="Movic Studio") as demo:
    gr.Markdown("# Movic Studio", elem_id="title")
    
    with gr.Row(elem_id="centered-row"):
        with gr.Column(scale=2):
            image_input = gr.Image(
                type="filepath", 
                label="Upload Image", 
                sources=["upload", "clipboard"], 
                width=600, 
                height=600
            )
            
        with gr.Column(scale=1):
            gr.Button("Setting 1", interactive=False)
            gr.Button("Setting 2", interactive=False)
            gr.Button("Setting 3", interactive=False)
            gr.Button("Setting 4", interactive=False)
            gr.Button("Setting 5", interactive=False)
            gr.Button("Setting 6", interactive=False)
            gr.Button("Setting 7", interactive=False)
            gr.Button("Setting 8", interactive=False)
            gr.Button("Setting 9", interactive=False)
            gr.Button("Setting 10", interactive=False)
            animate_btn = gr.Button("Animate", variant="primary")

        with gr.Column(scale=2):
            output_image = gr.Image(label="Output", width=600, height=600)

    animate_btn.click(
        fn=process_comic,
        inputs=image_input,
        outputs=output_image
    )

if __name__ == "__main__":
    demo.launch(css="styles.css")