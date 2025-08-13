from datetime import datetime
from app.extensions import db
from app.patients.models import Patient
from flask_login import current_user

class Clinic(db.Model):
    """
    A simple lookup table for hospital clinics/departments where appointments can be booked.
    """
    __tablename__ = 'clinics'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    def __repr__(self):
        return f"<Clinic {self.id} {self.name}>"


class Appointment(db.Model):
    """
    Represents an appointment for a patient at a given clinic, assigned to a doctor,
    at a specified date/time, with a reason and status.
    """
    __tablename__ = 'appointments'

    id = db.Column(db.Integer, primary_key=True)

    # Foreign keys
    patient_id = db.Column(
        db.Integer,
        db.ForeignKey('patients.id'),
        nullable=False
    )
    clinic_id  = db.Column(
        db.Integer,
        db.ForeignKey('clinics.id'),
        nullable=False
    )
    doctor_id  = db.Column(
        db.Integer,
        db.ForeignKey('user.id'),  # assumes your User model’s table name is "user"
        nullable=False
    )

    # Scheduled Date & Time
    scheduled_for = db.Column(db.DateTime, nullable=False)

    # Short reason / note
    reason = db.Column(db.Text, nullable=False)

    # Who created/booked it (user ID)
    created_by = db.Column(db.Integer, nullable=False)

    # Appointment status: scheduled, completed, cancelled, no_show, etc.
    status = db.Column(db.String(20), default='scheduled', nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    patient = db.relationship(
        'Patient',
        backref=db.backref('appointments', lazy=True)
    )
    clinic  = db.relationship(
        'Clinic',
        backref=db.backref('appointments', lazy=True)
    )
    doctor  = db.relationship(
        'User',
        backref=db.backref('assigned_appointments', lazy=True),
        foreign_keys=[doctor_id]
    )

    def __repr__(self):
        return (
            f"<Appointment {self.id} "
            f"Patient:{self.patient_id} Clinic:{self.clinic_id} "
            f"Doctor:{self.doctor_id} • {self.scheduled_for}>"
        )

    def mark_cancelled(self):
        self.status = 'cancelled'
        self.updated_at = datetime.utcnow()
        db.session.add(self)
        db.session.commit()

    def mark_completed(self):
        self.status = 'completed'
        self.updated_at = datetime.utcnow()
        db.session.add(self)
        db.session.commit()
