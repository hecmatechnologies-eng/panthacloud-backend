"""Domain exceptions for authentication and registration."""


class AuthServiceError(Exception):
    """Base exception for all authentication service domain errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UserAlreadyExistsError(AuthServiceError):
    """Raised when registering with an email that is already registered."""

    def __init__(
        self,
        message: str = "A user with this email address already exists.",
        field: str = "email",
    ) -> None:
        super().__init__(message)
        self.field = field


class InvalidCredentialsError(AuthServiceError):
    """Raised when authentication fails due to incorrect email or password."""

    def __init__(self, message: str = "Invalid email or password.") -> None:
        super().__init__(message)


class InactiveUserError(AuthServiceError):
    """Raised when authentication or access is attempted on a deactivated account."""

    def __init__(self, message: str = "User account is inactive.") -> None:
        super().__init__(message)


class CredentialsMissingError(AuthServiceError):
    """Raised when credentials are required but not provided."""

    def __init__(self, message: str = "Authentication credentials were not provided.") -> None:
        super().__init__(message)


class TokenExpiredError(AuthServiceError):
    """Raised when an authentication token has expired."""

    def __init__(self, message: str = "Authentication token has expired.") -> None:
        super().__init__(message)


class InvalidTokenError(AuthServiceError):
    """Raised when a token cannot be validated or is missing required claims."""

    def __init__(self, message: str = "Could not validate authentication credentials.") -> None:
        super().__init__(message)


class UserNotFoundError(AuthServiceError):
    """Raised when an authenticated subject is not found in the system."""

    def __init__(self, message: str = "User not found.") -> None:
        super().__init__(message)
