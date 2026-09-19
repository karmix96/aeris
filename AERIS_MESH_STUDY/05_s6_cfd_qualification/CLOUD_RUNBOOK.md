# Running the batch: preflight and pilot, step by step

Written 2026-09-19. Assumes you have a rented machine and a terminal on it, and nothing else.
Read `S8_CLOUD_BATCH_PLAN.md` for *why*; this is *how*.

---

## 0. Before you rent anything: one decision

**Re-run `gci_C` and `gci_M` on the cloud as well, for wing 83 only.** They already exist here,
solved on 17 September with **ADflow 2.13.1**. If the rented machine's ADflow is a different
build, the four-level analysis will **refuse to combine them** — correctly, because a
grid-convergence study whose levels came from different solvers is not one.

Re-running them removes the question entirely:

| | |
|---|---|
| Cost | **19.3 core-hours** — 5.3 for `gci_C`, 14.0 for `gci_M`, four angles each |
| As a share of the batch | **4.4 %** |
| What it buys | all four levels from one solver on one machine, so the study is computable whatever version the image ships |

At $0.10–0.15 per core-hour that is about **$2–3**. I would spend it. The alternative is
discovering after the batch that the levels cannot be combined, which costs the whole batch.

---

## 1. What to rent

The pilot's binding constraint is **one `gci_FF` case at 38.4 GiB**.

| | pilot | full batch |
|---|---|---|
| Physical cores | **≥ 8** | 16–32 |
| RAM | **≥ 48 GiB** | 128–256 GiB |
| Disk | 50 GiB | 100 GiB |
| Shape | memory-heavy: ≥ 9.6 GiB per physical core | same |

**Compute-optimised instances at 4 GiB per physical core will not hold `gci_FF`.** Use a
memory-optimised type. Pin ranks to physical cores; do not let two ranks share one core's
hyperthreads.

---

## 2. Getting the solver there

This is the only hard part. ADflow is not pip-installable.

**Use the MDO Lab's prebuilt image.** It ships ADflow, pyGeo, cgnsutilities and a matching
OpenMPI, which is exactly the stack `env_s8.py` looks for:

```bash
docker pull mdolab/public:u22-gcc-ompi-stable
```

Check the current tag at [hub.docker.com/r/mdolab/public](https://hub.docker.com/r/mdolab/public)
and the official notes at
[MACH-Aero Docker instructions](https://mdolab-mach-aero.readthedocs-hosted.com/en/latest/installInstructions/dockerInstructions.html) —
tags move, and this document will go stale before they do.

```bash
git clone <your repo url> aeris          # about 154 MB
docker run -it --rm \
  -v "$PWD/aeris:/aeris" \
  --shm-size=2g \
  mdolab/public:u22-gcc-ompi-stable bash
```

Inside the container, the project's own venv still has to exist — it holds the mesher, the gates
and the analysis, none of which are in the image:

```bash
cd /aeris
python3 -m venv .venv
.venv/bin/pip install numpy scipy pygeo pyspline aerosandbox neuralfoil pyyaml markdown-it-py
```

Then tell `env_s8.py` where the three things are. It resolves them automatically, but on an
unfamiliar machine **say it explicitly** — a wrong `mpirun` gives you six one-rank runs that each
think they are rank 0 and overwrite each other while reporting success:

```bash
export AERIS_MACH_PYTHON=$(which python3)      # the image's python, the one that imports adflow
export AERIS_VENV_PYTHON=/aeris/.venv/bin/python
export AERIS_MPIRUN=$(which mpirun)            # must be the one adflow's mpi4py was built against
```

**Verify before going further:**

```bash
$AERIS_MACH_PYTHON -c "import adflow; print('ADflow', adflow.__version__)"
$AERIS_MACH_PYTHON -c "import cgnsutilities; print('cgnsutilities ok')"
$AERIS_VENV_PYTHON  -c "import pygeo, numpy; print('venv ok')"
$AERIS_MPIRUN --version | head -1
```

**Write down the ADflow version it prints.** If it is not 2.13.1, §0's decision is no longer
optional — re-run `gci_C` and `gci_M` on the cloud or the four-level study cannot be computed.

---

## 3. Build the meshes

The cloud builds its own; nothing is uploaded. 25–45 s and 1.7 GiB peak per mesh.

```bash
cd /aeris
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/cloud_prep_build.py
```

**Expect `11 of 11 clean`.** Anything else — a folded cell, a wall-layer error above 1e-9 m —
stop. A grid with inverted cells must never reach a solver, and finding out here costs nothing.

---

## 4. Preflight

```bash
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/cloud_preflight.py --ranks 4
```

It checks nine things and writes `reports/s8_cloud_preflight.json`. **Read the verdict line.**

| verdict | what to do |
|---|---|
| `READY` | go to §5 |
| `NOT READY` | **stop.** Each fatal line names what is wrong |

The one most likely to fire is memory. On this development host it reads
*"11.0 GiB available, 38.2 GiB needed"* — which is correct and is the entire reason for renting.
If it fires on the rented machine too, the machine is too small; nothing downstream will work
and every minute after that bills.

---

## 5. The pilot — do not skip this

```bash
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/cloud_batch_run.py \
    --pilot --ranks 4
```

**31.4 core-hours. $0.63–$1.57 on spot or bare metal, $3.14–$4.70 on mainstream on-demand.**
About 7 % of the batch. It runs one `gci_F` and one `gci_FF` and then **stops on its own**.

It exists because four numbers in the estimate are extrapolations:

| what the pilot measures | against what |
|---|---|
| peak resident memory | a **two-point** memory law stretched to **4×** its largest input |
| iterations to 1e-6 | **one** measured growth ratio extrapolated two levels |
| seconds per Mcell-iteration | 9.7 s, measured only to 1.17M cells |
| **whether ANK-only converges at all** | it is proven only to **1,172,856 cells** |

That last one is the real risk. ANK-only was chosen *because* Newton–Krylov froze at gci_M with
this project's lean preconditioner. At 2.3M and 4.7M cells nobody knows. **Discover that on one
case, not forty-four.**

---

## 6. Reading the pilot

It prints a verdict and writes `reports/s8_cloud_pilot.json`.

```
pilot: PASS -- release the rest
```

Release only when **all four** are true:

1. **both cases `usable`** — judged on the artefacts, not the exit code
2. **peak memory inside the prediction** — 20.6 GiB for `gci_F`, 38.4 for `gci_FF`
3. **seconds per Mcell-iteration near 9.7** — much above it and the batch costs more than 439 core-hours
4. **`gci_FF` actually converged** — this is the ANK-only question

If memory came in **above** prediction, re-size before continuing: the law is a two-point fit and
the pilot is the first real measurement of it. If `gci_FF` did not converge, the fallback is
restoring ADflow's NK defaults, which needs about 2 GiB more per case — **46.8 GiB for
`gci_FF`** — and is itself unproven here. That is a decision, not a retry.

---

## 7. Releasing the rest

```bash
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/cloud_batch_run.py \
    --ranks 4 --budget-core-hours 600
```

The ledger at `artifacts/s8_hf/ledger.json` carries forward, so the two pilot cases are not
re-run and their core-hours are already counted.

**To stop it at any point, from anywhere:**

```bash
echo "why you stopped" > /aeris/AERIS_MESH_STUDY/artifacts/s8_hf/STOP
```

No process has to cooperate. The batch finishes the case it is on and stops before the next.

It also stops on its own if the budget would be exceeded or free disk falls below 25 GiB, and any
single case that starts paging is killed in minutes by the memory watch rather than being left to
finish at disk speed.

---

## 8. When it is done

```bash
.venv/bin/python AERIS_MESH_STUDY/04_strategy_studies/S8_oh_structured/gci_four_level.py --index 83
```

This is what the batch was for. Look for two things:

- **`compatibility.compatible: true`.** If it is false it names the field that differs and refuses
  to combine the levels. If `unverifiable` is non-empty, a level's solver version is unknown —
  §0 again.
- **`triplet_consistency.consistent`.** C/M/F and M/F/FF should give the **same observed order**.
  If they do not, the solutions are not in the asymptotic range and the extrapolated drag is not
  quotable, whatever the formula returns.

Then pull the whole tree back before you destroy the machine:

```bash
tar czf s8_hf.tgz AERIS_MESH_STUDY/artifacts/s8_hf AERIS_MESH_STUDY/05_s6_cfd_qualification/reports
```

`artifacts/` is gitignored and gets wiped. **Anything worth keeping goes in
`05_s6_cfd_qualification/` and gets committed.**
