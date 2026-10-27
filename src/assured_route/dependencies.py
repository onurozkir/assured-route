import httpx
from fastapi import Request

from assured_route.config import Settings
from assured_route.providers.cheap_model_provider import CheapModelProvider
from assured_route.providers.expensive_model_provider import ExpensiveModelProvider
from assured_route.providers.openai_compatible import (
    OpenAICompatibleProvider,
    OpenAICompatibleVerifier,
)
from assured_route.providers.verifier_provider import MockVerifierProvider
from assured_route.routing.router import Router


def build_router(settings: Settings, *, http_client: httpx.AsyncClient | None = None) -> Router:
    if settings.provider_mode == "openai_compatible":
        client = http_client or httpx.AsyncClient(
            trust_env=False,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        return Router(
            cheap=OpenAICompatibleProvider(
                settings.model_api("cheap"), client, settings.cheap_cost_usd
            ),
            expensive=OpenAICompatibleProvider(
                settings.model_api("expensive"), client, settings.expensive_cost_usd
            ),
            verifier=OpenAICompatibleVerifier(
                settings.model_api("expensive"), client, settings.expensive_cost_usd
            ),
            policy=settings.policy,
            close=client.aclose if http_client is None else None,
        )
    return Router(
        cheap=CheapModelProvider(settings.cheap_cost_usd, settings.mock_cheap_delay_ms),
        expensive=ExpensiveModelProvider(
            settings.expensive_cost_usd, settings.mock_expensive_delay_ms
        ),
        verifier=MockVerifierProvider(settings.verifier_cost_usd, settings.mock_verifier_delay_ms),
        policy=settings.policy,
    )


def get_router(request: Request) -> Router:
    router: Router = request.app.state.router
    return router
