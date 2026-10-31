from fastapi import APIRouter, Depends, Form, File, UploadFile, HTTPException
from database import MeterRecord
from sqlalchemy.orm import Session
from ultis import check_user, get_db, to_utc
from datetime import datetime, timezone
from uuid import uuid4
import aiofiles
import os

router = APIRouter(
    prefix="/meter-record",
    tags=["Record management"]
)

@router.post("/check_and_save")
async def check_and_save(
    user_id: str = Depends(check_user),
    meter_id: str = Form(),
    image: UploadFile | None = File(None),
    record_time: datetime = Form(),
    result: float = Form(),
    ability: int = Form(description="0/1/2 label for AI developer, 3 for manual record without image"),
    coordinates: UploadFile = File("Coordinates file for AI developer"),
    db: Session = Depends(get_db)
):
    #Only manual record (ability 3) can be saved without image
    if image is None and ability != 3:
        raise HTTPException(
            status_code= 422,
            detail= "Image is required."
        )

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

        if record_time.date() == db_time.date():
            raise HTTPException(
                status_code=400,
                detail="Meter has already recorded today."
            )

    # Save new record
    new_name = str(uuid4())

    image_relativepath = os.path.join("images", f"{new_name}.jpeg") if image is not None else None
    coordinates_relativepath = os.path.join("coordinates", f"{new_name}.txt")

    try:
        if image is not None:
            async with aiofiles.open(image_relativepath, "wb") as buffer:
                while chunk := await image.read(1024 * 1024):
                    await buffer.write(chunk)

        coordinates_data = await coordinates.read()
        async with aiofiles.open(coordinates_relativepath, "wb") as f:
            await f.write(coordinates_data)
    except Exception as e:
        if image_relativepath and os.path.exists(image_relativepath):
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
        "message": "Record saved!",
        "record_id": new_record.id
    }

@router.put("/{record_id}")
async def update_record(
    record_id: int,
    new_result: float,
    user_id = Depends(check_user),
    db: Session = Depends(get_db)
):
    record = db.query(MeterRecord).filter(MeterRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found.")
    
    # Deny edit while another latest record
    latest_record = db.query(MeterRecord).filter(MeterRecord.meter_id == record.meter_id).order_by(MeterRecord.record_time.desc()).first()
    if latest_record.id != record_id:
        raise HTTPException(status_code=400, detail="Only commit the latest record!")

    if record.photographer_id != user_id:
        raise HTTPException(
            status_code=403, 
            detail="Cannot edit the record which create by another user."
        )
        
    record.result = new_result
    db.commit()
    return {
        "message": "Updated!"
    }

@router.delete("/{record_id}")
async def delete_record(
    record_id: int,
    user_id = Depends(check_user),
    db: Session = Depends(get_db)
):
    record = db.query(MeterRecord).filter(MeterRecord.id == record_id).first()
    if not record:
        raise HTTPException(
            status_code=404,
            detail="Record not found."
        )
        
    latest_record = db.query(MeterRecord).filter(MeterRecord.meter_id == record.meter_id).order_by(MeterRecord.record_time.desc()).first()
    if latest_record.id != record_id:
        raise HTTPException(
            status_code=400,
            detail="Only delete the latest record."
        )

    if record.photographer_id != user_id:
        raise HTTPException(
            status_code=403, 
            detail="Cannot delete the record which create by another user."
        )
        
    db.delete(record)
    db.commit()
    return {
        "message": "Deleted!"
    }