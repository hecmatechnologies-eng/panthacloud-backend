"""The channels API: connecting accounts, and pointing a project at one.

Three properties are tested that the endpoint shape alone does not guarantee.

**A token never comes back.** ``ChannelAccountRead`` has no field for it, so this is structural -
but a future field addition could break it silently, and ``has_access_token`` is what the UI uses
instead, so both are asserted.

**A connected account answers nobody until a project selects it.** The list reports
``selected_by_project_id`` precisely so the Settings page cannot show "Connected" for a number that
is silently inert - which is the most likely way to lose an afternoon during setup.

**Refusals do not disclose.** A bad registration id, one from another organisation, and one on the
wrong channel are all the same 404.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

BASE = "/api/v1/organizations"
NUMBER = "256772123456"
SECRET_TOKEN = "EAAG-super-secret-token-value"


async def _org(client: AsyncClient, prefix: str = "ch") -> tuple[str, dict[str, str]]:
    """An organisation with one project. Returns ``(org_id, headers)``."""
    suffix = uuid.uuid4().hex[:8]
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{prefix}-{suffix}@example.com",
            "password": "Password123!",
            "full_name": f"Chan {suffix}",
            "org_name": f"Chan Org {suffix}",
        },
    )
    assert reg.status_code == 201, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    org_id = (await client.get("/api/v1/organizations", headers=headers)).json()[0]["id"]
    return org_id, headers


async def _project(client: AsyncClient, org_id: str, headers: dict[str, str], name: str = "Hotel") -> str:
    resp = await client.post(
        f"{BASE}/{org_id}/projects", headers=headers, json={"name": name, "slug": name.lower()}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _connect(
    client: AsyncClient, org_id: str, headers: dict[str, str], **over
) -> dict:
    payload = {
        "channel": "whatsapp",
        "external_identifier": NUMBER,
        "display_name": "+256 772 123 456",
        "phone_number_id": "1234567890",
        **over,
    }
    resp = await client.post(f"{BASE}/{org_id}/channels", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestConnecting:
    async def test_an_account_can_be_connected(self, client: AsyncClient) -> None:
        org_id, headers = await _org(client)

        created = await _connect(client, org_id, headers)

        assert created["external_identifier"] == NUMBER
        assert created["phone_number_id"] == "1234567890"
        assert created["is_active"] is True

    async def test_the_address_is_normalised_on_the_way_in(self, client: AsyncClient) -> None:
        """A hotel writes '+256 772 123 456'; Meta sends '256772123456'. One row, not two."""
        org_id, headers = await _org(client)

        created = await _connect(client, org_id, headers, external_identifier="+256772123456")

        assert created["external_identifier"] == NUMBER

    async def test_a_connected_account_is_not_attached_to_any_project(
        self, client: AsyncClient
    ) -> None:
        """The distinction the whole slice rests on: connected is not live."""
        org_id, headers = await _org(client)

        created = await _connect(client, org_id, headers)

        assert created["selected_by_project_id"] is None

    async def test_connecting_the_same_number_twice_is_a_conflict(
        self, client: AsyncClient
    ) -> None:
        org_id, headers = await _org(client)
        await _connect(client, org_id, headers)

        resp = await client.post(
            f"{BASE}/{org_id}/channels",
            headers=headers,
            json={"channel": "whatsapp", "external_identifier": NUMBER},
        )

        assert resp.status_code == 409

    async def test_another_tenant_cannot_take_a_number_already_connected(
        self, client: AsyncClient
    ) -> None:
        """Uniqueness is global across organisations, and the refusal does not say which tenant
        holds it - that would be a directory of every number on the platform."""
        org_a, headers_a = await _org(client, "a")
        await _connect(client, org_a, headers_a)
        org_b, headers_b = await _org(client, "b")

        resp = await client.post(
            f"{BASE}/{org_b}/channels",
            headers=headers_b,
            json={"channel": "whatsapp", "external_identifier": NUMBER},
        )

        assert resp.status_code == 409
        assert "already connected" in resp.json()["detail"].lower()

    async def test_an_organisation_can_connect_several_numbers(
        self, client: AsyncClient
    ) -> None:
        """The reason this is organisation-level: a group with two properties."""
        org_id, headers = await _org(client)
        # Each number has its own phone_number_id too - they are one number, so reusing the id
        # would be the same account twice and `uq_channel_registration_phone_number_id` refuses it.
        await _connect(
            client, org_id, headers,
            external_identifier="256772000001", phone_number_id="900000001",
        )
        await _connect(
            client, org_id, headers,
            external_identifier="256772000002", phone_number_id="900000002",
        )

        listed = (await client.get(f"{BASE}/{org_id}/channels", headers=headers)).json()

        assert len(listed) == 2
        assert {row["external_identifier"] for row in listed} == {"256772000001", "256772000002"}

    async def test_two_numbers_cannot_share_one_phone_number_id(self, client: AsyncClient) -> None:
        """`phone_number_id` is Meta's id for the number, so sharing it means sharing the number -
        and the partial unique index says so before the address check does."""
        org_id, headers = await _org(client)
        await _connect(client, org_id, headers)

        resp = await client.post(
            f"{BASE}/{org_id}/channels",
            headers=headers,
            json={
                "channel": "whatsapp",
                "external_identifier": "256772000009",
                "phone_number_id": "1234567890",
            },
        )

        assert resp.status_code == 409


class TestTokensStayHidden:
    async def test_a_stored_token_is_not_returned(self, client: AsyncClient) -> None:
        org_id, headers = await _org(client)

        created = await _connect(client, org_id, headers, access_token=SECRET_TOKEN)

        assert "access_token" not in created
        assert SECRET_TOKEN not in str(created)
        assert created["has_access_token"] is True

    async def test_an_account_with_no_token_reports_false(self, client: AsyncClient) -> None:
        """Embedded Signup fills the token in later, so 'connected without credentials' is a real
        state the UI has to render rather than infer."""
        org_id, headers = await _org(client)

        created = await _connect(client, org_id, headers)

        assert created["has_access_token"] is False

    async def test_listing_does_not_leak_it_either(self, client: AsyncClient) -> None:
        org_id, headers = await _org(client)
        await _connect(client, org_id, headers, access_token=SECRET_TOKEN)

        body = (await client.get(f"{BASE}/{org_id}/channels", headers=headers)).text

        assert SECRET_TOKEN not in body


class TestProjectSelection:
    async def test_a_project_can_be_pointed_at_a_connected_account(
        self, client: AsyncClient
    ) -> None:
        org_id, headers = await _org(client)
        project_id = await _project(client, org_id, headers)
        account = await _connect(client, org_id, headers)

        resp = await client.put(
            f"{BASE}/{org_id}/projects/{project_id}/channels/whatsapp",
            headers=headers,
            json={"channel_registration_id": account["id"]},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["channel_registration_id"] == account["id"]

    async def test_selecting_marks_the_account_in_the_organisation_list(
        self, client: AsyncClient
    ) -> None:
        """So Settings can say which project is live on a number rather than just 'Connected'."""
        org_id, headers = await _org(client)
        project_id = await _project(client, org_id, headers, name="Entebbe")
        account = await _connect(client, org_id, headers)
        await client.put(
            f"{BASE}/{org_id}/projects/{project_id}/channels/whatsapp",
            headers=headers,
            json={"channel_registration_id": account["id"]},
        )

        listed = (await client.get(f"{BASE}/{org_id}/channels", headers=headers)).json()

        assert listed[0]["selected_by_project_id"] == project_id
        assert listed[0]["selected_by_project_name"] == "Entebbe"

    async def test_selecting_again_replaces_rather_than_adds(
        self, client: AsyncClient
    ) -> None:
        """Two live numbers would leave 'where do replies go?' unanswerable."""
        org_id, headers = await _org(client)
        project_id = await _project(client, org_id, headers)
        first = await _connect(
            client, org_id, headers,
            external_identifier="256772000001", phone_number_id="900000001",
        )
        second = await _connect(
            client, org_id, headers,
            external_identifier="256772000002", phone_number_id="900000002",
        )

        for account in (first, second):
            await client.put(
                f"{BASE}/{org_id}/projects/{project_id}/channels/whatsapp",
                headers=headers,
                json={"channel_registration_id": account["id"]},
            )

        selections = (
            await client.get(f"{BASE}/{org_id}/projects/{project_id}/channels", headers=headers)
        ).json()

        assert len(selections) == 1
        assert selections[0]["channel_registration_id"] == second["id"]

    async def test_two_projects_cannot_share_one_account(self, client: AsyncClient) -> None:
        """Forced by routing: a webhook names the number and nothing else, so two projects on one
        number would leave the resolver choosing arbitrarily."""
        org_id, headers = await _org(client)
        project_a = await _project(client, org_id, headers, name="Entebbe")
        project_b = await _project(client, org_id, headers, name="Kampala")
        account = await _connect(client, org_id, headers)

        first = await client.put(
            f"{BASE}/{org_id}/projects/{project_a}/channels/whatsapp",
            headers=headers,
            json={"channel_registration_id": account["id"]},
        )
        assert first.status_code == 200

        second = await client.put(
            f"{BASE}/{org_id}/projects/{project_b}/channels/whatsapp",
            headers=headers,
            json={"channel_registration_id": account["id"]},
        )

        # Replaced rather than refused: the caller asked for project B to take it, and the unique
        # constraint means project A's row has to go. What must not happen is both keeping it.
        assert second.status_code == 200
        a_now = (
            await client.get(f"{BASE}/{org_id}/projects/{project_a}/channels", headers=headers)
        ).json()
        b_now = (
            await client.get(f"{BASE}/{org_id}/projects/{project_b}/channels", headers=headers)
        ).json()
        assert a_now == []
        assert len(b_now) == 1

    async def test_an_unknown_account_is_a_404(self, client: AsyncClient) -> None:
        org_id, headers = await _org(client)
        project_id = await _project(client, org_id, headers)

        resp = await client.put(
            f"{BASE}/{org_id}/projects/{project_id}/channels/whatsapp",
            headers=headers,
            json={"channel_registration_id": str(uuid.uuid4())},
        )

        assert resp.status_code == 404

    async def test_an_account_from_another_organisation_is_also_a_404(
        self, client: AsyncClient
    ) -> None:
        """Same status and body as an unknown id - the difference is not this endpoint's to
        disclose."""
        org_a, headers_a = await _org(client, "a")
        account = await _connect(client, org_a, headers_a)
        org_b, headers_b = await _org(client, "b")
        project_b = await _project(client, org_b, headers_b)

        resp = await client.put(
            f"{BASE}/{org_b}/projects/{project_b}/channels/whatsapp",
            headers=headers_b,
            json={"channel_registration_id": account["id"]},
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Channel account not found"

    async def test_a_retired_account_cannot_be_selected(self, client: AsyncClient) -> None:
        org_id, headers = await _org(client)
        project_id = await _project(client, org_id, headers)
        account = await _connect(client, org_id, headers)
        await client.patch(
            f"{BASE}/{org_id}/channels/{account['id']}",
            headers=headers,
            json={"is_active": False},
        )

        resp = await client.put(
            f"{BASE}/{org_id}/projects/{project_id}/channels/whatsapp",
            headers=headers,
            json={"channel_registration_id": account["id"]},
        )

        assert resp.status_code == 409

    async def test_another_project_in_a_different_org_is_not_reachable(
        self, client: AsyncClient
    ) -> None:
        _org_a, headers_a = await _org(client, "a")
        org_b, headers_b = await _org(client, "b")
        project_b = await _project(client, org_b, headers_b)

        resp = await client.get(
            f"{BASE}/{org_b}/projects/{project_b}/channels", headers=headers_a
        )

        assert resp.status_code == 404


class TestRetiring:
    async def test_an_account_can_be_retired_and_restored(self, client: AsyncClient) -> None:
        org_id, headers = await _org(client)
        account = await _connect(client, org_id, headers)

        retired = await client.patch(
            f"{BASE}/{org_id}/channels/{account['id']}",
            headers=headers,
            json={"is_active": False},
        )
        assert retired.json()["is_active"] is False

        restored = await client.patch(
            f"{BASE}/{org_id}/channels/{account['id']}",
            headers=headers,
            json={"is_active": True},
        )
        assert restored.json()["is_active"] is True

    async def test_a_retired_account_still_holds_the_number(
        self, client: AsyncClient
    ) -> None:
        """Deactivation rather than deletion, so the address cannot be handed to another tenant
        while the row sits around."""
        org_id, headers = await _org(client)
        account = await _connect(client, org_id, headers)
        await client.patch(
            f"{BASE}/{org_id}/channels/{account['id']}",
            headers=headers,
            json={"is_active": False},
        )

        org_b, headers_b = await _org(client, "b")
        resp = await client.post(
            f"{BASE}/{org_b}/channels",
            headers=headers_b,
            json={"channel": "whatsapp", "external_identifier": NUMBER},
        )

        assert resp.status_code == 409


class TestPermissions:
    async def test_a_non_member_gets_404_not_403(
        self, client: AsyncClient
    ) -> None:
        """Same refusal as an unknown organisation, so membership cannot be probed."""
        _, headers_a = await _org(client, "a")
        org_b, _ = await _org(client, "b")

        resp = await client.get(f"{BASE}/{org_b}/channels", headers=headers_a)

        assert resp.status_code == 404

    async def test_unauthenticated_is_refused(self, client: AsyncClient) -> None:
        org_id, _ = await _org(client)

        resp = await client.get(f"{BASE}/{org_id}/channels")

        assert resp.status_code in (401, 403)

class TestPagination:
    """Collections are paginated, per api-routing-standards section 6.

    Not ceremony here: accounts are *retired*, never deleted, so the list only grows, and an
    offset would let a row shift between pages as somebody connects a number mid-scroll - serving
    one twice and skipping another.
    """

    async def _connect_many(self, client: AsyncClient, org_id: str, headers: dict, n: int) -> None:
        for i in range(n):
            await _connect(
                client, org_id, headers,
                external_identifier=f"25677200{i:04d}", phone_number_id=f"91000000{i:02d}",
            )

    async def test_a_full_page_comes_back_with_a_next_link(
        self, client: AsyncClient
    ) -> None:
        org_id, headers = await _org(client)
        await self._connect_many(client, org_id, headers, 3)

        resp = await client.get(f"{BASE}/{org_id}/channels?limit=2", headers=headers)

        assert resp.status_code == 200
        assert len(resp.json()) == 2
        assert "Link" in resp.headers
        assert 'rel="next"' in resp.headers["Link"]

    async def test_walking_the_cursor_reaches_every_account_exactly_once(
        self, client: AsyncClient
    ) -> None:
        org_id, headers = await _org(client)
        await self._connect_many(client, org_id, headers, 5)

        seen: list[str] = []
        url = f"{BASE}/{org_id}/channels?limit=2"
        for _ in range(10):  # bounded so a broken cursor loop fails instead of hanging
            resp = await client.get(url, headers=headers)
            seen.extend(row["external_identifier"] for row in resp.json())
            link = resp.headers.get("Link", "")
            if 'rel="next"' not in link:
                break
            url = link.split("<")[1].split(">")[0]

        assert len(seen) == 5
        assert len(set(seen)) == 5, f"an account was served twice: {seen}"

    async def test_the_last_page_carries_no_next_link(self, client: AsyncClient) -> None:
        org_id, headers = await _org(client)
        await self._connect_many(client, org_id, headers, 2)

        resp = await client.get(f"{BASE}/{org_id}/channels?limit=10", headers=headers)

        assert len(resp.json()) == 2
        assert "Link" not in resp.headers

    async def test_a_cursor_this_server_did_not_issue_is_a_400(
        self, client: AsyncClient
    ) -> None:
        """400, not 422: the request was well formed, the cursor value was simply not ours."""
        org_id, headers = await _org(client)

        resp = await client.get(
            f"{BASE}/{org_id}/channels?cursor=not-a-real-cursor", headers=headers
        )

        assert resp.status_code == 400


class TestCreatedIsAddressable:
    async def test_the_201_points_at_a_url_that_resolves(self, client: AsyncClient) -> None:
        """A Location header naming a path that 404s is worse than none: a client that follows it
        reports failure for a request that succeeded."""
        org_id, headers = await _org(client)

        resp = await client.post(
            f"{BASE}/{org_id}/channels",
            headers=headers,
            json={"channel": "whatsapp", "external_identifier": NUMBER},
        )

        assert resp.status_code == 201
        location = resp.headers.get("Location")
        assert location, "201 without a Location header"

        followed = await client.get(location, headers=headers)
        assert followed.status_code == 200
        assert followed.json()["external_identifier"] == NUMBER
