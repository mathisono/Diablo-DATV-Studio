# SDRangel experimental backend

This branch adds an opt-in standalone SDRangel headless exciter and DATV receiver.
Existing hardware launchers and ASI remain unchanged. Do not enable on a live
repeater until independent hardware RF-off, PTT and receiver tests pass.

## Installation and operator configuration

Install a build of SDRangel that includes the headless DATV modulator,
ATV modulator, DATV demodulator and your SDR device plugins. Upstream:
https://github.com/f4exb/sdrangel . Its REST documentation is served by
the SDRangel instance. The worker uses a separate loopback-only server,
a scratch configuration and a private runtime directory per RX/TX start.
It never runs an RF device at Diablo startup. Only one RX or TX process
is permitted by the existing supervisor. No automatic restart of RF.

Run the normal Diablo installer. In your operator-owned Diablo environment
(or /etc/portsdown/portsdown.env for systemd), set:

    PORTSDOWN_BOARD=sdrangel
    PORTSDOWN_TX_EXEC=/absolute/path/to/Diablo-DATV-Studio/control/sdrangel-worker.py
    PORTSDOWN_RX_EXEC=/absolute/path/to/Diablo-DATV-Studio/control/sdrangel-worker.py
    PORTSDOWN_SDRANGEL_BINARY=/usr/bin/sdrangelsrv
    PORTSDOWN_SDRANGEL_PROFILE=/absolute/path/to/private/sdrangel-profile.json
    PORTSDOWN_SAFE_OFF_EXEC=/absolute/path/to/verified/hardware-safe-off-hook

Use export statements for the foreground launcher's shell environment.
The required safe-off hook must actually disable the physical transmitter,
PA/PTT or equivalent RF path and return success within the existing
supervisor's 500 ms budget. Do not replace it with a success-only dummy.
The worker does not assert an external PTT; site-specific PTT sequencing
and independent RF sensing remain separate hardware integration tasks.

The host JSON file is operator-owned, not web-writable. Copy
control/sdrangel-profile.example.json as a starting point and replace
device settings with values verified on the selected hardware (the
example intentionally contains no usable hardware serial or tuning).
Inspect GET /sdrangel/devices?direction=1 and direction=0, device settings
and channel settings in the upstream API. Profile device selectors are
hwType, serial and optionally sequence. deviceSettings contains exactly
one hardware-specific object with explicit scalar settings from that
device's API, including frequency, sample rate, gain, bandwidth and
interpolation where relevant. Verify sample rate/occupied bandwidth
and compliance before any RF use.

Select SDRangel and a television mode under Output settings, save,
then use the existing Arm / Start TX or Start RX buttons. Stop before
changing mode. The input is the host SDRangel profile, not the legacy
source-preview selector. RX has a separate DATVDemod profile; it is
not automatically tuned to the TX mode. An absent profile disables the
corresponding start control; the worker validates the profile again.
Master/Slave use is blocked at both API and process supervisor.

## Mode support

- DVB-S and DVB-S2 QPSK: transport stream file or local UDP, with
  symbol rate, FEC, roll-off and RF bandwidth in the host profile.
- Analog NTSC-style: 525 lines, 30 FPS, monochrome.
- Analog PAL-style: 625 lines, 25 FPS, monochrome.
- NBTV: configurable lines and frame rate, short sync.
- Analog FM television: configurable lines, frame rate and FM excursion.
- Analog sources: built-in patterns, local image or video file.
  No audio carrier, color encoding, exact NTSC-M timing, live capture
  integration, or analog receive in this headless implementation.

For DATV UDP, configure an existing FFmpeg encoder to send MPEG-TS to
the profile's loopback address/port. Its transport bitrate must fit
the selected modulation and FEC. The legacy direct capture, SRT and
multiview output pipeline is not automatically wired to this backend.
No stream-loss RF inhibit is implemented in this first integration.
Keep testing on an attenuated bench connection with a dummy load or
file sink and independently verified RF-off.

## Monitoring

The worker polls device run state and channel reports. It writes an atomic
PID-tagged timestamped telemetry file in the existing runtime directory.
The authenticated /api/state response includes sdrangel.tx and sdrangel.rx.
The browser already polls /api/state once per second, so RX/TX telemetry
appears without another exposed service or direct browser-to-SDR API.
Missing, stale, disconnected or mismatched-PID telemetry is unknown.
A stopped supervisor process is not proof that a physical PA is off.

Reported metrics depend on the actual plugin and version: channel-relative
power, sample rate, data rate, UDP byte count, MER/CNR, decode flags,
symbol rate and MODCOD when available. Missing values are not fabricated.
Video decode is not a certified RF lock indicator; no BER, actual watts,
spectrum waterfall, decoded RX preview or RF detector is claimed here.

## Acceptance test

1. Run software tests and verify the correct SDRangel plugins and API
   schema on the exact installed version. Older Swagger enum descriptions
   may differ from current source (e.g. DATV source Image=0, File=1, UDP=2).
2. Test with a file sink first, then verify physical safe-off independently.
3. Start TX in each of six modes, confirm device running and channel reports,
   and use E-Stop. Test missing profile, unavailable device and killed server.
4. Feed known TS via FFmpeg to DVB-S/DVB-S2 and check transport bitrate
   and pictures on a ProView receiver. Test no-input behavior explicitly.
5. Stop TX, start DATV RX, verify decode and MER/CNR reports against known
   signal. Confirm TX/RX mutual exclusion. Stop RX and confirm stale
   values are not shown as live. Analog reception is a separate task.
6. Verify RF off after supervisor crash, API timeout, service stop and
   hardware disconnect before using a real antenna.

Hardware compatibility, SDRangel build/package availability, full
software regression and over-the-air interoperability need validation.
