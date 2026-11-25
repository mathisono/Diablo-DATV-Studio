# LattePanda 3 Delta — DTA-2145 driver bring-up

Diablo's current repository is [mathisono/Diablo-DATV-Studio](https://github.com/mathisono/Diablo-DATV-Studio),
branch **Trixie**. For the new web GUI use [INSTALL.md](INSTALL.md); these
hardware/environment findings are retained and remain separate from GUI setup.
The old `portsdown4_NTSC` paths and commits below identify historical evidence.

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
bash scripts/install-dektec-asi-env.sh
bash scripts/install-dektec-dta.sh --status
```

The environment script invokes the driver installer, installs the pinned
official TSDuck package and FFmpeg, verifies device enumeration and performs
finite QSV and `libx264` probes. QSV failure is recorded but does not reject
the software fallback. Both scripts never start ASI output.

The driver script requires the card to enumerate, installs build dependencies and
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

The installed `svrename` processor also changed the copied TANK file's
service name to `DATV Test` **offline** while retaining all 6,135 packets,
zero unexpected discontinuities, and successful FFmpeg decode. This checks
the metadata operation used by the ASI-file launcher without opening the card.

Intel Jasper Lake QSV **does encode H.264**, but the tested driver/runtime
accepts constant-QP rate control, not bitrate-based CBR/VBR or ICQ. After
adding the account to `render` and `video`, a direct VAAPI test reported
`supported modes: CQP`; `h264_qsv -b:v 1484k` and
`h264_qsv -global_quality 24` failed with `Selected ratecontrol mode is
unsupported`. A short QSV encode succeeded with:

```sh
ffmpeg -hide_banner -f lavfi -i 'testsrc2=size=1280x720:rate=24' -t 2 \
  -vf format=nv12 -c:v h264_qsv -low_power 1 -qscale:v 30 -b:v 0 \
  -y qsv-cqp-test.mp4
```

The installer now uses this bounded CQP probe and retains `libx264` as the
fixed-bitrate fallback. A separate 3-second QSV H.264/AAC 720p/24 TS at
QP 30 and 3,071,588 bit/s muxrate decoded without error; `tsanalyze` reported
6,153 valid packets, PCR-derived bitrate 3,071,588 bit/s, service `DATV
Test`/`KJ6DZB`, and zero unexpected discontinuities. At QP 24, the same
synthetic source exceeded the muxrate and FFmpeg warned `dts < pcr, TS is
invalid`. **CQP is not a guaranteed bitrate limit**: tune QP and validate
representative content before using it with a fixed-rate TS/ASI path. The
host has `intel-media-va-driver` 24.1.0, `i965-va-driver` 2.4.1, `libmfx1`
22.5.4, and `libvpl2` 2023.3.0. No physical ASI output was tested.

## Isolated web-control build

The `headless-ucode-control` branch was shallow-cloned under
`/home/mat/dektec-asi/src/portsdown4_NTSC` at commit `aba3ac8`. Both C
utilities built natively with `make -C control`. The host had no packaged
`ucode`; `libubox` commit `a396f38a8568a1d670c240465cd8d24fdfdf6463`
and `ucode` commit `a2c42eac6369a0bba0315007c7dc7b7130275340` were
built with CMake into `/home/mat/dektec-asi/opt` without system installation.
The working ucode Git URL is `https://github.com/jow-/ucode.git` (the earlier
`https://git.openwrt.org/project/ucode.git` attempt returned 404). Required
system build packages were `cmake` and `libjson-c-dev`. Run the hardware-free
control tests with:

```sh
cd /home/mat/dektec-asi/src/portsdown4_NTSC
LD_LIBRARY_PATH=/home/mat/dektec-asi/opt/lib \
UCODE=/home/mat/dektec-asi/opt/bin/ucode \
UCODE_MODULE_DIR=/home/mat/dektec-asi/opt/lib/ucode \
python3 -m unittest tests/test_headless_control.py -v
```

All **30** tests passed, including the ASI board/safe-off fail-closed checks.
No web service or TX launcher was installed or enabled. This is software
validation on the actual x86-64 host, not a physical ASI playout test.
