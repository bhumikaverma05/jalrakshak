import { useEffect, useMemo, useState } from 'react'
import L from 'leaflet'
import { CircleMarker, GeoJSON, MapContainer, TileLayer, Tooltip, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { getWaterBodies } from '../../services/apiClient.js'
import './gis-map.css'

const PAGE_SIZE = 100
const DEFAULT_CENTER = [22, 79]
const TILE_URL = import.meta.env.VITE_OSM_TILE_URL
  || 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const TILE_ATTRIBUTION = import.meta.env.VITE_MAP_TILE_ATTRIBUTION
  || '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
const STATUS_COLORS = { verified: '#16836e', preliminary: '#c48a24', rejected: '#bd5a52' }

function hasPolygonBoundary(boundary) {
  return ['Polygon', 'MultiPolygon'].includes(boundary?.type)
    && Array.isArray(boundary.coordinates)
    && boundary.coordinates.length > 0
}

function getPointCoordinates(location) {
  if (location?.type !== 'Point' || !Array.isArray(location.coordinates)) return null
  const [longitude, latitude] = location.coordinates
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return null
  if (longitude < -180 || longitude > 180 || latitude < -90 || latitude > 90) return null
  return { longitude, latitude }
}

function getStatusColor(status) {
  return STATUS_COLORS[status] || '#52727a'
}

function getBoundaryBounds(boundary) {
  if (!hasPolygonBoundary(boundary)) return null
  const bounds = L.geoJSON(boundary).getBounds()
  return bounds.isValid() ? bounds : null
}

function fitBoundsOrCenter(map, bounds, maxZoom = 13) {
  if (!bounds.isValid()) return
  const southwest = bounds.getSouthWest()
  const northeast = bounds.getNorthEast()
  if (southwest.equals(northeast)) {
    map.setView(southwest, Math.min(12, maxZoom))
    return
  }
  map.fitBounds(bounds.pad(0.14), { maxZoom, padding: [24, 24] })
}

function MapViewportController({ waterBodies, selectedWaterBody, selectionIsManual }) {
  const map = useMap()

  useEffect(() => {
    if (selectionIsManual && selectedWaterBody) {
      const selectedBounds = getBoundaryBounds(selectedWaterBody.boundary)
      if (selectedBounds) {
        fitBoundsOrCenter(map, selectedBounds, 15)
        return
      }
      const point = getPointCoordinates(selectedWaterBody.location)
      if (point) {
        map.flyTo([point.latitude, point.longitude], Math.max(map.getZoom(), 12), { duration: 0.5 })
      }
      return
    }

    const allBounds = L.latLngBounds([])
    waterBodies.forEach((waterBody) => {
      const boundaryBounds = getBoundaryBounds(waterBody.boundary)
      if (boundaryBounds) {
        allBounds.extend(boundaryBounds)
        return
      }
      const point = getPointCoordinates(waterBody.location)
      if (point) allBounds.extend([point.latitude, point.longitude])
    })
    fitBoundsOrCenter(map, allBounds)
  }, [map, selectionIsManual, selectedWaterBody, waterBodies])

  return null
}

function displayStatus(status) {
  return status?.replaceAll('_', ' ') || 'Status unavailable'
}

function getErrorMessage(error) {
  const detail = error.response?.data?.detail
  if (typeof detail === 'string') return detail
  return 'Water bodies could not be loaded. Check the API connection and try again.'
}

function WaterBodyDetails({ waterBody }) {
  if (!waterBody) {
    return <p className="map-panel__hint">Select a water body from the list or map to view its registry details.</p>
  }

  const point = getPointCoordinates(waterBody.location)
  const hasBoundary = hasPolygonBoundary(waterBody.boundary)

  return (
    <div className="water-detail">
      <div className="water-detail__title-row">
        <div>
          <p className="map-eyebrow">Selected water body</p>
          <h3>{waterBody.name}</h3>
        </div>
        <span className={`status-pill status-pill--${waterBody.data_status || 'unknown'}`}>
          {displayStatus(waterBody.data_status)}
        </span>
      </div>
      <dl className="water-detail__fields">
        <div><dt>Registry code</dt><dd>{waterBody.water_body_code || 'Not provided'}</dd></div>
        <div><dt>Type</dt><dd>{waterBody.water_body_type || 'Not provided'}</dd></div>
        <div><dt>Village</dt><dd>{waterBody.village || 'Not provided'}</dd></div>
        <div><dt>District / state</dt><dd>{[waterBody.district, waterBody.state].filter(Boolean).join(', ') || 'Not provided'}</dd></div>
        <div><dt>Registered area</dt><dd>{waterBody.area_sq_km == null ? 'Not provided' : `${waterBody.area_sq_km} km²`}</dd></div>
        <div><dt>Responsible authority</dt><dd>{waterBody.responsible_authority || 'Not provided'}</dd></div>
        {point && (
          <div>
            <dt>Registered coordinates</dt>
            <dd>{point.latitude.toFixed(5)}, {point.longitude.toFixed(5)}</dd>
          </div>
        )}
        {waterBody.description && <div className="water-detail__description"><dt>Description</dt><dd>{waterBody.description}</dd></div>}
      </dl>
      {!hasBoundary && (
        <p className="boundary-notice" role="status">
          {point
            ? 'Boundary unavailable. The map uses the registered point when coordinates are available.'
            : 'No usable boundary or registered coordinates are available for this record.'}
        </p>
      )}
    </div>
  )
}

export default function GisMapPage() {
  const [waterBodies, setWaterBodies] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [selectedId, setSelectedId] = useState(null)
  const [selectionIsManual, setSelectionIsManual] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const [requestStatus, setRequestStatus] = useState({ key: '', error: '' })
  const requestKey = `${page}:${reloadKey}`
  const loading = requestStatus.key !== requestKey
  const error = requestStatus.key === requestKey ? requestStatus.error : ''

  useEffect(() => {
    const controller = new AbortController()
    let active = true

    getWaterBodies({ page, pageSize: PAGE_SIZE, signal: controller.signal })
      .then((response) => {
        if (!active) return
        if (!Array.isArray(response.items)) throw new Error('The water-body response was invalid.')
        const records = response.items
        setWaterBodies(records)
        setTotal(Number(response.total) || 0)
        setSelectedId((currentId) => (
          records.some((item) => item.id === currentId) ? currentId : records[0]?.id || null
        ))
        setSelectionIsManual(false)
        setRequestStatus({ key: requestKey, error: '' })
      })
      .catch((requestError) => {
        if (!active || controller.signal.aborted) return
        setWaterBodies([])
        setTotal(0)
        setSelectedId(null)
        setRequestStatus({ key: requestKey, error: getErrorMessage(requestError) })
      })

    return () => {
      active = false
      controller.abort()
    }
  }, [page, reloadKey, requestKey])

  const selectedWaterBody = useMemo(
    () => waterBodies.find((waterBody) => waterBody.id === selectedId) || null,
    [selectedId, waterBodies],
  )
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const empty = !loading && !error && total === 0

  function selectWaterBody(id) {
    setSelectedId(id)
    setSelectionIsManual(true)
  }

  return (
    <main className="gis-page">
      <section className="gis-page__heading" aria-labelledby="gis-title">
        <div>
          <p className="map-eyebrow">Registry locations and boundaries</p>
          <h1 id="gis-title">GIS water-body map</h1>
          <p>Map features come from the registered water-body API.</p>
        </div>
        <button className="refresh-button" type="button" onClick={() => setReloadKey((key) => key + 1)} disabled={loading}>
          {loading ? 'Loading…' : 'Refresh map data'}
        </button>
      </section>

      <div className="gis-layout">
        <aside className="map-panel" aria-label="Water-body registry details">
          <div className="map-panel__section-heading">
            <div>
              <h2>Water bodies</h2>
              {!error && !loading && <p>{total} registered in the API response</p>}
            </div>
            {total > 0 && <span className="map-panel__page">Page {page} of {pageCount}</span>}
          </div>

          {loading && <p className="map-state map-state--loading" role="status">Loading water bodies…</p>}
          {error && (
            <div className="map-state map-state--error" role="alert">
              <p>{error}</p>
              <button type="button" onClick={() => setReloadKey((key) => key + 1)}>Try again</button>
            </div>
          )}
          {empty && (
            <p className="map-state map-state--empty" role="status">
              No water bodies are registered yet. The map is empty until records are available from the API.
            </p>
          )}

          {!loading && !error && waterBodies.length > 0 && (
            <>
              <ul className="water-body-list">
                {waterBodies.map((waterBody) => (
                  <li key={waterBody.id}>
                    <button
                      type="button"
                      className={`water-body-list__item${waterBody.id === selectedId ? ' is-selected' : ''}`}
                      onClick={() => selectWaterBody(waterBody.id)}
                      aria-pressed={waterBody.id === selectedId}
                    >
                      <span>
                        <strong>{waterBody.name}</strong>
                        <small>{waterBody.water_body_code} · {waterBody.water_body_type}</small>
                      </span>
                      <span className={`status-dot status-dot--${waterBody.data_status || 'unknown'}`} aria-label={displayStatus(waterBody.data_status)} />
                    </button>
                  </li>
                ))}
              </ul>

              {pageCount > 1 && (
                <div className="map-pagination" aria-label="Water-body pages">
                  <button type="button" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={page <= 1 || loading}>Previous</button>
                  <button type="button" onClick={() => setPage((value) => Math.min(pageCount, value + 1))} disabled={page >= pageCount || loading}>Next</button>
                </div>
              )}

              <WaterBodyDetails waterBody={selectedWaterBody} />
            </>
          )}

          <div className="map-legend" aria-label="Registry status colors">
            <span><i className="map-legend__swatch map-legend__swatch--verified" />Verified</span>
            <span><i className="map-legend__swatch map-legend__swatch--preliminary" />Preliminary</span>
            <span><i className="map-legend__swatch map-legend__swatch--rejected" />Rejected</span>
          </div>
        </aside>

        <section className="map-frame" aria-label="Map of registered water bodies">
          <MapContainer className="gis-map" center={DEFAULT_CENTER} zoom={5} scrollWheelZoom>
            <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} maxZoom={19} />
            <MapViewportController
              waterBodies={waterBodies}
              selectedWaterBody={selectedWaterBody}
              selectionIsManual={selectionIsManual}
            />
            {waterBodies.map((waterBody) => {
              const selected = waterBody.id === selectedId
              const color = getStatusColor(waterBody.data_status)
              if (hasPolygonBoundary(waterBody.boundary)) {
                return (
                  <GeoJSON
                    key={`boundary-${waterBody.id}-${selected ? 'selected' : 'idle'}`}
                    data={waterBody.boundary}
                    style={{
                      color: selected ? '#063f39' : color,
                      fillColor: color,
                      weight: selected ? 4 : 2,
                      fillOpacity: selected ? 0.45 : 0.24,
                    }}
                    eventHandlers={{ click: () => selectWaterBody(waterBody.id) }}
                  />
                )
              }
              const point = getPointCoordinates(waterBody.location)
              if (!point) return null
              return (
                <CircleMarker
                  key={`point-${waterBody.id}`}
                  center={[point.latitude, point.longitude]}
                  radius={selected ? 9 : 7}
                  pathOptions={{ color: '#ffffff', weight: 2, fillColor: color, fillOpacity: 1 }}
                  eventHandlers={{ click: () => selectWaterBody(waterBody.id) }}
                >
                  <Tooltip direction="top">{waterBody.name} · {displayStatus(waterBody.data_status)}</Tooltip>
                </CircleMarker>
              )
            })}
          </MapContainer>
          {empty && <div className="map-overlay-state">No registered water bodies to display.</div>}
          {error && <div className="map-overlay-state map-overlay-state--error">Map data is unavailable.</div>}
        </section>
      </div>
      <p className="map-footer-note">Boundaries are shown only when supplied by the registry. Missing boundaries are not estimated.</p>
    </main>
  )
}
