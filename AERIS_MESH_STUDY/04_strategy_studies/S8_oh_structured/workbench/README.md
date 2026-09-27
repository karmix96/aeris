# S8 Aero Workbench

An Ansys-style front end for the S8 O-H structured pipeline. Published at
https://claude.ai/artifact/Qo7rhp2cBfhTzJgfewqGuA

    export_bundle.py   harvests runs/, reports/ and data/ into one bundle
    app_data.py        trims that bundle into s8data.js, the page's payload
    index.html         the workbench itself

Rebuild the payload and republish:

    python export_bundle.py && python app_data.py

`s8data.js` is generated, so it is not committed.

## What is live rather than illustrated

The mesh viewport is generated in the browser from the `OHLevel` fields, not
drawn. Changing `n_side`, `s0_frac`, `n_normal` or `te_floor_frac` re-runs the
ring construction, the normal marching with smoothed normals, and the signed
cell areas, so folded cells and y+ respond to the controls. The predicted cell
count is shown against the count of the mesh actually built at that level, with
the deviation, so the page cannot quietly disagree with the repo.

## What is a stand-in, and says so

Only RIBES carries a measured section. The NACA 0012 and 4412 sections are
generated, and are labelled as stand-ins; they are the sections the 2D TMR
verification cases actually used. The AERIS g83 planform numbers are editable
placeholders, because the g83 loft is not in this bundle - the panel says this
rather than implying the numbers are the design record.
