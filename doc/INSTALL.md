# Installing Diablo DATV Studio

## Scope

This installs the **headless GUI, source previews, and local TS control**. It does
not install/enable an RF launcher, ASI playout, a display driver, or a replacement
OS image. Legacy Pi camera/RF binaries are preserved but separate from this setup.
Linux/POSIX is required; “headless” does not mean Windows/macOS compatibility.

The bootstrap targets Debian-family systems: Debian/Raspberry Pi OS Trixie and
Ubuntu 24 / Mint 22. Actual migration validation is recorded in
[MIGRATION.md](MIGRATION.md); a supported installer path is not a claim of testing
every OS/architecture or physical device.

## Install

As the intended non-root user (not root):

```sh
git clone --branch Trixie https://github.com/mathisono/Diablo-DATV-Studio.git
cd Diablo-DATV-Studio
bash scripts/install-diablo.sh
```

The script installs distribution build tools, FFmpeg, and JSON-C headers; builds
pinned libubox and ucode with fs/socket/uloop; builds the C supervisor/config
writer; creates private initial configuration; and installs a foreground launcher.
It does not change apt sources, upgrade the OS/kernel, reboot, alter Secure Boot,
install a DekTec driver, or automatically start/enable anything.

Optional controls:

```sh
bash scripts/install-diablo.sh --prefix "$HOME/diablo-local" --jobs 2
# If dependencies are already installed:
bash scripts/install-diablo.sh --skip-system-packages
```

Default prefix: `$HOME/.local/share/diablo-datv-studio`. `logs/install.log` contains
build evidence; `runtime/` contains ucode/libubox; `diablo.env` holds launcher
settings; `state/` holds config, presets and private camera URLs. The checkout
must remain in place. A rerun preserves existing config and `diablo.env`.

## Start, connect, stop

```sh
"$HOME/.local/share/diablo-datv-studio/bin/diablo-studio"
```

Visit **http://127.0.0.1:8080/** on the host. From another computer, tunnel it:

```sh
ssh -N -L 8080:127.0.0.1:8080 your-user@your-encoder-host
```

Then visit http://127.0.0.1:8080/ on that computer. The web daemon binds loopback;
for LAN/public HTTP use an authenticated TLS reverse proxy with its exact
`PORTSDOWN_ALLOWED_HOST`. Do not expose the plain control API directly.

**Ctrl+C** stops both processes and the supervisor's owned source pipelines.
The launcher refuses a second instance in the same runtime directory.
No default service autostart is configured. The existing `systemd/portsdown-*`
units are advanced templates for a dedicated account, not used by this installer.

## First configuration

1. Set **CALLSIGN** and **Service name**, then Save configuration. No station
   identity is supplied by the installer.
2. For SRT, enable the desired input slot and use its displayed caller URL.
   Select **Direct source → SRT**, choose that slot, and save. Example:
   `srt://ENCODER_LAN_IP:9101?mode=caller&latency=200000`.
3. For an IP camera, enter its RTSP URL in **IP CAM input encoders → Save IP**.
   Use **Restart** to reconnect. Each camera is configured independently;
   saved URLs are not returned to the browser. Special characters in credentials
   are normalized by the UI backend. Keep URLs out of screenshots and shell history.
4. For HDMI/Pi Camera/IPTS, select the source and its actual device/index/port.
   Access to V4L2/ALSA/DRM devices requires the appropriate host groups. This
   installer does not seize a camera used by another service.
5. Use the selectors below the preview for four-source multiview.
6. **Start output TS** is separate from **Arm / Start TX**. Local TS defaults to
   loopback UDP `127.0.0.1:12010`; receiving TS does not prove RF/ASI output.

Default ports: HTTP 8080/TCP; preview ingress 8082–8092/TCP (loopback); SRT inputs
9101–9105/UDP (network); per-slot TS 12001–12005/UDP (loopback); IPTS preview
10000/UDP (loopback by default). Restrict SRT access to intended senders. If the
host has multiple interfaces, set `PORTSDOWN_SRT_ADVERTISE_HOST` in `diablo.env`.
Any custom port blocks must be disjoint and agree between both processes.

## Update / rollback

Stop Diablo, preserve a private backup of the install prefix's `state/` and
`diablo.env`, then:

```sh
cd Diablo-DATV-Studio
git switch Trixie
git pull --ff-only origin Trixie
bash scripts/install-diablo.sh --skip-system-packages
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
