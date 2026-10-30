from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from datetime import datetime, timezone, timedelta
from database import SessionLocal
from config import JWT_SECRET_KEY, JWT_ALGORITHM, TIME_ZONE, ADMIN_SESSION_TOKEN_EXPIRE_DAYS, USER_SESSION_TOKEN_EXPIRE_DAYS
import jwt
import os

security = HTTPBearer()

#Generate jwt token function
def create_session_token(data: dict, admin: bool = False):
    if admin:
        expire_days = ADMIN_SESSION_TOKEN_EXPIRE_DAYS
    expire_days = USER_SESSION_TOKEN_EXPIRE_DAYS
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=expire_days)
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def check_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])        
        user_id = payload.get("sub")

        if user_id is None:
            raise HTTPException(status_code=401, detail="Token payload invalid.")            
        return user_id
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Please login again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session token.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def cleanup_temp_file(path: str):
    if os.path.exists(path):
        os.remove(path)

def to_utc(time: datetime):
    if time.tzinfo is None or time.utcoffset() is None:
        time = time.replace(tzinfo=timezone(timedelta(hours=TIME_ZONE)))
    return time.astimezone(timezone.utc)
