# First start — Diablo DATV Studio

This guide gets the **web GUI, source preview and a software TS test** running.
It does not configure an RF transmitter or automatically play ASI. Start with one
source; add the other inputs only after that source is stable.

## Automated setup — recommended

Once you have Linux, a normal user with sudo access, and this repository cloned:

```sh
cd Diablo-DATV-Studio
bash scripts/first-start.sh
```

This single guided command:

1. Runs the installer and dependency checks (no Python/Node runtime needed).
2. Prompts for **CALLSIGN**, **service name**, initial direct source and web port.
3. Configures the selected SRT slot/LAN address, USB HDMI capture format/audio,
   Pi Camera index, or UDP IPTS port/scope. IP CAM selection is supported; enter
   its private RTSP URL later in the GUI, not in command-line history.
4. Offers targeted device-group grants. Existing credentials and unrelated
   settings are retained, with private backups before changing config/env.
5. Runs a short real GUI/API startup/shutdown check and confirms TX, RX and
   output TS are idle. If opted in, it checks the selected SRT listener process.
6. Prints the actual local browser URL, SSH tunnel command and SRT caller URL,
   then offers to keep the GUI running in the foreground.

Choose **yes** at the SRT listener question to receive video automatically when
Diablo is launched. This starts only the selected listener, not RF/ASI or output
TS. It applies only in STANDALONE with that matching Direct SRT source selected.
Disabling it in the GUI lasts until the next launch; use `--disable-srt` in setup
to remove the launch-time behavior. No service is enabled at boot.

If a web port is already occupied (for example TANK's existing port 8080 service),
choose another unused port such as **18880**. Do not reuse the preview ports.
The startup check fails with a log path instead of stopping the other service.

### Unattended setup

Replace `N0CALL`, the service name and address with your own values:

```sh
bash scripts/first-start.sh --non-interactive \
  --callsign N0CALL --service-name "My DATV station" \
  --source SRT --srt-slot 1 --enable-srt \
  --advertise-ip 192.168.3.33 --http-port 18880 --start
```

Without `--start`, unattended setup verifies startup, stops its instance and
returns. `--start` stays in the foreground; Ctrl+C stops it. For an installed
runtime, add `--configure-only`; `--skip-system-packages` only skips the installer's
apt step. Repeated runs retain saved values unless overridden; an explicit source
selection changes the layout to Direct. Stop the running GUI before rerunning.
Existing armed or MASTER/SLAVE installs are deliberately left unchanged: use their
normal GUI/config workflow rather than resetting them through first-start.

Example USB capture setup (use the actual video/audio nodes):

```sh
bash scripts/first-start.sh --configure-only --non-interactive \
  --callsign N0CALL --service-name "HDMI test" \
  --source HDMI --video-device /dev/video0 --input-format mjpeg \
  --audio-device hw:1,0 --device-groups video,audio --start
```

**Host changes are opt-in:** `--enable-ssh` installs and enables OpenSSH without
changing its authentication policy; `--device-groups video,audio,render` grants
only those named device groups; `--pi-camera-packages` selects an available distro
rpicam package only on a detected Raspberry Pi. These use sudo. Log out/back in
after group changes. Firewall rules, GPU/DekTec drivers, OS images, reboot and
boot-autostart are not changed. Use `--help` for all options.

Backups: `<prefix>/backups/first-start-*/`. Check logs:
`<prefix>/logs/first-start-*.log`. Restore config/env from the same backup while
stopped if needed; host package/group/SSH changes are separate and are not undone
by restoring those files. The default prefix is
`~/.local/share/diablo-datv-studio`.

**The automated check verifies the control application and listener process, not
live video, audio, RF or physical ASI.** Complete the source-arrival/loss and
software TS checks below with your actual sender/device. `--no-verify` skips the
startup check; it does not mean the installation has passed.

[Recorded two-host setup tests](testing/first-start-2026-11-25.md).

## Manual steps / what setup automates

## 1. Choose the OS and prepare access

- **Raspberry Pi:** use a 64-bit Raspberry Pi OS Trixie installation. Lite is
  sufficient: no desktop, physical screen or framebuffer is required.
- **Other ARM64 boards:** use a supported 64-bit Debian-family Linux with working
  vendor kernel/device support. ARM64 is also called AArch64; a Pi running a
  64-bit OS is an ARM64 system. Non-Pi boards do not acquire Pi camera/GPIO support
  just by installing Diablo.
- **x86-64:** Ubuntu 24 / Mint 22 are installer targets; VideoLP3D uses Mint 22.3.
- Use a normal user with sudo access, a network connection and several GB of free
  storage. Keep the default two build jobs on small machines. A 64-bit kernel
  with 32-bit userspace is not the same as a 64-bit OS.

Set up SSH in the OS if this is a headless machine. On Raspberry Pi OS, configure
SSH and your user in Raspberry Pi Imager before first boot. Keep that account's
credentials private. The installer does not change the network or SSH service.

```sh
uname -m                 # normally aarch64 on Pi/ARM64; x86_64 on a PC
getconf LONG_BIT          # 64 for this guide
cat /etc/os-release
sudo apt-get update
sudo apt-get install -y git
```

## 2. Install as your normal user

```sh
git clone --branch Trixie https://github.com/mathisono/Diablo-DATV-Studio.git
cd Diablo-DATV-Studio
bash scripts/install-diablo.sh
```

Do **not** put sudo before the installer. It uses sudo only for distribution
packages; the runtime and private settings belong to your user. It fetches pinned
ucode/libubox sources over HTTPS and compiles natively. It does not upgrade the
OS, alter the kernel, install board drivers, enable a service or reboot.

For a read-only dependency/device report, before or after installation:

```sh
bash scripts/install-diablo.sh --check
```

Missing **core dependencies** stop installation. Optional device-access and Pi
camera notes do not block network-only use. `--skip-system-packages` is for a
machine where prerequisites are already installed, not a way to skip checks.

## 3. Start and open the GUI

```sh
"$HOME/.local/share/diablo-datv-studio/bin/diablo-studio"
```

Leave this terminal running. Locally open **http://127.0.0.1:8080/**. From your
workstation use a second terminal:

```sh
ssh -N -L 8080:127.0.0.1:8080 your-user@your-encoder-host
```

Open **http://127.0.0.1:8080/** on the workstation. HTTP stays on the encoder's
loopback interface; the SSH tunnel carries browser requests and previews. There
is no need to expose port 8080 on the LAN. If a custom Host policy is configured,
allow the exact browser host/port; see [INSTALL.md](INSTALL.md).

Expected first state: **standalone, TX off**, no hardware TX launcher configured, inputs
not yet enabled. A test/waiting image without an enabled video source is normal.
Do not press TX to test a preview. Stop the application with **Ctrl+C**.

## 4. Save your station identity and test one source

Enter your **CALLSIGN** and **Service name**, then save. Do not leave another
operator's identity in generated TS metadata.

### Easiest network test: one SRT input

1. Set the encoder's LAN address in `PORTSDOWN_SRT_ADVERTISE_HOST` in the installed
   `diablo.env` if the displayed caller address is wrong; restart the launcher.
2. Enable SRT input 1 in **SRT input encoders**. Copy its caller URL to OBS or your
   sender. The sender must emit MPEG-TS, not RTMP/FLV. The SSH browser tunnel does
   **not** carry this UDP/SRT stream.
3. Allow UDP 9101 from the intended sender if a firewall blocks it. Other slots
   use 9102–9105; do not enable them until needed.
4. Select **Direct source → SRT → input 1**, save, and confirm a live low-resolution
   preview. Stop the sender and check that the waiting image returns; no old
   recording should replay. Restart the sender and verify recovery.
5. With that source valid, use **Start output TS** for the local software path.
   This is separate from **Arm / Start TX**. The default output is loopback UDP
   port 12010. A receiver on the same host can inspect it with:

   ```sh
   ffprobe -v error -rw_timeout 5000000 -show_programs -show_streams \
     'udp://127.0.0.1:12010?fifo_size=1000000&overrun_nonfatal=1'
   ```

   Confirm video dimensions, audio if supplied, CALLSIGN and service name.
   Stop output TS afterwards. This proves software output, not ASI or RF.

### USB HDMI capture

Select **USB HDMI capture**, choose the actual `/dev/videoN` capture node and
supported input format. Inspect with `v4l2-ctl --list-devices` and
`v4l2-ctl -d /dev/video0 --list-formats-ext`; not every video node is a capture
input. See [the tested USB HDMI procedure](usb-hdmi-capture.md).

A device-generated color-bar/no-HDMI picture is real captured video and should
appear in the preview. It is not proof of an attached HDMI source. Audio is
separate: inspect `arecord -l`, select the correct device, and verify actual audio.

### Pi Camera / IP CAM / IPTS

- Pi Camera needs `rpicam-vid` (or `libcamera-vid`) from the OS camera stack.
  On Raspberry Pi OS, check `apt-cache policy rpicam-apps-lite rpicam-apps` and
  install the available appropriate package; do not add unrelated repositories
  to generic Debian/ARM boards. Check `rpicam-vid --list-cameras` before selecting
  Pi Camera. Do not seize a camera in use by another service.
- For RTSP, use **IP CAM input encoders → Save IP**, then **Restart** if needed.
  Do not put camera passwords in screenshots, logs or issue reports.
- IPTS means **MPEG transport stream input over IP**, not a video codec. Match
  the chosen UDP/SRT input and sender settings; see [IP output](ipts-srt-link.md).
- Start with direct source. Four-tile multiview is currently a low-rate,
  video-only monitor composition, not a full-quality production switcher.

## 5. Device permissions and troubleshooting

The check report lists nodes your account cannot read/write. Grant only groups
needed for the devices you will use, after inspecting `ls -l` on those nodes:

```sh
# Examples only: use the groups actually owning your selected devices.
sudo usermod -aG video "$USER"   # V4L2 capture
sudo usermod -aG audio "$USER"   # ALSA audio, when required
sudo usermod -aG render "$USER"  # GPU encoding, when required
```

Log out completely and back in after a group change. Do not run Diablo as root
or chmod devices 777. The installer reports these requirements but does not
silently grant access. A listed hardware encoder does not prove it works.

| Symptom | Next check |
| --- | --- |
| Installer fails | Last log in `~/.local/share/diablo-datv-studio/logs/`; run `--check` |
| Web page unavailable | Launcher terminal errors, SSH tunnel and port conflicts |
| “Already running” / update refused | Stop the existing launcher normally; do not delete its lock |
| SRT waiting image only | Enabled slot, correct LAN IP/UDP port, MPEG-TS sender and firewall |
| Capture preview absent | Selected capture node/format, permissions and device ownership |
| Video but no sound | ALSA device, audio group, sender audio and actual recorded/decoded TS |
| Pi Camera missing | OS camera package, camera detection and competing service |
| TX unavailable | Expected default; hardware launchers and RF acceptance are separate |

Keep your checkout in place. Before updating, stop Diablo and back up private
`state/` and `diablo.env`; use the **Trixie** update steps in [INSTALL.md](INSTALL.md).
Do not share those backups: they can contain camera credentials. No automatic
start at boot is configured. Optional drivers/ASI/RF setup and remaining tests
are listed in [KNOWN_ISSUES.md](KNOWN_ISSUES.md).
