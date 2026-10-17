"""The branding API: tenancy, validation, and the states a form has to survive.

**Where the interesting failures came from.** Every test here that looks fussy was added because
something real broke:

- ``contact_email`` was briefly validated as an http(s) URL, on the reasoning that it renders near
  the website. It is printed as plain text and an address is not a URL, so *every* save failed for
  any tenant with a contact email - which is most tenants. Found by saving a real brand through the
  browser, not by reading the validator.
- The project picker defaulted to whichever project the database listed first, which was an empty
  one while the project actually answering guests sat at the bottom of a thirty-item list.

**Tenancy is the other half.** `org_id` and `project_id` both arrive in the path, so proving the
project belongs to the organisation is what stops a valid project id from being readable by a
different tenant who guessed it.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

BASE = "/api/v1/organizations"


async def make_org(client: AsyncClient) -> tuple[str, str]:
    """A user and an organisation. Returns ``(organization_id, token)``."""
    suffix = uuid.uuid4().hex[:8]
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"brand-{suffix}@example.com",
            "password": "Password123!",
            "full_name": f"Brand {suffix}",
            "org_name": f"Brand Org {suffix}",
        },
    )
    assert reg.status_code == 201, reg.text
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    org_id = (await client.get("/api/v1/organizations", headers=headers)).json()[0]["id"]
    return org_id, token


async def make_project(client: AsyncClient, org_id: str, token: str) -> str:
    proj = await client.post(
        f"{BASE}/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "K Hotels", "slug": f"brand-{uuid.uuid4().hex[:8]}"},
    )
    assert proj.status_code == 201, proj.text
    return proj.json()["id"]


@pytest.fixture
async def org(client: AsyncClient) -> tuple[str, str]:
    return await make_org(client)


@pytest.fixture
async def project(client: AsyncClient, org: tuple[str, str]) -> str:
    org_id, token = org
    return await make_project(client, org_id, token)


def _brand(**overrides) -> dict:
    payload = {
        "business_name": "K Hotels",
        "tagline": "Entebbe · Uganda",
        "accent_colour": "#8A6A3B",
        "postal_address": "Plot 7 Lugard Road",
        "phone": "+256 772 123 456",
        "contact_email": "reservations@ai-mwalimu.com",
        "website": "https://ai-mwalimu.com",
        "social_links": {"facebook": "https://facebook.com/khotels"},
        "footer_note": "You wrote to us, so we are writing back.",
    }
    payload.update(overrides)
    return payload


class TestSaveAndRead:
    async def test_a_brand_round_trips(self, client: AsyncClient, org, project) -> None:
        org_id, token = org
        headers = {"Authorization": f"Bearer {token}"}
        saved = await client.put(f"{BASE}/{org_id}/projects/{project}/branding", headers=headers, json=_brand())
        assert saved.status_code == 200, saved.text

        read = await client.get(f"{BASE}/{org_id}/projects/{project}/branding", headers=headers)
        assert read.status_code == 200
        assert read.json()["business_name"] == "K Hotels"
        assert read.json()["social_links"]["facebook"] == "https://facebook.com/khotels"

    async def test_a_save_replaces_rather_than_merges(self, client: AsyncClient, org, project) -> None:
        """The reason it is a PUT and not a PATCH.

        Removing the phone number has to be expressible. Under a partial update, omitting it would
        be indistinguishable from forgetting it and the value would be impossible to clear.
        """
        org_id, token = org
        headers = {"Authorization": f"Bearer {token}"}
        await client.put(f"{BASE}/{org_id}/projects/{project}/branding", headers=headers, json=_brand())
        second = await client.put(
            f"{BASE}/{org_id}/projects/{project}/branding", headers=headers, json=_brand(phone=None)
        )
        assert second.status_code == 200
        assert second.json()["phone"] is None

    async def test_an_unbranded_project_reads_as_empty_rather_than_404(
        self, client: AsyncClient, org, project
    ) -> None:
        """A form must be able to render "not branded yet" without a special case."""
        org_id, token = org
        response = await client.get(
            f"{BASE}/{org_id}/projects/{project}/branding",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["business_name"] is None

    async def test_removing_is_idempotent(self, client: AsyncClient, org, project) -> None:
        org_id, token = org
        headers = {"Authorization": f"Bearer {token}"}
        await client.put(f"{BASE}/{org_id}/projects/{project}/branding", headers=headers, json=_brand())
        first = await client.delete(f"{BASE}/{org_id}/projects/{project}/branding", headers=headers)
        second = await client.delete(f"{BASE}/{org_id}/projects/{project}/branding", headers=headers)
        assert first.status_code == 204
        assert second.status_code == 204


class TestValidation:
    async def test_a_contact_email_is_not_required_to_be_a_url(self, client: AsyncClient, org, project) -> None:
        """The regression that made this file exist.

        `contact_email` was validated alongside the website as an http(s) URL, on the grounds that
        it renders near it. It is printed as plain text and an address is not a URL, so every save
        failed for any tenant that had one.
        """
        org_id, token = org
        response = await client.put(
            f"{BASE}/{org_id}/projects/{project}/branding",
            headers={"Authorization": f"Bearer {token}"},
            json=_brand(contact_email="reservations@ai-mwalimu.com"),
        )
        assert response.status_code == 200, response.text

    async def test_a_website_must_be_a_url(self, client: AsyncClient, org, project) -> None:
        """It becomes an href, so a scheme check is what stops `javascript:` being one click away."""
        org_id, token = org
        response = await client.put(
            f"{BASE}/{org_id}/projects/{project}/branding",
            headers={"Authorization": f"Bearer {token}"},
            json=_brand(website="javascript:alert(1)"),
        )
        assert response.status_code == 422

    async def test_an_unknown_social_platform_is_refused_not_dropped(self, client: AsyncClient, org, project) -> None:
        """Refused, because dropping it would save successfully and then show nothing in the footer."""
        org_id, token = org
        response = await client.put(
            f"{BASE}/{org_id}/projects/{project}/branding",
            headers={"Authorization": f"Bearer {token}"},
            json=_brand(social_links={"facebok": "https://typo.example"}),
        )
        assert response.status_code == 422

    async def test_a_business_name_is_required(self, client: AsyncClient, org, project) -> None:
        org_id, token = org
        response = await client.put(
            f"{BASE}/{org_id}/projects/{project}/branding",
            headers={"Authorization": f"Bearer {token}"},
            json=_brand(business_name=""),
        )
        assert response.status_code == 422


class TestTenancy:
    async def test_another_organisation_cannot_read_the_brand(
        self, client: AsyncClient, org, project
    ) -> None:
        """404, not 403 - "forbidden" would confirm the project id exists."""
        org_id, token = org
        await client.put(
            f"{BASE}/{org_id}/projects/{project}/branding",
            headers={"Authorization": f"Bearer {token}"},
            json=_brand(),
        )
        other_org, other_token = await make_org(client)
        response = await client.get(
            f"{BASE}/{other_org}/projects/{project}/branding",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert response.status_code == 404

    async def test_another_organisation_cannot_write_it(
        self, client: AsyncClient, org, project
    ) -> None:
        org_id, token = org
        await client.put(
            f"{BASE}/{org_id}/projects/{project}/branding",
            headers={"Authorization": f"Bearer {token}"},
            json=_brand(),
        )
        other_org, other_token = await make_org(client)
        response = await client.put(
            f"{BASE}/{other_org}/projects/{project}/branding",
            headers={"Authorization": f"Bearer {other_token}"},
            json=_brand(business_name="Stolen"),
        )
        assert response.status_code == 404

        # And the original is untouched.
        read = await client.get(
            f"{BASE}/{org_id}/projects/{project}/branding",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert read.json()["business_name"] == "K Hotels"

    async def test_anonymous_access_is_refused(self, client: AsyncClient, org, project) -> None:
        org_id, _ = org
        assert (await client.get(f"{BASE}/{org_id}/projects/{project}/branding")).status_code in (401, 403)