// Central API client — proxied to FastAPI at /api
import axios from 'axios';

const api = axios.create({ baseURL: '/api' });

// ── Storage ────────────────────────────────────────────────
export const storage = {
  getFacilities: (params?: Record<string, string>) =>
    api.get('/storage/facilities', { params }).then(r => r.data),

  getKpis: (params?: Record<string, string>) =>
    api.get('/storage/kpis', { params }).then(r => r.data),

  getPriceHistory: (params?: Record<string, string>) =>
    api.get('/storage/price-history', { params }).then(r => r.data),

  getMarketShare: (params?: Record<string, string>) =>
    api.get('/storage/market-share', { params }).then(r => r.data),

  getPriceMovement: (params?: Record<string, string>) =>
    api.get('/storage/price-movement', { params }).then(r => r.data),

  getBrands: () => api.get('/storage/brands').then(r => r.data),
  getUnitSizes: () => api.get('/storage/unit-sizes').then(r => r.data),

  scraperStatus: () => api.get('/storage/scraper/status').then(r => r.data),
  scraperStart:  () => api.post('/storage/scraper/start').then(r => r.data),
  scraperStop:   () => api.post('/storage/scraper/stop').then(r => r.data),
};

// ── Real Estate ────────────────────────────────────────────
export const realEstate = {
  getListings: (params?: Record<string, string>) =>
    api.get('/real-estate/listings', { params }).then(r => r.data),

  getKpis: (params?: Record<string, string>) =>
    api.get('/real-estate/kpis', { params }).then(r => r.data),

  getByCounty: (params?: Record<string, string>) =>
    api.get('/real-estate/by-county', { params }).then(r => r.data),

  getPriceByCounty: (params?: Record<string, string>) =>
    api.get('/real-estate/price-by-county', { params }).then(r => r.data),

  getWeeklyTrend: (params?: Record<string, string>) =>
    api.get('/real-estate/weekly-trend', { params }).then(r => r.data),

  getStatusTransitions: (params?: Record<string, string>) =>
    api.get('/real-estate/status-transitions', { params }).then(r => r.data),

  getRealtors: (params?: Record<string, string>) =>
    api.get('/real-estate/realtors', { params }).then(r => r.data),

  getFilterOptions: () =>
    api.get('/real-estate/filter-options').then(r => r.data),

  getBenchmarks: (params?: Record<string, any>) =>
    api.get('/real-estate/benchmarks', { params }).then(r => r.data),

  addBenchmark: (data: any) =>
    api.post('/real-estate/benchmarks', data).then(r => r.data),

  bulkUploadBenchmarks: (records: any[]) =>
    api.post('/real-estate/benchmarks/bulk', records).then(r => r.data),

  getComparisons: (params?: Record<string, any>) =>
    api.get('/real-estate/comparisons', { params }).then(r => r.data),

  getUnderContractTimer: () =>
    api.get('/real-estate/under-contract-timer').then(r => r.data),

  contactRealtor: (data: { lead_id: number; contacted: boolean; notes?: string }) =>
    api.post('/real-estate/contact-realtor', data).then(r => r.data),
};

// ── Database ───────────────────────────────────────────────
export const database = {
  getPreMoverLeads: (params?: Record<string, string>) =>
    api.get('/database/pre-mover-leads', { params }).then(r => r.data),
};
