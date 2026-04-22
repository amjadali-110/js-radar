import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import Scans from './pages/Scans';
import ScanDetails from './pages/ScanDetails';
import CreateScan from './pages/CreateScan';

function AppContent() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const location = useLocation();

  // Auto-collapse on scan details, auto-expand on other pages
  useEffect(() => {
    const isScanDetails = /^\/scans\/[^/]+$/.test(location.pathname) && location.pathname !== '/scans/new';
    const isDesktop = window.innerWidth >= 1024;
    setSidebarCollapsed(isScanDetails && isDesktop);
  }, [location.pathname]);

  const toggleSidebar = () => {
    setSidebarOpen(!sidebarOpen);
  };

  return (
    <div className="flex min-h-screen bg-cyber-dark cyber-shell">
      <Sidebar isOpen={sidebarOpen} onToggle={toggleSidebar} collapsed={sidebarCollapsed} onCollapse={() => setSidebarCollapsed(!sidebarCollapsed)} />
      <main className="flex-1 overflow-y-auto overflow-x-hidden lg:ml-0 cyber-scanlines">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/scans" element={<Scans />} />
            <Route path="/scans/new" element={<CreateScan />} />
            <Route path="/scans/:scanId" element={<ScanDetails />} />
          </Routes>
        </main>
      </div>
  );
}

function App() {
  return (
    <Router>
      <AppContent />
    </Router>
  );
}

export default App;
