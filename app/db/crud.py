from sqlalchemy.orm import Session
from sqlalchemy.ext.declarative import DeclarativeMeta

def replace_simple_list(db: Session, model: DeclarativeMeta, items: list[str]):
    try:
        db.query(model).delete()
        for item in items:
            new_record = model(name=item)
            db.add(new_record)
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
