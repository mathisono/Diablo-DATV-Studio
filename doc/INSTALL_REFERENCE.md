# Installation reference — advanced options

For a new machine, run `bash scripts/first-start.sh`: it wraps this installer,
guides station/source setup and verifies GUI startup. See the
[first-start walkthrough](FIRST_START.md) for automated and manual options.

## Scope

This installs the **headless GUI, source previews, and local TS control**. It does
not install/enable an RF launcher, ASI playout, a display driver, or a replacement
OS image. Legacy Pi camera/RF binaries are preserved but separate from this setup.
Linux/POSIX is required; “headless” does not mean Windows/macOS compatibility.

The bootstrap targets Debian-family systems: Debian/Raspberry Pi OS Trixie and
Ubuntu 24 / Mint 22. Actual migration validation is recorded in
[MIGRATION.md](MIGRATION.md); a supported installer path is not a claim of testing
every OS/architecture or physical device. Raspberry Pi OS 64-bit is ARM64:
Pi and non-Pi ARM64 hosts build the same native headless runtime, not the legacy
framebuffer GUI. Generic ARM64 requires compatible distro packages/kernel drivers;
Pi-specific CSI camera and GPIO support is not portable to arbitrary ARM boards.
Fresh user-local bootstrap checks on TANK (Pi 4 / Trixie ARM64) and VideoLP3D
(Mint 22.3 x86-64) are recorded in [the installer review](testing/install-review-2026-11-25.md).
These used existing OS dependencies, not fresh OS images.

## Install

As the intended non-root user (not root):

```sh
sudo apt-get update
sudo apt-get install -y git
git clone --branch Trixie https://github.com/mathisono/Diablo-DATV-Studio.git
cd Diablo-DATV-Studio
bash scripts/install-diablo.sh
```

On a first installation, the script runs `apt-get update` and `apt-get upgrade`
before installing dependencies. It does not reboot the machine; check its
reboot-required notice before hardware testing. It installs distribution build
tools, FFmpeg, curl, JSON-C headers and V4L2/ALSA diagnostics; builds
pinned libubox and ucode with fs/socket/uloop; builds the C supervisor/config
writer; creates private initial configuration; and installs a foreground launcher.
It does not change apt sources, reboot, alter Secure Boot,
install a DekTec driver, or automatically start/enable anything.

Optional controls:

```sh
bash scripts/install-diablo.sh --prefix "$HOME/diablo-local" --jobs 2
# Read-only platform/dependency/capture-access report:
bash scripts/install-diablo.sh --check
# If dependencies are already installed:
bash scripts/install-diablo.sh --skip-system-packages
```

Default prefix: `$HOME/.local/share/diablo-datv-studio`. `logs/install.log` points
to the latest timestamped log (including package installation); older logs remain.
`logs/installed-version.txt` records the last successful source/dependency revisions
and architecture, without private settings; `runtime/` contains ucode/libubox; `diablo.env` holds launcher
settings; `state/` holds config, presets and private camera URLs. The checkout
must remain in place. A rerun preserves existing config and `diablo.env`.
Installation and the launcher share a lock: stop Diablo before updating. Builds
force native recompilation of the C tools, even if a copied checkout contains
stale binaries. The preflight checks actual FFmpeg SRT/UDP/TCP, H.264/AAC/MJPEG,
scaling/multiview and TS/V4L2/ALSA support; missing core features stop the build.
Optional Pi camera packages and capture/audio/render-group access are reported,
not silently changed. See the device-permissions section below for targeted group changes and
logging back in. The installer does not attempt GPU driver or QSV tuning.

## Start, connect, stop

```sh
"$HOME/.local/share/diablo-datv-studio/bin/diablo-studio"
```

The recommended `first-start.sh` workflow offers computer-only browser access
without a web password or protected HTTPS LAN access.
If you ran the lower-level installer alone, stop Diablo and configure access:

```sh
bash scripts/setup-access.sh
```

Open the printed `https://LAN_IP:8443/` address directly and sign in. Verify the
locally issued certificate's fingerprint on the first visit. No SSH tunnel is
required. After First Start, use **Access / Peer settings** in the GUI for ordinary
role and password changes. [LAN/password setup](LAN_ACCESS.md) covers changing roles/passwords,
private files, peer TLS and the local trust boundary.

`--local-only` on first-start selects browser access on the Diablo computer
only: it leaves an unconfigured instance's unauthenticated HTTP on loopback,
not the LAN. It does
not remove protection from an already protected install. Never expose that
plain loopback API with a network forwarder.

**Ctrl+C** stops the supervisor, daemon and TLS front end and the supervisor's owned source pipelines.
The launcher refuses a second instance in the same runtime directory.
No default service autostart is configured. The existing `systemd/portsdown-*`
units are advanced templates for a dedicated account, not used by this installer.

## First configuration

1. First Start asks for your callsign and initially uses it as the stream
   service name. The installer alone does not supply station identity; set both
   under Output settings if you bypass First Start.
2. For SRT, enable the desired input slot and use its displayed caller URL.
   Select **Video layout → One video input**, then **Video input → SRT input**,
   choose that slot, and save. Example:
   `srt://ENCODER_LAN_IP:9101?mode=caller&latency=200000`.
3. For an IP camera, enter its RTSP URL in **IP CAM input encoders → Save IP**.
   Use **Restart** to reconnect. Each camera is configured independently;
   saved URLs are not returned to the browser. Special characters in credentials
   are normalized by the UI backend. Keep URLs out of screenshots and shell history.
4. For [USB HDMI capture](usb-hdmi-capture.md)/Pi Camera/IPTS, select the source and its actual device/index/port.
   Access to V4L2/ALSA/DRM devices requires the appropriate host groups. This
   installer does not seize a camera used by another service.
5. Use the selectors below the preview for four-source multiview.
6. **Start output TS** is separate from **Arm / Start TX**. Local TS defaults to
   loopback UDP `127.0.0.1:12010`; receiving TS does not prove RF/ASI output.

Default ports: HTTPS 8443/TCP (LAN); peer TLS 8181/TCP (SLAVE LAN);
HTTP 8080/TCP and trusted internal HTTP 18080/TCP (loopback only); peer internals
18181/18182 TCP (loopback only); preview ingress 8082–8092/TCP (loopback); SRT inputs
9101–9105/UDP (network); per-slot TS 12001–12005/UDP (loopback); IPTS preview
10000/UDP (loopback by default). Restrict SRT access to intended senders. If the
host has multiple interfaces, set `PORTSDOWN_SRT_ADVERTISE_HOST` in `diablo.env`.
Any custom port blocks must be disjoint and agree between both processes.

## Update / rollback

Stop Diablo, preserve a private backup of the install prefix's `state/`, `security/` and
`diablo.env`, then:

```sh
cd Diablo-DATV-Studio
git switch Trixie
git pull --ff-only origin Trixie
bash scripts/install-diablo.sh
```

Do not use the old Portsdown updater: its `master` downloads do not belong to
Diablo. To roll back, check out a recorded known-good Diablo commit while stopped,
rerun the installer, and restore matching configuration if required. Dependency
revisions are pinned. Do not overwrite a modified checkout or private state.
To uninstall, stop the launcher and remove/archive only the chosen user-local
prefix and checkout. No boot service or system RF driver was added by this script;
distribution packages are intentionally left installed.

## Optional backends

### Experimental DATV-Express DVB-S2

```sh
sudo apt-get install build-essential pkg-config libusb-1.0-0-dev libfftw3-dev
bash scripts/build-express-s2.sh
src/express_s2/express_s2 --rate-only --symbol-rate 1000000 --fec 1/2
```

The helper fetches pinned F5OEO libdvbmod and builds the offline-capable backend.
It does not open the board or transmit. Headless RF launch/gating integration
remains a separate tracked issue; see [KNOWN_ISSUES.md](KNOWN_ISSUES.md).

### LattePanda / DekTec DTA-2145

Use [lattepanda-dta-driver.md](lattepanda-dta-driver.md). The separate
`scripts/install-dektec-asi-env.sh` installs the Dta/DtaNw driver environment and
TSDuck. It is **not** the generic GUI installer. ASI output requires correct
physical hookup, verified device/channel mapping and compatible modulator TS
bitrate. Existing driver installs are not changed by `install-diablo.sh`.

Bounded file and live IP/SRT-to-card tests are documented in [ASI output](asi-output.md),
including the required small-FIFO batch limit and shared channel lock. The GUI
installer does not enable these launchers or physical playout automatically.

## Scripted first-start setup

Replace `K1TEST`, the service name and address with your own values. For the
first unattended setup, supply a **private, owned mode-600 file** containing the
password on one line, via `--password-file`. Create it with your secret manager
or a hidden terminal prompt, not a literal password in shell history. Subsequent
unattended runs keep the existing password if that option is omitted.

```sh
bash scripts/first-start.sh --non-interactive \
  --password-file "$HOME/diablo-password.private" \
  --callsign K1TEST --service-name "My DATV station" \
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
  --password-file "$HOME/diablo-password.private" \
  --callsign K1TEST --service-name "HDMI test" \
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


## Capture devices and permissions

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

## Software TS output check

With SRT input 1 receiving valid video, select Direct SRT / slot 1, save, and
click **Start output TS**. This is separate from **Arm / Start TX**. The default
local output is MPEG-TS over UDP on `127.0.0.1:12010`. In a second terminal on the
same host:

```sh
timeout 12s ffprobe -v error -show_programs -show_streams \
  'udp://127.0.0.1:12010?fifo_size=1000000&overrun_nonfatal=1'
```

Check video dimensions, audio if supplied, CALLSIGN and service name. Timeout
without a report means this check has not passed. Click **Stop output TS**
afterwards. This is software output verification, not physical ASI or RF.

## Device permissions and troubleshooting

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
| Web page unavailable | Launcher terminal errors, printed HTTPS address, certificate trust and port conflicts |
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
