# Shared-password LAN access acceptance — 2026-11-25

## Scope and result

**PASS for direct HTTPS login and password-authenticated two-host control.**
TANK (Pi 4 ARM64 Debian 13) was MASTER; VideoLP3D (Mint 22.3 x86-64) was SLAVE.
Both ran isolated working-tree builds based on `ed58154`, private temporary
configuration and generated test passwords. The existing installed applications
were not reconfigured. No personal password was used or saved for deployment.

Only mock TX and mock safe-off hooks were installed in the test environment.
**No RF, ASI, SRT media, physical camera or rover operation was used.** This is
not a new claim of hardware output or complete peer video integration.

[Machine-readable results](shared-password-2026-11-25.json)

## Checked behavior

| Check | Result |
| --- | --- |
| Direct HTTPS on both LAN addresses, certificate verified | Pass; no SSH browser tunnel |
| No cookie: state, preview and TX command | HTTP 401 on both hosts |
| Plain HTTP/internal peer ports from LAN | Not reachable |
| Matching password: peer TLS, configuration, telemetry | Pass |
| Login while mock TX is active | TX and heartbeat/telemetry continue on both hosts |
| SLAVE web start locked, signed-in local E-Stop | Pass; MASTER request cleared and stopped status returned |
| Missing MASTER heartbeats | Mock TX stopped in 1.136 s |
| Wrong peer password while MASTER owns SLAVE | Rejected; active connection and mock TX unchanged |
| Second matching-password controller while MASTER owns SLAVE | Rejected without evicting active controller |
| Explicit handover after old MASTER disconnects | Matching-password controller accepted; no automatic TX |
| MASTER disconnect | Mock TX stopped in 0.029 s |
| Daemon restart | Browser sessions invalidated; peer reconnect does not restart TX |
| TLS transport process killed | Control link closed and mock TX stopped |
| Cleanup | All test-owned processes stopped on both hosts |

These stop timings are observed mock-process behavior, not measured RF/PTT-off.
SSH was used to administer the isolated test processes, not to carry GUI or peer
connections. Test HTTPS was TCP 28443 and peer TLS TCP 28181; normal installation
defaults are 8443 and 8181.

## Important correction discovered during testing

PBKDF2 password checking takes about **2.03 s on TANK**, versus **0.26 s on
VideoLP3D**. The initial synchronous implementation could delay the control loop.
The final implementation runs it in **one bounded uloop background task**, with
rate limiting and a ten-second timeout. The repeated two-host test signed into
both machines during mock TX and verified uninterrupted heartbeat/telemetry.
No cryptographic work factor was reduced to hide the timing problem.

## Local automated and browser checks

The hardware-free suite completed **59 tests: 58 passed, one Pi-only test skipped**
on the x86-64 development host. It includes real stunnel HTTPS tests for:

- Protected API/app/previews/SSE, wrong password and rate limiting.
- Secure/HttpOnly/SameSite cookies, cross-origin POST rejection.
- Logout and expiry closing existing SSE connections; stale-cookie denial.
- Private password record permissions; same-password peer key derivation with
  independently salted browser verifiers.
- First-start startup/idle check plus HTTPS 401 check, certificate address change,
  and certificate retention on ordinary access-setup reruns.

One initial full-suite attempt failed because this development host lacked the
json-c development pkg-config file; the official development package was
extracted into a private dependency directory and the complete suite rerun.
This was an environment prerequisite failure, not a suppressed assertion.

Real Chromium verified empty login page → password sign-in → dashboard → Sign
out → login, and that JavaScript cannot read the HttpOnly session cookie.
[Actual screenshot](../images/diablo-login.png). The browser test pins the fixture's
certificate public key; it does not disable all certificate checks.

## Reproduce

After a normal installation, run the suite described in [DEVELOPMENT](../DEVELOPMENT.md).
For the optional two-host harness:

```sh
python3 scripts/dev/test-access-two-host.py --help
```

Supply the two SSH aliases, existing source checkouts/native runtime paths, LAN
addresses and stunnel binaries. The harness generates temporary credentials and
sends them over SSH stdin, uses real HTTPS/TLS-PSK on the LAN, and cleans up its
owned mock processes. It requires free test ports and Python only for testing.
It does not deploy a permanent password, create boot services or open firewall rules.

## Remaining boundaries

See [LAN_ACCESS](../LAN_ACCESS.md). Shared password means shared control, not
per-user roles. Local OS processes are trusted. Media SRT/UDP protection remains
separate; the shared GUI/peer password is not an SRT passphrase. Optional remote
preview embedding may be restricted by cross-origin cookies. This test is not
an independent penetration audit or Internet-exposure qualification.
