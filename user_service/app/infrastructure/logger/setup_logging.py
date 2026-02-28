from logging.config import dictConfig

from user_service.app.config import Settings


def setup_logging(settings: Settings) -> None:
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "format": "%(asctime)s %(levelname)s %(message)s %(module)s",
                "datefmt": "%Y-%m-%dT%H:%M:%SZ",
                "class": "pythonjsonlogger.jsonlogger.JsonFormatter",
            }
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "json",
            }
        },
        "loggers": {
            "": {
                "handlers": ["stdout"],
                "level": settings.logging_settings.level,
            },
        },
    }
    dictConfig(logging_config)
