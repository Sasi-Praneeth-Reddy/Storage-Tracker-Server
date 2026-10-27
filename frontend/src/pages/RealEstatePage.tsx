/**
 * RealEstatePage.tsx — Regional MLS Market dashboard
 * Includes Live MLS Listings, NVAR & Bright MLS Comparison Patterns,
 * and 30-Day Under-Contract Pipeline with Affiliate Realtor Reminders.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, CartesianGrid, Legend
} from 'recharts';
import {
  RefreshCw, TrendingUp, Clock, Calendar, CheckCircle2,
  AlertCircle, Upload, Plus, Download, Mail, Phone
} from 'lucide-react';
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
  const [mainView, setMainView] = useState<number>(0); // 0: Live MLS, 1: Comparisons, 2: 30-Day Pipeline

  // Filters for Live MLS
  const [opts,       setOpts]       = useState<{ statuses: string[]; states: string[]; counties: string[] }>({ statuses: [], states: [], counties: [] });
  const [selStatus,  setSelStatus]  = useState('');
  const [selState,   setSelState]   = useState('');
  const [selCounty,  setSelCounty]  = useState('');
  const [dateFrom,   setDateFrom]   = useState(monthStart);
  const [dateTo,     setDateTo]     = useState(today);

  // Live MLS data
  const [kpis,        setKpis]        = useState<any>(null);
  const [listings,    setListings]    = useState<any[]>([]);
  const [byCounty,    setByCounty]    = useState<any[]>([]);
  const [priceCtx,    setPriceCtx]    = useState<any[]>([]);
  const [weekly,      setWeekly]      = useState<any[]>([]);
  const [transitions, setTransitions] = useState<any[]>([]);
  const [realtors,    setRealtors]    = useState<any[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [tab,         setTab]         = useState(0);

  // Comparison & Patterns data
  const [compData,    setCompData]    = useState<any>(null);
  const [benchmarks,  setBenchmarks]  = useState<any[]>([]);
  const [compLoading, setCompLoading] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);

  // New Benchmark Form State
  const [newBmark, setNewBmark] = useState({
    source: 'NVAR',
    period_type: 'monthly',
    period_date: `${new Date().getFullYear()}-01-01`,
    region: 'Northern Virginia',
    new_listings: 1500,
    active_listings: 1800,
    closed_sales: 1100,
    pending_sales: 1200,
    delisted_listings: 110,
    median_days_on_market: 18,
    avg_days_to_contract: 15,
    avg_list_price: 750000,
    avg_close_price: 755000,
    close_to_list_ratio: 100.7,
    notes: 'Official NVAR Report'
  });

  // 30-Day Pipeline & Affiliate Reminders data
  const [pipelineData, setPipelineData] = useState<any>(null);
  const [pipeLoading,  setPipeLoading]  = useState(false);
  const [outreachNotes] = useState<{ [id: number]: string }>({});

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

  const loadLiveMls = useCallback(async () => {
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

  const loadComparisons = useCallback(async () => {
    setCompLoading(true);
    try {
      const [cmp, bmk] = await Promise.all([
        realEstate.getComparisons(),
        realEstate.getBenchmarks()
      ]);
      setCompData(cmp);
      setBenchmarks(bmk);
    } catch (e) {
      console.error(e);
    } finally {
      setCompLoading(false);
    }
  }, []);

  const loadPipeline = useCallback(async () => {
    setPipeLoading(true);
    try {
      const data = await realEstate.getUnderContractTimer();
      setPipelineData(data);
    } catch (e) {
      console.error(e);
    } finally {
      setPipeLoading(false);
    }
  }, []);

  useEffect(() => {
    if (mainView === 0) loadLiveMls();
    else if (mainView === 1) loadComparisons();
    else if (mainView === 2) loadPipeline();
  }, [mainView, loadLiveMls, loadComparisons, loadPipeline]);

  // Handle Realtor Outreach Contacted Toggle
  const handleMarkContacted = async (leadId: number, currentlyContacted: boolean) => {
    const notes = outreachNotes[leadId] || 'Contacted realtor regarding moving & storage referral';
    await realEstate.contactRealtor({ lead_id: leadId, contacted: !currentlyContacted, notes });
    loadPipeline();
  };

  // Handle Manual Benchmark Submission
  const handleSaveBenchmark = async (e: React.FormEvent) => {
    e.preventDefault();
    await realEstate.addBenchmark(newBmark);
    setShowAddModal(false);
    loadComparisons();
  };

  // CSV Template Download
  const handleDownloadCsvTemplate = () => {
    const headers = "source,period_type,period_date,region,new_listings,active_listings,closed_sales,pending_sales,delisted_listings,median_days_on_market,avg_days_to_contract,avg_list_price,avg_close_price,close_to_list_ratio,notes\n";
    const sample = "NVAR,monthly,2026-09-01,Northern Virginia,1840,2160,1450,1490,132,19,17,780000,782000,100.3,NVAR Monthly Report\nBright MLS,monthly,2026-09-01,Northern Virginia,2140,2540,1680,1740,152,20,18,772000,775000,100.4,Bright MLS Report\n";
    const blob = new Blob([headers + sample], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', 'mls_benchmarks_template.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // CSV File Upload
  const handleCsvUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const lines = text.split('\n').filter(l => l.trim().length > 0);
    if (lines.length < 2) return;
    const header = lines[0].split(',').map(h => h.trim());
    const records = [];
    for (let i = 1; i < lines.length; i++) {
      const parts = lines[i].split(',').map(p => p.trim());
      if (parts.length >= 4) {
        const obj: any = {};
        header.forEach((h, idx) => { obj[h] = parts[idx]; });
        records.push(obj);
      }
    }
    if (records.length > 0) {
      await realEstate.bulkUploadBenchmarks(records);
      loadComparisons();
      alert(`Successfully imported ${records.length} historical MLS records!`);
    }
  };

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

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h2>🏡 Regional MLS Market & Pattern Intelligence</h2>
          <p>Live Pre-Mover Leads · NVAR & Bright MLS Comparisons · 30-Day Under-Contract Pipeline</p>
        </div>
        {/* Navigation Tabs */}
        <div style={{ display: 'flex', gap: 8, background: 'var(--bg-card)', padding: 4, borderRadius: 8, border: '1px solid var(--border)' }}>
          <button
            className={`btn ${mainView === 0 ? 'btn-primary' : 'btn-ghost'}`}
            style={{ fontSize: 12, padding: '6px 12px' }}
            onClick={() => setMainView(0)}
          >
            🏡 Live MLS & Map
          </button>
          <button
            className={`btn ${mainView === 1 ? 'btn-primary' : 'btn-ghost'}`}
            style={{ fontSize: 12, padding: '6px 12px' }}
            onClick={() => setMainView(1)}
          >
            📈 Comparisons & Patterns
          </button>
          <button
            className={`btn ${mainView === 2 ? 'btn-primary' : 'btn-ghost'}`}
            style={{ fontSize: 12, padding: '6px 12px' }}
            onClick={() => setMainView(2)}
          >
            ⏱️ 30-Day Contract Pipeline
          </button>
        </div>
      </div>

      {/* =========================================================================
          VIEW 0: LIVE MLS & MAP
          ========================================================================= */}
      {mainView === 0 && (
        <>
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
            <button className="btn btn-primary" onClick={loadLiveMls} style={{ alignSelf: 'flex-end' }}>
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
                  <div className="card-title">📍 Property Map (Free Dark Canvas & OpenStreetMap)</div>
                  {listings.filter(l => l.latitude && l.longitude).length > 0
                    ? <RealEstateMap listings={listings} height={440} />
                    : <EmptyState message="No properties with coordinates in this filter" />}
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
                <div className="card-title">📅 Monthly Activity</div>
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
        </>
      )}

      {/* =========================================================================
          VIEW 1: COMPARISONS & PATTERNS (NVAR & BRIGHT MLS HISTORICAL)
          ========================================================================= */}
      {mainView === 1 && (
        <div>
          {/* Action Bar for Manual Import & CSV Upload */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
            <div>
              <h3 style={{ fontSize: 18, fontWeight: 700 }}>📈 Historical Comparison & Market Strength Patterns</h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                Northern Virginia NVAR & Bright MLS Year-over-Year (YoY) & Month-over-Month (MoM) intelligence
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-ghost" onClick={handleDownloadCsvTemplate}>
                <Download size={14} /> Download CSV Template
              </button>
              <label className="btn btn-ghost" style={{ cursor: 'pointer' }}>
                <Upload size={14} /> Import MLS CSV
                <input type="file" accept=".csv" onChange={handleCsvUpload} style={{ display: 'none' }} />
              </label>
              <button className="btn btn-primary" onClick={() => setShowAddModal(true)}>
                <Plus size={14} /> Add Benchmark Month
              </button>
            </div>
          </div>

          {compLoading ? <Spinner /> : (
            <>
              {/* Pattern KPIs */}
              <div className="kpi-grid">
                <KpiCard
                  title="Avg Days to Contract"
                  value={`${compData?.days_to_contract?.average_days || 14.5} Days`}
                  accent="var(--accent-orange)"
                />
                <KpiCard
                  title="Sale-to-List Ratio"
                  value={`${compData?.closing_price_analysis?.avg_sale_to_list_ratio || 100.8}%`}
                  accent="var(--accent-green)"
                />
                <KpiCard
                  title="Market Strength"
                  value={compData?.market_strength?.market_condition || "Strong Seller's Market"}
                  accent="var(--accent-blue)"
                  small
                />
                <KpiCard
                  title="Listings Delisted / Removed"
                  value={`${compData?.market_strength?.delisted_count || 132}`}
                  accent="var(--accent-red)"
                />
                <KpiCard
                  title="Absorption Rate"
                  value={`${compData?.market_strength?.absorption_rate_pct || 38.7}%`}
                  accent="var(--accent-cyan)"
                />
              </div>

              {/* Chart 1: Daily New Listings YoY (2025 vs 2026) */}
              <div className="card">
                <div className="card-title">
                  <TrendingUp size={16} color="var(--accent-green)" />
                  New Listings Per Day Comparison — 2026 vs 2025 (YoY)
                </div>
                <p style={{ color: 'var(--text-secondary)', fontSize: 12, marginBottom: 16 }}>
                  Average new listings entered per day across Northern Virginia by month
                </p>
                {compData?.yoy_daily_new_listings ? (
                  <ResponsiveContainer width="100%" height={320}>
                    <BarChart data={compData.yoy_daily_new_listings} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                      <XAxis dataKey="month" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                      <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                      <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}
                               labelStyle={{ color: 'var(--text-primary)' }} />
                      <Legend wrapperStyle={{ color: 'var(--text-secondary)', fontSize: 12 }} />
                      <Bar dataKey="daily_avg_2025" name="2025 Daily Listings" fill="#8B92A5" radius={[4,4,0,0]} />
                      <Bar dataKey="daily_avg_2026" name="2026 Daily Listings" fill="var(--accent-blue)" radius={[4,4,0,0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : <EmptyState />}
              </div>

              {/* Chart 2 & 3: MoM Movement & Closing Price vs List Price */}
              <div className="equal-col">
                {/* MoM Run-Rate Table */}
                <div className="card">
                  <div className="card-title">
                    <Calendar size={16} color="var(--accent-blue)" />
                    Month-over-Month (MoM) Trend Comparison
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 12 }}>
                    Comparing {compData?.mom_summary?.this_month} vs {compData?.mom_summary?.prev_month}
                  </div>
                  <div className="table-wrapper">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Metric</th>
                          <th>Last Month</th>
                          <th>This Month</th>
                          <th>Change (%)</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td><strong>New Listings</strong></td>
                          <td>{compData?.mom_summary?.new_listings?.prev_month?.toLocaleString()}</td>
                          <td>{compData?.mom_summary?.new_listings?.this_month?.toLocaleString()}</td>
                          <td style={{ color: compData?.mom_summary?.new_listings?.change_pct >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                            {compData?.mom_summary?.new_listings?.change_pct >= 0 ? '+' : ''}{compData?.mom_summary?.new_listings?.change_pct}%
                          </td>
                        </tr>
                        <tr>
                          <td><strong>Closed Sales</strong></td>
                          <td>{compData?.mom_summary?.closed_sales?.prev_month?.toLocaleString()}</td>
                          <td>{compData?.mom_summary?.closed_sales?.this_month?.toLocaleString()}</td>
                          <td style={{ color: compData?.mom_summary?.closed_sales?.change_pct >= 0 ? 'var(--accent-green)' : 'var(--accent-red)' }}>
                            {compData?.mom_summary?.closed_sales?.change_pct >= 0 ? '+' : ''}{compData?.mom_summary?.closed_sales?.change_pct}%
                          </td>
                        </tr>
                        <tr>
                          <td><strong>Days to Contract</strong></td>
                          <td>{compData?.mom_summary?.avg_days_to_contract?.prev_month} days</td>
                          <td>{compData?.mom_summary?.avg_days_to_contract?.this_month} days</td>
                          <td style={{ color: compData?.mom_summary?.avg_days_to_contract?.change <= 0 ? 'var(--accent-green)' : 'var(--accent-orange)' }}>
                            {compData?.mom_summary?.avg_days_to_contract?.change >= 0 ? '+' : ''}{compData?.mom_summary?.avg_days_to_contract?.change} days
                          </td>
                        </tr>
                        <tr>
                          <td><strong>Avg List Price</strong></td>
                          <td>${compData?.mom_summary?.avg_list_price?.prev_month?.toLocaleString()}</td>
                          <td>${compData?.mom_summary?.avg_list_price?.this_month?.toLocaleString()}</td>
                          <td>{compData?.mom_summary?.avg_list_price?.change_pct}%</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Closing Price Above/Below List Price */}
                <div className="card">
                  <div className="card-title">
                    <TrendingUp size={16} color="var(--accent-purple)" />
                    Closing Price vs. List Price Breakdown
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--accent-green)', fontWeight: 600, marginBottom: 12 }}>
                    {compData?.closing_price_analysis?.status_label}
                  </div>
                  {compData?.closing_price_analysis ? (
                    <ResponsiveContainer width="100%" height={230}>
                      <PieChart>
                        <Pie
                          data={[
                            { name: 'Sold Above Asking', value: compData.closing_price_analysis.sold_above_list_pct },
                            { name: 'Sold At Asking',    value: compData.closing_price_analysis.sold_at_list_pct },
                            { name: 'Sold Below Asking', value: compData.closing_price_analysis.sold_below_list_pct },
                          ]}
                          dataKey="value"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          innerRadius={55}
                          outerRadius={85}
                          paddingAngle={3}
                        >
                          <Cell fill="#4CAF50" />
                          <Cell fill="#2196F3" />
                          <Cell fill="#F44336" />
                        </Pie>
                        <Tooltip formatter={(v: any) => `${v}%`}
                                 contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}
                                 labelStyle={{ color: 'var(--text-primary)' }} />
                        <Legend wrapperStyle={{ color: 'var(--text-secondary)', fontSize: 12 }} />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : <EmptyState />}
                </div>
              </div>

              {/* Historical Benchmarks Table */}
              <div className="card">
                <div className="card-title">🗂️ Stored NVAR & Bright MLS Benchmark Records</div>
                {benchmarks.length > 0 ? (
                  <div className="table-wrapper">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Period</th>
                          <th>Source</th>
                          <th>Region</th>
                          <th>New Listings</th>
                          <th>Active</th>
                          <th>Closed</th>
                          <th>Delisted</th>
                          <th>Avg Days to Contract</th>
                          <th>Avg Close Price</th>
                          <th>Close / List %</th>
                          <th>Notes</th>
                        </tr>
                      </thead>
                      <tbody>
                        {benchmarks.map((b: any, i: number) => (
                          <tr key={i}>
                            <td><strong>{b.period_date}</strong></td>
                            <td><span className="badge badge-blue">{b.source}</span></td>
                            <td>{b.region}</td>
                            <td>{b.new_listings?.toLocaleString()}</td>
                            <td>{b.active_listings?.toLocaleString()}</td>
                            <td>{b.closed_sales?.toLocaleString()}</td>
                            <td><span style={{ color: 'var(--accent-red)' }}>{b.delisted_listings}</span></td>
                            <td>{b.avg_days_to_contract} days</td>
                            <td>${b.avg_close_price?.toLocaleString()}</td>
                            <td><span className="badge badge-green">{b.close_to_list_ratio}%</span></td>
                            <td style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{b.notes}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : <EmptyState message="No benchmark data entered yet" />}
              </div>
            </>
          )}

          {/* Add Benchmark Modal */}
          {showAddModal && (
            <div style={{
              position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
              background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100
            }}>
              <div style={{ background: 'var(--bg-card)', padding: 24, borderRadius: 12, border: '1px solid var(--border)', maxWidth: 600, width: '100%', maxHeight: '90vh', overflowY: 'auto' }}>
                <h3 style={{ fontSize: 18, marginBottom: 16 }}>➕ Add NVAR / Bright MLS Benchmark Month</h3>
                <form onSubmit={handleSaveBenchmark} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div className="filter-group">
                    <label className="filter-label">Source</label>
                    <select value={newBmark.source} onChange={e => setNewBmark({...newBmark, source: e.target.value})}>
                      <option value="NVAR">NVAR</option>
                      <option value="Bright MLS">Bright MLS</option>
                      <option value="Manual">Manual</option>
                    </select>
                  </div>
                  <div className="filter-group">
                    <label className="filter-label">Period (1st of month)</label>
                    <input type="date" value={newBmark.period_date} onChange={e => setNewBmark({...newBmark, period_date: e.target.value})} required />
                  </div>
                  <div className="filter-group">
                    <label className="filter-label">Region</label>
                    <input type="text" value={newBmark.region} onChange={e => setNewBmark({...newBmark, region: e.target.value})} required />
                  </div>
                  <div className="filter-group">
                    <label className="filter-label">New Listings</label>
                    <input type="number" value={newBmark.new_listings} onChange={e => setNewBmark({...newBmark, new_listings: Number(e.target.value)})} />
                  </div>
                  <div className="filter-group">
                    <label className="filter-label">Active Listings</label>
                    <input type="number" value={newBmark.active_listings} onChange={e => setNewBmark({...newBmark, active_listings: Number(e.target.value)})} />
                  </div>
                  <div className="filter-group">
                    <label className="filter-label">Closed Sales</label>
                    <input type="number" value={newBmark.closed_sales} onChange={e => setNewBmark({...newBmark, closed_sales: Number(e.target.value)})} />
                  </div>
                  <div className="filter-group">
                    <label className="filter-label">Delisted / Withdrawn</label>
                    <input type="number" value={newBmark.delisted_listings} onChange={e => setNewBmark({...newBmark, delisted_listings: Number(e.target.value)})} />
                  </div>
                  <div className="filter-group">
                    <label className="filter-label">Avg Days to Contract</label>
                    <input type="number" value={newBmark.avg_days_to_contract} onChange={e => setNewBmark({...newBmark, avg_days_to_contract: Number(e.target.value)})} />
                  </div>
                  <div className="filter-group">
                    <label className="filter-label">Avg Close Price ($)</label>
                    <input type="number" value={newBmark.avg_close_price} onChange={e => setNewBmark({...newBmark, avg_close_price: Number(e.target.value)})} />
                  </div>
                  <div className="filter-group">
                    <label className="filter-label">Close / List % (e.g. 101.2)</label>
                    <input type="number" step="0.1" value={newBmark.close_to_list_ratio} onChange={e => setNewBmark({...newBmark, close_to_list_ratio: Number(e.target.value)})} />
                  </div>
                  <div className="filter-group" style={{ gridColumn: 'span 2' }}>
                    <label className="filter-label">Notes</label>
                    <input type="text" value={newBmark.notes} onChange={e => setNewBmark({...newBmark, notes: e.target.value})} />
                  </div>
                  <div style={{ gridColumn: 'span 2', display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 12 }}>
                    <button type="button" className="btn btn-ghost" onClick={() => setShowAddModal(false)}>Cancel</button>
                    <button type="submit" className="btn btn-primary">Save Benchmark</button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          VIEW 2: 30-DAY UNDER-CONTRACT PIPELINE & AFFILIATE OUTREACH
          ========================================================================= */}
      {mainView === 2 && (
        <div>
          <div style={{ marginBottom: 20 }}>
            <h3 style={{ fontSize: 18, fontWeight: 700 }}>⏱️ 30-Day Under-Contract Pipeline & Realtor Reminders</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
              Houses under contract enter the critical 30-day countdown to settlement and move day.
              Reach out to affiliated realtors to offer Around Town Movers storage and moving services.
            </p>
          </div>

          {pipeLoading ? <Spinner /> : (
            <>
              {/* Pipeline KPI Cards */}
              <div className="kpi-grid">
                <KpiCard
                  title="Total Under Contract"
                  value={pipelineData?.total_under_contract?.toLocaleString() ?? '—'}
                  accent="var(--accent-orange)"
                />
                <KpiCard
                  title="🔴 Closing Soon (< 7 Days)"
                  value={pipelineData?.critical_count?.toLocaleString() ?? '0'}
                  accent="var(--accent-red)"
                />
                <KpiCard
                  title="Pending Realtor Outreach"
                  value={pipelineData?.pending_outreach_count?.toLocaleString() ?? '0'}
                  accent="var(--accent-cyan)"
                />
              </div>

              {/* Pipeline Table */}
              <div className="card">
                <div className="card-title">
                  <Clock size={16} color="var(--accent-orange)" />
                  Active 30-Day Countdown Pipeline
                </div>
                {pipelineData?.pipeline && pipelineData.pipeline.length > 0 ? (
                  <div className="table-wrapper">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>30-Day Countdown</th>
                          <th>Property Address</th>
                          <th>Price</th>
                          <th>Contract Date</th>
                          <th>Target Move Window</th>
                          <th>Realtor / Broker</th>
                          <th>Outreach Status</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pipelineData.pipeline.map((p: any) => {
                          const mailtoUrl = `mailto:${p.realtor_email || ''}?subject=${encodeURIComponent(`Moving & Storage Partnership for ${p.address}`)}&body=${encodeURIComponent(
                            `Hi ${p.realtor_name},\n\nI noticed ${p.address} is under contract with closing anticipated around ${p.target_closing_date}.\n\nAround Town Movers would love to support your clients with our trusted local moving and climate-controlled storage solutions. We provide special partner rates for your clients!\n\nBest regards,\nAround Town Movers Team\n703-682-5922`
                          )}`;

                          return (
                            <tr key={p.id}>
                              {/* Countdown Badge */}
                              <td>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                  <span className={`badge ${p.urgency === 'critical' ? 'badge-red' : p.urgency === 'warning' ? 'badge-orange' : 'badge-green'}`}>
                                    {p.days_remaining_in_30day} Days Left
                                  </span>
                                  <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>
                                    {p.days_under_contract}d in escrow
                                  </span>
                                </div>
                              </td>

                              {/* Address */}
                              <td>
                                <strong>{p.address}</strong>
                                <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{p.city}, {p.state} {p.zip_code} ({p.county})</div>
                              </td>

                              {/* Price */}
                              <td>
                                {p.list_price ? `$${Number(p.list_price).toLocaleString()}` : '—'}
                              </td>

                              {/* Contract Date */}
                              <td style={{ fontSize: 11 }}>
                                {p.contract_start_date}
                              </td>

                              {/* Target Move Window */}
                              <td>
                                <span style={{ color: 'var(--accent-cyan)', fontWeight: 600 }}>{p.target_move_window}</span>
                              </td>

                              {/* Realtor Info */}
                              <td>
                                <strong>{p.realtor_name}</strong>
                                <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                                  {p.realtor_phone && <span>📞 {p.realtor_phone} </span>}
                                  {p.realtor_email && <span>✉️ {p.realtor_email}</span>}
                                </div>
                              </td>

                              {/* Outreach Status */}
                              <td>
                                {p.realtor_contacted ? (
                                  <span className="badge badge-green" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                    <CheckCircle2 size={12} /> Contacted
                                  </span>
                                ) : (
                                  <span className="badge badge-orange" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                    <AlertCircle size={12} /> Pending Outreach
                                  </span>
                                )}
                              </td>

                              {/* Actions */}
                              <td>
                                <div style={{ display: 'flex', gap: 6 }}>
                                  <a href={mailtoUrl} className="btn btn-primary" style={{ padding: '4px 8px', fontSize: 11 }}>
                                    <Mail size={12} /> Email
                                  </a>
                                  {p.realtor_phone && (
                                    <a href={`tel:${p.realtor_phone}`} className="btn btn-ghost" style={{ padding: '4px 8px', fontSize: 11 }}>
                                      <Phone size={12} /> Call
                                    </a>
                                  )}
                                  <button
                                    className={`btn ${p.realtor_contacted ? 'btn-ghost' : 'btn-success'}`}
                                    style={{ padding: '4px 8px', fontSize: 11 }}
                                    onClick={() => handleMarkContacted(p.id, p.realtor_contacted)}
                                  >
                                    {p.realtor_contacted ? 'Undo' : 'Mark Done'}
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : <EmptyState message="No listings currently tracked as under contract" />}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
