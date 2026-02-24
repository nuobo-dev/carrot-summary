"""Email delivery for FlowTrack weekly reports.

Uses smtplib and email standard library modules to send .docx attachments
via user-configured SMTP settings. On failure, logs the error and retains
the document locally for manual retrieval.
"""

import logging
import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flowtrack.core.models import SmtpConfig

logger = logging.getLogger(__name__)


class EmailSender:
    """Sends emails with .docx attachments using SMTP."""

    def __init__(self, config: SmtpConfig):
        self.config = config

    def send(self, to_address: str, subject: str, body: str, attachment_path: str) -> bool:
        """Send an email with the .docx attachment.

        Returns True on success, False on failure. Errors are logged but
        never raised — the document is retained locally for manual retrieval.
        """
        try:
            msg = self._build_message(to_address, subject, body, attachment_path)
            self._deliver(msg, to_address)
            logger.info("Email sent successfully to %s", to_address)
            return True
        except Exception:
            logger.error(
                "Failed to send email to %s. Document retained at: %s",
                to_address,
                attachment_path,
                exc_info=True,
            )
            return False

    def _build_message(
        self, to_address: str, subject: str, body: str, attachment_path: str
    ) -> MIMEMultipart:
        """Construct the MIME message with text body and .docx attachment."""
        msg = MIMEMultipart()
        msg["From"] = self.config.username
        msg["To"] = to_address
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))

        part = MIMEBase("application", "octet-stream")
        with open(attachment_path, "rb") as f:
            part.set_payload(f.read())
        encoders.encode_base64(part)
        filename = os.path.basename(attachment_path)
        part.add_header("Content-Disposition", f"attachment; filename={filename}")
        msg.attach(part)

        return msg

    def _deliver(self, msg: MIMEMultipart, to_address: str) -> None:
        """Connect to the SMTP server and send the message."""
        if self.config.use_tls:
            server = smtplib.SMTP(self.config.server, self.config.port)
            server.starttls()
        else:
            server = smtplib.SMTP(self.config.server, self.config.port)

        try:
            server.login(self.config.username, self.config.password)
            server.sendmail(self.config.username, to_address, msg.as_string())
        finally:
            server.quit()
