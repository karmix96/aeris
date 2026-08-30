# M-1 storage decision

Status: revised after capability audit; export/move and benchmark pending.

The Ubuntu ext4 filesystem already has an advertised virtual maximum near 1 TiB,
so increasing that maximum would not create physical host capacity. Its dynamic
VHD is currently 36.47 GiB on the C: SSD, where only 33.30 GiB remains free.
That cannot satisfy the campaign rule of `1.30 × remaining forecast + three
active-case footprints + 20 GiB` before case footprints are even measured.

The preferred separate-VHD implementation was rejected before mutation because
the Windows session is not elevated and neither the `New-VHD` nor `Mount-VHD`
cmdlet is available. Microsoft documents that attaching a separate disk/VHD to
WSL requires administrator access. No unsupported loop-device workaround is
authorized.

The supported implementation selected instead is:

- export Ubuntu as `D:\AERIS_WSL_BACKUPS\Ubuntu_pre_move_20260830.vhdx`;
- verify and record the export's SHA-256 before relocation;
- move the registered Ubuntu distribution with WSL 2.7's supported
  `wsl --manage Ubuntu --move D:\WSL\Ubuntu` operation;
- retain the verified export as the recovery copy;
- benchmark the moved Linux-native ext4 filesystem before accepting it as the
  active CGNS/restart root;
- keep heavy work blocked if throughput or persistence is inadequate.

D: has 570.84 GiB free but is an HDD. This decision obtains capacity and remains
Linux-native, but it does not presume adequate CFD I/O performance. A larger SSD
is the preferred hardware correction if the benchmark fails. The original
registered VHD must not be unregistered or manually deleted. The supported move
operation is allowed only after the independent export is verified.

The exact backup and destination paths were confirmed absent before use. Never
overwrite the recovery copy.
