from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Date, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot/models/ride_bot.db")

Base = declarative_base()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class User(Base):
    """טבלת משתמשים - כולל ניהול מסמכים ותוקף לנהגים"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    full_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    role = Column(String, default="client")  # client / driver
    current_mode = Column(String, default="client")
    driver_type = Column(String, nullable=True)  # taxi / delivery / both
    
    # סטטוסים של נהג
    is_verified = Column(Boolean, default=False)  # האם המנהל אישר אותו
    is_active = Column(Boolean, default=True)    # האם החשבון פעיל (חוסמים אם פג תוקף מסמך)
    is_available = Column(Boolean, default=True)  # האם הנהג מחובר כרגע
    work_regions = Column(String, nullable=True)

    # מסמכים (שומרים את ה-File ID של טלגרם)
    driver_license_file_id = Column(String, nullable=True)
    id_card_file_id = Column(String, nullable=True)
    taxi_permit_file_id = Column(String, nullable=True)
    
    # תאריכי תפוגה (מסוג Date)
    license_expiry = Column(Date, nullable=True)
    insurance_expiry = Column(Date, nullable=True)
    
    # ניטור התראות
    last_expiry_notification = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, nullable=True)
    type = Column(String)  # ride / delivery
    status = Column(String, default="open")
    pickup_loc = Column(String)
    dropoff_loc = Column(String)
    weight = Column(String, nullable=True)
    pickup_time = Column(String, nullable=True)
    deadline = Column(String, nullable=True)
    price = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    bids = relationship("Bid", back_populates
    ="job", cascade="all, delete-orphan")
    
    region = Column(String, nullable=True) # האזור שבו העבודה מתבצעת (מרכז/דרום/וכו')

class Bid(Base):
    __tablename__ = "bids"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    driver_id = Column(Integer)
    driver_name = Column(String)
    price = Column(String)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    job = relationship("Job", back_populates="bids")

def init_db():
    Base.metadata.create_all(bind=engine)
    print("✅ Database updated with document management fields.")
