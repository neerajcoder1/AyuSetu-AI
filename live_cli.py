import sounddevice as sd
import soundfile as sf
import numpy as np
import queue
import sys
import warnings
from neeraj.asr.transcriber import transcribe, reset_backend

# Ignore warnings from the audio libraries for a cleaner CLI
warnings.filterwarnings("ignore")

samplerate = 16000
channels = 1
q = queue.Queue()

def callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    q.put(indata.copy())

def main():
    print("Loading ASR model into memory (this may take a few seconds)...")
    reset_backend()
    
    print("\n" + "="*40)
    print("      🎙️ AyuSetu Live CLI Test      ")
    print("="*40)
    
    while True:
        input("\nPress [Enter] to START recording (or Ctrl+C to exit)...")
        
        # Clear queue
        while not q.empty():
            q.get()
            
        recording = []
        try:
            stream = sd.InputStream(samplerate=samplerate, channels=channels, callback=callback)
            with stream:
                input("🔴 RECORDING! Speak now, then press [Enter] to STOP...")
                
            print("Processing audio...")
            while not q.empty():
                recording.append(q.get())
                
            if not recording:
                print("No audio captured.")
                continue
                
            audio_data = np.concatenate(recording, axis=0)
            
            # Save to temporary file for the transcriber
            temp_wav = "live_sample.wav"
            sf.write(temp_wav, audio_data, samplerate)
            
            print("Transcribing...")
            out = transcribe(temp_wav)
            
            print("\n=== Transcription Result ===")
            print(f"📝 Text       : {out.text}")
            print(f"🌐 Language   : {out.language}")
            print(f"📊 Confidence : {out.confidence:.4f}")
            print("============================\n")
            
        except KeyboardInterrupt:
            print("\nExiting live test. Goodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")

if __name__ == "__main__":
    main()
