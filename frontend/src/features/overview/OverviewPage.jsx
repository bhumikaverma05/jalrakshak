import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getApiHealth } from '../../services/apiClient.js'
import './overview.css'

export default function OverviewPage() {
  const [health, setHealth] = useState({ state: 'checking' })

  useEffect(() => {
    let active = true
    getApiHealth()
      .then((data) => active && setHealth({ state: 'connected', service: data.service }))
      .catch(() => active && setHealth({ state: 'unavailable' }))

    return () => {
      active = false
    }
  }, [])

  const statusLabel = {
    checking: 'Checking API',
    connected: 'API connected',
    unavailable: 'API unavailable',
  }[health.state]

  return (
    <main className="overview-shell">
      <section className="welcome-card" aria-labelledby="welcome-title">
        <p className="eyebrow">GIS water-body registry</p>
        <h2 id="welcome-title">See registered water bodies on the map.</h2>
        <p className="welcome-copy">
          Explore the locations and verified boundaries currently available in the registry.
        </p>
        <Link className="overview-map-link" to="/map">Open GIS map</Link>
        <div className={`api-status api-status--${health.state}`} role="status">
          <span className="status-dot" />
          <span>{statusLabel}</span>
          {health.service && <span className="service-name">{health.service}</span>}
        </div>
      </section>
      <footer>JalRakshak · Water Body Monitoring and Intelligence System</footer>
    </main>
  )
}
