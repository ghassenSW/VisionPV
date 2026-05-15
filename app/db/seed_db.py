import os
import sys
import json

# Add project root to sys.path so we can import app modules directly
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, project_root)

# Override DATABASE_URL for seeding (inside container, use db service name)
if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql://myuser:mypassword@db:5432/visionpv"

from sqlalchemy.orm import Session
from app.db.database import engine
from app.db.models import (
    Base, InsuranceCompany, Governorate, Region,
    ClaimReason, DeathMedicalCause, HealthInstitution,
    NavGuardHq, PoliceHq, SocialState, VehicleType
)
from app.core import ftusa_names

def seed():
    # 1. Create all tables
    Base.metadata.create_all(bind=engine)
    
    with Session(engine) as db:
        # 2. Map models to their corresponding static lists
        simple_lists_to_seed = [
            (InsuranceCompany, ftusa_names.INSURANCE_LIST),
            (ClaimReason, ftusa_names.CLAIM_REASON_LIST),
            (DeathMedicalCause, ftusa_names.DEATH_MEDICAL_CAUSE_LIST),
            (HealthInstitution, ftusa_names.HEALTH_INSTITUTION_LIST),
            (NavGuardHq, ftusa_names.NAV_GUARD_HQ_LIST),
            (PoliceHq, ftusa_names.POLICE_HQ_LIST),
            (SocialState, ftusa_names.SOCIAL_STATE_LIST),
            (VehicleType, ftusa_names.VEHICLE_TYPE_LIST),
        ]
        
        # 3. Seed simple lists - add unique items and skip duplicates
        for model_class, static_list in simple_lists_to_seed:
            print(f"Processing {model_class.__tablename__} table...")
            
            # Get existing items
            existing_items = {item.name for item in db.query(model_class).all()}
            
            # Remove duplicates from the static list itself and add only new items
            seen = set()
            unique_new_items = []
            for item in static_list:
                if item not in existing_items and item not in seen:
                    seen.add(item)
                    unique_new_items.append(item)
            
            if unique_new_items:
                print(f"  Adding {len(unique_new_items)} new items to {model_class.__tablename__}")
                for item in unique_new_items:
                    db.add(model_class(name=item))
                db.commit()
            else:
                print(f"  All items already exist in {model_class.__tablename__}")
        
        # 4. Seed the hierarchical Governorate/Region map
        existing_govs = {gov.name for gov in db.query(Governorate).all()}
        if not existing_govs:  # Only seed if empty
            print("Seeding governorates and regions...")
            json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', 'regions_by_governorate.json')
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for gov_name, regions in data.items():
                        gov = Governorate(name=gov_name)
                        db.add(gov)
                        db.flush() # Get the auto-increment DB ID immediately
                        
                        for reg_name in regions:
                            reg = Region(name=reg_name, governorate_id=gov.id)
                            db.add(reg)
                db.commit()
            else:
                print(f"Warning: Could not find {json_path} for hierarchical seeding.")
        else:
            print(f"Governorates already seeded ({len(existing_govs)} found). Skipping hierarchical seeding.")
        
        print("Database seeding complete.")

if __name__ == "__main__":
    seed()
