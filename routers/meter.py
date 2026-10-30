from fastapi import APIRouter, Depends, Query, HTTPException, Form
from database import Customer, Meter, MeterRecord
from sqlalchemy import func
from sqlalchemy.orm import Session
from ultis import check_user, get_db
from config import DEFAULT_LIMIT_NEARBY_METERS, DEFAULT_RADIUS_M, TIME_ZONE
from datetime import datetime, timezone, timedelta

router = APIRouter(
    prefix="/meter",
    tags=["Find nearby meters from user location"]
)

@router.get("/nearby")
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

@router.post("/new")
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
