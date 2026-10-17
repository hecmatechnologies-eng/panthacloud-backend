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
    def test_without_a_logo_the_badge_is_drawn_as_text(self) -> None:
        """No request to a third party, nothing to be blocked, and it still looks deliberate."""
        html = render_html(BODY, _brand())
        assert "<img" not in html
        assert ">KH<" in html

    def test_with_a_logo_the_image_is_used(self) -> None:
        html = render_html(BODY, _brand(logo_url="https://cdn.example/logo.png"))
        assert '<img src="https://cdn.example/logo.png"' in html


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

    def test_social_links_are_labelled_not_raw(self) -> None:
        """Raw URLs in a footer are ugly and, as naked text, hard to recognise as destinations."""
        html = render_html(
            BODY, _brand(social_links={"facebook": "https://facebook.com/khotels"})
        )
        assert ">Facebook<" in html
        assert 'href="https://facebook.com/khotels"' in html

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