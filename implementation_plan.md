# Self-Storage Market Tracker — Implementation Plan

## Northern Virginia / DC Metro Area

A fully automated daily-refresh dashboard that tracks self-storage pricing, availability, and promotions alongside MLS housing activity, with a beautiful Streamlit dashboard and daily HTML email reports.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   Data Pipeline                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │ Google Maps  │  │ SpareFoot /  │  │ RentCast  │  │
│  │ Places API   │  │ Brand Sites  │  │ API (MLS) │  │
│  │ (Facilities) │  │  (Pricing)   │  │(Listings) │  │
│  └──────┬───────┘  └──────┬───────┘  └─────┬─────┘  │
│         └─────────────────▼─────────────────┘       │
│                      SQLite DB                      │
│                  (storage_tracker.db)               │
└───────────────────────┬─────────────────────────────┘
                        │
          ┌─────────────▼──────────────┐
          │      Streamlit Dashboard   │
          │  (Charts, Maps, KPIs,      │
          │   Comparison Tables)       │
          └─────────────┬──────────────┘
                        │
          ┌─────────────▼──────────────┐
          │  Daily Email Report        │
          │  (Brevo API — HTML email   │
          │   with dashboard link)     │
          └────────────────────────────┘
                        │
          ┌─────────────▼──────────────┐
          │  Windows Task Scheduler    │
          │  (daily at 7am ET)         │
          └────────────────────────────┘
```

---

## User Review Required

> [!IMPORTANT]
> **API Keys Needed (Free)** — Before we can run the live system, you'll need to register for:
>
> 1. **Google Maps Places API** — https://console.cloud.google.com (free $200/mo credit, ~5K searches free)
> 2. **RentCast API** — https://rentcast.io/api (50 free calls/month for MLS-like data)
> 3. **Brevo Email** — https://www.brevo.com (free forever, 300 emails/day)
>
> All are free-tier and require a Google/email account signup only (no credit card for Brevo/RentCast).

> [!NOTE]
> **MLS Data Limitations**: True MLS listing feeds require a real estate license or MLS membership. We'll use **RentCast** (50 free calls/mo) for property market data and supplement with publicly available data from **Zillow Research** public datasets and scraped active listings from public property portals. This gives you MLS-like market intelligence without a broker credential.

> [!WARNING]
> **Scraping**: Pricing data from SpareFoot and brand websites (Public Storage, Extra Space, CubeSmart) will be scraped from their public, non-login-required pages. The app will respect `robots.txt` and use polite rate limiting. This is legally defensible but scraping behavior may need updates if sites change their structure.

---

## Open Questions

> [!IMPORTANT]
> **Target ZIP Codes / Radius**: Which ZIP codes or cities in Northern Virginia / DC Metro should we focus on? (e.g., 22314 Alexandria, 22042 Falls Church, 20110 Manassas, the whole NoVa corridor). This affects how many facilities we'll track and API quota usage.

> [!IMPORTANT]
> **Email Recipients**: Who should receive the daily email report? (Just you, or a team?) And what email address should it send FROM? (We'll configure Brevo with that.)

---

## Proposed Changes

### Component 1: Project Scaffold & Configuration

#### [NEW] `config.py`

Central configuration file — API keys, target ZIP codes, storage brands to track, email recipients. All credentials stored as environment variables.

#### [NEW] `.env.example`

Template showing required environment variables (no real keys committed to code).

#### [NEW] `requirements.txt`

Python dependencies: `streamlit`, `playwright`, `beautifulsoup4`, `requests`, `plotly`, `pandas`, `folium`, `streamlit-folium`, `python-dotenv`, `brevo-python`, `schedule`, `apscheduler`

---

### Component 2: Database Layer

#### [NEW] `database/db_setup.py`

SQLite schema creation:

- `facilities` — name, address, lat/lon, brand, phone, website, google_place_id
- `pricing_snapshots` — facility_id, unit_size, rate, availability, discount, scraped_at
- `mls_listings` — zip_code, active_listings, median_price, new_listings, fetched_at
- `email_log` — recipient, sent_at, status

#### [NEW] `database/models.py`

Data models / helper functions for reading/writing to SQLite.

---

### Component 3: Data Collectors

#### [NEW] `collectors/google_maps_collector.py`

- Uses Google Maps Places API (Nearby Search) to discover all storage facilities within a configurable radius of target ZIP codes
- Stores name, address, lat/lon, rating, website URL into `facilities` table
- Runs weekly (facility list doesn't change often)

#### [NEW] `collectors/sparefoot_scraper.py`

- Scrapes SpareFoot.com search results for each target ZIP code
- Extracts: facility name, unit sizes, monthly rates, availability, current specials
- Uses `requests` + `BeautifulSoup` (falls back to `Playwright` if JS-heavy)
- Rate-limited to 1-2 second delays

#### [NEW] `collectors/brand_scrapers/public_storage.py`

- Scrapes PublicStorage.com for NoVa locations
- Extracts unit sizes, web rates, street rates, promotions

#### [NEW] `collectors/brand_scrapers/extra_space.py`

- Scrapes ExtraSpace.com for NoVa locations

#### [NEW] `collectors/brand_scrapers/cubesmart.py`

- Scrapes CubeSmart.com for NoVa locations

#### [NEW] `collectors/mls_collector.py`

- Calls RentCast API for market stats per ZIP code (active listings, median price, days on market)
- Falls back to Zillow Research public CSV datasets for supplemental data
- Stores results in `mls_listings` table

#### [NEW] `collectors/run_all.py`

- Orchestrates all collectors in sequence with logging
- Called by the scheduler every day at 7 AM

---

### Component 4: Streamlit Dashboard

#### [NEW] `dashboard/app.py`

Main Streamlit app with:

- **Header**: Logo, last-updated timestamp, market summary banner
- **Sidebar**: ZIP code filter, brand filter, date range picker
- **KPI Row**: Total facilities tracked | Avg 10x10 rate | Cheapest rate | MLS listings active
- **Price Trend Chart** (Plotly line): Average monthly rate over time by brand
- **Interactive Map** (Folium): All facilities as pins, color-coded by brand, click for pricing popup
- **Pricing Table**: Sortable table — facility name, unit sizes, current rate, last week rate, change, promotions
- **MLS Correlation Panel**: Active listings count vs. storage demand signals over time
- **Promotions Tracker**: Cards showing current deals/discounts from each facility

#### [NEW] `dashboard/components/kpi_cards.py`

Reusable styled KPI card components.

#### [NEW] `dashboard/components/pricing_chart.py`

Plotly chart components for price trends.

#### [NEW] `dashboard/components/facility_map.py`

Folium map component with facility markers.

#### [NEW] `dashboard/styles/custom.css`

Custom CSS injected via `st.markdown()` for premium look: gradient headers, card shadows, color palette.

---

### Component 5: Email Report Generator

#### [NEW] `email_reports/html_template.py`

Jinja2-based HTML email template:

- Summary stats in styled table
- Price change highlights (green/red)
- Inline Plotly chart as embedded image
- "View Full Dashboard" button linking to Streamlit app URL
- Professional branding for Around Town Movers

#### [NEW] `email_reports/sender.py`

- Uses Brevo API (free 300/day)
- Renders the HTML template with today's data
- Sends to configured recipient list
- Logs sent status to DB

---

### Component 6: Scheduler

#### [NEW] `scheduler/daily_job.py`

Uses Python `APScheduler` to:

1. Run all data collectors at 6:30 AM ET
2. Generate and send email report at 7:00 AM ET

#### [NEW] `scheduler/setup_windows_task.ps1`

PowerShell script to register the scheduler as a Windows Task Scheduler job (runs on startup, daily).

---

### Component 7: Supporting Files

#### [NEW] `README.md`

Setup instructions, how to add your API keys, how to run.

#### [NEW] `.gitignore`

Excludes `.env`, `*.db`, `__pycache__`, etc.

---

## Verification Plan

### Automated Tests

- `python collectors/run_all.py --dry-run` — validate all scrapers return data without writing to DB
- `python email_reports/sender.py --test` — send a test email with mock data

### Manual Verification

1. Run `streamlit run dashboard/app.py` and visually inspect the dashboard
2. Verify at least 10 storage facilities appear on the map for NoVa
3. Verify pricing data shows unit sizes and rates
4. Confirm daily email arrives with correct data and dashboard link works
5. Check Windows Task Scheduler shows job running successfully
