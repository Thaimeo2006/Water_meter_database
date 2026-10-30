from fastapi import APIRouter, Header, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session
from ultis import get_db
from starlette.background import BackgroundTasks
from database import MeterRecord
from ultis import cleanup_temp_file
import tempfile
import zipfile
import os
import io
import csv

with open("password/token_for_ai_dev.txt", "r") as f:
    AI_TOKEN = f.read().strip()

router = APIRouter(
    prefix="/AI-dev",
    tags=["Return dataset for AI developer"]
)

@router.get("/export_record_data")
async def export_ai_dataset(
    background_tasks: BackgroundTasks,
    ai_token: str = Header(..., description="Unique token for AI developer"),
    db: Session = Depends(get_db)
):
    #Check token
    if ai_token != AI_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")

    #Manual records (ability 3) have no image, not for AI training
    records = db.query(MeterRecord).filter(or_(MeterRecord.ability != 3, MeterRecord.ability.is_(None))).all()
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