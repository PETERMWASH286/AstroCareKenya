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