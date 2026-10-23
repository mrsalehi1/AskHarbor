"""What a signed in user does with the websites they may edit.

Every route goes through ``load_website``: admins reach every website, other
users only the ones they are members of, and anything else is a 404. Content
saves carry the revision they started from and get 409 when someone else
saved first. Export and import move a complete backup (settings and content)
as one JSON document.
"""

import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import audit
from .admin_routes import AuditEntryOut, audit_out
from .auth_routes import AuthService, enforce_same_origin
from .content import InvalidBotContent, validate_bot_content
from .orm import MAX_WEBSITE_NAME_LENGTH, BotContent, User, Website
from .storage import (
    InvalidSetting,
    RevisionConflict,
    get_bot_document,
    normalize_domain,
    normalize_origins,
    save_bot_document,
)

BACKUP_VERSION = 1


class WebsiteSummary(BaseModel):
    slug: str
    name: str
    domain: str | None


class WebsiteDetails(WebsiteSummary):
    allowed_origins: list[str]
    revision: int
    api_url: str
    widget_url: str
    embed_snippet: str
    members: list[str]
    can_manage: bool


class SettingsUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=MAX_WEBSITE_NAME_LENGTH)
    domain: str | None = None
    allowed_origins: list[str] | None = None


class ContentOut(BaseModel):
    document: dict[str, Any]
    revision: int


class ContentSave(BaseModel):
    document: dict[str, Any]
    revision: int


class SaveResult(BaseModel):
    revision: int


class ImportResult(BaseModel):
    revision: int
    applied: list[str]


def embed_snippet(api_url: str, widget_url: str, slug: str) -> str:
    return (
        f'<script\n  src="{widget_url}"\n  data-api-url="{api_url}"\n'
        f'  data-bot-id="{slug}"\n  defer\n></script>'
    )


def _validation_error(message: str, problems: list) -> HTTPException:
    return HTTPException(
        422,
        {
            "message": message,
            "problems": [{"path": p.path, "message": p.message} for p in problems],
        },
    )


def _check_document(document: Any, slug: str) -> None:
    try:
        validate_bot_content(document)
    except InvalidBotContent as error:
        raise _validation_error("The bot content is not valid.", error.problems) from None
    if document["config"]["id"] != slug:
        raise HTTPException(
            422,
            {
                "message": "The bot content is not valid.",
                "problems": [
                    {
                        "path": "config.id",
                        "message": f"must equal the website ID '{slug}'",
                    }
                ],
            },
        )


def build_website_router(service: AuthService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/websites", tags=["websites"])
    Current = Annotated[User, Depends(service.active_user)]
    settings = service.settings

    def base_url(request: Request) -> str:
        return (settings.public_url or str(request.base_url)).rstrip("/")

    def details(db, website: Website, user: User, request: Request) -> WebsiteDetails:
        revision = db.execute(
            select(BotContent.revision).where(BotContent.website_id == website.id)
        ).scalar_one_or_none()
        api_url = base_url(request)
        widget_url = f"{api_url}/admin/askharbor.js"
        return WebsiteDetails(
            slug=website.slug,
            name=website.name,
            domain=website.domain,
            allowed_origins=list(website.allowed_origins),
            revision=revision or 0,
            api_url=api_url,
            widget_url=widget_url,
            embed_snippet=embed_snippet(api_url, widget_url, website.slug),
            members=sorted(member.user.username for member in website.members),
            can_manage=user.is_admin,
        )

    @router.get("", response_model=list[WebsiteSummary])
    def list_websites(user: Current) -> list[WebsiteSummary]:
        with service.session() as db:
            statement = select(Website).order_by(Website.slug)
            if not user.is_admin:
                from .orm import WebsiteMember

                statement = statement.join(
                    WebsiteMember, WebsiteMember.website_id == Website.id
                ).where(WebsiteMember.user_id == user.id)
            return [
                WebsiteSummary(slug=site.slug, name=site.name, domain=site.domain)
                for site in db.execute(statement).scalars()
            ]

    @router.get("/{slug}", response_model=WebsiteDetails)
    def website_details(slug: str, user: Current, request: Request) -> WebsiteDetails:
        with service.session() as db:
            website = service.load_website(db, slug, user)
            return details(db, website, user, request)

    @router.patch("/{slug}", response_model=WebsiteDetails)
    def update_settings(
        slug: str, payload: SettingsUpdate, user: Current, request: Request
    ) -> WebsiteDetails:
        enforce_same_origin(request)
        with service.session() as db:
            website = service.load_website(db, slug, user)
            changes: dict[str, Any] = {}
            try:
                if payload.name is not None and payload.name != website.name:
                    website.name = payload.name
                    changes["name"] = payload.name
                if payload.domain is not None:
                    domain = normalize_domain(payload.domain)
                    if domain != website.domain:
                        website.domain = domain
                        changes["domain"] = domain
                if payload.allowed_origins is not None:
                    origins = normalize_origins(payload.allowed_origins)
                    if origins != list(website.allowed_origins):
                        website.allowed_origins = origins
                        changes["allowed_origins"] = origins
            except InvalidSetting as error:
                raise HTTPException(422, str(error)) from None
            if changes:
                audit.record(
                    db,
                    "settings_update",
                    user=user,
                    request=request,
                    target_type="website",
                    target_id=slug,
                    website_slug=slug,
                    details=changes,
                )
            db.commit()
            db.refresh(website)
            result = details(db, website, user, request)
        service.site_origins_changed(slug)
        return result

    @router.get("/{slug}/content", response_model=ContentOut)
    def get_content(slug: str, user: Current) -> ContentOut:
        with service.session() as db:
            service.load_website(db, slug, user)
            stored = get_bot_document(db, slug)
            if stored is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "This website has no bot yet.")
            return ContentOut(document=stored[0], revision=stored[1])

    @router.put("/{slug}/content", response_model=SaveResult)
    def save_content(
        slug: str, payload: ContentSave, user: Current, request: Request
    ) -> SaveResult:
        enforce_same_origin(request)
        _check_document(payload.document, slug)
        with service.session() as db:
            service.load_website(db, slug, user)
            try:
                revision = save_bot_document(
                    db, slug, payload.document, payload.revision, updated_by=user.id
                )
            except RevisionConflict as error:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    {
                        "code": "revision_conflict",
                        "current_revision": error.current_revision,
                        "message": str(error),
                    },
                ) from None
            audit.record(
                db,
                "content_save",
                user=user,
                request=request,
                target_type="website",
                target_id=slug,
                website_slug=slug,
                details={"revision": revision},
            )
            db.commit()
        return SaveResult(revision=revision)

    @router.get("/{slug}/export")
    def export_backup(slug: str, user: Current, request: Request) -> Response:
        """Settings and content as one JSON file for safekeeping or moving."""
        with service.session() as db:
            website = service.load_website(db, slug, user)
            stored = get_bot_document(db, slug)
            backup = {
                "askharbor_backup": BACKUP_VERSION,
                "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "website": {
                    "slug": website.slug,
                    "name": website.name,
                    "domain": website.domain,
                    "allowed_origins": list(website.allowed_origins),
                },
                "content": stored[0] if stored else None,
                "revision": stored[1] if stored else 0,
            }
            audit.record(
                db,
                "backup_export",
                user=user,
                request=request,
                target_type="website",
                target_id=slug,
                website_slug=slug,
            )
            db.commit()
        body = json.dumps(backup, indent=2, ensure_ascii=False) + "\n"
        return Response(
            content=body,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{slug}-askharbor-backup.json"'
            },
        )

    @router.post("/{slug}/import", response_model=ImportResult)
    def import_backup(slug: str, payload: dict[str, Any], user: Current, request: Request):
        """Restore a backup, or load a plain bot content document, into this website.

        Everything is validated before anything changes. The bot ID inside the
        content is set to this website's ID, so a backup from another website
        can be loaded here. Settings are applied only from a full backup.
        """
        enforce_same_origin(request)
        if "askharbor_backup" in payload:
            if payload.get("askharbor_backup") != BACKUP_VERSION:
                raise HTTPException(
                    422,
                    f"Unsupported backup version {payload.get('askharbor_backup')!r}.",
                )
            content = payload.get("content")
            site = payload.get("website") or {}
        elif "format_version" in payload:
            content = payload
            site = {}
        else:
            raise HTTPException(
                422,
                "This is neither an AskHarbor backup nor a bot content file.",
            )
        if not isinstance(content, dict):
            raise HTTPException(422, "The backup has no content.")
        content = json.loads(json.dumps(content))
        if isinstance(content.get("config"), dict):
            content["config"]["id"] = slug
        _check_document(content, slug)
        try:
            new_name = site.get("name")
            new_domain = normalize_domain(site.get("domain")) if "domain" in site else None
            new_origins = (
                normalize_origins(list(site.get("allowed_origins") or []))
                if "allowed_origins" in site
                else None
            )
        except InvalidSetting as error:
            raise HTTPException(422, str(error)) from None

        applied: list[str] = ["content"]
        with service.session() as db:
            website = service.load_website(db, slug, user)
            current = db.execute(
                select(BotContent).where(BotContent.website_id == website.id).with_for_update()
            ).scalar_one_or_none()
            if current is None:
                db.add(BotContent(website_id=website.id, document=content, revision=1))
                revision = 1
            else:
                revision = save_bot_document(db, slug, content, current.revision, user.id)
            if site:
                if isinstance(new_name, str) and new_name.strip():
                    website.name = new_name.strip()[:MAX_WEBSITE_NAME_LENGTH]
                if "domain" in site:
                    website.domain = new_domain
                if new_origins is not None:
                    website.allowed_origins = new_origins
                applied.append("settings")
            audit.record(
                db,
                "backup_import",
                user=user,
                request=request,
                target_type="website",
                target_id=slug,
                website_slug=slug,
                details={"revision": revision, "applied": applied},
            )
            db.commit()
        service.site_origins_changed(slug)
        return ImportResult(revision=revision, applied=applied)

    @router.get("/{slug}/audit", response_model=list[AuditEntryOut])
    def website_audit(slug: str, user: Current, limit: int = 100) -> list[AuditEntryOut]:
        with service.session() as db:
            service.load_website(db, slug, user)
            entries = audit.recent(db, website_slug=slug, limit=min(limit, 500))
            return [audit_out(entry) for entry in entries]

    return router
