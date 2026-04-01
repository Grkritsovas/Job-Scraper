import os
import smtplib
from email.mime.multipart import MIMEMultipart
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


def send_email(subject, body, recipient_email=None, html_body=None):
    if os.getenv("JOB_SCRAPER_DRY_RUN") == "1":
        print(f"[DRY RUN] {subject}")
        print(f"To: {recipient_email or '(default sender address)'}")
        print(body)
        if html_body:
            print("[DRY RUN HTML BODY AVAILABLE]")
        return

    email, app_password = get_email_config()
    recipient_email = recipient_email or email

    if html_body:
        message = MIMEMultipart("alternative")
        message.attach(MIMEText(body, "plain", "utf-8"))
        message.attach(MIMEText(html_body, "html", "utf-8"))
    else:
        message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = subject
    message["From"] = email
    message["To"] = recipient_email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(email, app_password)
        server.send_message(message)
