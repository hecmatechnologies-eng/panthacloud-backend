"""Location header for 201 responses.

RFC 9110 §15.3.2 says a 201 SHOULD carry a Location naming the resource that was created. One
helper rather than twelve inline header writes, so the prefix is defined once and a future
change of mount point is a one-line edit instead of twelve.

The path passed in is relative to the API root, which is how the routers are addressed internally;
this adds the public prefix.
"""

from fastapi import Response

API_ROOT = "/api/v1"

# Declare the header in the schema as well as setting it at runtime. The two do different jobs:
# this is what a client reading /openapi.json sees, and what the conformance gate checks;
# `created()` is what actually goes over the wire. Setting only the runtime header satisfies
# RFC 9110 while leaving the published contract silent about it.
CREATED_RESPONSE = {
    201: {
        "description": "Created",
        "headers": {
            "Location": {
                "description": "URI of the created resource.",
                "schema": {"type": "string"},
            }
        },
    }
}


def created(response: Response, *segments: str) -> None:
    """Set Location on a 201. Segments are path parts and must already be URL-safe.

    id: str
        The identifier of the thing just created.
    """
    tail = "/".join(s for s in segments if s)
    response.headers["Location"] = f"{API_ROOT}/{tail}" if tail else API_ROOT