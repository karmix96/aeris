# M1 contract status

Generated 2026-08-30 from the governed audit records.

## Geometry

The live parser-facing geometry configuration and the governance snapshot both
contain 20 active variables with an empty bound-difference set. The live config
SHA-256 and snapshot SHA-256 are retained in `audit_geometry_space.json`.
The Phase-I manifest remains `proposed_semantic_snapshot_not_frozen`; freezing it
requires an explicit review decision and must not modify the live configuration.

## Mission authority

`AERIS_MESH_STUDY/00_governance/operating_points.yaml` explicitly records
`mission_config_found: false`. Therefore Reynolds levels and primary points are
provisional, and the M1 mission gate is open. No CFD condition may be promoted
to authoritative until one mission authority is identified and hashed.

## Half-domain eligibility

The eventual gate must require beta = 0, zero angular rates, symmetric geometry
and controls, and explicit full/half reference-area and force-multiplier tests.
Those tests are not yet implemented; heavy work remains blocked.
