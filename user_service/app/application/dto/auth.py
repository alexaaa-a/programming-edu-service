from dataclasses import dataclass


@dataclass
class AuthResultDTO:
    access_token: str | None
    refresh_token: str | None
    is_email_exists: bool
