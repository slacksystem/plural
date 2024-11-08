from logging import getLogger, Filter, LogRecord
from fastapi import FastAPI, Response, Request
from contextlib import asynccontextmanager
from src.api.drest import start_drest
from src.api.docs import root as docs


class LocalHealthcheckFilter(Filter):
    def filter(self, record: LogRecord) -> bool:
        return not bool(
            isinstance(record.args, tuple) and
            len(record.args) == 5 and
            all((
                str(record.args[0]).startswith('172'),
                record.args[1] == 'GET',
                record.args[2] == '/healthcheck',
                record.args[4] == 204
            ))
        )


getLogger("uvicorn.access").addFilter(LocalHealthcheckFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.models import project
    from src.db import MongoDatabase
    DB = MongoDatabase(project.mongo_uri)

    await DB.connect()
    await start_drest()
    from src.api.drest import drest_client

    from .routers import image, message, latch, member, group, userproxy
    app.include_router(userproxy.router)
    app.include_router(message.router)
    app.include_router(member.router)
    app.include_router(latch.router)
    app.include_router(image.router)
    app.include_router(group.router)

    yield

    await drest_client.close()
    from src.api.drest import drest_app
    from src.api.models.discord.interaction.response import session
    await drest_app.close()
    await session.close()


app = FastAPI(
    title='/plu/ral API',
    description='get an API key by running /api on the bot',
    lifespan=lifespan,
    docs_url='/swdocs',
    redoc_url='/docs',
    version="1.0.0"
)


@app.middleware("http")
async def set_client_ip(request: Request, call_next):
    client_ip = request.headers.get('CF-Connecting-IP')
    if client_ip and request.client is not None:
        request.scope['client'] = (client_ip, request.scope['client'][1])
    response = await call_next(request)
    return response


@app.get(
    '/',
    responses=docs.get__root)
async def get__root():
    return {'message': 'this is very basic i\'ll work on it later'}


@app.get(
    '/healthcheck',
    status_code=204)
async def get__healthcheck():
    return Response(status_code=204)
