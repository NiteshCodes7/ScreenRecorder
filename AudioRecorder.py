
import queue
import threading

import soundcard as sc
import sounddevice as sd
import soundfile as sf


class AudioRecorder:
    def __init__(self, sample_rate=44100, mic_device=None):
        self.sample_rate = sample_rate
        self.mic_device = mic_device

        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.start_event = threading.Event()

        self.errors = []
        self.threads = []
        self.ready_events = []

        self.mic_stream = None
        self.mic_queue = queue.Queue()
        self.mic_path = None
        self.system_path = None

    def _record_microphone(self, ready_event):
        """Write queued microphone audio to WAV on a worker thread."""
        try:
            with sf.SoundFile(
                self.mic_path,
                mode="w",
                samplerate=self.sample_rate,
                channels=1,
                subtype="PCM_16",
            ) as wav_file:
                ready_event.set()

                while True:
                    data = self.mic_queue.get()

                    if data is None:
                        break

                    wav_file.write(data)

        except Exception as error:
            self.errors.append(f"Microphone writer: {error}")
            self.stop_event.set()
        finally:
            ready_event.set()

    def _microphone_callback(
        self, indata, frames, time_info, status
    ):
        """Called by sounddevice for each captured microphone block."""
        if status:
            # Report actual input overflow/underflow problems.
            # Other statuses may also be informational.
            self.errors.append(f"Microphone input status: {status}")

        if self.stop_event.is_set():
            return

        if not self.start_event.is_set() or self.pause_event.is_set():
            return

        try:
            self.mic_queue.put_nowait(indata.copy())
        except Exception as error:
            self.errors.append(f"Microphone queue: {error}")

    def _record_system_audio(self, ready_event):
        try:
            speaker = sc.default_speaker()
            loopback = sc.get_microphone(
                id=str(speaker.name),
                include_loopback=True,
            )

            with sf.SoundFile(
                self.system_path,
                mode="w",
                samplerate=self.sample_rate,
                channels=2,
                subtype="PCM_16",
            ) as wav_file:
                with loopback.recorder(
                    samplerate=self.sample_rate,
                    channels=2,
                ) as recorder:
                    ready_event.set()
                    self.start_event.wait()

                    while not self.stop_event.is_set():
                        data = recorder.record(numframes=4096)

                        if self.stop_event.is_set():
                            break

                        if not self.pause_event.is_set():
                            wav_file.write(data)

        except Exception as error:
            self.errors.append(f"System audio: {error}")
            self.stop_event.set()
        finally:
            ready_event.set()

    def start(self, mic_path, system_path, pause_event):
        self.stop_event.clear()
        self.start_event.clear()
        self.pause_event = pause_event
        self.errors.clear()
        self.threads.clear()
        self.mic_queue = queue.Queue()

        self.mic_path = mic_path
        self.system_path = system_path

        mic_ready = threading.Event()
        system_ready = threading.Event()
        self.ready_events = [mic_ready, system_ready]

        # Start the microphone WAV writer.
        mic_writer = threading.Thread(
            target=self._record_microphone,
            args=(mic_ready,),
            daemon=True,
        )
        self.threads.append(mic_writer)
        mic_writer.start()

        if not mic_ready.wait(timeout=10):
            self.stop_event.set()
            raise RuntimeError("Microphone writer failed to initialize.")

        if self.errors:
            raise RuntimeError("\n".join(self.errors))

        # Start system-audio loopback capture.
        system_thread = threading.Thread(
            target=self._record_system_audio,
            args=(system_ready,),
            daemon=True,
        )
        self.threads.append(system_thread)
        system_thread.start()

        if not system_ready.wait(timeout=10):
            self.stop_event.set()
            raise RuntimeError("System audio failed to initialize.")

        if self.errors:
            raise RuntimeError("\n".join(self.errors))

        # Open microphone capture, but don't save audio until begin().
        try:
            self.mic_stream = sd.InputStream(
                device=self.mic_device,
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                callback=self._microphone_callback,
            )
            self.mic_stream.start()

        except Exception as error:
            self.stop_event.set()
            self.mic_queue.put(None)
            raise RuntimeError(
                f"Could not start microphone capture: {error}"
            ) from error

    def begin(self):
        if self.errors:
            raise RuntimeError("\n".join(self.errors))

        self.start_event.set()

    def stop(self):
        self.stop_event.set()
        self.start_event.set()

        # Stop microphone callbacks before telling its writer to finish.
        if self.mic_stream is not None:
            try:
                self.mic_stream.stop()
                self.mic_stream.close()
            finally:
                self.mic_stream = None

        # Drain queued audio and close the microphone WAV cleanly.
        self.mic_queue.put(None)

        for thread in self.threads:
            thread.join(timeout=10)

        if any(thread.is_alive() for thread in self.threads):
            raise RuntimeError(
                "An audio recording thread did not stop in time."
            )

        if self.errors:
            raise RuntimeError("\n".join(self.errors))
