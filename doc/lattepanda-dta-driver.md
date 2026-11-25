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

**Current blocker:** Secure Boot is enabled; the DKMS signing certificate
`/var/lib/shim-signed/mok/MOK.der` is not enrolled. `sudo modprobe Dta` failed
with `Key was rejected by service`. The card has therefore **not** been
opened. No ASI output or RF transmission has been started. TSDuck is not yet
installed on this host.

To clear the blocker by the requested route, enter the LattePanda's **local
UEFI setup**, disable Secure Boot, and boot Linux again. This cannot be
changed over SSH. Do not disable it on a different machine. The DKMS build is
already installed, so normally no rebuild is needed after the firmware
change. Check with:

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
the `Dta`/`DtaNw` DKMS modules, and attempts to load `Dta`. It does **not**
start ASI playout or control external RF. Once the driver loads, verify card
access with `tsdektec` after installing a TSDuck build with DekTec support;
confirm the output channel and BNC mapping before a finite ASI test. Keep
the external modulator's RF disabled during bring-up.
