from aeris.dynamics.config import load_mass_properties_config


def test_load_mass_properties_config_yaml(tmp_path):
    path = tmp_path / "mass.yaml"
    path.write_text(
        """
mass_properties:
  mass_kg: 12.5
  x_cg_m: 0.4
  y_cg_m: 0.0
  z_cg_m: 0.0
  ixx_kg_m2: 0.8
  iyy_kg_m2: 1.5
  izz_kg_m2: 2.1
""".strip(),
        encoding="utf-8",
    )

    cfg = load_mass_properties_config(path)
    assert cfg.mass_kg == 12.5
    assert cfg.x_cg_m == 0.4
    assert cfg.ixx_kg_m2 == 0.8