from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    titles = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        422: "Unprocessable Content",
    }

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": "about:blank",
            "title": titles.get(exc.status_code, "HTTP Error"),
            "status": exc.status_code,
            "detail": exc.detail,
            "instance": request.url.path,
        },
        headers=exc.headers,
        media_type="application/problem+json",
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return JSON-safe validation errors without exposing submitted data."""

    errors = [
        {
            "type": error.get("type", "value_error"),
            "loc": list(error.get("loc", ())),
            "msg": error.get("msg", "Invalid input"),
        }
        for error in exc.errors()
    ]

    return JSONResponse(
        status_code=422,
        content={
            "type": "about:blank",
            "title": "Unprocessable Content",
            "status": 422,
            "detail": errors,
            "instance": request.url.path,
        },
        media_type="application/problem+json",
    )
