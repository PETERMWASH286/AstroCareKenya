from datetime import datetime
from flask_wtf import FlaskForm
from wtforms import EmailField, StringField, DateField, TextAreaField, SelectField, DecimalField, IntegerField, BooleanField, SubmitField, URLField, FileField
from wtforms.validators import DataRequired, Length, Optional, Email, NumberRange, URL
from flask_wtf.file import FileField, FileAllowed

class DisciplinaryActionForm(FlaskForm):
    action_type_id = SelectField('Action Type', coerce=int, validators=[DataRequired()])
    effective_date = DateField('Effective Date', format='%Y-%m-%d', validators=[DataRequired()])
    end_date = DateField('End Date', format='%Y-%m-%d')
    description = TextAreaField('Description', validators=[DataRequired()])
    outcome = TextAreaField('Expected Outcome')
    
    
    
# Recruitment Forms
class JobPostingForm(FlaskForm):
    title = StringField('Job Title', validators=[DataRequired(), Length(max=200)])
    reference_no = StringField('Reference Number', validators=[DataRequired(), Length(max=50)])
    category_id = SelectField('Category', coerce=int)
    department_id = SelectField('Department', coerce=int)
    
    description = TextAreaField('Job Description', validators=[DataRequired()])
    requirements = TextAreaField('Requirements')
    responsibilities = TextAreaField('Responsibilities')
    benefits = TextAreaField('Benefits')
    
    employment_type = SelectField('Employment Type', choices=[
        ('', 'Select Type'),
        ('Full-Time', 'Full-Time'),
        ('Part-Time', 'Part-Time'),
        ('Contract', 'Contract'),
        ('Internship', 'Internship'),
        ('Temporary', 'Temporary')
    ])
    
    experience_level = SelectField('Experience Level', choices=[
        ('', 'Select Level'),
        ('Entry', 'Entry Level'),
        ('Mid', 'Mid Level'),
        ('Senior', 'Senior Level'),
        ('Executive', 'Executive')
    ])
    
    education_level = SelectField('Education Level', choices=[
        ('', 'Select Level'),
        ('None', 'No Formal Education'),
        ('Certificate', 'Certificate'),
        ('Diploma', 'Diploma'),
        ('Bachelor', 'Bachelor\'s Degree'),
        ('Master', 'Master\'s Degree'),
        ('PhD', 'PhD')
    ])
    
    salary_disclosure = SelectField('Salary Disclosure', choices=[
        ('Confidential', 'Confidential'),
        ('Negotiable', 'Negotiable'),
        ('Fixed', 'Fixed Amount'),
        ('Range', 'Salary Range')
    ])
    
    salary_range_min = DecimalField('Minimum Salary', places=2, validators=[Optional()])
    salary_range_max = DecimalField('Maximum Salary', places=2, validators=[Optional()])
    salary_currency = StringField('Currency', default='KES')
    
    positions_available = IntegerField('Positions Available', default=1, validators=[NumberRange(min=1)])
    application_deadline = DateField('Application Deadline', validators=[DataRequired()])
    start_date = DateField('Expected Start Date')
    
    status = SelectField('Status', choices=[
        ('Draft', 'Draft'),
        ('Published', 'Published'),
        ('Closed', 'Closed')
    ])
    
    is_remote = BooleanField('Remote Position')
    location = StringField('Location')
    
    submit = SubmitField('Save Job Posting')

class CandidateForm(FlaskForm):
    # Personal Information
    first_name = StringField('First Name', validators=[DataRequired(), Length(max=100)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(max=100)])
    email = EmailField('Email Address', validators=[DataRequired(), Email(), Length(max=120)])
    phone = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    date_of_birth = DateField('Date of Birth', validators=[Optional()], format='%Y-%m-%d')
    nationality = StringField('Nationality', validators=[Optional(), Length(max=50)])
    gender = SelectField('Gender', choices=[
        ('', 'Select Gender'),
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other'),
        ('Prefer not to say', 'Prefer not to say')
    ], validators=[Optional()])
    
    # Contact Information
    address = TextAreaField('Address', validators=[Optional()])
    city = StringField('City', validators=[Optional(), Length(max=100)])
    country = StringField('Country', validators=[Optional(), Length(max=100)])
    postal_code = StringField('Postal Code', validators=[Optional(), Length(max=20)])
    
    # Professional Information
    current_company = StringField('Current Company', validators=[Optional(), Length(max=200)])
    current_position = StringField('Current Position', validators=[Optional(), Length(max=200)])
    current_salary = DecimalField('Current Salary', validators=[Optional()], places=2)
    expected_salary = DecimalField('Expected Salary', validators=[Optional()], places=2)
    notice_period = IntegerField('Notice Period (Days)', validators=[Optional(), NumberRange(min=0, max=180)])
    years_of_experience = IntegerField('Years of Experience', validators=[Optional(), NumberRange(min=0, max=50)])
    
    # Education
    highest_qualification = StringField('Highest Qualification', validators=[Optional(), Length(max=200)])
    institution = StringField('Institution', validators=[Optional(), Length(max=200)])
    graduation_year = IntegerField('Graduation Year', validators=[Optional(), NumberRange(min=1900, max=datetime.now().year)])
    
    # Application Details
    source = SelectField('Application Source', choices=[
        ('', 'Select Source'),
        ('Website', 'Website'),
        ('LinkedIn', 'LinkedIn'),
        ('Referral', 'Referral'),
        ('Agency', 'Agency'),
        ('Other', 'Other')
    ], validators=[Optional()])
    
    cover_letter = TextAreaField('Cover Letter', validators=[Optional()])
    
    # Documents & Links
    portfolio_url = URLField('Portfolio URL', validators=[Optional(), URL()])
    linkedin_url = URLField('LinkedIn URL', validators=[Optional(), URL()])
    
    # Resume and Cover Letter Files (handled separately)
    resume = FileField('Resume/CV', validators=[
        Optional(),
        FileAllowed(['pdf', 'doc', 'docx'], 'PDF, DOC, and DOCX files only!')
    ])
    
    cover_letter_file = FileField('Cover Letter File', validators=[
        Optional(),
        FileAllowed(['pdf', 'doc', 'docx'], 'PDF, DOC, and DOCX files only!')
    ])
    
    # Status
    status = SelectField('Status', choices=[
        ('Applied', 'Applied'),
        ('Under Review', 'Under Review'),
        ('Shortlisted', 'Shortlisted'),
        ('Interview Scheduled', 'Interview Scheduled'),
        ('Interviewed', 'Interviewed'),
        ('Reference Check', 'Reference Check'),
        ('Offer Extended', 'Offer Extended'),
        ('Offer Accepted', 'Offer Accepted'),
        ('Offer Rejected', 'Offer Rejected'),
        ('Rejected', 'Rejected'),
        ('On Hold', 'On Hold'),
        ('Withdrawn', 'Withdrawn')
    ], default='Applied', validators=[DataRequired()])

class InterviewPanelForm(FlaskForm):
    name = StringField('Panel Name', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[Optional()])
    panel_type = SelectField('Panel Type', choices=[
        ('', 'Select Type'),
        ('Technical', 'Technical'),
        ('HR', 'HR'),
        ('Management', 'Management'),
        ('Final', 'Final'),
        ('Other', 'Other')
    ])
    
    submit = SubmitField('Save Panel')

class InterviewScoreForm(FlaskForm):
    technical_competence = DecimalField('Technical Competence (0-10)', places=2, validators=[
        Optional(), NumberRange(min=0, max=10)
    ])
    communication_skills = DecimalField('Communication Skills (0-10)', places=2, validators=[
        Optional(), NumberRange(min=0, max=10)
    ])
    problem_solving = DecimalField('Problem Solving (0-10)', places=2, validators=[
        Optional(), NumberRange(min=0, max=10)
    ])
    cultural_fit = DecimalField('Cultural Fit (0-10)', places=2, validators=[
        Optional(), NumberRange(min=0, max=10)
    ])
    leadership_potential = DecimalField('Leadership Potential (0-10)', places=2, validators=[
        Optional(), NumberRange(min=0, max=10)
    ])
    
    strengths = TextAreaField('Strengths', validators=[Optional()])
    weaknesses = TextAreaField('Areas for Improvement', validators=[Optional()])
    overall_feedback = TextAreaField('Overall Feedback', validators=[Optional()])
    recommendation = SelectField('Recommendation', choices=[
        ('', 'Select Recommendation'),
        ('Strong Hire', 'Strong Hire'),
        ('Hire', 'Hire'),
        ('Neutral', 'Neutral'),
        ('No Hire', 'No Hire'),
        ('Strong No Hire', 'Strong No Hire')
    ])
    
    submit = SubmitField('Submit Scores')    