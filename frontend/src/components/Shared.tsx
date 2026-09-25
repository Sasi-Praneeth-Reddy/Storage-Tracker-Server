/* KPI Card component */
interface KpiCardProps {
  title: string;
  value: string | number;
  accent?: string;
  delta?: { value: number; higherIsBetter?: boolean };
  small?: boolean;
}

export function KpiCard({ title, value, accent = 'var(--accent-green)', delta, small }: KpiCardProps) {
  return (
    <div className="kpi-card" style={{ borderTopColor: accent }}>
      <div className="kpi-title">{title}</div>
      <div className="kpi-value" style={small ? { fontSize: 20 } : {}}>{value}</div>
      {delta != null && delta.value !== 0 && (
        <div className={`kpi-delta ${delta.value >= 0 ? (delta.higherIsBetter === false ? 'down' : 'up') : (delta.higherIsBetter === false ? 'up' : 'down')}`}>
          {delta.value >= 0 ? '↑' : '↓'} {Math.abs(delta.value).toFixed(1)}% vs prev period
        </div>
      )}
    </div>
  );
}

/* Loading spinner */
export function Spinner() {
  return (
    <div className="loading-center">
      <div className="spinner" />
      <span>Loading market data…</span>
    </div>
  );
}

/* Empty state */
export function EmptyState({ message = 'No data available' }: { message?: string }) {
  return <div className="empty-state">📭 {message}</div>;
}

/* Status badge */
export function StatusBadge({ status }: { status: string }) {
  const cls =
    status === 'for_sale'        ? 'badge-green'  :
    status === 'under_contract'  ? 'badge-orange' :
    status === 'sold'            ? 'badge-blue'   :
    status === 'Available'       ? 'badge-green'  :
    'badge-gray';
  const label = status.replace(/_/g, ' ');
  return <span className={`badge ${cls}`}>{label}</span>;
}

/* Tabs */
interface TabsProps {
  tabs: string[];
  active: number;
  onChange: (i: number) => void;
}

export function Tabs({ tabs, active, onChange }: TabsProps) {
  return (
    <div className="tabs-bar">
      {tabs.map((t, i) => (
        <button
          key={t}
          className={`tab-btn${active === i ? ' active' : ''}`}
          onClick={() => onChange(i)}
        >
          {t}
        </button>
      ))}
    </div>
  );
}
