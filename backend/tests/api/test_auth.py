import httpx


async def test_auth_and_roles(client):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=client.app), base_url="http://test"
    ) as anonymous:
        assert (await anonymous.get("/api/agents")).status_code == 401
        assert (
            await anonymous.post("/api/auth/login", json={"email": "owner@example.com", "password": "wrong"})
        ).status_code == 401
    created = await client.post(
        "/api/users",
        json={"email": "member@example.com", "display_name": "Test Member", "password": "Password123!"},
    )
    assert created.status_code == 201, created.text
    assert "password" not in created.text
    assert created.json()["avatar_initials"] == "TM"
    response = await client.post(
        "/api/auth/login", json={"email": "member@example.com", "password": "Password123!"}
    )
    headers = {"Authorization": "Bearer " + response.json()["access_token"]}
    assert (
        await client.post(
            "/api/agents", headers=headers, json={"handle": "@custom", "display_name": "Custom"}
        )
    ).status_code == 403
    assert (
        await client.patch(
            f"/api/users/{created.json()['id']}", headers=headers, json={"system_role": "ADMIN"}
        )
    ).status_code == 403
    assert (
        await client.patch(f"/api/users/{client.owner['id']}", json={"system_role": "MEMBER"})
    ).status_code == 409
    updated = await client.patch(
        f"/api/users/{created.json()['id']}",
        headers=headers,
        json={"password": "NewPassword123!", "display_name": "New Name"},
    )
    assert updated.status_code == 200, updated.text
    assert (
        await client.post(
            "/api/auth/login", json={"email": "member@example.com", "password": "NewPassword123!"}
        )
    ).status_code == 200


async def test_bad_jwt_and_validation_never_echo_secrets(client):
    assert (
        await client.get("/api/auth/me", headers={"Authorization": "Bearer bad-token"})
    ).status_code == 401
    response = await client.post(
        "/api/agents", json={"handle": "invalid", "display_name": "X", "api_key": "sensitive-key"}
    )
    assert response.status_code == 422
    assert "sensitive-key" not in response.text
    assert response.json()["code"] == "validation_error"
