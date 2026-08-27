from pydantic import BaseModel
from typing import Optional

class InvoiceData(BaseModel):
    doc_type: str = "invoice"
    exporter: str
    product: str
    quantity: float
    value: float
    invoice_number: str

class PackingListData(BaseModel):
    doc_type: str = "packing_list"
    exporter: str
    product: str
    quantity: float
    packages: int
    packing_list_number: str

class Verdict(BaseModel):
    case_id: str
    verdict: str
    reason: str
    rule_applied: str
    rule_satisfied: bool

class Case(BaseModel):
    case_id: str
    invoice: Optional[InvoiceData] = None
    packing_list: Optional[PackingListData] = None
    verdict: Optional[Verdict] = None
