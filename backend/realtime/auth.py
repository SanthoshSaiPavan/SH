"""JWT issue/verify and role checks for HTTP routes and the Socket.IO handshake."""
from datetime import timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import config
from utils import clock

bearer = HTTPBearer(auto_error=False)
SIMULATOR_SUBJECT = "gps-simulator"


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_token(subject: str, role: str, vehicle_ids: list[str] | None = None) -> str:
    if role not in config.ROLES:
        raise ValueError(f"Unknown role {role}")
    payload = {
        "sub": subject,
        "role": role,
        "vehicle_ids": vehicle_ids or [],
        "exp": clock.utcnow() + timedelta(minutes=config.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Raises jwt.PyJWTError on an invalid or expired token."""
    return jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        return decode_token(creds.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc


def require_roles(*roles: str):
    def checker(user: dict = Depends(current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user
    return checker


OPERATOR_ROLES = ("ADMIN", "LOGISTICS_OPERATOR")
require_operator = require_roles(*OPERATOR_ROLES)
require_admin = require_roles("ADMIN")
require_any = require_roles(*config.ROLES)


def can_report_vehicle(claims: dict, vehicle_id: str) -> bool:
    """DRIVER may only report its assigned vehicle(s); ADMIN may report any."""
    if claims.get("role") == "ADMIN":
        return True
    return claims.get("role") == "DRIVER" and vehicle_id in (claims.get("vehicle_ids") or [])


def simulator_claims(vehicle_ids: list[str]) -> dict:
    """Service-account claims the in-process GPS simulator uses (DRIVER permissions)."""
    return {"sub": SIMULATOR_SUBJECT, "role": "DRIVER", "vehicle_ids": list(vehicle_ids)}
