# Repository consolidation record

## Destination

- Repository: https://github.com/mathisono/Diablo-DATV-Studio
- Integration/default branch: **Trixie** (verified on GitHub; no migration to upstream `master`).
- Source: `mathisono/portsdown4_NTSC`, `headless-ucode-control` at `a9106a9`.
- All preceding Git history and license notices are preserved. The old repository
  and its branches are not deleted or force-pushed.

## Source coverage

Ancestry was checked after fetching the source remotes. `headless-ucode-control`
already contains every commit from these branches; no content needed to be
cherry-picked twice or reconciled through a competing merge:

| Source branch | Tip used | Commits unique to that branch versus headless |
| --- | --- | --- |
| `arm64-transmitter` | `f0047f7` | 0 |
| `Trixie` | `7f1d1c3` | 0 |
| `master` | `a9aad31` | 0 |
| `Bookworm` | `688c5d1` | 0 |
| `work/trixie-ntsc-foundation` | `96f0708` | 0 |

The copied tree includes OBS/SRT setup tools, ATEM-like sender, preview-return
scripts, TS metadata helpers, legacy capture/interlock paths, native transmitter
sources, DekTec installers, GUI assets and all existing tests. External libraries
needed for the new runtime and Express S2 are pinned in build scripts; see
[CREDITS.md](../CREDITS.md). Private notes and operator configurations are not
part of the source import.

## Changes made for Diablo

- Diablo identity in the actual web UI and a new project README.
- User-local headless installer and paired-process launcher; no autostart or RF.
- Explicit external Express S2 dependency builder, including the FFTW headers
  required by the inherited USB driver's shared header.
- Modern setup, update/rollback and developer instructions; source-lineage record.
- Reviewed backend notes distinguished from the current product/support matrix.
- Legacy Buster installer/updater entrypoints disabled to prevent a rollback to
  old Portsdown `master` downloads.
- Six regenerated browser screenshots, a gallery, capture tool and list of
  additional real-device images needed.
- Hardware-free GitHub Actions checks targeting **Trixie**.
- Completed migration tasks and remaining work separated in
  [KNOWN_ISSUES.md](KNOWN_ISSUES.md), with concrete acceptance criteria.

Compatibility identifiers such as `PORTSDOWN_DIR`, `portsdown_config.txt`, the
control header and old service-template names intentionally remain. Functional
media waiting cards and upstream test-card assets are retained; the old
Portsdown product photo is no longer the project's landing image.

## Verification on 24 November 2026

| Check | Result / boundary |
| --- | --- |
| Source ancestry and clean input worktree | All requested source code already included; no uncommitted source changes imported |
| New installer on isolated LattePanda prefix | Pinned libubox/ucode built; fs/socket/uloop loaded; native C utilities rebuilt |
| Installer rerun | Config and environment SHA-256 unchanged after adding a preservation marker |
| Foreground launcher on LattePanda | Startup/API save/duplicate rejection/unarmed TX/complete shutdown smoke test passed |
| Fresh clone from the published Diablo repo | `a92fb3b` on LattePanda, separate prefix; full bootstrap and real launcher smoke test passed; checkout clean |
| Full software suite on development host | 44 tests ran: 43 passed; one Pi-4-only live revision test skipped |
| Native AArch64 C build on TANK | Both C utilities built; all 7 supervisor tests passed in an isolated directory |
| TANK headless install | Not claimed: host lacks CMake/JSON-C build prerequisites; no system packages changed |
| Express S2 build / rate / offline modulation | Pinned dependency built; 1 Msym/s QPSK FEC 1/2 capacity 988,858 b/s; 1,000 null TS packets produced 46 offline frames |
| Screenshot capture | Six actual Chromium captures; title, two camera cards, five SRT cards and no horizontal overflow checked; visually reviewed |
| Physical ASI / RF | Not run; no acceptance inferred from software or screenshots |

Build and test artifacts are kept outside the source checkout. The new bootstrap
was exercised with preinstalled distribution packages (`--skip-system-packages`),
not by reinstalling the OS. Fresh Pi OS imaging, physical capture and hardware
output are tracked work, not prerequisites to publishing this consolidation.

## Follow-up ownership

[KNOWN_ISSUES.md](KNOWN_ISSUES.md) is the authoritative open-work register.
Its seven items are also tracked as [GitHub issues #1–#7](https://github.com/mathisono/Diablo-DATV-Studio/issues).
Migration resolves packaging/docs/screenshots; it does not claim completion of
unavailable hardware tests or implementation of full-quality mixing, live ASI,
headless RF launchers, all receiver functions, or DVB-S2X. Old upstream PRs are
not automatically merged or closed by moving this repository.
