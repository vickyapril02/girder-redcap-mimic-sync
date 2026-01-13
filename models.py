from pydantic import BaseModel

class Patient(BaseModel):
    center_code: str
    patient_id: str
    age: int
    sex: str

