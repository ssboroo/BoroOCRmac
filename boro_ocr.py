import os
import sys
import io
import base64
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageGrab, ImageChops, ImageStat, ImageTk
from openai import OpenAI

# =========================================================
# macOS SCREEN CAPTURE
# =========================================================
import ctypes

def check_screen_permission():
    if sys.platform != "darwin":
        return
    framework = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    if hasattr(framework, "CGPreflightScreenCaptureAccess"):
        framework.CGPreflightScreenCaptureAccess.restype = ctypes.c_bool
        framework.CGRequestScreenCaptureAccess.restype = ctypes.c_bool
        if not framework.CGPreflightScreenCaptureAccess():
            framework.CGRequestScreenCaptureAccess()
            raise RuntimeError("System Settings → Privacy & Security → Screen Recording "
                               "(эсвэл Screen & System Audio Recording) хэсэгт BoroOCR-д "
                               "зөвшөөрөл өгөөд програмыг дахин нээнэ үү.")

def crop_selection(image, bbox, logical_size):
    sx = image.width / logical_size[0]
    sy = image.height / logical_size[1]
    x1, y1, x2, y2 = bbox
    return image.crop((round(x1*sx), round(y1*sy), round(x2*sx), round(y2*sy)))

# =========================================================
# ТОХИРГОО
# =========================================================
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")

CHECK_INTERVAL_MS = 300
STABILITY_FRAMES = 2
CHANGE_THRESHOLD = 3.0
MAX_IMAGE_SIDE = 1600

PROMPT = """Чи Монгол хэл дээрх тестийг зурагнаас уншиж зөв хариултыг олдог AI.
Зөвхөн дараах форматаар хариул:

✅ Зөв хариулт: [Үсэг] — [Сонголтын бүтэн текст]
💡 [1 богино өгүүлбэр]"""

# =========================================================
# ЗУРАГ БЭЛТГЭХ
# =========================================================
def prepare_image(image):
    image = image.convert("RGB")
    width, height = image.size
    if width < 2 or height < 2:
        raise ValueError("Зургийн хэмжээ хэт жижиг")

    longest = max(width, height)
    if longest > MAX_IMAGE_SIDE:
        scale = MAX_IMAGE_SIDE / longest
        image = image.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            Image.Resampling.BILINEAR,
        )

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return "data:image/jpeg;base64," + encoded


def image_difference(image_a, image_b):
    if image_a is None or image_b is None:
        return 999.0
    size = (90, 55)
    a = image_a.convert("L").resize(size, Image.Resampling.BILINEAR)
    b = image_b.convert("L").resize(size, Image.Resampling.BILINEAR)
    diff = ImageChops.difference(a, b)
    return ImageStat.Stat(diff).mean[0]


# =========================================================
# ҮНДСЭН ПРОГРАМ
# =========================================================
class AutoQuizHelper:
    def __init__(self, root):
        self.root = root
        self.root.title("BoroOCR — macOS")
        self.root.geometry("780x620")
        self.root.minsize(600, 450)

        self.events = queue.Queue()
        self.cancel_event = threading.Event()
        self.monitor_after = None
        self.logical_size = None
        self.pending_lock = threading.Lock()
        self.client = None
        self.bbox = None
        self.monitoring = False
        self.processing = False
        self.closed = False
        self.previous_image = None
        self.last_processed_image = None
        self.stable_frames = 0
        self.pending_image = None

        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(60, self.process_events)

        if self.api_key_missing():
            self.status_var.set("GROQ_API_KEY оруулна уу")

    def api_key_missing(self):
        return (not GROQ_API_KEY or GROQ_API_KEY.strip() == "" or
                GROQ_API_KEY == "ЭНД_ШИНЭ_GROQ_API_KEY_ЭЭ_ОРУУЛНА")

    def build_ui(self):
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="BoroOCR  •  macOS",
                  font=("Helvetica", 14, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Сонгосон хэсгийн зураг Groq API руу илгээгдэнэ. Хариултын түүх хадгалагдана.").pack(anchor="w", pady=(2, 8))

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(0, 6))

        self.select_button = ttk.Button(buttons, text="1. Хэсэг сонгох", command=self.select_region)
        self.select_button.pack(side="left", padx=(0, 5))

        self.start_button = ttk.Button(buttons, text="2. Хяналт эхлүүлэх", command=self.start_monitoring, state="disabled")
        self.start_button.pack(side="left", padx=5)

        self.stop_button = ttk.Button(buttons, text="Зогсоох", command=self.stop_monitoring, state="disabled")
        self.stop_button.pack(side="left", padx=5)

        self.once_button = ttk.Button(buttons, text="Одоо шинжлэх", command=self.analyze_now, state="disabled")
        self.once_button.pack(side="left", padx=5)

        self.status_var = tk.StringVar(value="Бэлэн")
        ttk.Label(outer, textvariable=self.status_var, foreground="#1769aa").pack(anchor="w", pady=(0, 5))

        self.output = tk.Text(outer, wrap="word", font=("Helvetica", 11), height=20, bg="#f8f9fa")
        self.output.pack(fill="both", expand=True, pady=(3, 4))

        self.output.tag_configure("correct", foreground="#0a7a2f", font=("Helvetica", 13, "bold"), background="#d8f5e2")
        self.output.tag_configure("normal", foreground="#222222")
        self.output.tag_configure("wait", foreground="#b45309", font=("Helvetica", 11, "bold"))

    def log(self, text):
        self.output.insert("end", text + "\n\n", "normal")
        self.output.see("end")

    def log_answer(self, text):
        self.output.insert("end", "─" * 45 + "\n", "normal")
        for line in text.strip().split("\n"):
            if "✅" in line or "Зөв хариулт" in line:
                self.output.insert("end", line.strip() + "\n", "correct")
            else:
                self.output.insert("end", line + "\n", "normal")
        self.output.insert("end", "─" * 45 + "\n\n", "normal")
        self.output.see("end")

    def select_region(self):
        if self.monitoring:
            self.stop_monitoring()
        self.root.withdraw()
        self.root.after(180, self.open_selection_overlay)

    def open_selection_overlay(self):
        try:
            check_screen_permission()
            screenshot = ImageGrab.grab().convert("RGB")
        except Exception as exc:
            self.root.deiconify()
            messagebox.showerror("Алдаа", str(exc))
            return

        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.logical_size = (screen_w, screen_h)
        screenshot = screenshot.resize((screen_w, screen_h), Image.Resampling.LANCZOS)
        overlay = tk.Toplevel(self.root)
        overlay.withdraw()
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.geometry(f"{screen_w}x{screen_h}+0+0")

        canvas = tk.Canvas(overlay, width=screen_w, height=screen_h, highlightthickness=0, cursor="crosshair")
        canvas.pack(fill="both", expand=True)

        photo = ImageTk.PhotoImage(screenshot)
        canvas.create_image(0, 0, image=photo, anchor="nw")
        canvas.image = photo

        canvas.create_rectangle(0, 0, screen_w, 54, fill="#111827", outline="")
        canvas.create_text(16, 10, text="АСУУЛТ + СОНГОЛТУУДЫГ ХҮРЭЭЛНЭ ҮҮ", fill="white",
                           anchor="nw", font=("Helvetica", 12, "bold"))
        canvas.create_text(16, 32, text="Чирээд сонго  |  ESC — Болих", fill="#ccc",
                           anchor="nw", font=("Helvetica", 9))

        selection = {"x": 0, "y": 0, "rect": None}

        def mouse_down(e):
            selection["x"], selection["y"] = e.x, e.y
            if selection["rect"]:
                canvas.delete(selection["rect"])
            selection["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#00ff66", width=3)

        def mouse_move(e):
            if selection["rect"]:
                canvas.coords(selection["rect"], selection["x"], selection["y"], e.x, e.y)

        def mouse_up(e):
            ex, ey = max(0, min(e.x, screen_w)), max(0, min(e.y, screen_h))
            x1, y1 = min(selection["x"], ex), min(selection["y"], ey)
            x2, y2 = max(selection["x"], ex), max(selection["y"], ey)
            if x2 - x1 < 35 or y2 - y1 < 22:
                return
            self.bbox = (x1, y1, x2, y2)
            try:
                overlay.grab_release()
            except:
                pass
            overlay.destroy()
            self.root.deiconify()
            self.root.lift()
            self.previous_image = None
            self.last_processed_image = None
            self.stable_frames = 0
            self.start_button.configure(state="normal")
            self.once_button.configure(state="normal")
            self.status_var.set(f"Сонгосон: {x2-x1}×{y2-y1}")
            self.log(f"Хэсэг сонгогдлоо: {x2-x1}×{y2-y1}")

        def cancel(e=None):
            try:
                overlay.grab_release()
            except:
                pass
            if overlay.winfo_exists():
                overlay.destroy()
            self.root.deiconify()
            self.status_var.set("Цуцлагдлаа")

        canvas.bind("<ButtonPress-1>", mouse_down)
        canvas.bind("<B1-Motion>", mouse_move)
        canvas.bind("<ButtonRelease-1>", mouse_up)
        overlay.bind("<Escape>", cancel)

        overlay.update_idletasks()
        overlay.deiconify()
        overlay.lift()
        overlay.focus_force()
        overlay.grab_set()

    def get_client(self):
        global GROQ_API_KEY
        if self.api_key_missing():
            GROQ_API_KEY = (simpledialog.askstring("Groq API", "Шинэ Groq API key оруулна уу (зөвхөн санах ойд):", show="*", parent=self.root) or "").strip()
            if not GROQ_API_KEY:
                raise ValueError("API key оруулаагүй")
        if self.client is None:
            self.client = OpenAI(
                api_key=GROQ_API_KEY,
                base_url="https://api.groq.com/openai/v1",
                timeout=20.0,
                max_retries=0,
            )
        return self.client

    def capture_region(self):
        if not self.bbox:
            raise ValueError("Хэсэг сонгоогүй")
        check_screen_permission()
        full = ImageGrab.grab().convert("RGB")
        current_size = (self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        if current_size != self.logical_size:
            raise ValueError("Дэлгэцийн хэмжээ өөрчлөгдсөн. Хэсгээ дахин сонгоно уу.")
        img = crop_selection(full, self.bbox, self.logical_size)
        if img.width < 30 or img.height < 20:
            raise ValueError("Хэт жижиг хэсэг")
        return img

    def analyze_now(self):
        if self.processing:
            self.status_var.set("Боловсруулж байна...")
            return
        try:
            self.get_client()
            image = self.capture_region()
        except Exception as exc:
            messagebox.showerror("Алдаа", str(exc))
            return
        self.last_processed_image = image.copy()
        self.start_analysis(image)

    def start_monitoring(self):
        if self.monitoring:
            return
        if not self.bbox:
            messagebox.showwarning("Анхаар", "Эхлээд хэсэг сонго")
            return
        try:
            self.get_client()
        except Exception as exc:
            messagebox.showerror("API", str(exc))
            return

        self.monitoring = True
        self.previous_image = None
        self.last_processed_image = None
        self.stable_frames = 0
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.select_button.configure(state="disabled")
        self.status_var.set("Хянаж байна...")
        self.monitor_loop()

    def stop_monitoring(self):
        self.monitoring = False
        if self.monitor_after is not None:
            self.root.after_cancel(self.monitor_after)
            self.monitor_after = None
        self.stable_frames = 0
        with self.pending_lock:
            self.pending_image = None
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.select_button.configure(state="normal")
        self.status_var.set("Зогссон")

    def monitor_loop(self):
        self.monitor_after = None
        if self.closed or not self.monitoring:
            return
        try:
            current = self.capture_region()
            if self.previous_image is None:
                self.previous_image = current.copy()
                self.stable_frames = 0
            else:
                diff = image_difference(current, self.previous_image)
                if diff < CHANGE_THRESHOLD:
                    self.stable_frames += 1
                else:
                    self.stable_frames = 0
                self.previous_image = current.copy()

                if self.stable_frames >= STABILITY_FRAMES:
                    changed = image_difference(current, self.last_processed_image)
                    if self.last_processed_image is None or changed > CHANGE_THRESHOLD:
                        self.last_processed_image = current.copy()
                        if self.processing:
                            with self.pending_lock:
                                self.pending_image = current.copy()
                        else:
                            self.start_analysis(current.copy())
        except Exception as exc:
            self.stop_monitoring()
            self.events.put(("error", str(exc)))

        if self.monitoring and not self.closed:
            self.monitor_after = self.root.after(CHECK_INTERVAL_MS, self.monitor_loop)

    def start_analysis(self, image):
        if self.closed or self.processing:
            return
        self.processing = True
        self.status_var.set("Шинжилж байна...")
        threading.Thread(target=self.analysis_worker, args=(image.copy(),), daemon=True).start()

    def analysis_worker(self, image):
        try:
            client = self.client
            image_url = prepare_image(image)

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = client.chat.completions.create(
                        model=GROQ_MODEL,
                        messages=[
                            {"role": "system", "content": PROMPT},
                            {"role": "user", "content": [
                                {"type": "text", "text": "Зураг дээрх асуултын зөв хариултыг хэл."},
                                {"type": "image_url", "image_url": {"url": image_url}},
                            ]},
                        ],
                        temperature=0.0,
                        max_completion_tokens=1024,
                    )
                    answer = response.choices[0].message.content or "Хариулт ирсэнгүй"
                    self.events.put(("answer", answer))
                    break

                except Exception as e:
                    error_text = str(e)
                    if "429" in error_text:
                        wait_sec = 10
                        self.events.put(("wait", f"Rate limit → {wait_sec} секунд хүлээж байна... ({attempt+1}/{max_retries})"))
                        if self.cancel_event.wait(wait_sec):
                            return
                        if attempt == max_retries - 1:
                            self.events.put(("error", "Rate limit хэтэрхий олон удаа. Дараа дахин оролдоно уу."))
                    else:
                        self.events.put(("error", f"Алдаа: {e}"))
                        break
        except Exception as exc:
            self.events.put(("error", f"Алдаа: {exc}"))
        finally:
            self.events.put(("finished", None))

    def process_events(self):
        if self.closed:
            return
        try:
            while True:
                event_type, payload = self.events.get_nowait()
                if event_type == "answer":
                    self.log_answer(payload)
                    self.status_var.set("Бэлэн ✓")
                elif event_type == "wait":
                    self.output.insert("end", f"⏳ {payload}\n\n", "wait")
                    self.output.see("end")
                    self.status_var.set("Хүлээж байна...")
                elif event_type == "error":
                    self.log("⚠️ " + str(payload))
                    self.status_var.set("Алдаа")
                elif event_type == "finished":
                    self.processing = False
                    next_image = None
                    with self.pending_lock:
                        if self.monitoring:
                            next_image = self.pending_image
                        self.pending_image = None
                    if next_image is not None:
                        self.start_analysis(next_image)
        except queue.Empty:
            pass
        if not self.closed:
            self.root.after(60, self.process_events)

    def close(self):
        self.closed = True
        self.cancel_event.set()
        self.monitoring = False
        with self.pending_lock:
            self.pending_image = None
        self.root.destroy()


def self_test(report_path):
    """Exercise bundled Tcl/Tk, Pillow and SDK without screen permission or API calls."""
    import json
    import platform
    from pathlib import Path
    root = tk.Tk()
    root.withdraw()
    app = AutoQuizHelper(root)
    root.update()
    image = Image.new("RGB", (2000, 1200), "white")
    assert crop_selection(image, (100, 50, 400, 200), (1000, 600)).size == (600, 300)
    assert prepare_image(image).startswith("data:image/jpeg;base64,")
    assert image_difference(image, image) == 0
    photo = ImageTk.PhotoImage(image.resize((10, 10)), master=root)
    assert photo.width() == 10
    client = OpenAI(api_key="self-test-only", base_url="https://api.groq.com/openai/v1")
    client.close()
    root.update_idletasks()
    app.close()
    Path(report_path).write_text(json.dumps({"ok": True, "arch": platform.machine(),
        "frozen": bool(getattr(sys, "frozen", False)), "python": platform.python_version()}))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        self_test(sys.argv[2])
    else:
        root = tk.Tk()
        app = AutoQuizHelper(root)
        root.mainloop()