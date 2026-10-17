"""Rendering branded mail: the layout rules, and the escaping that makes it safe.

**Why escaping is tested so hard here.** Two different parties write into the same HTML document -
the model produces the body, the tenant supplies the name, tagline, address and footer note. Either
could contain something that looks like markup. Escaping is what stops a tenant's tagline from
injecting a link into every guest's mail, so these are not defensive tests about a hypothetical: the
interpolation is unconditional and happens on every reply.

**Why the layout is asserted on the source, not on a screenshot.** Outlook's Word renderer and
Gmail's sanitiser disagree about almost everything, and neither is available in a test. What *is*
checkable, and what actually breaks in practice, is that the constructs Outlook ignores are absent
and the ones it honours are present. The screenshot check was done by hand; these assertions stop it
quietly regressing afterwards.

**What these tests do not claim.** That the mail will look good. Rendering differs between clients,
and only sending a real message proves anything about placement in an inbox.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from app.channels.email.templates import (
    DEFAULT_ACCENT,
    Branding,
    body_to_html,
    branding_from_row,
    normalise_colour,
    render_html,
    render_text,
)

BODY = "Check-out is by 11:00.\n\nThe Deluxe King Room costs from USD 180 per night."


def _brand(**overrides) -> Branding:
    kwargs = {"business_name": "K Hotels", "tagline": "Entebbe · Uganda"}
    kwargs.update(overrides)
    return Branding(**kwargs)


class TestColour:
    def test_a_bare_hex_is_accepted(self) -> None:
        """The `#` is the thing people forget, and losing the accent over it would be absurd."""
        assert normalise_colour("8A6A3B") == "#8A6A3B"

    def test_a_well_formed_colour_is_kept(self) -> None:
        assert normalise_colour("#1a2b3c") == "#1a2b3c"

    @pytest.mark.parametrize("bad", ["red", "#12345", "#GGGGGG", "rgb(1,2,3)", "javascript:alert(1)"])
    def test_anything_else_falls_back_rather_than_failing(self, bad: str) -> None:
        """A wrong colour should cost a tenant their accent, not their ability to send mail."""
        assert normalise_colour(bad) == DEFAULT_ACCENT

    def test_absent_is_not_a_special_case(self) -> None:
        assert normalise_colour(None) == DEFAULT_ACCENT
        assert normalise_colour("") == DEFAULT_ACCENT


class TestInitials:
    def test_two_words_give_two_letters(self) -> None:
        assert _brand(business_name="K Hotels").initials == "KH"

    def test_one_word_gives_two_letters(self) -> None:
        """Not one. "K" alone looks like a mistake rather than a mark."""
        assert _brand(business_name="Kempinski").initials == "KE"

    def test_punctuation_is_not_a_word(self) -> None:
        """"K." is the word "K" with a full stop, not a separate token - so this is TK, not T."""
        assert _brand(business_name="The K. Hotels Ltd").initials == "TK"


class TestEscaping:
    def test_tenant_markup_cannot_become_markup(self) -> None:
        """The injection that matters: a tenant-supplied string reaching every guest's client."""
        html = render_html(BODY, _brand(business_name="<script>alert(1)</script>K Hotels"))
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_a_tagline_cannot_inject_a_link(self) -> None:
        html = render_html(BODY, _brand(tagline="<a href='https://elsewhere.example'>click</a>"))
        assert "<a href='https://elsewhere.example'>" not in html

    def test_quotes_are_escaped_so_an_attribute_cannot_be_broken(self) -> None:
        """`quote=True`. Without it, a tagline containing a double quote closes the attribute early."""
        html = render_html(BODY, _brand(business_name='K" onmouseover="alert(1)'))
        assert 'onmouseover="' not in html

    def test_model_output_is_escaped_too(self) -> None:
        html = render_html("<b>not bold</b>", _brand())
        assert "<b>not bold</b>" not in html
        assert "&lt;b&gt;" in html

    def test_paragraph_newlines_become_line_breaks_and_nothing_else(self) -> None:
        """The one transformation allowed, and it must not become a general escape hatch."""
        assert body_to_html("one\ntwo") == "one<br>two"
        assert body_to_html("<em>") == "&lt;em&gt;"


class TestMarkdown:
    """The model writes Markdown whether or not anything asks it to.

    Observed in a real inbox: a reply arrived containing `*   **Standard King Room**: A king-size
    bed...` and the guest saw every asterisk. Nothing about a prose email makes the formatting stop,
    so the renderer handles a small subset instead of hoping the model cooperates.
    """

    def test_bold_is_rendered_not_shown(self) -> None:
        html = render_html("We have the **Family Suite** available.", _brand())
        assert "<strong>Family Suite</strong>" in html
        assert "**" not in html

    def test_italics_are_rendered_not_shown(self) -> None:
        html = render_html("The *only* family room.", _brand())
        assert "<em>only</em>" in html

    def test_a_tight_bullet_is_rendered(self) -> None:
        html = render_html("* Deluxe King\n* Family Suite", _brand())
        assert html.count("&bull;") == 2
        assert "Deluxe King" in html

    def test_the_loose_bullet_the_model_actually_emitted_is_rendered(self) -> None:
        """`*   **Standard King Room**: ...` - a marker in its own token, with several spaces.

        This is the exact shape seen in the inbox. A pattern matching only ``* text`` leaves it
        alone, and the guest sees the asterisks again.
        """
        html = render_html(
            "Here are the rates:\n*   **Standard King Room**: from USD 120.", _brand()
        )
        assert "&bull;" in html
        assert "<strong>Standard King Room</strong>" in html
        assert "**" not in html

    def test_a_heading_is_rendered(self) -> None:
        # Asserted against the source text, not "#" generally: every inline style in this document
        # carries a hex colour, so a bare "#" check would fail on the template rather than the bug.
        html = render_html("## Rooms and rates", _brand())
        assert "font-weight:700" in html
        assert "##" not in html
        assert "Rooms and rates" in html

    def test_markup_in_the_body_cannot_survive_as_markup(self) -> None:
        """Emphasis is reintroduced *after* escaping, so only these four patterns can become tags."""
        html = render_html("**<script>alert(1)</script>**", _brand())
        assert "<script>" not in html
        assert "<strong>" in html

    def test_the_plain_text_twin_is_clean_too(self) -> None:
        """The two versions must not disagree.

        Markdown was interpreted in the HTML and left literal in the text part, which is the worse
        half of the problem: the text version is what a client with images blocked, a screen reader,
        or a decade-old phone actually reads. That asymmetry is not obvious from the HTML, which is
        how it survived the first fix.
        """
        body = "Here are the rates:\n*   **Standard King Room**: USD 120 [5]."
        text = render_text(body, _brand(), source_count=12)
        assert "**" not in text
        assert "*   " not in text
        assert "[5]" not in text
        assert "• Standard King Room: USD 120." in text

    def test_a_bullet_is_a_character_not_a_list_element(self) -> None:
        """Outlook's Word renderer mishandles ``<ul>`` badly enough that indentation comes out wrong."""
        html = render_html("* One\n* Two", _brand())
        assert "<ul>" not in html
        assert "<li>" not in html


class TestCitationStripping:
    """Provenance markers are ours, not the guest's.

    The model is instructed to cite by bracketed number, and those numbers are stored on the message
    for audit and cross-checking. None of that is meaningful to someone asking about room rates, and
    a stray "[10]" reads as a leaked internal id.
    """

    def test_a_marker_never_reaches_the_plain_text_version(self) -> None:
        text = render_text("Check-out is by 11:00 [3]. The Deluxe King is USD 180 [2][7].", _brand())
        assert "[3]" not in text
        assert "[2]" not in text
        assert text.startswith("Check-out is by 11:00.")

    def test_a_marker_never_reaches_the_html(self) -> None:
        html = render_html("Check-out is by 11:00 [3].", _brand())
        assert "[3]" not in html

    def test_markers_are_stripped_when_there_is_no_branding(self) -> None:
        assert render_text("The pool is open [6].", None) == "The pool is open."

    def test_bracketed_text_that_is_not_a_citation_is_kept(self) -> None:
        """The bug a first attempt caused, kept as a test.

        Stripping any ``[digits]`` ate ``Rates for [2024] were higher`` - an ordinary sentence about
        a hotel - which would have silently rewritten the assistant's answer. A year is far outside
        any possible citation range, so range-checking is what separates the two.
        """
        for keep in ("Rates for [2024] were higher.", "Breakfast is [included] daily."):
            assert keep in render_text(keep, _brand())

    def test_only_markers_within_the_supplied_range_are_stripped(self) -> None:
        """The count is what makes it precise rather than a guess.

        Five passages were given, so [3] is a citation and [7] is the model reaching past what it
        was shown. The first is ours to clean up; the second is a different problem and silently
        deleting it would hide it.
        """
        text = "The pool is open [3] and the gym closes [7]."
        assert render_text(text, _brand(), source_count=5) == "The pool is open and the gym closes [7]."

    def test_the_body_is_still_never_altered_beyond_citations(self) -> None:
        """Stripping must not become a general-purpose rewrite."""
        body = "Yes, we have a pool [1]. It is open 07:00 to 20:00 [2]."
        assert render_text(body, None) == "Yes, we have a pool. It is open 07:00 to 20:00."


class TestNoBranding:
    def test_html_is_omitted_entirely(self) -> None:
        """An empty string rather than an unstyled white page, which reads as a broken template."""
        assert render_html(BODY, None) == ""

    def test_the_plain_reply_is_untouched(self) -> None:
        assert render_text(BODY, None) == BODY


class TestLayout:
    """The constructs that survive Outlook, asserted on the source."""

    def test_there_is_no_style_block(self) -> None:
        """Outlook ignores it and Gmail strips it inconsistently, so every style is inline."""
        html = render_html(BODY, _brand())
        assert "<style" not in html.lower()

    def test_layout_is_tables_with_presentational_attributes(self) -> None:
        html = render_html(BODY, _brand())
        assert "<table" in html
        assert 'cellpadding="0"' in html
        assert 'cellspacing="0"' in html

    def test_the_outer_width_is_fixed_with_a_maximum(self) -> None:
        """A percentage would render anywhere from 300px to 1600px depending on the client."""
        html = render_html(BODY, _brand())
        assert "width:560px" in html
        assert "max-width:560px" in html

    def test_no_scripts_or_external_assets(self) -> None:
        html = render_html(BODY, _brand(logo_url="https://cdn.example/logo.png"))
        assert "<script" not in html.lower()
        # An <img> is permitted; a stylesheet link is not, because nothing would wait for it.
        assert "<link" not in html.lower()

    def test_the_brand_name_is_the_document_title(self) -> None:
        html = render_html(BODY, _brand())
        assert "<title>K Hotels</title>" in html


class TestLogoFallback:
    def test_the_badge_is_an_image_so_it_cannot_lead_the_snippet(self) -> None:
        """The defect this replaced, found in a real inbox.

        Gmail builds its list-view preview from the first *text* in the document. The badge was a
        styled `<div>`, so the preview read ``KH K Hotels Entebbe · Uganda Yes, there is a Family
        Suite...`` - two letters standing in for the answer. An `<img>` contributes only its `alt`,
        so `alt=""` keeps it out entirely, and a client that refuses the image leaves a blank space
        rather than printing "KH" in the message list.
        """
        html = render_html(BODY, _brand())
        assert 'alt=""' in html
        assert ">KH<" not in html

    def test_the_badge_makes_no_third_party_request(self) -> None:
        """A data URI, so blocking images costs appearance and nothing else."""
        html = render_html(BODY, _brand())
        assert "data:image/png;base64," in html
        assert "cdn.example" not in html

    def test_the_badge_is_a_png_and_never_an_svg(self) -> None:
        """The regression this whole module exists to prevent.

        The badge was inline SVG in a data URI, on the reasoning that a data URI is not a network
        request and therefore cannot be blocked. That was wrong: every message rendered as an empty
        box, because Gmail strips SVG as a script-capable format. Asserted positively so the format
        cannot be quietly changed back.
        """
        html = render_html(BODY, _brand())
        assert "data:image/svg" not in html
        assert "data:image/png;base64," in html
        # A real PNG: the eight-byte signature, base64-encoded.
        import base64 as b64
        import re as _re

        encoded = _re.search(r"data:image/png;base64,([A-Za-z0-9+/=]+)", html)
        assert encoded is not None
        assert b64.b64decode(encoded.group(1)).startswith(b"\x89PNG\r\n\x1a\n")

    def test_the_badge_carries_the_accent_colour(self) -> None:
        """The PNG's pixels are the accent, so a tenant's colour reaches the mark too."""
        import re as _re

        from app.channels.email.icons import _parse_hex, render_glyph, social_glyph

        html = render_html(BODY, _brand(accent_colour="#123456"))
        encoded = _re.search(r"data:image/png;base64,([A-Za-z0-9+/=]+)", html)
        assert encoded is not None
        assert render_glyph(social_glyph("x"), 8, "#123456") != render_glyph(
            social_glyph("x"), 8, "#654321"
        )
        assert _parse_hex("#123456") == (0x12, 0x34, 0x56)

    def test_with_a_logo_the_image_is_used(self) -> None:
        html = render_html(BODY, _brand(logo_url="https://cdn.example/logo.png"))
        assert '<img src="https://cdn.example/logo.png"' in html
        # A real logo is meaningful, so unlike the decorative badge it keeps its alt text.
        assert 'alt="K Hotels"' in html


class TestFooter:
    def test_an_empty_footer_is_omitted(self) -> None:
        """A footer with a blank line where a phone number should be looks worse than none."""
        html = render_html(BODY, _brand())
        assert "Plot 7" not in html
        assert "You are receiving this" not in html

    def test_contact_details_are_present_when_given(self) -> None:
        brand = _brand(
            postal_address="Plot 7 Lugard Road",
            phone="+256 772 123 456",
            contact_email="reservations@ai-mwalimu.com",
            website="https://ai-mwalimu.com",
        )
        html = render_html(BODY, brand)
        assert "+256 772 123 456" in html
        assert "Plot 7 Lugard Road" in html
        assert "https://ai-mwalimu.com" in html

    def test_social_marks_are_icons_that_link_out(self) -> None:
        """Glyphs, not raw URLs and not a wall of text labels.

        The plain-text twin still names them, but in HTML a row of six words reads as a link dump;
        glyphs are the convention for a footer row.
        """
        html = render_html(
            BODY, _brand(social_links={"facebook": "https://facebook.com/khotels"})
        )
        assert 'href="https://facebook.com/khotels"' in html
        assert "data:image/png;base64," in html
        assert "data:image/svg" not in html
        # alt stays empty so neither the mark nor a filename reaches the message snippet; the name
        # is carried by `title`, which a screen reader and a hover both use.
        assert 'alt=""' in html
        assert 'title="Facebook"' in html

    def test_the_marks_take_the_accent_colour(self) -> None:
        """Arriving in a fixed black would not match the rest of the mail."""
        import base64 as b64
        import re as _re

        html = render_html(
            BODY, _brand(accent_colour="#123456", social_links={"x": "https://x.com/khotels"})
        )
        encoded = _re.search(r"data:image/png;base64,([A-Za-z0-9+/=]+)", html)
        assert encoded is not None
        assert b64.b64decode(encoded.group(1)).startswith(b"\x89PNG\r\n\x1a\n")

    def test_social_names_appear_in_the_plain_text_version(self) -> None:
        """Where there is no image to speak for itself, the name has to be spelled out."""
        text = render_text(BODY, _brand(social_links={"facebook": "https://facebook.com/khotels"}))
        assert "Facebook: https://facebook.com/khotels" in text

    def test_unknown_platforms_are_dropped_at_normalisation(self) -> None:
        """The label set is closed; an unlabelled URL would print as a bare link."""
        from app.models.project_branding import ProjectBranding

        class Row:
            business_name = "K Hotels"
            tagline = None
            logo_url = None
            accent_colour = None
            postal_address = None
            phone = None
            contact_email = None
            website = None
            footer_note = None
            social_links: ClassVar[dict] = {
                "facebook": "https://facebook.com/khotels",
                "facebok": "https://typo.example",
            }

        assert ProjectBranding is not None
        brand = branding_from_row(Row())  # type: ignore[arg-type]
        assert brand is not None
        assert set(brand.social_links) == {"facebook"}

    def test_has_contact_details_reflects_emptiness(self) -> None:
        assert _brand().has_contact_details is False
        assert _brand(phone="+256 772 123 456").has_contact_details is True


class TestPlainText:
    def test_the_signature_uses_the_rfc_marker(self) -> None:
        """``-- `` is what tells a mail client where the human-written part ends."""
        text = render_text(BODY, _brand(phone="+256 772 123 456"))
        assert "\n-- \n" in text

    def test_the_body_is_never_altered(self) -> None:
        """It is the first thing a reader sees, and the version most filters see."""
        text = render_text(BODY, _brand(phone="+256 772 123 456"))
        assert text.startswith(BODY)

    def test_an_unbranded_reply_gets_no_signature(self) -> None:
        assert render_text(BODY, None) == BODY