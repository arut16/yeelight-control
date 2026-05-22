import tkinter as tk
import psutil
import socket
from datetime import datetime
import os
import subprocess
from subprocess import call 
import logging
from logging.handlers import RotatingFileHandler
from PIL import Image, ImageTk
import threading
import time
import shutil
import json
import random
import traceback

# ====== Paramètres ======
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(BASE_DIR, "Icons", "update_logo.png")
LOG_PATH = os.path.join(BASE_DIR, "Logs", "cpu_temp_bubble.log")
CHECK_INTERVAL_MS = 10800000
ANIMATION_FRAME_MS = 50
ANIMATION_STEP_DEG = -5
BULLE_BG = "#fff9c4"
BULLE_TEXT = "Mise à jour effectuée avec succès !"
BULLE_TXT_COLOR = "black"
BULLE_W = 360
BULLE_H = 50
BULLE_HOLD_MS    = 4000
BULLE_FADEIN_MS  = 3000
BULLE_FADEOUT_MS = 3000

# --- Paramètres UPS secteur USB (NUT / upsc en priorité, sysfs en secours) ---
UPS_NAME = os.getenv("CPU_BUBBLE_UPS_NAME", "master@localhost")
UPS_CONFIG_PATH = os.getenv("CPU_BUBBLE_UPS_CONFIG", os.path.join(BASE_DIR, "Config", "ups_shutdown_config.json"))
UPOWER_UPS_PATHS = [p.strip() for p in os.getenv("CPU_BUBBLE_UPOWER_PATHS", "/org/freedesktop/UPower/devices/ups_hiddev0").split(",") if p.strip()]
UPS_POLL_INTERVAL_MS = 5000
UPS_STATUS_CONFIRMATION_COUNT = 3
UPS_SHUTDOWN_DELAY_SECONDS = 5
SCHEDULE_POLL_INTERVAL_MS = 15000
SCHEDULE_STARTUP_GRACE_SECONDS = int(os.getenv("CPU_BUBBLE_SCHEDULE_STARTUP_GRACE_SECONDS", "300"))
MAX_SHUTDOWN_PROGRAMS = 5
WEEKDAYS = [
    (0, "Lun"),
    (1, "Mar"),
    (2, "Mer"),
    (3, "Jeu"),
    (4, "Ven"),
    (5, "Sam"),
    (6, "Dim"),
]

# ====== Mode test par variables d'environnement ======
TEST_MODE = os.getenv("CPU_BUBBLE_TEST", "off").strip().lower()
TEST_RESULT = os.getenv("CPU_BUBBLE_RESULT", "success").strip().lower()
CPU_BUBBLE_BUILD = "schedule-startup-grace-v1.0.4-2026-05-16"

# ====== Logging avec rotation ======
logger = logging.getLogger('cpu_temp_bubble')
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(
    filename=LOG_PATH,
    maxBytes=500000,
    backupCount=1,
    encoding="utf-8",
)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)

# Définir DISPLAY=:0 pour éviter de le faire manuellement via PuTTY
os.environ["DISPLAY"] = ":0"


# ====== Compositeur : picom ======
def _is_picom_running():
    try:
        out = subprocess.run(["pgrep", "-x", "picom"], capture_output=True)
        return out.returncode == 0
    except Exception:
        return False

def ensure_picom():
    try:
        if _is_picom_running():
            return
        if shutil.which("picom") is None:
            logger.info("picom absent -> pas de compositeur.")
            return

        env = dict(os.environ)
        env.setdefault("DISPLAY", ":0")
        xauth = os.path.expanduser("~/.Xauthority")
        if os.path.exists(xauth):
            env.setdefault("XAUTHORITY", xauth)

        # Lancement basique de picom
        subprocess.Popen(
            ["picom", "-b"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        logger.info("picom démarré (ou déjà actif).")
    except Exception as e:
        logger.error(f"Impossible de démarrer picom : {e}")


# ====== Données système (helpers module-level pour éviter les régressions de merge) ======
def get_wifi_ip_address():
    try:
        interfaces = psutil.net_if_addrs()
        for interface_name, addresses in interfaces.items():
            if "wlan" in interface_name.lower():
                for address in addresses:
                    if address.family == socket.AF_INET:
                        return address.address
        return "N/A"
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de l'adresse IP Wi-Fi : {e}")
        return "N/A"


def get_cpu_temperature():
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            temp = int(f.read().strip()) / 1000
            return temp
    except Exception as e:
        logger.error(f"Erreur lors de la lecture de la température : {e}")
        return None


def get_formatted_datetime():
    jours = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    now = datetime.now()
    jour_semaine = jours[now.weekday()]
    return f"{jour_semaine} {now.strftime('%d/%m %Hh%M')}"


class DraggableWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        
        # --- CORRECTION LINUX : Définir le type 'dock' aide le compositeur ---
        try:
            self.attributes("-type", "dock")
        except tk.TclError:
            pass # Ignorer si non supporté par le WM
            
        self.config(cursor="none")
        
        self.screen_width = self.winfo_screenwidth()
        self.screen_height = self.winfo_screenheight()

        ensure_picom()

        # État MAJ / animation
        self.is_animating = False
        self.rotation_angle = 0
        self.original_image = None
        self.update_arrow = None
        self.update_arrow_area = None
        self.update_arrow_image = None
        self.updating_in_progress = False

        # État UPS USB secteur
        self.battery_capacity = None
        self.ups_status = "UNKNOWN"
        self.ups_runtime_seconds = None
        self.battery_shutdown_imminent = False
        self.on_battery_counter = 0
        self.ac_power_ok = True
        self.ups_reader_note = ""
        self.last_ups_source = None

        # --- État des réglages UPS et programmations d'arrêt ---
        self.ups_config = self._load_ups_config()
        self.auto_shutdown_enabled = bool(self.ups_config.get("auto_shutdown_enabled", True))
        self.shutdown_schedules = self.ups_config.get("schedules", [])
        self.shutdown_setting_dirty = False
        self.schedule_window = None
        self.schedule_listbox = None
        self.schedule_selected_index = None
        self.schedule_day_vars = []
        self.schedule_hour_var = None
        self.schedule_minute_var = None
        self.last_schedule_fire_key = None
        self.schedule_checker_started_at = time.monotonic()
        self.schedule_startup_grace_logged = False
        self.settings_window = self._create_settings_window()
        self.apply_confirm_window = self._create_apply_confirm_window()


        # Bulle d'info (version Tk conservée en secours)
        self.info_bubble = None

        # Dimensions & position (520px)
        window_width = 520
        window_height = 40
        x = (self.screen_width - window_width) // 2
        y = self.screen_height - 50
        self.initial_x = x
        self.geometry(f"{window_width}x{window_height}+{x}+{y}")

        # Canvas principal
        self.canvas = tk.Canvas(self, width=window_width, height=window_height, bg='#323232', bd=0, highlightthickness=0)
        self.canvas.pack()

        # Liaison unique sur le canvas
        self.canvas.bind("<Button-1>", self._on_canvas_click)

        # Textes
        self.temp_text = self.canvas.create_text(
            50, 20, text="N/A", fill="white", font=("Arial", 14, "bold"), anchor="w"
        )
        
        # --- Icône Batterie (purement visuelle) ---
        self.BATT_X_START = 125 
        BATT_Y_START = 8
        BATT_WIDTH = 60
        BATT_HEIGHT = 24
        BATT_TERM_WIDTH = 4
        BATT_TERM_HEIGHT = 10
        BATT_PADDING = 3
        self.BATT_X_END = self.BATT_X_START + BATT_WIDTH + BATT_TERM_WIDTH 
        
        self.battery_icon_outline = self.canvas.create_rectangle(
            self.BATT_X_START, BATT_Y_START, self.BATT_X_START + BATT_WIDTH, BATT_Y_START + BATT_HEIGHT, 
            outline="white", width=2
        )
        self.battery_icon_terminal = self.canvas.create_rectangle(
            self.BATT_X_START + BATT_WIDTH, BATT_Y_START + (BATT_HEIGHT - BATT_TERM_HEIGHT)//2, 
            self.BATT_X_END, BATT_Y_START + (BATT_HEIGHT - BATT_TERM_HEIGHT)//2 + BATT_TERM_HEIGHT, 
            fill="white", outline="white"
        )
        self.battery_fill_width = BATT_WIDTH - 2 * BATT_PADDING
        self.battery_icon_fill = self.canvas.create_rectangle(
            self.BATT_X_START + BATT_PADDING, BATT_Y_START + BATT_PADDING, 
            self.BATT_X_START + BATT_PADDING + self.battery_fill_width, BATT_Y_START + BATT_HEIGHT - BATT_PADDING, 
            fill="green", width=0
        )
        self.battery_text = self.canvas.create_text(
            self.BATT_X_START + BATT_WIDTH / 2 + 2, 20, text="UPS?", fill="white",
            font=("Arial", 12, "bold"), anchor="c"
        )
        # --- Fin éléments Batterie ---

        # Positions ajustées
        self.ip_text = self.canvas.create_text(
            195, 20, text="N/A", fill="white", font=("Arial", 14, "bold"), anchor="w"
        )
        self.datetime_text = self.canvas.create_text(
            335, 20, text="N/A", fill="white", font=("Arial", 14, "bold"), anchor="w"
        )

        # Croix de fermeture (purement visuelle)
        self.CLOSE_X_START = window_width - 50 
        self.close_button_lines = [
            self.canvas.create_line(window_width - 30, 8,  window_width - 8,  32, fill="red", width=4),
            self.canvas.create_line(window_width - 30, 32, window_width - 8,   8, fill="red", width=4)
        ]

        # Fenêtre de confirmation (fermeture)
        self.confirm_window = tk.Toplevel(self)
        self.confirm_window.overrideredirect(True)
        self.confirm_window.attributes("-topmost", True)
        self.confirm_window.config(cursor="none") 
        self.confirm_window.geometry(f"350x120+{(self.screen_width - 350) // 2}+{(self.screen_height - 120) // 2}")
        self.confirm_canvas = tk.Canvas(self.confirm_window, width=350, height=120, bg="#646464", bd=0, highlightthickness=0)
        self.confirm_canvas.pack()
        self.confirm_text = self.confirm_canvas.create_text(
            175, 35, text="Fermer CPU Temp Bubble ?", fill="white", font=("Arial", 18, "bold")
        )
        self.yes_button = self.confirm_canvas.create_rectangle(60, 70, 160, 110, fill="green")
        self.no_button  = self.confirm_canvas.create_rectangle(190, 70, 290, 110, fill="red")
        self.yes_text   = self.confirm_canvas.create_text(110, 90, text="Oui", fill="white", font=("Arial", 18, "bold"))
        self.no_text    = self.confirm_canvas.create_text(240, 90, text="Non", fill="white", font=("Arial", 18, "bold"))
        
        self.confirm_canvas.tag_bind(self.yes_button, "<Button-1>", lambda e: self.quit())
        self.confirm_canvas.tag_bind(self.yes_text,   "<Button-1>", lambda e: self.quit())
        self.confirm_canvas.tag_bind(self.no_button,  "<Button-1>", lambda e: self.hide_confirm_window())
        self.confirm_canvas.tag_bind(self.no_text,    "<Button-1>", lambda e: self.hide_confirm_window())
        self.confirm_window.withdraw()

        logger.info(f"CPU Temp Bubble build actif: {CPU_BUBBLE_BUILD}")

        # Log du mode test à l'init
        if TEST_MODE != "off":
            logger.info(f"[TEST MODE] CPU_BUBBLE_TEST={TEST_MODE}, CPU_BUBBLE_RESULT={TEST_RESULT}")

        # === CORRECTION TRANSPARENCE POUR LINUX ===
        # On force l'application de l'alpha APRES l'initialisation géométrique
        # wait_visibility permet d'attendre que la fenêtre soit "mappée" par X11
        self.update_idletasks()
        try:
            self.wait_visibility(self)
            self.attributes("-alpha", 0.6)  # 40% de transparence
        except tk.TclError:
            # Sécurité si la fenêtre est fermée avant d'être visible
            pass

        # Boucles (démarrées après le setup graphique complet)
        self.update_temperature()
        self.update_battery_info()
        self.check_scheduled_shutdowns()
        self.check_updates()

    # ====== UI: Gestion des clics ======

    def _on_canvas_click(self, event):
        """Gère tous les clics sur la barre principale."""
        if event.x >= self.CLOSE_X_START:
            self.on_close_click()
        elif self.BATT_X_START <= event.x <= self.BATT_X_END:
            self._open_settings_window()
        elif self.update_arrow_area and event.x <= 40:
             pass 
        else:
            pass

    def on_close_click(self, event=None):
        self.show_confirm_window()

    def show_confirm_window(self):
        self.confirm_window.deiconify()
        self.confirm_window.grab_set() 

    def hide_confirm_window(self):
        self.confirm_window.grab_release() 
        self.confirm_window.withdraw()

    # ====== Configuration UPS USB et programmations ======

    def _default_ups_config(self):
        return {"auto_shutdown_enabled": True, "schedules": []}

    def _load_ups_config(self):
        """Charge la configuration UPS locale (auto-shutdown + programmes horaires)."""
        config = self._default_ups_config()
        try:
            if os.path.exists(UPS_CONFIG_PATH):
                with open(UPS_CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    config.update(data)
            config["schedules"] = self._sanitize_schedules(config.get("schedules", []))
        except Exception as e:
            logger.error(f"Impossible de charger {UPS_CONFIG_PATH}: {e}")
        return config

    def _save_ups_config(self):
        """Sauvegarde atomiquement la configuration UPS."""
        self.ups_config = {
            "auto_shutdown_enabled": bool(self.auto_shutdown_enabled),
            "schedules": self._sanitize_schedules(self.shutdown_schedules),
        }
        folder = os.path.dirname(UPS_CONFIG_PATH)
        if folder:
            os.makedirs(folder, exist_ok=True)
        tmp_path = f"{UPS_CONFIG_PATH}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.ups_config, f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, UPS_CONFIG_PATH)
        logger.info(f"Configuration UPS sauvegardée dans {UPS_CONFIG_PATH}")

    def _sanitize_schedules(self, schedules):
        clean = []
        if not isinstance(schedules, list):
            return clean
        for item in schedules[:MAX_SHUTDOWN_PROGRAMS]:
            try:
                days = sorted({int(d) for d in item.get("days", []) if 0 <= int(d) <= 6})
                hour = int(item.get("hour", 0))
                minute = int(item.get("minute", 0))
                enabled = bool(item.get("enabled", True))
                if days and 0 <= hour <= 23 and 0 <= minute <= 59:
                    clean.append({"enabled": enabled, "days": days, "hour": hour, "minute": minute})
            except Exception:
                continue
        return clean

    def _format_schedule(self, schedule):
        day_names = dict(WEEKDAYS)
        days = ",".join(day_names.get(d, "?") for d in schedule.get("days", []))
        state = "ON" if schedule.get("enabled", True) else "OFF"
        return f"{state}  {days}  à {int(schedule.get('hour', 0)):02d}:{int(schedule.get('minute', 0)):02d}"

    def _create_settings_window(self):
        """Crée la fenêtre Toplevel pour les réglages UPS USB."""
        win = tk.Toplevel(self)
        win.title("Auto Shutdown Setup")
        win.configure(bg="#646464")
        win.attributes("-topmost", True)
        win.overrideredirect(True)
        win.config(cursor="none")

        W, H = 460, 190
        x = (self.screen_width - W) // 2
        y = (self.screen_height - H) // 2
        win.geometry(f"{W}x{H}+{x}+{y}")

        title_label = tk.Label(win, text="Auto Shutdown Setup", bg="#646464", fg="white", font=("Arial", 14, "bold"))
        title_label.pack(pady=10)

        frame_toggle = tk.Frame(win, bg="#646464")
        frame_toggle.pack(pady=5, padx=20, fill="x")

        setting_label = tk.Label(
            frame_toggle,
            text="Extinction auto si UPS sur batterie :",
            bg="#646464",
            fg="white",
            font=("Arial", 11),
        )
        setting_label.pack(side=tk.LEFT, padx=5)

        self.shutdown_toggle_button = tk.Button(frame_toggle, text="N/A", width=10, command=self._on_toggle_shutdown)
        self.shutdown_toggle_button.pack(side=tk.RIGHT, padx=5, pady=5)

        frame_program = tk.Frame(win, bg="#646464")
        frame_program.pack(pady=4, padx=20, fill="x")
        tk.Label(
            frame_program,
            text="Arrêts programmés (max 5) :",
            bg="#646464",
            fg="white",
            font=("Arial", 11),
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_program, text="Programmation", command=self._open_schedule_window).pack(side=tk.RIGHT, padx=5)

        frame_buttons = tk.Frame(win, bg="#646464")
        frame_buttons.pack(pady=10, fill="x", side=tk.BOTTOM, padx=20)

        self.apply_button = tk.Button(frame_buttons, text="Appliquer", command=self._on_apply_settings)
        self.apply_button.pack(side=tk.LEFT, expand=True, fill='x', padx=10, pady=5)

        self.cancel_button = tk.Button(frame_buttons, text="Annuler", command=self._on_cancel_settings)
        self.cancel_button.pack(side=tk.RIGHT, expand=True, fill='x', padx=10, pady=5)

        win.withdraw()
        return win

    def _create_apply_confirm_window(self):
        win = tk.Toplevel(self)
        win.configure(bg="#323232", relief=tk.RIDGE, borderwidth=2)
        win.attributes("-topmost", True)
        win.overrideredirect(True)
        win.config(cursor="none")

        W, H = 240, 70
        x = (self.screen_width - W) // 2
        y = (self.screen_height - H) // 2
        win.geometry(f"{W}x{H}+{x}+{y}")

        label = tk.Label(win, text="Réglage appliqué !", bg="#323232", fg="white", font=("Arial", 12, "bold"))
        label.pack(pady=18, expand=True)

        win.withdraw()
        return win

    def _show_apply_confirmation(self):
        """Affiche le pop-up 'Réglage appliqué' pendant 2 secondes."""
        self.apply_confirm_window.deiconify()
        self.after(2000, self.apply_confirm_window.withdraw)

    def _open_settings_window(self, event=None):
        """Affiche la fenêtre de réglage UPS sans dépendance X1200/PLD."""
        try:
            self.ups_config = self._load_ups_config()
            self.auto_shutdown_enabled = bool(self.ups_config.get("auto_shutdown_enabled", True))
            self.shutdown_schedules = self.ups_config.get("schedules", [])
            self._update_toggle_button_ui(self.auto_shutdown_enabled)
            self.shutdown_setting_dirty = False
            self.settings_window.deiconify()
            self.settings_window.grab_set()
        except Exception as e:
            logger.error(f"Erreur ouverture fenêtre réglages UPS: {e}")

    def _update_toggle_button_ui(self, is_enabled):
        """Met à jour l'apparence du bouton bascule."""
        if is_enabled:
            self.shutdown_toggle_button.config(text="Activé", bg="#fff9c4", fg="black")
        else:
            self.shutdown_toggle_button.config(text="Désactivé", bg="#808080", fg="white")

    def _on_toggle_shutdown(self):
        """Bascule l'arrêt auto si l'UPS passe sur batterie."""
        current_text = self.shutdown_toggle_button.cget("text")
        new_state_enabled = (current_text == "Désactivé")
        self._update_toggle_button_ui(new_state_enabled)
        self.shutdown_setting_dirty = True
        logger.info(f"Bascule UI arrêt auto UPS vers: {'Activé' if new_state_enabled else 'Désactivé'}")

    def _on_apply_settings(self):
        """Applique les modifications dans le JSON local."""
        try:
            self.auto_shutdown_enabled = (self.shutdown_toggle_button.cget("text") == "Activé")
            self._save_ups_config()
            self._show_apply_confirmation()
        except Exception as e:
            logger.error(f"Erreur lors de l'application des réglages UPS: {e}")
        self.settings_window.grab_release()
        self.settings_window.withdraw()
        self.shutdown_setting_dirty = False

    def _on_cancel_settings(self):
        """Annule les modifications et ferme la fenêtre."""
        self.settings_window.grab_release()
        self.settings_window.withdraw()
        self.shutdown_setting_dirty = False
        logger.info("Réglages UPS annulés.")

    def _open_schedule_window(self):
        """Ouvre l'éditeur d'arrêts programmés."""
        try:
            self.settings_window.grab_release()
        except Exception:
            pass

        if self.schedule_window and self.schedule_window.winfo_exists():
            self._refresh_schedule_list()
            self.schedule_window.deiconify()
            self.schedule_window.lift()
            return

        win = tk.Toplevel(self)
        self.schedule_window = win
        win.title("Programmation extinction RPi")
        win.configure(bg="#202020")
        win.attributes("-topmost", True)
        win.overrideredirect(True)
        win.config(cursor="none")

        W, H = 640, 430
        x = (self.screen_width - W) // 2
        y = (self.screen_height - H) // 2
        win.geometry(f"{W}x{H}+{x}+{y}")

        # ===== HEADER =====
        header = tk.Frame(win, bg="#202020")
        header.pack(fill="x", padx=12, pady=(6, 2))

        tk.Label(
            header,
            text="Programmation extinction RPi",
            bg="#202020",
            fg="white",
            font=("Arial", 16, "bold"),
        ).pack(side=tk.LEFT, expand=True, fill="x")

        close_btn = tk.Canvas(header, width=36, height=36, bg="#202020", highlightthickness=0)
        close_btn.pack(side=tk.RIGHT)
        close_btn.create_oval(4, 4, 32, 32, fill="#D32F2F", outline="")
        close_btn.create_line(13, 13, 23, 23, fill="white", width=3)
        close_btn.create_line(23, 13, 13, 23, fill="white", width=3)
        close_btn.bind("<Button-1>", lambda e: self._close_schedule_window())

        # ===== SECTION JOURS EN HAUT, EN LIGNE =====
        days_top = tk.Frame(win, bg="#202020")
        days_top.pack(fill="x", padx=12, pady=(4, 4))

        tk.Label(
            days_top,
            text="Jours :",
            bg="#202020",
            fg="lightgray",
            font=("Arial", 11, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.schedule_day_vars = []
        for idx, label in WEEKDAYS:
            var = tk.BooleanVar(value=True)
            self.schedule_day_vars.append(var)

            tk.Checkbutton(
                days_top,
                text=label,
                variable=var,
                bg="#202020",
                fg="white",
                selectcolor="#323232",
                activebackground="#202020",
                activeforeground="white",
                font=("Arial", 9),
                padx=2,
                pady=0,
            ).pack(side=tk.LEFT, padx=2)

        # ===== CORPS PRINCIPAL =====
        body = tk.Frame(win, bg="#202020")
        body.pack(fill="both", expand=True, padx=12, pady=(2, 0))

        # Gauche : programmes enregistrés
        left = tk.Frame(body, bg="#202020")
        left.pack(side=tk.LEFT, fill="both", expand=True, padx=(0, 10))

        tk.Label(
            left,
            text="Programmes enregistrés",
            bg="#202020",
            fg="lightgray",
            font=("Arial", 11, "bold")
        ).pack(anchor="w")

        self.schedule_listbox = tk.Listbox(
            left,
            height=10,
            bg="#323232",
            fg="white",
            selectbackground="#1976D2",
            font=("Arial", 11)
        )
        self.schedule_listbox.pack(fill="both", expand=True, pady=6)
        self.schedule_listbox.bind("<<ListboxSelect>>", self._on_schedule_select)

        # Droite : heure + actions
        right = tk.Frame(body, bg="#202020")
        right.pack(side=tk.RIGHT, fill="y", anchor="n")

        time_frame = tk.Frame(right, bg="#202020")
        time_frame.pack(anchor="n", pady=(0, 6))

        tk.Label(
            time_frame,
            text="Heure",
            bg="#202020",
            fg="lightgray",
            font=("Arial", 11, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 2))

        self.schedule_hour_var = tk.StringVar(value="07")
        self.schedule_minute_var = tk.StringVar(value="59")

        self._create_large_time_selector(
            time_frame,
            "H",
            self.schedule_hour_var,
            23
        ).grid(row=1, column=0, pady=0)

        tk.Label(
            time_frame,
            text=":",
            bg="#202020",
            fg="white",
            font=("Arial", 12, "bold")
        ).grid(row=1, column=1, padx=3)

        self._create_large_time_selector(
            time_frame,
            "M",
            self.schedule_minute_var,
            59
        ).grid(row=1, column=2, pady=0)

        # Boutons remontés à droite
        tk.Button(
            right,
            text="Ajouter",
            bg="#4CAF50",
            fg="white",
            font=("Arial", 10, "bold"),
            command=self._add_schedule
        ).pack(fill="x", pady=2)

        tk.Button(
            right,
            text="Remplacer",
            bg="#1976D2",
            fg="white",
            font=("Arial", 10, "bold"),
            command=self._replace_schedule
        ).pack(fill="x", pady=2)

        tk.Button(
            right,
            text="Activer/Désactiver",
            bg="#757575",
            fg="white",
            font=("Arial", 10, "bold"),
            command=self._toggle_selected_schedule
        ).pack(fill="x", pady=2)

        tk.Button(
            right,
            text="Supprimer",
            bg="#D32F2F",
            fg="white",
            font=("Arial", 10, "bold"),
            command=self._delete_schedule
        ).pack(fill="x", pady=2)

        # ===== FOOTER CONSEIL =====
        footer = tk.Frame(win, bg="#202020")
        footer.pack(fill="x", padx=12, pady=(4, 6))

        tk.Label(
            footer,
            text="Conseil : programmer l'arrêt RPi 1 minute avant la coupure eWeLink.",
            bg="#202020",
            fg="#fff9c4",
            font=("Arial", 9)
        ).pack(side=tk.LEFT)

        self._refresh_schedule_list()


    def _create_large_time_selector(self, parent, label, variable, maximum):
        frame = tk.Frame(parent, bg="#202020")

        tk.Label(
            frame,
            text=label,
            bg="#202020",
            fg="lightgray",
            font=("Arial", 8, "bold")
        ).pack()

        tk.Button(
            frame,
            text="▲",
            width=2,
            height=1,
            bg="#606060",
            fg="white",
            font=("Arial", 8, "bold"),
            command=lambda: self._bump_schedule_time(variable, 1, maximum),
        ).pack(fill="x", pady=(0, 1))

        tk.Label(
            frame,
            textvariable=variable,
            width=2,
            bg="#323232",
            fg="white",
            font=("Arial", 12, "bold"),
        ).pack(fill="x", pady=1)

        tk.Button(
            frame,
            text="▼",
            width=2,
            height=1,
            bg="#606060",
            fg="white",
            font=("Arial", 8, "bold"),
            command=lambda: self._bump_schedule_time(variable, -1, maximum),
        ).pack(fill="x", pady=(1, 0))

        return frame

    def _bump_schedule_time(self, variable, delta, maximum):
        try:
            value = int(variable.get())
        except Exception:
            value = 0
        value = (value + delta) % (maximum + 1)
        variable.set(f"{value:02d}")

    def _close_schedule_window(self):
        try:
            self._save_ups_config()
        except Exception as e:
            logger.error(f"Erreur sauvegarde programmes: {e}")
        if self.schedule_window:
            self.schedule_window.withdraw()
        try:
            if self.settings_window.winfo_viewable():
                self.settings_window.grab_set()
        except Exception:
            pass

    def _refresh_schedule_list(self):
        if not self.schedule_listbox:
            return
        self.schedule_listbox.delete(0, tk.END)
        for schedule in self.shutdown_schedules:
            self.schedule_listbox.insert(tk.END, self._format_schedule(schedule))
        self.schedule_selected_index = None

    def _read_schedule_form(self):
        days = [idx for idx, var in enumerate(self.schedule_day_vars) if var.get()]
        if not days:
            raise ValueError("Sélectionner au moins un jour.")
        hour = int(self.schedule_hour_var.get())
        minute = int(self.schedule_minute_var.get())
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("Heure invalide.")
        return {"enabled": True, "days": days, "hour": hour, "minute": minute}

    def _on_schedule_select(self, event=None):
        selected = self.schedule_listbox.curselection() if self.schedule_listbox else []
        if not selected:
            self.schedule_selected_index = None
            return
        self.schedule_selected_index = selected[0]
        schedule = self.shutdown_schedules[self.schedule_selected_index]
        selected_days = set(schedule.get("days", []))
        for idx, var in enumerate(self.schedule_day_vars):
            var.set(idx in selected_days)
        self.schedule_hour_var.set(f"{int(schedule.get('hour', 0)):02d}")
        self.schedule_minute_var.set(f"{int(schedule.get('minute', 0)):02d}")

    def _add_schedule(self):
        try:
            if len(self.shutdown_schedules) >= MAX_SHUTDOWN_PROGRAMS:
                logger.warning("Nombre maximum de programmes atteint.")
                return
            self.shutdown_schedules.append(self._read_schedule_form())
            self._save_ups_config()
            self._refresh_schedule_list()
        except Exception as e:
            logger.error(f"Ajout programme impossible: {e}")

    def _replace_schedule(self):
        try:
            if self.schedule_selected_index is None:
                return
            self.shutdown_schedules[self.schedule_selected_index] = self._read_schedule_form()
            self._save_ups_config()
            self._refresh_schedule_list()
        except Exception as e:
            logger.error(f"Remplacement programme impossible: {e}")

    def _toggle_selected_schedule(self):
        try:
            if self.schedule_selected_index is None:
                return
            current = self.shutdown_schedules[self.schedule_selected_index].get("enabled", True)
            self.shutdown_schedules[self.schedule_selected_index]["enabled"] = not current
            self._save_ups_config()
            self._refresh_schedule_list()
        except Exception as e:
            logger.error(f"Bascule programme impossible: {e}")

    def _delete_schedule(self):
        try:
            if self.schedule_selected_index is None:
                return
            del self.shutdown_schedules[self.schedule_selected_index]
            self._save_ups_config()
            self._refresh_schedule_list()
        except Exception as e:
            logger.error(f"Suppression programme impossible: {e}")

    def check_scheduled_shutdowns(self):
        """Déclenche l'extinction aux heures programmées, une seule fois par minute.

        Au démarrage d'un Raspberry Pi sans horloge RTC, l'heure système peut rester
        quelques instants sur la dernière heure connue avant la synchronisation NTP.
        Sans temporisation, un programme d'arrêt proche de l'heure de coupure peut
        donc être rejoué immédiatement au boot et provoquer une boucle d'extinction.
        """
        try:
            uptime_seconds = time.monotonic() - self.schedule_checker_started_at
            if uptime_seconds < SCHEDULE_STARTUP_GRACE_SECONDS:
                if not self.schedule_startup_grace_logged:
                    logger.info(
                        "Programmations d'arrêt ignorées pendant %.0fs au démarrage "
                        "pour laisser l'heure système se synchroniser.",
                        SCHEDULE_STARTUP_GRACE_SECONDS,
                    )
                    self.schedule_startup_grace_logged = True
                return

            now = datetime.now()
            fire_key = now.strftime("%Y-%m-%d %H:%M")
            if fire_key != self.last_schedule_fire_key:
                for schedule in self.shutdown_schedules:
                    if not schedule.get("enabled", True):
                        continue
                    if now.weekday() in schedule.get("days", []) and now.hour == schedule.get("hour") and now.minute == schedule.get("minute"):
                        self.last_schedule_fire_key = fire_key
                        logger.warning(f"Extinction programmée déclenchée: {self._format_schedule(schedule)}")
                        threading.Thread(target=self._shutdown_system, kwargs={"reason": "extinction programmée"}, daemon=True).start()
                        break
        except Exception as e:
            logger.error(f"Erreur vérification programmations: {e}")
        finally:
            if not self.battery_shutdown_imminent:
                self.after(SCHEDULE_POLL_INTERVAL_MS, self.check_scheduled_shutdowns)

    # ====== Lecture UPS USB (NUT / sysfs) ======

    def _read_ups_info(self):
        # Sur le Pi cible, l'UPS Eaton/Master remonte immédiatement via UPower
        # (/org/freedesktop/UPower/devices/ups_hiddev0), alors que NUT peut ne
        # pas être démarré/configuré et répondre "Connection refused". On lit
        # donc UPower en premier pour éviter un faux état N/A/UPS?.
        info = self._read_upower_ups_info()
        if info:
            return info
        info = self._read_nut_ups_info()
        if info:
            return info
        return self._read_sysfs_ups_info()

    def _find_command(self, command_name):
        resolved = shutil.which(command_name)
        if resolved:
            return resolved
        fallback = f"/usr/bin/{command_name}"
        if os.path.exists(fallback) and os.access(fallback, os.X_OK):
            return fallback
        return None

    def _run_upsc(self, args):
        upsc_cmd = self._find_command("upsc")
        if upsc_cmd is None:
            return None
        result = subprocess.run([upsc_cmd, *args], capture_output=True, text=True, timeout=3)
        if result.returncode != 0:
            return None
        return result.stdout

    def _read_nut_ups_info(self):
        """Lit l'UPS via NUT. Fonctionne avec un nom explicite ou le premier UPS local."""
        try:
            ups_name = UPS_NAME
            raw = self._run_upsc([ups_name])
            if raw is None and UPS_NAME == "master@localhost":
                names = self._run_upsc(["-l"])
                first = next((line.strip() for line in (names or "").splitlines() if line.strip()), None)
                if first:
                    ups_name = first
                    raw = self._run_upsc([ups_name])
            if raw is None:
                return None

            data = {}
            for line in raw.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    data[key.strip()] = value.strip()

            status = data.get("ups.status", "UNKNOWN")
            charge = self._safe_int(data.get("battery.charge"))
            runtime = self._safe_int(data.get("battery.runtime"))
            return {
                "source": f"NUT:{ups_name}",
                "status": status,
                "charge": charge,
                "runtime": runtime,
                "online": "OL" in status.split(),
                "on_battery": "OB" in status.split(),
                "low_battery": "LB" in status.split(),
            }
        except Exception as e:
            logger.warning(f"Lecture UPS NUT impossible: {e}")
            return None

    def _read_upower_ups_info(self):
        """Secours via UPower, souvent disponible sur Raspberry Pi OS avec les UPS USB HID."""
        upower_cmd = self._find_command("upower")
        if upower_cmd is None:
            return None
        try:
            enum = subprocess.run([upower_cmd, "-e"], capture_output=True, text=True, timeout=3)
            if enum.returncode != 0:
                return None

            discovered_paths = [line.strip() for line in (enum.stdout or "").splitlines() if line.strip()]
            # Le Pi cible expose l'UPS sous ups_hiddev0. On tente ce chemin connu
            # en premier, puis les périphériques découverts par UPower.
            device_paths = []
            for candidate in [*UPOWER_UPS_PATHS, *discovered_paths]:
                if candidate and candidate not in device_paths:
                    device_paths.append(candidate)

            # On préfère les vrais UPS, puis les batteries système exposées par UPower.
            ordered_paths = sorted(
                device_paths,
                key=lambda item: ("ups" not in item.lower(), "battery" not in item.lower(), item),
            )

            for device_path in ordered_paths:
                details = subprocess.run([upower_cmd, "-i", device_path], capture_output=True, text=True, timeout=3)
                if details.returncode != 0:
                    continue

                data = {}
                for line in (details.stdout or "").splitlines():
                    if ":" in line:
                        key, value = line.split(":", 1)
                        data[key.strip().lower()] = value.strip()

                native_path = data.get("native-path", "")
                device_type = data.get("type", "").lower()
                lower_path = device_path.lower()
                if not ("ups" in lower_path or "ups" in native_path.lower() or device_type in ("ups", "battery")):
                    continue

                percentage = data.get("percentage", "").replace("%", "")
                charge = self._safe_int(percentage)
                state = data.get("state", "unknown").lower()
                warning = data.get("warning-level", "none").lower()
                runtime = self._parse_upower_duration_seconds(data.get("time to empty", ""))

                on_battery = state in ("discharging", "empty")
                online = state in ("charging", "fully-charged", "pending-charge")
                low_battery = warning not in ("", "none", "unknown") or (charge is not None and charge <= 10)

                return {
                    "source": f"UPower:{device_path}",
                    "status": state.upper(),
                    "charge": charge,
                    "runtime": runtime,
                    "online": online,
                    "on_battery": on_battery,
                    "low_battery": low_battery,
                }
        except Exception as e:
            logger.warning(f"Lecture UPS UPower impossible: {e}")
        return None

    def _read_sysfs_ups_info(self):
        """Secours pour les UPS exposés par le noyau dans /sys/class/power_supply."""
        try:
            base = "/sys/class/power_supply"
            if not os.path.isdir(base):
                return None
            for name in os.listdir(base):
                path = os.path.join(base, name)
                type_path = os.path.join(path, "type")
                try:
                    with open(type_path, "r", encoding="utf-8") as f:
                        supply_type = f.read().strip().lower()
                except Exception:
                    continue
                if supply_type not in ("ups", "battery"):
                    continue
                status = self._read_text_file(os.path.join(path, "status"), "Unknown")
                charge = self._safe_int(self._read_text_file(os.path.join(path, "capacity"), None))
                normalized = status.lower()
                return {
                    "source": f"sysfs:{name}",
                    "status": status.upper(),
                    "charge": charge,
                    "runtime": None,
                    "online": normalized in ("charging", "full", "not charging"),
                    "on_battery": normalized == "discharging",
                    "low_battery": charge is not None and charge <= 10,
                }
        except Exception as e:
            logger.warning(f"Lecture UPS sysfs impossible: {e}")
        return None

    def _read_text_file(self, path, default=None):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return default

    def _safe_int(self, value):
        try:
            if value is None or value == "":
                return None
            normalized = str(value).strip().replace(",", ".")
            return int(float(normalized))
        except Exception:
            return None

    def _parse_upower_duration_seconds(self, value):
        """Parse des durées UPower localisées du type '2,0 hours' ou '45 minutes'."""
        if not value:
            return None
        parts = str(value).strip().replace(",", ".").split()
        if not parts:
            return None
        amount = self._safe_int(parts[0])
        if amount is None:
            return None
        unit = parts[1].lower() if len(parts) > 1 else "seconds"
        if unit.startswith("hour") or unit.startswith("heure"):
            return amount * 3600
        if unit.startswith("minute"):
            return amount * 60
        return amount

    def _shutdown_system(self, reason="UPS sur batterie"):
        """Lance l'arrêt propre du Raspberry Pi."""
        logger.warning(f"Arrêt système demandé ({reason}) dans {UPS_SHUTDOWN_DELAY_SECONDS} secondes.")
        time.sleep(UPS_SHUTDOWN_DELAY_SECONDS)
        logger.info(f"Exécution de la commande d'arrêt: {reason}.")
        call("sudo nohup shutdown -h now", shell=True)
        self.quit()

    def update_battery_info(self, force_color_update=False):
        if self.battery_shutdown_imminent and not force_color_update:
            return

        try:
            info = self._read_ups_info()
            if not info:
                # Ne plus afficher N/A en permanence : l'UPS USB peut être présent mais
                # non exposé par NUT/UPower/sysfs. On garde une icône grise explicite.
                self.canvas.itemconfig(self.battery_text, text="UPS?", fill="white", state='normal')
                self.canvas.itemconfig(self.battery_icon_fill, fill="grey")
                self.canvas.coords(
                    self.battery_icon_fill,
                    self.BATT_X_START + 3,
                    11,
                    self.BATT_X_START + self.battery_fill_width,
                    29,
                )
                self.ups_reader_note = "UPS USB non lu: configurer NUT, UPower ou vérifier le câble USB."
                logger.warning(self.ups_reader_note)
                return

            self.ups_status = info.get("status", "UNKNOWN")
            self.battery_capacity = info.get("charge")
            self.ups_runtime_seconds = info.get("runtime")
            source = info.get("source", "UPS")
            if source != self.last_ups_source:
                logger.info(f"Source UPS active ({CPU_BUBBLE_BUILD}): {source} - statut={self.ups_status}, charge={self.battery_capacity}")
                self.last_ups_source = source
            self.ac_power_ok = bool(info.get("online", False)) and not bool(info.get("on_battery", False))

            cap_percent = self.battery_capacity if self.battery_capacity is not None else 100
            cap_percent = max(0, min(100, int(cap_percent)))
            self.canvas.itemconfig(self.battery_text, text=f"{cap_percent}%")

            if self.ac_power_ok:
                color = "dodgerblue"
                # Afficher aussi le pourcentage sur secteur: cela confirme que l'UPS est bien lu.
                self.canvas.itemconfig(self.battery_text, fill="black", state='normal')
                self.on_battery_counter = 0
            else:
                self.canvas.itemconfig(self.battery_text, state='normal')
                if info.get("low_battery") or cap_percent < 20:
                    color = "red"
                    self.canvas.itemconfig(self.battery_text, fill="white")
                elif cap_percent < 50:
                    color = "orange"
                    self.canvas.itemconfig(self.battery_text, fill="black")
                else:
                    color = "lime"
                    self.canvas.itemconfig(self.battery_text, fill="black")

            self.canvas.itemconfig(self.battery_icon_fill, fill=color)
            BATT_Y_START = 8
            BATT_HEIGHT = 24
            BATT_PADDING = 3
            fill_pixels = int(self.battery_fill_width * (cap_percent / 100.0))
            self.canvas.coords(
                self.battery_icon_fill,
                self.BATT_X_START + BATT_PADDING,
                BATT_Y_START + BATT_PADDING,
                self.BATT_X_START + BATT_PADDING + fill_pixels,
                BATT_Y_START + BATT_HEIGHT - BATT_PADDING,
            )

            if info.get("on_battery") or info.get("low_battery"):
                self.on_battery_counter += 1
                logger.warning(
                    f"UPS sur batterie ({self.on_battery_counter}/{UPS_STATUS_CONFIRMATION_COUNT}) "
                    f"- statut={self.ups_status}, charge={cap_percent}%, source={info.get('source')}"
                )
                if (
                    self.auto_shutdown_enabled
                    and self.on_battery_counter >= UPS_STATUS_CONFIRMATION_COUNT
                    and not self.battery_shutdown_imminent
                ):
                    self.battery_shutdown_imminent = True
                    self.canvas.itemconfig(self.battery_text, text="UPS!", fill="white", state='normal')
                    self.canvas.itemconfig(self.battery_icon_fill, fill="red")
                    threading.Thread(target=self._shutdown_system, kwargs={"reason": "UPS sur batterie"}, daemon=True).start()
            else:
                self.on_battery_counter = 0

        except Exception as e:
            logger.error(f"Erreur lecture UPS USB: {e}")
            self.canvas.itemconfig(self.battery_text, text="Err", state='normal')
            self.canvas.itemconfig(self.battery_icon_fill, fill="grey")

        finally:
            if not self.battery_shutdown_imminent and not force_color_update:
                self.after(UPS_POLL_INTERVAL_MS, self.update_battery_info)

    # ====== Données système ======
    def get_wifi_ip_address(self):
        return get_wifi_ip_address()

    def get_cpu_temperature(self):
        return get_cpu_temperature()

    def get_formatted_datetime(self):
        return get_formatted_datetime()

    def update_temperature(self):
        # Appel direct aux helpers module-level : évite un crash si un déploiement
        # partiel garde une classe Tk sans les méthodes wrapper ci-dessus.
        temp = get_cpu_temperature()
        ip_address = get_wifi_ip_address()
        formatted_datetime = get_formatted_datetime()

        if temp is not None:
            self.canvas.itemconfig(self.temp_text, text=f"{temp:.1f}°C")
            self.update_color(temp)
        else:
            self.canvas.itemconfig(self.temp_text, text="N/A")

        self.canvas.itemconfig(self.ip_text, text=f"IP={ip_address}")
        self.canvas.itemconfig(self.datetime_text, text=formatted_datetime)

        self.after(5000, self.update_temperature)

    def update_color(self, temp):
        if temp < 60:
            color = "lime green"
        elif 60 <= temp < 80:
            color = "orange"
        else:
            color = "red"
        self.canvas.itemconfig(self.temp_text, fill=color)

    # ====== Icône MAJ: affichage / animation ======
    def show_update_arrow(self):
        if self.update_arrow:
            return
        try:
            self.original_image = Image.open(ICON_PATH)
            height = 40
            aspect_ratio = self.original_image.width / self.original_image.height
            width = int(height * aspect_ratio)
            image = self.original_image.resize((width, height), Image.Resampling.BICUBIC)
            self.update_arrow_image = ImageTk.PhotoImage(image)

            self.update_arrow = self.canvas.create_image(
                5 + width/2, 20, image=self.update_arrow_image, anchor="center"
            )
            self.update_arrow_area = self.canvas.create_rectangle(
                5, 0, 5 + width, 40, fill="", outline=""
            )
            logger.info("Icône de mise à jour affichée")
        except Exception as e:
            logger.error(f"Erreur lors du chargement de l'icône : {e}")
            self.original_image = None
            self.update_arrow = None
            self.update_arrow_area = None
            self.update_arrow_image = None
            self.is_animating = False

    def hide_update_arrow(self):
        self.is_animating = False
        if self.update_arrow:
            self.canvas.delete(self.update_arrow)
            self.update_arrow = None
        if self.update_arrow_area:
            self.canvas.delete(self.update_arrow_area)
            self.update_arrow_area = None
        self.update_arrow_image = None
        self.original_image = None
        logger.info("Icône de mise à jour masquée")

    def animate_icon(self):
        if not self.is_animating or not self.update_arrow or not self.original_image:
            return
        try:
            self.rotation_angle = (self.rotation_angle + ANIMATION_STEP_DEG) % 360
            rotated_image = self.original_image.rotate(self.rotation_angle, resample=Image.Resampling.BICUBIC)
            height = 40
            aspect_ratio = rotated_image.width / rotated_image.height
            width = int(height * aspect_ratio)
            rotated_image = rotated_image.resize((width, height), Image.Resampling.BICUBIC)
            self.update_arrow_image = ImageTk.PhotoImage(rotated_image)
            self.canvas.itemconfig(self.update_arrow, image=self.update_arrow_image)
            self.canvas.coords(self.update_arrow_area, 5, 0, 5 + width, 40)
            self.canvas.coords(self.update_arrow, 5 + width/2, 20)
            self.after(ANIMATION_FRAME_MS, self.animate_icon)
        except Exception as e:
            logger.error(f"Erreur lors de l'animation de l'icône : {e}")
            self.is_animating = False

    # ====== (Secours Tk) Bulle d'information simple ======
    def show_info_bubble(self, message="Mise à jour effectuée avec succès !"):
        try:
            if self.info_bubble and self.info_bubble.winfo_exists():
                self.info_bubble.destroy()
        except Exception:
            pass

        try:
            self.update_idletasks()
            main_x = self.winfo_x()
            main_y = self.winfo_y()
            main_w = self.winfo_width()

            BODY_H  = 58
            TAIL_H  = 12
            BULLE_H = BODY_H + TAIL_H

            bubble_x = main_x + (main_w - BULLE_W) // 2
            bubble_y = max(0, main_y - BULLE_H - 2)

            self.info_bubble = tk.Toplevel(self)
            self.info_bubble.overrideredirect(True)
            self.info_bubble.attributes("-topmost", True)
            self.info_bubble.config(cursor="none") # Cacher curseur
            self.info_bubble.geometry(f"{BULLE_W}x{BULLE_H}+{bubble_x}+{bubble_y}")
            self.info_bubble.configure(bg=BULLE_BG)

            c = tk.Canvas(self.info_bubble, width=BULLE_W, height=BULLE_H,
                          bg=BULLE_BG, bd=0, highlightthickness=0)
            c.pack()

            c.create_rectangle(0, 0, BULLE_W, BODY_H, fill=BULLE_BG, outline=BULLE_BG)

            tri_center = BULLE_W//2 - 25
            tri_half_w = 9
            c.create_polygon(
                tri_center - tri_half_w, BODY_H,
                tri_center + tri_half_w, BODY_H,
                tri_center,              BODY_H + TAIL_H,
                fill=BULLE_BG, outline=BULLE_BG
            )

            c.create_text(
                BULLE_W//2, BODY_H//2,
                text=message, fill="black",
                font=("Arial", 13, "bold"),
                width=BULLE_W - 24
            )

            self.after(BULLE_HOLD_MS, self.hide_info_bubble)

        except Exception as e:
            logger.error(f"Erreur bulle (mono-Toplevel): {e}")
            self.after(BULLE_HOLD_MS, self.hide_update_arrow)

    def hide_info_bubble(self):
        try:
            if self.info_bubble and self.info_bubble.winfo_exists():
                if hasattr(self.info_bubble, "tail"):
                    try:
                        if self.info_bubble.tail and self.info_bubble.tail.winfo_exists():
                            self.info_bubble.tail.destroy()
                    except Exception:
                        pass
                self.info_bubble.destroy()
        except Exception:
            pass
        finally:
            self.info_bubble = None
            self.hide_update_arrow()

    # ====== Vérification & Exécution des MAJ (avec sudo) ======
    def check_updates(self):
        logger.info("Vérification des mises à jour système...")

        if TEST_MODE != "off":
            if TEST_MODE == "available":
                logger.info("[TEST MODE] Updates AVAILABLE -> auto start update")
                self.after(0, self._auto_start_update_if_needed)
            else:
                logger.info("[TEST MODE] No updates available")
                self.after(0, self.hide_update_arrow)
            self.after(CHECK_INTERVAL_MS, self.check_updates)
            return

        def run_check():
            import random
            import traceback

            rescheduled = False
            try:
                # 'sudo' est ajouté
                upd = subprocess.run(
                    ["sudo", "apt", "update"],
                    capture_output=True,
                    text=True
                )
                stderr = (upd.stderr or "").strip()
                stdout = (upd.stdout or "").strip()

                if upd.returncode != 0:
                    lock_markers = (
                        "Could not get lock", "is another process using",
                        "dpkg frontend is locked", "Unable to acquire the dpkg frontend lock"
                    )
                    now_hour = datetime.now().hour
                    is_lock = any(m in stderr for m in lock_markers)

                    if is_lock or now_hour == 1:
                        delay_min = 20 + random.randint(3, 9)
                        logger.info(f"APT occupé. Nouvel essai dans ~{delay_min} min.")
                        self.after(delay_min * 60 * 1000, self.check_updates)
                        rescheduled = True
                        return
                    else:
                        logger.error(f"Erreur apt update: {stderr or stdout or 'aucun message'}")
                        self.after(0, self.hide_update_arrow)
                        return

                logger.info("Mise à jour de la liste des paquets terminée")

                lst = subprocess.run(
                    ["apt", "list", "--upgradable"],
                    capture_output=True,
                    text=True
                )
                up_lines = [ln for ln in (lst.stdout or "").splitlines() if ln.strip() and not ln.lower().startswith("listing")]

                if len(up_lines) > 0:
                    logger.info("Mises à jour disponibles détectées")
                    self.after(0, self._auto_start_update_if_needed)
                else:
                    logger.info("Aucune mise à jour disponible")
                    self.after(0, self.hide_update_arrow)

            except Exception as e:
                logger.error(f"Erreur lors de la vérification des mises à jour : {e}\n{traceback.format_exc()}")
                self.after(0, self.hide_update_arrow)

            finally:
                if not rescheduled:
                    self.after(CHECK_INTERVAL_MS, self.check_updates)

        threading.Thread(target=run_check, daemon=True).start()

    def _auto_start_update_if_needed(self):
        if self.updating_in_progress:
            return
        self.show_update_arrow()
        if self.update_arrow:
            self.is_animating = True
            self.rotation_angle = 0
            self.animate_icon()
        self._run_update_async()

    def _run_update_async(self):
        if self.updating_in_progress:
            return
        self.updating_in_progress = True
        logger.info("Lancement de la mise à jour système...")

        if TEST_MODE != "off":
            def fake_update():
                time.sleep(2)
                if TEST_RESULT == "success":
                    logger.info("[TEST MODE] Update simulated SUCCESS")
                    self.after(0, self._on_update_success)
                else:
                    logger.info("[TEST MODE] Update simulated FAILURE")
                    self.after(0, self._on_update_end_no_success)
                self.updating_in_progress = False
            threading.Thread(target=fake_update, daemon=True).start()
            return

        def run_update():
            try:
                # 'sudo' est ajouté
                process = subprocess.Popen(["sudo", "apt", "upgrade", "-y"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                process.wait()
                if process.returncode == 0:
                    logger.info("Mise à jour système terminée avec succès")
                    self.after(0, self._on_update_success)
                else:
                    stderr = process.stderr.read().decode(errors='ignore')
                    logger.error(f"Erreur lors de la mise à jour : {stderr}")
                    self.after(0, self._on_update_end_no_success)
            except Exception as e:
                logger.error(f"Exception pendant la mise à jour : {e}")
                self.after(0, self._on_update_end_no_success)
            finally:
                self.updating_in_progress = False

        threading.Thread(target=run_update, daemon=True).start()

    def _on_update_success(self):
        self.is_animating = False
        try:
            self.update_idletasks()
            main_x = self.winfo_x()
            main_y = self.winfo_y()

            bubble_x = main_x
            bubble_y = max(0, main_y - (BULLE_H + 12) - 2)

            tailx = None
            try:
                if self.update_arrow:
                    cx, cy = self.canvas.coords(self.update_arrow)
                    tailx = int(cx)
            except Exception as e:
                logger.error(f"Calc tailx error: {e}")
                tailx = None

            cmd = [
                "/usr/bin/python3", os.path.join(BASE_DIR, "bubble_helper.py"),
                "--x", str(bubble_x), "--y", str(bubble_y),
                "--w", str(BULLE_W), "--h", str(BULLE_H - 12), # H corps
                "--ms", str(BULLE_HOLD_MS),
                "--fadein", str(BULLE_FADEIN_MS),
                "--fadeout", str(BULLE_FADEOUT_MS),
                "--text", "Mise à jour effectuée avec succès !"
            ]
            if tailx is not None:
                tailx = max(18, min(BULLE_W - 18, tailx))
                cmd += ["--tailx", str(tailx)]

            # Utilise l'environnement de l'utilisateur courant (arut16)
            subprocess.Popen(cmd, env={**os.environ, "DISPLAY": ":0"})
        except Exception as e:
            logger.error(f"Erreur lancement bubble_helper: {e}")

        total_ms = BULLE_FADEIN_MS + BULLE_HOLD_MS + BULLE_FADEOUT_MS
        self.after(total_ms, self.hide_update_arrow)

    def _on_update_end_no_success(self):
        self.is_animating = False
        self.hide_update_arrow()

if __name__ == "__main__":
    app = DraggableWindow()
    app.mainloop()
