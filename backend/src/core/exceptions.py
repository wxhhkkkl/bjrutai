from typing import Any, Optional


class AppException(Exception):
    """Base application exception with structured error metadata."""

    def __init__(
        self,
        code: int = 50000,
        message: str = "Internal server error",
        status_code: int = 500,
        error_type: str = "internal_error",
        retryable: bool = False,
        detail: Optional[Any] = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.error_type = error_type
        self.retryable = retryable
        self.detail = detail
        super().__init__(message)


class NotFoundException(AppException):
    """Resource not found."""

    def __init__(self, message: str = "Resource not found", detail: Optional[Any] = None, code: Optional[int] = None) -> None:
        super().__init__(
            code=code if code is not None else 40400,
            message=message,
            status_code=404,
            error_type="not_found",
            detail=detail,
        )


class UnauthorizedException(AppException):
    """Authentication required or invalid credentials."""

    def __init__(self, message: str = "Unauthorized", detail: Optional[Any] = None) -> None:
        super().__init__(
            code=40100,
            message=message,
            status_code=401,
            error_type="unauthorized",
            detail=detail,
        )


class ForbiddenException(AppException):
    """Insufficient permissions."""

    def __init__(self, message: str = "Forbidden", detail: Optional[Any] = None) -> None:
        super().__init__(
            code=40300,
            message=message,
            status_code=403,
            error_type="forbidden",
            detail=detail,
        )


class ConflictException(AppException):
    """Resource conflict (e.g. duplicate)."""

    def __init__(self, message: str = "Conflict", detail: Optional[Any] = None, code: Optional[int] = None) -> None:
        super().__init__(
            code=code if code is not None else 40900,
            message=message,
            status_code=409,
            error_type="conflict",
            detail=detail,
        )


class ValidationException(AppException):
    """Request validation failure."""

    def __init__(self, message: str = "Validation error", detail: Optional[Any] = None) -> None:
        super().__init__(
            code=42200,
            message=message,
            status_code=422,
            error_type="validation_error",
            detail=detail,
        )


class BadRequestException(AppException):
    """Generic bad request."""

    def __init__(self, message: str = "Bad request", detail: Optional[Any] = None, code: Optional[int] = None) -> None:
        super().__init__(
            code=code if code is not None else 40000,
            message=message,
            status_code=400,
            error_type="bad_request",
            detail=detail,
        )
