import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Services from './pages/Services'
import WhatsApp from './pages/WhatsApp'
import Settings from './pages/Settings'

export default function App() {
  const [currentTime, setCurrentTime] = useState(new Date())

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <BrowserRouter>
      <Layout currentTime={currentTime}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/services" element={<Services />} />
          <Route path="/whatsapp" element={<WhatsApp />} />
          <Route path="/settings" element={<Settings />} />
          
          {/* Redirect legacy routes to appropriate pages */}
          <Route path="/jarvis" element={<Navigate to="/" replace />} />
          <Route path="/dashboard" element={<Navigate to="/" replace />} />
          <Route path="/quick-setup" element={<Navigate to="/settings" replace />} />
          <Route path="/setup" element={<Navigate to="/settings" replace />} />
          <Route path="/tasks/view" element={<Navigate to="/" replace />} />
          <Route path="/whatsapp-qr" element={<Navigate to="/whatsapp" replace />} />
          <Route path="/whatsapp-status" element={<Navigate to="/whatsapp" replace />} />
          <Route path="/auth-dashboard" element={<Navigate to="/settings" replace />} />
          <Route path="/google-services-dashboard" element={<Navigate to="/settings" replace />} />
          
          {/* Catch all - redirect to dashboard */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
