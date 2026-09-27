"""Operational commands: ``flask --app backend.app xrays <command>``."""

import click
from flask import current_app
from flask.cli import AppGroup
from sqlalchemy.orm import undefer

from backend.extensions import db
from backend.models import XRay, XRayImage
from backend.services.storage import LocalFileStorage
from backend.services.xray_images import XRayImageError, _open, pixel_sha256, verify_full, _sha256

xrays_cli = AppGroup("xrays", help="X-ray storage maintenance.")


@xrays_cli.command("import-legacy")
@click.option("--delete-files", is_flag=True, help="Delete each legacy file after it is verified in the database.")
def import_legacy(delete_files):
    """Copy X-rays still stored on the server filesystem into PostgreSQL (byte-for-byte)."""
    storage = LocalFileStorage(current_app.config["AERODENT_STORAGE_PATH"])
    pending = db.session.scalars(
        db.select(XRay).where(XRay.storage_key.is_not(None)).outerjoin(
            XRayImage, (XRayImage.xray_id == XRay.id) & (XRayImage.clinic_id == XRay.clinic_id)
        ).where(XRayImage.id.is_(None))
    ).all()
    imported = missing = invalid = 0
    for xray in pending:
        try:
            with storage.open(xray.storage_key) as handle:
                content = handle.read()
        except (FileNotFoundError, ValueError, OSError):
            missing += 1
            click.echo(f"missing file for X-ray {xray.id}: {xray.storage_key}")
            continue
        try:
            image = _open(content)
        except XRayImageError:
            invalid += 1
            click.echo(f"unreadable file for X-ray {xray.id}")
            continue
        # Stored exactly as found. These were produced by the old pipeline, which resized and
        # re-encoded uploads as lossy WebP; they are labelled so and cannot be restored.
        xray.image = XRayImage(
            clinic_id=xray.clinic_id,
            data=content,
            mime_type=xray.mime_type or "image/webp",
            image_format=image.format or "WEBP",
            encoding="legacy-webp",
            size_bytes=len(content),
            sha256=_sha256(content),
            width=image.width,
            height=image.height,
            color_mode=image.mode,
            pixel_sha256=pixel_sha256(image),
            original_filename=xray.filename,
            original_mime_type=xray.original_mime_type,
            original_size_bytes=len(content),
            original_sha256=_sha256(content),
        )
        db.session.commit()
        legacy_key = xray.storage_key
        if delete_files:
            xray.storage_key = None
            db.session.commit()
            storage.delete(legacy_key)
        imported += 1
    click.echo(f"imported={imported} missing={missing} invalid={invalid}")


@xrays_cli.command("verify")
def verify_all():
    """Re-hash and re-decode every stored X-ray; exits non-zero if any fails."""
    failures = 0
    ids = db.session.scalars(db.select(XRayImage.id).order_by(XRayImage.id)).all()
    for image_id in ids:
        record = db.session.scalar(
            db.select(XRayImage).options(undefer(XRayImage.data)).where(XRayImage.id == image_id)
        )
        ok, reason = verify_full(record, record.data)
        if not ok:
            failures += 1
            click.echo(f"FAILED xray_id={record.xray_id} clinic_id={record.clinic_id}: {reason}")
        db.session.expunge(record)
    click.echo(f"verified={len(ids) - failures} failed={failures}")
    if failures:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# Accounts: ``flask --app backend.app admin <command>``
# ---------------------------------------------------------------------------

admin_cli = AppGroup("admin", help="Platform account management (run on the server).")


def _prompt_new_password():
    from backend.services.auth_security import validate_new_password

    while True:
        password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
        error = validate_new_password(password)
        if error is None:
            return password
        click.echo(f"  {error}", err=True)


@admin_cli.command("create-super-admin")
@click.option("--email", prompt=True, help="Sign-in e-mail of the platform administrator.")
@click.option("--name", prompt=True, default="Platform Super Admin", show_default=True)
def create_super_admin(email, name):
    """Creates the platform Super Admin (the account that creates clinics)."""
    from backend.auth.service import hash_password
    from backend.models import User

    email = email.strip().lower()
    if "@" not in email or len(email) > 255:
        raise click.ClickException("Enter a valid e-mail address.")
    if db.session.scalar(db.select(User.id).where(db.func.lower(User.email) == email)) is not None:
        raise click.ClickException("An account with this e-mail already exists (use `admin reset-password`).")
    password = _prompt_new_password()
    db.session.add(User(clinic_id=None, name=name.strip()[:120] or "Platform Super Admin", email=email,
                        password_hash=hash_password(password), role="super_admin", is_active=True))
    db.session.commit()
    click.echo(f"Super Admin {email} created. Sign in at your site's address.")


@admin_cli.command("reset-password")
@click.option("--email", prompt=True, help="E-mail of the account to reset.")
def reset_password(email):
    """Sets a new password for any account and signs it out everywhere (account recovery)."""
    from backend.auth.service import hash_password
    from backend.models import User
    from backend.services.auth_security import revoke_user_sessions

    user = db.session.scalar(db.select(User).where(db.func.lower(User.email) == email.strip().lower()))
    if user is None:
        raise click.ClickException("No account with this e-mail.")
    user.password_hash = hash_password(_prompt_new_password())
    revoke_user_sessions(user.id)
    db.session.commit()
    click.echo(f"Password for {user.email} updated; all of its sessions were signed out.")
