
import soundfile as sf
import numpy as np

path = r"C:\Users\nites\Desktop\Screen Recorder\system_audio_debug.wav"  # Update this to your actual WAV path

audio, sample_rate = sf.read(path)

if audio.ndim == 2:
    audio = np.max(np.abs(audio), axis=1)
else:
    audio = np.abs(audio)

window = int(sample_rate * 0.1)  # 100 ms windows
threshold = 0.005

print(f"Sample rate: {sample_rate}")
print(f"Duration: {len(audio) / sample_rate:.2f} seconds")

for start in range(0, len(audio), window):
    chunk = audio[start:start + window]
    if len(chunk) and np.sqrt(np.mean(chunk ** 2)) > threshold:
        print(f"First detected audio at: {start / sample_rate:.2f} seconds")
        break
else:
    print("No audio detected above the threshold.")
