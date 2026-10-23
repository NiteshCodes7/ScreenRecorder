from ScreenRecorder import ScreenRecorder
import tkinter as tk
from tkinter import messagebox, filedialog
from datetime import datetime


class RecorderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("OpenCV Screen Recorder")
        self.root.geometry("400x280")

        self.recorder = ScreenRecorder(fps=20)
        self.status = tk.StringVar(value="Ready to record")

        tk.Label(
            root,
            text="SCREEN RECORDER",
            font=("Arial", 18, "bold")
        ).pack(pady=20)

        tk.Label(root, textvariable=self.status).pack(pady=5)

        tk.Button(
            root, text="Start Recording",
            command=self.start_recording,
            width=22
        ).pack(pady=5)

        tk.Button(
            root, text="Pause / Resume",
            command=self.toggle_pause,
            width=22
        ).pack(pady=5)

        tk.Button(
            root, text="Stop Recording",
            command=self.stop_recording,
            width=22
        ).pack(pady=5)

        self.root.protocol(
            "WM_DELETE_WINDOW", self.close_app
        )

    def start_recording(self):
        if self.recorder.recording:
            return

        default_name = (
            "recording_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + ".mp4"
        )

        path = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            initialfile=default_name,
            filetypes=[("MP4 video", "*.mp4")]
        )

        if not path:
            return

        try:
            self.recorder.start(path)
            self.status.set("Recording video and audio...")
        except Exception as error:
            messagebox.showerror("Recording Error", str(error))
            self.status.set("Ready to record")

    def toggle_pause(self):
        if not self.recorder.recording:
            return

        if self.recorder.paused:
            self.recorder.resume()
            self.status.set("Recording...")
        else:
            self.recorder.pause()
            self.status.set("Paused")

    def stop_recording(self):
        if not self.recorder.recording:
            return

        self.status.set("Saving video and mixing audio...")
        self.root.update_idletasks()

        try:
            self.recorder.stop()

            self.status.set("Recording saved")

            messagebox.showinfo(
                "Screen Recorder",
                f"Video saved successfully to:\n"
                f"{self.recorder.output_path}"
            )

        except Exception as error:
            self.status.set("Export failed")

            messagebox.showerror(
                "Recording Error",
                f"Could not finalize the recording:\n\n{error}"
            )

    def close_app(self):
        if self.recorder.recording:
            try:
                self.recorder.stop()
            except Exception as error:
                messagebox.showerror(
                    "Recording Error",
                    f"Could not finalize the recording:\n\n{error}"
                )

        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = RecorderApp(root)
    root.mainloop()