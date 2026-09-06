#!/usr/bin/env python
"""ONERA M6: validate the SOLVER CONFIGURATION against published experiment.

    .venv/bin/python .../tmr_onera_m6.py fetch      # archive the published data
    .venv/bin/python .../tmr_onera_m6.py grids      # can a grid family be had?
    .venv/bin/python .../tmr_onera_m6.py compare --surface <run>/..._surf.cgns

PLAN_desktop_campaign.md 5.  S8 has no experimental validation at all, and
cross-method agreement with AVL is not validation: two codes agreeing about a
wing neither has ever been checked against is a consistency result.

What this can and cannot establish, stated once and then repeated in the output
--------------------------------------------------------------------------------
It validates the ADflow CONFIGURATION this project uses -- RANS-SA, liftIndex,
ANK->NK, NKSubspaceSize 20, NKPCILUFill 1, and the convergence gate -- against a
case with published experimental surface pressures and published reference
solutions.

It does NOT validate the S8 mesher.  It cannot: S8's mesher builds AERIS BWB
lofts and nothing else, and no public experimental case is an AERIS BWB.  Both
halves of that belong in any report that cites this.

The regime gap is large and is not a detail
--------------------------------------------
    ONERA M6   M 0.84,  transonic, with a lambda shock on the upper surface
    AERIS      M 0.0837, essentially incompressible

A transonic validation says little about shock-free low-speed accuracy beyond
"the solver, the turbulence model and the gate work as published".  PLAN 5 asks
for a low-speed TMR case as a better Reynolds and compressibility match if one
is available, and for the discrepancy to be stated explicitly if only the
transonic case is run.  It is stated here.

The operating point, and a correction to the plan
--------------------------------------------------
PLAN 5 gives "M = 0.8395, alpha = 3.06 deg, Re = 11.72e6 based on mean chord".
The TMR case definition is not quite that, and mixing them is how a validation
comes to compare two different flows:

    TMR Case 2308:  Minf = 0.84,  AoA = 3.06 deg,  Tinf = 540 R,
                    Rec_root = 14.6e6  based on ROOT chord, sharp trailing edge

Re = 11.72e6 is the ORIGINAL EXPERIMENT's Reynolds number, based on the blunt
model's mean aerodynamic chord of 646.07 mm.  TMR is explicit that the CFD
exercise should use Rec_root = 14.6e6 on the sharp-trailing-edge geometry, which
"approximately corresponds with the original experiment".  Both are recorded
below; the run uses the TMR exercise value, because the reference solutions this
would be compared against used it.

One more correction: the sixth pressure station is at eta = 0.96, not the 0.95
that the original AGARD report and many secondary sources give.  TMR says recent
measurements on the model confirmed 0.96.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ARCHIVE = REPO / "AERIS_MESH_STUDY/05_s6_cfd_qualification/external/onera_m6"
REPORTS = REPO / "AERIS_MESH_STUDY/05_s6_cfd_qualification/reports"

#: TMR Case 2308.  See the module docstring for why this is not what PLAN 5 says.
CASE = {
    "name": "TMR Case 2308",
    "mach": 0.84,
    "alpha_deg": 3.06,
    "reynolds": 14.6e6,
    "reynolds_length": "root chord, sharp trailing edge, normalised to 1.0",
    "temperature_R": 540.0,
    "temperature_K": 540.0 * 5.0 / 9.0,
    "plan_stated_mach": 0.8395,
    "plan_stated_reynolds": 11.72e6,
    "plan_reynolds_note": (
        "11.72e6 is the ORIGINAL EXPERIMENT's Re, on the blunt model's mean "
        "aerodynamic chord of 646.07 mm. The TMR CFD exercise specifies "
        "Rec_root = 14.6e6 on the sharp-TE geometry. Do not mix them."),
    "geometry": "sharp trailing edge, per AIAA 2016-1357; root chord normalised to 1",
    "reference": ("Schmitt, V. and Charpin, F., 'Pressure Distributions on the "
                  "ONERA-M6-Wing at Transonic Mach Numbers', AGARD AR-138, 1979"),
}

#: eta = y/b of the seven pressure stations.  The sixth is 0.96, NOT the 0.95
#: that AGARD AR-138 and most secondary sources print.
STATIONS = (0.20, 0.44, 0.65, 0.80, 0.90, 0.96, 0.99)

WIND = "https://www.grc.nasa.gov/WWW/wind/valid/m6wing"
TMR_RAW = "https://raw.githubusercontent.com/TMBWG/turbmodels/main"

#: what to archive.  The experimental data is the part that gets harder to
#: obtain with time, so it is fetched into the repository rather than
#: re-downloaded per run -- and into 05_s6_cfd_qualification, because
#: artifacts/ is gitignored and gets wiped.
SOURCES = {
    **{f"cp{i}{s}.ex": f"{WIND}/cp{i}{s}.ex"
       for i in range(1, 8) for s in ("u", "l")},
    "airfoil.txt": f"{WIND}/airfoil.txt",
    "case_2308.dat": f"{TMR_RAW}/Onerawingnumerics_val/case_2308.dat",
    "case_2565.dat": f"{TMR_RAW}/Onerawingnumerics_val/case_2565.dat",
    "profile_ONERA-D.dat": f"{TMR_RAW}/Onerawingnumerics_val/profile_ONERA-D.dat",
    "profile_M6_streamwise_alongy=0.dat":
        f"{TMR_RAW}/Onerawingnumerics_val/profile_M6_streamwise_alongy=0.dat",
    "AileM6_with_sharp_TE.igs":
        f"{TMR_RAW}/Onerawingnumerics_grids/AileM6_with_sharp_TE.igs",
    "AileM6_with_sharp_TE.stp":
        f"{TMR_RAW}/Onerawingnumerics_grids/AileM6_with_sharp_TE.stp",
    # Despite living under a name that reads like a grid, this is the EXPERIMENT:
    # "M6 WING - SURFACE PRESSURE DISTRIBUTIONS - TEST 2308", the Schmitt and
    # Charpin cp at all seven sections in one Tecplot POINT file. Its header also
    # settles where PLAN 5's operating point came from -- M 0.8395, alpha 3.06,
    # Re 0.117e8 are printed in it, so the plan quoted the EXPERIMENT's conditions
    # and not the TMR CFD exercise's.
    "ONERAb114.tec": f"{WIND}/ONERAb114.tec",
}

#: The grid family PLAN 5 step 1 asks for.  Every published route, so that
#: "it is not available" is a checked statement and not an assumption.
GRID_SOURCES = {
    "TMR generator archive (tar.gz), linked from onerawingnumerics_grids.html":
        f"{TMR_RAW}/Onerawingnumerics_grids/wing_release_072319.tar.gz",
    "TMR generator archive (zip), same page":
        "https://tmbwg.github.io/turbmodels/Onerawingnumerics_grids/wing_release_072319.zip",
    "TMR generator archive via github.com/raw":
        "https://github.com/TMBWG/turbmodels/raw/main/Onerawingnumerics_grids/wing_release_072319.tar.gz",
    "TMR generator archive via git-lfs media host":
        "https://media.githubusercontent.com/media/TMBWG/turbmodels/main/Onerawingnumerics_grids/wing_release_072319.tar.gz",
    # THE GRID. The page links m6wing.cgd, which does not exist; the server
    # answers 300 Multiple Choices and NAMES the file that does exist in the
    # response BODY. A probe that reads only the status code concludes there is
    # no grid, which is what this one did and it was wrong.
    "NASA WIND archive PLOT3D grid (m6wing.x.fmt) -- THE GRID":
        f"{WIND}/m6wing01/m6wing.x.fmt",
    "NASA WIND archive structured grid (m6wing.cgd, the page's own link)":
        f"{WIND}/m6wing01/m6wing.cgd",
    "NASA WIND archive case bundle (m6wing02.tar.Z)":
        f"{WIND}/m6wing02/m6wing02.tar.Z",
}

#: Routes that resolve but do NOT contain a grid.  Recorded so the next person
#: does not spend the same hour rediscovering it.  A probe that only asks "did
#: the byte stream arrive" will call both of these a success.
NOT_ACTUALLY_GRIDS = {
    f"{WIND}/ONERAb114.tec": (
        "downloads fine, and is the EXPERIMENT, not a grid: 'M6 WING - SURFACE "
        "PRESSURE DISTRIBUTIONS - TEST 2308', cp at the seven sections."),
    f"{WIND}/m6wing02/m6wing02.tar.Z": (
        "downloads fine, and holds a WIND SOLUTION (nsl2.gen) plus post-processing "
        "scripts. The grid it refers to lives in m6wing01 and is not in the bundle."),
}


def get(url: str, timeout: int = 120) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "aeris-s8/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def probe(url: str, timeout: int = 60) -> dict:
    """HEAD, falling back to a ranged GET, because some hosts refuse HEAD."""
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(url, method=method,
                                         headers={"User-Agent": "aeris-s8/1.0",
                                                  "Range": "bytes=0-1023"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                length = response.headers.get("Content-Length")
                ctype = response.headers.get("Content-Type", "")
                body = response.read(1024) if method == "GET" else b""
                # a 200 that hands back an HTML error page is not a file
                looks_html = b"<html" in body[:512].lower() or "text/html" in ctype
                return {"status": response.status, "content_length": length,
                        "content_type": ctype, "available": not looks_html,
                        "note": "served an HTML page, not the archive" if looks_html else ""}
        except urllib.error.HTTPError as exc:
            if method == "GET":
                return {"status": exc.code, "available": False, "note": exc.reason}
        except Exception as exc:  # noqa: BLE001
            if method == "GET":
                return {"status": None, "available": False,
                        "note": f"{type(exc).__name__}: {exc}"}
    return {"status": None, "available": False, "note": "unreachable"}


def cmd_fetch(args) -> int:
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    manifest = {"case": CASE, "stations_eta": list(STATIONS), "files": {}}
    print(f"archiving published ONERA M6 data into\n  {ARCHIVE}\n")
    for name, url in SOURCES.items():
        target = ARCHIVE / name
        if target.exists() and not args.refresh:
            data = target.read_bytes()
            status = "cached"
        else:
            try:
                data = get(url)
                target.write_bytes(data)
                status = "fetched"
            except Exception as exc:  # noqa: BLE001
                print(f"  {name:<40} FAILED  {type(exc).__name__}: {exc}")
                manifest["files"][name] = {"url": url, "error": str(exc)}
                continue
        manifest["files"][name] = {
            "url": url, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "status": status}
        print(f"  {name:<40} {status:>8}  {len(data):>9,} bytes")

    manifest["what_this_is"] = (
        "Published ONERA M6 data: experimental surface pressures at the seven "
        "span stations (NASA WIND validation archive, upper and lower surface "
        "per station), the TMR case files, the section profiles, and the "
        "sharp-trailing-edge CAD. Archived into the repository because "
        "artifacts/ is gitignored and wiped, and because experimental data "
        "gets harder to obtain with time, not easier.")
    manifest["what_is_missing"] = (
        "The GRID FAMILY. Run the `grids` subcommand: TMR publishes a grid "
        "GENERATOR rather than grids, and its archive is a dead link.")
    (ARCHIVE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"\nwrote {ARCHIVE / 'MANIFEST.json'}")
    return 0


def cmd_grids(args) -> int:
    """PLAN 5 step 1: 'Download the TMR ONERA M6 structured grid family.'"""
    print("PLAN 5 step 1 asks for the TMR ONERA M6 structured grid family.")
    print("Probing every published route:\n")
    results = {}
    for label, url in GRID_SOURCES.items():
        info = probe(url)
        if info.get("available") and url in NOT_ACTUALLY_GRIDS:
            info["available"] = False
            info["note"] = NOT_ACTUALLY_GRIDS[url]
        results[label] = {"url": url, **info}
        mark = "AVAILABLE" if info.get("available") else "NOT A GRID" \
            if url in NOT_ACTUALLY_GRIDS else "NOT AVAILABLE"
        print(f"  {mark:<14} {label}")
        print(f"                 {url}")
        print(f"                 status {info.get('status')}"
              f"  {info.get('note', '')}\n")

    available = [k for k, v in results.items() if v.get("available")]
    report = {"plan_section": "5", "step": "1 -- obtain the grid family",
              "probed": results, "available": available}
    if available:
        report["verdict"] = "a grid source is reachable; PLAN 5 can proceed"
        report["resolution"] = (
            "RESOLVED 2026-09-06. m6wing01/m6wing.x.fmt is a PLOT3D grid: 4 blocks, "
            "316,932 points, about 290k cells, with its boundary conditions "
            "documented in m6wing01/m6wing.gman.html. onera_m6.py converts it to "
            "CGNS, coarsens a family from it, solves and compares against the seven "
            "measured stations. An earlier verdict here said BLOCKED because the "
            "m6wing.cgd link 404s and the 300 response was read as a failure "
            "instead of as the directory listing it is.")
        print(f"A source is reachable: {available[0]}")
    else:
        report["verdict"] = "BLOCKED"
        report["finding"] = (
            "TMR does not publish ONERA M6 grid FILES. Its grids page publishes a "
            "Fortran grid GENERATOR plus a coarsening program, distributed as "
            "wing_release_072319.tar.gz -- and that archive is a dead link on every "
            "route: it 404s from the GitHub Pages host, from github.com/raw and from "
            "the LFS media host, and it does not appear in the GitHub API listing of "
            "the directory that is supposed to contain it. The directory holds only "
            "the CAD, the namelist inputs and images. The NASA WIND archive's grid "
            "(m6wing01/m6wing.cgd) answers 300/500 and never delivers bytes; its "
            "m6wing02 bundle downloads but contains a WIND solution and scripts, not "
            "a grid. Two other WIND URLs DO download and are not grids at all -- "
            "ONERAb114.tec is the experimental cp, and the bundle is a solution -- so "
            "a probe that only checks whether bytes arrived reports success here and "
            "is wrong.")
        report["consequence"] = (
            "PLAN 5 steps 1-4 cannot be executed as written. The published "
            "EXPERIMENT is available and is archived by the `fetch` subcommand; "
            "what is missing is the published GRID. Note that step 4 -- 'Run gci.py "
            "on the three levels' -- needs a FAMILY, so even a single recovered grid "
            "would only unblock steps 2 and 3.")
        report["not_actually_grids"] = NOT_ACTUALLY_GRIDS
        report["options"] = [
            "Mesh the published sharp-TE CAD with a mesher available here. This "
            "still validates the solver configuration against experiment, which is "
            "the point of PLAN 5, but the mesh becomes a variable that PLAN 5 "
            "deliberately wanted held fixed by using published grids. Say which was "
            "done.",
            "Obtain wing_release_072319.tar.gz from the TMR maintainers or a mirror, "
            "build the Fortran generator, and produce the family as intended.",
            "Use a different published case that ships grids. PLAN 5 already notes "
            "that a LOW-SPEED case would be a better match for this project's M "
            "0.0837 and Reynolds regime than transonic M6, so a substitution here is "
            "not purely a fallback -- it may be an improvement.",
        ]
        print("BLOCKED. No published grid family is reachable.\n")
        print(f"  {report['finding']}\n")
        print("  Options:")
        for option in report["options"]:
            print(f"    - {option}")

    REPORTS.mkdir(parents=True, exist_ok=True)
    out = args.out or REPORTS / "s8_tmr_onera_m6_grid_availability.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nwrote {out}")
    return 0 if available else 2


def read_wind_cp(path: Path) -> list[tuple[float, float]]:
    """NASA WIND .ex files: x/c, cp, and two error columns."""
    points = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            try:
                points.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
    return points


def cmd_compare(args) -> int:
    """PLAN 5 step 3: computed cp against the experimental stations."""
    if not ARCHIVE.exists():
        raise SystemExit(f"{ARCHIVE} does not exist. Run the `fetch` subcommand first.")
    print(f"experimental stations archived in {ARCHIVE}\n")
    print(f"{'station':>8}{'eta':>7}{'upper pts':>11}{'lower pts':>11}"
          f"{'cp min (exp)':>14}")
    summary = []
    for i, eta in enumerate(STATIONS, start=1):
        upper = ARCHIVE / f"cp{i}u.ex"
        lower = ARCHIVE / f"cp{i}l.ex"
        if not upper.exists():
            print(f"{i:>8}{eta:>7.2f}   missing")
            continue
        u, l = read_wind_cp(upper), read_wind_cp(lower)
        cp_min = min(p[1] for p in u) if u else float("nan")
        print(f"{i:>8}{eta:>7.2f}{len(u):>11}{len(l):>11}{cp_min:>14.3f}")
        summary.append({"station": i, "eta": eta, "n_upper": len(u),
                        "n_lower": len(l), "experimental_cp_min_upper": cp_min})

    if not args.surface:
        print("\nNo --surface given, so this listed the experimental data only.")
        print("PLAN 5 steps 2-4 need a solution on a published grid; run the "
              "`grids` subcommand for why that is currently blocked.")
    else:
        raise SystemExit(
            "comparing a computed solution needs a run on an ONERA M6 grid, and no "
            "grid family is available -- see the `grids` subcommand. This path is "
            "left unimplemented deliberately rather than written against a file "
            "format nobody has been able to produce yet.")

    out = args.out or REPORTS / "s8_tmr_onera_m6_experiment.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        {"case": CASE, "stations": summary,
         "scope": ("This is the EXPERIMENT, catalogued. It is not a validation "
                   "until a solution is run against it.")}, indent=2) + "\n")
    print(f"\nwrote {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch", help="archive the published experimental data")
    f.add_argument("--refresh", action="store_true")
    f.set_defaults(func=cmd_fetch)
    g = sub.add_parser("grids", help="probe every published grid route")
    g.add_argument("--out", type=Path, default=None)
    g.set_defaults(func=cmd_grids)
    c = sub.add_parser("compare", help="computed cp against the experiment")
    c.add_argument("--surface", type=Path, default=None)
    c.add_argument("--out", type=Path, default=None)
    c.set_defaults(func=cmd_compare)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
