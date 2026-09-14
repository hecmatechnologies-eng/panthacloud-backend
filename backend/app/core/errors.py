import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.services.auth.exceptions import (
    AuthServiceError,
    CredentialsMissingError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
    TokenExpiredError,
    UserAlreadyExistsError,
    UserNotFoundError,
)

logger = logging.getLogger("fussion.errors")


def create_error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    content: dict[str, Any] = {
        "detail": message,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details is not None:
        content["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=content, headers=headers)



def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        code_map = {
            status.HTTP_404_NOT_FOUND: "NOT_FOUND",
            status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
            status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
            status.HTTP_402_PAYMENT_REQUIRED: "PAYMENT_REQUIRED",
            status.HTTP_403_FORBIDDEN: "FORBIDDEN",
            status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
            status.HTTP_413_CONTENT_TOO_LARGE: "PAYLOAD_TOO_LARGE",
            status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
            status.HTTP_422_UNPROCESSABLE_CONTENT: "UNPROCESSABLE_CONTENT",
            status.HTTP_502_BAD_GATEWAY: "BAD_GATEWAY",
            status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
            status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_SERVER_ERROR",
        }
        error_code = code_map.get(exc.status_code, "HTTP_ERROR")
        details = None

        if isinstance(exc.detail, dict):
            error_code = exc.detail.get("code", error_code)
            message = str(exc.detail.get("message", exc.detail))
            details = exc.detail.get("details", None)
            if details is None and "field" in exc.detail:
                details = [
                    {
                        "field": exc.detail["field"],
                        "issue": error_code,
                        "message": message,
                    }
                ]
        else:
            message = str(exc.detail)

        return create_error_response(
            status_code=exc.status_code,
            code=error_code,
            message=message,
            details=details,
            # Preserve headers the raise site attached — Retry-After on 429, WWW-Authenticate on
            # 401. The JSONResponse this builds would otherwise drop them.
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return create_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="VALIDATION_ERROR",
            message="Request validation failed",
            # A field_validator's ValueError sits in each error's ctx; encode it as FastAPI does.
            # "input" is dropped: it echoes back what the caller sent, which for a rejected
            # github_token would put a credential in the response body.
            details=[
                {key: value for key, value in error.items() if key != "input"}
                for error in jsonable_encoder(exc.errors())
            ],
        )

    @app.exception_handler(UserAlreadyExistsError)
    async def user_already_exists_handler(request: Request, exc: UserAlreadyExistsError):
        return create_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            message=exc.message,
            details=[{"loc": ["body", exc.field], "msg": exc.message}],
        )

    @app.exception_handler(InvalidCredentialsError)
    async def invalid_credentials_handler(request: Request, exc: InvalidCredentialsError):
        return create_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(InactiveUserError)
    async def inactive_user_handler(request: Request, exc: InactiveUserError):
        return create_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(CredentialsMissingError)
    async def credentials_missing_handler(request: Request, exc: CredentialsMissingError):
        return create_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(TokenExpiredError)
    async def token_expired_handler(request: Request, exc: TokenExpiredError):
        return create_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(InvalidTokenError)
    async def invalid_token_handler(request: Request, exc: InvalidTokenError):
        return create_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(UserNotFoundError)
    async def user_not_found_handler(request: Request, exc: UserNotFoundError):
        return create_error_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(AuthServiceError)
    async def auth_service_error_handler(request: Request, exc: AuthServiceError):
        return create_error_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="BAD_REQUEST",
            message=exc.message,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled server exception: %s", exc)
        return create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected error occurred. Please try again later.",
        )
