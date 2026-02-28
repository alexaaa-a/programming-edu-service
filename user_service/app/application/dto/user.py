from dataclasses import dataclass


@dataclass
class UserDTO:
    user_id: int
    name: str
    surname: str
    username: str
    email: str
    password: str
    direction: str | None = None
    level: str | None = None


@dataclass
class UserRegisterDTO:
    name: str
    surname: str
    username: str
    email: str
    password: str


@dataclass
class UserLoginDTO:
    email: str
    password: str


@dataclass
class UserShowDTO:
    username: str
    name: str
    surname: str
    level: str | None
    direction: str | None
    email: str
