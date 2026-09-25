/**
 * RealEstatePage.tsx  — Regional MLS Market dashboard
 */
import { useState, useEffect, useCallback } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, CartesianGrid, Legend,
} from 'recharts';
import { RefreshCw } from 'lucide-react';
import { realEstate } from '../api';
import { KpiCard, Spinner, EmptyState, Tabs, StatusBadge } from '../components/Shared';
import RealEstateMap from '../components/RealEstateMap';
import { format } from 'date-fns';

const COLORS = ['#2196F3','#4CAF50','#FF9800','#F44336','#9C27B0','#00BCD4','#FFC107','#E91E63','#00E5FF','#76FF03'];
const STATUS_COLORS: Record<string,string> = {
  for_sale: '#4CAF50', under_contract: '#FF9800', sold: '#2196F3',
};

const today      = format(new Date(), 'yyyy-MM-dd');
const monthStart = format(new Date(new Date().getFullYear(), new Date().getMonth(), 1), 'yyyy-MM-dd');

export default function RealEstatePage() {
  const [opts,     setOpts]     = useState<{ statuses: string[]; states: string[]; counties: string[] }>({ statuses: [], states: [], counties: [] });
  const [selStatus, setSelStatus] = useState('');
  const [selState,  setSelState]  = useState('');
  const [selCounty, setSelCounty] = useState('');
  const [dateFrom,  setDateFrom]  = useState(monthStart);
  const [dateTo,    setDateTo]    = useState(today);
  const [kpis,      setKpis]      = useState<any>(null);
  const [listings,  setListings]  = useState<any[]>([]);
  const [byCounty,  setByCounty]  = useState<any[]>([]);
  const [priceCtx,  setPriceCtx]  = useState<any[]>([]);
  const [weekly,    setWeekly]    = useState<any[]>([]);
  const [transitions, setTransitions] = useState<any[]>([]);
  const [realtors,  setRealtors]  = useState<any[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [tab,       setTab]       = useState(0);

  // Load filter options once
  useEffect(() => {
    realEstate.getFilterOptions().then(setOpts).catch(console.error);
  }, []);

  const params = useCallback(() => {
    const p: Record<string,string> = { date_from: dateFrom, date_to: dateTo };
    if (selStatus) p.status  = selStatus;
    if (selState)  p.state   = selState;
    if (selCounty) p.county  = selCounty;
    return p;
  }, [selStatus, selState, selCounty, dateFrom, dateTo]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = params();
      const [k, l, bc, pc, w, tr, r] = await Promise.all([
        realEstate.getKpis(p),
        realEstate.getListings(p),
        realEstate.getByCounty(p),
        realEstate.getPriceByCounty(p),
        realEstate.getWeeklyTrend(p),
        realEstate.getStatusTransitions(p),
        realEstate.getRealtors(p),
      ]);
      setKpis(k); setListings(l); setByCounty(bc); setPriceCtx(pc);
      setWeekly(w); setTransitions(tr); setRealtors(r);
    } finally {
      setLoading(false);
    }
  }, [params]);

  useEffect(() => { load(); }, [dateFrom, dateTo, selStatus, selState, selCounty]);

  // Group weekly data for stacked bar
  const weeklyGrouped = (() => {
    const map: Record<string, Record<string,number>> = {};
    const statuses = new Set<string>();
    weekly.forEach((r: any) => {
      if (!map[r.week]) map[r.week] = {};
      map[r.week][r.status] = r.count;
      statuses.add(r.status);
    });
    return {
      rows: Object.entries(map).sort(([a],[b]) => a.localeCompare(b)).map(([week, vals]) => ({ week, ...vals })),
      statuses: Array.from(statuses),
    };
  })();

  // Group county data for grouped bar
  const countyGrouped = (() => {
    const map: Record<string, Record<string,number>> = {};
    const statuses = new Set<string>();
    byCounty.forEach((r: any) => {
      if (!map[r.county]) map[r.county] = {};
      map[r.county][r.status] = r.count;
      statuses.add(r.status);
    });
    return {
      rows: Object.entries(map).map(([county, vals]) => ({ county, ...vals, _total: Object.values(vals).reduce((s, n) => s + n, 0) }))
        .sort((a, b) => b._total - a._total).slice(0, 12),
      statuses: Array.from(statuses),
    };
  })();

  const dateLabel = `${dateFrom} – ${dateTo}`;

  return (
    <div>
      <div className="page-header">
        <h2>🏡 Regional MLS Market</h2>
        <p>Showing data for: <strong>{dateLabel}</strong></p>
      </div>

      {/* Filters */}
      <div className="filter-bar">
        <div className="filter-group">
          <label className="filter-label">Status</label>
          <select value={selStatus} onChange={e => setSelStatus(e.target.value)}>
            <option value="">All Statuses</option>
            {opts.statuses.map(s => <option key={s} value={s}>{s.replace(/_/g,' ')}</option>)}
          </select>
        </div>
        <div className="filter-group">
          <label className="filter-label">State</label>
          <select value={selState} onChange={e => setSelState(e.target.value)}>
            <option value="">All States</option>
            {opts.states.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="filter-group">
          <label className="filter-label">County</label>
          <select value={selCounty} onChange={e => setSelCounty(e.target.value)}>
            <option value="">All Counties</option>
            {opts.counties.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div className="filter-group">
          <label className="filter-label">From</label>
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
        </div>
        <div className="filter-group">
          <label className="filter-label">To</label>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} />
        </div>
        <button className="btn btn-primary" onClick={load} style={{ alignSelf: 'flex-end' }}>
          <RefreshCw size={14} /> Apply
        </button>
      </div>

      {loading ? <Spinner /> : (
        <>
          {/* KPI Cards */}
          <div className="kpi-grid">
            <KpiCard title="Total Listings"    value={kpis?.total_listings?.toLocaleString() ?? '—'} accent="var(--accent-green)" />
            <KpiCard title="Active (For Sale)" value={kpis?.active_count?.toLocaleString() ?? '—'} accent="var(--accent-blue)" />
            <KpiCard title="Under Contract"    value={kpis?.under_contract_count?.toLocaleString() ?? '—'} accent="var(--accent-orange)" />
            <KpiCard title="Avg List Price"    value={kpis?.avg_list_price != null ? `$${Math.round(kpis.avg_list_price).toLocaleString()}` : '—'} accent="var(--accent-purple)" />
            <KpiCard title="Status Changed"    value={kpis?.status_changed_count?.toLocaleString() ?? '—'} accent="var(--accent-red)" />
          </div>

          {/* Map + Pie */}
          <div className="two-col" style={{ marginBottom: 20 }}>
            <div className="card">
              <div className="card-title">📍 Property Map</div>
              {listings.filter(l => l.latitude && l.longitude).length > 0
                ? <RealEstateMap listings={listings} height={440} />
                : <EmptyState message="No properties with coordinates" />}
            </div>
            <div className="card">
              <div className="card-title">📊 Market Breakdown</div>
              {/* County bar */}
              {byCounty.length > 0 && (() => {
                const top = (() => {
                  const cnt: Record<string,number> = {};
                  byCounty.forEach((r: any) => { cnt[r.county] = (cnt[r.county] ?? 0) + r.count; });
                  return Object.entries(cnt).sort(([,a],[,b]) => b - a).slice(0, 10).map(([county, count]) => ({ county, count }));
                })();
                return (
                  <ResponsiveContainer width="100%" height={210}>
                    <BarChart data={top} layout="vertical" margin={{ left: 10 }}>
                      <XAxis type="number" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} />
                      <YAxis type="category" dataKey="county" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} width={100} />
                      <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}
                               labelStyle={{ color: 'var(--text-primary)' }} />
                      <Bar dataKey="count" name="Listings" fill="var(--accent-blue)" radius={[0,4,4,0]} />
                    </BarChart>
                  </ResponsiveContainer>
                );
              })()}
              {/* Status pie */}
              {kpis && (() => {
                const data = [
                  { name: 'For Sale',       value: kpis.active_count },
                  { name: 'Under Contract', value: kpis.under_contract_count },
                  { name: 'Other',          value: Math.max(0, kpis.total_listings - kpis.active_count - kpis.under_contract_count) },
                ].filter(d => d.value > 0);
                return (
                  <ResponsiveContainer width="100%" height={200}>
                    <PieChart>
                      <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%"
                           innerRadius={50} outerRadius={80} paddingAngle={2}>
                        <Cell fill="#4CAF50" />
                        <Cell fill="#FF9800" />
                        <Cell fill="#8B92A5" />
                      </Pie>
                      <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}
                               labelStyle={{ color: 'var(--text-primary)' }} />
                      <Legend wrapperStyle={{ color: 'var(--text-secondary)', fontSize: 11 }} />
                    </PieChart>
                  </ResponsiveContainer>
                );
              })()}
            </div>
          </div>

          {/* Monthly Stats Tabs */}
          <div className="card">
            <div className="card-title">📅 Monthly Statistics</div>
            <Tabs
              tabs={['📈 Listings Over Time', '🏘️ County Breakdown', '🤝 Top Realtors']}
              active={tab}
              onChange={setTab}
            />

            {tab === 0 && (
              weeklyGrouped.rows.length > 0 ? (
                <ResponsiveContainer width="100%" height={340}>
                  <BarChart data={weeklyGrouped.rows} margin={{ top: 0, right: 20, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="week" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                    <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                    <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}
                             labelStyle={{ color: 'var(--text-primary)' }} />
                    <Legend wrapperStyle={{ color: 'var(--text-secondary)', fontSize: 12 }} />
                    {weeklyGrouped.statuses.map((s, i) => (
                      <Bar key={s} dataKey={s} stackId="a" fill={STATUS_COLORS[s] ?? COLORS[i]} name={s.replace(/_/g,' ')} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              ) : <EmptyState message="No data in selected date range" />
            )}

            {tab === 1 && (
              countyGrouped.rows.length > 0 ? (
                <>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={countyGrouped.rows} margin={{ top: 0, right: 20, bottom: 40, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                      <XAxis dataKey="county" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} angle={-25} textAnchor="end" />
                      <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                      <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}
                               labelStyle={{ color: 'var(--text-primary)' }} />
                      <Legend wrapperStyle={{ color: 'var(--text-secondary)', fontSize: 12 }} />
                      {countyGrouped.statuses.map((s, i) => (
                        <Bar key={s} dataKey={s} fill={STATUS_COLORS[s] ?? COLORS[i]} name={s.replace(/_/g,' ')} />
                      ))}
                    </BarChart>
                  </ResponsiveContainer>
                  {/* Price by county */}
                  <div style={{ marginTop: 16, fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
                    Avg List Price by County
                  </div>
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={priceCtx.slice(0, 12)} margin={{ top: 0, right: 20, bottom: 40, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                      <XAxis dataKey="county" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} angle={-25} textAnchor="end" />
                      <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} tickFormatter={v => `$${(v/1000).toFixed(0)}k`} />
                      <Tooltip formatter={(v: any) => `$${v?.toLocaleString()}`}
                               contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}
                               labelStyle={{ color: 'var(--text-primary)' }} />
                      <Bar dataKey="avg_price" name="Avg Price" fill="var(--accent-purple)" radius={[4,4,0,0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </>
              ) : <EmptyState />
            )}

            {tab === 2 && (
              realtors.length > 0 ? (
                <div className="table-wrapper">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Realtor</th><th>Listings</th><th>Avg Price</th>
                        <th>Phone</th><th>Email</th>
                      </tr>
                    </thead>
                    <tbody>
                      {realtors.map((r: any, i: number) => (
                        <tr key={i}>
                          <td><strong>{r.realtor_name}</strong></td>
                          <td>{r.listings}</td>
                          <td>{r.avg_price != null ? `$${Math.round(r.avg_price).toLocaleString()}` : '—'}</td>
                          <td>{r.phone ?? '—'}</td>
                          <td>{r.email ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <EmptyState message="No realtor data available in this date range" />
            )}
          </div>

          {/* Status Transitions */}
          {transitions.length > 0 && (
            <div className="card">
              <div className="card-title">🔄 Recently Changed Listings</div>
              <div className="equal-col">
                <div>
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={transitions} layout="vertical" margin={{ left: 20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                      <XAxis type="number" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                      <YAxis type="category" dataKey="transition" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} width={140} />
                      <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}
                               labelStyle={{ color: 'var(--text-primary)' }} />
                      <Bar dataKey="count" name="Count" fill="var(--accent-red)" radius={[0,4,4,0]}>
                        {transitions.map((_: any, i: number) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div style={{ color: 'var(--text-secondary)', fontSize: 12, paddingTop: 8 }}>
                  {transitions.map((t: any, i: number) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                      <span>{t.transition}</span>
                      <strong style={{ color: 'var(--text-primary)' }}>{t.count}</strong>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Raw Data */}
          <div className="card">
            <div className="card-title">📋 Raw Data Explorer</div>
            {listings.length > 0 ? (
              <div className="table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Address</th><th>City</th><th>County</th><th>ZIP</th>
                      <th>Status</th><th>Price</th><th>Beds</th><th>Baths</th><th>SQFT</th>
                    </tr>
                  </thead>
                  <tbody>
                    {listings.slice(0, 300).map((l: any, i: number) => (
                      <tr key={i}>
                        <td>{l.address}</td>
                        <td>{l.city}</td>
                        <td>{l.county}</td>
                        <td>{l.zip_code}</td>
                        <td><StatusBadge status={l.status} /></td>
                        <td>{l.list_price != null ? `$${Number(l.list_price).toLocaleString()}` : '—'}</td>
                        <td>{l.bedrooms ?? '—'}</td>
                        <td>{l.bathrooms ?? '—'}</td>
                        <td>{l.sqft ? Number(l.sqft).toLocaleString() : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <EmptyState />}
          </div>
        </>
      )}
    </div>
  );
}
