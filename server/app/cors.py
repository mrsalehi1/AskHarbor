"""CORS for the public widget routes only.

The widget runs on other people's websites, so the bot endpoints must answer
cross-origin requests. Login and everything behind it must not: a configured
embed origin would otherwise be able to call account routes with the owner's
cookie. This wrapper applies Starlette's CORS middleware to the public path
prefixes and passes every other request through untouched.
"""

from collections.abc import Sequence

from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

PUBLIC_PREFIXES: tuple[str, ...] = ("/health", "/api/v1/bots/")


class PublicCORSMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        allow_origins: Sequence[str],
        public_prefixes: Sequence[str] = PUBLIC_PREFIXES,
    ) -> None:
        self.app = app
        self.public_prefixes = tuple(public_prefixes)
        self.cors = CORSMiddleware(
            app,
            allow_origins=list(allow_origins),
            allow_credentials=list(allow_origins) != ["*"],
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith(self.public_prefixes):
            await self.cors(scope, receive, send)
        else:
            await self.app(scope, receive, send)
