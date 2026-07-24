from datetime import datetime
from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, FloatField, IntegerField, StringField, TextAreaField, SelectField, HiddenField, DateTimeField
from wtforms.validators import DataRequired, Length, NumberRange, Optional
from app.auth.models import User, Role
from app.inpatient.models import Ward, Bed


def optional_int(value):
    """Safely coerce to int or None, handling strings, ints, and empty values."""
    if value is None or value == '':
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


class AdmissionForm(FlaskForm):
    # Patient selection
    patient_search = StringField('Search Patient', validators=[Optional()],
                                 render_kw={"placeholder": "Type name or reg no..."})
    patient_id = HiddenField('Patient ID', validators=[DataRequired()])

    # Admission details
    ward_id = SelectField('Ward', coerce=int, validators=[DataRequired()])          # required → int
    bed_id = SelectField('Bed', coerce=optional_int, validators=[Optional()])      # optional → None or int
    diagnosis = TextAreaField('Diagnosis', validators=[DataRequired()])
    admission_date = DateTimeField('Admission Date & Time', format='%Y-%m-%dT%H:%M',
                                   default=datetime.utcnow, validators=[Optional()])

    # Staff
    admitting_doctor_id = SelectField('Admitting Doctor', coerce=int, validators=[DataRequired()])  # required
    nurse_id = SelectField('Assigned Nurse', coerce=optional_int, validators=[Optional()])         # optional

    def __init__(self, *args, **kwargs):
        super(AdmissionForm, self).__init__(*args, **kwargs)

        # Ward choices
        self.ward_id.choices = [(w.id, w.name) for w in Ward.query.order_by(Ward.name).all()]

        # Bed choices (initially empty; will be populated via JavaScript)
        self.bed_id.choices = [('', 'Select ward first')]

        # Doctors (role = 'doctor')
        doctors = User.query.join(User.roles).filter(Role.name == 'doctor').order_by(User.full_name).all()
        self.admitting_doctor_id.choices = [(d.id, d.full_name) for d in doctors]

        # Nurses (role = 'nurse') – first choice is empty
        nurses = User.query.join(User.roles).filter(Role.name == 'nurse').order_by(User.full_name).all()
        self.nurse_id.choices = [('', 'Select nurse (optional)')] + [(n.id, n.full_name) for n in nurses]
        
        
        
        

# If you need the original LabStockRequestForm as well, here it is for reference:
class InpatientStockRequestForm(FlaskForm):
    item_id = SelectField('Laboratory Item', validators=[DataRequired()])
    quantity = IntegerField('Quantity Needed', validators=[
        DataRequired(),
        NumberRange(min=1, message="Quantity must be at least 1")
    ])
    priority = SelectField('Priority Level', choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical')
    ], validators=[DataRequired()])
    reason = TextAreaField('Reason for Request', validators=[
        DataRequired(),
        Length(min=10, max=500)
        
    ]),
    substore_id = SelectField('Substore', coerce=int, validators=[DataRequired()])  # ✅ Required



class InventoryItemForm(FlaskForm):
    substore_id = SelectField('Substore', coerce=int, validators=[DataRequired()])
    item_name = StringField('Item Name', validators=[DataRequired()])
    category = StringField('Category', validators=[DataRequired()])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=0)])
    unit = StringField('Unit', default='piece')
    buying_price = FloatField('Buying Price', validators=[DataRequired(), NumberRange(min=0)])
    selling_price = FloatField('Selling Price', validators=[Optional()])
    reorder_level = IntegerField('Reorder Level', default=5)
    low_stock_threshold = IntegerField('Low Stock Threshold', default=5)
    batch_number = StringField('Batch Number')
    expiry_date = DateField('Expiry Date', format='%Y-%m-%d', validators=[Optional()])
    supplier = StringField('Supplier')
    location = StringField('Location')
    storage_conditions = StringField('Storage Conditions')
    service_id = IntegerField('Service ID', validators=[Optional()])
    
    
    
# app/inpatient/forms.py

class GeneralSettingsForm(FlaskForm):
    default_admission_fee = FloatField('Default Admission Fee', validators=[Optional()], default=0.0)
    default_nursing_fee = FloatField('Default Nursing Fee (per day)', validators=[Optional()], default=0.0)
    default_admin_fee = FloatField('Administrative Fee', validators=[Optional()], default=0.0)
    max_stay_days = IntegerField('Max Stay Days (before review)', validators=[Optional()], default=7)
    default_discharge_fee = FloatField('Discharge Fee', validators=[Optional()], default=0.0)
    default_consultation_fee = FloatField('Consultation Fee', validators=[Optional()], default=0.0)
    auto_generate_invoice_on_discharge = BooleanField('Auto-generate Invoice on Discharge', default=True)


class WardBedFeeForm(FlaskForm):
    ward_id = SelectField('Ward', coerce=int, validators=[DataRequired()])
    admission_fee = FloatField('Admission Fee (one-time)', validators=[DataRequired(), NumberRange(min=0)])
    daily_bed_fee = FloatField('Daily Bed Fee (per night)', validators=[DataRequired(), NumberRange(min=0)])
    deposit_required = FloatField('Deposit Required', validators=[Optional(), NumberRange(min=0)])


class SettingForm(FlaskForm):
    key = StringField('Setting Key', validators=[DataRequired()])
    value = StringField('Value', validators=[DataRequired()])
    description = TextAreaField('Description')
    category = SelectField('Category', choices=[
        ('general', 'General'),
        ('fees', 'Fees'),
        ('ward', 'Ward Specific')
    ])