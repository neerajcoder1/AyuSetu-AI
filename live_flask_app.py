import os
import subprocess
from flask import Flask, request, jsonify, render_template_string
import imageio_ffmpeg
from neeraj.asr.transcriber import transcribe, reset_backend

app = Flask(__name__)
print("Pre-loading ASR Model...")
reset_backend()
print("Model loaded.")

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>AyuSetu Live ASR</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; text-align: center; margin-top: 50px; background-color: #f9fafb; color: #111827; }
        .container { max-width: 600px; margin: 0 auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
        h1 { color: #2563eb; margin-bottom: 30px; }
        button { font-size: 18px; padding: 12px 24px; margin: 10px; cursor: pointer; border: none; border-radius: 8px; font-weight: bold; transition: background-color 0.2s; }
        #recordBtn { background-color: #ef4444; color: white; }
        #recordBtn:hover { background-color: #dc2626; }
        #recordBtn:disabled { background-color: #fca5a5; cursor: not-allowed; }
        #stopBtn { background-color: #3b82f6; color: white; }
        #stopBtn:hover { background-color: #2563eb; }
        #stopBtn:disabled { background-color: #93c5fd; cursor: not-allowed; }
        #status { margin-top: 20px; font-weight: 500; color: #4b5563; }
        #result { margin-top: 30px; font-size: 22px; color: #111827; padding: 20px; border: 1px solid #e5e7eb; border-radius: 8px; background-color: #f8fafc; min-height: 80px; text-align: left; }
        .meta { font-size: 14px; color: #6b7280; display: block; margin-top: 15px; border-top: 1px solid #e5e7eb; padding-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎙️ AyuSetu Live ASR</h1>
        <p>Test the `zero-stt-hinglish` code-switching model live!</p>
        
        <button id="recordBtn">🔴 Start Recording</button>
        <button id="stopBtn" disabled>⏹️ Stop & Transcribe</button>
        
        <p id="status">Ready.</p>
        <div id="result">Transcription will appear here...</div>
    </div>

    <script>
        let mediaRecorder;
        let audioChunks = [];

        const recordBtn = document.getElementById('recordBtn');
        const stopBtn = document.getElementById('stopBtn');
        const statusText = document.getElementById('status');
        const resultDiv = document.getElementById('result');

        recordBtn.onclick = async () => {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream);
                mediaRecorder.start();
                audioChunks = [];

                mediaRecorder.addEventListener("dataavailable", event => {
                    audioChunks.push(event.data);
                });

                recordBtn.disabled = true;
                stopBtn.disabled = false;
                statusText.innerText = "Recording... Speak clearly into your microphone.";
                statusText.style.color = "#ef4444";
                resultDiv.innerHTML = "Listening...";
                
                mediaRecorder.addEventListener("stop", async () => {
                    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    const formData = new FormData();
                    formData.append('audio', audioBlob, 'recording.webm');

                    try {
                        const response = await fetch('/transcribe', {
                            method: 'POST',
                            body: formData
                        });
                        const data = await response.json();
                        
                        if (data.error) {
                            resultDiv.innerHTML = `<span style="color:red">Error: ${data.error}</span>`;
                        } else {
                            resultDiv.innerHTML = `
                                <strong>${data.text}</strong>
                                <span class="meta">
                                    🌐 Language: <strong>${data.language}</strong> &nbsp;|&nbsp; 
                                    📊 Confidence: <strong>${(data.confidence * 100).toFixed(1)}%</strong>
                                </span>
                            `;
                        }
                    } catch (e) {
                        resultDiv.innerHTML = `<span style="color:red">Network Error: ${e}</span>`;
                    }
                    statusText.innerText = "Processing complete.";
                    statusText.style.color = "#10b981";
                });
            } catch (err) {
                alert("Microphone access denied or not found!");
            }
        };

        stopBtn.onclick = () => {
            mediaRecorder.stop();
            recordBtn.disabled = false;
            stopBtn.disabled = true;
            statusText.innerText = "Transcribing audio... Please wait.";
            statusText.style.color = "#3b82f6";
        };
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/transcribe", methods=["POST"])
def do_transcribe():
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file uploaded"})
        
    file = request.files['audio']
    webm_path = "live_input.webm"
    wav_path = "live_input.wav"
    
    file.save(webm_path)
    
    # Convert browser webm recording to 16kHz wav using our bundled ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ffmpeg, "-i", webm_path, "-ar", "16000", "-ac", "1", wav_path, "-y"], capture_output=True)
    
    try:
        out = transcribe(wav_path)
        return jsonify({
            "text": out.text,
            "language": out.language,
            "confidence": out.confidence
        })
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    print("Server ready! Open http://127.0.0.1:5000 in your browser.")
    app.run(host="127.0.0.1", port=5000, debug=False)
