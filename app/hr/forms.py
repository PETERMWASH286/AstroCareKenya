from flask_wtf import FlaskForm
from wtforms import StringField, DateField, TextAreaField, SelectField
from wtforms.validators import DataRequired

class DisciplinaryActionForm(FlaskForm):
    action_type_id = SelectField('Action Type', coerce=int, validators=[DataRequired()])
    effective_date = DateField('Effective Date', format='%Y-%m-%d', validators=[DataRequired()])
    end_date = DateField('End Date', format='%Y-%m-%d')
    description = TextAreaField('Description', validators=[DataRequired()])
    outcome = TextAreaField('Expected Outcome')