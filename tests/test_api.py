import pytest
import pytest_asyncio

from app import create_app


@pytest_asyncio.fixture()
async def client(aiohttp_client, tmp_path):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    return await aiohttp_client(create_app(database_url))


async def test_advertisement_crud(client):
    create_response = await client.post(
        "/advertisements",
        json={
            "title": "Продам велосипед",
            "description": "Городской велосипед в хорошем состоянии",
            "owner": "alexander",
        },
    )
    assert create_response.status == 201
    created = await create_response.json()
    assert created["id"] == 1
    assert created["title"] == "Продам велосипед"
    assert created["owner"] == "alexander"
    assert created["created_at"].endswith("Z")

    get_response = await client.get("/advertisements/1")
    assert get_response.status == 200
    assert await get_response.json() == created

    patch_response = await client.patch(
        "/advertisements/1", json={"title": "Велосипед продан"}
    )
    assert patch_response.status == 200
    patched = await patch_response.json()
    assert patched["title"] == "Велосипед продан"
    assert patched["description"] == created["description"]

    list_response = await client.get("/advertisements")
    assert list_response.status == 200
    assert len(await list_response.json()) == 1

    delete_response = await client.delete("/advertisements/1")
    assert delete_response.status == 204
    assert (await client.get("/advertisements/1")).status == 404


async def test_put_replaces_all_editable_fields(client):
    await client.post(
        "/advertisements",
        json={"title": "Старый", "description": "Текст", "owner": "owner"},
    )

    response = await client.put(
        "/advertisements/1",
        json={
            "title": "Новый",
            "description": "Обновлённый текст",
            "owner": "new-owner",
        },
    )

    assert response.status == 200
    updated = await response.json()
    assert updated["title"] == "Новый"
    assert updated["owner"] == "new-owner"


@pytest.mark.parametrize(
    "payload, expected_error",
    [
        ({"title": "Только заголовок"}, "missing fields"),
        (
            {"title": "", "description": "Описание", "owner": "owner"},
            "non-empty string",
        ),
        (
            {
                "title": "Заголовок",
                "description": "Описание",
                "owner": "owner",
                "created_at": "2026-01-01",
            },
            "unknown fields",
        ),
    ],
)
async def test_create_validation(client, payload, expected_error):
    response = await client.post("/advertisements", json=payload)
    assert response.status == 400
    assert expected_error in (await response.json())["error"]


async def test_invalid_json(client):
    response = await client.post(
        "/advertisements",
        data="not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status == 400
    assert "valid JSON" in (await response.json())["error"]


async def test_not_found(client):
    assert (await client.get("/advertisements/999")).status == 404
    assert (
        await client.patch("/advertisements/999", json={"title": "Нет"})
    ).status == 404
    assert (await client.delete("/advertisements/999")).status == 404
