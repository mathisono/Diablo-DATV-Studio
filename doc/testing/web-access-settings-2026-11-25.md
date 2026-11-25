# Web access / Master–Slave settings acceptance — 2026-11-25

The new **Access / Peer settings** popup replaces terminal-based routine pairing
and password changes. First Start still creates the initial shared password.

## What was tested

- Actual Chromium against the managed HTTPS launcher: login, popup open,
  explicit saved-password reveal/hide, select Master, enter an example Slave IP,
  apply, automatic restart/sign-in, and read back the saved role/address.
- Responsive popup at a 390-pixel viewport. The published
  [screenshot](../images/diablo-access-settings.png) is a real desktop capture with
  passwords hidden/empty; `192.0.2.10` is a documentation-only address.
- Six local HTTPS/access regression tests: unauthenticated denial, same-origin
  checks, cookie protection, logout/expiry closing event and preview streams,
  First Start/certificate reruns, salted records/shared peer-key derivation,
  encryption/tamper/permissions, old-record display-copy upgrade only after a
  correct login, all three role changes, password change and session invalidation.
- Shell and JavaScript syntax checks passed. Full hardware-free suite: **61 tests,
  60 passed and one Pi-only test skipped** (130.967 seconds).

## Real two-host test

**TANK (AArch64)** was Master and **VideoLP3D (x86-64)** was Slave, using isolated
user-local checkouts, temporary environments and generated passwords. Both
started as Standalone under the real managed launcher and stunnel HTTPS.
The test drove the same authenticated endpoints used by the popup:

| Check | Result |
| --- | --- |
| Set Slave and Master/address through the web API | PASS — peer configuration and return telemetry ready |
| Reveal saved password on both authenticated sessions | PASS |
| Change access settings while mock TX runs | PASS — rejected on both hosts; output not interrupted |
| Slave E-Stop | PASS — mock TX stopped and Master request cleared |
| Change Slave password first | PASS — old-password control disconnected; old browser password rejected |
| Change Master to the same new password | PASS — control/telemetry reconnected; TX remained stopped |
| Switch Master back to Standalone in web settings | PASS — released Slave, which remained stopped |
| Logs and cleanup | PASS — no plaintext passwords logged; owned test processes exited |

[Machine-readable checks and source SHA-256 manifest](web-access-settings-2026-11-25.json).
The remote checkout HEADs in that report identify their base checkouts, not the
new tested revision: current working-tree files were copied into those isolated
directories. The manifest was compared against both hosts after the test and
records the exact tested control/launcher/UI sources.

**No real TX, ASI, camera capture, rover interruption, or installed-password change
occurred.** TX was a mock script with a private simulated safe-off hook and fake
Express control file. This verifies web configuration, authentication, lifecycle
and control telemetry—not physical PTT, RF, ASI or source/video quality.

## Reproduce

Local runtime plus a compatible stunnel4 are required:

```sh
export DIABLO_TEST_RUNTIME=/path/to/installed/runtime
export PORTSDOWN_STUNNEL=/path/to/stunnel4
python3 -m unittest discover -s tests -p test_access.py -v
python3 scripts/dev/capture-login.py
```

The capture tool additionally needs Chromium and the Python requests/websockets
development packages. It trusts only the temporary fixture certificate's SPKI;
it does not disable verification for arbitrary sites.

For two hosts, stage the current source and native C tools in isolated checkouts,
then use `python3 scripts/dev/test-access-settings-two-host.py --help`. Supply
both SSH aliases, repository/runtime paths, LAN addresses, stunnel paths and a
private output report location. The harness generates its passwords and passes
them through SSH stdin, never command arguments. It uses HTTPS 28443, peer TLS
28181 and private loopback/test ports; stop if these conflict with other services.
Do not substitute production environments or output launchers into this test.
