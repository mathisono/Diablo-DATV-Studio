# Credits and provenance

Diablo DATV Studio continues the Portsdown-derived NTSC and Trixie development
from [mathisono/portsdown4_NTSC](https://github.com/mathisono/portsdown4_NTSC),
[Marx1/portsdown4_NTSC](https://github.com/Marx1/portsdown4_NTSC), and
[BATC Portsdown 4](https://github.com/BritishAmateurTelevisionClub/portsdown4).

Thanks to the BATC contributors, Trevor Raty KG6MDW, Evariste Courjaud F5OEO,
Charles G4GUO, and all authors credited in the inherited source history and
individual files. Preserve those notices when modifying or redistributing code.
The top-level [GPLv3 license](LICENSE) is unchanged; bundled components retain
their own license files. Do not assume the top-level license replaces them.

## External dependencies (fetched, not relicensed or vendored)

| Component | Source / pinned revision | Purpose |
| --- | --- | --- |
| libubox | OpenWrt, `a396f38a8568a1d670c240465cd8d24fdfdf6463` | uloop event loop |
| ucode | jow-/ucode, `a2c42eac6369a0bba0315007c7dc7b7130275340` | Persistent web/control runtime |
| libdvbmod | F5OEO/libdvbmod, `eff68b37047196e5bc732b08fa7f73c2bf94107e` | Experimental Express DVB-S2 software modulation |
| FFmpeg | Distribution package | Capture, encoding, TS and preview |
| TSDuck / DTAPI | Official packages / vendor SDK | ASI processing and DekTec access |
| DekTec Linux SDK | Official SDK 2026.09.0 (separate installer) | Dta/DtaNw DKMS |

Check each upstream license, including proprietary SDK terms, before distributing
binary bundles. No SDK archive, credentials, private camera configuration, or
operator's historical credential-bearing notes are included in this migration.
