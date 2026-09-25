/**
 * DatabasePage.tsx — Raw database explorer with search
 */
import { useState, useEffect } from 'react';
import { Search } from 'lucide-react';
import { database } from '../api';
import { Spinner, EmptyState } from '../components/Shared';

export default function DatabasePage() {
  const [rows,    setRows]    = useState<any[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [search,  setSearch]  = useState('');
  const [loading, setLoading] = useState(true);
  const [debounced, setDebounced] = useState('');

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 400);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    setLoading(true);
    const p: Record<string,string> = {};
    if (debounced) p.search = debounced;
    database.getPreMoverLeads(p)
      .then(data => {
        setRows(data);
        if (data.length > 0) setColumns(Object.keys(data[0]));
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [debounced]);

  return (
    <div>
      <div className="page-header">
        <h2>🗄️ Raw Database Explorer</h2>
        <p>Browse and search the <code>pre_mover_leads</code> table</p>
      </div>

      <div style={{ position: 'relative', marginBottom: 16 }}>
        <Search size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-secondary)' }} />
        <input
          className="search-input"
          style={{ paddingLeft: 34 }}
          placeholder="Search zip code, address, status, name…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      {loading ? <Spinner /> : (
        <div className="card">
          <div className="card-title">
            {rows.length.toLocaleString()} rows
            {debounced && <span style={{ color: 'var(--text-secondary)', fontWeight: 400, fontSize: 12 }}> matching "{debounced}"</span>}
          </div>
          {rows.length === 0 ? (
            <EmptyState message="No records match your search" />
          ) : (
            <div className="table-wrapper" style={{ maxHeight: 700 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    {columns.map(c => (
                      <th key={c}>{c.replace(/_/g, ' ')}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => (
                    <tr key={i}>
                      {columns.map(c => (
                        <td key={c} style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {row[c] != null ? String(row[c]) : '—'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
