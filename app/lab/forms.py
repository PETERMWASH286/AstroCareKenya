from flask_wtf import FlaskForm
from wtforms import FloatField, StringField, IntegerField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, NumberRange, Length

class LabStockRequestForm(FlaskForm):
    item_id = SelectField('Item', coerce=int, validators=[DataRequired()], choices=[])
    quantity = IntegerField('Quantity', validators=[
        DataRequired(), 
        NumberRange(min=1, message='Quantity must be at least 1')
    ])
    priority = SelectField('Priority', choices=[
        ('low', 'Low'), 
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical')
    ], validators=[DataRequired()])
    reason = TextAreaField('Reason', validators=[DataRequired()])
    
    
class LabConsumableForm(FlaskForm):
    name = StringField('Consumable Name', validators=[DataRequired(), Length(max=120)])
    description = TextAreaField('Description')
    sku = StringField('SKU', validators=[DataRequired(), Length(max=50)])
    category = SelectField('Category', choices=[
        ('reagent', 'Reagent'),
        ('disposable', 'Disposable'),
        ('chemical', 'Chemical'),
        ('media', 'Culture Media'),
        ('standard', 'Standard/Calibrator'),
        ('control', 'Quality Control')
    ], validators=[DataRequired()])
    unit_of_measure = SelectField('Unit of Measure', choices=[
        ('ml', 'Milliliters'),
        ('l', 'Liters'),
        ('mg', 'Milligrams'),
        ('g', 'Grams'),
        ('kg', 'Kilograms'),
        ('units', 'Units'),
        ('packs', 'Packs'),
        ('test', 'Tests')
    ], validators=[DataRequired()])
    storage_temp = SelectField('Storage Temperature', choices=[
        ('room_temp', 'Room Temperature'),
        ('2-8c', '2-8°C (Refrigerated)'),
        ('-20c', '-20°C (Frozen)'),
        ('-80c', '-80°C (Ultra Frozen)'),
        ('ambient', 'Ambient')
    ])
    hazard_class = SelectField('Hazard Class', choices=[
        ('none', 'None'),
        ('flammable', 'Flammable'),
        ('corrosive', 'Corrosive'),
        ('toxic', 'Toxic'),
        ('oxidizer', 'Oxidizer'),
        ('biohazard', 'Biohazard'),
        ('radioactive', 'Radioactive')
    ])
    shelf_life = IntegerField('Shelf Life (months)', validators=[NumberRange(min=1)])
    current_stock = FloatField('Current Stock', validators=[DataRequired(), NumberRange(min=0)])
    min_stock_level = FloatField('Minimum Stock Level', validators=[DataRequired(), NumberRange(min=0)])
    unit_cost = FloatField('Unit Cost', validators=[DataRequired(), NumberRange(min=0)])
    supplier_id = SelectField('Supplier', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Add Consumable')
    
    
    
    
    
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, FloatField, DateField, SelectField
from wtforms.validators import DataRequired, Optional, Length, NumberRange, ValidationError
from datetime import datetime, timedelta

class NewItemRequestForm(FlaskForm):
    # Item Information
    item_name = StringField('Item Name', validators=[
        DataRequired(message="Item name is required"),
        Length(min=2, max=200, message="Item name must be between 2 and 200 characters")
    ])
    
    category = SelectField('Category', choices=[
        ('', 'Select Category'),
        ('reagents', 'Reagents & Chemicals'),
        ('consumables', 'Lab Consumables'),
        ('glassware', 'Glassware'),
        ('equipment', 'Equipment & Instruments'),
        ('safety', 'Safety Equipment'),
        ('furniture', 'Lab Furniture'),
        ('electronics', 'Electronics'),
        ('pharmaceuticals', 'Pharmaceuticals'),
        ('diagnostics', 'Diagnostic Kits'),
        ('other', 'Other')
    ], validators=[DataRequired(message="Please select a category")])
    
    manufacturer = StringField('Manufacturer / Brand', validators=[
        Optional(),
        Length(max=100, message="Manufacturer name too long")
    ])
    
    specifications = TextAreaField('Item Specifications', validators=[
        Optional(),
        Length(max=500, message="Specifications too long")
    ])
    
    # Quantity & Requirements
    quantity = IntegerField('Quantity', validators=[
        DataRequired(message="Quantity is required"),
        NumberRange(min=1, max=100000, message="Quantity must be between 1 and 100,000")
    ])
    
    units = StringField('Units', validators=[
        DataRequired(message="Units are required"),
        Length(max=50, message="Unit description too long")
    ])
    
    estimated_price = FloatField('Estimated Unit Price', validators=[
        Optional(),
        NumberRange(min=0, message="Price cannot be negative")
    ])
    
    required_date = DateField('Required By Date', validators=[
        DataRequired(message="Required date is required")
    ])
    
    priority = SelectField('Priority Level', choices=[
        ('low', 'Low - Routine'),
        ('medium', 'Medium - Important'),
        ('high', 'High - Urgent'),
        ('critical', 'Critical - Emergency')
    ], validators=[DataRequired(message="Please select a priority level")])
    
    # Business Justification
    reason = TextAreaField('Reason for Request', validators=[
        DataRequired(message="Reason for request is required"),
        Length(min=10, max=1000, message="Reason must be between 10 and 1000 characters")
    ])
    
    alternatives = TextAreaField('Alternative Items', validators=[
        Optional(),
        Length(max=500, message="Alternative items description too long")
    ])
    
    urgency_reason = TextAreaField('Urgency Explanation', validators=[
        Optional(),
        Length(max=500, message="Urgency explanation too long")
    ])
    
    def validate_required_date(self, field):
        """Validate that required date is not in the past"""
        if field.data:
            if field.data < datetime.now().date():
                raise ValidationError("Required date cannot be in the past")
            
            # Optional: Add a maximum date (e.g., 1 year from now)
            max_date = datetime.now().date() + timedelta(days=365)
            if field.data > max_date:
                raise ValidationError("Required date cannot be more than 1 year from now")
    
    def validate_estimated_price(self, field):
        """Validate estimated price if provided"""
        if field.data is not None:
            if field.data < 0:
                raise ValidationError("Price cannot be negative")
            if field.data > 1000000:  # $1 million max
                raise ValidationError("Price seems too high. Please verify.")
    
    def validate_urgency_reason(self, field):
        """Validate urgency reason is provided for high/critical priorities"""
        if self.priority.data in ['high', 'critical']:
            if not field.data or not field.data.strip():
                raise ValidationError("Please provide an urgency explanation for high/critical priority requests")
            if len(field.data.strip()) < 10:
                raise ValidationError("Please provide a more detailed urgency explanation (at least 10 characters)")

# If you need the original LabStockRequestForm as well, here it is for reference:
class LabStockRequestForm(FlaskForm):
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
    ])