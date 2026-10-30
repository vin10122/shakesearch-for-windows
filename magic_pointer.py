import os
import sys
import time
import math
import threading
import base64
import io
import subprocess
import ctypes
import warnings

# Sopprime warning di deprecazione interni delle librerie (es. httpx URL.raw)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
from dotenv import load_dotenv
from pynput import mouse, keyboard
from mss import MSS
from PIL import Image, ImageEnhance, ImageTk, ImageDraw
import tkinter as tk

# DPI awareness su Windows
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

load_dotenv()

SHAKE_DISTANCE_THRESHOLD = 300
SHAKE_TIME_WINDOW = 0.55
SHAKE_MIN_REVERSALS = 4
SHAKE_DEBOUNCE = 0.8

COLOR_AMBER = "#ff944d"


def get_current_mouse_pos():
    pt = (ctypes.c_long * 2)()
    ctypes.windll.user32.GetCursorPos(pt)
    return pt[0], pt[1]


def get_monitor_work_area(x, y):
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("rcMonitor", ctypes.c_long * 4),
            ("rcWork", ctypes.c_long * 4),
            ("dwFlags", ctypes.c_ulong)
        ]

    pt = POINT(x, y)
    h_mon = ctypes.windll.user32.MonitorFromPoint(pt, 2)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    if ctypes.windll.user32.GetMonitorInfoW(h_mon, ctypes.byref(mi)):
        w = mi.rcWork
        return (w[0], w[1], w[2], w[3])
    return None


class MagicPointer:
    def __init__(self):
        self.positions = []
        self.last_shake = 0
        self.root = tk.Tk()
        self.root.withdraw()

        self.mouse_listener = None
        self.hotkey_listener = None
        self.multi_overlay = None

    def detect_shake(self, x, y):
        now = time.time()
        self.positions.append((x, y, now))
        cutoff = now - SHAKE_TIME_WINDOW
        self.positions = [(px, py, pt) for px, py, pt in self.positions if pt > cutoff]

        if len(self.positions) < 6:
            return False

        total_distance = sum(
            math.hypot(self.positions[i][0] - self.positions[i - 1][0],
                       self.positions[i][1] - self.positions[i - 1][1])
            for i in range(1, len(self.positions))
        )
        if total_distance < SHAKE_DISTANCE_THRESHOLD:
            return False

        dx_signs = []
        dy_signs = []
        for i in range(1, len(self.positions)):
            dx = self.positions[i][0] - self.positions[i - 1][0]
            dy = self.positions[i][1] - self.positions[i - 1][1]
            if abs(dx) > 12:
                dx_signs.append(1 if dx > 0 else -1)
            if abs(dy) > 12:
                dy_signs.append(1 if dy > 0 else -1)

        x_reversals = sum(1 for i in range(1, len(dx_signs)) if dx_signs[i] != dx_signs[i - 1])
        y_reversals = sum(1 for i in range(1, len(dy_signs)) if dy_signs[i] != dy_signs[i - 1])

        if (x_reversals >= SHAKE_MIN_REVERSALS or y_reversals >= SHAKE_MIN_REVERSALS):
            if now - self.last_shake > SHAKE_DEBOUNCE:
                self.last_shake = now
                self.positions = []
                print("[Magic Pointer] Shake rilevato!")
                return True

        return False

    def on_move(self, x, y):
        if self.multi_overlay:
            return
        if self.detect_shake(x, y):
            self.root.after(0, self.trigger_capture)

    def on_hotkey_triggered(self):
        print("[Magic Pointer] Scorciatoia Alt+F7 premuta!")
        self.root.after(0, self.trigger_capture)

    def trigger_capture(self):
        if self.multi_overlay:
            return

        screen_data = self.capture_all_screens()
        self.multi_overlay = MultiScreenOverlayManager(
            self.root,
            screen_data,
            self.on_session_finished
        )

    def capture_all_screens(self):
        results = []
        with MSS() as sct:
            for i, mon in enumerate(sct.monitors[1:], start=1):
                shot = sct.grab(mon)
                img = Image.frombytes("RGB", shot.size, shot.rgb)
                results.append({
                    "id": i,
                    "rect": (mon["left"], mon["top"], mon["width"], mon["height"]),
                    "image": img
                })
        return results

    def on_session_finished(self):
        self.multi_overlay = None

    def run(self):
        self.mouse_listener = mouse.Listener(on_move=self.on_move)
        self.mouse_listener.daemon = True
        self.mouse_listener.start()

        self.hotkey_listener = keyboard.GlobalHotKeys({
            '<alt>+<f7>': self.on_hotkey_triggered
        })
        self.hotkey_listener.daemon = True
        self.hotkey_listener.start()

        print("[Magic Pointer] Attivo! Premi Alt + F7 o scuoti il mouse.")
        self.root.mainloop()


class MultiScreenOverlayManager:
    def __init__(self, root, screen_data, on_finish):
        self.root = root
        self.screen_data = screen_data
        self.on_finish = on_finish
        self.overlays = []
        self.selection_done = False

        cur_x, cur_y = get_current_mouse_pos()
        self.target_screen = screen_data[0]
        for s in screen_data:
            sl, st, sw, sh = s["rect"]
            if sl <= cur_x < sl + sw and st <= cur_y < st + sh:
                self.target_screen = s
                break

        self.work_area = get_monitor_work_area(cur_x, cur_y)

        for data in screen_data:
            overlay = AnimatedScreenOverlay(self.root, data, self)
            self.overlays.append(overlay)

    def on_confirm_crop(self, cropped_img):
        """Chiamato solo dopo la conferma con INVIO."""
        if self.selection_done:
            return
        self.selection_done = True
        self.close_overlays()

        # Salva l'immagine ritagliata confermata
        temp_img_path = os.path.join(os.environ.get("TEMP", "."), "cts_selection.png")
        cropped_img.save(temp_img_path, format="PNG")

        s_left, s_top, s_width, s_height = self.target_screen["rect"]
        if self.work_area:
            w_left, w_top, w_right, w_bottom = self.work_area
            bottom_limit = w_bottom
        else:
            bottom_limit = s_top + s_height - 48

        target_w = min(560, s_width - 80)
        center_x = s_left + (s_width - target_w) // 2
        expanded_h = min(680, int((bottom_limit - s_top) * 0.82))
        pos_y = bottom_limit - expanded_h - 14

        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drawer_webview.py")
        cmd = [
            sys.executable,
            script_path,
            temp_img_path,
            str(center_x),
            str(pos_y),
            str(target_w),
            str(expanded_h)
        ]
        subprocess.Popen(cmd)
        self.on_finish()

    def cancel(self):
        self.close_all()

    def close_overlays(self):
        for o in self.overlays:
            try:
                o.destroy()
            except Exception:
                pass
        self.overlays.clear()

    def close_all(self):
        self.close_overlays()
        self.on_finish()


class AnimatedScreenOverlay:
    """
    Overlay di cattura:
    - Sfondo con trasparenza scura colorata di arancione tenue
    - Mostra il rettangolo di selezione al rilascio del cerchiamento
    - Modalità conferma: Invio per procedere, Esc per cancellare o riprovare
    """
    def __init__(self, root, screen_dict, manager):
        self.root = root
        self.manager = manager
        self.screen_img = screen_dict["image"]
        self.rect = screen_dict["rect"]
        left, top, width, height = self.rect

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.geometry(f"{width}x{height}+{left}+{top}")
        self.win.attributes("-topmost", True)
        self.win.configure(bg="#000000", cursor="crosshair")

        self.width = width
        self.height = height

        self.canvas = tk.Canvas(self.win, highlightthickness=0, bg="#000000", cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

        self.prepare_visuals()

        self.points = []
        self.is_drawing = False
        self.pending_crop = None
        self.pending_bbox = None

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        # Tasti di conferma e annullamento
        self.win.bind("<Return>", self.on_key_enter)
        self.win.bind("<KP_Enter>", self.on_key_enter)
        self.win.bind("<Escape>", self.on_key_escape)

    def prepare_visuals(self):
        margin = 16
        target_w = max(100, self.width - (margin * 2))
        target_h = max(100, self.height - (margin * 2))

        # Tonalità con trasparenza calda arancione tenue (nessun gradiente aggressivo)
        shrunk = self.screen_img.resize((target_w, target_h), Image.Resampling.BILINEAR)
        dimmed = ImageEnhance.Brightness(shrunk).enhance(0.70)

        # Sovrapposizione velatura arancione tenue
        tint = Image.new("RGBA", (target_w, target_h), (255, 140, 50, 26))
        dimmed_rgba = dimmed.convert("RGBA")
        blended = Image.alpha_composite(dimmed_rgba, tint).convert("RGB")
        self.bg_photo = ImageTk.PhotoImage(blended)

        self.canvas.create_image(margin, margin, image=self.bg_photo, anchor="nw")

        # Bordo perimetrale pulito arancione
        self.canvas.create_rectangle(
            margin - 1, margin - 1,
            self.width - margin + 1, self.height - margin + 1,
            outline=COLOR_AMBER, width=2
        )

        self.header_text = self.canvas.create_text(
            self.width // 2,
            38,
            text="✨ Cerchia qualsiasi cosa  •  Esc per uscire",
            fill="#ffffff",
            font=("Segoe UI", 12, "bold")
        )

    def on_press(self, e):
        # Se era già presente una selezione da confermare, un nuovo click la cancella per rifarla
        if self.pending_crop:
            self.clear_selection_preview()

        margin = 16
        if margin <= e.x <= self.width - margin and margin <= e.y <= self.height - margin:
            self.is_drawing = True
            self.points = [(e.x, e.y)]
            self.canvas.delete("trail")
            self.canvas.delete("glow")

    def on_drag(self, e):
        if not self.is_drawing:
            return
        prev_x, prev_y = self.points[-1]
        dist = math.hypot(e.x - prev_x, e.y - prev_y)
        if dist > 3:
            self.points.append((e.x, e.y))
            # Tracciamento pulito arancione
            self.canvas.create_line(
                prev_x, prev_y, e.x, e.y,
                fill=COLOR_AMBER, width=6, capstyle="round", smooth=True, tags="glow"
            )
            self.canvas.create_line(
                prev_x, prev_y, e.x, e.y,
                fill="#ffffff", width=2, capstyle="round", smooth=True, tags="trail"
            )

    def on_release(self, e):
        if not self.is_drawing or len(self.points) < 5:
            self.is_drawing = False
            return

        self.is_drawing = False
        margin = 16

        # Calcola le coordinate min/max disegnate
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]

        disp_min_x, disp_max_x = max(margin, min(xs)), min(self.width - margin, max(xs))
        disp_min_y, disp_max_y = max(margin, min(ys)), min(self.height - margin, max(ys))

        if (disp_max_x - disp_min_x) < 25 or (disp_max_y - disp_min_y) < 25:
            self.canvas.delete("trail")
            self.canvas.delete("glow")
            return

        # Coordinate mappate all'immagine originale ad alta risoluzione
        scale_x = self.screen_img.width / float(self.width - (margin * 2))
        scale_y = self.screen_img.height / float(self.height - (margin * 2))

        orig_min_x = max(0, (disp_min_x - margin) * scale_x)
        orig_max_x = min(self.screen_img.width, (disp_max_x - margin) * scale_x)
        orig_min_y = max(0, (disp_min_y - margin) * scale_y)
        orig_max_y = min(self.screen_img.height, (disp_max_y - margin) * scale_y)

        cropped = self.screen_img.crop((int(orig_min_x), int(orig_min_y), int(orig_max_x), int(orig_max_y)))
        self.pending_crop = cropped
        self.pending_bbox = (disp_min_x, disp_min_y, disp_max_x, disp_max_y)

        # Mostra rettangolo di selezione in evidenza con badge di conferma
        self.show_selection_preview(disp_min_x, disp_min_y, disp_max_x, disp_max_y)

    def show_selection_preview(self, x1, y1, x2, y2):
        self.canvas.delete("selection_box")

        # Bordo rettangolare tratteggiato in evidenza
        self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline=COLOR_AMBER, width=3, dash=(6, 4), tags="selection_box"
        )
        self.canvas.create_rectangle(
            x1 - 1, y1 - 1, x2 + 1, y2 + 1,
            outline="#ffffff", width=1, tags="selection_box"
        )

        # Badge con istruzioni sotto o sopra il rettangolo
        badge_y = y2 + 26 if y2 + 50 < self.height else y1 - 26
        badge_x = (x1 + x2) // 2

        self.canvas.create_rectangle(
            badge_x - 170, badge_y - 16, badge_x + 170, badge_y + 16,
            fill="#1f1814", outline=COLOR_AMBER, width=2, tags="selection_box"
        )
        self.canvas.create_text(
            badge_x, badge_y,
            text="Premi INVIO per confermare  •  ESC per riprovare",
            fill="#ffffff", font=("Segoe UI", 10, "bold"), tags="selection_box"
        )

    def clear_selection_preview(self):
        self.pending_crop = None
        self.pending_bbox = None
        self.canvas.delete("selection_box")
        self.canvas.delete("trail")
        self.canvas.delete("glow")

    def on_key_enter(self, event=None):
        if self.pending_crop:
            self.manager.on_confirm_crop(self.pending_crop)

    def on_key_escape(self, event=None):
        # Se c'è una selezione attiva, il primo ESC la resetta per farti riprovare
        if self.pending_crop:
            self.clear_selection_preview()
        else:
            self.manager.cancel()

    def destroy(self):
        if self.win and self.win.winfo_exists():
            self.win.destroy()


if __name__ == "__main__":
    MagicPointer().run()
