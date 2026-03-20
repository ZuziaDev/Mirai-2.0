import json
import math
import os
import random
import sys
import time
import tkinter as tk
from collections import deque
from pathlib import Path
from queue import Empty, SimpleQueue
from tkinter import messagebox


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR = get_base_dir()
VAULT_DIR = BASE_DIR / "security_vault"
API_FILE = VAULT_DIR / "access.json"

SYSTEM_NAME = "MIRAI // NEURAL CONTROL"
MODEL_BADGE = "VOICE · MEMORY · TOOLS · AUTONOMY"

C_BG = "#040813"
C_BG_2 = "#091225"
C_PANEL = "#0b1426"
C_PANEL_ALT = "#101a31"
C_PANEL_SOFT = "#0f1d39"
C_GRID = "#13233f"
C_PRIMARY = "#74f0ff"
C_SECONDARY = "#7d78ff"
C_TEAL = "#2fd0c8"
C_TEXT = "#eef6ff"
C_MUTED = "#7e95b8"
C_MUTED_2 = "#5d7296"
C_ALERT = "#ff6f91"
C_WARN = "#ffd166"
C_SUCCESS = "#5ff2bb"
C_LOG_BG = "#07111d"
C_LOG_EDGE = "#1f3b58"
C_SHADOW = "#050910"
C_USER = "#ffd166"
C_AI = "#74f0ff"
C_SYS = "#ff9e7a"
KNOWLEDGE_FILE = BASE_DIR / "neural_store" / "knowledge_memory.json"
QUEUE_FILE = VAULT_DIR / "task_queue.json"


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _mix(c1: str, c2: str, ratio: float) -> str:
    ratio = max(0.0, min(1.0, ratio))
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex(
        (
            int(r1 + (r2 - r1) * ratio),
            int(g1 + (g2 - g1) * ratio),
            int(b1 + (b2 - b1) * ratio),
        )
    )


class MiraiUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(SYSTEM_NAME)
        self.root.resizable(False, False)

        self.W, self.H = 1440, 980
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{self.W}x{self.H}+{(sw-self.W)//2}+{(sh-self.H)//2}")
        self.root.configure(bg=C_BG)

        self.tick = 0
        self.core_phase = 0.0
        self.core_activity = 0.0
        self.frame_ms = 40
        self.session_start = time.time()
        self.speaking = False
        self.status_text = "VOICE LINK STANDBY"
        self.mode_text = "AUTONOMOUS"
        self.visual_status = "AWARE"
        self.health_status = "STABLE"
        self.alert_text = ""
        self.alert_until = 0.0
        self.log_count = 0
        self.typing_queue = deque()
        self.pending_logs = SimpleQueue()
        self.pending_events = SimpleQueue()
        self.current_typing = None
        self._typing_job = None
        self._animation_job = None
        self._stream_finish_job = None
        self._running = True
        self.engine_started = False
        self.stream_text = "idle / waiting for response"
        self.stream_mode = "IDLE"
        self._badge_state = None
        self.recent_events = deque(maxlen=6)
        self.signal_history = deque([0.12] * 56, maxlen=56)
        self.last_user_text = "No operator prompt yet."
        self.last_neural_text = "Neural channel is waiting for first signal."
        self._api_key_ready = False
        self.knowledge_count = 0
        self.queue_depth = 0
        self._knowledge_mtime = None
        self._queue_mtime = None
        self._next_stats_refresh = 0.0

        self.particles = self._build_particles()
        self.penta_nodes, self.penta_edges = self._build_penta_lattice()

        self.canvas = tk.Canvas(
            self.root,
            width=self.W,
            height=self.H,
            bg=C_BG,
            highlightthickness=0,
        )
        self.canvas.place(x=0, y=0)

        self._build_terminal()

        if API_FILE.exists():
            try:
                with open(API_FILE, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                    if data.get("gemini_api_key"):
                        self._api_key_ready = True
            except Exception:
                pass

        self._push_recent_event("SYSTEM", "Mirai arayuzu hazirlandi.")

        if not self._api_key_ready:
            self.root.withdraw()
            self._show_setup_ui()
        else:
            self._start_engine()

    def _build_particles(self) -> list[dict]:
        rng = random.Random(42)
        items = []
        for _ in range(48):
            items.append(
                {
                    "x": rng.randint(40, self.W - 40),
                    "y": rng.randint(50, self.H - 260),
                    "r": rng.randint(1, 2),
                    "speed": rng.uniform(0.4, 1.4),
                    "phase": rng.uniform(0, math.tau),
                    "color": rng.choice([C_PRIMARY, C_SECONDARY, C_TEAL]),
                }
            )
        return items

    def _build_penta_lattice(self) -> tuple[list[tuple[float, float, float, float, float, float, float]], list[tuple[int, int]]]:
        nodes = []
        for index in range(5):
            angle = -math.pi / 2 + index * (math.tau / 5)
            nodes.append(
                (
                    math.cos(angle) * 1.06,
                    math.sin(angle) * 0.92,
                    0.94,
                    math.cos(angle * 2.0) * 0.34,
                    math.sin(angle * 2.0) * 0.26,
                    math.cos(angle * 3.0) * 0.18,
                    math.sin(angle * 5.0) * 0.14,
                )
            )

        for index in range(5):
            angle = -math.pi / 2 + index * (math.tau / 5) + 0.26
            nodes.append(
                (
                    math.cos(angle) * 1.00,
                    math.sin(angle) * 0.88,
                    -0.96,
                    math.cos(angle * 2.0 + 0.4) * 0.30,
                    math.sin(angle * 2.0 + 0.4) * 0.22,
                    math.cos(angle * 3.0 - 0.25) * 0.16,
                    math.sin(angle * 5.0) * 0.12,
                )
            )

        nodes.append((0.0, 0.0, 0.0, 0.18, -0.12, 0.10, 0.16))

        edges = set()
        for index in range(5):
            front = index
            back = 5 + index
            next_front = (index + 1) % 5
            next_back = 5 + ((index + 1) % 5)
            star_front = (index + 2) % 5
            star_back = 5 + ((index + 2) % 5)

            edges.add(tuple(sorted((front, next_front))))
            edges.add(tuple(sorted((back, next_back))))
            edges.add(tuple(sorted((front, back))))
            edges.add(tuple(sorted((front, star_front))))
            edges.add(tuple(sorted((back, star_back))))
            edges.add(tuple(sorted((front, next_back))))
            edges.add(tuple(sorted((back, next_front))))
            edges.add(tuple(sorted((front, 10))))
            edges.add(tuple(sorted((back, 10))))

        return nodes, sorted(edges)

    def _rotate_pair(self, coords, first: int, second: int, angle: float):
        values = list(coords)
        sin_a = math.sin(angle)
        cos_a = math.cos(angle)
        a_val = values[first]
        b_val = values[second]
        values[first] = a_val * cos_a - b_val * sin_a
        values[second] = a_val * sin_a + b_val * cos_a
        return values

    def _regular_polygon_points(self, cx: float, cy: float, sides: int, radius_x: float, radius_y: float, rotation: float = 0.0) -> list[float]:
        points = []
        for index in range(sides):
            angle = rotation - math.pi / 2 + index * (math.tau / sides)
            points.extend(
                [
                    cx + math.cos(angle) * radius_x,
                    cy + math.sin(angle) * radius_y,
                ]
            )
        return points

    def _project_globe_point(self, x: float, y: float, z: float, cx: float, cy: float, rx: float, ry: float, yaw: float, pitch: float) -> dict:
        cos_yaw = math.cos(yaw)
        sin_yaw = math.sin(yaw)
        xz_x = x * cos_yaw - z * sin_yaw
        xz_z = x * sin_yaw + z * cos_yaw

        cos_pitch = math.cos(pitch)
        sin_pitch = math.sin(pitch)
        yz_y = y * cos_pitch - xz_z * sin_pitch
        yz_z = y * sin_pitch + xz_z * cos_pitch

        perspective = 3.1 / (4.1 - yz_z)
        return {
            "x": cx + xz_x * rx * perspective,
            "y": cy + yz_y * ry * perspective,
            "z": yz_z,
        }

    def _draw_globe_path(self, points: list[dict], front_color: str, back_color: str, front_width: int = 2, back_width: int = 1, closed: bool = False):
        if len(points) < 2:
            return

        limit = len(points) if closed else len(points) - 1
        for index in range(limit):
            first = points[index]
            second = points[(index + 1) % len(points)]
            avg_z = (first["z"] + second["z"]) / 2.0
            color = front_color if avg_z >= 0 else back_color
            width = front_width if avg_z >= 0 else back_width
            self.canvas.create_line(first["x"], first["y"], second["x"], second["y"], fill=color, width=width)

    def _neural_activity_strength(self) -> float:
        activity = 0.18 + max(self.signal_history, default=0.0) * 0.22
        if self._has_open_stream():
            activity += 0.46
        if self.speaking:
            activity += 0.56
        if self.stream_mode == "BUFFER":
            activity += 0.12
        return max(0.18, min(1.34, activity))

    def _project_seven_dim_vertex(
        self,
        vertex: tuple[float, float, float, float, float, float, float],
        t: float,
        cx: float,
        cy: float,
        scale: float,
        activity: float,
    ) -> dict:
        coords = list(vertex)
        x3, y3, z3 = coords[0], coords[1], coords[2]
        for dim_index, perspective in ((6, 4.95), (5, 4.8), (4, 4.62), (3, 4.44)):
            depth = perspective / (perspective - coords[dim_index] * 0.92)
            x3 *= depth
            y3 *= depth
            z3 *= depth

        vec3 = [x3, y3, z3]
        vec3 = self._rotate_pair(vec3, 0, 2, -0.36)
        vec3 = self._rotate_pair(vec3, 1, 2, 0.24)

        z_depth = 4.4 / (5.8 - vec3[2])
        x2 = cx + vec3[0] * z_depth * scale
        y2 = cy + vec3[1] * z_depth * scale
        return {
            "x": x2,
            "y": y2,
            "depth": z_depth,
            "phase": 0.5 + 0.5 * math.sin(t * 0.055 + coords[6] * 2.8),
            "tilt": coords[3],
            "z": vec3[2],
        }

    def _build_terminal(self):
        self.log_frame = tk.Frame(
            self.root,
            bg=C_PANEL_ALT,
            highlightbackground=C_LOG_EDGE,
            highlightthickness=1,
            bd=0,
        )
        self.log_header = tk.Frame(self.log_frame, bg=C_PANEL, height=42)
        self.log_header.pack(fill="x")
        title_stack = tk.Frame(self.log_header, bg=C_PANEL)
        title_stack.pack(side="left", padx=14, pady=6)
        self.log_title = tk.Label(
            title_stack,
            text="LIVE CONVERSATION",
            fg=C_TEXT,
            bg=C_PANEL,
            font=("Bahnschrift SemiBold", 12),
            anchor="w",
        )
        self.log_title.pack(anchor="w")
        self.log_subtitle = tk.Label(
            title_stack,
            text="incremental response rendering / low-latency ui queue",
            fg=C_MUTED,
            bg=C_PANEL,
            font=("Consolas", 8),
            anchor="w",
        )
        self.log_subtitle.pack(anchor="w")
        self.log_badge = tk.Label(
            self.log_header,
            text="IDLE",
            fg=C_BG,
            bg=C_SUCCESS,
            font=("Bahnschrift SemiBold", 9),
            padx=8,
            pady=2,
        )
        self.log_badge.pack(side="right", padx=12, pady=8)

        body = tk.Frame(self.log_frame, bg=C_LOG_BG)
        body.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            body,
            bg=C_LOG_BG,
            fg=C_TEXT,
            font=("Segoe UI", 12),
            borderwidth=0,
            padx=20,
            pady=18,
            wrap="word",
            insertbackground=C_PRIMARY,
            insertwidth=0,
            cursor="arrow",
            takefocus=0,
            undo=False,
            spacing1=3,
            spacing2=2,
            spacing3=3,
        )
        self.log_scroll = tk.Scrollbar(body, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=self.log_scroll.set, state="disabled")
        self.log_text.pack(side="left", fill="both", expand=True)
        self.log_scroll.pack(side="right", fill="y")

        self.log_text.tag_config("default", foreground=C_TEXT)
        self.log_text.tag_config("spacer", foreground=C_TEXT, font=("Segoe UI", 7))
        self.log_text.tag_config(
            "user_label",
            foreground=_mix(C_USER, C_TEXT, 0.4),
            font=("Bahnschrift SemiBold", 9),
            spacing1=14,
            spacing3=2,
        )
        self.log_text.tag_config(
            "user_body",
            foreground=C_TEXT,
            background=_mix(C_LOG_BG, C_USER, 0.11),
            font=("Segoe UI Semibold", 13),
            lmargin1=18,
            lmargin2=18,
            rmargin=260,
            spacing1=0,
            spacing2=3,
            spacing3=10,
        )
        self.log_text.tag_config(
            "neural_label",
            foreground=_mix(C_PRIMARY, C_TEXT, 0.35),
            font=("Bahnschrift SemiBold", 9),
            spacing1=14,
            spacing3=2,
        )
        self.log_text.tag_config(
            "neural_body",
            foreground=C_TEXT,
            background=_mix(C_LOG_BG, C_PRIMARY, 0.13),
            font=("Segoe UI", 13),
            lmargin1=18,
            lmargin2=18,
            rmargin=140,
            spacing1=0,
            spacing2=3,
            spacing3=10,
        )
        self.log_text.tag_config(
            "system_label",
            foreground=_mix(C_SYS, C_TEXT, 0.42),
            font=("Bahnschrift SemiBold", 9),
            spacing1=12,
            spacing3=2,
        )
        self.log_text.tag_config(
            "system_body",
            foreground=_mix(C_TEXT, C_SYS, 0.12),
            background=_mix(C_LOG_BG, C_SYS, 0.08),
            font=("Segoe UI", 11),
            lmargin1=18,
            lmargin2=18,
            rmargin=120,
            spacing3=8,
        )
        self.log_text.tag_config(
            "tool_label",
            foreground=_mix(C_TEAL, C_TEXT, 0.35),
            font=("Bahnschrift SemiBold", 9),
            spacing1=12,
            spacing3=2,
        )
        self.log_text.tag_config(
            "tool_body",
            foreground=C_TEAL,
            background=_mix(C_LOG_BG, C_TEAL, 0.08),
            font=("Consolas", 10),
            lmargin1=18,
            lmargin2=18,
            rmargin=90,
            spacing3=8,
        )

    def _start_engine(self):
        if self.engine_started:
            self.root.deiconify()
            return

        self.engine_started = True
        self.root.deiconify()
        self._place_widgets()
        self._refresh_external_stats()
        self._animate()
        self.root.protocol("WM_DELETE_WINDOW", self._shutdown)

    def _place_widgets(self):
        self.log_frame.place(x=38, y=742, width=self.W - 76, height=188)

    def _animate(self):
        if not self._running:
            return

        self.tick += 1
        self._drain_ui_events()
        self._drain_pending_logs()
        self._ensure_typing()
        self._update_signal_history()
        self.core_activity = self._neural_activity_strength()
        self.core_phase += 0.42 + self.core_activity * 1.05
        now = time.time()
        if now >= self._next_stats_refresh:
            self._refresh_external_stats()
            self._next_stats_refresh = now + 2.5
        if self.alert_text and time.time() > self.alert_until:
            self.alert_text = ""
        self._update_terminal_badge()
        self._draw()
        self._animation_job = self.root.after(self.frame_ms, self._animate)

    def _refresh_external_stats(self):
        try:
            if KNOWLEDGE_FILE.exists():
                mtime = KNOWLEDGE_FILE.stat().st_mtime_ns
                if mtime != self._knowledge_mtime:
                    self._knowledge_mtime = mtime
                    data = json.loads(KNOWLEDGE_FILE.read_text(encoding="utf-8"))
                    self.knowledge_count = len(data) if isinstance(data, list) else 0
            else:
                self.knowledge_count = 0
                self._knowledge_mtime = None
        except Exception:
            self.knowledge_count = 0
            self._knowledge_mtime = None

        try:
            if QUEUE_FILE.exists():
                mtime = QUEUE_FILE.stat().st_mtime_ns
                if mtime != self._queue_mtime:
                    self._queue_mtime = mtime
                    data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
                    self.queue_depth = len(
                        [
                            item
                            for item in data
                            if isinstance(item, dict) and item.get("status") == "queued"
                        ]
                    )
            else:
                self.queue_depth = 0
                self._queue_mtime = None
        except Exception:
            self.queue_depth = 0
            self._queue_mtime = None

    def _update_signal_history(self):
        if self.speaking:
            level = 0.55 + random.random() * 0.45
        else:
            wave = 0.08 + (math.sin(self.tick * 0.09) + 1.0) * 0.04
            level = wave + random.random() * 0.04
        self.signal_history.append(max(0.02, min(1.0, level)))

    def _draw(self):
        c = self.canvas
        c.delete("all")

        self._draw_background()
        self._draw_header()
        self._draw_left_panels()
        self._draw_right_panels()
        self._draw_core()
        self._draw_terminal_overlay()
        self._draw_footer()

    def _draw_background(self):
        c = self.canvas
        stripe_h = 14
        for y in range(0, self.H, stripe_h):
            ratio = y / max(1, self.H)
            color = _mix(C_BG, C_BG_2, 0.15 + ratio * 0.85)
            c.create_rectangle(0, y, self.W, y + stripe_h + 1, fill=color, outline="")

        for x in range(0, self.W + 1, 64):
            c.create_line(x, 0, x, self.H, fill=C_GRID, width=1)
        for y in range(0, self.H + 1, 64):
            c.create_line(0, y, self.W, y, fill=C_GRID, width=1)

        for x in range(-self.H, self.W, 120):
            c.create_line(x, 0, x + self.H * 0.38, self.H, fill=_mix(C_BG_2, C_GRID, 0.4), width=1)

        c.create_oval(260, 84, 920, 740, fill="", outline=_mix(C_BG_2, C_PRIMARY, 0.08), width=30)
        c.create_oval(self.W - 920, 120, self.W - 180, 860, fill="", outline=_mix(C_BG_2, C_SECONDARY, 0.08), width=26)
        c.create_oval(110, 340, 530, 760, fill="", outline=_mix(C_BG_2, C_TEAL, 0.06), width=18)

        for particle in self.particles:
            drift = math.sin(self.tick * 0.018 * particle["speed"] + particle["phase"]) * 8
            glow = math.sin(self.tick * 0.04 + particle["phase"]) * 0.5 + 0.5
            px = particle["x"]
            py = particle["y"] + drift
            color = _mix(C_BG_2, particle["color"], 0.25 + glow * 0.45)
            r = particle["r"]
            c.create_oval(px - r, py - r, px + r, py + r, fill=color, outline="")

    def _draw_header(self):
        c = self.canvas
        c.create_rectangle(24, 24, self.W - 24, 98, fill=C_PANEL, outline=C_LOG_EDGE, width=1)
        c.create_rectangle(24, 24, self.W - 24, 30, fill=C_PRIMARY, outline="")
        c.create_rectangle(24, 30, self.W - 24, 34, fill=_mix(C_PRIMARY, C_SECONDARY, 0.4), outline="")
        c.create_text(46, 54, text=SYSTEM_NAME, fill=C_TEXT, font=("Bahnschrift SemiBold", 24), anchor="w")
        c.create_text(46, 80, text=MODEL_BADGE, fill=C_MUTED, font=("Consolas", 10), anchor="w")
        c.create_text(420, 80, text="adaptive voice shell / embedded memory / live tools", fill=C_MUTED_2, font=("Consolas", 9), anchor="w")

        self._draw_chip(self.W - 522, 44, 132, 28, time.strftime("%H:%M:%S"), C_PRIMARY, C_BG)
        self._draw_chip(self.W - 376, 44, 136, 28, self.mode_text, C_SECONDARY, C_TEXT)
        self._draw_chip(self.W - 222, 44, 158, 28, f"STREAM {self.stream_mode}", C_PANEL_SOFT, C_TEXT)

    def _draw_left_panels(self):
        self._draw_panel(38, 118, 326, 332, "SENSORY HUB", "Core perception state")
        self._draw_status_row(58, 164, "VISION", self.visual_status, self._status_color(self.visual_status))
        self._draw_status_row(58, 202, "HEALTH", self.health_status, self._status_color(self.health_status))
        self._draw_status_row(58, 240, "VOICE", "TRANSMITTING" if self.speaking else "LISTENING", C_SUCCESS if self.speaking else C_PRIMARY)
        self._draw_status_row(58, 278, "MODE", self.mode_text, C_SECONDARY)
        self._draw_metric_bar(58, 304, 220, 12, 0.82 if self.speaking else 0.46, C_PRIMARY)

        self._draw_panel(38, 350, 326, 692, "SESSION MATRIX", "Live operational")
        uptime = self._format_uptime()
        self._draw_metric_block(58, 396, "UPTIME", uptime)
        self._draw_metric_block(58, 460, "EVENTS", str(self.log_count))
        self._draw_metric_block(58, 524, "KNOWLEDGE", str(self.knowledge_count))
        self._draw_metric_block(58, 588, "QUEUE", str(self.queue_depth))

        c = self.canvas
        c.create_text(58, 648, text="LAST OPERATOR SIGNAL", fill=C_MUTED, font=("Consolas", 9), anchor="w")
        c.create_text(
            58,
            670,
            text=self._truncate(self.last_user_text, 36),
            fill=C_TEXT,
            font=("Consolas", 10),
            anchor="w",
        )

    def _draw_right_panels(self):
        self._draw_panel(self.W - 326, 118, self.W - 38, 332, "SIGNAL ANALYZER", "Realtime neural activity")
        self._draw_signal_bars(self.W - 308, 162, self.W - 58, 254)
        self._draw_status_row(self.W - 308, 280, "LINK", "OPEN" if self._api_key_ready else "LOCKED", C_SUCCESS if self._api_key_ready else C_ALERT)
        self._draw_status_row(self.W - 308, 306, "ALERT", "ACTIVE" if self.alert_text else "CLEAR", C_ALERT if self.alert_text else C_SUCCESS)

    def _draw_core(self):
        c = self.canvas
        cx, cy = self.W // 2, 360
        t = self.tick

        globe_rx, globe_ry = 214, 228
        c.create_oval(cx - 308, cy - 270, cx + 308, cy + 270, outline=_mix(C_BG_2, C_PRIMARY, 0.08), width=28)
        c.create_oval(cx - 262, cy - 232, cx + 262, cy + 232, outline=_mix(C_BG_2, C_SECONDARY, 0.12), width=2)
        c.create_oval(cx - globe_rx, cy - globe_ry, cx + globe_rx, cy + globe_ry, outline=_mix(C_PANEL, C_PRIMARY, 0.62), width=2)
        c.create_oval(cx - globe_rx + 22, cy - globe_ry + 28, cx + globe_rx - 32, cy + globe_ry - 20, outline=_mix(C_PANEL, C_TEAL, 0.18), width=1)

        yaw = t * 0.022
        pitch = math.radians(24) + math.sin(t * 0.012) * 0.08

        latitude_colors = [C_SECONDARY, C_PRIMARY, C_TEAL, C_PRIMARY, C_SECONDARY]
        for latitude_index, latitude in enumerate([-60, -30, 0, 30, 60]):
            lat = math.radians(latitude)
            path = []
            for longitude in range(0, 361, 8):
                lon = math.radians(longitude)
                x = math.cos(lat) * math.cos(lon)
                y = math.sin(lat)
                z = math.cos(lat) * math.sin(lon)
                path.append(self._project_globe_point(x, y, z, cx, cy, globe_rx, globe_ry, yaw, pitch))
            color = latitude_colors[latitude_index]
            self._draw_globe_path(
                path,
                front_color=_mix(C_PANEL, color, 0.60),
                back_color=_mix(C_PANEL, color, 0.22),
                front_width=2 if latitude == 0 else 1,
                back_width=1,
            )

        longitude_colors = [C_PRIMARY, C_TEAL, C_SECONDARY, C_TEAL, C_PRIMARY, C_SECONDARY]
        for longitude_index, longitude in enumerate([0, 30, 60, 90, 120, 150]):
            lon = math.radians(longitude)
            path = []
            for latitude in range(-90, 91, 6):
                lat = math.radians(latitude)
                x = math.cos(lat) * math.cos(lon)
                y = math.sin(lat)
                z = math.cos(lat) * math.sin(lon)
                path.append(self._project_globe_point(x, y, z, cx, cy, globe_rx, globe_ry, yaw, pitch))
            color = longitude_colors[longitude_index]
            self._draw_globe_path(
                path,
                front_color=_mix(C_PANEL, color, 0.55),
                back_color=_mix(C_PANEL, color, 0.18),
                front_width=1,
                back_width=1,
            )

        for radius, extent, speed, color in [
            (278, 42, -0.35, C_SECONDARY),
            (238, 118, 0.85, C_PRIMARY),
            (190, 64, -1.2, C_TEAL),
        ]:
            self._draw_arc_ring(cx, cy, radius, t * speed, extent, color, 3)

        inner = 136
        c.create_oval(cx - inner, cy - inner, cx + inner, cy + inner, outline=C_PRIMARY, width=2)
        c.create_oval(cx - 104, cy - 104, cx + 104, cy + 104, outline=C_LOG_EDGE, width=1)
        c.create_oval(cx - 72, cy - 72, cx + 72, cy + 72, outline=_mix(C_PANEL, C_TEAL, 0.45), width=1)

        for angle in range(0, 360, 12):
            ang = math.radians(angle + t * 0.4)
            base = 109
            wave = 18 + (math.sin(t * 0.11 + angle * 0.12) + 1.0) * 10
            if self.speaking:
                wave += random.randint(4, 22)
            x1 = cx + base * math.cos(ang)
            y1 = cy + base * math.sin(ang)
            x2 = cx + (base + wave) * math.cos(ang)
            y2 = cy + (base + wave) * math.sin(ang)
            color = C_ALERT if wave > 36 else C_PRIMARY
            c.create_line(x1, y1, x2, y2, fill=color, width=3)

        for angle in range(0, 360, 30):
            ang = math.radians(angle - t * 0.8)
            x = cx + 166 * math.cos(ang)
            y = cy + 166 * math.sin(ang)
            c.create_text(x, y, text=random.choice(["0", "1", "·"]), fill=C_MUTED, font=("Consolas", 8))

        for orbit_index in range(5):
            ang = math.radians(t * (1.1 + orbit_index * 0.14) + orbit_index * 72)
            point = self._project_globe_point(
                math.cos(ang) * 0.82,
                math.sin(ang * 0.76) * 0.42,
                math.sin(ang) * 0.82,
                cx,
                cy,
                globe_rx,
                globe_ry,
                yaw,
                pitch,
            )
            ox, oy = point["x"], point["y"]
            dot_color = [C_PRIMARY, C_TEAL, C_SECONDARY, C_USER, C_ALERT][orbit_index]
            radius = 5 if point["z"] >= 0 else 3
            fill = dot_color if point["z"] >= 0 else _mix(C_PANEL, dot_color, 0.35)
            c.create_oval(ox - radius, oy - radius, ox + radius, oy + radius, fill=fill, outline="")

        scan_width = 26 + math.sin(t * 0.06) * 10
        c.create_arc(
            cx - 154,
            cy - 154,
            cx + 154,
            cy + 154,
            start=t * 1.4,
            extent=scan_width,
            outline=C_TEAL,
            style="arc",
            width=5,
        )

        c.create_text(cx, cy - 12, text="MIRAI", fill=C_TEXT, font=("Bahnschrift SemiBold", 26))
        c.create_text(cx, cy + 16, text=self.status_text, fill=C_PRIMARY, font=("Consolas", 10, "bold"))
        c.create_text(cx, cy + 38, text="adaptive neural control matrix", fill=C_MUTED, font=("Consolas", 9))

        c.create_text(cx - 242, cy - 212, text="VOICE BUS", fill=C_MUTED, font=("Consolas", 8), anchor="w")
        c.create_line(cx - 190, cy - 210, cx - 116, cy - 126, fill=C_LOG_EDGE)
        c.create_text(cx + 154, cy - 214, text="MEMORY MESH", fill=C_MUTED, font=("Consolas", 8), anchor="w")
        c.create_line(cx + 144, cy - 206, cx + 72, cy - 132, fill=C_LOG_EDGE)
        c.create_text(cx + 196, cy + 188, text="TOOL EXECUTION LANE", fill=C_MUTED, font=("Consolas", 8), anchor="w")
        c.create_line(cx + 144, cy + 170, cx + 72, cy + 102, fill=C_LOG_EDGE)

        if self.alert_text:
            pulse = 0.35 + (math.sin(t * 0.18) + 1.0) * 0.15
            alert_color = _mix(C_PANEL, C_ALERT, pulse)
            c.create_rectangle(392, 520, self.W - 392, 562, fill=alert_color, outline=C_ALERT, width=1)
            c.create_text(self.W // 2, 541, text=f"PROACTIVE ALERT // {self._truncate(self.alert_text, 60)}", fill=C_TEXT, font=("Bahnschrift SemiBold", 11))

    def _draw_terminal_overlay(self):
        c = self.canvas
        c.create_text(48, 720, text="CONVERSATION STREAM", fill=C_TEXT, font=("Bahnschrift SemiBold", 12), anchor="w")
        c.create_text(
            self.W - 48,
            720,
            text=self._truncate(self.stream_text, 66),
            fill=C_MUTED,
            font=("Consolas", 9),
            anchor="e",
        )

    def _draw_footer(self):
        c = self.canvas
        c.create_text(42, self.H - 22, text="NEURAL LINK STATUS", fill=C_MUTED, font=("Consolas", 9), anchor="w")
        self._draw_chip(196, self.H - 36, 132, 24, "READY" if not self.speaking else "RESPONDING", C_SUCCESS if not self.speaking else C_PRIMARY, C_BG)
        self._draw_chip(340, self.H - 36, 160, 24, self.health_status, self._status_color(self.health_status), C_BG)
        self._draw_chip(514, self.H - 36, 128, 24, f"QUEUE {self.queue_depth}", C_PANEL_SOFT, C_TEXT)
        self._draw_chip(self.W - 210, self.H - 36, 170, 24, time.strftime("%d.%m.%Y"), C_PANEL_ALT, C_TEXT)

    def _draw_panel(self, x1, y1, x2, y2, title, subtitle=""):
        c = self.canvas
        c.create_rectangle(x1 + 6, y1 + 8, x2 + 6, y2 + 8, fill=C_SHADOW, outline="")
        c.create_rectangle(x1, y1, x2, y2, fill=C_PANEL, outline=C_LOG_EDGE, width=1)
        c.create_rectangle(x1, y1, x2, y1 + 4, fill=C_PRIMARY, outline="")
        c.create_text(x1 + 18, y1 + 24, text=title, fill=C_TEXT, font=("Bahnschrift SemiBold", 12), anchor="w")
        if subtitle:
            c.create_text(x1 + 18, y1 + 46, text=subtitle, fill=C_MUTED, font=("Consolas", 9), anchor="w")
        c.create_line(x1 + 16, y1 + 62, x2 - 16, y1 + 62, fill=C_LOG_EDGE)

    def _draw_status_row(self, x, y, label, value, color):
        c = self.canvas
        c.create_text(x, y, text=label, fill=C_MUTED, font=("Consolas", 9), anchor="w")
        c.create_text(x + 92, y, text=value, fill=color, font=("Bahnschrift SemiBold", 11), anchor="w")

    def _draw_metric_block(self, x, y, label, value):
        c = self.canvas
        c.create_text(x, y, text=label, fill=C_MUTED, font=("Consolas", 9), anchor="w")
        c.create_text(x, y + 22, text=value, fill=C_TEXT, font=("Bahnschrift SemiBold", 12), anchor="w")
        c.create_line(x, y + 36, 250, y + 36, fill=C_LOG_EDGE)

    def _draw_metric_bar(self, x, y, width, height, value, color):
        value = max(0.0, min(1.0, float(value)))
        self.canvas.create_rectangle(x, y, x + width, y + height, fill=C_PANEL_ALT, outline=C_LOG_EDGE, width=1)
        self.canvas.create_rectangle(x + 2, y + 2, x + 2 + (width - 4) * value, y + height - 2, fill=color, outline="")

    def _draw_signal_bars(self, x1, y1, x2, y2):
        c = self.canvas
        width = x2 - x1
        height = y2 - y1
        bars = list(self.signal_history)[-28:]
        bar_w = width / max(1, len(bars))
        c.create_rectangle(x1, y1, x2, y2, fill=C_PANEL_ALT, outline=C_LOG_EDGE, width=1)

        for idx, level in enumerate(bars):
            px1 = x1 + idx * bar_w + 2
            px2 = px1 + max(3, bar_w - 4)
            bar_h = max(6, height * level)
            py1 = y2 - bar_h
            color = _mix(C_SECONDARY, C_PRIMARY, idx / max(1, len(bars) - 1))
            if level > 0.72:
                color = C_ALERT
            c.create_rectangle(px1, py1, px2, y2 - 2, fill=color, outline="")

        c.create_text(x1 + 10, y1 + 10, text="voice amplitude", fill=C_MUTED, font=("Consolas", 8), anchor="nw")

    def _draw_chip(self, x, y, w, h, text, fill, text_color):
        self.canvas.create_rectangle(x, y, x + w, y + h, fill=fill, outline="", width=0)
        self.canvas.create_text(
            x + w / 2,
            y + h / 2,
            text=text,
            fill=text_color,
            font=("Bahnschrift SemiBold", 10),
        )

    def _draw_arc_ring(self, cx, cy, r, start_ang, extent, color, width):
        self.canvas.create_arc(
            cx - r,
            cy - r,
            cx + r,
            cy + r,
            start=start_ang,
            extent=extent,
            outline=color,
            style="arc",
            width=width,
        )
        self.canvas.create_arc(
            cx - r,
            cy - r,
            cx + r,
            cy + r,
            start=start_ang + 180,
            extent=extent,
            outline=color,
            style="arc",
            width=width,
        )

    def _format_uptime(self) -> str:
        elapsed = int(time.time() - self.session_start)
        hours, rem = divmod(elapsed, 3600)
        minutes, seconds = divmod(rem, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _status_color(self, value: str) -> str:
        text = str(value or "").upper()
        if any(token in text for token in ["ALERT", "FAIL", "ERROR", "HIGH LOAD", "CRITICAL", "LOCKED"]):
            return C_ALERT
        if any(token in text for token in ["READY", "STABLE", "AWARE", "OPEN", "LISTENING"]):
            return C_SUCCESS if "STABLE" in text else C_PRIMARY
        return C_WARN

    def _truncate(self, text: str, limit: int) -> str:
        value = str(text or "").replace("\n", " ").strip()
        if len(value) <= limit:
            return value
        return value[: limit - 1].rstrip() + "…"

    def _push_recent_event(self, kind: str, text: str):
        self.recent_events.append((kind, self._truncate(text, 72)))

    def _merge_stream_text(self, existing: str, chunk: str) -> str:
        left = str(existing or "").strip()
        right = str(chunk or "").strip()
        if not right:
            return left
        if not left:
            return right
        if right == left or left.endswith(right):
            return left
        if right.startswith(left):
            return right

        overlap_max = min(len(left), len(right))
        for size in range(overlap_max, 0, -1):
            if left[-size:].lower() == right[:size].lower():
                return left + right[size:]

        if left[-1].isspace() or right[0] in ".,!?;:)]}%":
            joiner = ""
        elif left[-1] in "([{\"'":
            joiner = ""
        else:
            joiner = " "
        return left + joiner + right

    def _has_open_stream(self) -> bool:
        return bool(self.current_typing and self.current_typing.get("stream"))

    def _schedule_stream_finish(self):
        if self._stream_finish_job is not None:
            try:
                self.root.after_cancel(self._stream_finish_job)
            except Exception:
                pass
        self._stream_finish_job = self.root.after(900, self._finalize_active_stream)

    def _format_log_line(self, text: str) -> dict:
        line = str(text or "").strip()
        kind = "SYSTEM"
        role = "Stream"
        instant = True
        streaming = False
        body = line
        label_tag = "system_label"
        body_tag = "system_body"

        if line.startswith("You:"):
            body = line.replace("You:", "", 1).strip()
            kind = "USER"
            role = "Operator"
            label_tag = "user_label"
            body_tag = "user_body"
            self.last_user_text = body
        elif line.lower().startswith("mirai:"):
            body = line.split(":", 1)[1].strip()
            kind = "NEURAL"
            role = "Mirai"
            label_tag = "neural_label"
            body_tag = "neural_body"
            instant = False
            streaming = True
            self.last_neural_text = body
        elif line.startswith("SYS:"):
            body = line.replace("SYS:", "", 1).strip()
            kind = "SYSTEM"
            role = "System"
            label_tag = "system_label"
            body_tag = "system_body"
        elif line.startswith("["):
            kind = "SYSTEM"
            role = "Tools"
            label_tag = "tool_label"
            body_tag = "tool_body"

        if not streaming:
            self._push_recent_event(kind, body)
        return {
            "role": role,
            "body": body,
            "instant": instant,
            "kind": kind,
            "streaming": streaming,
            "label_tag": label_tag,
            "body_tag": body_tag,
        }

    def _append_message_prefix(self, message: dict):
        if self.log_text.index("end-1c") != "1.0":
            self._append_terminal_text("\n", "spacer")
        self._append_terminal_text(f"{message['role']}\n", message["label_tag"])

    def _finish_message_block(self):
        self._append_terminal_text("\n\n", "spacer")

    def _drain_pending_logs(self, limit: int = 12):
        for _ in range(limit):
            try:
                text = self.pending_logs.get_nowait()
            except Empty:
                break
            raw_text = str(text or "")
            if raw_text.lower().startswith("mirai:"):
                self._ingest_neural_chunk(raw_text)
                continue
            if self._has_open_stream():
                self._finalize_active_stream()
            self.typing_queue.append(raw_text)
            self.log_count += 1

    def _drain_ui_events(self, limit: int = 16):
        for _ in range(limit):
            try:
                event, payload = self.pending_events.get_nowait()
            except Empty:
                break

            if event == "request_new_key":
                self._apply_request_new_key(payload)
            elif event == "start_speaking":
                self._apply_start_speaking()
            elif event == "stop_speaking":
                self._apply_stop_speaking()
            elif event == "show_alert":
                self._apply_show_proactive_alert(payload)
            elif event == "update_sensory":
                vision, health = payload
                self.visual_status = vision
                self.health_status = health
            elif event == "finish_stream":
                self._finalize_active_stream()

    def _ingest_neural_chunk(self, raw_line: str):
        self.log_count += 1
        message = self._format_log_line(raw_line)
        self.stream_mode = "COMPOSING"

        if self._has_open_stream():
            self.current_typing["text"] = self._merge_stream_text(self.current_typing["text"], message["body"])
            self.last_neural_text = self.current_typing["text"]
            self.stream_text = self._truncate(self.current_typing["text"], 66)
            self.current_typing["closed"] = False
            self._schedule_stream_finish()
            if self._typing_job is None and self.current_typing["index"] < len(self.current_typing["text"]):
                self._type_next_character()
            return

        self._append_message_prefix(message)
        self.current_typing = {
            "text": message["body"],
            "tag": message["body_tag"],
            "index": 0,
            "stream": True,
            "closed": False,
            "kind": message["kind"],
        }
        self.last_neural_text = message["body"]
        self.stream_text = self._truncate(message["body"], 66)
        self._schedule_stream_finish()
        self._type_next_character()

    def _ensure_typing(self):
        if self._has_open_stream():
            if self._typing_job is None and self.current_typing["index"] < len(self.current_typing["text"]):
                self._type_next_character()
            return

        if self.current_typing is not None or self._typing_job is not None or not self.typing_queue:
            return

        raw_line = self.typing_queue.popleft()
        message = self._format_log_line(raw_line)
        if message["streaming"]:
            self._ingest_neural_chunk(raw_line)
            self._update_terminal_badge()
            return

        self._append_message_prefix(message)
        self._append_terminal_text(message["body"], message["body_tag"])
        self._finish_message_block()
        self._update_terminal_badge()

    def _type_next_character(self):
        self._typing_job = None
        if not self.current_typing or not self._running:
            return

        state = self.current_typing
        text = state["text"]
        index = state["index"]
        chunk = text[index:index + 1]
        if not chunk:
            if state.get("stream") and not state.get("closed"):
                self._update_terminal_badge()
                return
            self._complete_current_message()
            return

        self._append_terminal_text(chunk, state["tag"])
        state["index"] += len(chunk)
        self.stream_text = self._truncate(text[: state["index"]], 66)

        if state["index"] >= len(text):
            if state.get("stream") and not state.get("closed"):
                self._update_terminal_badge()
                return
            self._complete_current_message()
            return

        delay = self._typing_delay(text[state["index"] - 1], state["tag"])
        self._typing_job = self.root.after(delay, self._type_next_character)

    def _complete_current_message(self):
        if self.current_typing and self.current_typing.get("stream"):
            self._push_recent_event(self.current_typing.get("kind", "NEURAL"), self.current_typing["text"])
        self.current_typing = None
        self._finish_message_block()
        self._update_terminal_badge()
        self._ensure_typing()

    def _finalize_active_stream(self):
        if self._stream_finish_job is not None:
            try:
                self.root.after_cancel(self._stream_finish_job)
            except Exception:
                pass
            self._stream_finish_job = None

        if not self._has_open_stream():
            return

        self.current_typing["closed"] = True
        if self._typing_job is None:
            if self.current_typing["index"] >= len(self.current_typing["text"]):
                self._complete_current_message()
            else:
                self._type_next_character()

    def _typing_delay(self, previous_char: str, tag: str) -> int:
        if tag != "neural_body":
            return 4

        delay = 10
        if previous_char in ".!?":
            delay += 48
        elif previous_char in ",;:":
            delay += 20
        elif previous_char == "\n":
            delay += 28
        elif previous_char == " ":
            delay = 6
        return delay

    def _append_terminal_text(self, text: str, tag: str):
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, text, tag)
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _update_terminal_badge(self):
        if self._has_open_stream():
            if self.current_typing["index"] < len(self.current_typing["text"]):
                badge_text, bg, fg = "COMPOSING", C_PRIMARY, C_BG
            else:
                badge_text, bg, fg = "STREAMING", C_PRIMARY, C_BG
            self.stream_mode = "COMPOSING"
            self.stream_text = self._truncate(self.current_typing["text"], 66)
        elif self.speaking:
            badge_text, bg, fg = "VOICE LIVE", C_PRIMARY, C_BG
            self.stream_mode = "VOICE"
            self.stream_text = "voice stream active / response playback in progress"
        elif self.typing_queue:
            badge_text, bg, fg = "BUFFER", C_SECONDARY, C_TEXT
            self.stream_mode = "BUFFER"
            self.stream_text = "incoming conversation packets queued"
        else:
            badge_text, bg, fg = "IDLE", C_SUCCESS, C_BG
            self.stream_mode = "IDLE"
            self.stream_text = "idle / waiting for operator signal"

        badge_state = (badge_text, bg, fg)
        if badge_state != self._badge_state:
            self._badge_state = badge_state
            self.log_badge.config(text=badge_text, bg=bg, fg=fg)

    def _shutdown(self):
        self._running = False
        for job in (self._typing_job, self._animation_job, self._stream_finish_job):
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
        try:
            self.root.destroy()
        finally:
            os._exit(0)

    def _apply_request_new_key(self, message):
        self._api_key_ready = False
        self._show_setup_ui(message)

    def _apply_start_speaking(self):
        self.speaking = True
        self.status_text = "VOICE RESPONSE STREAM"
        self.mode_text = "SPEAKING"
        self._update_terminal_badge()

    def _apply_stop_speaking(self):
        self.speaking = False
        self.status_text = "READY FOR OPERATOR SIGNAL"
        self.mode_text = "AUTONOMOUS"
        self._update_terminal_badge()

    def _apply_show_proactive_alert(self, text: str):
        self.alert_text = str(text or "").strip()
        self.alert_until = time.time() + 5.0
        self._push_recent_event("SYSTEM", f"ALERT // {self.alert_text}")

    def write_log(self, text: str):
        self.pending_logs.put(str(text or ""))

    def request_new_key(self, message="INVALID KEY DETECTED"):
        self.pending_events.put(("request_new_key", message))

    def _show_setup_ui(self, custom_msg=None):
        win = tk.Toplevel()
        win.title("MIRAI AUTHORIZATION")
        win.geometry("560x360")
        win.configure(bg=C_BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)

        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(f"560x360+{(sw-560)//2}+{(sh-360)//2}")

        shell = tk.Frame(win, bg=C_PANEL, highlightbackground=C_LOG_EDGE, highlightthickness=1, bd=0)
        shell.place(x=24, y=24, width=512, height=312)

        top_bar = tk.Frame(shell, bg=C_PANEL_ALT, height=44)
        top_bar.pack(fill="x")
        tk.Label(
            top_bar,
            text="MIRAI // SECURE KEY VAULT",
            fg=C_TEXT,
            bg=C_PANEL_ALT,
            font=("Bahnschrift SemiBold", 14),
        ).pack(side="left", padx=16, pady=10)

        body = tk.Frame(shell, bg=C_PANEL)
        body.pack(fill="both", expand=True, padx=22, pady=18)

        tk.Label(
            body,
            text="Neural core authorization required",
            fg=C_PRIMARY,
            bg=C_PANEL,
            font=("Bahnschrift SemiBold", 18),
        ).pack(anchor="w")
        tk.Label(
            body,
            text="Gemini API anahtarini girin. Kayit security_vault/access.json icine yapilacak.",
            fg=C_MUTED,
            bg=C_PANEL,
            font=("Consolas", 10),
            justify="left",
        ).pack(anchor="w", pady=(6, 18))

        if custom_msg:
            tk.Label(
                body,
                text=custom_msg,
                fg=C_ALERT,
                bg=C_PANEL,
                font=("Consolas", 10, "bold"),
            ).pack(anchor="w", pady=(0, 12))

        entry = tk.Entry(
            body,
            width=48,
            show="*",
            bg=C_LOG_BG,
            fg=C_TEXT,
            insertbackground=C_PRIMARY,
            relief="flat",
            font=("Consolas", 11),
        )
        entry.pack(fill="x", ipady=8)
        entry.focus_set()

        hint = tk.Label(
            body,
            text="Mirai bu anahtari sadece yerel kasada saklar.",
            fg=C_MUTED,
            bg=C_PANEL,
            font=("Consolas", 9),
        )
        hint.pack(anchor="w", pady=(10, 18))

        buttons = tk.Frame(body, bg=C_PANEL)
        buttons.pack(fill="x")

        def save(evt=None):
            key = entry.get().strip()
            if not key:
                return
            try:
                current_data = {}
                if API_FILE.exists():
                    try:
                        with open(API_FILE, "r", encoding="utf-8") as handle:
                            current_data = json.load(handle)
                    except Exception:
                        current_data = {}
                current_data["gemini_api_key"] = key
                VAULT_DIR.mkdir(parents=True, exist_ok=True)
                with open(API_FILE, "w", encoding="utf-8") as handle:
                    json.dump(current_data, handle, ensure_ascii=False, indent=2)
                win.destroy()
                self._api_key_ready = True
                self._start_engine()
            except Exception as exc:
                messagebox.showerror("VAULT ERROR", f"Security vault write failed: {exc}")

        tk.Button(
            buttons,
            text="AUTHORIZE CORE",
            command=save,
            bg=C_PRIMARY,
            fg=C_BG,
            activebackground=C_SUCCESS,
            activeforeground=C_BG,
            relief="flat",
            padx=18,
            pady=10,
            font=("Bahnschrift SemiBold", 11),
            cursor="hand2",
        ).pack(side="left")

        tk.Button(
            buttons,
            text="EXIT",
            command=lambda: os._exit(0),
            bg=C_PANEL_ALT,
            fg=C_TEXT,
            activebackground=C_ALERT,
            activeforeground=C_TEXT,
            relief="flat",
            padx=18,
            pady=10,
            font=("Bahnschrift SemiBold", 11),
            cursor="hand2",
        ).pack(side="left", padx=(10, 0))

        win.bind("<Return>", save)
        win.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))

    def start_speaking(self):
        self.pending_events.put(("start_speaking", None))

    def stop_speaking(self):
        self.pending_events.put(("stop_speaking", None))

    def show_proactive_alert(self, text: str):
        self.pending_events.put(("show_alert", text))

    def update_sensory(self, vision="AWARE", health="STABLE"):
        self.pending_events.put(("update_sensory", (vision, health)))

    def finish_stream(self):
        self.pending_events.put(("finish_stream", None))

    def wait_for_api_key(self):
        while not self._api_key_ready:
            time.sleep(0.1)


if __name__ == "__main__":
    ui = MiraiUI()
    ui.root.mainloop()
