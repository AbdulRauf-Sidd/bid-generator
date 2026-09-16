from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.database import get_db
from app.models import User
from app.schemas import GoogleAuthRequest, GoogleAuthResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _verify_google_id_token(token: str) -> dict:
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID is not configured")

    try:
        return google_id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid Google ID token") from exc
    except GoogleAuthError as exc:
        raise HTTPException(status_code=401, detail="Unable to verify Google ID token") from exc


@router.post("/google", response_model=GoogleAuthResponse, summary="Sign in with Google")
async def google_auth(data: GoogleAuthRequest, db: AsyncSession = Depends(get_db)):
    payload = await run_in_threadpool(_verify_google_id_token, data.id_token.strip())

    google_sub = payload.get("sub")
    email = payload.get("email")
    if not google_sub or not email:
        raise HTTPException(status_code=401, detail="Google profile is missing required user data")

    now = datetime.utcnow()
    result = await db.execute(
        select(User).where(or_(User.google_sub == google_sub, User.email == email))
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(google_sub=google_sub, email=email)
        db.add(user)

    user.google_sub = google_sub
    user.email = email
    user.email_verified = bool(payload.get("email_verified", False))
    user.name = payload.get("name")
    user.given_name = payload.get("given_name")
    user.family_name = payload.get("family_name")
    user.picture = payload.get("picture")
    user.locale = payload.get("locale")
    user.provider = "google"
    user.raw_profile = payload
    user.last_login_at = now
    user.updated_at = now

    await db.commit()
    await db.refresh(user)

    return GoogleAuthResponse(user=user, message="Google sign-in successful")
