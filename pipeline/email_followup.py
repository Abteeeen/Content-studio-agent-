"""Email follow-up — sends a follow-up email 3 days after postcard arrives.

Free options:
- Gmail SMTP (500 emails/day free)
- Mailgun (1,000 emails/mo free for 3 months)
- Resend (100 emails/day free)
- SendGrid (100 emails/day free forever)

The email includes a link to their reel and a soft CTA.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from pipeline.models import Store

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_NAME = os.getenv("FROM_NAME", "Your Agency Name")
FROM_EMAIL = os.getenv("FROM_EMAIL", "hello@youragency.com")


def send_followup_email(
    store: Store,
    to_email: str,
    reel_url: str,
) -> bool:
    """Send a personalized follow-up email after the postcard."""
    if not SMTP_USER:
        logger.warning("SMTP not configured — skipping email for %s", store.name)
        return False

    owner = store.owner_name or "there"
    subject = f"Did you get our postcard, {owner}?"

    html_body = _build_email_html(store, owner, reel_url)
    text_body = _build_email_text(store, owner, reel_url)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        logger.info("Follow-up email sent to %s for %s", to_email, store.name)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to_email, e)
        return False


def _build_email_html(store: Store, owner: str, reel_url: str) -> str:
    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
        <h2 style="color: #1a1a1a; font-size: 24px;">Hey {owner},</h2>

        <p style="color: #444; font-size: 16px; line-height: 1.6;">
            A few days ago we sent you a postcard with a cinematic reel we made
            for <strong>{store.name}</strong> — completely free, no strings attached.
        </p>

        <p style="color: #444; font-size: 16px; line-height: 1.6;">
            We picked one piece from your store, put it on a model, and turned it
            into a cinematic fashion reel. Here it is:
        </p>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{reel_url}"
               style="background: #1a1a1a; color: white; padding: 16px 40px;
                      text-decoration: none; border-radius: 8px; font-size: 18px;
                      display: inline-block;">
                Watch Your Reel
            </a>
        </div>

        <p style="color: #444; font-size: 16px; line-height: 1.6;">
            If you like what you see, imagine what we could do with your
            <em>full collection</em> — weekly reels, seasonal campaigns,
            product launches.
        </p>

        <p style="color: #444; font-size: 16px; line-height: 1.6;">
            Want to chat? Just reply to this email or book a 15-minute call:
            <br>
            <a href="https://calendly.com/youragency" style="color: #2563eb;">Book a call</a>
        </p>

        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">

        <p style="color: #999; font-size: 13px;">
            {FROM_NAME} · Cinematic content for fashion brands
            <br>
            <a href="https://youragency.com" style="color: #999;">youragency.com</a>
        </p>
    </div>
    """


def _build_email_text(store: Store, owner: str, reel_url: str) -> str:
    return f"""Hey {owner},

A few days ago we sent you a postcard with a cinematic reel we made for {store.name} — completely free.

We picked one piece from your store, put it on a model, and turned it into a cinematic fashion reel.

Watch it here: {reel_url}

If you like what you see, imagine what we could do with your full collection.

Reply to this email or book a call: https://calendly.com/youragency

— {FROM_NAME}
"""
