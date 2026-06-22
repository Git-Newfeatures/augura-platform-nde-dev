from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

log = structlog.get_logger(__name__)


class AppError(Exception):
    """Erreur applicative de base. Sous-classer, ne jamais lever directement."""

    code: str = "app_error"
    http_status: int = 500
    title: str = "Application error"

    def __init__(self, detail: str, **context: Any) -> None:
        super().__init__(detail)
        self.detail = detail
        self.context = context


class NotFoundError(AppError):
    code = "not_found"
    http_status = 404
    title = "Resource not found"


class BadRequestError(AppError):
    code = "bad_request"
    http_status = 400
    title = "Bad request"


class UnauthorizedError(AppError):
    code = "unauthorized"
    http_status = 401
    title = "Unauthorized"


class ForbiddenError(AppError):
    code = "forbidden"
    http_status = 403
    title = "Forbidden"


class ConflictError(AppError):
    code = "conflict"
    http_status = 409
    title = "Conflict"


class PayloadTooLargeError(AppError):
    code = "payload_too_large"
    http_status = 413
    title = "Payload too large"


class UnsupportedMediaTypeError(AppError):
    code = "unsupported_media_type"
    http_status = 415
    title = "Unsupported media type"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        body: dict[str, Any] = {
            "type": f"https://augura.dev/errors/{exc.code}",
            "title": exc.title,
            "status": exc.http_status,
            "detail": exc.detail,
            "code": exc.code,
        }
        if exc.context:
            body["context"] = exc.context
        return JSONResponse(
            status_code=exc.http_status,
            content=body,
            media_type="application/problem+json",
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_db_error(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
        # Une erreur base non mappée (violation RLS, contrainte, panne) remonterait sinon
        # en 500 brut AU-DESSUS du middleware CORS (généré par ServerErrorMiddleware) :
        # le navigateur la lit alors « Failed to fetch » sans en-tête CORS, donc sans
        # message. En la rattrapant ici (ExceptionMiddleware, sous CORS) la réponse
        # repasse par CORS et le front voit une vraie erreur 500.
        log.exception("db_error", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "type": "https://augura.dev/errors/database_error",
                "title": "Database error",
                "status": 500,
                "detail": "l'opération base de données a échoué",
                "code": "database_error",
            },
            media_type="application/problem+json",
        )
