import logging.config

from agent_service.app.config import Settings


class LoggingConfigurator:
    @staticmethod
    def setup(settings: Settings) -> None:
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
            "loggers": {"": {"handlers": ["stdout"], "level": settings.logging_settings.level}},
        }
        logging.config.dictConfig(logging_config)


def setup_logging(settings: Settings) -> None:
    LoggingConfigurator.setup(settings)

