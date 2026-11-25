# LAN access — one shared password, no SSH tunnel

## First installation

Run the [First start wizard](FIRST_START.md). Choose a **12–128 byte shared
password** when asked, and repeat it. A long, unique passphrase is easiest to type.
This is not your Linux login password. Password characters are hidden while typing.

Setup prints an address such as **`https://192.168.3.33:8443/`**. Open **your
printed address** in a browser on any computer on the same LAN. Check the locally
issued certificate's SHA-256 fingerprint against setup's output on the first
visit, trust that certificate for this host, then sign in. No SSH tunnel is used.
Do not blindly accept a different fingerprint on a later visit.

A matching fingerprint can also be displayed on the Diablo Linux computer:

```sh
source "$HOME/.local/share/diablo-datv-studio/diablo.env"
openssl x509 -in "$PORTSDOWN_TLS_CERT" -noout -fingerprint -sha256
```

## Change access settings in the web GUI

Sign in, then click **Access / Peer settings** at the top of the dashboard.
The popup handles ordinary password changes and Master/Slave pairing—no Terminal
commands or SSH tunnel are needed after First Start.

![Access and Master/Slave settings popup, with password hidden](images/diablo-access-settings.png)

Actual Chromium capture of an isolated test installation. The selected Master
role and `192.0.2.10` address illustrate the form; use your own Slave's LAN address.
The password is hidden and no hardware output was running.

| Control | What to do |
| --- | --- |
| This computer acts as | Choose **Standalone**, **Master**, or **Slave** |
| Slave IP address | On Master, enter the Slave's IPv4 address only, e.g. `192.168.3.232`—not a URL, port or SRT link |
| Show saved password | Reveal the current password; **Hide saved password** hides it again. It clears after 30 seconds, when the tab is hidden, or when the popup closes |
| New shared password / Repeat new password | Leave both blank to keep it, or type the same new 12–128 byte password in both boxes |
| Apply & reconnect | Save, restart the control services, then return to sign-in |

**Stop TX, RX and output TS first.** Apply is rejected while an output is active
or a remote TX request is pending. Applying disconnects the old peer, restarts
previews/control services and signs out existing browser sessions. **It never
restarts TX automatically.** Sign in again with the saved (or new) password.

All signed-in operators have the same control rights, including viewing and
changing this password and changing the role. Even a Slave's locked dashboard
retains **Access / Peer settings** and local **E-Stop** for its operator.

## Pair a Master and Slave

Both computers must already have Diablo installed, First Start completed, and
Diablo running. Updating an older install? Follow [Install / update](INSTALL.md#update-an-existing-install).
Choose the same shared password during First Start, or change it in the popup.

### 1. Set up the Slave (remote transmitter)

1. Open **the Slave's HTTPS address** and sign in.
2. Click **Access / Peer settings**.
3. Select **Slave — receive IPTS over SRT**.
4. Keep its password, or enter your chosen shared password twice.
5. Click **Apply & reconnect**, then sign in again.

### 2. Set up the Master (video-producing computer)

1. Open **the Master's HTTPS address** and sign in.
2. Click **Access / Peer settings**.
3. Select **Master — produce video and control a Slave**.
4. Enter **the Slave's LAN IPv4 address**, not the Master's.
5. Make sure its shared password is **exactly the same as the Slave's**. A blank
   new-password field keeps this computer's password; it does not copy the other one.
6. Click **Apply & reconnect**, then sign in again.

### 3. Check the link, then configure video

Master's peer status should show **MASTER · linked**, configuration ready and
fresh Slave telemetry. A different password cannot establish the control link.
If it does not link, check both passwords, the selected roles, Slave address,
TCP 8181 access to the Slave, and that no other Master still controls it.

The peer connection authenticates automatically; browser login grants access to
the controls but does not establish the peer link itself. **Linked confirms
control communication, not video reception or RF output.** Configure the separate
SRT video stream and output hardware as described in [peer control](peer-control.md).
Slave is **IPTS over SRT only**. The shared password does not bypass valid-video
gates or hardware requirements, and does not automatically encrypt SRT media.

**Changing the password on a pair:** stop outputs on both, change Slave first,
then Master to the same password. The link drops while they differ and reconnects
when they match. TX stays stopped; old browser sessions must sign in again.

**Handover:** with outputs stopped, change the old Master to **Standalone** (or
stop its Diablo application). Then configure the replacement Master with the
Slave address and matching password. A second Master cannot evict an active one.

## Recovery or an older installation

Normal role/password changes belong in the popup. Use Terminal only if you cannot
sign in, have no protected access yet, or need to change the host's HTTPS address.

**Forgot the password?** On the Diablo Linux computer, stop Diablo with **Ctrl+C**,
then run as the Linux account that installed it:

```sh
cd "$HOME/Diablo-DATV-Studio" &&
bash scripts/setup-access.sh
```

Choose a new shared password twice; the old password is not required. Restart:

```sh
"$HOME/.local/share/diablo-datv-studio/bin/diablo-studio"
```

For custom installations add `--prefix /your/install/path` to setup. A valid
certificate for the same address is kept. An address change or certificate renewal
prints a new fingerprint. Back up `state/`, `security/` and `diablo.env` together,
privately; old backups still contain old password-derived keys and recoverable secrets.

## What is protected

- **HTTPS TCP 8443:** GUI, settings, commands, logs/SSE and every preview require
  a valid browser session. The login page and its CSS/JavaScript are public.
- **Peer TLS TCP 8181 on SLAVE:** password-derived pre-shared-key authentication
  happens before a connection reaches the control daemon. Master and Slave
  authenticate with the same key; no browser certificate setup is needed for peers.
- Cookies are Secure, HttpOnly and SameSite=Strict. Sessions last at most eight
  hours, expire on daemon restart, and are invalidated by **Sign out**. Logout and
  expiry close that session's event/video connections. They **do not stop TX**;
  use E-Stop/Stop TX for that. Password hashing runs in a bounded background worker
  so a slow login does not block control heartbeats.
- Login uses a salted PBKDF2-SHA256 verifier; peer TLS uses a separately derived
  key. **Show saved password** also requires a recoverable copy: AES-256-GCM
  ciphertext and a random local key are kept in separate owner-only files (0600)
  under the private `security/` directory. No plaintext password is stored there.
  The Linux account owner can recover it; this is not protection against a
  compromised OS account. Never publish this directory, environment files or backups.
  Older verifier-only installs gain the encrypted display copy after the first
  successful login. Passwords never appear in ordinary config/state APIs or logs.

The implementation uses the existing ucode daemon and minimal C tools plus
OpenSSL and **stunnel4**. No Python, Node.js or frontend framework is needed to run it.
This is LAN access control, not an independently audited Internet-facing service.
Do not expose these ports through your router to the public Internet.

### Local trust and media are separate

The main HTTP backend is loopback-only (`127.0.0.1:8080`); trusted local helpers
use loopback HTTP `18080` without a browser login. Peer plaintext internals use
loopback `18181`/`18182`. Local OS accounts/processes are trusted. Never forward
these internal ports to the LAN. Install/run as a dedicated trusted Linux user
on shared computers.

**The GUI/peer password is not automatically an SRT passphrase.** SRT media,
UDP TS, RTSP cameras and optional external preview consumers retain their own
access settings. Restrict those ports to the intended senders; separately
configure media encryption when required. The current sender URLs are not made
password-protected by signing into the GUI. A browser on MASTER must separately
sign into SLAVE to load its optional protected remote preview; cross-origin
cookie rules may prevent embedding it. Open SLAVE directly if needed.

### Ports and troubleshooting

| Symptom | Check |
| --- | --- |
| Cannot open the page | Use `https://` and the printed LAN IP/port; keep Diablo running; allow TCP 8443 from your LAN in the host firewall if necessary |
| Incorrect password | Use the Diablo shared password, not your Linux password; after repeated failures wait 30 seconds |
| Peer not linked | Same password on both, MASTER points to SLAVE, SLAVE role selected, TCP 8181 reachable, previous MASTER stopped |
| Login unexpectedly reappears | Session expired or daemon restarted; sign in again |
| Changed IP / HTTPS port | Stop Diablo, rerun `setup-access.sh --host NEW_IP --https-port 8443`, verify the printed fingerprint |
| Old install lacks stunnel | Run the normal `install-diablo.sh` update to install the new dependencies, then `setup-access.sh` |

The setup scripts do not edit firewall rules, enable boot services, or start
RF/ASI output. Low-level developers may explicitly use `first-start.sh
--local-only` without LAN exposure; this does not remove existing HTTPS settings.
