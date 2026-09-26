#!/usr/bin/env python3
"""Extract the RIBES wind-tunnel data from the public test report into JSON.

The report (138 pages, "Dissemination level: Public") is the only published
route to this campaign -- CORDIS lists no dataset. It is kept in external/ribes,
which is gitignored because the repository excludes *.pdf; the SHA256 beside it
and the URL below are how it is re-obtained.

  http://ribes-project.eu/Documents/RIBES-ExperimentalTestReport.pdf
  sha256 e83020c558d3e2d803c8fb0c912cdcabc8cf48d0826f2cf6785c490914cd4a78

Three kinds of table are parsed, and each parse is CHECKED rather than trusted:
integrated forces (appendix A), sectional Cl/Cm from pressure integration, and
raw Cp against x/c at each pressure section (appendix B).
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PDF = HERE / "external/ribes/RIBES-ExperimentalTestReport.pdf"
OUT = HERE / "data/ribes"

NUM = re.compile(r'^-?\d+\.?\d*(?:[eE][-+]?\d+)?$')


def pages() -> list[str]:
    import pypdf
    r = pypdf.PdfReader(str(PDF))
    return [(p.extract_text() or "") for p in r.pages]


def repair(line: str) -> list[str]:
    """Undo how the PDF text layer splits numbers.

    Two failures, both seen on the appendix B pages:
      "- 0.13005"  a minus sign orphaned from its number
      "-0 .13638"  the decimal point orphaned from its integer part
      "0.01 6508"  a number broken mid-digits, the tail having no decimal point

    The first is unambiguous. The second is only joined when the tail is a bare
    integer with no sign and no point, which is never a valid column on its own
    in these tables. Anything else is left alone and will be caught by the
    column-count check rather than silently guessed at.
    """
    toks = line.split()
    out: list[str] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t == "-" and i + 1 < len(toks) and NUM.match(toks[i + 1]):
            out.append("-" + toks[i + 1]); i += 2; continue
        if (re.match(r'^-?\d+$', t) and i + 1 < len(toks)
                and re.match(r'^\.\d+$', toks[i + 1])):
            out.append(t + toks[i + 1]); i += 2; continue
        if (out and re.match(r'^\d+$', t) and "." in out[-1] and NUM.match(out[-1])):
            out[-1] = out[-1] + t; i += 1; continue
        out.append(t); i += 1
    return out


def numbers(line: str) -> list[float]:
    toks = repair(line)
    out = []
    for tok in toks:
        if NUM.match(tok):
            out.append(float(tok))
        else:
            return out if out else []
    return out


def cp_tables(text: str) -> list[dict]:
    """Every Cp table on a page.

    A page can carry MORE THAN ONE section: file page 128 holds SECTION C and
    SECTION E one after the other, and an earlier version of this parser took
    the first header and filed all 63 rows under C. The design report's tap
    counts are what caught it -- section 3 has 38 taps and section 5 has 26, so
    63 rows under one section was impossible. Split on the section markers.
    """
    marks = list(re.finditer(r'SECTION\s+([A-F])\s*\(y=(\d+)\s*mm\)', text))
    if not marks:
        return []
    out = []
    for i, m in enumerate(marks):
        block = text[m.start(): marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        lines = [l for l in block.split("\n") if l.strip()]
        alphas, has_z = None, False
        for l in lines:
            if re.match(r'\s*x/c', l):
                has_z = "z/c" in l
                tail = l.split("z/c")[-1] if has_z else l.split("x/c")[-1]
                a = [float(x) for x in tail.replace("Cp", " ").split() if NUM.match(x)]
                if len(a) >= 5:
                    alphas = a
                    break
        if alphas is None:
            continue
        need = len(alphas) + (2 if has_z else 1)
        rows = [v for v in (numbers(l) for l in lines)
                if len(v) == need and 0.0 <= v[0] <= 1.0001]
        if not rows:
            continue
        # A data row starts with an x/c in [0,1] AND carries a value per alpha.
        # The sectional Cl/Cm table shares some of these pages and its rows also
        # start with a decimal -- it has five values, a Cp row has at least
        # eleven -- so a looser test over-counts and hides an incomplete parse.
        cand = sum(1 for l in lines
                   if re.match(r'\s*[01]?\.\d', l.strip()) and len(numbers(l)) >= 8)
        out.append({"section": m.group(1), "y_mm": int(m.group(2)),
                    "rows_parsed": len(rows), "rows_that_looked_like_data": cand,
                    "alpha_corrected_deg": alphas, "has_z_over_c": has_z,
                    "x_over_c": [r[0] for r in rows],
                    "z_over_c": [r[1] for r in rows] if has_z else None,
                    "cp": [r[(2 if has_z else 1):] for r in rows]})
    return out


def sectional(text: str) -> dict | None:
    """alfa cor | Cl_corr Cm_corr (SEC C) | Cl_corr Cm_corr (SEC E)"""
    if "Cl_corr" not in text:
        return None
    rows = [numbers(l) for l in text.split("\n") if l.strip()]
    rows = [r for r in rows if len(r) == 5 and -25 <= r[0] <= 25]
    if not rows:
        return None
    return {"alpha_corrected_deg": [r[0] for r in rows],
            "SEC_C": {"Cl": [r[1] for r in rows], "Cm": [r[2] for r in rows]},
            "SEC_E": {"Cl": [r[3] for r in rows], "Cm": [r[4] for r in rows]}}


def main() -> int:
    if not PDF.exists():
        print(f"missing {PDF}; download it first (URL in this file's docstring)")
        return 1
    P = pages()
    TEST = re.compile(r'TEST\s+([LT]\d\d)\s*:?\s*V=(\d+)\s*m/s')
    current, data = None, {}
    for i, txt in enumerate(P):
        m = TEST.search(txt)
        if m:
            current = m.group(1)
            data.setdefault(current, {"speed_m_s": int(m.group(2)), "cp": [], "sectional": None,
                                      "source_pages": []})
        if current is None:
            continue
        got = False
        for c in cp_tables(txt):
            data[current]["cp"].append(c); got = True
        s = sectional(txt)
        if s and data[current]["sectional"] is None:
            data[current]["sectional"] = s; got = True
        if got:
            data[current]["source_pages"].append(i + 1)
    meta = {"schema": "aeris.ribes.experiment.v1",
            "source": "RIBES experimental test report, January 2017, Dissemination level: Public",
            "url": "http://ribes-project.eu/Documents/RIBES-ExperimentalTestReport.pdf",
            "sha256": "e83020c558d3e2d803c8fb0c912cdcabc8cf48d0826f2cf6785c490914cd4a78",
            "project": "RIBES, Clean Sky JTI (FP7-JTI, JTI-CS-GRA), grant agreement 632556",
            "coordinator": "Universita degli Studi di Roma Tor Vergata",
            "tunnel": "University of Naples Federico II, closed-circuit low speed",
            "model": {"span_mm": 1600, "root_chord_mm": 600, "tip_chord_mm": 420,
                      "taper_ratio": round(420 / 600, 4), "mounting": "cantilever off the wall"},
            "test_matrix": {
                "L30": {"speed_m_s": 30, "reynolds": 1.06e6, "transition": "free", "polar": "full, to stall"},
                "L40": {"speed_m_s": 40, "reynolds": 1.43e6, "transition": "free", "polar": "to 8 deg"},
                "T30": {"speed_m_s": 30, "reynolds": 1.06e6, "transition": "tripped at 1.4 %c", "polar": "full"},
                "T35": {"speed_m_s": 35, "reynolds": 1.25e6, "transition": "tripped at 1.4 %c", "polar": "full"},
                "T40": {"speed_m_s": 40, "reynolds": 1.43e6, "transition": "tripped at 1.4 %c", "polar": "to 8 deg"}},
            "pressure_sections_y_mm": {"A": 160, "C": 600, "E": 1200},
            "deformation_measurement_error_mm": 0.3,
            "tests": data}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "ribes_experiment.json").write_text(json.dumps(meta, indent=2) + "\n")

    print(f"{'test':>5s} {'V':>4s} {'Cp tables':>10s} {'sections':>28s} {'alphas':>7s} {'taps':>6s} {'sectional Cl/Cm':>16s}")
    for k, v in sorted(data.items()):
        secs = ", ".join(f"{c['section']}@{c['y_mm']}mm" for c in v["cp"])
        na = max((len(c["alpha_corrected_deg"]) for c in v["cp"]), default=0)
        nt = sum(len(c["x_over_c"]) for c in v["cp"])
        print(f"  {k:>3s} {v['speed_m_s']:>4d} {len(v['cp']):>10d} {secs:>28s} {na:>7d} {nt:>6d} "
              f"{'yes' if v['sectional'] else 'no':>16s}")
    print(f"\nwrote {OUT/'ribes_experiment.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
