import re
from urllib.parse import urlparse

from fastapi import HTTPException

HEX_COLOR_REGEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
ALLOWED_URL_SCHEMES = {"http", "https"}
HTTP_422 = 422


def validate_hex_color(color: str, field_name: str = "color") -> str:
    """
    Validate that a color string is a 6-digit hex color code starting with '#'.
    Examples: #6366F1, #FFFFFF, #000000.
    Rejects: red, #123, #1234567, 123456.
    """
    if not isinstance(color, str) or not HEX_COLOR_REGEX.match(color.strip()):
        raise HTTPException(
            status_code=HTTP_422,
            detail=f"Invalid {field_name}: must be a 6-digit hex color starting with '#' (e.g. #6366F1)",
        )
    return color.strip()


def validate_avatar_url(url: str | None) -> str | None:
    """
    Validate that an avatar URL uses only http:// or https:// scheme
    and does not exceed 500 characters.
    Rejects: javascript:, data:, file:, relative paths.
    """
    if url is None:
        return None

    cleaned_url = url.strip()
    if not cleaned_url:
        return None

    if len(cleaned_url) > 500:
        raise HTTPException(
            status_code=HTTP_422,
            detail="Invalid avatar_url: URL length exceeds maximum limit of 500 characters.",
        )

    try:
        parsed = urlparse(cleaned_url)
        if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES or not parsed.netloc:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=HTTP_422,
            detail="Invalid avatar_url: must be a valid absolute http:// or https:// URL.",
        ) from None

    return cleaned_url


def validate_assistant_fields(data: dict) -> None:
    """
    Validate all assistant fields according to security and contract constraints.
    """
    if "brand_color" in data and data["brand_color"] is not None:
        validate_hex_color(data["brand_color"], "brand_color")

    if "text_color" in data and data["text_color"] is not None:
        validate_hex_color(data["text_color"], "text_color")

    if "avatar_url" in data:
        validate_avatar_url(data["avatar_url"])

    if "name" in data and data["name"] is not None:
        name = data["name"].strip()
        if not name:
            raise HTTPException(
                status_code=HTTP_422,
                detail="Assistant name cannot be empty.",
            )
        if len(name) > 100:
            raise HTTPException(
                status_code=HTTP_422,
                detail="Assistant name cannot exceed 100 characters.",
            )

    if "welcome_message" in data and data["welcome_message"] is not None:
        welcome = data["welcome_message"].strip()
        if not welcome:
            raise HTTPException(
                status_code=HTTP_422,
                detail="Welcome message cannot be empty.",
            )
        if len(welcome) > 1000:
            raise HTTPException(
                status_code=HTTP_422,
                detail="Welcome message cannot exceed 1000 characters.",
            )

    if "starter_prompt" in data and data["starter_prompt"] is not None and len(data["starter_prompt"]) > 500:
        raise HTTPException(
            status_code=HTTP_422,
            detail="Starter prompt cannot exceed 500 characters.",
        )

    if "description" in data and data["description"] is not None and len(data["description"]) > 1000:
        raise HTTPException(
            status_code=HTTP_422,
            detail="Description cannot exceed 1000 characters.",
        )

    if "system_instructions" in data and data["system_instructions"] is not None and len(data["system_instructions"]) > 5000:
        raise HTTPException(
            status_code=HTTP_422,
            detail="System instructions cannot exceed 5000 characters.",
        )
