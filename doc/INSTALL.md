# Install / update — the short version

## First installation?

Use **[First start: get your first picture](FIRST_START.md)**. It takes you through
one setup command, the wizard answers, opening the browser and a 30-second test
picture. No camera or transmitter board is needed for that test.

Diablo runs on Linux. The checked machines are a **Pi 4 with 64-bit Debian
13/Trixie** and a **64-bit PC with Mint 22.3**. Raspberry Pi OS Trixie 64-bit and
Ubuntu 24.04 are installer targets; not every OS image or board has been tested.
A 64-bit Pi is an ARM64 computer. Windows/macOS can be browser clients, not the
Diablo server. [Advanced platform details](INSTALL_REFERENCE.md#scope).

The basic install starts **no RF or ASI output** and does not install board
drivers. It does not replace Linux, reboot the computer, or enable startup at boot.

## Everyday start and stop

Run this in Terminal **on the Linux computer running Diablo**:

```sh
"$HOME/.local/share/diablo-datv-studio/bin/diablo-studio"
```

Leave it running and open the browser address from setup, normally
**https://YOUR_LINUX_IP:8443/**. Sign in with the shared password you chose during
setup; no SSH tunnel is needed. See
[First start, step 4](FIRST_START.md#4-open-the-web-page).

To stop: return to the Diablo terminal and press **Ctrl+C**. Settings are saved.
Keep the downloaded `Diablo-DATV-Studio` folder; the launcher needs it.

## Update an existing install

These steps assume you used the default folders in First start. If someone
customized your installation, use the [advanced reference](INSTALL_REFERENCE.md)
with them instead.

**1. Stop Diablo** with Ctrl+C in its terminal. Do not update while it is running.

**2. Make a private backup.** Run on the Diablo computer:

```sh
umask 077
backup="$HOME/diablo-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup" &&
cp -a "$HOME/.local/share/diablo-datv-studio/state" \
      "$HOME/.local/share/diablo-datv-studio/diablo.env" "$backup/" &&
if [ -d "$HOME/.local/share/diablo-datv-studio/security" ]; then
  cp -a "$HOME/.local/share/diablo-datv-studio/security" "$backup/"
fi &&
git -C "$HOME/Diablo-DATV-Studio" rev-parse HEAD > "$backup/source-commit.txt" &&
echo "Backup saved in $backup"
```

Continue only after **Backup saved in ...** appears. Keep that folder private:
settings can include camera passwords.

**3. Download and install the update:**

```sh
cd "$HOME/Diablo-DATV-Studio" &&
git switch Trixie &&
git pull --ff-only origin Trixie &&
bash scripts/install-diablo.sh
```

Use **Trixie**, not `master`. The installer keeps your saved settings. Let it
finish; it may ask for your Linux password to install required packages. Do not
put `sudo` before `bash scripts/install-diablo.sh`.

If Git reports local changes, conflicts or “cannot fast-forward,” **stop and ask
for help**. Do not delete files or use a force/reset command to get past it.

**4. Enable protected LAN access if upgrading an older installation.** While
Diablo is stopped, run:

```sh
bash scripts/setup-access.sh
```

Choose the role and a shared password. Existing protected installs may skip this;
updates preserve their password and certificate. Once signed in, use **Access / Peer settings**
to show/change the password, select Master/Slave, and enter the Slave IP. See [web setup](LAN_ACCESS.md).

**5. Start Diablo** using the Everyday start command above. Run the
[first-picture test](FIRST_START.md#5-show-a-test-picture--no-extra-hardware)
again if you still use SRT input 1. Other source users should check their saved
source, its preview and stop behavior.

**If an update fails:** keep the error text and your backup. Do not overwrite
private settings while guessing. [Rollback details for an experienced helper](INSTALL_REFERENCE.md#update--rollback).

## Change first-start choices

Stop Diablo, then run:

```sh
cd "$HOME/Diablo-DATV-Studio" &&
bash scripts/first-start.sh --configure-only
```

This reuses the installed software and offers your saved choices. It creates
private configuration backups. It is for **standalone, unarmed setups**; existing
Master/Slave or hardware-output configurations are intentionally not reset.

To stop enabling the selected SRT listener automatically on future launches:

```sh
cd "$HOME/Diablo-DATV-Studio" &&
bash scripts/first-start.sh --configure-only --disable-srt
```

Keep the listener answer `no` when prompted. This does not enable/disable a boot
service: Diablo still needs to be launched manually.

**Downloaded the folder, but setup did not finish?** Run
`cd "$HOME/Diablo-DATV-Studio" && bash scripts/first-start.sh` to retry the full
setup instead. `--configure-only` is for a successfully installed runtime.

## SSH help

Only needed for remote Linux installation/maintenance, not browser access. On a new Pi, use
Raspberry Pi Imager's SSH option. On an already running supported Linux machine,
open a terminal **on that machine** and run:

```sh
sudo apt-get update &&
sudo apt-get install -y openssh-server &&
sudo systemctl enable --now ssh
hostname -I
```

The last line shows network addresses. Use that machine's LAN address and Linux
username to connect. Do not forward router ports or expose it to the Internet
for this test. Browser access uses the printed HTTPS address directly.

## More help, only when needed

- [Beginner troubleshooting](FIRST_START.md#if-something-does-not-work)
- [Advanced installation, custom folders, ports, scripted setup and rollback](INSTALL_REFERENCE.md)
- [Hardware output and remaining limitations](KNOWN_ISSUES.md)
- [DekTec ASI setup and test results](asi-output.md)

The old Portsdown `install_portsdown.sh` and `update.sh` are **not** Diablo's
installer/updater. Use the commands above.
