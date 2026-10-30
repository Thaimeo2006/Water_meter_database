from sqladmin.authentication import AuthenticationBackend
from fastapi import Request
from ultis import create_session_token
from password_store import pwd_context
from config import JWT_ALGORITHM, JWT_SECRET_KEY
import json
import jwt

with open("password/admin_account.json", "r") as f:
    admin_account = json.load(f)
    admin_username, admin_password_hash = admin_account["username"], admin_account["password_hash"]

class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username = form.get("username")
        password = form.get("password")

        if username == admin_username and pwd_context.verify(password, admin_password_hash):
            admin_token = create_session_token(data={"sub": "admin"}, admin=True)
            request.session.update({"session_token": admin_token})
            return True            
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        token = request.session.get("session_token")
        if not token:
            return False
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            if payload.get("sub") == "admin":
                return True
            return False
            
        except jwt.ExpiredSignatureError:
            request.session.clear()
            return False
        except jwt.InvalidTokenError:
            return False