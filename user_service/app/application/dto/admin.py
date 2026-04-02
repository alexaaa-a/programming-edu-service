from dataclasses import dataclass


@dataclass
class AdminDTO:
    user_id: int
    role: str
