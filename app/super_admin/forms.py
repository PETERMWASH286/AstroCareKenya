# app/super_admin/forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length, ValidationError
from .models import Hospital
from wtforms.validators import Regexp

class HospitalForm(FlaskForm):
    """
    Form for creating and editing Hospital (tenant) records.
    Validates uniqueness of name and subdomain.
    """
    name = StringField(
        'Hospital Name',
        validators=[DataRequired(message="Name is required"), Length(max=128)]
    )
    subdomain = StringField(
        'Subdomain',
        validators=[
            DataRequired(),
            Length(max=64),
            Regexp(r'^[a-z0-9\-]+$',
                   message='Subdomain may only contain lowercase letters, numbers, and hyphens.')
        ]
    )
    db_uri = StringField(
        'Database URI',
        description="SQLAlchemy URI (e.g. mysql+pymysql://user:pass@host:port/dbname)",
        validators=[DataRequired(message="Database URI is required"), Length(max=255)]
    )
    submit = SubmitField('Save')

    def __init__(self, obj=None, *args, **kwargs):
        """
        Accept an existing obj when editing to skip uniqueness on itself.
        """
        super().__init__(*args, **kwargs)
        self.obj = obj

    def validate_name(self, field):
        # Ensure hospital name is unique (except for the current record)
        query = Hospital.query.filter_by(name=field.data.strip())
        if self.obj:
            query = query.filter(Hospital.id != self.obj.id)
        if query.first():
            raise ValidationError('A hospital with that name already exists.')

    def validate_subdomain(self, field):
        # Ensure subdomain is unique (except for the current record)
        query = Hospital.query.filter_by(subdomain=field.data.strip().lower())
        if self.obj:
            query = query.filter(Hospital.id != self.obj.id)
        if query.first():
            raise ValidationError('That subdomain is already taken.')
