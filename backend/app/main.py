import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from backend.app.api.v1.router import router
from backend.app.core.config import Settings
from backend.app.core.logging import configure_logging
from backend.app.data.repository import FileRepository, Repository
from backend.app.schemas.errors import ErrorResponse


def create_app(
    repo: Repository | None = None, settings: Settings | None = None
) -> FastAPI:
    config = settings or Settings()
    configure_logging(config.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = config
        app.state.repository = (
            repo if repo is not None else FileRepository(config.processed_dir)
        )
        yield

    app = FastAPI(
        title="Wind Decision API",
        version="0.3.0",
        lifespan=lifespan,
        responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Invalid request parameters",
                    "details": [
                        {"loc": list(e["loc"]), "message": e["msg"], "type": e["type"]}
                        for e in exc.errors()
                    ],
                }
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "validation_error"
                    if exc.status_code == 422
                    else "http_error",
                    "message": str(exc.detail),
                    "details": [],
                }
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger(__name__).exception("Request failed: %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Unable to complete request",
                    "details": [],
                }
            },
        )

    app.include_router(router)
    return app


app = create_app()
