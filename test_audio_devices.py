import soundcard as sc

print("=== Microphones ===")
for mic in sc.all_microphones(include_loopback=False):
    print(mic.name)

print("\n=== Speakers / System Audio ===")
for speaker in sc.all_speakers():
    print(speaker.name)
