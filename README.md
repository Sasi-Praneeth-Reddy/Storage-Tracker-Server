# 🏢 Market Tracking Dashboard (Real Estate & Self-Storage)

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
First, clone the repository and navigate into the project directory:
```bash
git clone <repository_url>
cd self_storrage_tracking
```

Next, create a fresh Python virtual environment and activate it:
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
*(If you are running Playwright scrapers, you may also need to run `playwright install chromium`)*

### 3. Configure Environment Variables
The system relies on a `.env` file for API keys and email configuration. 

Create a file named `.env` in the root directory and add the following variables:
```ini
# --- Required for Email Reports ---
BREVO_API_KEY=your_brevo_api_key_here
EMAIL_FROM_ADDRESS=your_verified_brevo_email@example.com
EMAIL_FROM_NAME="Around Town Movers Storage Tracker"
EMAIL_TO_ADDRESSES=recipient1@example.com,recipient2@example.com

# --- Required for Google Maps Scraper ---
GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
```
*Note: Make sure your `EMAIL_FROM_ADDRESS` is a verified sender in your Brevo account, otherwise emails will be silently blocked (HTTP 401).*

### 4. Database Initialization
The system uses a unified SQLite database (`database/storage_tracker.db`). Initialize the database to create all the necessary tables (`pre_mover_leads`, `facilities`, `pricing_snapshots`, `email_log`):
```bash
python database/db_setup.py
```

### 5. Running Data Collectors (Scrapers)
You can run the collectors individually to pull fresh market data into your database:
```bash
# 1. Discover Self-Storage facilities via Google Maps API
python collectors/google_maps_collector.py

# 2. Pull live pricing from Public Storage facilities
python collectors/public_storage_scraper.py

# 3. Pull live pricing from Extra Space Storage (Warning: strict bot protection)
python collectors/extra_space_scraper.py
```

### 6. Launch the Dashboard
To view the data on the interactive Streamlit dashboard:
```bash
streamlit run dashboard/app.py
```
This will open the dashboard in your default web browser at `http://localhost:8501`.

### 7. Run the Email Reporter & Scheduler
To test the email reporting system manually:
```bash
# Send a test email to verify Brevo configuration
python -c "from email_reports.brevo_sender import send_test_email; send_test_email()"

# Send the actual full HTML daily report
python -c "from email_reports.brevo_sender import send_daily_report; send_daily_report()"
```

To run the automated background scheduler (which runs scrapers and sends the email at 7:00 AM daily):
```bash
python scheduler/daily_job.py
```

---

## 🏗️ Architecture & Component Guide

### 1. Data Models (`database/db_setup.py`)
- **`pre_mover_leads`**: Stores real estate MLS data.
- **`facilities`**: Physical self-storage locations discovered via Google Maps. Includes brand, lat/lon, and address.
- **`pricing_snapshots`**: Daily price log for self-storage units. Maps a `facility_id` and `unit_size` (e.g., 10x10) to a `web_rate` and `street_rate`.
- **`email_log` & `scrape_log`**: Audit tables to track system health.

### 2. The Email System (`email_reports/`)
- **`report_builder.py`**: Queries the SQLite database and generates a beautifully styled HTML email template containing KPI cards and market summaries matching the Streamlit dashboard.
- **`brevo_sender.py`**: Uses the `requests` library to securely dispatch the HTML payload to the Brevo (Sendinblue) transactional email API.

### 3. The Dashboard (`dashboard/app.py`)
Built with Streamlit and styled with custom CSS for a premium dark-mode aesthetic. Features a **Real Estate Page** and a **Self-Storage Page** with interactive Folium maps and Plotly charts.

---

## ☁️ Cloud Deployment (Docker)

To run this system 24/7 without keeping your local machine awake, the project is designed to be containerized using Docker and deployed to a Virtual Private Server (VPS) like AWS EC2, Google Cloud, or DigitalOcean.

1. **Dockerfile**: Packages Python 3.11, the requirements, and the source code.
2. **docker-compose.yml**: Spins up two services simultaneously:
   - `dashboard` (exposing port 8501)
   - `scheduler` (running `daily_job.py` in the background)
3. **Volume Mount**: Ensure the `database/` folder is mounted as a persistent Docker volume so SQLite data is not lost when containers restart.

---

## ⚠️ Known Limitations & Troubleshooting
- **Bot Protection (403 Errors)**: Extra Space and aggregator sites (Sparefoot) use aggressive Cloudflare protection. Headless scraping may fail. Consider using residential proxies or increasing `SCRAPE_DELAY_SECONDS` in `config.py`.
- **Brevo Email Rejections**: If the script logs a successful send but you receive no email, verify that the `EMAIL_FROM_ADDRESS` is authenticated in your Brevo account dashboard.
- **Database Locks**: If you see `sqlite3.OperationalError: database is locked`, ensure multiple scripts aren't trying to write to the SQLite file simultaneously.
