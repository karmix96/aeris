# Flow maps: wing in, flow picture and model out (first version, 31 Oct 2026)

Mike's plan: full design space → what the parametrization can make → focus (Class I–II, b ≤ 7 m)
→ flow maps per family (Re along the span, phenomena, transition, effect of the sections) → a tool that
takes a wing and shows all this with a proposed turbulence model.

`cfdauto/flowmap` (CLI `python -m cfdauto.flowmap`):
1. Family (input: tailless or conventional) and type (our rules, `labels.classify`).
2. Strips: root, two per panel, each break, 97 % of the semi-span; ruled-blend section at each.
3. Local Re = (rho/mu) V c (Stage 0 air), Mach from ISA sound speed.
4. XFOIL per strip at alpha + local twist, free (Ncrit 9) and tripped at 1 % chord; cached in
   data/xfoil_cache. Transition, bubbles (Cf < 0), trailing-edge separation, drag bias of SA.
5. Phenomena list and model proposal by stated rules:
   - laminar run ≥ 10 % chord anywhere and Re < 3.5e6 → γ-Reθ (SST, SU2) for drag; SA (ADflow) for
     mesh studies and as a bound;
   - Re < 1e5 anywhere → RANS indicative only, ILES/LES reference;
   - bubbles → cluster chordwise cells, y+ ≤ 1;
   - LE sweep > 25° and Re normal to the edge > 1e6 → crossflow transition possible.

Limits: 2-D strips; no induced angle; no crossflow; no 3-D bubble relief; angles 5° (slow) and 1°
(fast) in the focus study are our choice, not trimmed.

Focus study (`scripts/focus_flowmaps.py`): every type's mid wing, slow (lowest cruise, 3,048 m) and
fast (top speed, sea level), three section sets each. SA would raise the wing profile drag by
+31 to +94 % in every case except the LA2573A at slow speed (−7 to −9 %: a long bubble).
