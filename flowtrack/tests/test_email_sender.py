"""Tests for the EmailSender class."""

import os
import smtplib
from unittest.mock import MagicMock, patch

import pytest

from flowtrack.core.models import SmtpConfig
from flowtrack.reporting.email_sender import EmailSender


@pytest.fixture
def smtp_config():
    return SmtpConfig(
        server="smtp.example.com",
        port=587,
        username="user@example.com",
        password="secret",
        use_tls=True,
    )


@pytest.fixture
def smtp_config_no_tls():
    return SmtpConfig(
        server="smtp.example.com",
        port=25,
        username="user@example.com",
        password="secret",
        use_tls=False,
    )


@pytest.fixture
def docx_file(tmp_path):
    """Create a small dummy .docx file for attachment."""
    path = tmp_path / "report.docx"
    path.write_bytes(b"PK\x03\x04fake-docx-content")
    return str(path)


class TestEmailSenderSuccess:
    """Tests for successful email delivery."""

    @patch("flowtrack.reporting.email_sender.smtplib.SMTP")
    def test_send_returns_true_on_success(self, mock_smtp_cls, smtp_config, docx_file):
        sender = EmailSender(smtp_config)

        result = sender.send("recipient@example.com", "Weekly Report", "Here is your report.", docx_file)

        assert result is True

    @patch("flowtrack.reporting.email_sender.smtplib.SMTP")
    def test_smtp_starttls_called_when_use_tls(self, mock_smtp_cls, smtp_config, docx_file):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        sender = EmailSender(smtp_config)
        sender.send("recipient@example.com", "Subject", "Body", docx_file)

        mock_server.starttls.assert_called_once()

    @patch("flowtrack.reporting.email_sender.smtplib.SMTP")
    def test_smtp_no_starttls_when_tls_disabled(self, mock_smtp_cls, smtp_config_no_tls, docx_file):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        sender = EmailSender(smtp_config_no_tls)
        sender.send("recipient@example.com", "Subject", "Body", docx_file)

        mock_server.starttls.assert_not_called()

    @patch("flowtrack.reporting.email_sender.smtplib.SMTP")
    def test_smtp_login_with_credentials(self, mock_smtp_cls, smtp_config, docx_file):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        sender = EmailSender(smtp_config)
        sender.send("recipient@example.com", "Subject", "Body", docx_file)

        mock_server.login.assert_called_once_with("user@example.com", "secret")

    @patch("flowtrack.reporting.email_sender.smtplib.SMTP")
    def test_smtp_sendmail_called_with_correct_addresses(self, mock_smtp_cls, smtp_config, docx_file):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        sender = EmailSender(smtp_config)
        sender.send("recipient@example.com", "Subject", "Body", docx_file)

        mock_server.sendmail.assert_called_once()
        args = mock_server.sendmail.call_args[0]
        assert args[0] == "user@example.com"
        assert args[1] == "recipient@example.com"

    @patch("flowtrack.reporting.email_sender.smtplib.SMTP")
    def test_smtp_quit_called(self, mock_smtp_cls, smtp_config, docx_file):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        sender = EmailSender(smtp_config)
        sender.send("recipient@example.com", "Subject", "Body", docx_file)

        mock_server.quit.assert_called_once()

    @patch("flowtrack.reporting.email_sender.smtplib.SMTP")
    def test_message_contains_subject_and_body(self, mock_smtp_cls, smtp_config, docx_file):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        sender = EmailSender(smtp_config)
        sender.send("recipient@example.com", "Weekly Report", "Here is your report.", docx_file)

        raw_msg = mock_server.sendmail.call_args[0][2]
        assert "Weekly Report" in raw_msg
        assert "Here is your report." in raw_msg

    @patch("flowtrack.reporting.email_sender.smtplib.SMTP")
    def test_message_contains_attachment_filename(self, mock_smtp_cls, smtp_config, docx_file):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        sender = EmailSender(smtp_config)
        sender.send("recipient@example.com", "Subject", "Body", docx_file)

        raw_msg = mock_server.sendmail.call_args[0][2]
        assert "report.docx" in raw_msg

    @patch("flowtrack.reporting.email_sender.smtplib.SMTP")
    def test_smtp_connects_to_configured_server_and_port(self, mock_smtp_cls, smtp_config, docx_file):
        sender = EmailSender(smtp_config)
        sender.send("recipient@example.com", "Subject", "Body", docx_file)

        mock_smtp_cls.assert_called_once_with("smtp.example.com", 587)


class TestEmailSenderFailure:
    """Tests for failure scenarios — errors logged, document retained."""

    @patch("flowtrack.reporting.email_sender.smtplib.SMTP")
    def test_connection_failure_returns_false(self, mock_smtp_cls, smtp_config, docx_file):
        mock_smtp_cls.side_effect = ConnectionRefusedError("Connection refused")

        sender = EmailSender(smtp_config)
        result = sender.send("recipient@example.com", "Subject", "Body", docx_file)

        assert result is False

    @patch("flowtrack.reporting.email_sender.smtplib.SMTP")
    def test_auth_failure_returns_false(self, mock_smtp_cls, smtp_config, docx_file):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failed")

        sender = EmailSender(smtp_config)
        result = sender.send("recipient@example.com", "Subject", "Body", docx_file)

        assert result is False

    @patch("flowtrack.reporting.email_sender.smtplib.SMTP")
    def test_send_failure_returns_false(self, mock_smtp_cls, smtp_config, docx_file):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server
        mock_server.sendmail.side_effect = smtplib.SMTPException("Send failed")

        sender = EmailSender(smtp_config)
        result = sender.send("recipient@example.com", "Subject", "Body", docx_file)

        assert result is False

    @patch("flowtrack.reporting.email_sender.smtplib.SMTP")
    def test_failure_retains_document_locally(self, mock_smtp_cls, smtp_config, docx_file):
        mock_smtp_cls.side_effect = ConnectionRefusedError("Connection refused")

        sender = EmailSender(smtp_config)
        sender.send("recipient@example.com", "Subject", "Body", docx_file)

        # Document should still exist after failure
        assert os.path.isfile(docx_file)

    @patch("flowtrack.reporting.email_sender.smtplib.SMTP")
    def test_failure_logs_error(self, mock_smtp_cls, smtp_config, docx_file, caplog):
        mock_smtp_cls.side_effect = ConnectionRefusedError("Connection refused")

        sender = EmailSender(smtp_config)
        with caplog.at_level("ERROR"):
            sender.send("recipient@example.com", "Subject", "Body", docx_file)

        assert "Failed to send email" in caplog.text
        assert docx_file in caplog.text

    def test_missing_attachment_returns_false(self, smtp_config):
        sender = EmailSender(smtp_config)
        result = sender.send("recipient@example.com", "Subject", "Body", "/nonexistent/file.docx")

        assert result is False

    @patch("flowtrack.reporting.email_sender.smtplib.SMTP")
    def test_quit_called_even_on_sendmail_failure(self, mock_smtp_cls, smtp_config, docx_file):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server
        mock_server.sendmail.side_effect = smtplib.SMTPException("Send failed")

        sender = EmailSender(smtp_config)
        sender.send("recipient@example.com", "Subject", "Body", docx_file)

        mock_server.quit.assert_called_once()
