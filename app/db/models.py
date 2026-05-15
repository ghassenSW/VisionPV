from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Governorate(Base):
    __tablename__ = "governorates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    regions = relationship("Region", back_populates="governorate", cascade="all, delete-orphan")

class Region(Base):
    __tablename__ = "regions"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    governorate_id = Column(Integer, ForeignKey("governorates.id", ondelete="CASCADE"), nullable=False)
    governorate = relationship("Governorate", back_populates="regions")

class InsuranceCompany(Base):
    __tablename__ = "insurance_companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)

class ClaimReason(Base):
    __tablename__ = "claim_reasons"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)

class DeathMedicalCause(Base):
    __tablename__ = "death_medical_causes"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)

class HealthInstitution(Base):
    __tablename__ = "health_institutions"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)

class NavGuardHq(Base):
    __tablename__ = "nav_guard_hqs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)

class PoliceHq(Base):
    __tablename__ = "police_hqs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)

class SocialState(Base):
    __tablename__ = "social_states"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)

class VehicleType(Base):
    __tablename__ = "vehicle_types"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
