"""Login, logout, current user and password change, plus the access dependencies
every protected route uses.

Cross-site request protection has three layers. The session cookie is
SameSite=Lax, so browsers do not attach it to cross-site POSTs. State changing
routes compare the Origin (or Referer) host with the Host header and reject
mismatches. And request bodies must be JSON, which an HTML form cannot produce.
CORS never applies to these routes; it is scoped to the public bot endpoints.
"""

from collections.abc import Callable
from datetime import timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import audit, auth
from .config import Settings
from .login_limit import DatabaseLoginLimiter
from .orm import LoginSession, User, Website, WebsiteMember
from .rate_limit import FixedWindowRateLimiter

COOKIE_NAME = "askharbor_session"
PASSWORD_CHANGE_REQUIRED = "password_change_required"

_ACCOUNTS_DISABLED = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail=(
        "Accounts are not configured on this server. Set ASKHARBOR_DATABASE_URL and run the "
        "migrations to enable login; see 'Accounts and login' in README.md."
    ),
)
_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password."
)
_NOT_SIGNED_IN = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in.")
_ADMIN_REQUIRED = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required."
)
WEBSITE_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Website not found."
)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=auth.MAX_PASSWORD_LENGTH)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=auth.MAX_PASSWORD_LENGTH)
    new_password: str = Field(min_length=1, max_length=auth.MAX_PASSWORD_LENGTH)


class CurrentUser(BaseModel):
    username: str
    is_admin: bool
    must_change_password: bool


def current_user_summary(user: User) -> CurrentUser:
    return CurrentUser(
        username=user.username,
        is_admin=user.is_admin,
        must_change_password=user.must_change_password,
    )


def enforce_same_origin(request: Request) -> None:
    """Reject browser requests whose Origin or Referer host differs from ours.

    Only the host is compared, so a TLS terminating proxy that forwards plain
    HTTP does not break logins. Requests without either header come from non
    browser clients, which cannot be the victim of a cross-site request.
    """
    source = request.headers.get("origin") or request.headers.get("referer")
    if source is None:
        return
    if urlsplit(source).netloc != request.headers.get("host"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Cross-site request rejected."
        )


class AuthService:
    """Holds what the protected routes need: settings, the database and the limiter.

    With a database the failed-login counters live in it and are shared by every
    worker. Without one accounts are disabled and the in-memory limiter is only
    kept so the attributes exist.
    """

    def __init__(self, settings: Settings, factory: sessionmaker[Session] | None) -> None:
        self.settings = settings
        self.factory = factory
        # Set by main.py to drop a website's cached origins after a settings change.
        self.site_origins_changed: Callable[[str], None] = lambda slug: None
        self.login_limiter: DatabaseLoginLimiter | FixedWindowRateLimiter
        if factory is not None:
            self.login_limiter = DatabaseLoginLimiter(
                factory, settings.login_rate_limit, settings.login_rate_window_seconds
            )
        else:
            self.login_limiter = FixedWindowRateLimiter(
                limit=settings.login_rate_limit,
                window_seconds=settings.login_rate_window_seconds,
            )

    @property
    def enabled(self) -> bool:
        return self.factory is not None

    def session(self) -> Session:
        if self.factory is None:
            raise _ACCOUNTS_DISABLED
        return self.factory()

    # --- dependencies -------------------------------------------------------

    def current_user(self, request: Request) -> tuple[User, LoginSession]:
        """The signed in user, forced password change or not."""
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            raise _NOT_SIGNED_IN
        with self.session() as db, db.begin():
            found = auth.find_session(db, token)
            if found is None:
                raise _NOT_SIGNED_IN
            login_session, user = found
            db.expunge(user)
            db.expunge(login_session)
        return user, login_session

    def active_user(self, request: Request) -> User:
        """A signed in user whose password change, if required, is done.

        Every route except login, logout, "who am I" and the password change
        itself depends on this, so a bootstrap admin or a user whose password
        was reset cannot do anything with a temporary password.
        """
        user, _ = self.current_user(request)
        if user.must_change_password:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": PASSWORD_CHANGE_REQUIRED,
                    "message": "Change your password before using this account.",
                },
            )
        return user

    def admin_user(self, request: Request) -> User:
        user = self.active_user(request)
        if not user.is_admin:
            raise _ADMIN_REQUIRED
        return user

    @staticmethod
    def load_website(db: Session, slug: str, user: User) -> Website:
        """The website if ``user`` may edit it, otherwise 404.

        Admins see every website. Everyone else only the ones they are a member
        of, and a website they cannot access looks exactly like one that does
        not exist.
        """
        statement = select(Website).where(Website.slug == slug)
        if not user.is_admin:
            statement = statement.join(
                WebsiteMember, WebsiteMember.website_id == Website.id
            ).where(WebsiteMember.user_id == user.id)
        website = db.execute(statement).scalar_one_or_none()
        if website is None:
            raise WEBSITE_NOT_FOUND
        return website

    # --- cookie helpers -------------------------------------------------------

    def set_cookie(self, response: Response, token: str) -> None:
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            max_age=self.settings.session_hours * 3600,
            path="/",
            httponly=True,
            secure=self.settings.cookie_secure,
            samesite="lax",
        )

    def clear_cookie(self, response: Response) -> None:
        response.delete_cookie(
            key=COOKIE_NAME,
            path="/",
            httponly=True,
            secure=self.settings.cookie_secure,
            samesite="lax",
        )


def verify_login(user: User | None, password_hash: str | None, password: str) -> bool:
    """True only for an existing, active user with the right password.

    The hash check always runs, against a dummy hash for unknown names, so the
    response time does not reveal whether an account exists.
    """
    matches = auth.verify_password(password_hash, password)
    return matches and user is not None and user.is_active


def build_router(service: AuthService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["accounts"])
    settings = service.settings

    @router.post("/login", response_model=CurrentUser)
    def login(payload: LoginRequest, request: Request, response: Response) -> CurrentUser:
        if not service.enabled:
            raise _ACCOUNTS_DISABLED
        enforce_same_origin(request)
        client_key = f"ip:{request.client.host if request.client else 'unknown'}"
        user_key = f"user:{payload.username.lower()}"
        for key in (client_key, user_key):
            retry_after = service.login_limiter.peek(key)
            if retry_after is not None:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many login attempts. Try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )

        with service.session() as db:
            user = db.execute(
                select(User).where(User.username == payload.username)
            ).scalar_one_or_none()
            password_hash = user.password_hash if user is not None else None
            if not verify_login(user, password_hash, payload.password):
                # Only failures consume the budget, for the address and the name.
                service.login_limiter.hit(client_key)
                service.login_limiter.hit(user_key)
                audit.record(
                    db,
                    "login_failed",
                    user=None,
                    request=request,
                    target_type="user",
                    target_id=payload.username[:120],
                )
                db.commit()  # the audit row must survive the 401 below
                raise _INVALID_CREDENTIALS
            assert user is not None
            if auth.password_needs_rehash(user.password_hash):
                user.password_hash = auth.hash_password(payload.password)
            token = auth.create_session(db, user, timedelta(hours=settings.session_hours))
            audit.record(db, "login", user=user, request=request)
            summary = current_user_summary(user)
            db.commit()
        service.set_cookie(response, token)
        return summary

    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
    def logout(request: Request) -> Response:
        if not service.enabled:
            raise _ACCOUNTS_DISABLED
        enforce_same_origin(request)
        token = request.cookies.get(COOKIE_NAME)
        if token:
            with service.session() as db, db.begin():
                found = auth.find_session(db, token)
                if found is not None:
                    auth.revoke_session(db, found[0])
                    audit.record(db, "logout", user=found[1], request=request)
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        service.clear_cookie(response)
        return response

    @router.get("/me", response_model=CurrentUser)
    def me(request: Request) -> CurrentUser:
        if not service.enabled:
            raise _ACCOUNTS_DISABLED
        user, _ = service.current_user(request)
        return current_user_summary(user)

    @router.post("/password", response_model=CurrentUser)
    def change_password(payload: PasswordChangeRequest, request: Request) -> CurrentUser:
        if not service.enabled:
            raise _ACCOUNTS_DISABLED
        enforce_same_origin(request)
        user, login_session = service.current_user(request)
        with service.session() as db, db.begin():
            user = db.get(User, user.id)
            login_session = db.get(LoginSession, login_session.id)
            assert user is not None and login_session is not None
            try:
                auth.change_password(
                    db, user, payload.current_password, payload.new_password, keep=login_session
                )
            except auth.PasswordPolicyError as error:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
                ) from None
            audit.record(db, "password_change", user=user, request=request)
            summary = current_user_summary(user)
        return summary

    return router
