"""احراز هویت ساده با JWT (بدون سرویس خارجی).

POST /api/auth/register — ثبت‌نام (دانش‌آموز/معلم)
POST /api/auth/login    — دریافت توکن JWT
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from models.database import get_db
from models.user import User, VALID_MAJORS, VALID_ROLES

router = APIRouter(prefix="/api/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


# ---------- رمز عبور: PBKDF2-HMAC-SHA256 (بدون وابستگی بیرونی) ----------
def hash_password(password: str) -> str:
    iterations = 120_000
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    # فرمت ذخیره: pbkdf2$<iterations>$<salt_hex>$<hash_hex>
    return "pbkdf2$" + str(iterations) + "$" + salt + "$" + dk.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt, hash_hex = stored.split("$")
        if scheme != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# ---------- توکن ----------
def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "exp": datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="توکن احراز هویت لازم است.")
    try:
        payload = jwt.decode(credentials.credentials, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id = int(payload.get("sub", "0"))
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="نشست منقضی شده است؛ دوباره وارد شوید.")
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="توکن نامعتبر است.")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="کاربر یافت نشد.")
    return user


def require_roles(*roles: str):
    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="دسترسی مجاز نیست.")
        return user

    return _guard


# ---------- اسکیماها ----------
class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    role: str = "student"
    grade: Optional[int] = Field(default=None, ge=1, le=12)
    major: Optional[str] = None
    full_name: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/register", status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"نقش نامعتبر است. نقش‌های مجاز: {sorted(VALID_ROLES)}")
    if body.role == "student" and body.grade is None:
        body.grade = 11  # پیش‌فرض معقول برای دانش‌آموز
    if body.major is not None and body.major not in VALID_MAJORS:
        raise HTTPException(status_code=422, detail=f"رشته نامعتبر است. مقادیر مجاز: {sorted(VALID_MAJORS)}")
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status_code=409, detail="این نام کاربری قبلاً ثبت شده است.")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
        grade=body.grade,
        major=body.major,
        full_name=body.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"user": user.to_public_dict(), "token": create_token(user)}


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="نام کاربری یا رمز عبور اشتباه است.")
    return {"user": user.to_public_dict(), "token": create_token(user)}
