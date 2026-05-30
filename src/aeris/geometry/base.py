"""
Defines the abstract contract for all AERIS geometry generators.

A geometry generator in AERIS must implement:
    - configuration construction from raw YAML input
    - sampling of explicit design vectors
    - deterministic geometry realization from a sample
    - summary metadata about a realized case

Pipelines and higher-level systems depend only on this contract, allowing
multiple geometry families and implementations to coexist behind a single API.

Type parameters:
    ConfigT: typed configuration object returned by build_config.
    SampleT: typed sample object returned by sample_one.
    CaseT:   typed case result returned by run_full_case.

Generators SHOULD declare these explicitly for downstream type safety:

    class BwbSegmentedV1Generator(
        GeometryGenerator[BwbConfig, BwbSample, BwbCaseResult]
    ):
        GENERATOR_ID: ClassVar[str] = "bwb_segmented_v1"
        ...

Identity convention:
    Generators declare their ID via the GENERATOR_ID class attribute. The
    instance property `generator_id` is a convenience accessor that reads
    this attribute. The registry uses the class attribute (no instance needed
    for registration).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar, Generic, Mapping, TypeVar

ConfigT = TypeVar("ConfigT")
SampleT = TypeVar("SampleT")
CaseT = TypeVar("CaseT")


class GeometryGenerator(ABC, Generic[ConfigT, SampleT, CaseT]):
    """External contract for AERIS geometry generators.

    Pipelines should depend on this contract, not on generator-specific files.
    """

    #: Required class attribute. Single source of truth for the generator
    #: identity. Used by the registry for lookup, and by the property
    #: ``generator_id`` for instance-level access.
    GENERATOR_ID: ClassVar[str]

    @property
    def generator_id(self) -> str:
        """Return the generator's identity string (from GENERATOR_ID)."""
        return self.GENERATOR_ID

    @property
    def display_name(self) -> str:
        """Return a human-readable name. Defaults to generator_id."""
        return self.generator_id

    @abstractmethod
    def build_config(self, raw_config: dict[str, Any]) -> ConfigT:
        """Build and validate the generator-specific typed config object.

        Raises:
            ValueError: if the raw YAML structure is invalid for this generator.
        """
        raise NotImplementedError

    @abstractmethod
    def sample_one(self, config: ConfigT, seed: int | None = None) -> SampleT:
        """Produce one explicit, deterministic sampled design vector.

        The same (config, seed) MUST produce the same sample.
        """
        raise NotImplementedError

    @abstractmethod
    def run_full_case(
        self,
        sample: SampleT,
        config: ConfigT,
        output_dir: Path,
    ) -> CaseT:
        """Run the full deterministic geometry realization from an explicit sample.

        The same (sample, config) MUST produce the same case result. Output
        artifacts are written under output_dir.

        Note:
            Some generators (e.g. BWB v1) accept additional keyword arguments
            beyond this base signature (e.g. save_plot, build_aerosandbox).
            That is a known temporary contract mismatch — see deferred tracker
            item D15. The intent is to move those toggles into the config
            object so this abstract signature becomes complete.
        """
        raise NotImplementedError

    def summarize_case(self, case: CaseT) -> Mapping[str, Any]:
        """Return a JSON-serializable summary of a case.

        Downstream consumers (aeris.dataset.*, aeris.ml.*) read this summary.
        The recommended minimum schema:

            - 'design_id': stable string identifier
            - 'feasible': bool

        Generators may return additional generator-specific keys.

        Note:
            This method is currently OPTIONAL (empty default). It will become
            abstract once all generators implement it — see deferred tracker
            item D14. Generators SHOULD override it.
        """
        return {}