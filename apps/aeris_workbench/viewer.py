"""One VTK scene, shared by every tab.

A workbench has a single 3D viewport and swaps what is in it, rather than one
render window per tab: the camera stays where the user put it when they move
from geometry to mesh to results, which is the behaviour every commercial tool
has and the thing people notice immediately when it is missing.
"""

from __future__ import annotations

from typing import Any

import vtk

COLORMAPS = {
    "Cool to warm": "coolwarm",
    "Viridis": "viridis",
    "Inferno": "inferno",
    "Grayscale": "gray",
    "Rainbow": "rainbow",
}

# Distinct, reasonably colour-blind-safe patch colours for surface labels.
LABEL_COLORS = [
    (0.24, 0.55, 0.85), (0.94, 0.49, 0.20), (0.20, 0.72, 0.55),
    (0.85, 0.72, 0.25), (0.68, 0.51, 0.85), (0.90, 0.40, 0.50),
]


def _lookup_table(name: str, low: float, high: float) -> vtk.vtkLookupTable:
    table = vtk.vtkLookupTable()
    table.SetTableRange(low, high)
    if name == "gray":
        table.SetHueRange(0.0, 0.0)
        table.SetSaturationRange(0.0, 0.0)
        table.SetValueRange(0.15, 1.0)
    elif name == "rainbow":
        table.SetHueRange(0.667, 0.0)
    elif name in ("viridis", "inferno"):
        ctf = vtk.vtkColorTransferFunction()
        stops = ([(0.0, 0.267, 0.005, 0.329), (0.25, 0.229, 0.322, 0.545),
                  (0.5, 0.128, 0.567, 0.551), (0.75, 0.369, 0.789, 0.383),
                  (1.0, 0.993, 0.906, 0.144)] if name == "viridis" else
                 [(0.0, 0.001, 0.000, 0.014), (0.25, 0.341, 0.063, 0.429),
                  (0.5, 0.735, 0.216, 0.330), (0.75, 0.978, 0.557, 0.035),
                  (1.0, 0.988, 0.998, 0.645)])
        for position, r, g, b in stops:
            ctf.AddRGBPoint(low + (high - low) * position, r, g, b)
        table.SetNumberOfTableValues(256)
        for index in range(256):
            value = low + (high - low) * index / 255.0
            table.SetTableValue(index, *ctf.GetColor(value), 1.0)
        table.Build()
        return table
    else:  # cool to warm
        table.SetHueRange(0.667, 0.0)
        table.SetSaturationRange(0.75, 0.75)
        table.SetValueRange(0.9, 0.9)
    table.Build()
    return table


class Scene:
    """The render window plus whatever is currently displayed in it."""

    def __init__(self, background: tuple[float, float, float] = (0.09, 0.10, 0.12)):
        self.renderer = vtk.vtkRenderer()
        self.renderer.SetBackground(*background)
        self.renderer.SetBackground2(0.04, 0.05, 0.07)
        self.renderer.GradientBackgroundOn()

        self.window, self.backend = self._make_window()
        self.window.AddRenderer(self.renderer)
        self.window.SetSize(1100, 760)

        self.interactor = vtk.vtkRenderWindowInteractor()
        self.interactor.SetRenderWindow(self.window)
        self.interactor.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())

        self._actors: dict[str, vtk.vtkActor] = {}
        self._scalar_bar: vtk.vtkScalarBarActor | None = None
        self._axes: vtk.vtkOrientationMarkerWidget | None = None

    @staticmethod
    def _make_window() -> tuple[Any, str]:
        """Pick a render window that this machine can actually draw with.

        On a desktop session the default X/GLX window is right.  Over SSH or in
        a container there is no GLX, and VTK's failure there is an X protocol
        abort that takes the process down rather than an exception - so each
        candidate is tried in a probe render before it is adopted.
        """
        candidates: list[tuple[str, Any]] = [("glx", vtk.vtkRenderWindow)]
        for name in ("vtkEGLRenderWindow", "vtkOSOpenGLRenderWindow"):
            factory = getattr(vtk, name, None)
            if factory is not None:
                candidates.append((name.replace("vtk", "").replace("RenderWindow", "").lower(),
                                   factory))
        errors: list[str] = []
        for label, factory in candidates:
            try:
                window = factory()
                window.SetOffScreenRendering(1)
                window.SetSize(80, 60)
                probe = vtk.vtkRenderer()
                window.AddRenderer(probe)
                window.Render()
                window.RemoveRenderer(probe)
                window.SetSize(1100, 760)
                return window, label
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{label}: {type(exc).__name__}")
        window = vtk.vtkRenderWindow()
        window.SetOffScreenRendering(1)
        return window, "default (" + ", ".join(errors) + ")" if errors else "default"

    # -- content --------------------------------------------------------- #

    def clear(self) -> None:
        for actor in self._actors.values():
            self.renderer.RemoveActor(actor)
        self._actors.clear()
        self.remove_scalar_bar()

    def remove(self, key: str) -> None:
        actor = self._actors.pop(key, None)
        if actor is not None:
            self.renderer.RemoveActor(actor)

    def remove_scalar_bar(self) -> None:
        if self._scalar_bar is not None:
            self.renderer.RemoveActor2D(self._scalar_bar)
            self._scalar_bar = None

    def add_surface(self, key: str, polydata, *, color=(0.62, 0.70, 0.80),
                    opacity: float = 1.0, edges: bool = False,
                    scalars: str | None = None, association: str = "cell",
                    colormap: str = "coolwarm", scalar_range=None,
                    representation: str = "surface", label: str = "") -> vtk.vtkActor:
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(polydata)
        if scalars:
            data = polydata.GetCellData() if association == "cell" else polydata.GetPointData()
            array = data.GetArray(scalars)
            if array is not None:
                if association == "cell":
                    data.SetActiveScalars(scalars)
                    mapper.SetScalarModeToUseCellData()
                else:
                    data.SetActiveScalars(scalars)
                    mapper.SetScalarModeToUsePointData()
                low, high = scalar_range or array.GetRange()
                if low == high:
                    high = low + 1e-9
                table = _lookup_table(colormap, low, high)
                mapper.SetLookupTable(table)
                mapper.SetScalarRange(low, high)
                mapper.ScalarVisibilityOn()
                self._add_scalar_bar(table, label or scalars)
            else:
                mapper.ScalarVisibilityOff()
        else:
            mapper.ScalarVisibilityOff()

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetColor(*color)
        prop.SetOpacity(opacity)
        prop.SetInterpolationToPhong()
        prop.SetSpecular(0.18)
        prop.SetSpecularPower(24)
        if representation == "wireframe":
            prop.SetRepresentationToWireframe()
            prop.SetLineWidth(1.0)
        elif representation == "points":
            prop.SetRepresentationToPoints()
            prop.SetPointSize(2.0)
        if edges:
            prop.EdgeVisibilityOn()
            prop.SetEdgeColor(0.16, 0.19, 0.24)
            prop.SetLineWidth(0.6)

        self.remove(key)
        self.renderer.AddActor(actor)
        self._actors[key] = actor
        return actor

    def _add_scalar_bar(self, table, title: str) -> None:
        self.remove_scalar_bar()
        bar = vtk.vtkScalarBarActor()
        bar.SetLookupTable(table)
        bar.SetTitle(title)
        bar.SetNumberOfLabels(6)
        bar.SetMaximumWidthInPixels(72)
        bar.SetMaximumHeightInPixels(320)
        bar.GetTitleTextProperty().SetFontSize(13)
        bar.GetTitleTextProperty().SetColor(0.88, 0.90, 0.93)
        bar.GetLabelTextProperty().SetFontSize(11)
        bar.GetLabelTextProperty().SetColor(0.78, 0.82, 0.87)
        bar.GetPositionCoordinate().SetValue(0.90, 0.18)
        self.renderer.AddActor2D(bar)
        self._scalar_bar = bar

    def show_orientation_axes(self) -> None:
        if self._axes is not None:
            return
        axes = vtk.vtkAxesActor()
        axes.SetXAxisLabelText("X")
        axes.SetYAxisLabelText("Y")
        axes.SetZAxisLabelText("Z")
        widget = vtk.vtkOrientationMarkerWidget()
        widget.SetOrientationMarker(axes)
        widget.SetInteractor(self.interactor)
        widget.SetViewport(0.0, 0.0, 0.16, 0.22)
        widget.SetEnabled(1)
        widget.InteractiveOff()
        self._axes = widget

    # -- camera ---------------------------------------------------------- #

    def reset_camera(self) -> None:
        self.renderer.ResetCamera()

    def set_view(self, name: str) -> None:
        camera = self.renderer.GetActiveCamera()
        focal = camera.GetFocalPoint()
        distance = camera.GetDistance() or 1.0
        directions = {
            "+X": ((1, 0, 0), (0, 0, 1)), "-X": ((-1, 0, 0), (0, 0, 1)),
            "+Y": ((0, 1, 0), (0, 0, 1)), "-Y": ((0, -1, 0), (0, 0, 1)),
            "+Z": ((0, 0, 1), (0, 1, 0)), "-Z": ((0, 0, -1), (0, 1, 0)),
            "Isometric": ((1, -1, 0.6), (0, 0, 1)),
        }
        direction, up = directions.get(name, directions["Isometric"])
        norm = sum(component * component for component in direction) ** 0.5
        camera.SetPosition(*[focal[i] + direction[i] / norm * distance for i in range(3)])
        camera.SetViewUp(*up)
        self.renderer.ResetCamera()

    def render(self) -> None:
        self.window.Render()
