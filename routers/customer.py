from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import or_, and_, case
from sqlalchemy.orm import Session
from database import Customer
from ultis import check_user, get_db

router = APIRouter(
    prefix="/customer",
    tags=["API for customer"]
)

@router.get("/search")
async def search_customers(
    user_id: str = Depends(check_user),
    keyword: str = Query(..., min_length=1, max_length=40, description="Customer name or identity number"),
    limit: int = Query(default= 10, ge=1, le=20, description="Maximum return customers"),
    db: Session = Depends(get_db)
):
    #Clean keyword: remove spaces at both ends and duplicate spaces between words
    keyword = " ".join(keyword.split())
    if keyword == "":
        raise HTTPException(
            status_code= 400,
            detail= "Do not leave the keyword blank"
        )

    #Escape special characters of LIKE, so they are searched as normal characters
    escaped_keyword = keyword.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")
    words = escaped_keyword.split(" ")

    #Compare name without case and accents ("duc" matches "Đức")
    customer_name = Customer.name.collate("Latin1_General_100_CI_AI")

    #Relevance of each customer (smaller is more relevant)
    relevance_expr = case(
        (Customer.identity_number == keyword, 0),                      #Same identity number
        (Customer.identity_number.like(f"{escaped_keyword}%"), 1),     #Identity number starts with keyword
        (customer_name.like(f"{escaped_keyword}%"), 2),                #Name starts with keyword
        (customer_name.like(f"% {escaped_keyword}%"), 3),              #A word in name starts with keyword
        (customer_name.like(f"%{escaped_keyword}%"), 4),               #Name contains keyword
        (Customer.identity_number.like(f"%{escaped_keyword}%"), 6),    #Identity number contains keyword
        else_=5                                                        #Name contains all words of keyword
    )

    try:
        customers = (
            db.query(
                Customer.identity_number.label("identity_number"),
                Customer.name.label("name"),
                Customer.address.label("address")
            )
            .filter(
                or_(
                    Customer.identity_number.like(f"%{escaped_keyword}%"),
                    and_(*[customer_name.like(f"%{word}%") for word in words])
                )
            )
            .order_by(relevance_expr.asc(), Customer.name.asc())
            .limit(limit)
            .all()
        )

        result = []
        for customer in customers:
            result.append({
                "identity_number": customer.identity_number,
                "name": customer.name,
                "address": customer.address,
            })

        return {
            "message": f"Retrieved customers successfully! Limit: {limit}",
            "data": result,
            "meta": {

            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")