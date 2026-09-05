"""Open the S8 O-H grid in ParaView: the wall surface AND the volume together.

    paraview --script=AERIS_MESH_STUDY/artifacts/paraview_inspection/s8_oh/open_surface_and_volume.py

The two existing openers show one or the other.  What you usually want when
judging an O-H grid is both at once: the wall as a solid body, and the volume cut
open beside it so the wall-normal march and the O-ring are visible against the
surface they came from.

Layout, on `oh_L3` (index 83, the mesh the CFD sweep used):

  * the closed wall surface (o_wing eta=0 plus the tip cap), drawn as a solid
    with its edges on, so the chordwise and spanwise distributions read directly;
  * the volume, clipped at y = 0.30 m, showing the O in the section plane -- the
    view of figure 28 in the Zhang paper this topology is drawn from;
  * a second clip near the tip, y = 0.94 m, where the section is thinnest and
    the spanwise cells are smallest -- the region every S8 defect so far has
    come from;
  * a Threshold on volume_m3 <= 0, which should be empty.  It is the inverted
    cell check, drawn rather than asserted.

The camera sits on the -y side so +x runs to the right and the flow reads left
to right.
"""

from paraview.simple import *  # noqa: F403

HERE = ("/home/mike/Desktop/Start_Up/Code/v.0.1_Project/AERIS_MESH_STUDY"
        "/artifacts/paraview_inspection/s8_oh")
LEVEL = "oh_L3"
VOLUME_BLOCKS = ("o_wing", "o_out", "cap_out")
#: the wing block alone; the far-field annulus buries the geometry if shown solid
SECTION_CLIP_Y = 0.30
TIP_CLIP_Y = 0.94

view = GetActiveViewOrCreate("RenderView")
view.ViewSize = [1600, 1000]

# ---------------------------------------------------------------- the wall ---
surface = LegacyVTKReader(
    registrationName=f"{LEVEL}_wall_surface",
    FileNames=[f"{HERE}/{LEVEL}_surface.vtk"],
)
wall = Show(surface, view, "UnstructuredGridRepresentation")
wall.Representation = "Surface With Edges"
wall.AmbientColor = [0.15, 0.15, 0.15]
wall.DiffuseColor = [0.78, 0.80, 0.84]
wall.EdgeColor = [0.20, 0.22, 0.26]
wall.LineWidth = 1.0
wall.Opacity = 1.0

# -------------------------------------------------------------- the volume ---
# Only the wing block is cut open.  o_out and cap_out reach 40 root chords and
# would swamp the view; they are loaded but hidden, so they are one click away.
readers = {}
for name in VOLUME_BLOCKS:
    reader = LegacyVTKReader(
        registrationName=f"{LEVEL}_{name}",
        FileNames=[f"{HERE}/{LEVEL}_{name}.vtk"],
    )
    readers[name] = reader
    if name != "o_wing":
        Show(reader, view, "UnstructuredGridRepresentation")
        Hide(reader, view)

for tag, y in (("section", SECTION_CLIP_Y), ("tip", TIP_CLIP_Y)):
    clip = Clip(registrationName=f"o_wing_clip_{tag}", Input=readers["o_wing"])
    clip.ClipType = "Plane"
    clip.ClipType.Origin = [0.0, y, 0.0]
    clip.ClipType.Normal = [0.0, 1.0, 0.0]
    clip.Invert = 1
    shown = Show(clip, view, "UnstructuredGridRepresentation")
    shown.Representation = "Surface With Edges"
    shown.EdgeColor = [0.35, 0.45, 0.60]
    shown.DiffuseColor = [0.55, 0.68, 0.85]
    shown.LineWidth = 0.6
    shown.Opacity = 1.0 if tag == "section" else 0.0
    if tag == "tip":
        Hide(clip, view)          # loaded and one click from visible

# ------------------------------------------------- the inverted-cell check ---
empty = []
for name, reader in readers.items():
    threshold = Threshold(registrationName=f"inverted_{name}", Input=reader)
    try:
        threshold.Scalars = ["CELLS", "volume_m3"]
        threshold.LowerThreshold = -1.0e30
        threshold.UpperThreshold = 0.0
        threshold.ThresholdMethod = "Between"
        threshold.UpdatePipeline()
        n = threshold.GetDataInformation().GetNumberOfCells()
    except Exception as error:      # noqa: BLE001 - reported, never assumed clean
        n = f"unavailable: {error}"
    empty.append((name, n))
    Show(threshold, view, "UnstructuredGridRepresentation")
    Hide(threshold, view)

# ------------------------------------------------------------------ camera ---
view.ResetCamera()
view.CameraPosition = [0.45, -3.0, 0.9]
view.CameraFocalPoint = [0.45, 0.45, 0.0]
view.CameraViewUp = [0.0, 0.0, 1.0]
view.CameraParallelProjection = 0
view.Background = [1.0, 1.0, 1.0]
view.UseColorPaletteForBackground = 0
Render()

print(f"S8 {LEVEL}, lhs100_seed42[83] -- the mesh the CFD sweep used")
print(f"  wall surface : {HERE}/{LEVEL}_surface.vtk")
print(f"  volume cut at y = {SECTION_CLIP_Y} m (visible) and y = {TIP_CLIP_Y} m (hidden)")
print(f"  o_out and cap_out are loaded and hidden; the far field is 40 root chords")
print("  inverted cells per block (should all be 0):")
for name, n in empty:
    print(f"    {name:9s} {n}")
