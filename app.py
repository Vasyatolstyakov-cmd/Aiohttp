import json
import os
from pathlib import Path

from aiohttp import web
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from models import Advertisement, Base


EDITABLE_FIELDS = {"title", "description", "owner"}
DATABASE_URL_KEY = web.AppKey("database_url", str)
DB_ENGINE_KEY = web.AppKey("db_engine", AsyncEngine)
DB_SESSION_KEY = web.AppKey("db_session", async_sessionmaker)


def error_response(message: str, status_code: int) -> web.Response:
    return web.json_response({"error": message}, status=status_code)


def validate_advertisement(data, *, partial: bool = False):
    if not isinstance(data, dict):
        return None, "request body must be a JSON object"

    unknown_fields = set(data) - EDITABLE_FIELDS
    if unknown_fields:
        fields = ", ".join(sorted(unknown_fields))
        return None, f"unknown fields: {fields}"

    if not partial:
        missing_fields = EDITABLE_FIELDS - set(data)
        if missing_fields:
            fields = ", ".join(sorted(missing_fields))
            return None, f"missing fields: {fields}"
    elif not data:
        return None, "at least one editable field is required"

    cleaned = {}
    for field in EDITABLE_FIELDS & set(data):
        value = data[field]
        if not isinstance(value, str) or not value.strip():
            return None, f"field '{field}' must be a non-empty string"
        cleaned[field] = value.strip()

    if len(cleaned.get("title", "")) > 200:
        return None, "field 'title' must contain no more than 200 characters"
    if len(cleaned.get("owner", "")) > 120:
        return None, "field 'owner' must contain no more than 120 characters"

    return cleaned, None


async def read_json(request: web.Request):
    try:
        return await request.json(), None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, "request body must contain valid JSON"


async def database_context(app: web.Application):
    engine = create_async_engine(app[DATABASE_URL_KEY], pool_pre_ping=True)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    app[DB_ENGINE_KEY] = engine
    app[DB_SESSION_KEY] = session_factory

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield
    await engine.dispose()


async def index(_request: web.Request) -> web.Response:
    return web.json_response(
        {
            "service": "advertisements-api-aiohttp",
            "endpoints": {
                "create": "POST /advertisements",
                "list": "GET /advertisements",
                "get": "GET /advertisements/<id>",
                "edit": "PATCH or PUT /advertisements/<id>",
                "delete": "DELETE /advertisements/<id>",
            },
        }
    )


async def create_advertisement(request: web.Request) -> web.Response:
    payload, json_error = await read_json(request)
    if json_error:
        return error_response(json_error, 400)

    data, validation_error = validate_advertisement(payload)
    if validation_error:
        return error_response(validation_error, 400)

    advertisement = Advertisement(**data)
    session_factory = request.app[DB_SESSION_KEY]
    async with session_factory() as session:
        try:
            session.add(advertisement)
            await session.commit()
            await session.refresh(advertisement)
        except SQLAlchemyError:
            await session.rollback()
            request.app.logger.exception("failed to create advertisement")
            return error_response("database error", 500)

    return web.json_response(advertisement.to_dict(), status=201)


async def list_advertisements(request: web.Request) -> web.Response:
    session_factory = request.app[DB_SESSION_KEY]
    async with session_factory() as session:
        advertisements = (
            await session.scalars(
                select(Advertisement).order_by(Advertisement.id)
            )
        ).all()
        return web.json_response([item.to_dict() for item in advertisements])


async def get_advertisement(request: web.Request) -> web.Response:
    advertisement_id = int(request.match_info["advertisement_id"])
    session_factory = request.app[DB_SESSION_KEY]
    async with session_factory() as session:
        advertisement = await session.get(Advertisement, advertisement_id)
        if advertisement is None:
            return error_response("advertisement not found", 404)
        return web.json_response(advertisement.to_dict())


async def edit_advertisement(request: web.Request) -> web.Response:
    advertisement_id = int(request.match_info["advertisement_id"])
    payload, json_error = await read_json(request)
    if json_error:
        return error_response(json_error, 400)

    data, validation_error = validate_advertisement(
        payload, partial=request.method == "PATCH"
    )
    if validation_error:
        return error_response(validation_error, 400)

    session_factory = request.app[DB_SESSION_KEY]
    async with session_factory() as session:
        try:
            advertisement = await session.get(Advertisement, advertisement_id)
            if advertisement is None:
                return error_response("advertisement not found", 404)

            for field, value in data.items():
                setattr(advertisement, field, value)
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            request.app.logger.exception("failed to edit advertisement")
            return error_response("database error", 500)

    return web.json_response(advertisement.to_dict())


async def delete_advertisement(request: web.Request) -> web.Response:
    advertisement_id = int(request.match_info["advertisement_id"])
    session_factory = request.app[DB_SESSION_KEY]
    async with session_factory() as session:
        try:
            advertisement = await session.get(Advertisement, advertisement_id)
            if advertisement is None:
                return error_response("advertisement not found", 404)

            await session.delete(advertisement)
            await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            request.app.logger.exception("failed to delete advertisement")
            return error_response("database error", 500)

    return web.Response(status=204)


def create_app(database_url: str | None = None) -> web.Application:
    default_database = Path(__file__).with_name("advertisements.db")
    database_url = database_url or os.getenv(
        "DATABASE_URL", f"sqlite+aiosqlite:///{default_database}"
    )

    app = web.Application()
    app[DATABASE_URL_KEY] = database_url
    app.cleanup_ctx.append(database_context)
    app.add_routes(
        [
            web.get("/", index),
            web.post("/advertisements", create_advertisement),
            web.get("/advertisements", list_advertisements),
            web.get(
                r"/advertisements/{advertisement_id:\d+}", get_advertisement
            ),
            web.patch(
                r"/advertisements/{advertisement_id:\d+}", edit_advertisement
            ),
            web.put(
                r"/advertisements/{advertisement_id:\d+}", edit_advertisement
            ),
            web.delete(
                r"/advertisements/{advertisement_id:\d+}", delete_advertisement
            ),
        ]
    )
    return app


if __name__ == "__main__":
    web.run_app(
        create_app(),
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8080")),
    )
