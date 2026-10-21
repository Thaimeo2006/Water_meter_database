"""Main program, run the server, manage admin page, connect to mobile app"""

from database import SessionLocal, User, Customer, Meter, MeterRecord, engine
from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form, Query, Header, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import func
#from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload
from sqladmin import Admin
from sqladmin.authentication import AuthenticationBackend
from datetime import datetime, timezone, timedelta
from admin import UserAdmin, CustomerAdmin, MeterAdmin, MeterRecordAdmin
from password_store import pwd_context
from starlette.background import BackgroundTasks
from uuid import uuid4
from typing import Annotated
import pandas as pd
import tempfile
import os
import secrets
import zipfile
import csv
import io
import aiofiles
import jwt
import json
import time

with open("password/token_for_ai_dev.txt", "r") as f:
    AI_TOKEN = f.read().strip()

with open("password/jwt_secret_key.txt", "rb") as f:
    JWT_SECRET_KEY = f.read()

with open("password/admin_account.json", "r") as f:
    admin_account = json.load(f)
    admin_username, admin_password_hash = admin_account["username"], admin_account["password_hash"]

with open("config.json", "r") as f:
    config = json.load(f)
    JWT_ALGORITHM =config["jwt_algorithm"]
    USER_SESSION_TOKEN_EXPIRE_DAYS = config["user_session_token_expire_days"]
    ADMIN_SESSION_TOKEN_EXPIRE_DAYS = config["admin_session_token_expire_days"]
    TIME_ZONE = config["time_zone"]
    DEFAULT_RADIUS_M = config["default_radius_m"]
    DEFAULT_LIMIT_NEARBY_METERS = config["default_limit_nearby_meters"]

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

#Create "images" dir to save image
os.makedirs("./images", exist_ok=True)
#Create "coordinates" dir to save log file from AI model
os.makedirs("./coordinates", exist_ok=True)

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

security = HTTPBearer()

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
    if not time.tzinfo:
        time = time.replace(tzinfo=timezone(timedelta(hours=TIME_ZONE)))
        return time.astimezone(timezone.utc)

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

"""
@app.middleware("http")
async def log(request: Request, call_next):
    start_time = time.time()

    # ================= REQUEST =================
    request_body = await request.body()

    print("\n========== REQUEST ==========")
    print(f"{request.method} {request.url}")

    print("Headers:")
    print(dict(request.headers))

    print("Body:")
    print(request_body.decode("utf-8", errors="replace"))

    # ================= ENDPOINT =================
    response = await call_next(request)

    # ================= RESPONSE =================
    response_body = b""

    async for chunk in response.body_iterator:
        response_body += chunk

    process_time = time.time() - start_time

    print("\n========== RESPONSE ==========")
    print(f"Status: {response.status_code}")
    print(f"Time: {process_time:.4f}s")

    print("Headers:")
    print(dict(response.headers))

    print("Body:")
    print(response_body.decode("utf-8", errors="replace"))

    print("==============================\n")

    # Trả response lại cho client
    return Response(
        content=response_body,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
    )
"""

@app.post("/login")
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

@app.post("/logout")
async def logout_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    return {
        "message": "Logged out successfully! Delete session token on client side."
    }

@app.post("/check_and_save")
async def check_and_save(
    user_id: int = Depends(check_user),
    meter_id: str = Form(),
    image: UploadFile = File(),
    record_time: datetime = Form(),
    result: float = Form(),
    ability: int = Form(description="0/1/2 label for AI developer"),
    coordinates: UploadFile = File("Coordinates file for AI developer"),
    db: Session = Depends(get_db)
):
    #Get latest record of meter
    latest_record = (
        db.query(MeterRecord)
        .filter(MeterRecord.meter_id == meter_id)
        .order_by(MeterRecord.record_time.desc())
        .first()
    )

    #Check new record
    record_time = to_utc(record_time)
    if latest_record is not None:
        if result < latest_record.result:
            raise HTTPException(
                status_code= 400,
                detail= "The result result is less than the latest record result. Please try again"
            )
        #Maybe pyodbc return Naive Datetime
        db_time = latest_record.record_time
        if db_time.tzinfo is None:
           db_time = db_time.replace(tzinfo=timezone.utc)

        if record_time <= db_time:
            raise HTTPException(
                status_code= 400,
                detail= "Record time is older than the latest record time. Please try again."
            )

    # Save new record
    new_name = str(uuid4())

    image_relativepath = os.path.join("images", f"{new_name}.jpeg")
    coordinates_relativepath = os.path.join("coordinates", f"{new_name}.txt")

    try:
        async with aiofiles.open(image_relativepath, "wb") as buffer:
            while chunk := await image.read(1024 * 1024):
                await buffer.write(chunk)

        coordinates_data = await coordinates.read()
        async with aiofiles.open(coordinates_relativepath, "wb") as f:
            await f.write(coordinates_data)
    except Exception as e:
        if os.path.exists(image_relativepath):
            os.remove(image_relativepath)
        if os.path.exists(coordinates_relativepath):
            os.remove(coordinates_relativepath)

        raise HTTPException(
            status_code = 500,
            detail= f"Database error: {str(e)}"
        )

    try:
        new_record = MeterRecord(
            meter_id=meter_id,
            image_path=image_relativepath,
            record_time= record_time,
            result=result,
            ability= ability,
            coordinates_path= coordinates_relativepath,
            photographer_id= user_id
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)
        
    except Exception as e:
        db.rollback()
        if image_relativepath and os.path.exists(image_relativepath):
            os.remove(image_relativepath)
        if coordinates_relativepath and os.path.exists(coordinates_relativepath):
            os.remove(coordinates_relativepath)
        raise HTTPException(
            status_code=500,
            detail=f"Add to database failed. {str(e)}"
        )

    return {
        "message": "Record saved!"
    }

@app.get("/history")
async def serve_history_summary(
    customer_id: Annotated[list[str] | None, Query()] = None,
    user_id: str = Depends(check_user),
    all_customer: bool = Query(default=False),
    limit: int = Query(20,ge=1, description="Maximum return records"),
    offset: int = Query(0,ge=0),
    month: str | None = Query(default= None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    export_xlsx: bool = Query(default=False),
    db: Session = Depends(get_db)
):
    query = db.query(MeterRecord)
    if not all_customer:
        if not customer_id:
            raise HTTPException(
                status_code=400,
                detail="customer_id is required when all_customer is false."
            )
        query = query.join(MeterRecord.meter).filter(Meter.customer_id.in_(customer_id))

    if month:
        try:
            start_time = datetime.strptime(month, "%Y-%m")
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail="Bad month data format."
            )
        if start_time.month == 12:
            end_time = datetime(start_time.year + 1, 1, 1)
        else:
            end_time = datetime(
                start_time.year,
                start_time.month + 1,
                1
            )
        query = query.filter(
            MeterRecord.record_time >= start_time,
            MeterRecord.record_time <= end_time
        )

    else:
        if start_time:
            start_time = to_utc(start_time)
            query = query.filter(MeterRecord.record_time >= start_time)
        if end_time:
            end_time = to_utc(end_time)
            query = query.filter(MeterRecord.record_time < end_time)
    query = query.order_by(MeterRecord.record_time.desc())
    if not export_xlsx:
        try:
            records = query.limit(limit).offset(offset).all()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
        history_data = []
        for record in records:
            history_data.append({
                "id": record.id,
                "record_time": record.record_time,
                "result": record.result
            })

        return {
            "message": "Retrieved history successfully",
            "data": history_data
        }

    else:
        try:
            records = query.options(
                joinedload(MeterRecord.meter).joinedload(Meter.owner),
                joinedload(MeterRecord.photographer)
            ).all()
        except Exception as e:
                raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
        
        if not records:
            raise HTTPException(status_code=404, detail="No records found at this time.")
        excel_data = []
        for record in records:
            local_time = record.record_time.astimezone(timezone(timedelta(hours=TIME_ZONE)))
            excel_data.append({
                "Full name": record.meter.owner.name,
                "Identity number": record.meter.owner.identity_number,
                "Address": record.meter.owner.address,
                "Meter_location": record.meter.address,
                "Record time": local_time.strftime("%Y-%m-%d %H:%M:%S"),
                "Result": record.result,
                "Photographer": record.photographer.username
            })

        df = pd.DataFrame(excel_data)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='History records')

            worksheet = writer.sheets['History records']
            worksheet.column_dimensions['A'].width = 30
            worksheet.column_dimensions['B'].width = 15
            worksheet.column_dimensions['C'].width = 60
            worksheet.column_dimensions['D'].width = 60
            worksheet.column_dimensions['E'].width = 20
            worksheet.column_dimensions['F'].width = 12
            worksheet.column_dimensions['G'].width = 15

        buffer.seek(0)
        headers = {
            'Content-Disposition': f'attachment; filename="history_customer.xlsx"'
        }
        return StreamingResponse(
            buffer, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
            headers=headers
        )

"""
@app.get("/history/{record_id}")
def serve_history_detail(
    record_id: int,
    user_id: str = Depends(check_user),
    db: Session = Depends(get_db)
):
    try:
        record = db.query(MeterRecord).filter(MeterRecord.id == record_id).first()

        if record is None:
            raise HTTPException(status_code=404, detail="Record not found")
        
        return {
            "message": "Retrieved detail of record successfully!",
            "data": {
                "id": record.id,
                "record_time": record.record_time,
                "image_url": f"/image/{record.id}",
                "result": record.result,
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/image/{record_id}")
def serve_image(
    record_id: int,
    user_id: str = Depends(check_user),
    db: Session = Depends(get_db)
):
    try:
        record = db.query(MeterRecord).filter(MeterRecord.id == record_id).first()

        if record is None:
            raise HTTPException(status_code=404, detail="Record not found")

        image_path = record.image_path
        if not os.path.exists(image_path):
            raise HTTPException(status_code=404, detail="Image file missing on server")
        return FileResponse(path=image_path)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
"""

@app.get("/nearby_meters")
async def serve_nearby_meters(
    user_id: str = Depends(check_user),
    limit: int = Query(default= DEFAULT_LIMIT_NEARBY_METERS),
    radius: int = Query(default=DEFAULT_RADIUS_M, description="Limit distance of return meters (m)"),
    latitude: float = Query(...),
    longitude: float = Query(...),
    db: Session = Depends(get_db)
):
    #Collect recorded meter today
    today_start = datetime.now(timezone(timedelta(hours=TIME_ZONE))).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

    recorded_meter = (
        db.query(MeterRecord.meter_id)
        .filter(MeterRecord.record_time >= today_start)
    )
    
    #Spherical Law of Cosines Function (to M)
    lat_rad = func.radians(latitude)
    lon_rad = func.radians(longitude)

    db_lat_rad = func.radians(Meter.latitude)
    db_lon_rad = func.radians(Meter.longitude)
    
    distance_expr = 6371000.0 * func.acos(
        func.sin(lat_rad) * func.sin(db_lat_rad) +
        func.cos(lat_rad) * func.cos(db_lat_rad) * func.cos(db_lon_rad - lon_rad)
    )

    try:
        nearby_meters = (
            db.query(
                Meter.id.label("id"),
                Meter.address.label("address"),
                Meter.customer_id.label("customer_id"),
                Customer.name.label("customer_name"),               
                Customer.address.label("customer_address"),
                distance_expr.label("distance_m")
            )
            .join(Meter.owner)
            .filter(
                Meter.latitude.isnot(None),
                Meter.longitude.isnot(None),
                ~Meter.id.in_(recorded_meter),
                distance_expr <= radius
                )
            .order_by(distance_expr.asc())
            .limit(limit)
            .all()
        )

        result = []
        for meter in nearby_meters:
            result.append({
                "id": meter.id,
                "address": meter.address,
                "distance_m": int(round(meter.distance_m, 0)),
                "name": meter.customer_name,
                "identity_number": meter.customer_id,
                "customer_address": meter.customer_address,
            })

        return {
            "message": f"Retrieved nearby meters successfully! Limit: {limit}, Radius: {radius}",
            "data": result,
            "meta": {

            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.post("/new_meter")
async def make_new_meter(
    user_id: str = Depends(check_user),
    identity_number: str = Form(),
    address: str = Form(),
    latitude: float = Form(),
    longitude: float = Form(),
    force_add: bool = Form(False, description="Force add the customer while maybe it existed"),
    db: Session = Depends(get_db)
):
    #Check existed meter with the same owner
    if not force_add:
        #Distance function
        lat_rad = func.radians(latitude)
        lon_rad = func.radians(longitude)
        db_lat_rad = func.radians(Meter.latitude)
        db_lon_rad = func.radians(Meter.longitude)
        
        distance_expr = 6371000.0 * func.acos(
            func.sin(lat_rad) * func.sin(db_lat_rad) +
            func.cos(lat_rad) * func.cos(db_lat_rad) * func.cos(db_lon_rad - lon_rad)
        )

        check_exist_customer = (
            db.query(Customer)
            .filter(Customer.identity_number==identity_number)
            .all()
        )

        if not check_exist_customer:
            raise HTTPException(
                status_code=400,
                detail="Customer id is not existed!"
            )

        check_exist_meter = (
            db.query(Meter, distance_expr.label("distance_m"))
            .filter(Meter.customer_id == identity_number)
            .all()
        )
        
        if len(check_exist_meter) > 0:
            return_meter = []
            for row in check_exist_meter:
                meter, distance_m = row.Meter, row.distance_m
                distance_m = int(round(distance_m, 0))
                return_meter.append({
                    "id": meter.id,
                    "address": meter.address,
                    "distance": distance_m
                })
            return {
                "message": f"Another meter with the same owner already exists. Still save this new meter?",
                "exist_meter": return_meter
            }

    #Save to database
    try:
        new_meter = Meter(
            customer_id=identity_number,
            address=address,
            latitude=latitude,
            longitude=longitude
        )
        db.add(new_meter)
        db.commit()
        db.refresh(new_meter)
        
        return {
            "message": "Add new meter successfully!",
            "meter_id": new_meter.id
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
"""
@app.post("/new_customer_and_meter")
async def make_new_customer_and_meter(
    user_id: str = Depends(check_user),
    customer_name: str = Form(),
    identity_number: str = Form(),
    customer_address: str = Form(),
    address: str = Form(),
    latitude: float = Form(),
    longitude: float = Form(),
    #force_add: bool = Form(False, description="Force add the customer while maybe it existed"),
    db: Session = Depends(get_db)
):
    #Check existed meter with the same owner
    #Distance function
    lat_rad = func.radians(latitude)
    lon_rad = func.radians(longitude)
    db_lat_rad = func.radians(Meter.latitude)
    db_lon_rad = func.radians(Meter.longitude)
    
    distance_expr = 6371000.0 * func.acos(
        func.sin(lat_rad) * func.sin(db_lat_rad) +
        func.cos(lat_rad) * func.cos(db_lat_rad) * func.cos(db_lon_rad - lon_rad)
    )
    #Save to database
    try:
        new_customer = Customer(
            name=customer_name,
            identity_number=identity_number,
            address=customer_address
        )
        db.add(new_customer)
        db.commit()
        db.refresh(new_customer)
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    
    try:
        new_meter = Meter(
            customer_id=identity_number,
            address=address,
            latitude=latitude,
            longitude=longitude
        )
        db.add(new_meter)
        db.commit()
        db.refresh(new_meter)
        
        return {
            "message": "Add new customer successfully! Add new meter successfully!",
            "meter_id": new_meter.id
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
"""

@app.get("/export_record_data")
async def export_ai_dataset(
    background_tasks: BackgroundTasks,
    ai_token: str = Header(..., description="Unique token for AI developer"),
    db: Session = Depends(get_db)
):
    #Check token
    if ai_token != AI_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")

    records = db.query(MeterRecord).all()
    fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)

    try:
        with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            csv_buffer = io.StringIO()
            csv_writer = csv.writer(csv_buffer)
            csv_writer.writerow(["record_id", "image_filename", "coordinates_filename", "ability", "result"])

            for record in records:
                img_name = os.path.basename(record.image_path) if record.image_path else ""
                coord_name = os.path.basename(record.coordinates_path) if record.coordinates_path else ""

                if record.image_path and os.path.exists(record.image_path):
                    zip_file.write(record.image_path, arcname=f"images/{img_name}")

                if record.coordinates_path and os.path.exists(record.coordinates_path):
                    zip_file.write(record.coordinates_path, arcname=f"coordinates/{coord_name}")

                csv_writer.writerow([record.id, img_name, coord_name, record.ability, record.result])

            zip_file.writestr("dataset_labels.csv", csv_buffer.getvalue())

    except Exception as e:
        cleanup_temp_file(temp_zip_path)
        raise HTTPException(status_code=500, detail=f"Error in creating zip file: {str(e)}")

    background_tasks.add_task(cleanup_temp_file, temp_zip_path)
    
    return FileResponse(
        path=temp_zip_path, 
        filename="meter_dataset.zip", 
        media_type="application/zip"
    )