import { Navigate, Route, Routes } from 'react-router-dom'
import OverviewPage from '../features/overview/OverviewPage.jsx'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<OverviewPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
