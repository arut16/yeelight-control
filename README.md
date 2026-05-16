# Yeelight Touchscreen Home Automation Controller

![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![Raspberry Pi 5](https://img.shields.io/badge/Raspberry%20Pi-5-C51A4A?logo=raspberrypi&logoColor=white)
![Yeelight LAN Mode](https://img.shields.io/badge/Yeelight-LAN%20Mode-00A86B)
![Pygame UI](https://img.shields.io/badge/UI-Pygame-5A4FCF)
![Local Network Only](https://img.shields.io/badge/Network-Local%20Only-orange)

A Raspberry Pi 5 touchscreen home automation controller for local Yeelight smart bulb control over a LAN. The project is written in Python and centers on `yeelight_control.py`, a fullscreen `pygame` interface designed for kiosk-style usage on a 640×480 Raspberry Pi touchscreen.

The controller operates Yeelight bulbs directly on the local network through the Yeelight LAN protocol. No cloud service is required for normal Yeelight operation once the bulbs are reachable on the same LAN and LAN control is enabled in the Yeelight ecosystem.

> **Target environment:** Raspberry Pi 5 + Raspberry Pi OS desktop session + touchscreen display.

> [!WARNING]
> Many runtime paths are currently hardcoded under `/home/arut16/`. Deployments on another username, home directory, or installation path require updating the scripts and local configuration paths accordingly before running the application.

---

## 🎯 Project Goals

This project exists to provide a practical, self-hosted touchscreen controller for Yeelight smart bulbs in a home environment. It is designed for installations where responsiveness, local ownership, and predictable behavior are more important than cloud dashboards or mobile-app-first workflows.

The core philosophy is to keep everyday lighting control close to the user and close to the devices. Commands are sent directly over the local LAN through Yeelight LAN control, which helps deliver fast response times, supports offline-capable operation when internet access is unavailable, and avoids relying on external cloud services for routine bulb actions.

The user experience is intentionally simple: a Raspberry Pi touchscreen presents a kiosk-style interface with large controls, minimal navigation, and immediate feedback. This makes the controller suitable for wall-mounted, desk-mounted, or appliance-like home automation usage where the device should be ready for quick taps rather than keyboard-and-mouse interaction.

Deployment is optimized for a lightweight Raspberry Pi setup. The application uses local scripts, local JSON configuration, and standard Linux desktop tooling so it can run as a dedicated controller without a heavy server stack. The goal is a home-controlled environment that remains understandable, maintainable, and easy to adapt for personal automation needs.

---

## ⚡ Quick Start

A minimal local setup workflow for a Raspberry Pi OS desktop session:

```bash
git clone <your-repository-url> yeelight-control
cd yeelight-control
python3 -m venv /home/arut16/YeelightDomEnv
source /home/arut16/YeelightDomEnv/bin/activate
pip install -r requirements.txt
export DISPLAY=:0
python3 yeelight_control.py
```

Before launching on real hardware, make sure the required local JSON files, image assets, sound assets, font file, and video files described below exist at the expected paths or update the scripts for your installation.

---

## ✨ Features

- **Fullscreen touchscreen GUI** built with `pygame`.
- **LAN-only Yeelight control** using the Python `yeelight` library.
- **No cloud dependency** for day-to-day bulb commands.
- **Kiosk-oriented UI** with hidden cursor, fullscreen mode, and a compact windowed mode for editing.
- **Single-tap / double-tap lamp actions**:
  - Single tap toggles a lamp on or off.
  - Double tap toggles a low-brightness warm night mode.
- **Multi-threaded lamp monitoring** to keep UI state synchronized with physical bulb state changes.
- **Automatic Wi-Fi recovery** when all lamps stay unreachable for a configured timeout.
- **Screensaver system** with selectable visual modes:
  - Stars
  - Matrix
  - Lava Lamp video
  - Particles video
  - Nebula video
  - Turbulence video
- **`ffmpeg` video screensaver rendering** into raw RGB frames for the `pygame` surface.
- **Screensaver preview and enable/disable settings** from the touchscreen settings modal.
- **Automation system** with a dedicated touchscreen editor.
- **Astral sun condition support** for sunrise/sunset automation windows.
- **Lamp IP management** using local JSON files and `arp-scan` discovery.
- **Virtual keyboard support** through `onboard` when editing lamp configuration.
- **Automatic git update integration** from inside the UI.
- **CPU temperature bubble widget** with Wi-Fi IP display and update/UPS-related UI logic.
- **Startup and shutdown shell scripts** for Raspberry Pi operation.
- **Rotating logs** for the main controller and CPU bubble widget.
- **Local JSON configuration** for lamp IPs, lamp MAC/name configuration, screensaver settings, automations, and related runtime state.
- **Optional SD-card watchdog helper** for Raspberry Pi microSD/MMC kernel error alerts.

---

## 🖼️ Screenshots

### Main Dashboard

<p align="center">
  <img src="docs/screenshots/main-dashboard.png" alt="Main Dashboard" width="560">
</p>

### Settings Modal

<p align="center">
  <img src="docs/screenshots/settings-modal.png" alt="Settings Modal" width="560">
</p>

### Automation Editor

<p align="center">
  <img src="docs/screenshots/automation-editor.png" alt="Automation Editor" width="560">
</p>

### Matrix Screensaver

<p align="center">
  <img src="docs/screenshots/screensaver-matrix.png" alt="Matrix Screensaver" width="560">
</p>

### CPU Bubble Widget

<p align="center">
  <img src="docs/screenshots/cpu-bubble.png" alt="CPU Bubble Widget" width="360">
</p>

---

## 🧱 Hardware Requirements

Recommended production setup:

- Raspberry Pi 5.
- Raspberry Pi-compatible touchscreen display.
- microSD card or other boot storage suitable for continuous desktop/kiosk use.
- Wi-Fi or Ethernet LAN access.
- Yeelight smart bulbs connected to the same local network.
- Optional UPS if you want to use the UPS-related behavior implemented in `cpu_temp_bubble.py`.

Yeelight requirements:

- Bulbs must be reachable from the Raspberry Pi on the same LAN.
- LAN control must be enabled for the bulbs in the Yeelight/Mi Home ecosystem.
- Stable IP mapping is recommended. This project can refresh IPs with `arp-scan`, but DHCP reservations are still useful.

---

## 💻 Software Requirements

The project is intended for Raspberry Pi OS with a graphical desktop session.

Core software:

- Raspberry Pi OS with desktop environment.
- Python 3.11 or compatible Python 3 version.
- `git`.
- `ffmpeg` command-line tools.
- `arp-scan` for lamp discovery.
- `pygame` and other Python dependencies from `requirements.txt`.
- `onboard` virtual keyboard for touchscreen editing.
- `mousepad` text editor for lamp configuration editing.
- `picom` for transparent overlay behavior used by the CPU bubble helper stack.

Optional helper dependencies:

- `zenity` and `notify-send` for the SD watchdog alert script.
- `PyQt5` if you use `bubble_helper.py` directly. It imports `PyQt5`, but `PyQt5` is not currently listed in `requirements.txt`.

---

## 🍓 Raspberry Pi OS Setup

Update the base OS and install system packages:

```bash
sudo apt update
sudo apt upgrade -y

sudo apt install -y \
  git \
  python3 \
  python3-venv \
  python3-pip \
  ffmpeg \
  arp-scan \
  onboard \
  mousepad \
  picom \
  zenity \
  libnotify-bin
```

Clone the repository. The current scripts are optimized for the production path `/home/arut16`; if you use a different user or path, update the hardcoded paths in the Python and shell scripts accordingly.

```bash
cd /home/arut16
git clone <your-repository-url> yeelight-control
cd yeelight-control
```

For the existing production-style path layout, scripts may also be placed directly in `/home/arut16`. The startup script detects whether the application is in `/home/arut16` and falls back to the directory containing the script when needed.

---

## 🐍 Python Virtual Environment Setup

The application currently expects the production virtual environment at:

```text
/home/arut16/YeelightDomEnv
```

Create it with:

```bash
python3 -m venv /home/arut16/YeelightDomEnv
source /home/arut16/YeelightDomEnv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

If you choose another virtual environment path, update:

- `venv_path` in `yeelight_control.py`.
- `PYTHON_BIN` in `start_yeelight_control.sh`.

---

## 📦 Install Python Requirements

Install the Python dependencies from the repository:

```bash
source /home/arut16/YeelightDomEnv/bin/activate
cd /home/arut16/yeelight-control
pip install -r requirements.txt
```

The dependency set includes `pygame`, `numpy`, `ffmpeg-python`, `yeelight`, `astral`, `opencv-python`, `psutil`, `pillow`, and related packages.

---

## 🎞️ Install and Verify ffmpeg

Install `ffmpeg` with APT:

```bash
sudo apt install -y ffmpeg
```

Verify it is available:

```bash
ffmpeg -version
```

The video screensavers use `ffmpeg-python` to start an `ffmpeg` process that reads a random segment of a configured video and streams raw `rgb24` frames into the `pygame` display surface.

Configured production video paths:

```text
/home/arut16/Videos/lava_lamp.mp4
/home/arut16/Videos/particles_explosions.mp4
/home/arut16/Videos/Nebula.mp4
/home/arut16/Videos/Turbulence.mp4
```

Create the directory and copy your videos:

```bash
mkdir -p /home/arut16/Videos
# Copy the required video files into /home/arut16/Videos
```

---

## ⚙️ Required Local Files and Assets

Several local files and assets are referenced by absolute production paths. Ensure they exist or update the scripts for your environment.

### JSON configuration files

```text
/home/arut16/lamp_ips.json
/home/arut16/lamp_config.json
/home/arut16/screensavers_set.json
/home/arut16/automations.json
/home/arut16/ups_shutdown_config.json
```

### Image assets

```text
/home/arut16/Pictures/yeelight_logo_32x32.png
/home/arut16/Pictures/bulb_on.png
/home/arut16/Pictures/bulb_off.png
/home/arut16/Pictures/arrow_back_icon.png
/home/arut16/Pictures/raspberry-pi_logo_button.png
/home/arut16/Pictures/yeelight_logo_button.png
/home/arut16/Pictures/settings_icon.png
/home/arut16/Pictures/update_logo.png
```

### Sound assets

```text
/home/arut16/sounds/click.wav
/home/arut16/sounds/light_on.wav
/home/arut16/sounds/light_off.wav
```

### Font asset

```text
/home/arut16/font/ms mincho.ttf
```

The Matrix screensaver uses this font to render Katakana-style symbols.

---

## 🚀 Launch Manually

From a Raspberry Pi desktop session:

```bash
export DISPLAY=:0
source /home/arut16/YeelightDomEnv/bin/activate
cd /home/arut16/yeelight-control
python3 yeelight_control.py
```

To start the CPU temperature bubble separately:

```bash
export DISPLAY=:0
source /home/arut16/YeelightDomEnv/bin/activate
cd /home/arut16/yeelight-control
python3 cpu_temp_bubble.py
```

Or use the provided launcher:

```bash
chmod +x start_yeelight_control.sh
./start_yeelight_control.sh
```

The launcher waits for the LXDE session, starts `yeelight_control.py`, then starts `cpu_temp_bubble.py` if they are not already running.

---

## 🔁 Launch Automatically at Startup

The repository includes `start_yeelight_control.sh`, which is intended to be called after the Raspberry Pi desktop session has started.

One common Raspberry Pi OS desktop approach is LXDE autostart:

```bash
mkdir -p ~/.config/lxsession/LXDE-pi
nano ~/.config/lxsession/LXDE-pi/autostart
```

Add:

```text
@/home/arut16/yeelight-control/start_yeelight_control.sh
```

Make the script executable:

```bash
chmod +x /home/arut16/yeelight-control/start_yeelight_control.sh
```

Reboot to test:

```bash
sudo reboot
```

Startup logs are written to:

```text
/home/arut16/start_yeelight_control_debug.log
```

> If your project is installed somewhere else, adjust the path in the autostart entry. The script itself falls back to its own directory if it does not find the application scripts directly in `/home/arut16`.

---

## ⏻ Shutdown Script

`shutdown_script.sh` stops the CPU bubble and main controller processes, waits briefly, and powers off the Raspberry Pi:

```bash
chmod +x shutdown_script.sh
./shutdown_script.sh
```

Because it calls system shutdown through `sudo`, configure sudo permissions appropriately for your kiosk user if you want passwordless shutdown.

---

## 🔄 Git Update Workflow

The main application includes an automatic git update workflow in the settings modal.

How it works:

1. The app reads the local project version from `VERSION`.
2. The settings modal shows the current version.
3. The **Vérifier mises à jour** button runs git commands in the project directory.
4. The app fetches the upstream branch and lists files changed between `HEAD` and the upstream ref.
5. If updates are available, the update modal can apply them with `git pull --ff-only`.
6. After a successful pull, the application restarts the controller process and restarts the CPU bubble process.

Manual equivalent:

```bash
cd /home/arut16/yeelight-control
git fetch --prune
git status
git pull --ff-only
```

Important notes:

- The in-app workflow expects the repository to have a configured remote/upstream branch.
- The pull is fast-forward only.
- Keep local production changes committed or stashed before using the in-app update button.

---

## 🌌 Screensaver System

The controller enters a screensaver after inactivity while running in fullscreen mode. The default inactivity timeout is five minutes.

Available modes:

| Mode | Type | Description |
| --- | --- | --- |
| Stars | Procedural `pygame` | Colored stars move outward from the screen center. |
| Matrix | Procedural `pygame` | Katakana-like falling symbol columns. |
| Lava Lamp | Video | Random segment from `lava_lamp.mp4`. |
| Particles | Video | Random segment from `particles_explosions.mp4`. |
| Nebula | Video | Random segment from `Nebula.mp4`. |
| Turbulence | Video | Random segment from `Turbulence.mp4`. |

Screensaver settings are stored in:

```text
/home/arut16/screensavers_set.json
```

The settings modal lets you:

- Enable or disable each screensaver.
- Preview each screensaver.
- Exit a screensaver with a touch or key press.

Video screensavers use `ffmpeg` with raw frame output:

```text
ffmpeg input video -> raw rgb24 pipe -> numpy frame -> pygame surface
```

---

## 🤖 Automation System

Automation rules are edited with `automatisations_v12.py`, a dedicated fullscreen `tkinter` interface optimized for the same 640×480 touchscreen.

Rules are stored in:

```text
/home/arut16/automations.json
```

A rule contains:

- Trigger lamp name.
- Trigger state: `on` or `off`.
- Target lamp name.
- Target action: `on` or `off`.
- Optional solar condition.

Example automation shape:

```json
[
  {
    "trigger": "Living Room",
    "trigger_state": "on",
    "target": "Desk",
    "action": "on",
    "condition": {
      "start": "sunset_offset_-30",
      "end": "sunrise_offset_30",
      "text": "Début: 30 min avant coucher, Fin: 30 min après lever"
    }
  }
]
```

The main controller reloads rules after the automation editor closes. It also monitors lamp state changes in the background, so automation can react both to touchscreen actions and to detected state changes.

### Astral sun conditions

When `astral` is installed, solar conditions are evaluated against the configured location in `yeelight_control.py`:

```text
Latitude: 43.659
Longitude: 7.123
Location label: Villeneuve-Loubet, France
Timezone: Europe/Paris
```

If `astral` is unavailable or condition evaluation fails, the code treats the condition as active to keep automations from blocking unexpectedly.

---

## 🧩 Configuration Files

The current configuration model is file-based and uses production paths under `/home/arut16/`. Future versions may centralize paths and runtime settings into a dedicated configuration system or `.env`-style configuration to improve portability.

### `lamp_config.json`

Production path:

```text
/home/arut16/lamp_config.json
```

Used by `update_lamp_ips.py` to map lamp names and MAC addresses. The script supports either common orientation and normalizes the mapping internally.

Example:

```json
{
  "Living Room": "AA:BB:CC:DD:EE:FF",
  "Desk": "11:22:33:44:55:66"
}
```

### `lamp_ips.json`

Production path:

```text
/home/arut16/lamp_ips.json
```

Used by the main UI to build lamp buttons and connect to bulbs.

Example:

```json
{
  "Living Room": "192.168.1.40",
  "Desk": "192.168.1.41"
}
```

### `screensavers_set.json`

Production path:

```text
/home/arut16/screensavers_set.json
```

Stores enabled/disabled flags for screensaver modes.

Example:

```json
{
  "matrix": true,
  "stars": true,
  "lava": true,
  "particles": true,
  "nebula": true,
  "turbulence": true
}
```

### `automations.json`

Production path:

```text
/home/arut16/automations.json
```

Stores automation rules created by the automation editor.

### `VERSION`

Repository path:

```text
VERSION
```

Displayed in the settings modal and used by the git update workflow when comparing with the upstream version file.

---

## 🪵 Logging System

The project uses local log files suitable for unattended Raspberry Pi operation.

| Component | Log file | Notes |
| --- | --- | --- |
| Main controller | `/home/arut16/yeelight_control.log` | Uses `RotatingFileHandler`, 10 MB max, one backup. |
| Startup launcher | `/home/arut16/start_yeelight_control_debug.log` | Recreated each launcher run. |
| CPU bubble | `/home/arut16/cpu_temp_bubble.log` | Uses rotating logging in `cpu_temp_bubble.py`. |
| Lamp IP updater | `lamp_ips_update.log` | Relative to the working directory used when running `update_lamp_ips.py`. |
| SD watchdog | stdout/system service logs | Intended for service-style execution or terminal monitoring. |

Useful commands:

```bash
tail -f /home/arut16/yeelight_control.log
tail -f /home/arut16/start_yeelight_control_debug.log
tail -f /home/arut16/cpu_temp_bubble.log
```

---

## 🏗️ Architecture Overview

```text
                 ┌───────────────────────────┐
                 │ Raspberry Pi touchscreen  │
                 └─────────────┬─────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────┐
│ yeelight_control.py                                    │
│ - pygame fullscreen kiosk UI                           │
│ - lamp button rendering                                │
│ - Yeelight LAN commands                                │
│ - screensaver manager                                  │
│ - git update modal                                     │
│ - background lamp monitor thread                       │
└───────────────┬───────────────────┬────────────────────┘
                │                   │
                │                   ▼
                │        ┌───────────────────────┐
                │        │ automatisations_v12.py │
                │        │ tkinter editor         │
                │        │ automations.json       │
                │        └───────────────────────┘
                │
                ▼
┌─────────────────────────┐       ┌──────────────────────┐
│ Yeelight bulbs on LAN   │       │ Local JSON config     │
│ No cloud required       │       │ lamp_ips/config/etc.  │
└─────────────────────────┘       └──────────────────────┘
                ▲
                │
┌───────────────┴───────────────┐
│ update_lamp_ips.py            │
│ arp-scan local network scan   │
└───────────────────────────────┘

┌───────────────────────────┐
│ cpu_temp_bubble.py        │
│ Tk overlay widget          │
│ CPU temp / Wi-Fi IP / UPS  │
└───────────────────────────┘
```

The architecture currently favors a direct Raspberry Pi deployment layout with local scripts, local JSON files, and hardcoded production paths. A future centralized configuration layer could make these paths easier to override per installation.

---

## 🌳 Project Structure

```text
.
├── README.md
├── VERSION
├── automatisations_v12.py      # Touchscreen automation editor
├── bubble_helper.py            # PyQt5 speech-bubble overlay helper
├── cpu_temp_bubble.py          # CPU temperature / IP / update / UPS bubble widget
├── requirements.txt            # Python dependency pins
├── sd_watchdog.py              # microSD/MMC kernel error alert helper
├── shutdown_script.sh          # Stops app processes and powers off the Pi
├── start_yeelight_control.sh   # Desktop-session startup launcher
├── update_lamp_ips.py          # arp-scan-based Yeelight IP updater
└── yeelight_control.py         # Main pygame Yeelight touchscreen controller
```

---

## 🛠️ Troubleshooting

### The GUI does not appear

Check that a desktop session is running and `DISPLAY` is set:

```bash
export DISPLAY=:0
pgrep -f lxsession
```

Review launcher logs:

```bash
tail -n 100 /home/arut16/start_yeelight_control_debug.log
```

### `pygame.error: No available video device`

Run the application inside the Raspberry Pi graphical session, not from a headless SSH shell without X forwarding/session access. If launching from SSH into the local desktop, ensure:

```bash
export DISPLAY=:0
```

### Lamps do not respond

Verify the bulbs are reachable:

```bash
ping <lamp-ip>
```

Confirm `lamp_ips.json` contains the current IP addresses:

```bash
cat /home/arut16/lamp_ips.json
```

Refresh lamp IPs:

```bash
cd /home/arut16/yeelight-control
source /home/arut16/YeelightDomEnv/bin/activate
python3 update_lamp_ips.py
```

Also confirm Yeelight LAN control is enabled for each bulb.

### `arp-scan` fails or returns no lamps

Install `arp-scan`:

```bash
sudo apt install -y arp-scan
```

Run manually:

```bash
sudo arp-scan --localnet
```

If this requires a password during kiosk use, configure appropriate sudo rules for the Raspberry Pi user.

### Video screensavers are black or fail

Verify videos exist at the configured paths:

```bash
ls -lh /home/arut16/Videos
```

Verify `ffmpeg` works:

```bash
ffmpeg -version
```

If hardware acceleration causes issues on your OS image, inspect the `ffmpeg.input(..., hwaccel='drm')` usage in `yeelight_control.py` and adjust for your Raspberry Pi OS graphics stack.

### Matrix screensaver font error

Ensure this file exists:

```bash
ls -lh "/home/arut16/font/ms mincho.ttf"
```

Or update the font path in `yeelight_control.py`.

### Sound files fail to load

Ensure the referenced sound assets exist:

```bash
ls -lh /home/arut16/sounds
```

Required files:

```text
click.wav
light_on.wav
light_off.wav
```

### Virtual keyboard does not open

Install `onboard`:

```bash
sudo apt install -y onboard
```

The app launches `onboard` while editing the lamp configuration file from the settings modal.

### In-app git update fails

Check repository status and upstream configuration:

```bash
cd /home/arut16/yeelight-control
git status
git remote -v
git branch -vv
```

The in-app updater uses `git fetch --prune` and `git pull --ff-only`, so local uncommitted changes or non-fast-forward history can block updates.

### All lamps show unavailable and Wi-Fi recovery runs

The monitor thread considers all lamps offline after repeated failures. If all lamps stay unreachable for the configured timeout, it attempts:

```bash
sudo ifdown wlan0
sudo ifup wlan0
```

Make sure those commands are valid for your Raspberry Pi OS networking setup. Newer NetworkManager-based installations may require adapting this recovery logic.

---

## ⚠️ Known Limitations

- Many paths are hardcoded under `/home/arut16/`, which requires manual updates for other users or installation directories.
- The UI is optimized mainly for 640×480 Raspberry Pi touchscreen usage.
- There is no authentication layer; the controller is intended for trusted local touchscreen access.
- The application is designed for LAN environments only and expects Yeelight bulbs to be reachable locally.
- Portability is limited without path adjustments and Raspberry Pi OS desktop-session assumptions.
- The application depends on local image, sound, font, video, and JSON configuration assets existing at expected locations.

---

## 🧭 Future Improvements

Potential improvements that fit the current architecture:

- Replace hardcoded `/home/arut16` paths with a single configuration file or environment variables.
- Add a first-run setup wizard for lamp config, assets, and paths.
- Add systemd user/service templates for startup instead of relying only on desktop autostart.
- Add screenshots and a short demo video to the repository.
- Add a sample `lamp_config.json`, `lamp_ips.json`, `screensavers_set.json`, and `automations.json` under an `examples/` directory.
- Add automated linting and formatting configuration.
- Add graceful handling for missing image, sound, font, and video assets.
- Add configurable location settings for Astral sun conditions.
- Add a settings screen for video paths and screensaver timeout.
- Add tests for JSON parsing, automation rule evaluation, and sun-condition windows.

---

## 📄 License

This project is licensed under the MIT License. See [`LICENSE`](LICENSE) for the full license text.

---

## 🙏 Credits

Built for a Raspberry Pi 5 touchscreen home automation setup using:

- Python
- `pygame`
- `yeelight`
- `ffmpeg-python` and `ffmpeg`
- `astral`
- `tkinter`
- Raspberry Pi OS
- Yeelight smart bulbs with LAN control enabled

