from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from grok_bot.api.routes.auth import router as auth_router
from grok_bot.api.routes.health import router as health_router
from grok_bot.api.routes.me import router as me_router
from grok_bot.api.routes.properties import router as properties_router
from grok_bot.api.routes.units import router as units_router
from grok_bot.db import build_engine
from grok_bot.settings import Settings


def create_app(settings: Settings, *, pool_size: int = 5, max_overflow: int = 5) -> FastAPI:
    app = FastAPI(title="Grok Bot API", version="0.1.0")
    app.state.settings = settings
    app.state.engine = build_engine(settings.database_url, pool_size=pool_size, max_overflow=max_overflow)
    if settings.allows_local_auth:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "If-Match", "X-Request-Id"],
            expose_headers=["X-Request-Id", "ETag", "Idempotency-Status"],
        )
        app.include_router(auth_router, prefix="/v1")
    app.include_router(health_router, prefix="/v1")
    app.include_router(me_router, prefix="/v1")
    app.include_router(properties_router, prefix="/v1")
    app.include_router(units_router, prefix="/v1")

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or f"req_{uuid4().hex}"
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        if not detail:
            code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
            message = str(exc.detail)
            details: dict = {}
            retryable = False
        else:
            code = detail.get("code", "HTTP_ERROR")
            message = detail.get("message", "Request failed.")
            details = detail.get("details") or {}
            retryable = bool(detail.get("retryable", False))
        return _error_response(request, exc.status_code, code, message, details, retryable)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return _error_response(
            request,
            422,
            "VALIDATION_ERROR",
            "The request is invalid.",
            {"errors": _public_errors(exc.errors())},
            False,
        )

    @app.exception_handler(IntegrityError)
    async def integrity_handler(request: Request, exc: IntegrityError):
        return _error_response(
            request,
            409,
            "CONSTRAINT_VIOLATION",
            "The request conflicts with an existing record.",
            {},
            False,
        )

    return app


def _error_response(request: Request, status: int, code: str, message: str, details: dict, retryable: bool):
    request_id = getattr(request.state, "request_id", None) or f"req_{uuid4().hex}"
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "retryable": retryable,
            },
            "request_id": request_id,
        },
        headers={"X-Request-Id": request_id},
    )


def _public_errors(errors: list) -> list[dict]:
    public = []
    for error in errors:
        public.append({"loc": [str(part) for part in error.get("loc", ())], "msg": error.get("msg", "invalid")})
    return public
