"""Provider contracts for Sentinel-2 scene discovery and band access.

No live provider is configured yet. A concrete adapter can be added once the
deployment supplies an approved imagery source and any required credentials.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.domains.satellite.processing import Sentinel2RasterInputs


@dataclass(frozen=True)
class Sentinel2Scene:
    scene_id: str
    acquired_at: datetime
    cloud_percentage: float


class Sentinel2Provider(Protocol):
    """Adapter contract; provider implementations return real sourced scenes."""

    def search_scenes(
        self,
        *,
        boundary: Mapping[str, Any],
        start_at: datetime,
        end_at: datetime,
        max_cloud_percentage: float,
    ) -> Sequence[Sentinel2Scene]: ...

    def load_bands(
        self, *, scene_id: str, boundary: Mapping[str, Any]
    ) -> Sentinel2RasterInputs: ...


class Sentinel2ProviderUnavailable(RuntimeError):
    """Raised when a requested provider is not configured for this deployment."""
