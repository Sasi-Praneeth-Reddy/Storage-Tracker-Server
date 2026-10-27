import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { Home, Package, Database, BarChart2 } from 'lucide-react';
import RealEstatePage  from './pages/RealEstatePage';
import StoragePage     from './pages/StoragePage';
import DatabasePage    from './pages/DatabasePage';

function Sidebar() {
  const navItem = (to: string, Icon: React.FC<{ size?: number }>, label: string) => (
    <NavLink to={to} className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
      <Icon size={16} />
      {label}
    </NavLink>
  );

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <h1>🏢 Storage Tracker</h1>
        <p>Market Intelligence v2</p>
      </div>
      <nav className="sidebar-nav">
        <div className="nav-section-label">Markets</div>
        {navItem('/real-estate',  Home,      '🏡 Real Estate')}
        {navItem('/storage',      Package,   '📦 Self-Storage')}
        <div className="nav-section-label" style={{ marginTop: 16 }}>Data</div>
        {navItem('/database',     Database,  '🗄️ Database View')}
      </nav>
      <div style={{ padding: '20px', borderTop: '1px solid var(--border)', marginTop: 'auto' }}>
        <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
          <BarChart2 size={12} style={{ display: 'inline', marginRight: 4 }} />
          Around Town Movers
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginTop: 2 }}>
          Northern Virginia · DC · MD
        </div>
      </div>
    </aside>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        <Sidebar />
        <main className="main-content">
          <Routes>
            <Route path="/"             element={<RealEstatePage />} />
            <Route path="/real-estate"  element={<RealEstatePage />} />
            <Route path="/storage"      element={<StoragePage />} />
            <Route path="/database"     element={<DatabasePage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
