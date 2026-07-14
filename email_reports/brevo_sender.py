"""
email_reports/brevo_sender.py

Sends the daily HTML report email via Brevo (formerly Sendinblue).
Free tier: 300 emails/day, no credit card required.

Usage:
    from email_reports.brevo_sender import send_daily_report
    send_daily_report()

Or run standalone:
    venv\\Scripts\\python email_reports/brevo_sender.py
"""

import sys
import logging
import pathlib
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from config import BREVO_API_KEY, EMAIL_TO_ADDRESSES, EMAIL_FROM_ADDRESS, EMAIL_FROM_NAME
from email_reports.report_builder import build_report
from database.db_setup import get_connection

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s -- %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


def _log_email(status: str, recipient: str, error: str = ""):
    """Record email send attempt in the email_log table."""
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO email_log (recipients, status, error_msg, sent_at)
            VALUES (?, ?, ?, datetime('now'))
        """, (recipient, status, error))
        conn.commit()
    except Exception as exc:
        log.warning("Could not write to email_log: %s", exc)
    finally:
        conn.close()


def send_daily_report() -> bool:
    """
    Build the HTML report and send it to all recipients in EMAIL_TO_ADDRESSES.
    Returns True if all sends succeeded.
    """
    if not BREVO_API_KEY or "your_" in BREVO_API_KEY:
        log.warning("BREVO_API_KEY not set. Email not sent.")
        log.info("To enable email: add your Brevo API key to the .env file.")
        log.info("Sign up free at: https://www.brevo.com")
        return False

    # Build the report HTML
    log.info("Building daily report HTML...")
    try:
        html_content = build_report()
    except Exception as exc:
        log.error("Failed to build report: %s", exc, exc_info=True)
        return False

    # Prepare subject
    date_str = datetime.now().strftime("%B %d, %Y")
    subject  = "Storage Market Report — {}".format(date_str)

    # EMAIL_TO_ADDRESSES is already a list from config.py
    recipients = EMAIL_TO_ADDRESSES if isinstance(EMAIL_TO_ADDRESSES, list) \
                 else [r.strip() for r in EMAIL_TO_ADDRESSES.split(",") if r.strip()]
    if not recipients:
        log.error("No recipient email addresses configured in .env EMAIL_TO_ADDRESSES")
        return False

    # Send via Brevo REST API (avoids Pydantic v2 bugs in the official SDK)
    try:
        import requests
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "accept": "application/json",
            "api-key": BREVO_API_KEY,
            "content-type": "application/json"
        }
        payload = {
            "sender": {"name": EMAIL_FROM_NAME, "email": EMAIL_FROM_ADDRESS},
            "to": [{"email": r} for r in recipients],
            "subject": subject,
            "htmlContent": html_content
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        
        if response.status_code in (200, 201, 202):
            log.info("Email successfully dispatched via Brevo!")
            _log_email("sent", ",".join(recipients))
            return True
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            log.error("Brevo send failed: %s", error_msg)
            _log_email("failed", ",".join(recipients), error_msg[:500])
            return False

    except Exception as exc:
        error_msg = str(exc)
        log.error("Brevo send failed: %s", error_msg)
        _log_email("failed", ",".join(recipients), error_msg[:500])
        return False


def send_test_email(to_address: str = None) -> bool:
    """
    Send a test email with placeholder content to verify Brevo is configured.
    Defaults to the first address in EMAIL_TO_ADDRESSES.
    """
    if not to_address:
        to_address = EMAIL_TO_ADDRESSES[0] if isinstance(EMAIL_TO_ADDRESSES, list) \
                     else EMAIL_TO_ADDRESSES.split(",")[0].strip()

    if not BREVO_API_KEY or "your_" in BREVO_API_KEY:
        log.warning("BREVO_API_KEY not set. Cannot send test email.")
        return False

    log.info("Sending test email to %s ...", to_address)
    html = """
    <html><body>
    <h2 style='color:#1a3c5e;'>Around Town Movers Storage Tracker</h2>
    <p>This is a <strong>test email</strong> confirming that Brevo is configured correctly.</p>
    <p>Your daily storage market report will be sent automatically once scrapers are running.</p>
    <hr>
    <p style='color:#888; font-size:12px;'>Sent: {}</p>
    </body></html>
    """.format(datetime.now().strftime("%Y-%m-%d %H:%M UTC"))

    try:
        import requests
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "accept": "application/json",
            "api-key": BREVO_API_KEY,
            "content-type": "application/json"
        }
        payload = {
            "sender": {"name": EMAIL_FROM_NAME, "email": EMAIL_FROM_ADDRESS},
            "to": [{"email": to_address}],
            "subject": "System Test: Storage Tracker",
            "htmlContent": html
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        
        if response.status_code in (200, 201, 202):
            log.info("Test email successfully dispatched to %s via Brevo!", to_address)
            return True
        else:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            log.error("Test email failed: %s", error_msg)
            return False

    except Exception as exc:
        log.error("Test email failed: %s", exc)
        return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Brevo email sender")
    parser.add_argument("--test", action="store_true",
                        help="Send a test email instead of the full report")
    parser.add_argument("--to", default=None,
                        help="Override recipient email for test")
    args = parser.parse_args()

    if args.test:
        ok = send_test_email(args.to)
        sys.exit(0 if ok else 1)
    else:
        ok = send_daily_report()
        sys.exit(0 if ok else 1)
