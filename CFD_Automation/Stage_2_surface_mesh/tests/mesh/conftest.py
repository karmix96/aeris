import pytest

from cfdauto.mesh.surface import build_surface, wing_from_set


@pytest.fixture(scope="session")
def bwb():
    return wing_from_set("bwb", "reference", 0)


@pytest.fixture(scope="session")
def mesh_vc(bwb):
    return build_surface(bwb.loft, 3.0e5, "VC")
