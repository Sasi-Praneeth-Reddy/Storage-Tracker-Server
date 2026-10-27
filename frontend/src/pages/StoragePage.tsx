/**
 * StoragePage.tsx  — Self-Storage Market dashboard
 * Uses Recharts for charts + Leaflet for maps (no API key required)
 */
import { useState, useEffect, useCallback } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend, PieChart, Pie, Cell, CartesianGrid,
} from 'recharts';
import { RefreshCw, StopCircle, PlayCircle } from 'lucide-react';
import { storage } from '../api';
import { KpiCard, Spinner, EmptyState, Tabs } from '../components/Shared';
import StorageMap from '../components/StorageMap';
import { format } from 'date-fns';

const COLORS = ['#2196F3','#4CAF50','#FF9800','#F44336','#9C27B0','#00BCD4','#FFC107','#E91E63'];

const today = format(new Date(), 'yyyy-MM-dd');
const monthStart = format(new Date(new Date().getFullYear(), new Date().getMonth(), 1), 'yyyy-MM-dd');

export default function StoragePage() {
  const [brands,     setBrands]     = useState<string[]>([]);
  const [unitSizes,  setUnitSizes]  = useState<string[]>([]);
  const [selBrands,  setSelBrands]  = useState<string>('');
  const [selSize,    setSelSize]    = useState<string>('');
  const [dateFrom,   setDateFrom]   = useState(monthStart);
  const [dateTo,     setDateTo]     = useState(today);
  const [kpis,       setKpis]       = useState<any>(null);
  const [facilities, setFacilities] = useState<any[]>([]);
  const [priceHist,  setPriceHist]  = useState<any[]>([]);
  const [mktShare,   setMktShare]   = useState<any[]>([]);
  const [movement,   setMovement]   = useState<any[]>([]);
  const [loading,    setLoading]    = useState(true);
  const [tab,        setTab]        = useState(0);
  const [scraperRunning, setScraperRunning] = useState(false);

  // Load static options once
  useEffect(() => {
    Promise.all([storage.getBrands(), storage.getUnitSizes()]).then(([b, s]) => {
      setBrands(b);
      setUnitSizes(s);
      if (s.length) setSelSize(s.find((x: string) => x === '10x10') ?? s[0]);
    });
    // Check scraper status
    storage.scraperStatus().then(d => setScraperRunning(d.running)).catch(() => {});
  }, []);

  const params = useCallback(() => {
    const p: Record<string,string> = { date_from: dateFrom, date_to: dateTo };
    if (selBrands) p.brand = selBrands;
    if (selSize)   p.unit_size = selSize;
    return p;
  }, [selBrands, selSize, dateFrom, dateTo]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = params();
      const [k, f, ph, ms, mv] = await Promise.all([
        storage.getKpis(p),
        storage.getFacilities(p),
        storage.getPriceHistory(p),
        storage.getMarketShare(p),
        storage.getPriceMovement(p),
      ]);
      setKpis(k); setFacilities(f); setPriceHist(ph); setMktShare(ms); setMovement(mv);
    } finally {
      setLoading(false);
    }
  }, [params]);

  useEffect(() => { if (selSize) load(); }, [selSize, selBrands, dateFrom, dateTo]);

  // ── Scraper controls ────────────────────────
  const startScraper = async () => {
    await storage.scraperStart();
    setScraperRunning(true);
  };
  const stopScraper = async () => {
    await storage.scraperStop();
    setScraperRunning(false);
  };

  // ── Chart data processing ────────────────────
  // Price trend: group by date+brand for line chart
  const trendData = (() => {
    const byDate: Record<string, Record<string, number>> = {};
    const allBrands = new Set<string>();
    priceHist.forEach((r: any) => {
      if (!byDate[r.snap_date]) byDate[r.snap_date] = {};
      byDate[r.snap_date][r.brand] = r.avg_rate;
      allBrands.add(r.brand);
    });
    return {
      rows: Object.entries(byDate).sort(([a],[b]) => a.localeCompare(b)).map(([date, vals]) => ({ date, ...vals })),
      brands: Array.from(allBrands),
    };
  })();

  const brandPrices = (() => {
    const byBrand: Record<string, { total: number; count: number }> = {};
    facilities.forEach((f: any) => {
      if (f.web_rate == null) return;
      if (!byBrand[f.brand]) byBrand[f.brand] = { total: 0, count: 0 };
      byBrand[f.brand].total += f.web_rate;
      byBrand[f.brand].count += 1;
    });
    return Object.entries(byBrand).map(([brand, v]) => ({ brand, avg_rate: v.total / v.count }))
      .sort((a, b) => b.avg_rate - a.avg_rate);
  })();

  const pricingFacilities = facilities.filter((f: any) => f.unit_size === selSize);
  const rateValues = pricingFacilities.map((f: any) => f.web_rate).filter((v: any) => v != null);
  const histBins = (() => {
    if (!rateValues.length) return [];
    const min = Math.min(...rateValues), max = Math.max(...rateValues);
    const step = Math.ceil((max - min) / 15) || 10;
    const bins: Record<string, number> = {};
    rateValues.forEach((v: number) => {
      const bucket = `$${Math.floor(v / step) * step}`;
      bins[bucket] = (bins[bucket] || 0) + 1;
    });
    return Object.entries(bins).map(([range, count]) => ({ range, count }));
  })();

  return (
    <div>
      <div className="page-header">
        <h2>📦 Self-Storage Market Tracker</h2>
        <p>Pricing intelligence across Northern Virginia · DC · Maryland</p>
      </div>

      {/* Scraper banner */}
      {scraperRunning ? (
        <div className="scraper-banner">
          <span>🕵️ Scraper is currently running in the background</span>
          <button className="btn btn-danger" style={{ marginLeft: 'auto' }} onClick={stopScraper}>
            <StopCircle size={14} /> Stop
          </button>
          <button className="btn btn-ghost" onClick={load}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      ) : (
        <div style={{ marginBottom: 16 }}>
          <button className="btn btn-success" onClick={startScraper}>
            <PlayCircle size={14} /> Run Storage Scraper
          </button>
        </div>
      )}

      {/* Filters */}
      <div className="filter-bar">
        <div className="filter-group">
          <label className="filter-label">Unit Size</label>
          <select value={selSize} onChange={e => setSelSize(e.target.value)}>
            {unitSizes.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div className="filter-group">
          <label className="filter-label">Brand</label>
          <select value={selBrands} onChange={e => setSelBrands(e.target.value)}>
            <option value="">All Brands</option>
            {brands.map(b => <option key={b} value={b}>{b}</option>)}
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

      {/* KPI Cards */}
      {loading ? <Spinner /> : (
        <>
          <div className="kpi-grid">
            <KpiCard title="Tracked Facilities"    value={kpis?.total_facilities?.toLocaleString() ?? '—'} accent="var(--accent-pink)" />
            <KpiCard title={`Avg ${selSize} Rate`} value={kpis?.avg_rate != null ? `$${kpis.avg_rate.toFixed(2)}` : '—'} accent="var(--accent-cyan)" />
            <KpiCard title="Dominant Brand"        value={kpis?.dominant_brand ?? '—'} accent="var(--accent-yellow)" small />
            <KpiCard title={`Available (${selSize})`} value={kpis?.available_count?.toLocaleString() ?? '—'} accent="var(--accent-green)" />
          </div>

          {/* Map + Brand Pricing */}
          <div className="two-col" style={{ marginBottom: 20 }}>
            <div className="card">
              <div className="card-title">📍 Facilities Map</div>
              {pricingFacilities.length > 0
                ? <StorageMap facilities={pricingFacilities} selectedSize={selSize} height={440} />
                : <EmptyState message="No facilities mapped yet" />}
            </div>
            <div className="card">
              <div className="card-title">📈 Avg Price by Brand ({selSize})</div>
              {brandPrices.length > 0 ? (
                <ResponsiveContainer width="100%" height={400}>
                  <BarChart data={brandPrices} layout="vertical" margin={{ left: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis type="number" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }}
                           tickFormatter={v => `$${v}`} />
                    <YAxis type="category" dataKey="brand" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} width={110} />
                    <Tooltip formatter={(v: any) => `$${v.toFixed(2)}`}
                             contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}
                             labelStyle={{ color: 'var(--text-primary)' }} />
                    <Bar dataKey="avg_rate" name="Avg Rate" radius={[0,4,4,0]}>
                      {brandPrices.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : <EmptyState />}
            </div>
          </div>

          {/* Monthly Stats Tabs */}
          <div className="card">
            <div className="card-title">📅 Monthly Statistics</div>
            <Tabs
              tabs={['📈 Price Trends by Brand', '📊 Price Movement vs Prev Period', '🥧 Market Share']}
              active={tab}
              onChange={setTab}
            />

            {tab === 0 && (
              trendData.rows.length > 0 ? (
                <ResponsiveContainer width="100%" height={360}>
                  <LineChart data={trendData.rows} margin={{ top: 0, right: 20, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                    <XAxis dataKey="date" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                    <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} tickFormatter={v => `$${v}`} />
                    <Tooltip formatter={(v: any) => `$${v?.toFixed(2)}`}
                             contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}
                             labelStyle={{ color: 'var(--text-primary)' }} />
                    <Legend wrapperStyle={{ color: 'var(--text-secondary)', fontSize: 12 }} />
                    {trendData.brands.map((brand, i) => (
                      <Line key={brand} type="monotone" dataKey={brand}
                            stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={false} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              ) : <EmptyState message="No trend data for this date range" />
            )}

            {tab === 1 && (
              movement.length > 0 ? (
                <div className="table-wrapper">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Unit Size</th><th>This Period</th><th>Prev Period</th>
                        <th>Change ($)</th><th>Change (%)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {movement.map((r: any) => (
                        <tr key={r.unit_size}>
                          <td><strong>{r.unit_size}</strong></td>
                          <td>${r.this_period?.toFixed(2) ?? '—'}</td>
                          <td>${r.prev_period?.toFixed(2) ?? '—'}</td>
                          <td style={{ color: r.change_dollar >= 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}>
                            {r.change_dollar >= 0 ? '+' : ''}${r.change_dollar?.toFixed(2) ?? '—'}
                          </td>
                          <td style={{ color: r.change_pct >= 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}>
                            {r.change_pct >= 0 ? '+' : ''}{r.change_pct?.toFixed(1) ?? '—'}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <EmptyState message="Select a date range with at least two periods of data" />
            )}

            {tab === 2 && (
              <div className="equal-col">
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Rate Distribution ({selSize})</div>
                  {histBins.length > 0 ? (
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={histBins}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                        <XAxis dataKey="range" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} />
                        <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                        <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}
                                 labelStyle={{ color: 'var(--text-primary)' }} />
                        <Bar dataKey="count" name="Facilities" fill="var(--accent-cyan)" radius={[4,4,0,0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : <EmptyState />}
                </div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Facility Ownership by Brand</div>
                  {mktShare.length > 0 ? (
                    <ResponsiveContainer width="100%" height={300}>
                      <PieChart>
                        <Pie data={mktShare} dataKey="count" nameKey="brand" cx="50%" cy="50%"
                             innerRadius={60} outerRadius={100} paddingAngle={2}>
                          {mktShare.map((_: any, i: number) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                        </Pie>
                        <Tooltip contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8 }}
                                 labelStyle={{ color: 'var(--text-primary)' }} />
                        <Legend wrapperStyle={{ color: 'var(--text-secondary)', fontSize: 11 }} />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : <EmptyState />}
                </div>
              </div>
            )}
          </div>

          {/* Data Table */}
          <div className="card">
            <div className="card-title">📋 Storage Data Explorer</div>
            {pricingFacilities.length > 0 ? (
              <div className="table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Facility</th><th>Brand</th><th>City</th><th>ZIP</th>
                      <th>Unit Size</th><th>Rate/mo</th><th>Availability</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pricingFacilities.slice(0, 200).map((f: any, i: number) => (
                      <tr key={i}>
                        <td>{f.name}</td>
                        <td>{f.brand}</td>
                        <td>{f.city}</td>
                        <td>{f.zip_code}</td>
                        <td>{f.unit_size}</td>
                        <td>{f.web_rate != null ? `$${f.web_rate.toFixed(0)}` : '—'}</td>
                        <td>
                          <span className={`badge ${f.availability === 'Available' ? 'badge-green' : 'badge-gray'}`}>
                            {f.availability ?? 'Unknown'}
                          </span>
                        </td>
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
