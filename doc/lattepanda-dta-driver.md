# LattePanda 3 Delta — DTA-2145 driver bring-up

On 24 November 2026, the LattePanda (`VideoLP3D`, Linux Mint 22.3 x86-64,
kernel `6.14.0-37-generic`) enumerated the DTA-2145 Rev. 2 at PCI `02:00.0`
as `1a0e:0861`. This is the **legacy `Dta`** device, not `DtPcie`.

The official [DekTec Linux SDK 2026.09.0](https://www.dektec.com/downloads/SDK/)
was downloaded from
`https://www.dektec.com/products/SDK/DTAPI/Downloads/LinuxSDK_v2026.09.0.tar.gz`.
Its observed SHA-256 is
`f7bdf97421b39047efa379cfffbd208114bf0f3cb37c3565d709e46f3157fdf3`.
The vendor's `Install_Dta` script built and installed `Dta` and `DtaNw`
through DKMS for the running kernel. The build log is on the target at
`/home/mat/dektec-asi/logs/dta-dkms-install.log`.

**Initial blocker, now resolved:** Secure Boot rejected the DKMS module with
`Key was rejected by service` because the signing MOK was not enrolled. The
operator disabled Secure Boot locally and rebooted. The card is now bound to
`Dta`, and non-root `tsdektec` identifies device 0, input channel 0 on
physical port 1 (top), and output channel 0 on physical port 2. The installed
TSDuck package is official Ubuntu 24 x86-64 release `3.45-4798`, with DTAPI
`6.13.0.242` and Dta `4.28.15.294`; the package SHA-256 observed locally is
`0023689f76e75b64e45253771208bcf8ca95b91fbfd0900da097c729f3c39fde`.
No ASI output or RF transmission has been started.

On a future reinstall where Secure Boot blocks the module, enter the
LattePanda's **local UEFI setup**, disable Secure Boot, and boot Linux again.
This cannot be changed over SSH. The DKMS build normally does not need
rebuilding after the firmware change. Check with:

```sh
sudo mokutil --sb-state
sudo modprobe Dta
dkms status
lspci -nnk -d 1a0e:0861
lsmod | grep '^Dta'
```

An alternative is enrolling the existing MOK through the firmware's next-boot
MOK manager, leaving Secure Boot enabled; that also requires local interaction.
Do not assume the module is usable merely because DKMS reports `installed`.

For a fresh, matching x86-64 installation, from this repository run:

```sh
bash scripts/install-dektec-dta.sh
bash scripts/install-dektec-dta.sh --status
```

The script requires the card to enumerate, installs build dependencies and
matching headers, verifies the pinned official SDK archive, installs only
the `Dta`/`DtaNw` DKMS modules, attempts to load `Dta`, and replaces the
vendor's world-writable device-node mode with a `dektec` group rule (`0660`).
The user running the script is added to that group; log in again before
non-root card access. It does **not**
start ASI playout or control external RF. Once the driver loads, verify card
access with `tsdektec` after installing a TSDuck build with DekTec support.
On this host, the vendor package is `tsduck_3.45-4798.ubuntu24_amd64.deb`
from the [official TSDuck binaries page](https://tsduck.io/tsduck-binaries/).
Confirm output channel and BNC mapping before a finite ASI test. Keep the
external modulator's RF disabled during bring-up.

## Offline transport-stream checks

The LattePanda generated a 5-second SMPTE-bars H.264/AAC 1280×720/24 TS at
`/home/mat/dektec-asi/samples/720p24-3071588.ts`. `tsanalyze` reported
10,175 valid 188-byte packets, no invalid sync or transport-error packets,
PCR-derived bitrate **3,071,588 bit/s**, service `DATV Test`/`KJ6DZB`, video
PID `0x0100`, audio PID `0x0101`, PMT `0x1000`, and zero unexpected
discontinuities. FFmpeg decoded it without error.

An independently generated 3-second TANK sample was copied byte-for-byte to
`/home/mat/dektec-asi/samples/tank-720p24-3071588.ts` (SHA-256
`32fd13d73d07af4dc5e9007eedcae8edaa71a5d932c775e6d0d692c72e3c9b03`).
TSDuck on the LattePanda reported 6,135 valid packets, no transport errors,
the same PCR-derived 3,071,588 bit/s rate, service `ASI Test`/`KJ6DZB`, and
FFmpeg decoded it without error. These checks validate file compatibility,
**not physical ASI output**.

Intel Jasper Lake QSV was not yet demonstrated: the first short H.264 QSV
encode failed before GPU group access was granted; after adding the account
to `render` and `video`, it reached the QSV runtime but rejected the selected
rate-control modes. Software `libx264` worked for the finite TS and remains
the fallback.
