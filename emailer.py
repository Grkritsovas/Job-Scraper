import os
import smtplib
from email.mime.text import MIMEText


def get_email_config():
    email = os.getenv("JOB_SCRAPER_EMAIL")
    app_password = os.getenv("JOB_SCRAPER_APP_PASSWORD")

    if not email or not app_password:
        raise RuntimeError(
            "Email config is missing. Set JOB_SCRAPER_EMAIL and "
            "JOB_SCRAPER_APP_PASSWORD in the current environment before "
            "running the scraper."
        )

    return email, app_password


def send_email(subject, body):
    if os.getenv("JOB_SCRAPER_DRY_RUN") == "1":
        print(f"[DRY RUN] {subject}")
        print(body)
        return

    email, app_password = get_email_config()

    message = MIMEText(body)
    message["Subject"] = subject
    message["From"] = email
    message["To"] = email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(email, app_password)
        server.send_message(message)
