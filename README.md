# 📦 Market Tracking Dashboard (Real Estate & Self-Storage)

A fully automated, dual-purpose data tracking system and dashboard. It tracks **Self-Storage pricing & availability** alongside **MLS Real Estate / Pre-Mover activity** across Northern Virginia, Washington DC, and neighboring Maryland.

This project uses Python, SQLite, and Streamlit to provide actionable market intelligence on a clean, dynamic dashboard. It also features a fully automated background scheduler and a daily HTML email reporting system.

---

## 🚀 Quick Start Guide for New Developers

Follow these steps to set up the project from scratch on your local machine.

### 1. Prerequisites
- Python 3.10 or higher
- Git
- Windows, macOS, or Linux

### 2. Clone & Setup
```bash
git clone <repository_url>
cd self_storrage_tracking
```

Create a virtual environment and activate it:
```bash
# On Windows
python -m venv venv
venv\Scripts\activate

# On macOS/Linux
python3 -m venv venv
source venv/bin/activate
```

Install all required dependencies:
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Create a `.env` file in the root directory:
```ini
# --- Required for Email Reports ---
BREVO_API_KEY=your_brevo_api_key_here
EMAIL_FROM_ADDRESS=your_verified_brevo_email@example.com
EMAIL_FROM_NAME="Around Town Movers Storage Tracker"
EMAIL_TO_ADDRESSES=recipient1@example.com,recipient2@example.com

# --- USA Home Listings (Real Estate leads) ---
USAHOMELISTINGS_EMAIL=your_email@example.com
USAHOMELISTINGS_PASSWORD=your_password

# --- Optional ---
GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
```

### 4. Database Initialization
```bash
python database/db_setup.py
```

### 5. Running Data Collectors (Scrapers)
```bash
# Run all collectors (storage + real estate)
python collectors/run_all.py

# OR run the StorageCafe ETL individually
python collectors/fetch.py
python collectors/parse.py
```

### 6. Launch the Dashboard
```bash
streamlit run dashboard/app.py
```
Opens at `http://localhost:8501`.

### 7. Run the Email Reporter & Scheduler
```bash
# Send the full HTML daily report immediately
python -c "from email_reports.brevo_sender import send_daily_report; send_daily_report()"

# Start the automated background scheduler (runs daily at 11:45 AM ET)
python scheduler/daily_job.py
```

---

## ☁️ AWS Deployment Guide (Docker)

This is the recommended way to run the project 24/7 on an AWS EC2 instance (or any Linux VPS).

### Prerequisites on the server
```bash
sudo apt update
sudo apt install -y docker.io docker-compose git
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER   # so you can run docker without sudo
```
> Log out and back in after running `usermod` for it to take effect.

### Step 1: Clone the project
```bash
git clone https://github.com/Sasi-Praneeth-Reddy/Storage-Tracker-Server.git
cd Storage-Tracker-Server
```

### Step 2: Create your .env file
```bash
cp .env.example .env
nano .env   # fill in your API keys and email settings
```

### Step 3: Build and start the containers (first time only)
```bash
sudo docker-compose build
sudo docker-compose up -d
```
This starts two containers:
- **`storage_dashboard`** — Streamlit web app on port `8501`
- **`storage_scheduler`** — background daily job runner

### Step 4: Open port 8501 in AWS
In the AWS Console → EC2 → Security Groups → add an **Inbound Rule**:
- Type: Custom TCP
- Port: `8501`
- Source: `0.0.0.0/0`

Your dashboard will be live at: `http://YOUR_EC2_PUBLIC_IP:8501`

---

## 🔄 Updating the Project (After Code Changes)

Because the project uses **volume mounts** (local folders are mounted directly into the Docker containers), you **never need to rebuild** after a code change. Just pull and restart:

```bash
cd ~/Storage-Tracker-Server
git pull origin main
sudo docker-compose restart
```

> ✅ Your database (`database/storage_tracker.db`) is safe — it lives on the server disk and is never touched by Docker restarts or rebuilds.

---

## 📋 Useful Docker Commands

```bash
# Check if containers are running
sudo docker ps

# View live logs for the dashboard (shows scraper output)
sudo docker logs -f --tail 100 storage_dashboard

# View live logs for the scheduler (shows daily job status)
sudo docker logs -f --tail 100 storage_scheduler

# Stop all containers
sudo docker-compose down

# Start all containers
sudo docker-compose up -d

# Trigger the email report manually
sudo docker exec storage_scheduler python -c "from email_reports.brevo_sender import send_daily_report; send_daily_report()"

# Run the scrapers manually right now
sudo docker exec storage_scheduler python collectors/run_all.py
```

---

## 🏗️ Architecture & Component Guide

### 1. Data Models (`database/db_setup.py`)
- **`pre_mover_leads`**: Stores real estate MLS data (listings, prices, realtor info).
- **`facilities`**: Physical self-storage locations. Includes brand, lat/lon, and address.
- **`pricing_snapshots`**: Daily price log for self-storage units (e.g., 10x10 → $119/mo).
- **`email_log` & `scrape_log`**: Audit tables to track system health.

### 2. The Scraper Pipeline (`collectors/`)
| File | Purpose |
|---|---|
| `fetch.py` | Downloads raw HTML from StorageCafe for each ZIP code |
| `parse.py` | Parses HTML and saves pricing to the database, then deletes HTML files |
| `run_all.py` | Orchestrates all collectors in the right order |
| `portal_exporter.py` | Pulls real estate leads from USA Home Listings portal |
| `csv_importer.py` | Imports listings from CSV files |

### 3. The Email System (`email_reports/`)
- **`report_builder.py`**: Queries SQLite and generates a styled HTML email with KPI cards, monthly comparisons, realtor listings, and storage price trends.
- **`brevo_sender.py`**: Sends the HTML email via the Brevo transactional email API.

### 4. The Dashboard (`dashboard/app.py`)
Built with Streamlit. Features:
- **Real Estate Page**: Date range filter, MoM KPI comparisons, weekly charts, county breakdown, Top Realtors table.
- **Self-Storage Page**: Price trend by brand, price movement vs. previous period, market share.
- **Database View**: Searchable raw data explorer.

---

## ⚠️ Known Limitations & Troubleshooting
- **Bot Protection (403 Errors)**: StorageCafe uses bot detection. The scraper automatically rotates through free US proxies if blocked. Max 4 retries per ZIP code.
- **Brevo Email Rejections**: Verify that `EMAIL_FROM_ADDRESS` is an authenticated sender in your Brevo dashboard.
- **Database Locks**: If you see `sqlite3.OperationalError: database is locked`, ensure only one scraper process is writing at a time.
- **Animation still showing after scrape**: Click the **🔄 Refresh** button on the dashboard — Streamlit does not auto-refresh when background tasks finish.
