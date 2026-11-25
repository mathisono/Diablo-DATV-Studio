# Documentation index

## Current Diablo documentation

- [Automated first start: wizard, source setup and verification](FIRST_START.md)
- [Installation, startup, update and rollback](INSTALL.md)
- [Peer control, IPTS/SRT-only SLAVE and two-host acceptance](peer-control.md)
- [Screenshot gallery and captures still needed](SCREENSHOTS.md)
- [Development, source layout and tests](DEVELOPMENT.md)
- [Capability matrix and open issues](KNOWN_ISSUES.md)
- [Repository migration and validation record](MIGRATION.md)
- [Headless architecture and API/source details](headless-ucode-control.md)
- [LattePanda / DTA-2145 installation and QSV findings](lattepanda-dta-driver.md)
- [Credits and external dependency provenance](../CREDITS.md)

## Retained Portsdown backend notes

These describe inherited paths or historical tests, **not** a complete Diablo
headless RF/receiver release. Consult the current status ledger before using
hardware. Old commit hashes and test-host paths are evidence, not install targets.

- [64-bit transmitter / Express S2](arm64-transmitter.md)
- [NTSC / 32-bit migration](ntsc-trixie-migration.md)
- [32-bit isolated camera/source test](trixie-32bit-first-run.md)
- [Capture/output porting scope](trixie-mode-porting-scope.md)
- [SRT ingest](srt-express-ingest.md)
- [SRT TX interlock](srt-interlocked-tx.md)
- [IPTS/SRT links and input gate](ipts-srt-link.md)
- [OBS/SRT ATEM-like test sender and confidence return](mse88-obs-srt-to-tank.md)
- [Historical Buster/Lime Mini results](buster-limemini-test-results.md)
- [Archived pre-migration README](legacy-portsdown-readme.md)

Legacy receiver/utility source docs remain alongside their code. They are not
new installation instructions. The old Buster install/update entrypoints are
blocked in Diablo to prevent accidental replacement by the Portsdown distribution.
