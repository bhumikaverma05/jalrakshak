"""Sentinel-2 raster alignment, MNDWI classification, and area measurements."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import ceil, floor
from typing import Any

import numpy as np
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.errors import CRSError, TransformError
from rasterio.features import bounds, geometry_mask
from rasterio.transform import Affine
from rasterio.warp import reproject, transform_geom

MAX_ANALYSIS_PIXELS = 5_000_000


@dataclass(frozen=True)
class RasterBand:
    """A reflectance-normalized band with grid metadata required for reprojection.

    A concrete imagery provider must convert raw source digital numbers and
    band-specific offsets to reflectance before handing arrays to the processor.
    """

    data: np.ndarray
    transform: Affine
    crs: CRS | str
    nodata: float | int | None = None


@dataclass(frozen=True)
class Sentinel2RasterInputs:
    """Sentinel-2 L2A green, SWIR1, and scene-classification bands."""

    b03_green: RasterBand
    b11_swir1: RasterBand
    scl: RasterBand


@dataclass(frozen=True)
class ProcessingSettings:
    mndwi_water_threshold: float = 0.0
    analysis_pixel_size_m: float = 20.0

    def __post_init__(self) -> None:
        if not -1 <= self.mndwi_water_threshold <= 1:
            raise ValueError("MNDWI water threshold must be between -1 and 1")
        if not 0 < self.analysis_pixel_size_m <= 120:
            raise ValueError("Analysis pixel size must be greater than 0 and at most 120 m")


@dataclass(frozen=True)
class SatelliteProcessingResult:
    mndwi: np.ndarray
    valid_mask: np.ndarray
    water_mask: np.ndarray
    mean_mndwi: float
    cloud_percentage: float
    water_pixel_count: int
    valid_pixel_count: int
    water_area_sq_m: float
    analysis_crs: str
    analysis_pixel_size_m: float
    mndwi_water_threshold: float


class SatelliteProcessingError(ValueError):
    """Raised when a scene or boundary cannot produce a valid measurement."""


def local_utm_crs(boundary: Mapping[str, Any]) -> CRS:
    """Choose the local metre-based UTM CRS from a WGS84 boundary extent."""
    try:
        left, bottom, right, top = bounds(boundary)
    except (TypeError, ValueError, KeyError):
        raise SatelliteProcessingError("A valid boundary geometry is required") from None
    longitude = (left + right) / 2
    latitude = (bottom + top) / 2
    if not (-180 <= longitude <= 180 and -80 <= latitude <= 84):
        raise SatelliteProcessingError("Boundary is outside the supported UTM latitude range")
    if right - left > 6 or top - bottom > 8:
        raise SatelliteProcessingError("Boundary is too large for a single local UTM zone")
    zone = min(60, max(1, floor((longitude + 180) / 6) + 1))
    epsg = (32600 if latitude >= 0 else 32700) + zone
    return CRS.from_epsg(epsg)


def _aligned_band(
    band: RasterBand,
    *,
    shape: tuple[int, int],
    transform: Affine,
    target_crs: CRS,
    resampling: Resampling,
    destination_nodata: float,
) -> np.ndarray:
    source = np.asarray(band.data)
    if source.ndim != 2 or source.size == 0:
        raise SatelliteProcessingError("Input bands must be non-empty two-dimensional rasters")
    destination = np.full(shape, destination_nodata, dtype=np.float32)
    reproject(
        source=source,
        destination=destination,
        src_transform=band.transform,
        src_crs=CRS.from_user_input(band.crs),
        src_nodata=band.nodata,
        dst_transform=transform,
        dst_crs=target_crs,
        dst_nodata=destination_nodata,
        resampling=resampling,
        init_dest_nodata=True,
    )
    return destination


def process_sentinel2_bands(
    inputs: Sentinel2RasterInputs,
    boundary: Mapping[str, Any],
    *,
    settings: ProcessingSettings | None = None,
    analysis_crs: CRS | str | None = None,
) -> SatelliteProcessingResult:
    """Align B03/B11/SCL on a metric grid and compute masked water area.

    B03 and B11 are resampled bilinearly to the target grid; SCL is resampled
    with nearest-neighbour to preserve categorical values. Pixel area is
    calculated in a projected metre-based CRS, never in longitude/latitude.
    """
    settings = settings or ProcessingSettings()
    if not boundary or boundary.get("type") not in {"Polygon", "MultiPolygon"}:
        raise SatelliteProcessingError("A Polygon or MultiPolygon boundary is required")
    try:
        target_crs = CRS.from_user_input(analysis_crs) if analysis_crs else local_utm_crs(boundary)
        if not target_crs.is_projected or target_crs.linear_units != "metre":
            raise SatelliteProcessingError("Analysis CRS must be projected in metres")
        projected_boundary = transform_geom("EPSG:4326", target_crs, boundary)
        left, bottom, right, top = bounds(projected_boundary)
    except SatelliteProcessingError:
        raise
    except (CRSError, TransformError, TypeError, ValueError) as exc:
        raise SatelliteProcessingError(f"Boundary could not be projected: {exc}") from None

    pixel_size = settings.analysis_pixel_size_m
    width = ceil((right - left) / pixel_size)
    height = ceil((top - bottom) / pixel_size)
    if width < 1 or height < 1:
        raise SatelliteProcessingError("Boundary has no measurable area")
    if width * height > MAX_ANALYSIS_PIXELS:
        raise SatelliteProcessingError(
            f"Boundary exceeds the processing limit of {MAX_ANALYSIS_PIXELS} pixels"
        )
    transform = Affine(pixel_size, 0, left, 0, -pixel_size, top)
    shape = (height, width)

    green = _aligned_band(
        inputs.b03_green,
        shape=shape,
        transform=transform,
        target_crs=target_crs,
        resampling=Resampling.bilinear,
        destination_nodata=np.nan,
    )
    swir = _aligned_band(
        inputs.b11_swir1,
        shape=shape,
        transform=transform,
        target_crs=target_crs,
        resampling=Resampling.bilinear,
        destination_nodata=np.nan,
    )
    scl = _aligned_band(
        inputs.scl,
        shape=shape,
        transform=transform,
        target_crs=target_crs,
        resampling=Resampling.nearest,
        destination_nodata=0,
    )
    inside_boundary = geometry_mask(
        [projected_boundary], out_shape=shape, transform=transform, invert=True
    )

    no_data_or_defective = np.isin(scl, [0, 1])
    cloud_or_shadow = np.isin(scl, [3, 7, 8, 9, 10])
    snow = scl == 11
    valid_mask = (
        inside_boundary
        & np.isfinite(green)
        & np.isfinite(swir)
        & np.isfinite(scl)
        & ~no_data_or_defective
        & ~cloud_or_shadow
        & ~snow
    )
    observed_mask = inside_boundary & np.isfinite(scl) & ~no_data_or_defective
    observed_count = int(np.count_nonzero(observed_mask))
    if observed_count == 0:
        raise SatelliteProcessingError("No scene-classification pixels overlap the boundary")

    cloud_percentage = 100.0 * np.count_nonzero(cloud_or_shadow & observed_mask) / observed_count
    denominator = green + swir
    mndwi = np.full(shape, np.nan, dtype=np.float32)
    np.divide(green - swir, denominator, out=mndwi, where=valid_mask & (denominator != 0))
    valid_mask &= np.isfinite(mndwi)
    valid_count = int(np.count_nonzero(valid_mask))
    if valid_count == 0:
        raise SatelliteProcessingError("No valid cloud-free pixels overlap the boundary")

    water_mask = valid_mask & (mndwi >= settings.mndwi_water_threshold)
    water_count = int(np.count_nonzero(water_mask))
    return SatelliteProcessingResult(
        mndwi=mndwi,
        valid_mask=valid_mask,
        water_mask=water_mask,
        mean_mndwi=float(np.mean(mndwi[valid_mask])),
        cloud_percentage=cloud_percentage,
        water_pixel_count=water_count,
        valid_pixel_count=valid_count,
        water_area_sq_m=water_count * pixel_size**2,
        analysis_crs=target_crs.to_string(),
        analysis_pixel_size_m=pixel_size,
        mndwi_water_threshold=settings.mndwi_water_threshold,
    )


def compare_historical_area(
    current_area_sq_m: float, previous_area_sq_m: float | None
) -> dict[str, float | None]:
    """Return area change against the preceding successful observation."""
    if current_area_sq_m < 0 or (previous_area_sq_m is not None and previous_area_sq_m < 0):
        raise ValueError("Water areas cannot be negative")
    if previous_area_sq_m is None:
        return {"previous_area_sq_m": None, "delta_area_sq_m": None, "change_percent": None}
    delta = current_area_sq_m - previous_area_sq_m
    change = (delta / previous_area_sq_m * 100) if previous_area_sq_m else None
    return {
        "previous_area_sq_m": previous_area_sq_m,
        "delta_area_sq_m": delta,
        "change_percent": change,
    }
