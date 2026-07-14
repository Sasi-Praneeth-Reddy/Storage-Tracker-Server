# 🗓️ Self-Storage Tracker — Roadmap to July 3rd

**Start:** June 24, 2026 &nbsp;|&nbsp; **Deadline:** July 3, 2026 &nbsp;|&nbsp; **Total:** 9 days

> [!IMPORTANT]
> Each phase builds directly on the last. Nothing is skipped or rushed. By following this order you'll always have a **working, runnable system** at every stage — not half-built pieces.

---

## Overview

| Phase                   | Days | Dates     | Deliverable                                  |
| ----------------------- | ---- | --------- | -------------------------------------------- |
| **1 — Foundation**      | 1–2  | Jun 24–25 | Project runs, DB exists, API keys connected  |
| **2 — Data Collectors** | 3–4  | Jun 26–27 | Real data flowing into DB from all sources   |
| **3 — Dashboard**       | 5–6  | Jun 28–29 | Live Streamlit dashboard with map & charts   |
| **4 — Email Reports**   | 7    | Jun 30    | Daily HTML email sends successfully          |
| **5 — Automation**      | 8    | Jul 1     | Task Scheduler runs everything automatically |
| **6 — Polish & Buffer** | 9    | Jul 2–3   | Fully tested, documented, production-ready   |

---

## Phase 1 — Foundation (Jun 24–25)

> **Goal**: A working skeleton you can run end-to-end, even with no real data yet.

### Day 1 — Jun 24

- [✅] Create project folder structure
- [✅] Set up Python virtual environment (`venv`)
- [✅] Create `requirements.txt` and install all libraries
- [✅] Create `config.py` and `.env.example`
- [✅] Create SQLite database with all tables (`db_setup.py`)
- [✅] Verify DB opens and tables are created correctly

### Day 2 — Jun 25

- [] Register for free API keys:
  - [] Google Maps Places API (console.cloud.google.com)
  - [ ] RentCast API (rentcast.io/api)
  - [ ] Brevo email account (brevo.com)
- [ ] Store keys in `.env` file
- [ ] Confirm each API key works with a simple test call
- [ ] Create `collectors/run_all.py` (stub/skeleton — no real scrapers yet)

✅ **Phase 1 Exit Criteria**: `python db_setup.py` runs clean. API keys verified working.

---

## Phase 2 — Data Collectors (Jun 26–27)

> **Goal**: Real pricing data from NoVa self-storage facilities flowing into the database.

### Day 3 — Jun 26

- [ ] **Google Maps Collector** — find all storage facilities in target ZIP codes, save to DB
- [ ] **SpareFoot Scraper** — scrape unit sizes, monthly rates, availability, promotions
- [ ] Verify 10+ facilities with pricing data appear in DB
- [ ] Add basic logging so you can see what's happening

### Day 4 — Jun 27

- [ ] **Brand scrapers** — Public Storage, Extra Space Storage, CubeSmart NoVa locations
- [ ] **MLS/Market Collector** — RentCast API for housing market stats per ZIP code
- [ ] Wire all collectors into `run_all.py`
- [ ] Run full pipeline end-to-end, verify DB is populated with clean data

✅ **Phase 2 Exit Criteria**: `python collectors/run_all.py` populates the database with real pricing data from ≥10 NoVa facilities.

---

## Phase 3 — Streamlit Dashboard (Jun 28–29)

> **Goal**: A beautiful, interactive dashboard showing all collected data visually.

### Day 5 — Jun 28

- [ ] Create `dashboard/app.py` skeleton with Streamlit
- [ ] Build **KPI cards** row (total facilities, avg rates, active MLS listings)
- [ ] Build **interactive map** (Folium) — pin each facility, click for pricing popup
- [ ] Build **sidebar filters** (ZIP code, brand, date range)
- [ ] Verify `streamlit run dashboard/app.py` launches and map shows facilities

### Day 6 — Jun 29

- [ ] Build **price trend line chart** (Plotly) — avg rate over time by brand
- [ ] Build **pricing comparison table** — sortable, shows rate changes week-over-week
- [ ] Build **promotions panel** — cards with current deals/discounts
- [ ] Build **MLS correlation panel** — listings count vs. storage rate trends
- [ ] Apply custom CSS for premium look (gradient header, card shadows, color palette)

✅ **Phase 3 Exit Criteria**: Dashboard runs locally, shows map + charts + tables with real data. Looks polished.

---

## Phase 4 — Email Reports (Jun 30)

> **Goal**: A professional HTML email generated from today's data and sent successfully.

### Day 7 — Jun 30

- [ ] Build **HTML email template** (Jinja2) — styled summary stats, price changes, promotions
- [ ] Add green/red indicators for rate changes vs. prior day
- [ ] Add **"View Full Dashboard" button** linking to Streamlit app URL
- [ ] Wire Brevo API sender (`email_reports/sender.py`)
- [ ] Send a test email and verify it looks correct on desktop + mobile
- [ ] Add email logging to DB (who received it, when, success/fail)

✅ **Phase 4 Exit Criteria**: `python email_reports/sender.py --test` sends a correctly formatted email.

---

## Phase 5 — Automation (Jul 1)

> **Goal**: The entire system runs itself, every day, with no manual action.

### Day 8 — Jul 1

- [ ] Create `scheduler/daily_job.py` — runs collectors at 6:30 AM, email at 7:00 AM
- [ ] Create `scheduler/setup_windows_task.ps1` — registers the job in Windows Task Scheduler
- [ ] Run the PowerShell script to register the task
- [ ] Verify Task Scheduler shows job as active
- [ ] Manually trigger the task to confirm full pipeline runs unattended
- [ ] Set up error alerting (send email if scraper fails)

✅ **Phase 5 Exit Criteria**: Windows Task Scheduler runs the full pipeline automatically. You receive the email without doing anything.

---

## Phase 6 — Polish & Buffer (Jul 2–3)

> **Goal**: Fully tested, documented, and stable. Buffer time for any surprises.

### Day 9 — Jul 2–3

- [ ] End-to-end test: let full automated cycle run overnight Jul 1→2, verify Jul 2 email arrived
- [ ] Fix any broken scrapers (websites change structure)
- [ ] Write `README.md` — setup guide, how to add ZIP codes, how to add email recipients
- [ ] Final dashboard visual polish (fonts, colors, spacing)
- [ ] Optional: deploy Streamlit to Streamlit Community Cloud (public URL, free)
- [ ] Optional: add a second email recipient

✅ **Phase 6 Exit Criteria**: System runs two consecutive days automatically. Dashboard is shareable. Documentation is clear.

---

## Daily Time Estimate

Each phase is designed to be achievable in **2–4 hours of focused work per day**:

| Day     | Hours Needed | Complexity           |
| ------- | ------------ | -------------------- |
| Jun 24  | 2–3 hrs      | 🟢 Low               |
| Jun 25  | 1–2 hrs      | 🟢 Low (API signups) |
| Jun 26  | 3–4 hrs      | 🟡 Medium            |
| Jun 27  | 3–4 hrs      | 🟡 Medium            |
| Jun 28  | 2–3 hrs      | 🟡 Medium            |
| Jun 29  | 3–4 hrs      | 🟡 Medium            |
| Jun 30  | 2–3 hrs      | 🟢 Low               |
| Jul 1   | 2–3 hrs      | 🟡 Medium            |
| Jul 2–3 | 1–2 hrs      | 🟢 Low (buffer)      |

---

## What I Build vs. What You Set Up

| Task                                             | Who Does It         |
| ------------------------------------------------ | ------------------- |
| All code (scrapers, dashboard, email, scheduler) | ✅ Me (Antigravity) |
| Register Google Maps API key (free)              | 🔑 You              |
| Register RentCast API key (free)                 | 🔑 You              |
| Register Brevo account (free)                    | 🔑 You              |
| Confirm target ZIP codes & email recipient       | 🔑 You              |
| Approve each phase before we move on             | 🔑 You              |

---

## Starting Point — Right Now

> [!NOTE]
> We're ready to begin **Phase 1 today (Jun 24)** as soon as you confirm:
>
> 1. **Which ZIP codes** in NoVa/DC Metro to target
> 2. **What email address** should receive the daily report
>
> Tell me these two things and I'll start building immediately.
