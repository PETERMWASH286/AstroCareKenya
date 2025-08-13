from app.user_management.models import Department
from app.extensions import db

departments = [
    "General Medicine", "Pediatrics", "Surgery", "Pharmacy",
    "Laboratory", "Radiology", "Human Resources", "Billing",
    "Doctor", "Clinical Officer", "Receptionist"
]

for name in departments:
    if not Department.query.filter_by(name=name).first():
        db.session.add(Department(name=name))

db.session.commit()
