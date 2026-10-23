import cv2
import mss
import numpy as np
import threading
import time
import os
import shutil
import tempfile
import subprocess

from AudioRecorder import AudioRecorder


FFMPEG_PATH = (
    r"C:\Users\nites\Downloads\ffmpeg-master-latest-win64-gpl"
    r"\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"
)


class ScreenRecorder:
    def __init__(self, fps=20):
        self.fps = fps
        self.recording = False
        self.paused = False
        self.thread = None
        self.output_path = None

        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.video_ready_event = threading.Event()

        self.audio_recorder = AudioRecorder(mic_device=1)
        self.temp_dir = None
        self.video_temp_path = None
        self.mic_temp_path = None
        self.system_temp_path = None

    def start(self, output_path):
        if self.recording:
            return

        if not os.path.isfile(FFMPEG_PATH):
            raise FileNotFoundError(
                f"FFmpeg executable not found:\n{FFMPEG_PATH}"
            )

        self.output_path = output_path
        self.temp_dir = tempfile.mkdtemp(prefix="screen_recorder_")

        self.video_temp_path = os.path.join(
            self.temp_dir, "video.mp4"
        )
        self.mic_temp_path = os.path.join(
            self.temp_dir, "microphone.wav"
        )
        self.system_temp_path = os.path.join(
            self.temp_dir, "system_audio.wav"
        )

        self.stop_event.clear()
        self.pause_event.clear()
        self.recording = True
        self.paused = False

        
        try:
            # Prepare audio capture first. Audio waits for begin().
            self.audio_recorder.start(
                self.mic_temp_path,
                self.system_temp_path,
                self.pause_event
            )

            self.video_ready_event.clear()

            self.thread = threading.Thread(
                target=self._record,
                daemon=True
            )
            self.thread.start()

            if not self.video_ready_event.wait(timeout=10):
                raise RuntimeError("Video recorder failed to initialize.")

            # Release audio and video from the same start event.
            self.audio_recorder.begin()

        except Exception:
            self.stop_event.set()

            try:
                self.audio_recorder.stop()
            except Exception:
                pass

            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=5)

            self.recording = False
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None
            raise


    def _record(self):
        writer = None

        try:
            with mss.mss() as screen:
                monitor = screen.monitors[1]

                width = monitor["width"]
                height = monitor["height"]

                fourcc = cv2.VideoWriter_fourcc(*"mp4v")

                writer = cv2.VideoWriter(
                    self.video_temp_path,
                    fourcc,
                    self.fps,
                    (width, height)
                )

                if not writer.isOpened():
                    raise RuntimeError("Could not initialize video writer.")

                self.video_ready_event.set()

                # Wait until audio recording is released.
                frame_interval = 1.0 / self.fps
                next_frame_time = time.monotonic()

                while not self.stop_event.is_set():
                    if self.pause_event.is_set():
                        time.sleep(0.02)
                        # Prevent a large timing jump after resuming.
                        next_frame_time = time.monotonic() + frame_interval
                        continue

                    screenshot = screen.grab(monitor)
                    frame = np.asarray(screenshot)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                    writer.write(frame)

                    next_frame_time += frame_interval
                    remaining = next_frame_time - time.monotonic()

                    if remaining > 0:
                        time.sleep(remaining)
                    else:
                        # Avoid trying to catch up indefinitely if capture is slow.
                        next_frame_time = time.monotonic()

        except Exception as error:
            print(f"Recording error: {error}")

        finally:
            if writer is not None:
                writer.release()

            self.recording = False

    def pause(self):
        if self.recording and not self.paused:
            self.pause_event.set()
            self.paused = True

    def resume(self):
        if self.recording and self.paused:
            self.pause_event.clear()
            self.paused = False

    def stop(self):
        self.stop_event.set()

        if self.thread and self.thread.is_alive():
            self.thread.join()

        self.recording = False
        self.paused = False

        try:
            # Stop audio capture and close both WAV files.
            self.audio_recorder.stop()

            debug_audio_path = os.path.abspath("system_audio_debug.wav")
            shutil.copy2(self.system_temp_path, debug_audio_path)

            print(f"System audio saved to: {debug_audio_path}")

            if not os.path.isfile(self.video_temp_path):
                raise RuntimeError("Temporary video file was not created.")

            if (
                not os.path.isfile(self.mic_temp_path)
                or not os.path.isfile(self.system_temp_path)
            ):
                raise RuntimeError("One or both audio files are missing.")

            # Mix microphone and system audio, then mux with video.
            
            command = [
                FFMPEG_PATH,
                "-y",

                "-i", self.video_temp_path,
                "-i", self.mic_temp_path,
                "-i", self.system_temp_path,

                "-filter_complex",
                (
                     "[1:a]asetpts=PTS-STARTPTS[mic];"
                    "[2:a]asetpts=PTS-STARTPTS,aresample=async=1000:first_pts=0[sys];"
                    "[mic][sys]amix=inputs=2:duration=longest:dropout_transition=0[a]"
                ),

                "-map", "0:v:0",
                "-map", "[a]",

                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",

                "-movflags", "+faststart",
                self.output_path,
            ]


            result = subprocess.run(
                command,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                raise RuntimeError(
                    "FFmpeg failed to create the final video:\n"
                    + result.stderr[-3000:]
                )

            # Remove temporary files only after successful export.
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None

        except Exception:
            # Keep temporary files if export fails, for troubleshooting.
            raise