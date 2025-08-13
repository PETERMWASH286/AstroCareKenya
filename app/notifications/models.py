from app.extensions import db
from datetime import datetime

from app.extensions import db

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), default='info')
    icon = db.Column(db.String(30))
    action_url = db.Column(db.String(255))
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    expires_at = db.Column(db.DateTime)
    
    # Recipient types
    is_broadcast = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    
    # Use strings for relationships to avoid circular imports
    sender = db.relationship('User', foreign_keys=[sender_id], remote_side='User.id')
    department = db.relationship('Department')
    reads = db.relationship('NotificationRead', back_populates='notification')
    
    @property
    def time_ago(self):
        now = datetime.utcnow()
        diff = now - self.created_at
        
        if diff.days > 0:
            return f"{diff.days}d ago"
        elif diff.seconds > 3600:
            return f"{diff.seconds // 3600}h ago"
        elif diff.seconds > 60:
            return f"{diff.seconds // 60}m ago"
        else:
            return "Just now"
    def __repr__(self):
        return f'<Notification {self.title}>'

class NotificationRead(db.Model):
    __tablename__ = 'notification_reads'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    notification_id = db.Column(db.Integer, db.ForeignKey('notifications.id'), nullable=False)
    read_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    dismissed = db.Column(db.Boolean, default=False)
    
    # Use strings for relationships
    user = db.relationship('User', back_populates='read_notifications')
    notification = db.relationship('Notification', back_populates='reads')
    
    


# ---------------------------
# Message Template Model
# ---------------------------
class MessageTemplate(db.Model):
    __tablename__ = 'message_templates'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    content = db.Column(db.Text, nullable=False)
    template_type = db.Column(db.Enum('sms', 'email', name='template_types'), nullable=False)
    category = db.Column(db.Enum('employee', 'patient', name='template_categories'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    last_updated = db.Column(db.DateTime, default=db.func.current_timestamp(), 
                             onupdate=db.func.current_timestamp())
    variables = db.Column(db.JSON)  # Store available template variables
    icon = db.Column(db.String(30))  # Icon name for UI display
    priority = db.Column(db.Enum('normal', 'high', 'urgent', name='template_priorities'))
    
    # Relationships
    creator = db.relationship('User', backref='templates_created')
    
    def __repr__(self):
        return f'<MessageTemplate {self.name} ({self.category}/{self.template_type})>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'content': self.content,
            'template_type': self.template_type,
            'category': self.category,
            'variables': self.variables,
            'icon': self.icon,
            'priority': self.priority,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None
        }



# SMS Broadcast Model
class SMSBroadcast(db.Model):
    __tablename__ = 'sms_broadcasts'
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    recipient_type = db.Column(db.String(20), nullable=False)  # 'group' or 'individual'
    group_id = db.Column(db.String(50))  # Only if recipient_type is 'group'
    patient_ids = db.Column(db.JSON)  # Array of patient IDs if individual
    scheduled_time = db.Column(db.DateTime(timezone=True), nullable=True)
    status = db.Column(db.String(20), default='scheduled')  # scheduled, processing, completed, failed
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    sent_at = db.Column(db.DateTime)
    
    # Relationships
    creator = db.relationship('User', backref='sms_broadcasts')
    
    def __repr__(self):
        return f'<SMSBroadcast {self.id} ({self.status})>'

# Patient SMS Log Model
class PatientSMSLog(db.Model):
    __tablename__ = 'patient_sms_logs'
    id = db.Column(db.Integer, primary_key=True)
    broadcast_id = db.Column(db.Integer, db.ForeignKey('sms_broadcasts.id'), nullable=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='sent')  # sent, delivered, failed
    status_message = db.Column(db.String(255))  # Provider's status message
    cost = db.Column(db.Numeric(10, 2))  # Cost in KES
    provider_id = db.Column(db.String(100))  # Provider's message ID
    sent_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    delivered_at = db.Column(db.DateTime)
    
    # Relationships
    patient = db.relationship('Patient', backref='sms_logs')
    broadcast = db.relationship('SMSBroadcast', backref='logs')
    
    def __repr__(self):
        return f'<PatientSMSLog {self.id} to {self.phone_number}>'