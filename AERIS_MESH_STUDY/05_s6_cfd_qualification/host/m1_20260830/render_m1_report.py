#!/usr/bin/env python3
# ruff: noqa: E501
"""Render the governed M-1 host/resource report from retained JSON evidence."""

from __future__ import annotations

import hashlib
import html
import json
import os
from pathlib import Path

import matplotlib.pyplot as plt

plt.switch_backend("Agg")


ROOT = Path(__file__).resolve().parent
REPORTS = ROOT.parent.parent / "reports"
INPUTS = {
    "windows": ROOT / "host_inventory_windows.json",
    "linux": ROOT / "host_inventory_linux.json",
    "restart": ROOT / "post_restart_verification.json",
    "move": ROOT / "post_move_verification.json",
    "benchmark": ROOT / "storage_benchmark_001" / "benchmark.json",
    "gate": ROOT / "m1_gate.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def load() -> tuple[dict[str, dict], dict[str, str]]:
    data = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in INPUTS.items()}
    hashes = {str(path.relative_to(ROOT)): sha256(path) for path in INPUTS.values()}
    return data, hashes


def render_figure(data: dict[str, dict], hashes: dict[str, str]) -> None:
    gate = data["gate"]["resource_summary"]
    benchmark = data["benchmark"]
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.4), constrained_layout=True)

    memory_labels = ["Host RAM", "WSL limit", "WSL swap"]
    memory_values = [gate["host_physical_memory_gib"], gate["effective_wsl_memory_gib"], gate["effective_swap_gib"]]
    axes[0].bar(memory_labels, memory_values, color=["#4063D8", "#389826", "#CB3C33"])
    axes[0].set_ylabel("GiB")
    axes[0].set_title("Verified memory policy")
    axes[0].tick_params(axis="x", rotation=20)
    for index, value in enumerate(memory_values):
        axes[0].text(index, value + 0.25, f"{value:.2f}", ha="center", fontsize=9)

    disk_labels = ["C: SSD free", "D: HDD free"]
    disk_values = [gate["c_free_gib"], gate["d_free_gib"]]
    axes[1].bar(disk_labels, disk_values, color=["#9558B2", "#9558B2"])
    axes[1].set_ylabel("GiB")
    axes[1].set_title("Physical host free space")
    axes[1].tick_params(axis="x", rotation=20)
    for index, value in enumerate(disk_values):
        axes[1].text(index, value + 8, f"{value:.1f}", ha="center", fontsize=9)

    io_labels = ["Direct write", "Direct read"]
    io_values = [benchmark["write"]["throughput_mb_per_second"], benchmark["read"]["throughput_mb_per_second"]]
    axes[2].bar(io_labels, io_values, color=["#E6AB02", "#1B9E77"])
    axes[2].set_ylabel("MB/s")
    axes[2].set_title("D:-backed ext4 baseline")
    for index, value in enumerate(io_values):
        axes[2].text(index, value + 1.5, f"{value:.1f}", ha="center", fontsize=9)

    source_digest = hashlib.sha256("".join(sorted(hashes.values())).encode()).hexdigest()[:16]
    fig.suptitle(f"AERIS S6 M-1 host/resource evidence | source digest {source_digest}", fontsize=11)
    title = "AERIS S6 M-1 host/resource evidence"
    metadata = {
        "png": {"Title": title, "Description": source_digest},
        "svg": {"Title": title, "Description": source_digest},
        "pdf": {"Title": title, "Subject": source_digest},
    }
    for extension in ("png", "svg", "pdf"):
        target = REPORTS / f"m1_host_resource.{extension}"
        temporary = target.with_name(target.stem + ".tmp" + target.suffix)
        fig.savefig(temporary, dpi=180, metadata=metadata[extension])
        os.replace(temporary, target)
    plt.close(fig)


def render_text(data: dict[str, dict], hashes: dict[str, str]) -> None:
    gate = data["gate"]
    summary = gate["resource_summary"]
    rows = "\n".join(f"| `{html.escape(path)}` | `{digest}` |" for path, digest in hashes.items())
    markdown = f"""# AERIS S6 M-1 host/resource report

Status: **{gate['status']}**

The WSL policy and supported distro relocation passed. The repository remains
Linux-native and hash/identity-preserved. The D:-backed ext4 filesystem measures
{summary['direct_write_mb_per_second']:.1f} MB/s direct write and
{summary['direct_read_mb_per_second']:.1f} MB/s direct read: honest HDD-class
performance. M0/M1 code and tests are authorized; heavy mesh/CFD work remains
blocked until real case footprints complete the campaign storage forecast.

## Verified resources

| Quantity | Value |
|---|---:|
| Host physical RAM | {summary['host_physical_memory_gib']:.2f} GiB |
| Effective WSL RAM | {summary['effective_wsl_memory_gib']:.2f} GiB |
| WSL swap | {summary['effective_swap_gib']:.2f} GiB |
| Logical processors | {summary['logical_processors']} |
| C: SSD free | {summary['c_free_gib']:.2f} GiB |
| D: HDD free | {summary['d_free_gib']:.2f} GiB |

## Gate matrix

| Gate | Result |
|---|---|
{chr(10).join(f"| {name} | {'PASS' if result else 'OPEN'} |" for name, result in gate['gates'].items())}

## Storage interpretation

The absolute remaining-campaign upper bound is {gate['storage_capacity_envelope']['absolute_forecast_upper_bound_at_zero_case_footprint_gib']:.2f} GiB only when active-case footprint is zero. It is not a campaign forecast. The actual bound follows `{gate['storage_capacity_envelope']['rule']}` and decreases once the first written mesh and complete canary establish their footprints.

![M-1 host/resource figure](m1_host_resource.png)

## Source hashes

| Input | SHA-256 |
|---|---|
{rows}
"""
    atomic_text(REPORTS / "m1_host_resource_report.md", markdown)

    svg = (REPORTS / "m1_host_resource.svg").read_text(encoding="utf-8")
    body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>AERIS S6 M-1 report</title>
<style>body{{font:16px/1.45 system-ui;margin:2rem auto;max-width:1100px;padding:0 1rem}}table{{border-collapse:collapse}}td,th{{border:1px solid #bbb;padding:.4rem .6rem}}.status{{font-weight:700;color:#9a6700}}svg{{max-width:100%;height:auto}}</style></head>
<body><h1>AERIS S6 M-1 host/resource report</h1><p class="status">{html.escape(gate['status'])}</p>
<p>WSL and relocation gates pass. Heavy mesh/CFD remains blocked pending measured case footprints and a complete campaign storage forecast.</p>
<table><tr><th>Metric</th><th>Value</th></tr>
<tr><td>Host RAM</td><td>{summary['host_physical_memory_gib']:.2f} GiB</td></tr>
<tr><td>Effective WSL RAM / swap</td><td>{summary['effective_wsl_memory_gib']:.2f} / {summary['effective_swap_gib']:.2f} GiB</td></tr>
<tr><td>C: / D: free</td><td>{summary['c_free_gib']:.2f} / {summary['d_free_gib']:.2f} GiB</td></tr>
<tr><td>Direct write / read</td><td>{summary['direct_write_mb_per_second']:.1f} / {summary['direct_read_mb_per_second']:.1f} MB/s</td></tr></table>
{svg}<h2>Evidence hashes</h2><table><tr><th>Input</th><th>SHA-256</th></tr>{''.join(f'<tr><td>{html.escape(path)}</td><td><code>{digest}</code></td></tr>' for path, digest in hashes.items())}</table>
</body></html>"""
    atomic_text(REPORTS / "m1_host_resource_report.html", body)
    index = "<!doctype html><meta charset=\"utf-8\"><title>AERIS reports</title><h1>AERIS S6 qualification reports</h1><ul><li><a href=\"m1_host_resource_report.html\">M-1 host/resource report</a></li></ul>"
    atomic_text(REPORTS / "report_index.html", index)


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    data, hashes = load()
    render_figure(data, hashes)
    render_text(data, hashes)


if __name__ == "__main__":
    main()
