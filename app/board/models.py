from datetime import datetime
from app.extensions import db

class StrategicInitiative(db.Model):
    __tablename__ = 'strategic_initiatives'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))  # e.g., 'Growth', 'Quality', 'Efficiency', 'Infrastructure'
    start_date = db.Column(db.Date)
    target_end_date = db.Column(db.Date)
    actual_end_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='not_started')  # not_started, in_progress, completed, on_hold
    priority = db.Column(db.String(20), default='medium')     # low, medium, high, critical
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    progress_percent = db.Column(db.Integer, default=0)        # 0-100
    budget_allocated = db.Column(db.Float, default=0.0)
    budget_spent = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = db.relationship('User', backref='owned_initiatives')
    milestones = db.relationship('InitiativeMilestone', backref='initiative', cascade='all, delete-orphan')
    key_results = db.relationship('KeyResult', backref='initiative', cascade='all, delete-orphan')


class InitiativeMilestone(db.Model):
    __tablename__ = 'initiative_milestones'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    initiative_id = db.Column(db.Integer, db.ForeignKey('strategic_initiatives.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    due_date = db.Column(db.Date)
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime)


class KeyResult(db.Model):
    __tablename__ = 'key_results'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    initiative_id = db.Column(db.Integer, db.ForeignKey('strategic_initiatives.id'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    target_value = db.Column(db.Float)
    current_value = db.Column(db.Float, default=0.0)
    unit = db.Column(db.String(20))  # e.g., '%', 'KES', 'patients'
    as_of_date = db.Column(db.Date, default=datetime.utcnow().date)
    
    


class BoardMeeting(db.Model):
    __tablename__ = 'board_meetings'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    meeting_date = db.Column(db.DateTime, nullable=False)
    agenda = db.Column(db.Text)
    minutes = db.Column(db.Text)
    minutes_document = db.Column(db.String(255))  # file path
    status = db.Column(db.String(20), default='scheduled')  # scheduled, held, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<BoardMeeting {self.title} {self.meeting_date}>'


class BoardDocument(db.Model):
    __tablename__ = 'board_documents'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    document_type = db.Column(db.String(50), nullable=False)  # policy, charter, bylaw, minutes, report
    description = db.Column(db.Text)
    file_path = db.Column(db.String(255))
    version = db.Column(db.String(20))
    effective_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    uploader = db.relationship('User', foreign_keys=[uploaded_by])

    def __repr__(self):
        return f'<BoardDocument {self.title} ({self.document_type})>'


class ComplianceItem(db.Model):
    __tablename__ = 'compliance_items'
    __audit_trail__ = True

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))  # regulatory, internal, statutory
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='pending')  # compliant, non-compliant, pending, overdue
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'))
    last_reviewed = db.Column(db.Date)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assignee = db.relationship('User', foreign_keys=[assigned_to])

    def __repr__(self):
        return f'<ComplianceItem {self.name}>'