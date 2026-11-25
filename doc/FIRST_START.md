# First start — get your first picture

**Yes: you can install Diablo and test video yourself.** Start with the web page
and a test picture. You do **not** need a transmitter board, camera or OBS.

This is a **development release**. The basic install does not enable radio
transmission or ASI output. Those require separate hardware setup and testing.

## 1. What you need

- A **Raspberry Pi 4 with a 64-bit Trixie OS**, or a **64-bit Linux PC**.
  Our checked systems are a Pi 4 running Debian 13/Trixie and a LattePanda running
  Linux Mint 22.3. Ubuntu 24.04 is also an installer target, but not tested here.
- Linux already installed, an Internet connection, and several GB of free space.
- Your normal Linux login and its password, with permission to install software
  (`sudo`). Do not log in as `root`.
- A web browser, either on that computer or on another computer.

Windows/macOS can display the web page, but **Diablo itself runs on Linux**.
Other ARM64 boards and 32-bit Pi systems are not the beginner-tested path.
We have tested new application installs on existing Linux systems, **not every
fresh OS image**. Keep a working installation on a separate SD card if needed.

**No screen attached to your Pi?** Enable SSH and set your username/password in
Raspberry Pi Imager before first boot. In Windows PowerShell, macOS Terminal, or
a Linux terminal, connect with `ssh YOUR_USER@YOUR_PI_IP` (replace both values).
The remaining install commands run **on the Pi**, in that SSH window.

## 2. Install

Open **Terminal** on the Linux computer (usually **Ctrl+Alt+T**), or use the SSH
window described above. Copy this entire block, paste it, then press Enter:

```sh
cd "$HOME" &&
sudo apt-get update &&
sudo apt-get install -y git &&
git clone --branch Trixie https://github.com/mathisono/Diablo-DATV-Studio.git &&
cd Diablo-DATV-Studio &&
bash scripts/first-start.sh
```

When asked for your password, type your **Linux login password** and press Enter.
It is normal for nothing—not even dots—to appear as you type. Building the
software can take several minutes; keep the window open.

**Already have a `Diablo-DATV-Studio` folder?** Do not delete it or clone over it.
Use [Install / update](INSTALL.md#update-an-existing-install) instead.
If a command fails, stop and use [Help](#if-something-does-not-work) below.

## 3. Answer the setup questions

For your **first test**, use these choices. Press **Enter** to keep a value shown
in square brackets, or type the replacement and press Enter.

| Setup question | What to enter |
| --- | --- |
| CALLSIGN | Your callsign; `N0CALL` is suitable only for this non-transmitting test if you do not have one |
| Service name | `My video test` |
| Direct source | `SRT` — receives video; our test sends it from this same computer |
| SRT input slot | `1` |
| SRT advertised LAN IPv4 | Press Enter to keep the detected address; it is not needed for the local test |
| Start selected SRT listener on each launch? | Type `yes` |
| Loopback web GUI port | Keep `8080`; if already occupied, use `18880` |
| Device groups to add | Leave blank and press Enter; no capture device is needed yet |
| Start GUI now in foreground? | Type `yes` |

**Success looks like:** `GUI startup/API/shutdown check passed`, followed by a
browser address. The last answer starts Diablo and keeps it running in this
terminal. Leave that terminal open. No service is started automatically at boot.

## 4. Open the web page

**Browser on the same Linux computer:** open the **Browser:** address printed by
setup. Normally it is **http://127.0.0.1:8080/**.

**Browser on another computer:** open a second terminal **on the computer with
the browser**. Paste the complete **Remote browser: ssh ...** command printed
by setup, enter the Linux computer's password if asked, and leave that window
open too. Then open the printed browser address. A successful tunnel may show
no further text; that is normal. This connection is called an **SSH tunnel**.

`127.0.0.1` means “this computer”; it is not the Pi's network address. Typing the
Pi's IP into the browser is not enough with this default setup. If the tunnel
says **Connection refused**, SSH must first be enabled on the Linux computer;
see [SSH help](INSTALL.md#ssh-help).

You should see **Diablo DATV Studio**, source **SRT input**, slot **1**, and a
waiting picture. **Do not press Arm / Start TX** to see video.

## 5. Show a test picture — no extra hardware

Open another terminal **on the Diablo Linux computer**. If using SSH, open a
second SSH login to that same computer. Leave Diablo and the browser tunnel
running. Copy and run:

```sh
cd "$HOME/Diablo-DATV-Studio" &&
bash scripts/test-srt-input.sh
```

Watch the **Low-resolution preview** in the web page:

1. Within several seconds, a moving test picture should replace the waiting card.
2. The sender runs for **30 seconds**, then stops by itself.
3. Within several seconds of stopping, **NO SRT INPUT 1** should return.
4. Run the command again: live video should return.

If it stays on the waiting card, expand **SRT input encoders** and check input 1
is enabled. Disconnect any other sender using input 1. Select **Direct source →
SRT input**, choose **SRT encoder 1**, and click **Save configuration** if needed.

**A successful picture → waiting → picture test means your basic installation
and local SRT preview work.** It does not prove a remote network connection,
RF transmission or ASI output. The preview is video-only; the test sends an
audio tone but you will not hear it in this preview.

![Example waiting state after an SRT sender stops](images/diablo-picam-srt-waiting.png)

This screenshot is from a hardware test installation; some output settings differ
from your fresh setup. The waiting image and SRT slot behavior are what to check.

## 6. Stop and start again

To stop Diablo, click its original terminal and press **Ctrl+C**. Stop any SSH
tunnel with Ctrl+C too. To start Diablo another day, run this **on the Linux
computer**, then reopen the browser/tunnel as above:

```sh
"$HOME/.local/share/diablo-datv-studio/bin/diablo-studio"
```

Your settings are saved. Keep the `Diablo-DATV-Studio` folder in place; the
installed launcher still uses it.

## Next: your own video

Start with **one** source, after the test above works:

- **OBS / another SRT sender:** use input 1's caller link in **SRT input encoders**.
  The sender must support **SRT with MPEG-TS**, not RTMP. The link needs the Linux
  computer's LAN address, not `127.0.0.1`. Allow UDP 9101 from your sender if a
  firewall blocks it. The SSH browser tunnel does not carry the video stream.
- **USB HDMI capture:** follow the [USB capture guide](usb-hdmi-capture.md).
- **RTSP camera:** use **IP CAM input encoders → Save IP**, then **Restart**;
  select that camera as the direct source. Keep its password private.
- **Pi Camera, software TS output, permissions or scripted setup:** see the
  [advanced setup reference](INSTALL_REFERENCE.md).
- **ASI or a radio transmitter:** read the [current limitations](KNOWN_ISSUES.md)
  and [ASI guide](asi-output.md) first. These are separate from first start.

## If something does not work

| What you see | What to do |
| --- | --- |
| Install reports an error | Stop there. Copy the last error lines, not pages of scrolling output |
| “Already running” | Return to the original Diablo terminal and press Ctrl+C; do not delete lock files |
| “Address already in use” | Stop Diablo, rerun setup and choose web port `18880`; use its newly printed URL/tunnel |
| Browser cannot connect | Check Diablo is still running; on another computer, also check the SSH tunnel |
| Test sender reports a connection error | Enable SRT input 1 and run the sender on the Diablo computer, not your browser computer |
| Arm / Start TX is disabled | Expected for this basic installation; preview testing does not need TX |

For a diagnostic report, run on the Linux computer:

```sh
cd "$HOME/Diablo-DATV-Studio" &&
bash scripts/install-diablo.sh --check
```

[Report a problem](https://github.com/mathisono/Diablo-DATV-Studio/issues): include
your computer model, Linux version, the step that failed and the error text.
Install logs are in `~/.local/share/diablo-datv-studio/logs/`. Do not post camera
passwords, private settings, or backups.
