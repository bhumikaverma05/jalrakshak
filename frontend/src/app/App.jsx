import { Link, Navigate, NavLink, Route, Routes } from 'react-router-dom'
import GisMapPage from '../features/map/GisMapPage.jsx'
import OverviewPage from '../features/overview/OverviewPage.jsx'
import './app.css'

function SiteHeader() {
  return (
    <header className="site-header">
      <Link className="site-brand" to="/" aria-label="JalRakshak dashboard">
        <span className="site-brand__mark" aria-hidden="true">J</span>
        <span>
          <span className="site-brand__eyebrow">Water body monitoring</span>
          <span className="site-brand__name">JalRakshak</span>
        </span>
      </Link>
      <nav className="site-navigation" aria-label="Main navigation">
        <NavLink to="/" end className={({ isActive }) => isActive ? 'site-navigation__link is-active' : 'site-navigation__link'}>
          Dashboard
        </NavLink>
        <NavLink to="/map" className={({ isActive }) => isActive ? 'site-navigation__link is-active' : 'site-navigation__link'}>
          GIS map
        </NavLink>
      </nav>
    </header>
  )
}

export default function App() {
  return (
    <>
      <SiteHeader />
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/map" element={<GisMapPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  )
}
