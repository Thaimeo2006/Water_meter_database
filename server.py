"""Main program, run the server, manage admin page, connect to mobile app"""

from routers import auth, record, history, meter, search, AI_dev
from routers.admin import AdminAuth
from ultis import *
from database import engine
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqladmin import Admin
from admin import UserAdmin, CustomerAdmin, MeterAdmin, MeterRecordAdmin
import os
import secrets

#Create "images" dir to save image
os.makedirs("./images", exist_ok=True)
#Create "coordinates" dir to save log file from AI model
os.makedirs("./coordinates", exist_ok=True)

app = FastAPI()
app.mount("/images", StaticFiles(directory="images"), name="images")
app.mount("/coordinates", StaticFiles(directory="coordinates"), name="coordinates")

#Admin page initialize
admin = Admin(app, engine, authentication_backend=AdminAuth(secret_key=secrets.token_hex(32)))

#Menu page for admin initialize
admin.add_view(UserAdmin)
admin.add_view(CustomerAdmin)
admin.add_view(MeterAdmin)
admin.add_view(MeterRecordAdmin)

app.include_router(auth.router)
app.include_router(record.router)
app.include_router(history.router)
app.include_router(meter.router)
app.include_router(search.router)
app.include_router(AI_dev.router)