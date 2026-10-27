from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from assured_route import __version__
from assured_route.audit import configure_audit_logging
from assured_route.config import Settings
from assured_route.core.models import ExtractRequest, ExtractResponse
from assured_route.dependencies import build_router, get_router
from assured_route.routing.router import Router


def create_app(settings: Settings | None = None, router: Router | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_audit_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await app.state.router.aclose()

    application = FastAPI(title="Assured Route", version=__version__, lifespan=lifespan)
    application.state.router = router or build_router(settings)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": [{"loc": error["loc"], "type": error["type"]} for error in exc.errors()]
            },
        )

    @application.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @application.post("/extract", response_model=ExtractResponse)
    async def extract(
        body: ExtractRequest, service: Annotated[Router, Depends(get_router)]
    ) -> ExtractResponse:
        try:
            service.policy.with_overrides(body.policy)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        return await service.extract(body)

    return application


app = create_app()

# TODO: Authenticate at ingress and resolve metadata/policy per trusted tenant configuration.
