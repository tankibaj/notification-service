import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

logger = logging.getLogger(__name__)


class SMTPClient:
    def __init__(self, host: str, port: int, sender: str) -> None:
        self.host = host
        self.port = port
        self.sender = sender

    async def send_email(self, to: str, subject: str, html_body: str) -> None:
        message = MIMEMultipart("alternative")
        message["From"] = self.sender
        message["To"] = to
        message["Subject"] = subject
        message.attach(MIMEText(html_body, "html"))

        await aiosmtplib.send(
            message,
            hostname=self.host,
            port=self.port,
            use_tls=False,
        )
        logger.info(
            "Email sent successfully",
            extra={"to_domain": to.split("@")[-1] if "@" in to else "unknown"},
        )
