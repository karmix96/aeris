# S6 CFD desktop-session checkpoint

Updated: 2026-08-30T13:05:45+03:00

## Resume

From a terminal:

```bash
cd /home/mike_kara/aeris
codex resume --last
```

If the prior conversation cannot be selected, start a new Codex conversation in
`/home/mike_kara/aeris` and instruct it to read, in order:

1. `AERIS_MESH_STUDY/AERIS_S6_AUTOMATED_CFD_MASTER_EXECUTION_GUIDE.md`
2. this file;
3. `AERIS_MESH_STUDY/PROJECT_HANDOFF/LIVE_STATE.md`;
4. `AERIS_MESH_STUDY/PROJECT_HANDOFF/CURRENT_STATUS.md`;
5. `AERIS_MESH_STUDY/PROJECT_HANDOFF/DECISIONS.md`;
6. `AERIS_MESH_STUDY/PROJECT_HANDOFF/RISKS_AND_OPEN_GATES.md`.

Then say: `Continue M-1 from the durable checkpoint; do not launch CFD.`

## Current work order

The master guide is the controlling work order. M-1 is active. No CFD or heavy
mesh process has been launched.

Completed read-only findings:

- Physical RAM: 17,033,293,824 bytes (15.86 GiB).
- CPU: Intel Core i5-10400, 6 physical cores, 12 logical processors.
- WSL: version 2.7.11.0; Ubuntu 24.04.3 LTS; WSL2.
- Current WSL memory: 8,059,528 KiB (7.69 GiB).
- Current WSL swap: 2,097,152 KiB (2 GiB).
- Linux root: ext4, 1 TiB advertised, about 944 GiB available.
- Ubuntu VHD physical file: 39,155,924,992 bytes (36.47 GiB), on C:.
- C: SSD free: 35,761,373,184 bytes (33.30 GiB).
- D: HDD free: 612,930,969,600 bytes (570.84 GiB).
- Repository: `/home/mike_kara/aeris`, Linux-native, commit
  `44de99814b02e2f2bf0c87256b081acedf9daa38` on `main`.
- Claude Code is installed at `/home/mike_kara/.local/bin/claude`, version
  2.1.241.

Approved engineering decision:

- Write `%USERPROFILE%\\.wslconfig` with `memory=13GB`, `swap=8GB`, and gradual
  automatic memory reclaim; omit `processors` so all 12 logical CPUs remain
  visible.
- Keep Ubuntu and the repository on C: SSD.
- Do not resize the existing Ubuntu VHD: its virtual maximum is already 1 TiB.
- A separate mounted VHD was rejected because this Windows session is not
  elevated and the required VHD cmdlets are unavailable. Use the supported WSL
  move route instead: export Ubuntu to
  `D:\AERIS_WSL_BACKUPS\Ubuntu_pre_move_20260830.vhdx`, verify its SHA-256, and
  only then run `wsl --manage Ubuntu --move D:\WSL\Ubuntu`.
- Never unregister or manually delete the original distro/VHD. The D: device is
  an HDD, so the relocated ext4 filesystem must be benchmarked. A larger SSD is
  preferred if the benchmark is inadequate.

## Next exact actions

1. Commit/push the governed M-1 files without staging pre-existing user changes
   or the ignored 1 GiB benchmark payload.
2. Continue M0/M1 implementation and tests; do not launch mesh/CFD work.
3. Measure real written-mesh and complete-canary footprints before completing
   the campaign storage forecast or lifting the heavy-work block.

The Windows file `C:\Users\mike\.wslconfig` was atomically created and verified
before shutdown. It is 76 bytes with SHA-256
`e6e2b6bc046d284660cd103dba2d032a64597faec26116d8fd261230030d93f9`.
The WSL VM restarted successfully at 2026-08-30T11:46:04+03:00. Effective
memory is 13,279,880 KiB (12.66 GiB), swap is 8 GiB and unused, and all 12
logical processors are visible. The RAM/swap portion of M-1 is verified.

Export attempt 003 completed with a 39,155,924,992-byte recovery VHD and SHA-256
`a0ec879330d8c65a08eb34f20aa1db932b89943804340428a428b9897c30e9d1`.
The governed move script is copied to
`D:\AERIS_WSL_BACKUPS\RUN_MOVE_ATTEMPT01.ps1`; its PowerShell parse has zero
errors and its SHA-256 is
`cf4f50817a1b4ca149aa951b262a24bc4891acfed19f295f5e478ee86e5c60f3`.
It independently re-hashes the backup before executing the supported move. It
never unregisters or deletes the distro.

Post-move verification passed: Ubuntu is registered at `D:\WSL\Ubuntu`, ext4
is healthy/writable, repository commit and dirty user state are unchanged, and
the WSL resource policy remains effective. The governed 1 GiB direct-I/O
benchmark measured 60.5 MB/s write and 73.0 MB/s read. M-1 status is
`CONDITIONAL_GO_M0_M1_ONLY`; every heavy mesh/CFD command remains blocked.

## Existing user work to preserve

These changes predated this session and are unrelated. Do not edit, stage,
discard, reset, clean, or overwrite them:

```text
 M AERIS_MESH_STUDY/04_strategy_studies/S7_unstructured_gmsh_su2/campaign.py
?? configs/aero/section_study/stage1_reference_subset.json
?? configs/aero/section_study/stage1_summary_subset.txt
```

The locked holdout `round_c_lhs10_seed42` remains forbidden before M8.
