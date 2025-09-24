from flask_wtf import FlaskForm
from wtforms import FloatField, StringField, IntegerField, SelectField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, NumberRange, Length

class RadiologyStockRequestForm(FlaskForm):
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