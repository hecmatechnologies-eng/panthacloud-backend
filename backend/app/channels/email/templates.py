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

from app.channels.email.icons import contact_glyph, render_glyph, social_glyph
from app.models.project_branding import SOCIAL_PLATFORMS, ProjectBranding

#: The content well. Narrow enough to read comfortably in Outlook, wide enough not to wrap a rate.
CONTENT_WIDTH = 560

#: Plain, legible fallback accent. Deliberately not a brand colour: a tenant who chose none should
#: see neutral ink, not someone else's identity.
DEFAULT_ACCENT = "#8A6A3B"

#: Readable grey for the small print. Checked for contrast against white at 4.5:1 or better.
MUTED = "#5F6368"

_HEX_COLOUR = re.compile(r"^#[0-9A-Fa-f]{6}$")

#: Platform -> the label a reader sees in the plain-text version, where an image cannot help.
_SOCIAL_LABELS = {
    "facebook": "Facebook",
    "instagram": "Instagram",
    "x": "X",
    "linkedin": "LinkedIn",
    "youtube": "YouTube",
    "tiktok": "TikTok",
}

def _icon_img(uri: str, size: int, title: str | None = None) -> str:
    """Any glyph as an inline image, so it needs no network request to render.

    Shared by the social marks and the contact-detail icons because the hard parts are identical: a
    data URI rather than a hosted file, so a client that blocks remote images still shows them, and
    ``alt=""`` so nothing lands in the message snippet. The name rides on ``title``, which a screen
    reader and a hover both pick up - ``alt`` is deliberately left empty because these glyphs are
    decorative next to the visible value they sit beside.
    """
    title_attr = f' title="{escape(title)}"' if title else ""
    return (
        f'<img src="{uri}" alt=""{title_attr} width="{size}" height="{size}" '
        f'style="display:inline-block;border:0;width:{size}px;height:{size}px;" />'
    )


def _social_icon(platform: str, colour: str) -> str:
    """One social mark, wearing the brand colour because it *is* the brand."""
    return _icon_img(render_glyph(social_glyph(platform), 36, colour), 18, _SOCIAL_LABELS[platform])


_CONTACT_ICON_SIZE = 14


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


#: A citation marker: a bracketed number.
#:
#: Stripped from anything a guest sees. The numbers are stored on the message for audit and so the
#: staff inbox can cross-check a claim, but a guest cannot look up "[10]" and it reads as either a
#: mistake or a leaked internal id - exactly the impression a branded, professional email is meant
#: to avoid.
_CITATION = re.compile(r"\s*\[(\d{1,3})\]")

#: Assumed number of sources when the caller does not say.
#:
#: Deliberately small, because the fallback has to be *too narrow* rather than too wide: a marker
#: above this survives and reaches a guest, which is a cosmetic flaw, whereas a rule wide enough to
#: swallow a year would silently edit a sentence the assistant actually wrote. Real citations are
#: bounded by ``RETRIEVAL_MAX_CHUNKS``.
_ASSUMED_SOURCE_COUNT = 32


def strip_citations(text: str, source_count: int | None = None) -> str:
    """Remove provenance markers from guest-facing text, leaving the stored record intact.

    ``source_count`` is how many numbered sources were actually handed to the model, and it is what
    makes this precise rather than a guess. The numbers in "[1]" are positions in the context we
    built, not dates or measurements, so a marker is only a citation if it is within range.

    Getting that wrong is not hypothetical. A first attempt stripped any ``[digits]``, which ate
    ``Rates for [2024] were higher`` - a perfectly ordinary sentence about a hotel - and would have
    quietly rewritten the assistant's answer. Range-checking is what separates the two.
    """
    limit = _ASSUMED_SOURCE_COUNT if source_count is None else source_count

    def replace(match: re.Match[str]) -> str:
        return "" if 1 <= int(match.group(1)) <= limit else match.group(0)

    return _CITATION.sub(replace, text).strip()


def body_to_html(text: str) -> str:
    """Escape a reply body, then turn its newlines into line breaks.

    Order matters: escaping first means the only markup that exists is the ``<br>`` added afterwards.
    Doing it the other way round would escape the breaks and produce one long line.
    """
    escaped = escape(text.strip())
    # Two trailing spaces are a hard break in plain text; preserve that intent.
    escaped = escaped.replace("  \n", "<br>\n")
    return escaped.replace("\n", "<br>")


#: The model's text comes back as Markdown whether or not anything asks it to, and prose with a
#: literal "**Standard King Room**" or "* " in front of it is the single most visible flaw a guest
#: can see. Observed in a real inbox, 2026-10-17.
#:
#: A small subset is rendered rather than a full parser, and the reason is injection: the text is
#: escaped *first*, so ``<`` and ``>`` are already inert, and only these four patterns are then
#: reintroduced as tags. A full Markdown parser would have to reason about code spans, links and
#: HTML blocks - all of which are ways to smuggle markup back in after escaping.
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ITALIC = re.compile(r"(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?![\*\w])", re.DOTALL)
_HEADING = re.compile(r"^\s{0,3}#{1,4}\s+(.+?)\s*#*\s*$")
_BULLET = re.compile(r"^\s*(?:[-*+•])\s+(.+?)\s*$")
#: A lone "*" followed by two spaces, which is how the model emits a bullet when it puts the marker
#: in its own token: "*   **Standard King Room**: ...".
_LOOSE_BULLET = re.compile(r"^\s*\*\s{2,}(.+?)\s*$")


def _inline(text: str) -> str:
    """Markdown emphasis, applied to text that has already been escaped."""
    out = _BOLD.sub(r"<strong>\1</strong>", text)
    out = _ITALIC.sub(r"<em>\1</em>", out)
    return out


def _paragraphs(text: str) -> str:
    """The body: paragraphs, headings and bullet lists, all as inline-styled elements.

    Bullets are indented paragraphs with a literal "•" rather than ``<ul>``/``<li>``, because
    Outlook's Word renderer handles list markup badly enough that indentation and spacing routinely
    come out wrong. A character bullet is the approach that survives it.
    """
    out: list[str] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        if not block.strip():
            continue
        lines = [line for line in block.split("\n") if line.strip()]
        heading = _HEADING.match(lines[0]) if len(lines) == 1 else None
        if heading:
            out.append(
                '<p style="margin:0 0 12px 0;font-size:17px;line-height:26px;font-weight:700;'
                f'color:#202124;">{_inline(body_to_html(heading.group(1)))}</p>'
            )
            continue

        bullets = [_BULLET.match(line) or _LOOSE_BULLET.match(line) for line in lines]
        if any(bullets):
            for line, match in zip(lines, bullets, strict=True):
                inner = body_to_html(match.group(1)) if match else body_to_html(line)
                out.append(
                    '<p style="margin:0 0 8px 0;padding-left:16px;font-size:16px;line-height:26px;'
                    f'color:#202124;">&bull;&nbsp;&nbsp;{_inline(inner)}</p>'
                )
            continue

        joined = "<br>".join(body_to_html(line) for line in lines)
        out.append(
            '<p style="margin:0 0 14px 0;font-size:16px;line-height:26px;color:#202124;">'
            f"{_inline(joined)}</p>"
        )
    return "".join(out)


def _social_row(branding: Branding) -> str:
    """The footer social row: glyphs inline, each linking to the profile.

    Inline-block images with a fixed height rather than a table cell per icon, so the row holds
    together on a narrow phone screen instead of wrapping one mark per line.
    """
    if not branding.social_links:
        return ""
    links = "&nbsp;&nbsp;".join(
        f'<a href="{escape(url)}" style="text-decoration:none;display:inline-block;" '
        f'title="{escape(_SOCIAL_LABELS[platform])}">{_social_icon(platform, branding.accent_colour)}</a>'
        for platform, url in branding.social_links.items()
    )
    return (
        f'<p style="margin:0 0 12px 0;font-size:13px;line-height:20px;">{links}</p>'
    )


def _contact_block(branding: Branding) -> str:
    """Website, email and telephone, each behind its own glyph. Address on its own line.

    A two-column table rather than ``<br>``-separated spans, because a glyph sitting on a text
    baseline drops a pixel or two in some clients and the row reads as broken. Table cells put the
    icon and its value on a shared middle line everywhere, which is why this is a table and the
    social row is not - that one is a single line of marks with no text to align against.
    """
    rows: list[tuple[str, str]] = []
    if branding.website:
        link = (
            f'<a href="{escape(branding.website)}" '
            f'style="color:{MUTED};text-decoration:none;">'
            f"{escape(branding.website)}</a>"
        )
        rows.append(("website", link))
    if branding.contact_email:
        rows.append(("email", escape(branding.contact_email)))
    if branding.phone:
        rows.append(("phone", escape(branding.phone)))
    if not rows:
        return ""

    # `font-size:0` on the icon cell removes the gap an inline image leaves beside it. Ignored by
    # some clients, which costs a couple of pixels of gutter - a far better failure than a
    # misaligned row.
    lines = "".join(
        "<tr>"
        f'<td width="{_CONTACT_ICON_SIZE + 10}" valign="middle" '
        f'style="padding:0;font-size:0;line-height:0;">'
        f"{_icon_img(render_glyph(contact_glyph(kind), 28, MUTED), _CONTACT_ICON_SIZE)}</td>"
        f'<td valign="middle" style="padding:0 0 0 6px;font-size:13px;line-height:20px;'
        f'color:{MUTED};">{value}</td>'
        "</tr>"
        for kind, value in rows
    )
    block = (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:0 0 12px 0;">{lines}</table>'
    )

    if branding.postal_address:
        block += (
            f'<p style="margin:0 0 12px 0;font-size:13px;line-height:20px;color:{MUTED};">'
            f"{escape(branding.postal_address)}</p>"
        )
    return block


def _badge_shapes(initials: str, colour: str) -> list:
    """The badge: a rounded square in the brand colour with the initials reversed out of it.

    The initials are drawn as a *hole* rather than white text, so the mark keeps working if the
    accent is a light colour - white-on-pale-yellow is invisible where reversed-out is not.
    """
    from app.channels.email.icons import _circle, _rounded_rect, _union

    plate = _rounded_rect(0.0, 0.0, 24.0, 24.0, 4.0)
    # Two letters side by side, centred as a pair; one letter is centred on its own.
    letters = _union(*[_circle(x, 12.0, 5.2) for x in _letter_positions(initials)])
    return [plate, lambda px, py: 0.0 if letters(px, py) else 1.0]


def _letter_positions(initials: str) -> list[float]:
    letters = list(initials)[:2]
    if len(letters) == 1:
        return [12.0]
    return [8.4, 15.6]


def _initials_badge(branding: Branding) -> str:
    """The initials mark, as a small image rather than text.

    **Why an image and not styled text.** Observed in a real Gmail inbox, 2026-10-17: the list-view
    preview read ``KH K Hotels Entebbe - Uganda Yes, there is a Family Suite available...`` - Gmail
    builds its snippet from the first *text* in the document, so a text badge became the summary. A
    guest skimming their inbox saw two letters instead of the answer.

    **Why PNG and not SVG.** This was SVG in a data URI first, and it rendered as an empty box in
    every message. The reasoning that a data URI is not a network request and therefore cannot be
    blocked was wrong: Gmail strips SVG because it is a script-capable format, and most clients follow
    its lead. PNG is what mail clients actually render. See :mod:`app.channels.email.icons`.
    """
    return _icon_img(
        render_glyph(_badge_shapes(branding.initials, branding.accent_colour), 128, branding.accent_colour),
        64,
    )



def _header(branding: Branding) -> str:
    if branding.logo_url:
        mark = (
            f'<img src="{escape(branding.logo_url)}" alt="{escape(branding.business_name)}" '
            f'width="64" height="64" style="display:block;border:0;width:64px;height:64px;" />'
        )
    else:
        mark = _initials_badge(branding)

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


def render_html(body: str, branding: Branding | None, source_count: int | None = None) -> str:
    body = strip_citations(body, source_count)
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


def plainify(text: str) -> str:
    """Strip Markdown markers, for the plain-text twin.

    The HTML renderer *interprets* ``**bold**``; this has to *remove* it. That distinction matters
    because the text part is not a lesser fallback - it is what a client with images blocked, a
    screen reader, or a decade-old phone actually reads. Leaving asterisks in it means the two
    versions of the same email disagree, and the worse one is the one more people see.
    """
    out: list[str] = []
    for line in text.split("\n"):
        heading = _HEADING.match(line)
        if heading:
            out.append(heading.group(1).strip())
            continue
        bullet = _BULLET.match(line) or _LOOSE_BULLET.match(line)
        out.append(f"• {bullet.group(1).strip()}" if bullet else line.strip())
    # Emphasis markers are removed last, over the whole text, so a bold span cannot straddle the
    # line breaks that bullet handling just introduced.
    out = [_BOLD.sub(r"\1", line) for line in out]
    return _ITALIC.sub(r"\1", "\n".join(out))


def render_text(body: str, branding: Branding | None, source_count: int | None = None) -> str:
    """The plain-text twin, with a signature block appended.

    This is the version that decides whether a reply reads as a desk or as a robot, because it is
    what a client shows when images are blocked and what most people actually read first. The
    separator is ``-- ``, the RFC 3676 signature marker, because that is what tells a mail client
    where the human-written part ends.
    """
    body = plainify(body)

    if branding is None:
        return strip_citations(body, source_count)

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
    return strip_citations(body, source_count) + "\n".join(lines)


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