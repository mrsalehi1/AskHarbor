"""Admin only: users, websites, memberships and the full audit log.

Every route depends on ``admin_user``: signed in, password change done, and
``is_admin``. Everything an admin changes is written to the audit log in the
same transaction.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from . import audit, auth
from .auth_routes import WEBSITE_NOT_FOUND, AuthService, enforce_same_origin
from .content import ID_PATTERN
from .orm import (
    MAX_SLUG_LENGTH,
    MAX_USERNAME_LENGTH,
    MAX_WEBSITE_NAME_LENGTH,
    AuditEntry,
    BotContent,
    User,
    Website,
    WebsiteMember,
)
from .storage import InvalidSetting, normalize_domain, starter_document


class UserSummary(BaseModel):
    id: int
    username: str
    is_admin: bool
    is_active: bool
    must_change_password: bool
    created_at: datetime
    last_login_at: datetime | None
    websites: list[str]


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=MAX_USERNAME_LENGTH, pattern=ID_PATTERN)
    password: str = Field(min_length=1, max_length=auth.MAX_PASSWORD_LENGTH)
    is_admin: bool = False


class UpdateUserRequest(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=1, max_length=auth.MAX_PASSWORD_LENGTH)


class WebsiteAdminSummary(BaseModel):
    id: int
    slug: str
    name: str
    domain: str | None
    allowed_origins: list[str]
    members: list[str]


class CreateWebsiteRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=MAX_SLUG_LENGTH, pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=MAX_WEBSITE_NAME_LENGTH)
    domain: str | None = None


class AddMemberRequest(BaseModel):
    user_id: int


class AuditEntryOut(BaseModel):
    id: int
    at: datetime
    username: str | None
    action: str
    target_type: str | None
    target_id: str | None
    website_slug: str | None
    details: dict | None
    client_address: str | None


def audit_out(entry: AuditEntry) -> AuditEntryOut:
    return AuditEntryOut(
        id=entry.id,
        at=entry.at,
        username=entry.username,
        action=entry.action,
        target_type=entry.target_type,
        target_id=entry.target_id,
        website_slug=entry.website_slug,
        details=entry.details,
        client_address=entry.client_address,
    )


def build_admin_router(service: AuthService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
    Admin = Annotated[User, Depends(service.admin_user)]

    def user_summary(user: User) -> UserSummary:
        return UserSummary(
            id=user.id,
            username=user.username,
            is_admin=user.is_admin,
            is_active=user.is_active,
            must_change_password=user.must_change_password,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            websites=sorted(member.website.slug for member in user.memberships),
        )

    def website_summary(website: Website) -> WebsiteAdminSummary:
        return WebsiteAdminSummary(
            id=website.id,
            slug=website.slug,
            name=website.name,
            domain=website.domain,
            allowed_origins=list(website.allowed_origins),
            members=sorted(member.user.username for member in website.members),
        )

    # --- users ----------------------------------------------------------------

    @router.get("/users", response_model=list[UserSummary])
    def list_users(_: Admin) -> list[UserSummary]:
        with service.session() as db:
            users = db.execute(select(User).order_by(User.username)).scalars().all()
            return [user_summary(user) for user in users]

    @router.post("/users", response_model=UserSummary, status_code=status.HTTP_201_CREATED)
    def create_user(payload: CreateUserRequest, admin: Admin, request: Request) -> UserSummary:
        enforce_same_origin(request)
        try:
            auth.check_password_policy(payload.password)
        except auth.PasswordPolicyError as error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from None
        with service.session() as db:
            user = User(
                username=payload.username,
                password_hash=auth.hash_password(payload.password),
                is_admin=payload.is_admin,
                is_active=True,
                must_change_password=True,
            )
            db.add(user)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                raise HTTPException(
                    status.HTTP_409_CONFLICT, f"A user named '{payload.username}' already exists."
                ) from None
            audit.record(
                db,
                "user_create",
                user=admin,
                request=request,
                target_type="user",
                target_id=user.id,
                details={"username": user.username, "is_admin": user.is_admin},
            )
            db.commit()
            db.refresh(user)
            return user_summary(user)

    @router.patch("/users/{user_id}", response_model=UserSummary)
    def update_user(
        user_id: int, payload: UpdateUserRequest, admin: Admin, request: Request
    ) -> UserSummary:
        enforce_same_origin(request)
        with service.session() as db:
            user = db.get(User, user_id)
            if user is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
            if user.id == admin.id and (payload.is_active is False or payload.is_admin is False):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "You cannot deactivate yourself or remove your own admin access.",
                )
            changes: dict[str, bool] = {}
            if payload.is_active is not None and payload.is_active != user.is_active:
                user.is_active = payload.is_active
                changes["is_active"] = payload.is_active
                if not payload.is_active:
                    auth.revoke_other_sessions(db, user, keep=None)
            if payload.is_admin is not None and payload.is_admin != user.is_admin:
                user.is_admin = payload.is_admin
                changes["is_admin"] = payload.is_admin
            if changes:
                audit.record(
                    db,
                    "user_update",
                    user=admin,
                    request=request,
                    target_type="user",
                    target_id=user.id,
                    details={"username": user.username, **changes},
                )
            db.commit()
            db.refresh(user)
            return user_summary(user)

    @router.post("/users/{user_id}/password", response_model=UserSummary)
    def reset_password(
        user_id: int, payload: ResetPasswordRequest, admin: Admin, request: Request
    ) -> UserSummary:
        """Give a user a temporary password. Their sessions end and they must change it."""
        enforce_same_origin(request)
        try:
            auth.check_password_policy(payload.new_password)
        except auth.PasswordPolicyError as error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from None
        with service.session() as db:
            user = db.get(User, user_id)
            if user is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
            user.password_hash = auth.hash_password(payload.new_password)
            user.must_change_password = True
            user.password_changed_at = None
            auth.revoke_other_sessions(db, user, keep=None)
            audit.record(
                db,
                "user_password_reset",
                user=admin,
                request=request,
                target_type="user",
                target_id=user.id,
                details={"username": user.username},
            )
            db.commit()
            db.refresh(user)
            return user_summary(user)

    # --- websites -------------------------------------------------------------

    @router.get("/websites", response_model=list[WebsiteAdminSummary])
    def list_websites(_: Admin) -> list[WebsiteAdminSummary]:
        with service.session() as db:
            websites = db.execute(select(Website).order_by(Website.slug)).scalars().all()
            return [website_summary(site) for site in websites]

    @router.post(
        "/websites", response_model=WebsiteAdminSummary, status_code=status.HTTP_201_CREATED
    )
    def create_website(
        payload: CreateWebsiteRequest, admin: Admin, request: Request
    ) -> WebsiteAdminSummary:
        """Create a website with a starter bot so its widget works at once."""
        enforce_same_origin(request)
        try:
            domain = normalize_domain(payload.domain)
        except InvalidSetting as error:
            raise HTTPException(422, str(error)) from None
        with service.session() as db:
            website = Website(slug=payload.slug, name=payload.name, domain=domain)
            db.add(website)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                raise HTTPException(
                    status.HTTP_409_CONFLICT, f"A website with ID '{payload.slug}' already exists."
                ) from None
            db.add(
                BotContent(
                    website_id=website.id,
                    document=starter_document(payload.slug, payload.name),
                    revision=1,
                    updated_by=admin.id,
                )
            )
            audit.record(
                db,
                "website_create",
                user=admin,
                request=request,
                target_type="website",
                target_id=website.slug,
                website_slug=website.slug,
                details={"name": website.name, "domain": domain},
            )
            db.commit()
            db.refresh(website)
            return website_summary(website)

    @router.delete("/websites/{slug}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_website(slug: str, admin: Admin, request: Request) -> None:
        enforce_same_origin(request)
        with service.session() as db:
            website = db.execute(select(Website).where(Website.slug == slug)).scalar_one_or_none()
            if website is None:
                raise WEBSITE_NOT_FOUND
            audit.record(
                db,
                "website_delete",
                user=admin,
                request=request,
                target_type="website",
                target_id=slug,
                website_slug=slug,
                details={"name": website.name},
            )
            db.delete(website)
            db.commit()
        service.site_origins_changed(slug)

    # --- memberships ---------------------------------------------------------------

    @router.post(
        "/websites/{slug}/members",
        response_model=WebsiteAdminSummary,
        status_code=status.HTTP_201_CREATED,
    )
    def add_member(
        slug: str, payload: AddMemberRequest, admin: Admin, request: Request
    ) -> WebsiteAdminSummary:
        enforce_same_origin(request)
        with service.session() as db:
            website = db.execute(select(Website).where(Website.slug == slug)).scalar_one_or_none()
            if website is None:
                raise WEBSITE_NOT_FOUND
            user = db.get(User, payload.user_id)
            if user is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
            existing = db.get(WebsiteMember, (website.id, user.id))
            if existing is None:
                db.add(WebsiteMember(website_id=website.id, user_id=user.id))
                audit.record(
                    db,
                    "member_add",
                    user=admin,
                    request=request,
                    target_type="user",
                    target_id=user.id,
                    website_slug=slug,
                    details={"username": user.username},
                )
            db.commit()
            db.refresh(website)
            return website_summary(website)

    @router.delete("/websites/{slug}/members/{user_id}", response_model=WebsiteAdminSummary)
    def remove_member(
        slug: str, user_id: int, admin: Admin, request: Request
    ) -> WebsiteAdminSummary:
        enforce_same_origin(request)
        with service.session() as db:
            website = db.execute(select(Website).where(Website.slug == slug)).scalar_one_or_none()
            if website is None:
                raise WEBSITE_NOT_FOUND
            member = db.get(WebsiteMember, (website.id, user_id))
            if member is not None:
                audit.record(
                    db,
                    "member_remove",
                    user=admin,
                    request=request,
                    target_type="user",
                    target_id=user_id,
                    website_slug=slug,
                    details={"username": member.user.username},
                )
                db.delete(member)
            db.commit()
            db.refresh(website)
            return website_summary(website)

    # --- audit -----------------------------------------------------------------------

    @router.get("/audit", response_model=list[AuditEntryOut])
    def full_audit_log(_: Admin, limit: int = 200) -> list[AuditEntryOut]:
        with service.session() as db:
            return [audit_out(entry) for entry in audit.recent(db, limit=min(limit, 1000))]

    return router
