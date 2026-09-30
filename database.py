"""Declare tables structure in sql database"""

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from urllib.parse import quote_plus
import secrets


with open("password/database_url.txt", "r") as f:
    DATABASE_URL = f.read().strip()

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True, default=lambda: secrets.token_hex(32))
    username = Column(String(32), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    records_taken = relationship("MeterRecord", back_populates="photographer")

class Customer(Base):
    __tablename__ = "customers"

    name = Column(String(40))
    identity_number = Column(String(12), primary_key=True, nullable=False)
    address = Column(String(120), nullable=False)

    meters = relationship(
        "Meter", 
        back_populates="owner",
    )

class Meter(Base):
    __tablename__ = "meters"

    id = Column(String(64), primary_key=True, default=lambda: secrets.token_hex(32))
    customer_id = Column(String(12), ForeignKey("customers.identity_number"))
    address = Column(String(120), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    last_paid_record_id = Column(
        Integer, 
        ForeignKey("meter_records.id", use_alter=True, name="fk_last_paid"), 
        nullable=True
    )

    owner = relationship(
        "Customer",
        back_populates="meters"
    )

    records = relationship(
        "MeterRecord",
        back_populates="meter",
        foreign_keys="[MeterRecord.meter_id]"
    )

    last_paid_record = relationship(
        "MeterRecord", 
        foreign_keys=[last_paid_record_id],
        post_update=True # Must have to except error loops
    )

class MeterRecord(Base):
    __tablename__ = "meter_records"

    id = Column(Integer, primary_key=True)
    meter_id = Column(String(64), ForeignKey("meters.id"))
    image_path = Column(String(256), nullable=False)
    record_time = Column(DateTime(timezone= True), server_default=func.sysdatetimeoffset(), nullable= False)
    result = Column(Float, nullable= False)
    ability = Column(Integer)
    coordinates_path = Column(String(256))
    photographer_id = Column(String(64), ForeignKey("users.id"), nullable=False)

    meter = relationship("Meter", back_populates="records", foreign_keys=[meter_id])
    photographer = relationship("User", back_populates="records_taken")

Base.metadata.create_all(bind=engine)