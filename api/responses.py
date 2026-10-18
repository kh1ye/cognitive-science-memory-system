"""Shared API response helpers."""

from fastapi.responses import JSONResponse


def error_response(message: str, status: int = 400, error: str = "validation_error"):
    return JSONResponse({"error": error, "message": message}, status_code=status)
