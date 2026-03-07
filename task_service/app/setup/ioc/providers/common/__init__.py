from .di import SettingsProvider, LoggingProvider


common_provider = [
    SettingsProvider(),
    LoggingProvider()
]

__all__ = ["common_provider"]
