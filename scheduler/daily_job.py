"""
scheduler/daily_job.py

APScheduler-based daily job runner.
Runs all data collectors at 7:00 AM every day, then sends the email report.

Run (keeps running in the background):
    venv\\Scripts\\python scheduler/daily_job.py

Or trigger once immediately (for testing):
    venv\\Scripts\\python scheduler/daily_job.py --run-now
"""

import sys
import logging
import argparse
import pathlib
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s -- %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


def daily_real_estate_job():
    """Daily pipeline for Real Estate."""
    from collectors.run_all import run_real_estate
    try:
        run_real_estate()
    except Exception as exc:
        log.error("Real Estate run failed: %s", exc, exc_info=True)

    # We send the daily email report every day, regardless of whether
    # self-storage ran today. It will just pull the latest available storage data.
    from email_reports.brevo_sender import send_daily_report
    log.info("Sending daily email report...")
    try:
        ok = send_daily_report()
        if ok:
            log.info("Daily report sent successfully.")
        else:
            log.warning("Daily report could not be sent.")
    except Exception as exc:
        log.error("Report send failed: %s", exc, exc_info=True)

def tri_daily_storage_job():
    """Every 3 days pipeline for Self Storage."""
    from collectors.run_all import run_self_storage
    try:
        run_self_storage()
    except Exception as exc:
        log.error("Self Storage run failed: %s", exc, exc_info=True)


def main():
    parser = argparse.ArgumentParser(description="Self-Storage & Real Estate Tracker Scheduler")
    parser.add_argument("--run-now", action="store_true", help="Run both jobs immediately (once)")
    parser.add_argument("--hour", type=int, default=11, help="Hour to run (24h, default: 11)")
    parser.add_argument("--minute", type=int, default=45, help="Minute to run (default: 45)")
    args = parser.parse_args()

    if args.run_now:
        log.info("--run-now flag detected. Running both jobs immediately...")
        daily_real_estate_job()
        tri_daily_storage_job()
        return

    scheduler = BlockingScheduler(timezone="America/New_York")
    
    # Real Estate runs every day
    re_trigger = CronTrigger(hour=args.hour, minute=args.minute, timezone="America/New_York")
    scheduler.add_job(daily_real_estate_job, re_trigger, id="daily_re_job", name="Daily Real Estate Tracker")

    # Self Storage runs every 3 days (e.g., 1st, 4th, 7th...)
    st_minute = (args.minute + 30) % 60
    st_hour = (args.hour + 1) if (args.minute + 30) >= 60 else args.hour
    st_trigger = CronTrigger(day="*/3", hour=st_hour, minute=st_minute, timezone="America/New_York")
    scheduler.add_job(tri_daily_storage_job, st_trigger, id="tri_daily_st_job", name="Every 3 Days Storage Tracker")

    log.info("Scheduler started.")
    log.info("Real Estate: Every day at %02d:%02d AM", args.hour, args.minute)
    log.info("Self Storage: Every 3 days at %02d:%02d", st_hour, st_minute)
    log.info("Press Ctrl+C to stop.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")

if __name__ == "__main__":
    main()
