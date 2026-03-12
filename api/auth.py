"""JWT 认证与密码哈希"""
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyCookie

from .config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

# 使用 pbkdf2_sha256，避免 bcrypt 在某些环境下的兼容问题和 72 字节长度限制
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
security = HTTPBearer(auto_error=False)
cookie_scheme = APIKeyCookie(name="token", auto_error=False)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    token_cookie: Optional[str] = Depends(cookie_scheme),
) -> int:
    token = None
    if credentials:
        token = credentials.credentials
    elif token_cookie:
        token = token_cookie

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或 token 已过期",
        )
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="token 无效")
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="token 无效")
    return int(uid)
