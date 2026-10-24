"""CORS for the public widget routes only, with per website origin lists.

The widget runs on other people's websites, so the bot endpoints must answer
cross-origin requests. Login and everything behind it must not: a configured
embed origin would otherwise be able to call account routes with the owner's
cookie. This middleware handles CORS itself for the public path prefixes and
passes every other request through untouched.

Which origins are allowed for a bot: the website's own ``allowed_origins``
when it has any, otherwise the global ``ASKHARBOR_ALLOWED_ORIGINS`` list. A
global ``*`` with no per site list answers ``*`` as before.
"""

import re
from collections.abc import Callable, Sequence

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

PUBLIC_PREFIXES: tuple[str, ...] = ("/health", "/api/v1/bots/")
_BOT_PATH = re.compile(r"^/api/v1/bots/([^/]+)")

OriginLookup = Callable[[str], list[str]]


class PublicCORSMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        allow_origins: Sequence[str],
        site_origins: OriginLookup | None = None,
        public_prefixes: Sequence[str] = PUBLIC_PREFIXES,
    ) -> None:
        self.app = app
        self.global_origins = list(allow_origins)
        self.site_origins = site_origins
        self.public_prefixes = tuple(public_prefixes)

    def allowed_for(self, path: str, origin: str) -> str | None:
        """The Access-Control-Allow-Origin value for this request, or None."""
        match = _BOT_PATH.match(path)
        if match and self.site_origins is not None:
            site_list = self.site_origins(match.group(1))
            if site_list:
                return origin if origin in site_list else None
        if self.global_origins == ["*"]:
            return "*"
        return origin if origin in self.global_origins else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self.public_prefixes):
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        origin = headers.get("origin")
        if origin is None:
            await self.app(scope, receive, send)
            return

        allow = self.allowed_for(scope["path"], origin)
        if scope["method"] == "OPTIONS" and "access-control-request-method" in headers:
            if allow is None:
                response = PlainTextResponse("Disallowed CORS origin", status_code=400)
            else:
                response = PlainTextResponse("OK", status_code=200)
                response.headers["Access-Control-Allow-Origin"] = allow
                response.headers["Access-Control-Allow-Methods"] = "GET, POST"
                response.headers["Access-Control-Allow-Headers"] = "Content-Type"
                response.headers["Access-Control-Max-Age"] = "600"
                if allow != "*":
                    response.headers["Vary"] = "Origin"
            await response(scope, receive, send)
            return

        async def send_with_cors(message: Message) -> None:
            if message["type"] == "http.response.start" and allow is not None:
                response_headers = MutableHeaders(scope=message)
                response_headers["Access-Control-Allow-Origin"] = allow
                if allow != "*":
                    response_headers.add_vary_header("Origin")
            await send(message)

        await self.app(scope, receive, send_with_cors)
