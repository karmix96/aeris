# AERIS

AI-Driven Engineering and Rapid Integrated Synthesis

AERIS is a modular aircraft design platform for deterministic geometry generation, dataset creation, and future aero/ML workflows.

## Current Status

- BWB geometry generator (bwb_segmented_v1)
- Modular sampling (lhs_v1, random_v1)
- Dataset pipeline with metadata + failures
- Optional AeroSandbox geometry build
- Plotting can be disabled for fast batch runs

## Quick Start

Install:

python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .

Run geometry:

aeris geometry generate -c configs/geometry/baseline_bwb.yaml

Run dataset:

aeris dataset generate \
  -c configs/geometry/wing_bwb.yaml \
  --n 20 \
  --sampler lhs_v1 \
  --sampler-seed 123

Fast dataset (no plots):

aeris dataset generate \
  -c configs/geometry/wing_bwb.yaml \
  --n 500 \
  --sampler lhs_v1 \
  --sampler-seed 123 \
  --no-save-plot

With AeroSandbox:

aeris dataset generate \
  -c configs/geometry/wing_bwb.yaml \
  --n 20 \
  --sampler lhs_v1 \
  --sampler-seed 123 \
  --no-save-plot \
  --build-aerosandbox

Inspect dataset:

aeris dataset inspect --dataset <path>

## Principles

- modular
- deterministic
- CLI-first
- artifact-driven

## Next Phase

Checkpoint 6 — Aero Architecture
