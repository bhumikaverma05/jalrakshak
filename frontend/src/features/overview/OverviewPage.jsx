import { useEffect, useState } from 'react'
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
      <header className="overview-header">
        <div className="brand-mark" aria-hidden="true">J</div>
        <div>
          <p className="eyebrow">Water body monitoring</p>
          <h1>JalRakshak</h1>
        </div>
      </header>
      <section className="welcome-card" aria-labelledby="welcome-title">
        <p className="eyebrow">Project foundation</p>
        <h2 id="welcome-title">Monitoring starts with a clear picture.</h2>
        <p className="welcome-copy">
          The application shell is ready. Monitoring modules will be added in the next milestones.
        </p>
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
