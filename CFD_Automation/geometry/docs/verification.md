# Geometry verification

Numbers, not pictures. All errors in % of local chord. Limits: sections 0.01, edges 1e-06, ruled 1e-06, CAD 0.05.

| wing | loft | sections max | edges max | ruled max | outside data | pass |
|---|---|---|---|---|---|---|
| onera_m6 | numpy | 0.00026 | 4.9e-14 | 4.8e-14 | CATIA IGES: max 0.0113, rms 0.0017 | yes |
| ribes | numpy | 0.00049 | 2.3e-14 | 5.3e-14 | none in repo | yes |
| nasa_crm | numpy | 0.00279 | 2.2e-13 | 2.3e-13 | none in repo | yes |
| blendednet_low | numpy | 0.00268 | 9.8e-14 | 7.9e-14 | none in repo | yes |
| blendednet_mid | numpy | 0.00268 | 1.5e-13 | 8.8e-14 | none in repo | yes |
| blendednet_high | numpy | 0.00268 | 2.4e-13 | 1.4e-13 | none in repo | yes |
| blendednetpp_mid | numpy | 0.00268 | 1.5e-13 | 1.4e-13 | none in repo | yes |

Points in the airfoil files that look like typos (one point off a smooth line; left out of the error, the loft smooths over them):

- sc20412: lower surface at x/c 0.72999

What this proves and what it does not:

- sections/edges/ruled: the surface is exactly the wing the parameters describe (right airfoils, chords, sweeps, twists, straight panels).
- outside data: only the ONERA M6 has an independent CAD model here. BlendedNet, CRM and RIBES need their own surface files (see OPEN_DECISIONS.md) to prove the parameters themselves are right.
