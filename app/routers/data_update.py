from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import (
    InsuranceCompany, Governorate, Region,
    ClaimReason, DeathMedicalCause, HealthInstitution,
    NavGuardHq, PoliceHq, SocialState, VehicleType
)
from app.schemas import SimpleListUpdate, HierarchicalListUpdate
from app.db.crud import replace_simple_list

router = APIRouter(prefix="/api", tags=["data-update"])


def _refresh_llm_reference_lists():
    from app.services.llm_gemini import refresh_reference_lists

    refresh_reference_lists()

@router.post("/regions/update")
def update_regions(data: HierarchicalListUpdate, db: Session = Depends(get_db)):
    try:
        # Start a transaction (already started implicitly by Session)
        for gov_name, regions in data.items.items():
            # Check if Governorate exists 
            gov = db.query(Governorate).filter(Governorate.name == gov_name).first()
            if not gov:
                gov = Governorate(name=gov_name)
                db.add(gov)
                db.flush()
            else:
                # DELETE ONLY the Regions belonging to that specific Governorate
                db.query(Region).filter(Region.governorate_id == gov.id).delete()
            
            # Bulk INSERT the new list of Regions for that Governorate
            for reg_name in regions:
                new_reg = Region(name=reg_name, governorate_id=gov.id)
                db.add(new_reg)
                
        db.commit()
        _refresh_llm_reference_lists()
        return {"message": "Hierarchical Regions data updated successfully."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/insurance-company/update")
def update_insurance_companies(data: SimpleListUpdate, db: Session = Depends(get_db)):
    try:
        replace_simple_list(db, InsuranceCompany, data.items)
        _refresh_llm_reference_lists()
        return {"message": "Insurance companies updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/claim-reason/update")
def update_claim_reasons(data: SimpleListUpdate, db: Session = Depends(get_db)):
    try:
        replace_simple_list(db, ClaimReason, data.items)
        _refresh_llm_reference_lists()
        return {"message": "Claim reasons updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/death-medical-cause/update")
def update_death_medical_causes(data: SimpleListUpdate, db: Session = Depends(get_db)):
    try:
        replace_simple_list(db, DeathMedicalCause, data.items)
        _refresh_llm_reference_lists()
        return {"message": "Death medical causes updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/health-institution/update")
def update_health_institutions(data: SimpleListUpdate, db: Session = Depends(get_db)):
    try:
        replace_simple_list(db, HealthInstitution, data.items)
        _refresh_llm_reference_lists()
        return {"message": "Health institutions updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/nav-guard-hq/update")
def update_nav_guard_hqs(data: SimpleListUpdate, db: Session = Depends(get_db)):
    try:
        replace_simple_list(db, NavGuardHq, data.items)
        _refresh_llm_reference_lists()
        return {"message": "Nav guard HQs updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/police-hq/update")
def update_police_hqs(data: SimpleListUpdate, db: Session = Depends(get_db)):
    try:
        replace_simple_list(db, PoliceHq, data.items)
        _refresh_llm_reference_lists()
        return {"message": "Police HQs updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/social-state/update")
def update_social_states(data: SimpleListUpdate, db: Session = Depends(get_db)):
    try:
        replace_simple_list(db, SocialState, data.items)
        _refresh_llm_reference_lists()
        return {"message": "Social states updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/vehicle-type/update")
def update_vehicle_types(data: SimpleListUpdate, db: Session = Depends(get_db)):
    try:
        replace_simple_list(db, VehicleType, data.items)
        _refresh_llm_reference_lists()
        return {"message": "Vehicle types updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
