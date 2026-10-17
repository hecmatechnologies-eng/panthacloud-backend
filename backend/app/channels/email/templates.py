"""Rendering a reply as branded HTML alongside its plain-text twin.

**Why HTML at all.** A guest assistant that answers *"what time is check-out?"* in an unbranded wall
of plain text reads as a bot that found the address somewhere. Adding a header, the hotel's details
and a way to stop the mail makes it read as correspondence from a front desk, which is what it is.

**This has no effect on spam placement, and the distinction matters.** Whether a message lands in the
inbox is decided by the sending pool's reputation. What the message says and looks like is a
separate, much smaller input. Anyone who reaches for a template expecting the junk folder to clear
will be disappointed, and it is better to say so in the module that implements it than to let the
intention pass unchallenged.

**The plain-text version is not optional.** Every reply is sent with both ``text`` and ``html``, never
one or the other. Text-only scores marginally better with some filters, and it is what a guest with
images blocked, a screen reader, or a 2008 phone actually reads. HTML is an addition, never a
replacement.

**What the HTML has to survive.** Email clients are not browsers. Outlook's Word rendering engine
ignores ``<style>`` blocks, strips ``<div>`` margins, and handles padding inconsistently. So:

- Every style is an inline ``style`` attribute. There is no ``<style>`` block, because Outlook
  ignores it and Gmail strips it inconsistently.
- Layout is tables with ``cellpadding``/``cellspacing``/``border`` attributes set, not CSS. Those are
  presentational attributes and are how layout was specified before CSS; they still work everywhere.
- Widths are fixed pixels with a ``max-width``, never percentages for the outer shell, because a
  percentage outer width renders at anything from 300px to 1600px depending on the client.
- No external CSS, no web fonts, no ``<script>``, no SVG. Every one of those is stripped or blocked,
  and the message must still look right when all of them fail.

**Escaping is the security boundary.** The body is model output that has already passed the outbound
guardrail, and it is interleaved with tenant-supplied branding. Both are escaped independently
before being placed in the document: a tenant's tagline containing ``<`` and a model mentioning a
tag-like string must neither be able to inject markup. The one exception is deliberate and narrow -
newlines in the body become ``<br>`` - so the only transformation is whitespace, and nothing else can
survive it.
"""

import html
import re
from dataclasses import dataclass, field

from app.models.project_branding import SOCIAL_PLATFORMS, ProjectBranding

#: The content well. Narrow enough to read comfortably in Outlook, wide enough not to wrap a rate.
CONTENT_WIDTH = 560

#: Plain, legible fallback accent. Deliberately not a brand colour: a tenant who chose none should
#: see neutral ink, not someone else's identity.
DEFAULT_ACCENT = "#8A6A3B"

#: Readable grey for the small print. Checked for contrast against white at 4.5:1 or better.
MUTED = "#5F6368"

_HEX_COLOUR = re.compile(r"^#[0-9A-Fa-f]{6}$")

#: Platform -> the label a reader sees. Text rather than icon glyphs on purpose: a social icon is
#: either an image (blocked by default in many clients) or a font a client does not have.
_SOCIAL_LABELS = {
    "facebook": "Facebook",
    "instagram": "Instagram",
    "x": "X",
    "linkedin": "LinkedIn",
    "youtube": "YouTube",
    "tiktok": "TikTok",
}


@dataclass(frozen=True, slots=True)
class Branding:
    """A resolved, validated brand, ready to render.

    A separate frozen type rather than the ORM row, for two reasons: rendering must not depend on a
    live session, and the normalisation that makes a half-filled form renderable (missing accent,
    stray spaces, a colour typed without its ``#``) has to happen once, in one place, rather than at
    every place the values are read.
    """

    business_name: str
    tagline: str | None = None
    logo_url: str | None = None
    accent_colour: str = DEFAULT_ACCENT
    postal_address: str | None = None
    phone: str | None = None
    contact_email: str | None = None
    website: str | None = None
    social_links: dict[str, str] = field(default_factory=dict)
    footer_note: str | None = None

    @property
    def has_contact_details(self) -> bool:
        """Whether the footer has anything worth printing.

        A footer with an empty line where a phone number should be looks worse than no footer, so it
        is suppressed rather than rendered half-empty.
        """
        return any(
            v for v in (self.postal_address, self.phone, self.contact_email, self.website)
        ) or bool(self.social_links)

    @property
    def initials(self) -> str:
        """Up to two initials, used when there is no logo.

        Better than an empty box or a broken image icon, and it is what most small businesses would
        choose anyway.
        """
        words = [w for w in re.split(r"\W+", self.business_name) if w]
        if not words:
            return "?"
        if len(words) == 1:
            return words[0][:2].upper()
        return (words[0][0] + words[1][0]).upper()


def normalise_colour(value: str | None) -> str:
    """A safe accent colour from anything a tenant might type.

    Accepts an uppercase hex with or without ``#``; anything else falls back to the neutral default
    rather than raising. A wrong colour should cost a tenant their accent, not their ability to send
    mail.
    """
    if not value:
        return DEFAULT_ACCENT
    candidate = value.strip()
    if not candidate.startswith("#"):
        candidate = f"#{candidate}"
    return candidate if _HEX_COLOUR.match(candidate) else DEFAULT_ACCENT


def branding_from_row(row: ProjectBranding | None) -> Branding | None:
    """Normalise a stored row into a renderable brand, or None when there is none.

    None is meaningful and handled by the caller: a project with no branding still gets a reply, just
    an unbranded one. Failing to send because a tenant has not branded themselves yet would be the
    wrong trade.
    """
    if row is None:
        return None
    social: dict[str, str] = {}
    raw = row.social_links or {}
    for platform, url in raw.items():
        # Unknown keys dropped rather than rendered: the label set is closed, and a URL in an
        # unlabelled slot would print as a bare link in the footer.
        if platform in SOCIAL_PLATFORMS and isinstance(url, str) and url.strip():
            social[platform] = url.strip()
    return Branding(
        business_name=row.business_name,
        tagline=(row.tagline or "").strip() or None,
        logo_url=(row.logo_url or "").strip() or None,
        accent_colour=normalise_colour(row.accent_colour),
        postal_address=(row.postal_address or "").strip() or None,
        phone=(row.phone or "").strip() or None,
        contact_email=(row.contact_email or "").strip() or None,
        website=(row.website or "").strip() or None,
        social_links=social,
        footer_note=(row.footer_note or "").strip() or None,
    )


def escape(text: str) -> str:
    return html.escape(text, quote=True)


def body_to_html(text: str) -> str:
    """Escape a reply body, then turn its newlines into line breaks.

    Order matters: escaping first means the only markup that exists is the ``<br>`` added afterwards.
    Doing it the other way round would escape the breaks and produce one long line.
    """
    escaped = escape(text.strip())
    # Two trailing spaces are a hard break in plain text; preserve that intent.
    escaped = escaped.replace("  \n", "<br>\n")
    return escaped.replace("\n", "<br>")


def _paragraphs(text: str) -> str:
    """The body, split into paragraphs."""
    chunks = [c.strip() for c in re.split(r"\n\s*\n", text.strip()) if c.strip()]
    return "".join(
        f'<p style="margin:0 0 14px 0;font-size:16px;line-height:26px;color:#202124;">'
        f"{body_to_html(chunk)}</p>"
        for chunk in chunks
    )


def _social_row(branding: Branding) -> str:
    if not branding.social_links:
        return ""
    links = " &nbsp; ".join(
        f'<a href="{escape(url)}" style="color:{escape(branding.accent_colour)};'
        f'text-decoration:none;font-size:13px;font-weight:600;">'
        f"{escape(_SOCIAL_LABELS[platform])}</a>"
        for platform, url in branding.social_links.items()
    )
    return (
        f'<p style="margin:0 0 12px 0;font-size:13px;line-height:20px;">{links}</p>'
    )


def _contact_block(branding: Branding) -> str:
    lines: list[str] = []
    if branding.website:
        lines.append(
            f'<a href="{escape(branding.website)}" '
            f'style="color:{escape(MUTED)};text-decoration:none;">{escape(branding.website)}</a>'
        )
    if branding.contact_email:
        lines.append(escape(branding.contact_email))
    if branding.phone:
        lines.append(escape(branding.phone))
    if branding.postal_address:
        lines.append(escape(branding.postal_address))
    if not lines:
        return ""
    body = "<br>".join(lines)
    return f'<p style="margin:0 0 12px 0;font-size:13px;line-height:20px;color:{MUTED};">{body}</p>'


def _header(branding: Branding) -> str:
    if branding.logo_url:
        mark = (
            f'<img src="{escape(branding.logo_url)}" alt="{escape(branding.business_name)}" '
            f'width="64" height="64" style="display:block;border:0;width:64px;height:64px;" />'
        )
    else:
        # A text badge rather than an image: no request to a third party, nothing to block, and it
        # still looks deliberate in a client that strips images.
        mark = (
            f'<div style="font-size:26px;font-weight:700;color:#FFFFFF;'
            f'background-color:{escape(branding.accent_colour)};width:64px;height:64px;'
            f'line-height:64px;text-align:center;">{escape(branding.initials)}</div>'
        )

    tagline = (
        f'<p style="margin:4px 0 0 0;font-size:14px;line-height:20px;color:{MUTED};">'
        f"{escape(branding.tagline)}</p>"
        if branding.tagline
        else ""
    )
    return (
        f'<tr><td style="padding:24px 24px 20px 24px;background-color:#F7F5F2;'
        f'border-top:4px solid {escape(branding.accent_colour)};">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        f'<tr><td style="vertical-align:middle;width:64px;">{mark}</td>'
        f'<td style="vertical-align:middle;padding-left:16px;">'
        f'<p style="margin:0;font-size:20px;line-height:26px;font-weight:700;color:#202124;">'
        f"{escape(branding.business_name)}</p>{tagline}</td></tr></table></td></tr>"
    )


def _footer(branding: Branding) -> str:
    if not branding.has_contact_details and not branding.footer_note:
        return ""
    note = (
        f'<p style="margin:0 0 12px 0;font-size:13px;line-height:20px;color:{MUTED};">'
        f"{escape(branding.footer_note)}</p>"
        if branding.footer_note
        else ""
    )
    return (
        f'<tr><td style="padding:20px 24px 24px 24px;border-top:1px solid #E3E0DC;'
        f'background-color:#FAF9F8;">{note}{_contact_block(branding)}{_social_row(branding)}</td></tr>'
    )


def render_html(body: str, branding: Branding | None) -> str:
    """One reply as a complete HTML document, or an empty string when there is no branding.

    Returning ``""`` rather than an unstyled document is deliberate: an unbranded project should send
    plain text and nothing else, not a bare white page that looks like a broken template.
    """
    if branding is None:
        return ""

    # `dir="ltr"`/`lang` because this is English business correspondence and Outlook's renderer will
    # otherwise guess per-line; the outer table is `role="presentation"` because a screen reader
    # should not announce layout as content.
    return f"""<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="color-scheme" content="light" />
<title>{escape(branding.business_name)}</title>
</head>
<body style="margin:0;padding:0;background-color:#EFEDE9;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
 style="background-color:#EFEDE9;">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="{CONTENT_WIDTH}" cellpadding="0" cellspacing="0" border="0"
 style="width:{CONTENT_WIDTH}px;max-width:{CONTENT_WIDTH}px;background-color:#FFFFFF;
 border-radius:8px;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',
 Roboto,Helvetica,Arial,sans-serif;">
{_header(branding)}
<tr><td style="padding:28px 24px 8px 24px;">{_paragraphs(body)}</td></tr>
{_footer(branding)}
</table>
</td></tr>
</table>
</body>
</html>"""


def render_text(body: str, branding: Branding | None) -> str:
    """The plain-text twin, with a signature block appended.

    This is the version that decides whether a reply reads as a desk or as a robot, because it is
    what a client shows when images are blocked and what most people actually read first. The
    separator is ``-- ``, the RFC 3676 signature marker, because that is what tells a mail client
    where the human-written part ends.
    """
    if branding is None:
        return body

    lines: list[str] = []
    if branding.has_contact_details or branding.footer_note:
        lines.append("")
        lines.append("-- ")
        lines.append(f"{branding.business_name}" + (f" · {branding.tagline}" if branding.tagline else ""))
        if branding.footer_note:
            lines.append(branding.footer_note)
        for value in (branding.website, branding.contact_email, branding.phone, branding.postal_address):
            if value:
                lines.append(value)
        if branding.social_links:
            lines.append(
                " · ".join(
                    f"{_SOCIAL_LABELS[p]}: {u}" for p, u in branding.social_links.items()
                )
            )
    return body + "\n".join(lines)


__all__ = [
    "CONTENT_WIDTH",
    "DEFAULT_ACCENT",
    "Branding",
    "body_to_html",
    "branding_from_row",
    "escape",
    "normalise_colour",
    "render_html",
    "render_text",
]