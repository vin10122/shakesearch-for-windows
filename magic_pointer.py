import os
import time
import math
import threading
import base64
import io
from dotenv import load_dotenv
from pynput import mouse
from mss import mss
from PIL import Image, ImageDraw, ImageTk
import tkinter as tk

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

SHAKE_THRESHOLD = 150
SHAKE_TIME_WINDOW = 0.8
SHAKE_MIN_DIRECTION_CHANGES = 5
SHAKE_DEBOUNCE = 0.8

SELECTION_MIN_RADIUS = 60
SELECTION_MAX_RADIUS = 500


class MagicPointer:
    def __init__(self):
        self.client = None
        if GROQ_API_KEY:
            from groq import Groq
            self.client = Groq(api_key=GROQ_API_KEY)

        self.positions = []
        self.last_shake = 0
        self.root = tk.Tk()
        self.root.withdraw()
        self.listener = None
        self.selector = None
        self.chat = None

    def detect_shake(self, x, y):
        now = time.time()
        self.positions.append((x, y, now))
        cutoff = now - SHAKE_TIME_WINDOW
        self.positions = [
            (px, py, pt) for px, py, pt in self.positions if pt > cutoff
        ]

        if len(self.positions) < SHAKE_MIN_DIRECTION_CHANGES + 2:
            return False

        total_distance = 0.0
        for i in range(1, len(self.positions)):
            x1, y1, _ = self.positions[i - 1]
            x2, y2, _ = self.positions[i]
            total_distance += abs(x2 - x1) + abs(y2 - y1)

        direction_changes = 0
        for i in range(2, len(self.positions)):
            x1, y1, _ = self.positions[i - 2]
            x2, y2, _ = self.positions[i - 1]
            x3, y3, _ = self.positions[i]
            dx1 = x2 - x1
            dy1 = y2 - y1
            dx2 = x3 - x2
            dy2 = y3 - y2
            cross = dx1 * dy2 - dy1 * dx2
            if cross != 0:
                direction_changes += 1

        if direction_changes >= SHAKE_MIN_DIRECTION_CHANGES and total_distance > SHAKE_THRESHOLD:
            now = time.time()
            if now - self.last_shake > SHAKE_DEBOUNCE:
                self.last_shake = now
                self.positions = []
                print("[Magic Pointer] Shake rilevato")
                return True
        return False

    def on_move(self, x, y):
        if self.selector or self.chat:
            return
        if self.detect_shake(x, y):
            self.root.after(0, self.start_selector)

    def start_selector(self):
        self.selector = CircleSelector(self.root, self.on_selection_done)

    def on_selection_done(self, center, radius):
        self.selector = None
        if not center or not radius:
            return
        img = self.capture_circle(center, radius)
        self.open_chat(img)

    def capture_circle(self, center, radius):
        with mss() as sct:
            mon = sct.monitors[1]
            left = max(0, int(center[0] - radius))
            top = max(0, int(center[1] - radius))
            right = min(mon["width"], int(center[0] + radius))
            bottom = min(mon["height"], int(center[1] + radius))
            width = right - left
            height = bottom - top
            shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
            img = Image.frombytes("RGB", shot.size, shot.rgb)

        mask = Image.new("L", img.size, 0)
        draw = ImageDraw.Draw(mask)
        cx = center[0] - left
        cy = center[1] - top
        r = min(radius, width // 2, height // 2)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)

        output = Image.new("RGB", img.size, (20, 20, 20))
        output.paste(img, mask=mask)
        return output

    def open_chat(self, img):
        self.chat = ChatWindow(self.root, img, self.client, GROQ_MODEL, self.close_chat)

    def close_chat(self):
        self.chat = None

    def run(self):
        self.listener = mouse.Listener(on_move=self.on_move)
        self.listener.daemon = True
        self.listener.start()
        print("[Magic Pointer] In ascolto. Scuoti il mouse per attivare.")
        self.root.mainloop()


class CircleSelector:
    def __init__(self, root, callback):
        self.root = root
        self.callback = callback
        self.win = tk.Toplevel(root)
        self.win.attributes("-fullscreen", True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.35)
        self.win.configure(bg="black")

        self.canvas = tk.Canvas(self.win, bg="black", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

        self.center = None
        self.radius = 0
        self.anim_phase = 0
        self.done = False

        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Escape>", lambda e: self.cancel())

        self.animate()

    def on_motion(self, e):
        if self.done or self.center is None:
            return
        self.center = (e.x, e.y)

    def on_press(self, e):
        self.center = (e.x, e.y)
        self.radius = SELECTION_MIN_RADIUS

    def on_drag(self, e):
        if not self.center:
            return
        dx = e.x - self.center[0]
        dy = e.y - self.center[1]
        self.radius = max(SELECTION_MIN_RADIUS, min(SELECTION_MAX_RADIUS, int(math.hypot(dx, dy))))

    def on_release(self, e):
        if self.center and self.radius >= SELECTION_MIN_RADIUS:
            self.done = True
            self.win.destroy()
            self.callback(self.center, self.radius)
        else:
            self.cancel()

    def cancel(self):
        self.done = True
        self.win.destroy()
        self.callback(None, None)

    def animate(self):
        if self.done or not self.win.winfo_exists():
            return
        self.anim_phase += 0.15
        self.canvas.delete("all")
        if self.center:
            r = self.radius
            pulse = r + 14 + 12 * math.sin(self.anim_phase * 5)
            self.canvas.create_oval(
                self.center[0] - pulse, self.center[1] - pulse,
                self.center[0] + pulse, self.center[1] + pulse,
                outline="#00ff88", width=2
            )
            self.canvas.create_oval(
                self.center[0] - r, self.center[1] - r,
                self.center[0] + r, self.center[1] + r,
                outline="#ffffff", width=3
            )
            self.canvas.create_oval(
                self.center[0] - 6, self.center[1] - 6,
                self.center[0] + 6, self.center[1] + 6,
                fill="#00ff88", outline="#ffffff", width=1
            )
            self.canvas.create_text(
                self.center[0], self.center[1] - r - 32,
                text="Trascina per selezionare  •  Esc per annulla",
                fill="#ffffff", font=("Segoe UI", 12, "bold")
            )
        self.win.after(30, self.animate)


class ChatWindow:
    def __init__(self, root, img, client, model, on_close):
        self.root = root
        self.img = img
        self.client = client
        self.model = model
        self.on_close = on_close
        self.win = tk.Toplevel(root)
        self.win.title("Magic Pointer")
        self.win.geometry("480x640")
        self.win.configure(bg="#0a0a0a")
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.0)

        self.build_ui()
        self.fade_in()

        threading.Thread(target=self.fetch_suggestions, daemon=True).start()

    def show_preview(self):
        img = self.img.copy()
        img.thumbnail((450, 300), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        self.preview_label.configure(image=photo)
        self.preview_label.image = photo

    def _on_mousewheel(self, event):
        self.scroll.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def build_ui(self):
        self.header = tk.Frame(self.win, bg="#121212", height=56)
        self.header.pack(fill="x")
        self.header.pack_propagate(False)

        tk.Label(
            self.header, text="Magic Pointer",
            bg="#121212", fg="#00ff88",
            font=("Segoe UI", 13, "bold")
        ).pack(side="left", padx=18, pady=15)

        tk.Button(
            self.header, text="✕", bg="#121212", fg="#ffffff",
            bd=0, font=("Segoe UI", 13), command=self.close,
            cursor="hand2"
        ).pack(side="right", padx=16)

        self.scroll = tk.Canvas(self.win, bg="#0a0a0a", highlightthickness=0)
        self.scroll.pack(fill="both", expand=True, padx=16, pady=14)
        self.scroll.bind("<MouseWheel>", self._on_mousewheel)

        self.frame = tk.Frame(self.scroll, bg="#0a0a0a")
        self.scroll.create_window((0, 0), window=self.frame, anchor="nw")
        self.frame.bind("<Configure>", lambda e: self.scroll.configure(scrollregion=self.scroll.bbox("all")))

        self.status = tk.Label(
            self.frame, text="Analisi in corso…",
            bg="#0a0a0a", fg="#aaaaaa",
            font=("Segoe UI", 10)
        )
        self.status.pack(anchor="w", pady=(12, 6))

        self.preview_frame = tk.Frame(self.frame, bg="#121212", highlightbackground="#333333", highlightthickness=1)
        self.preview_frame.pack(fill="x", pady=(0, 10))

        self.preview_label = tk.Label(self.preview_frame, bg="#121212")
        self.preview_label.pack(pady=8)

        self.preview_title = tk.Label(
            self.preview_frame, text="Selezione",
            bg="#121212", fg="#666666", font=("Segoe UI", 9)
        )
        self.preview_title.pack(pady=(0, 8))

        self.show_preview()

        self.chips_frame = tk.Frame(self.frame, bg="#0a0a0a")
        self.chips_frame.pack(fill="x")

        self.custom_frame = tk.Frame(self.frame, bg="#0a0a0a")
        self.custom_frame.pack(fill="x", pady=(16, 0))

        tk.Button(
            self.chips_frame,
            text="Chiudi",
            bg="#0a0a0a",
            fg="#666666",
            bd=0,
            font=("Segoe UI", 9),
            cursor="hand2",
            command=self.close,
        ).pack(pady=(18, 0))

        self.footer = tk.Frame(self.win, bg="#121212", height=56)
        self.footer.pack(fill="x", side="bottom")
        self.footer.pack_propagate(False)

        self.prompt_entry = tk.Entry(
            self.footer,
            bg="#1a1a1a",
            fg="#ffffff",
            insertbackground="#00ff88",
            bd=0,
            highlightbackground="#333333",
            highlightthickness=1,
            font=("Segoe UI", 10),
        )
        self.prompt_entry.pack(side="left", padx=(16, 8), pady=12, fill="x", expand=True)
        self.prompt_entry.bind("<Return>", lambda e: self.send_custom_prompt())

        self.send_btn = tk.Button(
            self.footer,
            text="Invia",
            bg="#00ff88",
            fg="#000000",
            activebackground="#33ffaa",
            activeforeground="#000000",
            bd=0,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            command=self.send_custom_prompt,
        )
        self.send_btn.pack(side="right", padx=(0, 16), pady=12)

    def send_custom_prompt(self):
        text = self.prompt_entry.get().strip()
        if not text or not self.client:
            return
        self.prompt_entry.delete(0, "end")
        self.send_btn.configure(state="disabled", text="Invio…")

        bubble = tk.Label(
            self.custom_frame,
            text=f"Tu: {text}",
            bg="#1a1a1a",
            fg="#00ff88",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
            justify="left",
            wraplength=420,
        )
        bubble.pack(fill="x", pady=(4, 2), padx=2)

        resp_label = tk.Label(
            self.custom_frame,
            text="…",
            bg="#121212",
            fg="#cccccc",
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=420,
        )
        resp_label.pack(fill="x", pady=(0, 8), padx=2)

        threading.Thread(target=self.ask_custom, args=(text, resp_label), daemon=True).start()

    def ask_custom(self, user_prompt, resp_label):
        buf = io.BytesIO()
        self.img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": user_prompt,
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{b64}"},
                            },
                        ],
                    }
                ],
                max_tokens=300,
                temperature=0.6,
            )
            answer = completion.choices[0].message.content.strip()
            self.root.after(0, lambda: resp_label.configure(text=answer))
        except Exception as e:
            self.root.after(0, lambda: resp_label.configure(text=f"Errore Groq: {e}"))
        finally:
            self.root.after(0, lambda: self.send_btn.configure(state="normal", text="Invia"))

    def fade_in(self):
        try:
            alpha = self.win.attributes("-alpha")
        except tk.TclError:
            return
        if alpha < 1.0:
            self.win.attributes("-alpha", min(1.0, alpha + 0.07))
            self.win.after(20, self.fade_in)

    def fetch_suggestions(self):
        if not self.client:
            self.root.after(0, lambda: self.show_result(["Inserisci GROQ_API_KEY nel file .env"]))
            return

        buf = io.BytesIO()
        self.img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Analizza l'area dello schermo selezionata. Genera fino a 3 suggerimenti brevi (chip) su azioni che l'utente potrebbe voler fare. Rispondi solo con i testi, uno per riga. Nessuna spiegazione, nessun numero, nessun simbolo."
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{b64}"},
                            },
                        ],
                    }
                ],
                max_tokens=150,
                temperature=0.6,
            )
            text = completion.choices[0].message.content.strip()
            suggestions = [s.strip() for s in text.split("\n") if s.strip()][:3]
            if not suggestions:
                suggestions = ["Nessun suggerimento rilevato"]
            self.root.after(0, lambda: self.show_result(suggestions))
        except Exception as e:
            self.root.after(0, lambda: self.show_result([f"Errore Groq: {e}"]))

    def show_result(self, suggestions):
        self.status.destroy()
        for s in suggestions:
            chip = tk.Button(
                self.chips_frame,
                text=s,
                bg="#1a1a1a",
                fg="#ffffff",
                activebackground="#242424",
                activeforeground="#ffffff",
                bd=0,
                highlightthickness=0,
                font=("Segoe UI", 10),
                padx=16,
                pady=12,
                cursor="hand2",
                anchor="w",
                justify="left",
                wraplength=400,
                command=lambda val=s: self.copy_text(val),
            )
            chip.pack(fill="x", pady=7, padx=2)
            chip.bind("<Enter>", lambda e, b=chip: b.configure(bg="#242424"))
            chip.bind("<Leave>", lambda e, b=chip: b.configure(bg="#1a1a1a"))

    def copy_text(self, text):
        try:
            self.win.clipboard_clear()
            self.win.clipboard_append(text)
        except Exception:
            pass

    def close(self):
        if self.win and self.win.winfo_exists():
            self.win.destroy()
        self.on_close()


if __name__ == "__main__":
    MagicPointer().run()
