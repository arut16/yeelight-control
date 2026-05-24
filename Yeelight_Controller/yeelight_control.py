import os
import sys
import pygame as pg
import numpy as np
import ffmpeg
from yeelight import Bulb, BulbException
from yeelight.enums import SceneClass
import threading
import logging
import logging.handlers
import random
import math
import time
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import subprocess
from solar_conditions import is_solar_condition_active

# --- MODULE ASTRAL (Optionnel pour stabilité) ---
try:
    from astral import LocationInfo
    from astral.sun import sun
    ASTRAL_AVAILABLE = True
except ImportError:
    ASTRAL_AVAILABLE = False

# Définir DISPLAY=:0 pour éviter de le faire manuellement via PuTTY
os.environ["DISPLAY"] = ":0"

# Configuration des logs avec rotation
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_PARENT_DIR = os.path.dirname(PROJECT_DIR)
REPO_DIR = PROJECT_PARENT_DIR if os.path.isdir(os.path.join(PROJECT_PARENT_DIR, '.git')) else PROJECT_DIR
CONFIG_DIR = os.path.join(PROJECT_DIR, 'Config')
LOGS_DIR = os.path.join(PROJECT_DIR, 'Logs')
ICONS_DIR = os.path.join(PROJECT_DIR, 'Icons')
SOUNDS_DIR = os.path.join(PROJECT_DIR, 'sounds')
VIDEOS_DIR = os.path.join(PROJECT_DIR, 'Videos')

LOG_FILENAME = os.path.join(LOGS_DIR, 'yeelight_control.log')
MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 Mo
handler = logging.handlers.RotatingFileHandler(LOG_FILENAME, maxBytes=MAX_LOG_SIZE, backupCount=1, encoding="utf-8")
handler.setLevel(logging.INFO)
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# Chemin vers l'environnement virtuel
venv_path = os.path.expanduser("~/YeelightDomEnv")
site_packages_path = os.path.join(venv_path, "lib", "python3.11", "site-packages")
sys.path.insert(0, site_packages_path)

# Fichiers de configuration
LAMP_IPS_FILE = os.path.join(CONFIG_DIR, 'lamp_ips.json')
LAMP_CONFIG_FILE = os.path.join(CONFIG_DIR, 'lamp_config.json')
SCREENSAVERS_SET_FILE = os.path.join(CONFIG_DIR, 'screensavers_set.json')

# --- AJOUTS AUTOMATISATIONS ---
AUTOMATIONS_FILE = os.path.join(CONFIG_DIR, 'automations.json')
AUTOMATIONS_SCRIPT = os.path.join(PROJECT_DIR, 'automatisations.py')
CPU_BUBBLE_SCRIPT = os.path.join(PROJECT_DIR, 'cpu_temp_bubble.py')
VERSION_FILE = os.path.join(PROJECT_DIR, 'VERSION')

# Scripts
UPDATE_LAMP_IPS_SCRIPT = os.path.join(PROJECT_DIR, 'update_lamp_ips.py')

# --- CONFIGURATION GEO (Optimisation V26: Une seule fois) ---
LATITUDE = 43.659
LONGITUDE = 7.123
CITY_INFO = None
if ASTRAL_AVAILABLE:
    CITY_INFO = LocationInfo("Villeneuve-Loubet", "France", "Europe/Paris", LATITUDE, LONGITUDE)

# --- CONFIGURATION VIDÉOS (IDENTIQUE V10.1) ---
VIDEO_SEGMENT_DURATION = 300 
LAVA_LAMP_VIDEO_PATH = os.path.join(VIDEOS_DIR, "lava_lamp.mp4")
LAVA_LAMP_DURATION = 16200 
PARTICLES_VIDEO_PATH = os.path.join(VIDEOS_DIR, "particles_explosions.mp4")
PARTICLES_DURATION = 36144 
NEBULA_VIDEO_PATH = os.path.join(VIDEOS_DIR, "Nebula.mp4")
NEBULA_DURATION = 36036 
TURBULENCE_VIDEO_PATH = os.path.join(VIDEOS_DIR, "Turbulence.mp4")
TURBULENCE_DURATION = 42939

# --- Gestion de la config Screensaver ---
def load_screensaver_settings():
    default_settings = {
        "matrix": True, "stars": True, "lava": True, 
        "particles": True, "nebula": True, "turbulence": True
    }
    try:
        with open(SCREENSAVERS_SET_FILE, 'r') as f:
            settings = json.load(f)
            for key in default_settings:
                if key not in settings:
                    settings[key] = True
            return settings
    except (FileNotFoundError, json.JSONDecodeError):
        logging.warning("Config screensaver non trouvée, création par défaut.")
        save_screensaver_settings(default_settings)
        return default_settings

def save_screensaver_settings(settings):
    try:
        with open(SCREENSAVERS_SET_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
        logging.info("Config screensaver sauvegardée.")
    except Exception as e:
        logging.error(f"Erreur sauvegarde screensaver: {e}")

screensaver_settings = load_screensaver_settings()

def load_project_version():
    try:
        with open(VERSION_FILE, 'r', encoding='utf-8') as f:
            version = f.read().strip()
            return version if version else '1.0'
    except Exception as e:
        logging.error(f"Erreur lecture version projet: {e}")
        return '1.0'

def run_git_command(args):
    completed = subprocess.run(
        ['git', *args],
        cwd=REPO_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or 'commande git échouée'
        raise RuntimeError(message)
    return completed.stdout.strip()

def get_upstream_ref():
    try:
        return run_git_command(['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}'])
    except RuntimeError:
        remotes = run_git_command(['remote']).splitlines()
        current_branch = run_git_command(['branch', '--show-current'])
        if not remotes or not current_branch:
            raise RuntimeError('aucune branche distante configurée')
        return f"{remotes[0]}/{current_branch}"

def get_project_version_from_ref(ref):
    try:
        version = run_git_command(['show', f'{ref}:Yeelight_Controller/VERSION']).strip()
        return version or None
    except RuntimeError as e:
        logging.error(f"Erreur lecture version distante: {e}")
        return None

def get_project_update_info():
    run_git_command(['rev-parse', '--is-inside-work-tree'])
    run_git_command(['fetch', '--prune', '--quiet'])
    upstream_ref = get_upstream_ref()
    output = run_git_command(['diff', '--name-only', f'HEAD..{upstream_ref}'])
    update_files = [line for line in output.splitlines() if line.strip()]
    return update_files, get_project_version_from_ref(upstream_ref)

def get_project_updates():
    update_files, _ = get_project_update_info()
    return update_files

def apply_project_updates():
    try:
        run_git_command(['pull', '--ff-only'])
    except RuntimeError as e:
        message = str(e)
        if any(text in message for text in ['Please commit your changes', 'Please stash your changes', 'would be overwritten by merge']):
            raise RuntimeError("Mise à jour bloquée : des modifications locales empêchent git pull. Committez ou stashez vos changements puis réessayez.")
        raise

def restart_project_processes():
    try:
        subprocess.run(['pkill', '-f', 'cpu_temp_bubble.py'], stderr=subprocess.DEVNULL)
    except Exception as e:
        logging.error(f"Erreur arrêt cpu bubble avant redémarrage: {e}")
    try:
        subprocess.Popen(['python3', CPU_BUBBLE_SCRIPT], stderr=subprocess.DEVNULL)
    except Exception as e:
        logging.error(f"Erreur redémarrage cpu bubble: {e}")
    try:
        pg.quit()
    except Exception as e:
        logging.error(f"Erreur fermeture pygame avant redémarrage: {e}")
    python_executable = sys.executable or 'python3'
    os.execvp(python_executable, [python_executable, os.path.abspath(__file__)])

PROJECT_VERSION = load_project_version()

def load_lamp_ips():
    try:
        with open(LAMP_IPS_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

LAMP_IPS = load_lamp_ips()
BULB_OBJECTS = {}

def load_lamp_config():
    default = {"lampes": {}}
    try:
        with open(LAMP_CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            lampes = data.get("lampes", {})
            if isinstance(lampes, dict):
                return {"lampes": lampes}
    except Exception:
        pass
    return default

def save_lamp_config(lampes_list):
    try:
        ordered = {item["mac"]: item["name"] for item in lampes_list if item["mac"] and item["name"]}
        with open(LAMP_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({"lampes": ordered}, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logging.error(f"Erreur sauvegarde lamp_config: {e}")

def build_lampes_from_config():
    cfg = load_lamp_config()
    result = []
    for mac, name in cfg.get("lampes", {}).items():
        result.append({"name": name, "mac": mac.upper(), "ip": LAMP_IPS.get(name, "N/A")})
    return result

def get_detected_macs():
    macs = []
    try:
        result = subprocess.run(['sudo', 'arp-scan', '--localnet'], capture_output=True, text=True, timeout=10, check=True)
        for line in result.stdout.splitlines()[2:]:
            parts = line.split('\t')
            if len(parts) >= 2:
                mac = parts[1].strip().upper()
                if mac and mac not in macs:
                    macs.append(mac)
    except Exception:
        pass
    return macs

def get_bulb(ip):
    bulb = BULB_OBJECTS.get(ip)
    if bulb is None:
        bulb = Bulb(ip)
        BULB_OBJECTS[ip] = bulb
    return bulb

# --- CACHE RÈGLES (Pour ne pas lire le disque en boucle) ---
CACHED_RULES = []
def reload_automation_rules():
    global CACHED_RULES
    try:
        if os.path.exists(AUTOMATIONS_FILE):
            with open(AUTOMATIONS_FILE, 'r') as f:
                CACHED_RULES = json.load(f)
        else:
            CACHED_RULES = []
    except:
        CACHED_RULES = []
reload_automation_rules()

# Constantes UI
SCREEN_WIDTH, SCREEN_HEIGHT = 640, 480
INACTIVITY_TIMEOUT = 300000  # 5 min (Remis à 5min comme demandé implicitement, V10.1 avait 10000ms soit 10s ?)
STAR_COLORS = [(0, 0, 255), (255, 165, 0), (255, 0, 0), (255, 255, 0)]
FADE_DURATION = 2000
FPS = 30
IDLE_FPS = 12
VIDEO_FPS = 25
CLOSE_BUTTON_SIZE = 40
SETTINGS_BUTTON_SIZE = 40
CONFIRM_WIDTH, CONFIRM_HEIGHT = 350, 120
CONFIG_SAVED_WIDTH, CONFIG_SAVED_HEIGHT = 200, 100
UPDATE_MODAL_WIDTH, UPDATE_MODAL_HEIGHT = 500, 280
UPDATE_BTN_WIDTH, UPDATE_BTN_HEIGHT = 150, 40

# Fenêtre Paramètres
SETTINGS_MODAL_WIDTH, SETTINGS_MODAL_HEIGHT = 550, 400 
SETTINGS_BTN_WIDTH, SETTINGS_BTN_HEIGHT = 220, 50
SETTINGS_CHECKBOX_SIZE = 24
PREVIEW_BTN_WIDTH, PREVIEW_BTN_HEIGHT = 60, 24 

# Effets Visuels
RIPPLE_DURATION = 1500
RIPPLE_COUNT = 3
RIPPLE_THICKNESS = 4
BUTTON_EXPAND_SIZE = 6
BUTTON_EXPAND_DURATION = 150
HALO_SIZE = 40

MATRIX_FONT_SIZE = 18
BUTTON_WIDTH, BUTTON_HEIGHT = 315, 100
BUTTON_SPACING = 10
CHECK_INTERVAL = 5
CHECK_INTERVAL_SCREENSAVER = 10
CHECK_INTERVAL_ERROR = 15
MAX_FAILURES = 5
DOUBLE_CLICK_DELAY = 300
POPUP_FADE_DURATION = 2000
WIFI_OFFLINE_TIMEOUT = 300

WINDOWED_WIDTH, WINDOWED_HEIGHT = BUTTON_WIDTH, BUTTON_HEIGHT

# Variables globales
lampe_states = {nom: "off" for nom in LAMP_IPS.keys()}
lampe_modes = {nom: "normal" for nom in LAMP_IPS.keys()}
failure_counts = {nom: 0 for nom in LAMP_IPS.keys()}
screensaver_active = False
fading = False
fade_start_time = 0
last_activity = time.time()
show_confirm = False
show_settings_modal = False
show_edit_lamps_modal = False
show_lamp_detail_modal = False
show_mac_list_modal = False
dragging_lamp_index = None
drag_mouse_offset = (0, 0)
editor_drag_last_target = None
selected_lamp_index = None
lampes_editor_data = build_lampes_from_config()
detected_macs = []
editing_lamp_name = False
show_update_modal = False
update_files = []
update_version = None
updating_project = False
editing_config = False
config_saved = False
config_process = None
keyboard_process = None
automation_process = None # Ajout V26
ripple_active = False
ripple_start_time = 0
ripple_pos = (0, 0)
ripple_button = None
button_expand_active = False
button_expand_start_time = 0
button_expand_name = None
is_fullscreen = True
current_screensaver = 0
video_stream = None
last_click_time = {nom: 0 for nom in LAMP_IPS.keys()}
click_count = {nom: 0 for nom in LAMP_IPS.keys()}
last_click_pos = {nom: (0, 0) for nom in LAMP_IPS.keys()}
last_click_sound_time = 0
popup_messages = {}
all_lamps_offline_start_time = None

# Variables Preview
preview_running = False
preview_start_time = 0

pg.init()
audio_enabled = True
try:
    pg.mixer.init(frequency=48000, size=-16, channels=2)
    click_sound = pg.mixer.Sound(os.path.join(SOUNDS_DIR, "click.wav"))
    click_sound.set_volume(0.9)
    light_on_sound = pg.mixer.Sound(os.path.join(SOUNDS_DIR, "light_on.wav"))
    light_on_sound.set_volume(0.9)
    light_off_sound = pg.mixer.Sound(os.path.join(SOUNDS_DIR, "light_off.wav"))
    light_off_sound.set_volume(0.9)
    pg.mixer.set_num_channels(8)
except Exception as e:
    audio_enabled = False
    click_sound = None
    light_on_sound = None
    light_off_sound = None
    logging.error(f"Audio indisponible (mixer/sounds): {e}")

def play_sound(sound):
    if audio_enabled and sound is not None:
        try:
            sound.play()
        except Exception as e:
            logging.error(f"Erreur lecture son: {e}")

pg.display.set_mode((1, 1))
yeelight_taskbar_icon = pg.image.load(os.path.join(ICONS_DIR, "yeelight_logo_32x32.png")).convert_alpha()
pg.display.set_icon(yeelight_taskbar_icon)

screen = pg.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pg.FULLSCREEN)
pg.mouse.set_visible(False)
pg.display.set_caption("Contrôle des lampes Yeelight")
clock = pg.time.Clock()

black_surface = pg.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
black_surface.fill((0, 0, 0))
fade_surface = pg.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
fade_surface.fill((0, 0, 0))

# Images
bulb_on_icon = pg.image.load(os.path.join(ICONS_DIR, "bulb_on.png")).convert_alpha()
bulb_off_icon = pg.image.load(os.path.join(ICONS_DIR, "bulb_off.png")).convert_alpha()
arrow_back_icon = pg.image.load(os.path.join(ICONS_DIR, "arrow_back_icon.png")).convert_alpha()
raspberry_pi_icon = pg.image.load(os.path.join(ICONS_DIR, "raspberry-pi_logo_button.png")).convert_alpha()
yeelight_icon = pg.image.load(os.path.join(ICONS_DIR, "yeelight_logo_button.png")).convert_alpha()
settings_icon = pg.image.load(os.path.join(ICONS_DIR, "settings_icon.png")).convert_alpha()
settings_icon = pg.transform.scale(settings_icon, (SETTINGS_BUTTON_SIZE, SETTINGS_BUTTON_SIZE))

# Polices
font = pg.font.SysFont("Arial", 28, bold=True)
small_font = pg.font.SysFont("Arial", 18, bold=True)
popup_font = pg.font.SysFont("Arial", 12, bold=True)
center_popup_font = pg.font.SysFont("Arial", 24, bold=True)
checkbox_font = pg.font.SysFont("Arial", 20, bold=False)
preview_font = pg.font.SysFont("Arial", 12, bold=True) 
matrix_font = pg.font.Font(os.path.join(PROJECT_DIR, 'font', 'ms mincho.ttf'), MATRIX_FONT_SIZE)
katakana = [chr(int('0x30a0', 16) + i) for i in range(96)]
green_katakana = [matrix_font.render(char, True, (40, random.randrange(160, 256), 40)) for char in katakana]
lightgreen_katakana = [matrix_font.render(char, True, pg.Color('lightgreen')) for char in katakana]

def reload_ui_from_config():
    global LAMP_IPS, BULB_OBJECTS, boutons, click_count, last_click_time, last_click_pos, lampe_states, lampe_modes, failure_counts
    logging.info("Rechargement UI...")
    LAMP_IPS.clear()
    LAMP_IPS.update(load_lamp_ips())
    BULB_OBJECTS.clear()
    boutons.clear()
    click_count.clear()
    last_click_time.clear()
    last_click_pos.clear()
    lampe_states.clear()
    lampe_modes.clear()
    failure_counts.clear()
    
    total_width_per_row = BUTTON_WIDTH + BUTTON_SPACING
    total_cols = 2
    start_x = 0
    start_y = 0
    row, col = 0, 0
    
    for nom, ip in LAMP_IPS.items():
        x = start_x + col * (total_width_per_row)
        y = start_y + row * (BUTTON_HEIGHT + BUTTON_SPACING)
        rect = pg.Rect(x, y, BUTTON_WIDTH, BUTTON_HEIGHT)
        text = font.render(nom, True, (255, 255, 255))
        text_rect = text.get_rect(center=(rect.x + rect.width // 2, rect.y + rect.height // 2))
        boutons[nom] = {
            "rect": rect, "ip": ip, "text": text, "text_rect": text_rect,
            "original_rect": rect.copy(), "current_color": (150, 150, 150),
            "target_color": (150, 150, 150), "transition_start_time": None, "transition_duration": 1500
        }
        click_count[nom] = 0
        last_click_time[nom] = 0
        last_click_pos[nom] = (0, 0)
        lampe_states[nom] = "unknown"
        lampe_modes[nom] = "normal"
        failure_counts[nom] = 0
        col += 1
        if col >= total_cols:
            col = 0
            row += 1

boutons = {}
reload_ui_from_config()


def get_editor_grid_geometry():
    grid_cols = 2
    grid_rows = 4
    card_w = (settings_modal_rect.width - 70) // grid_cols
    card_h = 72
    gap_x = 10
    gap_y = 12
    origin_x = settings_modal_rect.x + 20
    origin_y = settings_modal_rect.y + 70
    return origin_x, origin_y, card_w, card_h, gap_x, gap_y, grid_cols, grid_rows

def get_editor_card_rect(index):
    origin_x, origin_y, card_w, card_h, gap_x, gap_y, grid_cols, _ = get_editor_grid_geometry()
    col = index % grid_cols
    row = index // grid_cols
    x = origin_x + col * (card_w + gap_x)
    y = origin_y + row * (card_h + gap_y)
    return pg.Rect(x, y, card_w, card_h)

def get_grid_index_from_pos(pos, item_count):
    if item_count <= 0:
        return None
    origin_x, origin_y, card_w, card_h, gap_x, gap_y, grid_cols, grid_rows = get_editor_grid_geometry()
    total_w = grid_cols * card_w + (grid_cols - 1) * gap_x
    total_h = grid_rows * card_h + (grid_rows - 1) * gap_y
    grid_rect = pg.Rect(origin_x, origin_y, total_w, total_h)
    if not grid_rect.collidepoint(pos):
        return None
    rel_x = pos[0] - origin_x
    rel_y = pos[1] - origin_y
    col = min(grid_cols - 1, max(0, rel_x // (card_w + gap_x)))
    row = min(grid_rows - 1, max(0, rel_y // (card_h + gap_y)))
    idx = int(row * grid_cols + col)
    return min(item_count - 1, idx)

back_button_rect = pg.Rect(0 + BUTTON_WIDTH + BUTTON_SPACING, 0 + 3 * (BUTTON_HEIGHT + BUTTON_SPACING), BUTTON_WIDTH, BUTTON_HEIGHT)
close_button_rect = pg.Rect(SCREEN_WIDTH - CLOSE_BUTTON_SIZE - 10, SCREEN_HEIGHT - CLOSE_BUTTON_SIZE - 10, CLOSE_BUTTON_SIZE, CLOSE_BUTTON_SIZE)
settings_button_rect = pg.Rect(10, SCREEN_HEIGHT - SETTINGS_BUTTON_SIZE - 10, SETTINGS_BUTTON_SIZE, SETTINGS_BUTTON_SIZE)

confirm_rect = pg.Rect((SCREEN_WIDTH - CONFIRM_WIDTH) // 2, (SCREEN_HEIGHT - CONFIRM_HEIGHT) // 2, CONFIRM_WIDTH, CONFIRM_HEIGHT)
yes_button_rect = pg.Rect(confirm_rect.x + 60, confirm_rect.y + 70, 100, 40)
no_button_rect = pg.Rect(confirm_rect.x + 190, confirm_rect.y + 70, 100, 40)
confirm_text = small_font.render("Fermer Yeelight_Controller ?", True, (255, 255, 255))
yes_text = small_font.render("Oui", True, (255, 255, 255))
no_text = small_font.render("Non", True, (255, 255, 255))

# --- Fenêtre Paramètres ---
settings_modal_rect = pg.Rect((SCREEN_WIDTH - SETTINGS_MODAL_WIDTH) // 2, (SCREEN_HEIGHT - SETTINGS_MODAL_HEIGHT) // 2, SETTINGS_MODAL_WIDTH, SETTINGS_MODAL_HEIGHT)
settings_title_text = font.render("Paramètres", True, (255, 255, 255))
settings_title_rect = settings_title_text.get_rect(center=(settings_modal_rect.centerx, settings_modal_rect.y + 30))

btn_maj_ip_rect = pg.Rect(settings_modal_rect.x + 20, settings_modal_rect.y + 80, SETTINGS_BTN_WIDTH, SETTINGS_BTN_HEIGHT)
text_maj_ip = small_font.render("MAJ @IP lampes", True, (255, 255, 255))
text_maj_ip_rect = text_maj_ip.get_rect(center=btn_maj_ip_rect.center)

btn_edit_config_rect = pg.Rect(settings_modal_rect.x + 20, settings_modal_rect.y + 160, SETTINGS_BTN_WIDTH, SETTINGS_BTN_HEIGHT)
text_edit_config = small_font.render("Editer Lampes", True, (255, 255, 255))
text_edit_config_rect = text_edit_config.get_rect(center=btn_edit_config_rect.center)
btn_close_submenu_rect = pg.Rect(settings_modal_rect.right - 50, settings_modal_rect.y + 10, 35, 30)

# --- AJOUT BOUTON AUTOMATISATIONS ---
btn_auto_rect = pg.Rect(settings_modal_rect.x + 20, settings_modal_rect.y + 240, SETTINGS_BTN_WIDTH, SETTINGS_BTN_HEIGHT)
text_auto = small_font.render("Automatisations", True, (255, 255, 255))
text_auto_rect = text_auto.get_rect(center=btn_auto_rect.center)

btn_check_updates_rect = pg.Rect(settings_modal_rect.x + 20, settings_modal_rect.y + 305, SETTINGS_BTN_WIDTH, 45)
text_check_updates = small_font.render("Vérifier mises à jour", True, (255, 255, 255))
text_check_updates_rect = text_check_updates.get_rect(center=btn_check_updates_rect.center)
settings_version_text = preview_font.render(f"Version {PROJECT_VERSION}", True, (220, 220, 220))
settings_version_rect = settings_version_text.get_rect(bottomleft=(settings_modal_rect.x + 12, settings_modal_rect.bottom - 10))

# Fenêtre MAJ projet
update_modal_rect = pg.Rect((SCREEN_WIDTH - UPDATE_MODAL_WIDTH) // 2, (SCREEN_HEIGHT - UPDATE_MODAL_HEIGHT) // 2, UPDATE_MODAL_WIDTH, UPDATE_MODAL_HEIGHT)
update_title_text = font.render("Mises à jour disponibles", True, (255, 255, 255))
update_title_rect = update_title_text.get_rect(center=(update_modal_rect.centerx, update_modal_rect.y + 30))
update_info_text = small_font.render("Fichiers à mettre à jour :", True, (255, 255, 255))
update_info_rect = update_info_text.get_rect(topleft=(update_modal_rect.x + 25, update_modal_rect.y + 85))
btn_apply_update_rect = pg.Rect(update_modal_rect.x + 90, update_modal_rect.bottom - 60, UPDATE_BTN_WIDTH, UPDATE_BTN_HEIGHT)
btn_cancel_update_rect = pg.Rect(update_modal_rect.x + 260, update_modal_rect.bottom - 60, UPDATE_BTN_WIDTH, UPDATE_BTN_HEIGHT)
text_apply_update = small_font.render("Mettre à jour", True, (255, 255, 255))
text_apply_update_rect = text_apply_update.get_rect(center=btn_apply_update_rect.center)
text_cancel_update = small_font.render("Annuler", True, (255, 255, 255))
text_cancel_update_rect = text_cancel_update.get_rect(center=btn_cancel_update_rect.center)

# Positionnement Checkboxes et Boutons Aperçu
check_start_x = settings_modal_rect.x + 270
check_start_y = settings_modal_rect.y + 80
check_spacing = 40
preview_offset_x = 160

check_matrix_rect = pg.Rect(check_start_x, check_start_y, SETTINGS_CHECKBOX_SIZE, SETTINGS_CHECKBOX_SIZE)
preview_matrix_rect = pg.Rect(check_start_x + preview_offset_x, check_start_y, PREVIEW_BTN_WIDTH, PREVIEW_BTN_HEIGHT)
check_stars_rect = pg.Rect(check_start_x, check_start_y + check_spacing, SETTINGS_CHECKBOX_SIZE, SETTINGS_CHECKBOX_SIZE)
preview_stars_rect = pg.Rect(check_start_x + preview_offset_x, check_start_y + check_spacing, PREVIEW_BTN_WIDTH, PREVIEW_BTN_HEIGHT)
check_lava_rect = pg.Rect(check_start_x, check_start_y + check_spacing * 2, SETTINGS_CHECKBOX_SIZE, SETTINGS_CHECKBOX_SIZE)
preview_lava_rect = pg.Rect(check_start_x + preview_offset_x, check_start_y + check_spacing * 2, PREVIEW_BTN_WIDTH, PREVIEW_BTN_HEIGHT)
check_particles_rect = pg.Rect(check_start_x, check_start_y + check_spacing * 3, SETTINGS_CHECKBOX_SIZE, SETTINGS_CHECKBOX_SIZE)
preview_particles_rect = pg.Rect(check_start_x + preview_offset_x, check_start_y + check_spacing * 3, PREVIEW_BTN_WIDTH, PREVIEW_BTN_HEIGHT)
check_nebula_rect = pg.Rect(check_start_x, check_start_y + check_spacing * 4, SETTINGS_CHECKBOX_SIZE, SETTINGS_CHECKBOX_SIZE)
preview_nebula_rect = pg.Rect(check_start_x + preview_offset_x, check_start_y + check_spacing * 4, PREVIEW_BTN_WIDTH, PREVIEW_BTN_HEIGHT)
check_turbulence_rect = pg.Rect(check_start_x, check_start_y + check_spacing * 5, SETTINGS_CHECKBOX_SIZE, SETTINGS_CHECKBOX_SIZE)
preview_turbulence_rect = pg.Rect(check_start_x + preview_offset_x, check_start_y + check_spacing * 5, PREVIEW_BTN_WIDTH, PREVIEW_BTN_HEIGHT)

text_matrix = checkbox_font.render("Matrix", True, (255, 255, 255))
text_stars = checkbox_font.render("Etoiles", True, (255, 255, 255))
text_lava = checkbox_font.render("Lava Lamp", True, (255, 255, 255))
text_particles = checkbox_font.render("Particules", True, (255, 255, 255))
text_nebula = checkbox_font.render("Nebula", True, (255, 255, 255))
text_turbulence = checkbox_font.render("Turbulence", True, (255, 255, 255))
text_preview = preview_font.render("Aperçu", True, (200, 200, 200)) 

config_saved_rect = pg.Rect((SCREEN_WIDTH - CONFIG_SAVED_WIDTH) // 2, (SCREEN_HEIGHT - CONFIG_SAVED_HEIGHT) // 2, CONFIG_SAVED_WIDTH, CONFIG_SAVED_HEIGHT)
config_saved_text = small_font.render("Sauvegardé", True, (255, 255, 255))
config_saved_text_rect = config_saved_text.get_rect(center=(config_saved_rect.x + CONFIG_SAVED_WIDTH // 2, config_saved_rect.y + 35))
config_ok_button_rect = pg.Rect(config_saved_rect.x + (CONFIG_SAVED_WIDTH - 80) // 2, config_saved_rect.y + 60, 80, 30)
config_ok_text = small_font.render("OK", True, (255, 255, 255))
config_ok_text_rect = config_ok_text.get_rect(center=config_ok_button_rect.center)

stars = []
for _ in range(200):
    angle = random.uniform(0, 2 * math.pi)
    speed = random.uniform(0.5, 2)
    color = random.choice(STAR_COLORS) if random.randint(1, 40) == 1 else (255, 255, 255)
    stars.append({"x": SCREEN_WIDTH / 2, "y": SCREEN_HEIGHT / 2, "angle": angle, "speed": speed, "color": color})

class Symbol:
    def __init__(self, x, y, speed):
        self.x, self.y = x, y
        self.speed = speed
        self.value = random.choice(green_katakana)
        self.interval = random.randrange(5, 30)
    def draw(self, color, surface):
        frames = pg.time.get_ticks()
        if not frames % self.interval:
            self.value = random.choice(green_katakana if color == 'green' else lightgreen_katakana)
        self.y = self.y + self.speed if self.y < SCREEN_HEIGHT else -MATRIX_FONT_SIZE
        surface.blit(self.value, (self.x, self.y))
class SymbolColumn:
    def __init__(self, x, y):
        self.column_height = random.randrange(8, 24)
        self.speed = random.randrange(2, 4)
        self.symbols = [Symbol(x, i, self.speed) for i in range(y, y - MATRIX_FONT_SIZE * self.column_height, -MATRIX_FONT_SIZE)]
    def draw(self, surface):
        [symbol.draw('green', surface) if i else symbol.draw('lightgreen', surface) for i, symbol in enumerate(self.symbols)]
matrix_columns = [SymbolColumn(x, random.randrange(-SCREEN_HEIGHT, 0)) for x in range(0, SCREEN_WIDTH, int(MATRIX_FONT_SIZE * 1.5))]

def start_video_screensaver():
    global video_stream, screensaver_active, fade_start_time
    video_path = LAVA_LAMP_VIDEO_PATH
    video_duration = LAVA_LAMP_DURATION
    
    if current_screensaver == 3: video_path, video_duration = PARTICLES_VIDEO_PATH, PARTICLES_DURATION
    elif current_screensaver == 4: video_path, video_duration = NEBULA_VIDEO_PATH, NEBULA_DURATION
    elif current_screensaver == 5: video_path, video_duration = TURBULENCE_VIDEO_PATH, TURBULENCE_DURATION
        
    try:
        start_time = random.randint(0, video_duration - VIDEO_SEGMENT_DURATION)
        if start_time < 0: start_time = 0
            
        video_stream = (
            ffmpeg
            .input(video_path, ss=str(start_time), hwaccel='drm') # V10.1 EXACTE
            .output('pipe:', format='rawvideo', pix_fmt='rgb24', r=VIDEO_FPS, s='640x480', t=str(VIDEO_SEGMENT_DURATION))
            .global_args('-loglevel', 'error')
            .run_async(pipe_stdout=True)
        )
        screensaver_active = True
        fade_start_time = time.time()
        logging.info(f"Video SS ({current_screensaver}) start {start_time}s")
    except ffmpeg.Error as e:
        logging.error(f"Video Error: {e.stderr.decode()}")
        screensaver_active = False

def stop_screensaver():
    global video_stream, screensaver_active
    if video_stream:
        video_stream.terminate()
        video_stream = None
    screensaver_active = False
    reset_inactivity_timer()

def stop_preview():
    global preview_running, video_stream, screensaver_active
    preview_running = False
    screensaver_active = False
    if video_stream:
        video_stream.terminate()
        video_stream = None
    logging.info("Fin de l'aperçu")

def draw_video_screensaver():
    global fade_start_time, video_stream
    if video_stream:
        try:
            raw_frame = video_stream.stdout.read(SCREEN_WIDTH * SCREEN_HEIGHT * 3)
            if raw_frame:
                if len(raw_frame) != SCREEN_WIDTH * SCREEN_HEIGHT * 3: return
                frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((SCREEN_HEIGHT, SCREEN_WIDTH, 3))
                video_frame = pg.surfarray.make_surface(frame.swapaxes(0, 1))
                full_surface.blit(video_frame, (0, 0))
            else:
                if preview_running:
                    stop_preview() 
                else:
                    stop_screensaver()
                    start_video_screensaver()
                return
        except Exception:
            if preview_running: stop_preview()
            else:
                stop_screensaver()
                start_video_screensaver()
            return
            
    # Fondu V10.1
    if video_stream:
        elapsed = (time.time() - fade_start_time) * 1000
        alpha = min(elapsed / FADE_DURATION, 1.0) * 255
        fade_surface = pg.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        fade_surface.fill((0, 0, 0))
        fade_surface.set_alpha(255 - int(alpha))
        full_surface.blit(fade_surface, (0, 0))



AUTO_STATUS_DURATION = 5
auto_status_by_button = {}

def _get_active_solar_window_end(condition_dict):
    if not ASTRAL_AVAILABLE or not CITY_INFO or not condition_dict:
        return None
    try:
        local_now = datetime.now(ZoneInfo(CITY_INFO.timezone))
        sun_times = sun(CITY_INFO.observer, date=local_now.date(), tzinfo=CITY_INFO.timezone)
        start_event, start_offset = condition_dict["start"].rsplit("_offset_", 1)
        end_event, end_offset = condition_dict["end"].rsplit("_offset_", 1)
        start_offset = int(start_offset)
        end_offset = int(end_offset)

        if start_event != end_event and start_offset <= 0 <= end_offset:
            before_offset = start_offset if start_offset <= 0 else -abs(start_offset)
            after_offset = end_offset if end_offset >= 0 else abs(end_offset)
            for event_name in (start_event, end_event):
                base_time = sun_times[event_name]
                window_start = base_time + timedelta(minutes=before_offset)
                window_end = base_time + timedelta(minutes=after_offset)
                if window_start <= local_now <= window_end:
                    return window_end
            return None

        start_dt = sun_times[start_event] + timedelta(minutes=start_offset)
        end_dt = sun_times[end_event] + timedelta(minutes=end_offset)
        if start_dt <= end_dt:
            return end_dt if start_dt <= local_now <= end_dt else None
        if local_now >= start_dt or local_now <= end_dt:
            return end_dt if local_now <= end_dt else end_dt + timedelta(days=1)
    except Exception as exc:
        logging.warning(f"Calcul fin tranche auto impossible: {exc}")
    return None

# --- LOGIQUE AUTOMATISATION (FONCTIONS) ---
def is_condition_active(condition_dict):
    if not ASTRAL_AVAILABLE or not CITY_INFO: return True 
    try:
        local_now = datetime.now(ZoneInfo(CITY_INFO.timezone))
        s = sun(CITY_INFO.observer, date=local_now.date(), tzinfo=CITY_INFO.timezone)
        return is_solar_condition_active(condition_dict, s, local_now)
    except Exception as exc:
        logging.warning(f"Condition solaire ignorée après erreur: {exc}")
        return True 

def process_automation(trigger_name, trigger_state):
    try:
        for rule in CACHED_RULES:
            if rule["trigger"] == trigger_name and rule["trigger_state"] == trigger_state:
                condition_ok = True
                condition = rule.get("condition")
                if condition:
                    condition_ok = is_condition_active(condition)

                if condition_ok:
                    target_name = rule["target"]
                    action = rule["action"]
                    if target_name in LAMP_IPS:
                        target_ip = LAMP_IPS[target_name]
                        logging.info(f"Auto: {target_name} -> {action}")
                        try:
                            t_bulb = Bulb(target_ip)
                            if action == "on":
                                t_bulb.turn_on()
                            else:
                                t_bulb.turn_off()
                            lampe_states[target_name] = action

                            end_dt = _get_active_solar_window_end(condition)
                            if end_dt:
                                auto_action = "On" if action == "on" else "Off"
                                auto_status_by_button[target_name] = {
                                    "message": f"Auto {auto_action} jusqu'à {end_dt.strftime('%Hh%M')}",
                                    "until": time.time() + AUTO_STATUS_DURATION,
                                }
                        except:
                            pass
    except:
        pass

def toggle_lampe(nom, ip):
    try:
        bulb = get_bulb(ip)
        if lampe_states[nom] == "off":
            bulb.turn_on()
            bulb.set_scene(SceneClass.CT, 6500, 100)
            lampe_states[nom] = "on"
            lampe_modes[nom] = "normal"
            play_sound(light_on_sound)
            process_automation(nom, "on") # Ajout
        else:
            bulb.turn_off()
            lampe_states[nom] = "off"
            lampe_modes[nom] = "normal"
            play_sound(light_off_sound)
            process_automation(nom, "off") # Ajout
        failure_counts[nom] = 0
        return True
    except BulbException:
        failure_counts[nom] += 1
        if failure_counts[nom] >= MAX_FAILURES: lampe_states[nom] = "error"
        return False

def toggle_night_mode(nom, ip):
    try:
        bulb = get_bulb(ip)
        if lampe_states[nom] == "off":
            bulb.turn_on()
            bulb.set_scene(SceneClass.CT, 1700, 1)
            lampe_states[nom] = "on"
            lampe_modes[nom] = "night"
            play_sound(light_on_sound)
            process_automation(nom, "on") # Ajout
        elif lampe_modes[nom] == "normal":
            bulb.set_scene(SceneClass.CT, 1700, 1)
            lampe_modes[nom] = "night"
        else:
            bulb.set_scene(SceneClass.CT, 6500, 100)
            lampe_modes[nom] = "normal"
        failure_counts[nom] = 0
        return True
    except BulbException:
        failure_counts[nom] += 1
        if failure_counts[nom] >= MAX_FAILURES: lampe_states[nom] = "error"
        return False

def check_lampe_state():
    global screensaver_active, all_lamps_offline_start_time
    while True:
        try:
            all_lamps_offline = True
            for nom, ip in LAMP_IPS.items():
                try:
                    bulb = get_bulb(ip)
                    props = bulb.get_properties()
                    if not props:
                        failure_counts[nom] += 1
                        if failure_counts[nom] >= MAX_FAILURES: lampe_states[nom] = "error"
                        continue
                    state = "on" if props.get("power") == "on" else "off"
                    ct = int(props.get("ct", 6500) or 6500)
                    bright = int(props.get("bright", 100) or 100)
                    nl_br = int(props.get("nl_br", 0) or 0)
                    active_mode = int(props.get("active_mode", 0) or 0)
                    if state == "on":
                        mode = "night" if (bright <= 10 and ct <= 3000) or (nl_br > 0 and active_mode == 1) else "normal"
                    else:
                        mode = "normal"
                    if state != lampe_states[nom] or mode != lampe_modes[nom]:
                        if state == "on" and lampe_states[nom] == "off" and screensaver_active:
                            stop_screensaver()
                        
                        # --- AJOUT AUTOMATISATION ---
                        if state != lampe_states[nom] and lampe_states[nom] != "unknown":
                            process_automation(nom, state)
                        # ----------------------------

                        lampe_states[nom] = state
                        lampe_modes[nom] = mode
                    failure_counts[nom] = 0
                    all_lamps_offline = False
                except Exception:
                    failure_counts[nom] += 1
                    if failure_counts[nom] >= MAX_FAILURES: lampe_states[nom] = "error"
            if all_lamps_offline:
                if all_lamps_offline_start_time is None: all_lamps_offline_start_time = time.time()
                elif (time.time() - all_lamps_offline_start_time) >= WIFI_OFFLINE_TIMEOUT:
                    try:
                        subprocess.run(["sudo", "ifdown", "wlan0"], check=True)
                        time.sleep(2)
                        subprocess.run(["sudo", "ifup", "wlan0"], check=True)
                        all_lamps_offline_start_time = None
                    except: pass
            else: all_lamps_offline_start_time = None
        except Exception: pass
        sleep_interval = CHECK_INTERVAL
        if screensaver_active: sleep_interval = CHECK_INTERVAL_SCREENSAVER
        if all(v >= MAX_FAILURES for v in failure_counts.values()): sleep_interval = CHECK_INTERVAL_ERROR
        time.sleep(sleep_interval)

def interpolate_color(start_color, end_color, progress):
    r = start_color[0] + (end_color[0] - start_color[0]) * progress
    g = start_color[1] + (end_color[1] - start_color[1]) * progress
    b = start_color[2] + (end_color[2] - start_color[2]) * progress
    return (int(r), int(g), int(b))

def on_button_click(nom, pos, action):
    global ripple_active, ripple_start_time, ripple_pos, ripple_button
    global button_expand_active, button_expand_start_time, button_expand_name
    global popup_messages
    ip = boutons[nom]["ip"]
    success = False
    if action == "toggle": success = toggle_lampe(nom, ip)
    elif action == "night": success = toggle_night_mode(nom, ip)
    reset_inactivity_timer()
    ripple_active = True
    ripple_start_time = time.time()
    ripple_pos = pos
    ripple_button = nom
    button_expand_active = True
    button_expand_start_time = time.time()
    button_expand_name = nom
    btn = boutons[nom]
    btn["rect"] = pg.Rect(btn["original_rect"].x - BUTTON_EXPAND_SIZE, btn["original_rect"].y - BUTTON_EXPAND_SIZE, btn["original_rect"].width + 2 * BUTTON_EXPAND_SIZE, btn["original_rect"].height + 2 * BUTTON_EXPAND_SIZE)
    btn["text_rect"] = btn["text"].get_rect(center=btn["rect"].center)
    if not success:
        popup_text = popup_font.render("Lampe temporairement indisponible.", True, (0, 0, 0))
        popup_rect = pg.Rect(0, 0, popup_text.get_width() + 10, popup_text.get_height() + 10)
        popup_rect.center = btn["rect"].center
        popup_rect.move_ip(0, 25)
        popup_messages[nom] = {"start_time": time.time(), "rect": popup_rect, "text": popup_text}

def reset_inactivity_timer():
    global last_activity
    last_activity = time.time()

def toggle_window_mode():
    global is_fullscreen, screen, editing_config, config_process, keyboard_process, automation_process
    if is_fullscreen:
        screen = pg.display.set_mode((WINDOWED_WIDTH, WINDOWED_HEIGHT), pg.RESIZABLE)
        os.environ['SDL_VIDEO_CENTERED'] = '1'
    else:
        screen = pg.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pg.FULLSCREEN)
        if editing_config:
            if config_process: config_process.terminate()
            if keyboard_process: keyboard_process.terminate()
            config_process = None
            keyboard_process = None
            try:
                subprocess.run(['python3', UPDATE_LAMP_IPS_SCRIPT], check=True, stderr=subprocess.DEVNULL)
                reload_ui_from_config()
            except Exception: pass
            editing_config = False
    is_fullscreen = not is_fullscreen
    reset_inactivity_timer()

def move_stars():
    for star in stars:
        star["x"] += math.cos(star["angle"]) * star["speed"]
        star["y"] += math.sin(star["angle"]) * star["speed"]
        if star["x"] < 0 or star["x"] > SCREEN_WIDTH or star["y"] < 0 or star["y"] > SCREEN_HEIGHT:
            star["x"], star["y"] = SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2

def fade_to_black(start_time):
    elapsed = (time.time() - start_time) * 1000
    alpha = min(elapsed / FADE_DURATION, 1.0)
    fade_surface.set_alpha(int(255 * alpha))
    return fade_surface, alpha >= 1.0

def draw_ripple():
    global ripple_active
    if ripple_active and ripple_button:
        elapsed = (time.time() - ripple_start_time) * 1000
        if elapsed <= RIPPLE_DURATION:
            btn = boutons[ripple_button]
            ripple_surface = pg.Surface((BUTTON_WIDTH + 2 * BUTTON_EXPAND_SIZE, BUTTON_HEIGHT + 2 * BUTTON_EXPAND_SIZE), pg.SRCALPHA)
            max_radius = math.hypot(BUTTON_WIDTH, BUTTON_HEIGHT) / 1.5
            for i in range(RIPPLE_COUNT):
                start_time = i * (RIPPLE_DURATION / RIPPLE_COUNT)
                prog = (elapsed - start_time) / ((RIPPLE_DURATION / RIPPLE_COUNT) * 1.5)
                if prog <= 1.0:
                    rad = prog * max_radius * (1.0 if i==0 else (0.5 if i==1 else 0.33))
                    alpha = max(0, min(255, int(255 * (1 - prog) ** 3 * (1.0 if i==0 else (0.5 if i==1 else 0.33)))))
                    pg.draw.circle(ripple_surface, (255, 255, 255, alpha), (int(ripple_pos[0]-btn["rect"].x), int(ripple_pos[1]-btn["rect"].y)), int(rad), max(1, int(RIPPLE_THICKNESS * (1.0 if i==0 else (0.5 if i==1 else 0.33)))))
            return ripple_surface
        else: ripple_active = False
    return None

def update_button_size():
    global button_expand_active, button_expand_name
    if button_expand_active and button_expand_name:
        if (time.time() - button_expand_start_time) * 1000 > BUTTON_EXPAND_DURATION:
            btn = boutons[button_expand_name]
            btn["rect"] = btn["original_rect"].copy()
            btn["text_rect"] = btn["text"].get_rect(center=btn["rect"].center)
            button_expand_active = False
            button_expand_name = None

def draw_popup_messages(surface):
    global popup_messages
    to_remove = []
    for nom, popup in popup_messages.items():
        elapsed = (time.time() - popup["start_time"]) * 1000
        if elapsed <= POPUP_FADE_DURATION:
            alpha = max(0, int(204 - (204 * elapsed / POPUP_FADE_DURATION)))
            s = pg.Surface((popup["rect"].width, popup["rect"].height), pg.SRCALPHA)
            s.fill((200, 200, 200, alpha))
            text_rect = popup["text"].get_rect(center=(popup["rect"].width // 2, popup["rect"].height // 2))
            s.blit(popup["text"], text_rect)
            surface.blit(s, popup["rect"].topleft)
        else: to_remove.append(nom)
    for nom in to_remove: del popup_messages[nom]

def show_center_popup(message, large=False):
    font_to_use = center_popup_font if large else popup_font
    padding = 20 if large else 10
    popup_text = font_to_use.render(message, True, (0, 0, 0))
    popup_rect = pg.Rect(0, 0, popup_text.get_width() + padding, popup_text.get_height() + padding)
    popup_rect.center = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
    popup_messages[f"popup_{time.time()}"] = {"start_time": time.time(), "rect": popup_rect, "text": popup_text}

def draw_update_modal(surface):
    overlay = pg.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pg.SRCALPHA)
    overlay.fill((0, 0, 0, 210))
    surface.blit(overlay, (0, 0))
    pg.draw.rect(surface, (70, 70, 70), update_modal_rect)
    pg.draw.rect(surface, (220, 220, 220), update_modal_rect, 2)
    surface.blit(update_title_text, update_title_rect)
    if update_version and update_version != PROJECT_VERSION:
        version_text = small_font.render(f"Nouvelle version {update_version}", True, (255, 230, 120))
        version_rect = version_text.get_rect(topleft=(update_modal_rect.x + 25, update_modal_rect.y + 58))
        surface.blit(version_text, version_rect)
    surface.blit(update_info_text, update_info_rect)

    max_visible_files = 6
    visible_files = update_files[:max_visible_files]
    for index, filename in enumerate(visible_files):
        file_text = checkbox_font.render(f"• {filename}", True, (230, 230, 230))
        surface.blit(file_text, (update_modal_rect.x + 40, update_modal_rect.y + 120 + (index * 22)))
    if len(update_files) > max_visible_files:
        more_text = checkbox_font.render(f"… et {len(update_files) - max_visible_files} autre(s) fichier(s)", True, (230, 230, 230))
        surface.blit(more_text, (update_modal_rect.x + 40, update_modal_rect.y + 120 + (max_visible_files * 22)))

    pg.draw.rect(surface, (0, 150, 0), btn_apply_update_rect)
    surface.blit(text_apply_update, text_apply_update_rect)
    pg.draw.rect(surface, (180, 0, 0), btn_cancel_update_rect)
    surface.blit(text_cancel_update, text_cancel_update_rect)

def draw_checkbox(surface, rect, is_checked, text_surface):
    pg.draw.rect(surface, (255, 255, 255), rect, 2)
    if is_checked:
        inner = rect.inflate(-6, -6)
        pg.draw.rect(surface, (0, 255, 0), inner)
    text_pos = (rect.right + 10, rect.centery - text_surface.get_height() // 2)
    surface.blit(text_surface, text_pos)

def draw_preview_button(surface, rect):
    pg.draw.rect(surface, (100, 100, 120), rect) # Fond gris-bleu
    pg.draw.rect(surface, (180, 180, 180), rect, 1) # Bordure claire
    text_rect = text_preview.get_rect(center=rect.center)
    surface.blit(text_preview, text_rect)

def get_halo_surface(button_rect_size, halo_rgb):
    key = (button_rect_size[0], button_rect_size[1], halo_rgb)
    cached = halo_surface_cache.get(key)
    if cached:
        return cached

    surf_w = button_rect_size[0] + (HALO_SIZE * 2)
    surf_h = button_rect_size[1] + (HALO_SIZE * 2)
    halo_surf = pg.Surface((surf_w, surf_h), pg.SRCALPHA)
    layers = 50
    for i in range(layers):
        current_size = int(HALO_SIZE * (layers - i) / layers)
        ratio = i / layers
        alpha = int(220 * (ratio ** 3))
        rect_on_surf = pg.Rect(
            HALO_SIZE - current_size,
            HALO_SIZE - current_size,
            button_rect_size[0] + (current_size * 2),
            button_rect_size[1] + (current_size * 2),
        )
        pg.draw.rect(halo_surf, (*halo_rgb, alpha), rect_on_surf, border_radius=0)

    halo_surface_cache[key] = halo_surf
    return halo_surf

def draw_single_button(surface, nom, btn, with_halo=False):
    if with_halo and lampe_states[nom] == "on":
        halo_rgb = (255, 215, 0) if lampe_modes[nom] == "normal" else (25, 25, 112)
        halo_surf = get_halo_surface((btn["rect"].width, btn["rect"].height), halo_rgb)
        surface.blit(halo_surf, (btn["rect"].x - HALO_SIZE, btn["rect"].y - HALO_SIZE))

    pg.draw.rect(surface, btn["current_color"], btn["rect"])
    icon = bulb_on_icon if lampe_states[nom] == "on" else bulb_off_icon
    surface.blit(icon, icon.get_rect(center=(btn["rect"].x + 30, btn["rect"].centery)))
    surface.blit(btn["text"], btn["text_rect"])

    hint_info = auto_status_by_button.get(nom)
    if hint_info:
        if time.time() < hint_info["until"]:
            hint_surface = popup_font.render(hint_info["message"], True, (255, 255, 255))
            hint_surface.set_alpha(175)
            hint_rect = hint_surface.get_rect(center=(btn["rect"].centerx, btn["rect"].centery + 20))
            surface.blit(hint_surface, hint_rect)
        else:
            del auto_status_by_button[nom]

    if ripple_active and nom == ripple_button:
        rip = draw_ripple()
        if rip: surface.blit(rip, btn["rect"].topleft)

# Boucle principale
running = True
threading.Thread(target=check_lampe_state, daemon=True).start()
full_surface = pg.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
fade_surface = pg.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
fade_surface.fill((0, 0, 0))
halo_surface_cache = {}

while running:
    current_time = pg.time.get_ticks()
    target_fps = FPS

    if editing_config and config_process and config_process.poll() is not None:
        if keyboard_process: keyboard_process.terminate()
        config_process = None
        keyboard_process = None
    
    # GESTION FIN PROCESSUS AUTOMATISATION (V26)
    if editing_config and automation_process and automation_process.poll() is not None:
        automation_process = None
        editing_config = False
        reload_automation_rules() # Recharger les règles
        try:
            subprocess.Popen(['python3', CPU_BUBBLE_SCRIPT], stderr=subprocess.DEVNULL)
        except: pass
        if not is_fullscreen: toggle_window_mode()

    if not is_fullscreen and pg.display.get_window_size() == (SCREEN_WIDTH, SCREEN_HEIGHT):
        is_fullscreen = True
        toggle_window_mode()

    for event in pg.event.get():
        if event.type == pg.QUIT:
            stop_screensaver()
            running = False
        elif event.type == pg.KEYDOWN and show_edit_lamps_modal and show_lamp_detail_modal and editing_lamp_name and selected_lamp_index is not None:
            current_name = lampes_editor_data[selected_lamp_index]["name"]
            if event.key == pg.K_RETURN:
                editing_lamp_name = False
                save_lamp_config(lampes_editor_data)
                reload_ui_from_config()
            elif event.key == pg.K_BACKSPACE:
                lampes_editor_data[selected_lamp_index]["name"] = current_name[:-1]
            else:
                if event.unicode and event.unicode.isprintable():
                    lampes_editor_data[selected_lamp_index]["name"] = current_name + event.unicode
        elif event.type == pg.MOUSEBUTTONDOWN:
            pos = event.pos
            if pg.time.get_ticks() - last_click_sound_time > 100:
                play_sound(click_sound)
                last_click_sound_time = pg.time.get_ticks()
            if not is_fullscreen: pos = (pos[0] + back_button_rect.x, pos[1] + back_button_rect.y)
            
            if preview_running:
                stop_preview()
            
            elif screensaver_active: stop_screensaver()
            elif show_update_modal:
                if btn_apply_update_rect.collidepoint(pos):
                    updating_project = True
                    try:
                        apply_project_updates()
                        restart_project_processes()
                    except Exception as e:
                        updating_project = False
                        show_update_modal = False
                        logging.error(f"Erreur mise à jour projet: {e}")
                        show_center_popup("Erreur mise à jour")
                elif btn_cancel_update_rect.collidepoint(pos) or not update_modal_rect.collidepoint(pos):
                    show_update_modal = False
                    update_files = []
                    update_version = None
            elif show_confirm:
                if yes_button_rect.collidepoint(pos): stop_screensaver(); running = False
                elif no_button_rect.collidepoint(pos): show_confirm = False
            elif config_saved:
                if config_ok_button_rect.collidepoint(pos): config_saved = False
            elif show_edit_lamps_modal and is_fullscreen:
                if btn_close_submenu_rect.collidepoint(pos):
                    show_edit_lamps_modal = False
                    show_lamp_detail_modal = False
                    show_mac_list_modal = False
                    selected_lamp_index = None
                    dragging_lamp_index = None
                else:
                    if show_mac_list_modal and selected_lamp_index is not None:
                        mac_y_start = settings_modal_rect.y + 145
                        for i, mac in enumerate(detected_macs):
                            r = pg.Rect(settings_modal_rect.x + 50, mac_y_start + i * 28, settings_modal_rect.width - 100, 24)
                            if r.collidepoint(pos):
                                lampes_editor_data[selected_lamp_index]["mac"] = mac
                                save_lamp_config(lampes_editor_data)
                                show_mac_list_modal = False
                                break
                    elif show_lamp_detail_modal and selected_lamp_index is not None:
                        name_rect = pg.Rect(settings_modal_rect.x + 60, settings_modal_rect.y + 90, settings_modal_rect.width - 120, 38)
                        mac_rect = pg.Rect(settings_modal_rect.x + 60, settings_modal_rect.y + 145, settings_modal_rect.width - 120, 38)
                        if name_rect.collidepoint(pos):
                            try:
                                keyboard_height = SCREEN_HEIGHT // 3
                                keyboard_process = subprocess.Popen(['onboard', '--size', f'{SCREEN_WIDTH}x{keyboard_height}'], stderr=subprocess.DEVNULL)
                                editing_lamp_name = True
                            except Exception:
                                pass
                        elif mac_rect.collidepoint(pos):
                            detected_macs = get_detected_macs() or [l["mac"] for l in lampes_editor_data if l["mac"]]
                            show_mac_list_modal = True
                    else:
                        for i, lamp in enumerate(lampes_editor_data):
                            card_rect = get_editor_card_rect(i)
                            drag_handle = pg.Rect(card_rect.x + 8, card_rect.y + 12, 24, 26)
                            if drag_handle.collidepoint(pos):
                                dragging_lamp_index = i
                                editor_drag_last_target = i
                                drag_mouse_offset = (pos[0] - card_rect.x, pos[1] - card_rect.y)
                                break
                            if card_rect.collidepoint(pos):
                                selected_lamp_index = i
                                show_lamp_detail_modal = True
                                show_mac_list_modal = False
                                break
            elif show_settings_modal and is_fullscreen:
                if btn_maj_ip_rect.collidepoint(pos):
                    try:
                        subprocess.run(['python3', UPDATE_LAMP_IPS_SCRIPT], check=True, stderr=subprocess.DEVNULL)
                        reload_ui_from_config()
                        popup_text = popup_font.render("Mise à jour effectuée !", True, (0, 0, 0))
                        popup_rect = pg.Rect(0, 0, popup_text.get_width() + 10, popup_text.get_height() + 10)
                        popup_rect.center = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
                        popup_messages["update_ok"] = {"start_time": time.time(), "rect": popup_rect, "text": popup_text}
                    except Exception as e: logging.error(f"MAJ Error: {e}")
                    show_settings_modal = False
                elif btn_edit_config_rect.collidepoint(pos):
                    show_edit_lamps_modal = True
                    show_lamp_detail_modal = False
                    show_mac_list_modal = False
                    selected_lamp_index = None
                    lampes_editor_data = build_lampes_from_config()
                
                # --- AJOUT CLIC AUTOMATISATION ---
                elif btn_auto_rect.collidepoint(pos):
                    show_settings_modal = False
                    if not editing_config:
                        toggle_window_mode()
                        try:
                            subprocess.run(["pkill", "-f", "cpu_temp_bubble.py"], stderr=subprocess.DEVNULL)
                            automation_process = subprocess.Popen(['python3', AUTOMATIONS_SCRIPT], stderr=subprocess.DEVNULL)
                            editing_config = True 
                        except Exception as e: logger.error(f"Erreur lancement auto script: {e}")
                # ---------------------------------

                elif btn_check_updates_rect.collidepoint(pos):
                    try:
                        update_files, update_version = get_project_update_info()
                        if update_files:
                            show_update_modal = True
                        else:
                            update_version = None
                            show_center_popup("Aucune mise à jour", large=True)
                    except Exception as e:
                        logging.error(f"Erreur vérification mises à jour: {e}")
                        show_settings_modal = False
                        show_center_popup("Erreur vérification MAJ")

                elif check_matrix_rect.collidepoint(pos):
                    screensaver_settings["matrix"] = not screensaver_settings["matrix"]
                    save_screensaver_settings(screensaver_settings)
                elif check_stars_rect.collidepoint(pos):
                    screensaver_settings["stars"] = not screensaver_settings["stars"]
                    save_screensaver_settings(screensaver_settings)
                elif check_lava_rect.collidepoint(pos):
                    screensaver_settings["lava"] = not screensaver_settings["lava"]
                    save_screensaver_settings(screensaver_settings)
                elif check_particles_rect.collidepoint(pos):
                    screensaver_settings["particles"] = not screensaver_settings["particles"]
                    save_screensaver_settings(screensaver_settings)
                elif check_nebula_rect.collidepoint(pos):
                    screensaver_settings["nebula"] = not screensaver_settings["nebula"]
                    save_screensaver_settings(screensaver_settings)
                elif check_turbulence_rect.collidepoint(pos):
                    screensaver_settings["turbulence"] = not screensaver_settings["turbulence"]
                    save_screensaver_settings(screensaver_settings)
                
                elif preview_matrix_rect.collidepoint(pos):
                    current_screensaver = 1
                    preview_running = True
                    screensaver_active = True
                    preview_start_time = time.time()
                elif preview_stars_rect.collidepoint(pos):
                    current_screensaver = 0
                    preview_running = True
                    screensaver_active = True
                    preview_start_time = time.time()
                elif preview_lava_rect.collidepoint(pos):
                    current_screensaver = 2
                    preview_running = True
                    screensaver_active = True
                    preview_start_time = time.time()
                    start_video_screensaver()
                elif preview_particles_rect.collidepoint(pos):
                    current_screensaver = 3
                    preview_running = True
                    screensaver_active = True
                    preview_start_time = time.time()
                    start_video_screensaver()
                elif preview_nebula_rect.collidepoint(pos):
                    current_screensaver = 4
                    preview_running = True
                    screensaver_active = True
                    preview_start_time = time.time()
                    start_video_screensaver()
                elif preview_turbulence_rect.collidepoint(pos):
                    current_screensaver = 5
                    preview_running = True
                    screensaver_active = True
                    preview_start_time = time.time()
                    start_video_screensaver()

                elif not settings_modal_rect.collidepoint(pos): show_settings_modal = False
            else:
                if settings_button_rect.collidepoint(pos) and is_fullscreen:
                    show_settings_modal = True
                elif back_button_rect.collidepoint(pos):
                    toggle_window_mode()
                elif close_button_rect.collidepoint(pos) and is_fullscreen:
                    show_confirm = True
                else:
                    for nom, btn in boutons.items():
                        if btn["rect"].collidepoint(pos):
                            click_count[nom] += 1
                            last_click_pos[nom] = pos
                            if click_count[nom] == 1:
                                last_click_time[nom] = current_time
                            elif click_count[nom] == 2 and (current_time - last_click_time[nom]) < DOUBLE_CLICK_DELAY:
                                on_button_click(nom, pos, "night")
                                click_count[nom] = 0
                            break
        elif event.type == pg.MOUSEBUTTONUP:
            if dragging_lamp_index is not None:
                dragging_lamp_index = None
                editor_drag_last_target = None
        elif event.type == pg.MOUSEMOTION:
            pos = event.pos
            if show_edit_lamps_modal and dragging_lamp_index is not None:
                target_index = get_grid_index_from_pos(pos, len(lampes_editor_data))
                if target_index is not None and target_index != dragging_lamp_index:
                    item = lampes_editor_data.pop(dragging_lamp_index)
                    lampes_editor_data.insert(target_index, item)
                    dragging_lamp_index = target_index
                    if editor_drag_last_target != target_index:
                        editor_drag_last_target = target_index
                        save_lamp_config(lampes_editor_data)
                        reload_ui_from_config()
        elif event.type == pg.KEYDOWN:
            if preview_running:
                stop_preview()
            elif screensaver_active: stop_screensaver(); play_sound(click_sound)
        elif event.type == pg.VIDEORESIZE and not is_fullscreen:
            WINDOWED_WIDTH, WINDOWED_HEIGHT = event.size
            screen = pg.display.set_mode((WINDOWED_WIDTH, WINDOWED_HEIGHT), pg.RESIZABLE)

    for nom in boutons:
        if click_count[nom] == 1 and (current_time - last_click_time[nom]) >= DOUBLE_CLICK_DELAY:
            on_button_click(nom, last_click_pos[nom], "toggle")
            click_count[nom] = 0

    if not screensaver_active and not fading and is_fullscreen and not show_settings_modal and not show_update_modal and (time.time() - last_activity) * 1000 >= INACTIVITY_TIMEOUT:
        available_sa = []
        if screensaver_settings["stars"]: available_sa.append(0)
        if screensaver_settings["matrix"]: available_sa.append(1)
        if screensaver_settings["lava"]: available_sa.append(2)
        if screensaver_settings["particles"]: available_sa.append(3)
        if screensaver_settings["nebula"]: available_sa.append(4)
        if screensaver_settings["turbulence"]: available_sa.append(5)
        
        if available_sa:
            fading = True
            fade_start_time = time.time()
            current_screensaver = random.choice(available_sa)
        else:
            reset_inactivity_timer()

    update_button_size()
    full_surface.fill((50, 50, 50))

    if preview_running and (time.time() - preview_start_time > 10):
        stop_preview()

    if preview_running:
        full_surface.fill((0, 0, 0))
        if current_screensaver >= 2:
            target_fps = VIDEO_FPS
        if current_screensaver == 0:
            move_stars()
            for s in stars: pg.draw.circle(full_surface, s["color"], (int(s["x"]), int(s["y"])), 2)
        elif current_screensaver == 1:
            for column in matrix_columns:
                column.draw(full_surface)
        elif current_screensaver >= 2: draw_video_screensaver()
        
        if is_fullscreen: screen.blit(full_surface, (0, 0))
        pg.display.flip()
        clock.tick(target_fps)
        continue 

    if not screensaver_active and not fading:
        if not ripple_active and not button_expand_active and not popup_messages and not show_confirm and not show_settings_modal and not show_update_modal:
            target_fps = IDLE_FPS
        for nom, btn in boutons.items():
            if lampe_states[nom] != "on":
                if lampe_states[nom] == "error": target = (255, 0, 0)
                else: target = (150, 150, 150)
                
                if target != btn["target_color"]:
                    btn["target_color"] = target
                    btn["transition_start_time"] = time.time()
                if btn["transition_start_time"]:
                    elapsed = (time.time() - btn["transition_start_time"]) * 1000
                    progress = min(elapsed / btn["transition_duration"], 1.0)
                    btn["current_color"] = interpolate_color(btn["current_color"], btn["target_color"], progress)
                    if progress >= 1.0: btn["transition_start_time"] = None
                
                draw_single_button(full_surface, nom, btn, with_halo=False)

        for nom, btn in boutons.items():
            if lampe_states[nom] == "on":
                target = (255, 215, 0) if lampe_modes[nom] == "normal" else (25, 25, 112)
                
                if target != btn["target_color"]:
                    btn["target_color"] = target
                    btn["transition_start_time"] = time.time()
                if btn["transition_start_time"]:
                    elapsed = (time.time() - btn["transition_start_time"]) * 1000
                    progress = min(elapsed / btn["transition_duration"], 1.0)
                    btn["current_color"] = interpolate_color(btn["current_color"], btn["target_color"], progress)
                    if progress >= 1.0: btn["transition_start_time"] = None
                
                draw_single_button(full_surface, nom, btn, with_halo=True)
        
        pg.draw.rect(full_surface, (150, 150, 150), back_button_rect)
        full_surface.blit(raspberry_pi_icon if is_fullscreen else yeelight_icon, raspberry_pi_icon.get_rect(center=back_button_rect.center))

        if is_fullscreen:
            pg.draw.line(full_surface, (255, 0, 0), (close_button_rect.x+5, close_button_rect.y+5), (close_button_rect.right-5, close_button_rect.bottom-5), 3)
            pg.draw.line(full_surface, (255, 0, 0), (close_button_rect.right-5, close_button_rect.y+5), (close_button_rect.x+5, close_button_rect.bottom-5), 3)
            full_surface.blit(settings_icon, settings_button_rect.topleft)

    if fading and is_fullscreen:
        fade, done = fade_to_black(fade_start_time)
        full_surface.blit(fade, (0, 0))
        if done:
            fading = False
            screensaver_active = True
            if current_screensaver >= 2: start_video_screensaver()

    if screensaver_active and is_fullscreen:
        target_fps = VIDEO_FPS if current_screensaver >= 2 else FPS
        full_surface.fill((0, 0, 0))
        if current_screensaver == 0:
            move_stars()
            for s in stars: pg.draw.circle(full_surface, s["color"], (int(s["x"]), int(s["y"])), 2)
        elif current_screensaver == 1:
            for column in matrix_columns:
                column.draw(full_surface)
        elif current_screensaver >= 2: draw_video_screensaver()

    if show_confirm and is_fullscreen:
        pg.draw.rect(full_surface, (100, 100, 100), confirm_rect)
        full_surface.blit(confirm_text, confirm_text.get_rect(center=(confirm_rect.centerx, confirm_rect.y + 35)))
        pg.draw.rect(full_surface, (0, 200, 0), yes_button_rect); full_surface.blit(yes_text, yes_text.get_rect(center=yes_button_rect.center))
        pg.draw.rect(full_surface, (200, 0, 0), no_button_rect); full_surface.blit(no_text, no_text.get_rect(center=no_button_rect.center))
    
    if show_settings_modal and is_fullscreen and not screensaver_active:
        overlay = pg.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pg.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        full_surface.blit(overlay, (0, 0))
        
        pg.draw.rect(full_surface, (80, 80, 80), settings_modal_rect)
        pg.draw.rect(full_surface, (200, 200, 200), settings_modal_rect, 2)
        full_surface.blit(settings_title_text, settings_title_rect)
        
        pg.draw.rect(full_surface, (100, 100, 150), btn_maj_ip_rect)
        full_surface.blit(text_maj_ip, text_maj_ip_rect)
        pg.draw.rect(full_surface, (100, 150, 100), btn_edit_config_rect)
        full_surface.blit(text_edit_config, text_edit_config_rect)

        # --- DESSIN BOUTON AUTO (AJOUT V26) ---
        pg.draw.rect(full_surface, (100, 100, 150), btn_auto_rect) 
        full_surface.blit(text_auto, text_auto_rect)
        # --------------------------------------
        pg.draw.rect(full_surface, (100, 150, 100), btn_check_updates_rect)
        full_surface.blit(text_check_updates, text_check_updates_rect)
        full_surface.blit(settings_version_text, settings_version_rect)

        draw_checkbox(full_surface, check_matrix_rect, screensaver_settings["matrix"], text_matrix)
        draw_checkbox(full_surface, check_stars_rect, screensaver_settings["stars"], text_stars)
        draw_checkbox(full_surface, check_lava_rect, screensaver_settings["lava"], text_lava)
        draw_checkbox(full_surface, check_particles_rect, screensaver_settings["particles"], text_particles)
        draw_checkbox(full_surface, check_nebula_rect, screensaver_settings["nebula"], text_nebula)
        draw_checkbox(full_surface, check_turbulence_rect, screensaver_settings["turbulence"], text_turbulence)

        draw_preview_button(full_surface, preview_matrix_rect)
        draw_preview_button(full_surface, preview_stars_rect)
        draw_preview_button(full_surface, preview_lava_rect)
        draw_preview_button(full_surface, preview_particles_rect)
        draw_preview_button(full_surface, preview_nebula_rect)
        draw_preview_button(full_surface, preview_turbulence_rect)

    if show_update_modal and is_fullscreen and not screensaver_active:
        draw_update_modal(full_surface)

    if show_edit_lamps_modal and is_fullscreen and not screensaver_active:
        overlay = pg.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pg.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        full_surface.blit(overlay, (0, 0))
        pg.draw.rect(full_surface, (70, 70, 80), settings_modal_rect)
        pg.draw.rect(full_surface, (220, 220, 220), settings_modal_rect, 2)
        title = font.render("Editer Lampes", True, (255, 255, 255))
        full_surface.blit(title, (settings_modal_rect.x + 20, settings_modal_rect.y + 15))
        pg.draw.rect(full_surface, (130, 40, 40), btn_close_submenu_rect)
        full_surface.blit(small_font.render("X", True, (255, 255, 255)), (btn_close_submenu_rect.x + 11, btn_close_submenu_rect.y + 6))

        if show_lamp_detail_modal and selected_lamp_index is not None:
            lamp = lampes_editor_data[selected_lamp_index]
            full_surface.blit(small_font.render(f"IP: {lamp.get('ip', 'N/A')}", True, (255, 255, 255)), (settings_modal_rect.x + 60, settings_modal_rect.y + 65))
            name_rect = pg.Rect(settings_modal_rect.x + 60, settings_modal_rect.y + 90, settings_modal_rect.width - 120, 38)
            mac_rect = pg.Rect(settings_modal_rect.x + 60, settings_modal_rect.y + 145, settings_modal_rect.width - 120, 38)
            pg.draw.rect(full_surface, (90, 90, 120), name_rect)
            pg.draw.rect(full_surface, (90, 120, 90), mac_rect)
            full_surface.blit(small_font.render(f"Nom: {lamp['name']}", True, (255, 255, 255)), (name_rect.x + 10, name_rect.y + 10))
            full_surface.blit(small_font.render(f"MAC: {lamp['mac']}", True, (255, 255, 255)), (mac_rect.x + 10, mac_rect.y + 10))
            if show_mac_list_modal:
                full_surface.blit(small_font.render("Choisir MAC LAN:", True, (255, 255, 255)), (settings_modal_rect.x + 60, settings_modal_rect.y + 190))
                for i, mac in enumerate(detected_macs[:7]):
                    r = pg.Rect(settings_modal_rect.x + 50, settings_modal_rect.y + 215 + i * 26, settings_modal_rect.width - 100, 22)
                    color = (180, 180, 70) if mac == lamp["mac"] else (95, 95, 95)
                    pg.draw.rect(full_surface, color, r)
                    full_surface.blit(preview_font.render(mac, True, (0, 0, 0) if mac == lamp["mac"] else (255, 255, 255)), (r.x + 8, r.y + 4))
        else:
            hint = preview_font.render("Glisser les poignées pour réorganiser (4 lignes x 2 colonnes)", True, (210, 210, 210))
            full_surface.blit(hint, (settings_modal_rect.x + 20, settings_modal_rect.y + 48))
            for i, lamp in enumerate(lampes_editor_data):
                card = get_editor_card_rect(i)
                alpha = 120 if dragging_lamp_index == i else 255
                row_surf = pg.Surface((card.width, card.height), pg.SRCALPHA)
                row_surf.fill((100, 100, 130, alpha))
                full_surface.blit(row_surf, card.topleft)
                full_surface.blit(small_font.render("⋮⋮", True, (240, 240, 240)), (card.x + 10, card.y + 14))
                lamp_name = small_font.render(lamp["name"], True, (255, 255, 255))
                full_surface.blit(lamp_name, (card.x + 40, card.y + 18))

    draw_popup_messages(full_surface)

    if is_fullscreen: screen.blit(full_surface, (0, 0))
    else: screen.blit(full_surface.subsurface(back_button_rect), (0, 0))

    pg.display.flip()
    clock.tick(target_fps)

stop_screensaver()
if config_process: config_process.terminate()
if keyboard_process: keyboard_process.terminate()
if automation_process: automation_process.terminate()
pg.quit()
sys.exit()
