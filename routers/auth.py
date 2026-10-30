from fastapi import APIRouter, Form, Depends, HTTPException
from ultis import get_db, security, create_session_token
from sqlalchemy.orm import Session
from database import User
from fastapi.security import HTTPAuthorizationCredentials
from password_store import pwd_context

router = APIRouter(
    prefix="/auth",
    tags=["Session management"]
)

@router.post("/login")
async def check_login(
    username: str = Form(),
    password: str = Form(),
    db: Session = Depends(get_db)
):
    if username=="":
        raise HTTPException(
            status_code= 400,
            detail= "Do not leave the username blank"
        )
    user_record = (
        db.query(User)
        .filter(User.username == username)
        .first()
    )
    if user_record is not None:
        if pwd_context.verify(password, user_record.password_hash):
            session_token = create_session_token(data={"sub": str(user_record.id)})
            return {
                "message": "Logged in successfully! Send it to server for any request.",
                "user_id": user_record.id,
                "session_token": session_token,
            }
    raise HTTPException(
        status_code= 400,
        detail= "Invalid username or password."
    )

@router.post("/logout")
async def logout_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    return {
        "message": "Logged out successfully! Delete session token on client side."
    }