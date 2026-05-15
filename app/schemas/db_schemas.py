from pydantic import BaseModel
from typing import List, Dict

class SimpleListUpdate(BaseModel):
    items: List[str]

class HierarchicalListUpdate(BaseModel):
    items: Dict[str, List[str]]
