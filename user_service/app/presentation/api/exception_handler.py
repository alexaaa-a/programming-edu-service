import json
import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from starlette.responses import Response


logger = logging.getLogger(__name__)


def _error_payload(exc: Exception, default_message: str) -> dict[str, str]:
    error_code = getattr(exc, "code", exc.__class__.__name__)
    message = str(exc) or default_message
    return {"error": str(error_code), "message": message}


def unhandled_exception_handler(_: Request, exc: Exception) -> Response:
    logger.exception("Необработанная ошибка API", exc_info=exc)
    return Response(
        content=json.dumps(_error_payload(exc, "Внутренняя ошибка сервера.")),
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        media_type="application/json",
    )


def setup_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(Exception, unhandled_exception_handler)
