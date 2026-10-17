"""Glyphs for email, rasterised to PNG at runtime.

**Why not SVG, and why this module exists.** The badge and footer icons were first drawn as inline
SVG in a data URI, on the reasoning that a data URI is not a network request and so cannot be
blocked. That reasoning was wrong, and the proof arrived in a real inbox: every SVG rendered as an
empty box. Gmail strips SVG because it is a script-capable format, and most mail clients follow its
lead. PNG is what email actually supports - inline, via ``cid`` or as a data URI.

**Why not an image library.** Adding Pillow to a backend so it can draw six dots would be a
dependency bought for a very small job, and it would have to be trusted on the render path. The PNG
container is simple enough to write directly: ``zlib`` is in the standard library and the format is
zlib-compressed scanlines behind three small chunks.

**Why the rasteriser is hand-written.** Because the shapes needed are circles, rectangles, rings,
polygons and thick line segments, all of which reduce to a point-in-shape test. That is a few dozen
lines and it renders deterministically, so a tenant's mail cannot change because a library's
anti-aliasing changed between versions.

**Antialiasing** is 3x3 supersampling per pixel. Not the highest quality available and not meant to
be - these are 14 to 18 pixel glyphs, where the difference is invisible and the cost is not.

Colours are supplied per call rather than baked in, so a tenant's accent colour applies to the glyphs
as well as to the text.
"""

from __future__ import annotations

import base64
import math
import struct
import zlib
from collections.abc import Callable

#: Coverage is computed on this grid within each pixel, then averaged. Higher looks smoother and
#: costs more; at these sizes this is the point where it stops being visible.
SUPERSAMPLE = 3

#: A shape reports 1.0 inside and 0.0 outside. Returned per sample point in a 0..24 grid.
Shape = Callable[[float, float], float]


def _rounded_rect(x: float, y: float, w: float, h: float, r: float) -> Shape:
    def inside(px: float, py: float) -> float:
        cx = min(max(px, x + r), x + w - r)
        cy = min(max(py, y + r), y + h - r)
        return 1.0 if math.hypot(px - cx, py - cy) <= r else 0.0

    return inside


def _circle(cx: float, cy: float, r: float) -> Shape:
    def inside(px: float, py: float) -> float:
        return 1.0 if math.hypot(px - cx, py - cy) <= r else 0.0

    return inside


def _ellipse(cx: float, cy: float, rx: float, ry: float) -> Shape:
    def inside(px: float, py: float) -> float:
        return 1.0 if ((px - cx) / rx) ** 2 + ((py - cy) / ry) ** 2 <= 1.0 else 0.0

    return inside


def _ring(shape: Shape, thickness: float) -> Shape:
    """A hollow version of another shape, by shrinking it."""

    def inside(px: float, py: float) -> float:
        return shape(px, py) and not _scaled_out(shape, px, py, thickness)

    return inside


def _scaled_out(shape: Shape, px: float, py: float, thickness: float) -> bool:
    # Approximated by testing a point pushed toward the shape's own centre. Exact for circles and
    # rectangles, close enough for the rest at these sizes.
    for dx, dy in ((thickness, 0), (-thickness, 0), (0, thickness), (0, -thickness)):
        if shape(px + dx, py + dy):
            return False
    return True


def _segment(x1: float, y1: float, x2: float, y2: float, thickness: float) -> Shape:
    """A thick line with round caps - the workhorse for glyph strokes."""
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx * dx + dy * dy
    half = thickness / 2.0

    def inside(px: float, py: float) -> float:
        if length_sq == 0:
            t = 0.0
        else:
            t = ((px - x1) * dx + (py - y1) * dy) / length_sq
            t = min(max(t, 0.0), 1.0)
        cx, cy = x1 + t * dx, y1 + t * dy
        return 1.0 if math.hypot(px - cx, py - cy) <= half else 0.0

    return inside


def _polygon(points: list[tuple[float, float]]) -> Shape:
    def inside(px: float, py: float) -> bool:
        hit = False
        n = len(points)
        for i in range(n):
            x1, y1 = points[i]
            x2, y2 = points[(i + 1) % n]
            if (y1 > py) != (y2 > py):
                x_at = x1 + (py - y1) / (y2 - y1) * (x2 - x1)
                if px < x_at:
                    hit = not hit
        return hit

    return lambda px, py: 1.0 if inside(px, py) else 0.0


def _union(*shapes: Shape) -> Shape:
    return lambda px, py: 1.0 if any(s(px, py) for s in shapes) else 0.0


def _difference(outer: Shape, inner: Shape) -> Shape:
    return lambda px, py: 1.0 if (outer(px, py) and not inner(px, py)) else 0.0


def _png(width: int, height: int, pixels: bytearray) -> bytes:
    """A minimal RGBA PNG: signature, IHDR, one IDAT of zlib-compressed scanlines, IEND."""
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # filter type 0: none. Every row is incompressible enough already.
        raw.extend(pixels[y * stride : (y + 1) * stride])

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def render_glyph(shapes: list[Shape], size: int, colour: str) -> str:
    """Draw ``shapes`` on a 24x24 grid into a transparent PNG of ``size`` pixels, as a data URI.

    The grid is fixed at 24 and scaled at the end, so a glyph is authored once and drawn at whatever
    size the design calls for. Supersampled, so the result is not visibly stair-stepped.
    """
    r, g, b = _parse_hex(colour)
    pixels = bytearray(size * size * 4)
    step = 24.0 / size
    samples = SUPERSAMPLE * SUPERSAMPLE

    for py in range(size):
        for px in range(size):
            covered = 0
            for sy in range(SUPERSAMPLE):
                for sx in range(SUPERSAMPLE):
                    x = px * step + (sx + 0.5) * step / SUPERSAMPLE
                    y = py * step + (sy + 0.5) * step / SUPERSAMPLE
                    if any(shape(x, y) for shape in shapes):
                        covered += 1
            if covered == 0:
                continue
            alpha = round(255 * covered / samples)
            offset = (py * size + px) * 4
            pixels[offset : offset + 4] = bytes((r, g, b, alpha))

    uri = "data:image/png;base64," + base64.b64encode(_png(size, size, pixels)).decode("ascii")
    return uri


def _parse_hex(colour: str) -> tuple[int, int, int]:
    """``#RRGGBB`` only, with a neutral fallback.

    The caller's normaliser already rejects anything else, so this is a last-resort guard rather than
    validation: raising here would mean one odd colour turns into no email at all.
    """
    value = colour.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    if len(value) != 6:
        return (0x5F, 0x63, 0x68)
    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return (0x5F, 0x63, 0x68)


# ---------------------------------------------------------------------------
# The glyphs. Authored as primitives rather than as path data, because a scanline
# rasteriser has no path parser and every one of these is circles, bars and lines.
# ---------------------------------------------------------------------------

_CIRC = 24.0


def social_glyph(platform: str) -> list[Shape]:
    """The mark for one social platform, as drawable primitives.

    Simplified to the essential silhouette rather than reproduced from the trademark artwork. At 18
    pixels that is indistinguishable, and it avoids shipping someone else's exact vector data.
    """
    if platform == "facebook":
        # Stem offset to the right with the crossbar reaching left from it.
        #
        # Two earlier attempts failed and are worth recording. Adding a circle to suggest the hook
        # at the top made a lollipop, because at this size the circle is larger than the stroke it
        # was meant to blend into. Centring the stem and the crossbar on the same axis made a plus
        # sign - which is exactly what two equal bars across the same point look like. The crossbar
        # has to break the stem's centre line, and that is the whole of the mark.
        return [
            _union(
                _rounded_rect(12.6, 3.2, 3.6, 17.8, 1.0),
                _rounded_rect(6.6, 10.2, 10.2, 3.4, 0.8),
            )
        ]
    if platform == "instagram":
        return [
            _union(
                _difference(
                    _rounded_rect(3.0, 3.0, 18.0, 18.0, 5.0),
                    _rounded_rect(5.2, 5.2, 13.6, 13.6, 3.2),
                ),
                _circle(16.8, 7.2, 1.7),
            )
        ]
    if platform == "x":
        return [_segment(5.0, 5.0, 19.0, 19.0, 3.0), _segment(19.0, 5.0, 5.0, 19.0, 3.0)]
    if platform == "linkedin":
        return [
            _difference(
                _rounded_rect(3.0, 3.0, 18.0, 18.0, 2.4),
                _rounded_rect(4.6, 4.6, 14.8, 14.8, 1.4),
            ),
            _circle(8.0, 8.0, 1.7),
            _rounded_rect(6.4, 11.2, 3.4, 9.4, 0.5),
            _rounded_rect(11.0, 11.2, 3.2, 4.6, 0.5),
            _rounded_rect(15.6, 11.2, 3.4, 9.4, 0.5),
        ]
    if platform == "youtube":
        return [
            _difference(
                _rounded_rect(2.0, 5.0, 20.0, 14.0, 4.4),
                _rounded_rect(4.0, 7.0, 16.0, 10.0, 2.6),
            ),
            _polygon([(9.8, 8.4), (9.8, 15.6), (16.2, 12.0)]),
        ]
    if platform == "tiktok":
        # Stem into an open bowl, plus the flag at the top. An earlier version had a second bowl
        # above the stem to suggest the hook, and the pair read as a key rather than a note.
        return [
            _union(
                _rounded_rect(9.2, 3.0, 3.0, 13.4, 1.2),
                _difference(_circle(14.2, 17.4, 4.4), _circle(14.2, 17.4, 2.0)),
            )
        ]
    raise KeyError(platform)


def contact_glyph(kind: str) -> list[Shape]:
    """The glyph beside a contact value: globe, envelope or handset."""
    if kind == "website":
        return [
            _difference(_circle(12.0, 12.0, 9.0), _circle(12.0, 12.0, 7.4)),
            _difference(_ellipse(12.0, 12.0, 4.0, 9.0), _ellipse(12.0, 12.0, 2.4, 9.0)),
            _segment(3.4, 12.0, 20.6, 12.0, 1.4),
        ]
    if kind == "email":
        return [
            _difference(
                _rounded_rect(3.0, 5.6, 18.0, 12.8, 1.6),
                _rounded_rect(4.6, 7.2, 14.8, 9.6, 0.8),
            ),
            _segment(3.8, 6.4, 12.0, 13.0, 1.5),
            _segment(20.2, 6.4, 12.0, 13.0, 1.5),
        ]
    if kind == "phone":
        # A mobile, not a handset.
        #
        # The handset silhouette is a curve, and at 14 pixels this rasteriser turned it into a pin -
        # a diagonal line with a dot at each end, which reads as a location marker rather than a
        # telephone. The mobile glyph is unambiguous at that size, and it is the symbol most
        # transactional footers actually use next to a number.
        return [
            _difference(
                _rounded_rect(6.8, 2.2, 10.4, 19.6, 2.6),
                _rounded_rect(8.4, 4.8, 7.2, 12.4, 0.8),
            ),
            _circle(12.0, 19.2, 1.0),
        ]
    raise KeyError(kind)


__all__ = ["contact_glyph", "render_glyph", "social_glyph"]