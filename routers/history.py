from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from database import Meter, MeterRecord
from sqlalchemy.orm import Session, joinedload
from ultis import check_user, get_db, to_utc
from datetime import datetime, timezone, timedelta
from typing import Annotated
from config import TIME_ZONE
import pandas as pd
import io

router = APIRouter(
    prefix="/history",
    tags=["Check history"]
)

@router.get("/")
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