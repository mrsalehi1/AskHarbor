"""Create or recover an admin account on purpose.

Usage, from server/ with the environment active and ASKHARBOR_DATABASE_URL set:

    python -m app.create_admin USERNAME            # prompts for a temporary password
    python -m app.create_admin USERNAME --reset    # also allowed when USERNAME exists

The password can also be given through ASKHARBOR_NEW_ADMIN_PASSWORD for
scripts. The account is created (or, with --reset, updated) as an active
admin with a temporary password that must be changed at first sign in; a reset
also ends the user's sessions. This is the recovery path when every admin was
deleted or locked out: the automatic bootstrap never runs a second time.
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import select

from . import audit, auth
from .config import get_settings
from .db import session_factory
from .import_content import ALEMBIC_DIR
from .orm import User
from .storage import assert_database_ready


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", help="Login name (letters, digits, - and _)")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="If the user exists, make it an active admin with the new temporary password",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.database_url:
        print(
            "ASKHARBOR_DATABASE_URL is not set; see 'Accounts and login' in README.md.",
            file=sys.stderr,
        )
        return 2

    prompt = (
        f"Temporary password for '{args.username}' "
        f"(at least {auth.MIN_PASSWORD_LENGTH} characters): "
    )
    password = os.environ.get("ASKHARBOR_NEW_ADMIN_PASSWORD") or getpass.getpass(prompt)
    try:
        auth.check_password_policy(password)
    except auth.PasswordPolicyError as error:
        print(str(error), file=sys.stderr)
        return 1

    factory = session_factory(settings.database_url)
    assert_database_ready(factory.kw["bind"], ALEMBIC_DIR)
    with factory() as db, db.begin():
        user = db.execute(select(User).where(User.username == args.username)).scalar_one_or_none()
        if user is not None and not args.reset:
            print(
                f"User '{args.username}' already exists. Use --reset to make it an active admin "
                "with a new temporary password.",
                file=sys.stderr,
            )
            return 1
        if user is None:
            user = User(username=args.username, password_hash=auth.hash_password(password))
            db.add(user)
            action = "admin_create_cli"
        else:
            user.password_hash = auth.hash_password(password)
            auth.revoke_other_sessions(db, user, keep=None)
            action = "admin_reset_cli"
        user.is_admin = True
        user.is_active = True
        user.must_change_password = True
        user.password_changed_at = None
        db.flush()
        if not auth.bootstrap_completed(db):
            auth.mark_bootstrap_completed(db, args.username, how="create_admin")
        audit.record(
            db,
            action,
            user=None,
            target_type="user",
            target_id=user.id,
            details={"username": user.username},
        )
    print(
        f"Admin '{args.username}' is ready. It must change the temporary password at first sign in."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
