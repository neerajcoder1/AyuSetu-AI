import gradio as gr
from ayusetu.ai.voice.asr.transcriber import transcribe, reset_backend
import tempfile
import os

# Ensure the backend is initialized
reset_backend()

def process_audio(audio_filepath):
    if not audio_filepath:
        return "No audio provided.", "unknown", 0.0
    
    try:
        # Transcribe directly
        out = transcribe(audio_filepath)
        return out.text, out.language, round(out.confidence, 4)
    except Exception as e:
        return f"Error during transcription: {str(e)}", "unknown", 0.0

with gr.Blocks(title="AyuSetu Live ASR", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        """
        # 🎙️ AyuSetu Live ASR Testing
        Test the `shunyalabs/zero-stt-hinglish` model live. 
        Click **Record from Microphone**, speak in Hindi, English, or Hinglish, and wait for the transcription!
        """
    )
    
    with gr.Row():
        with gr.Column():
            audio_input = gr.Audio(sources=["microphone", "upload"], type="filepath", label="Input Audio")
            submit_btn = gr.Button("Transcribe", variant="primary")
            
        with gr.Column():
            text_output = gr.Textbox(label="Transcription (Text)")
            lang_output = gr.Textbox(label="Detected Language")
            conf_output = gr.Number(label="Confidence Score (0.0 to 1.0)")
            
    submit_btn.click(
        fn=process_audio,
        inputs=audio_input,
        outputs=[text_output, lang_output, conf_output]
    )

if __name__ == "__main__":
    print("Launching AyuSetu Live ASR on http://127.0.0.1:7860 ...")
    demo.launch(server_name="127.0.0.1", server_port=7860, show_api=False)
