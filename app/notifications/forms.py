from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, BooleanField
from wtforms.validators import DataRequired, Length, Optional
from wtforms.widgets import TextArea

class TemplateForm(FlaskForm):
    name = StringField('Template Name', validators=[
        DataRequired(message="Template name is required"),
        Length(min=3, max=120, message="Name must be between 3-120 characters")
    ], render_kw={"placeholder": "e.g., Appointment Reminder"})
    
    content = TextAreaField('Content', validators=[
        DataRequired(message="Content is required"),
        Length(min=10, message="Content is too short")
    ], widget=TextArea(), render_kw={"rows": 6})
    
    template_type = SelectField('Message Type', choices=[
        ('sms', 'SMS'),
        ('email', 'Email')
    ], validators=[DataRequired()], default='sms')
    
    category = SelectField('Recipient Type', choices=[
        ('employee', 'Staff/Employee'),
        ('patient', 'Patient')
    ], validators=[DataRequired()], default='patient')
    
    priority = SelectField('Priority Level', choices=[
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent')
    ], default='normal')
    
    icon = SelectField('Icon', choices=[
        ('', 'Select an icon'),
        ('fa-envelope', 'Envelope'),
        ('fa-comment', 'Comment'),
        ('fa-calendar', 'Calendar'),
        ('fa-bell', 'Bell'),
        ('fa-user-md', 'Doctor'),
        ('fa-stethoscope', 'Stethoscope'),
        ('fa-heartbeat', 'Heartbeat'),
        ('fa-pills', 'Pills'),
        ('fa-file-invoice', 'Invoice'),
        ('fa-credit-card', 'Credit Card'),
        ('fa-clock', 'Clock'),
        ('fa-map-marker', 'Map Marker'),
        ('fa-ambulance', 'Ambulance'),
        ('fa-hospital', 'Hospital'),
        ('fa-syringe', 'Syringe'),
        ('fa-heart', 'Heart'),
        ('fa-exclamation-triangle', 'Warning')
    ], validators=[Optional()])
    
    variables = StringField('Available Variables (comma separated)', 
        validators=[Optional()],
        render_kw={"placeholder": "e.g., name, date, time, doctor"})
    
    is_active = BooleanField('Active Template', default=True)
    
    def validate_variables(self, field):
        """Clean up variables input"""
        if field.data:
            # Remove any non-alphanumeric characters except commas and underscores
            cleaned = ''.join(c for c in field.data if c.isalnum() or c in [',', '_', ' '])
            # Remove extra spaces
            cleaned = ','.join([v.strip() for v in cleaned.split(',') if v.strip()])
            field.data = cleaned