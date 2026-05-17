from dataclasses import dataclass, field


@dataclass
class EmailSendResult:
    success: bool
    provider_message_id: str = ""
    error_message: str = ""


class BaseEmailProvider:
    provider_name = "base"

    def send_email(self, *, to_email, from_email, subject, html_body="", text_body="", metadata=None):
        raise NotImplementedError
