# C:\Users\user\Desktop\AstroCare-main\app\main\routes.py

from datetime import datetime, timedelta
from app.main.models import PatientUser
from flask import render_template, current_app, redirect, url_for, flash, request, jsonify
from flask_login import current_user, login_required, login_user, logout_user
from app.main import main_bp
from app.auth.models import User
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db

# --- Global variable to manage hero content state ---
hero_contents_data = [
    {
        "title": "AstroCare: The Future of Health, Today.",
        "subtitle": "Experience unparalleled efficiency and precision in healthcare management with our AI-powered platform."
    },
    {
        "title": "For Patients: Your Health, Simplified.",
        "subtitle": "Access appointments, medical records, and telehealth services seamlessly. Manage your well-being with ease."
    },
    {
        "title": "For Hospitals: Elevate Operational Excellence.",
        "subtitle": "Streamline workflows, enhance patient care, and boost efficiency with integrated AI-driven solutions."
    }
]
current_hero_content_index = 0
last_content_update_time = datetime.now()

# --- Image Paths for AstroCare In Action Section ---
# Define these paths relative to your 'static' folder
astrocare_system_images = {
    'dashboard_image': 'static/uploads/main_images/doctor-dashboard-black.PNG',
    'registration_image': 'static/uploads/main_images/treatment-form.PNG',
    'doctor_dashboard': 'static/uploads/main_images/dashbboard.PNG',
    'treatment_form': 'static/uploads/main_images/treatment-form.PNG',


}


# --- Existing Routes ---
@main_bp.route('/')
@main_bp.route('/index')
def index():
    """Renders the main homepage of AstroCare."""
    current_app.logger.info("Accessing the main index page.")
    # Pass initial hero content to the template
    initial_content = hero_contents_data[current_hero_content_index]

    # Pass the image paths to the template
    return render_template('index.html',
                           title='Welcome to AstroCare',
                           current_user=current_user,
                           datetime=datetime,
                           initial_hero_title=initial_content['title'],
                           initial_hero_subtitle=initial_content['subtitle'],
                           system_images=astrocare_system_images # <-- Pass image paths here
                          )

@main_bp.route('/get_next_hero_content')
def get_next_hero_content():
    """
    Returns the next set of hero content.
    Manages the 1-minute timer on the backend.
    """
    global current_hero_content_index
    global last_content_update_time

    # Calculate time difference
    time_difference = (datetime.now() - last_content_update_time).total_seconds()

    if time_difference >= 60: # If 1 minute (60 seconds) has passed
        current_hero_content_index = (current_hero_content_index + 1) % len(hero_contents_data)
        last_content_update_time = datetime.now() # Reset timer

    next_content = hero_contents_data[current_hero_content_index]
    return jsonify(next_content) # Return content as JSON

@main_bp.route('/about')
def about():
    """Renders the About Us page."""
    return render_template('about.html', title='About AstroCare')

@main_bp.route('/contact')
def contact():
    """Renders the Contact Us page."""
    return render_template('contact.html', title='Contact Us')

# --- NEW/MOVED Authentication-Related Routes for main_bp ---

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard_bp.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # CORRECTED: Query PatientUser instead of User
        user = PatientUser.query.filter_by(username=username).first()

        # CORRECTED: Use the model's password check method
        if user and user.check_password(password):
            login_user(user, remember=request.form.get('remember_me'))
            flash('Logged in successfully!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main_bp.dashboard'))  # Redirect to dashboard or next page
        else:
            flash('Invalid username or password.', 'error')

    return render_template('login-patient.html', title='Log In')


@main_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard_bp.index'))

    if request.method == 'POST':
        # Get all form data
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')
        phone_number = request.form.get('phone_number')
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        agree_terms = 'agree_terms' in request.form  # Check if checkbox is checked

        # Validation checks
        errors = False
        
        # Check password match
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            errors = True
            
        # Check terms agreement
        if not agree_terms:
            flash('You must agree to the terms and conditions', 'error')
            errors = True
            
        # Check existing user
        if PatientUser.query.filter_by(username=username).first():
            flash('Username already taken.', 'error')
            errors = True
            
        if PatientUser.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            errors = True
            
        if not errors:
            # Create new PatientUser
            new_patient = PatientUser(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone_number=phone_number,
                username=username,
                agree_terms=True
            )
            new_patient.set_password(password)
            
            # Save to database
            db.session.add(new_patient)
            db.session.commit()
            
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('main_bp.login'))

    return render_template('patient-register.html', title='Register')


@main_bp.route('/dashboard')

@main_bp.route('/dashboard')
def dashboard():
    """
    Renders the patient dashboard with aggregated data from various hospitals.
    This will serve as the central hub for the patient.
    """
    # --- Simulate fetching aggregated data from multiple hospitals ---
    # In a real system, these would be complex queries or API calls to various hospital systems
    # For now, we'll use dummy data to illustrate the concept.

    # Data for Quick Access / Action Cards
    upcoming_appointments_count = 2 # e.g., fetched from multiple hospitals
    active_prescriptions_count = 3  # e.g., fetched from multiple hospitals
    total_medical_records = 12      # e.g., aggregated from all reports
    
    # Placeholder for next telehealth session
    # In a real app, you'd fetch the actual next scheduled telehealth session.
    next_telehealth_session_data = datetime.now() + timedelta(hours=2)
    next_telehealth_session = next_telehealth_session_data.strftime('%I:%M %p Today')


    # Detailed Upcoming Appointments (simulated)
    upcoming_appointments = [
        {
            'doctor_name': 'Dr. Sarah Johnson',
            'specialty': 'Cardiology',
            'hospital_name': 'Nairobi General Hospital', # Crucial for multi-hospital context
            'date': datetime.now() + timedelta(days=1),
            'time': datetime.now().replace(hour=10, minute=30)
        },
        {
            'doctor_name': 'Dr. Michael Chen',
            'specialty': 'Dentistry',
            'hospital_name': 'Coastline Dental Clinic', # Another hospital
            'date': datetime.now() + timedelta(days=5),
            'time': datetime.now().replace(hour=14, minute=15)
        }
    ]

    # Health Indicators (simulated)
    health_indicators = [
        {
            'name': 'Blood Pressure',
            'status': 'Normal',
            'color_class': 'text-green-600',
            'bg_class': 'bg-green-500',
            'progress_width': 75
        },
        {
            'name': 'Blood Sugar',
            'status': 'Moderate',
            'color_class': 'text-yellow-600',
            'bg_class': 'bg-yellow-500',
            'progress_width': 45
        },
        {
            'name': 'Cholesterol',
            'status': 'High',
            'color_class': 'text-red-600',
            'bg_class': 'bg-red-500',
            'progress_width': 85
        }
    ]

    # Health Alerts (simulated)
    health_alerts = [
        "Your cholesterol levels are elevated. Consult your doctor about lifestyle changes.",
        "Remember to schedule your annual checkup this quarter."
    ]
    # For demonstration, you can make health_alerts empty to see the "good health" message:
    # health_alerts = []


    # Recent Activities (simulated, from various hospitals)
    recent_activities = [
        {
            'title': 'New Prescription Added',
            'description': 'Dr. Johnson prescribed Lisinopril for blood pressure management.',
            'timestamp': 'Today, 10:45 AM',
            'hospital_name': 'Nairobi General Hospital',
            'dot_color_class': 'bg-indigo-500',
            'icon_class': 'fas fa-prescription-bottle-alt'
        },
        {
            'title': 'Lab Results Updated',
            'description': 'Complete blood count results are now available.',
            'timestamp': 'Yesterday, 3:22 PM',
            'hospital_name': 'Kenyatta National Hospital',
            'dot_color_class': 'bg-green-500',
            'icon_class': 'fas fa-flask'
        },
        {
            'title': 'Imaging Result Received',
            'description': 'X-ray results for your knee are now available.',
            'timestamp': 'Yesterday, 1:00 PM',
            'hospital_name': 'Aga Khan University Hospital',
            'dot_color_class': 'bg-red-500',
            'icon_class': 'fas fa-x-ray'
        },
        {
            'title': 'Appointment Completed',
            'description': 'Annual physical examination with Dr. Rodriguez.',
            'timestamp': 'Jun 5, 11:30 AM',
            'hospital_name': 'Nairobi General Hospital',
            'dot_color_class': 'bg-blue-500',
            'icon_class': 'fas fa-calendar-check'
        }
    ]

    return render_template(
        'patient-dashboard.html',
        title='Your Dashboard',
        current_user=current_user, # Ensure current_user is passed
        upcoming_appointments_count=upcoming_appointments_count,
        active_prescriptions_count=active_prescriptions_count,
        total_medical_records=total_medical_records,
        next_telehealth_session=next_telehealth_session,
        upcoming_appointments=upcoming_appointments,
        health_indicators=health_indicators,
        health_alerts=health_alerts,
        recent_activities=recent_activities
    )

@main_bp.route('/patient/appointments/my')
def patient_appointments_my():
    """
    Displays all of a patient's appointments, aggregated from all connected hospitals.
    Provides options to filter by hospital or date.
    """
    # Simulate fetching appointments from multiple hospitals
    all_appointments = [
        {
            'id': 1, 'date': datetime(2025, 8, 1, 10, 30), 'doctor': 'Dr. Sarah Johnson',
            'specialty': 'Cardiology', 'hospital': 'Nairobi General Hospital',
            'status': 'Confirmed', 'type': 'In-person'
        },
        {
            'id': 2, 'date': datetime(2025, 8, 5, 14, 15), 'doctor': 'Dr. Michael Chen',
            'specialty': 'Dentistry', 'hospital': 'Coastline Dental Clinic',
            'status': 'Confirmed', 'type': 'In-person'
        },
        {
            'id': 3, 'date': datetime(2025, 8, 10, 9, 0), 'doctor': 'Dr. Jane Smith',
            'specialty': 'General Practice', 'hospital': 'Kenyatta National Hospital',
            'status': 'Confirmed', 'type': 'Telehealth'
        },
        {
            'id': 4, 'date': datetime(2025, 7, 25, 11, 0), 'doctor': 'Dr. Alex Kimani',
            'specialty': 'Orthopedics', 'hospital': 'Aga Khan University Hospital',
            'status': 'Completed', 'type': 'In-person'
        },
    ]
    # In a real app, you might add filtering logic here based on request.args (e.g., hospital_id, date_range)
    
    # --- FIX HERE: Pass datetime.now() as a variable ---
    return render_template(
        'patient/appointments/my-appointments.html',
        title='My Appointments',
        appointments=all_appointments,
        current_time=datetime.now(), # Pass datetime.now() as 'current_time'
        # Also ensure timedelta is available in Jinja for the 'Join Telehealth' logic
        # You might need to add it to app.jinja_env.globals if it's not available by default
        timedelta=timedelta # Pass timedelta to the template
    )

@main_bp.route('/patient/appointments/book')

def patient_appointments_book():
    """
    Allows patient to book a new appointment. This route might redirect to
    hospital-specific booking flows or integrate a universal booking form.
    It's generally better to select a hospital first before booking.
    """
    flash("Please select a hospital first to book an appointment.", "info")
    return redirect(url_for('main_bp.book_appointment_select_hospital'))


@main_bp.route('/patient/appointments/hospital-selection')

def book_appointment_select_hospital():
    """
    Patient selects a hospital to book an appointment. This is the new primary entry point
    for booking, reflecting the multi-hospital nature.
    """
    # Simulate available hospitals
    hospitals = [
        {'id': 1, 'name': 'Nairobi General Hospital', 'location': 'Nairobi CBD', 'image': url_for('static', filename='uploads/hospital_logos/hospital1.png')},
        {'id': 2, 'name': 'Kenyatta National Hospital', 'location': 'Upper Hill, Nairobi', 'image': url_for('static', filename='uploads/hospital_logos/hospital2.png')},
        {'id': 3, 'name': 'Aga Khan University Hospital', 'location': 'Parklands, Nairobi', 'image': url_for('static', filename='uploads/hospital_logos/hospital3.png')},
        {'id': 4, 'name': 'Coastline Dental Clinic', 'location': 'Mombasa Road, Nairobi', 'image': url_for('static', filename='uploads/hospital_logos/hospital4.png')},
    ]
    return render_template('patient/appointments/book-by-hospital.html', title='Book by Hospital', hospitals=hospitals)

@main_bp.route('/patient/appointments/book/<int:hospital_id>', methods=['GET', 'POST'])

def patient_appointments_book_at_hospital(hospital_id):
    """
    Booking form for a specific hospital.
    """
    # Simulate fetching hospital details and available doctors/clinics
    # In a real app, this would query the specific hospital's data
    hospitals_data = {
        1: {'name': 'Nairobi General Hospital', 'specialties': ['Cardiology', 'Pediatrics', 'General Medicine']},
        2: {'name': 'Kenyatta National Hospital', 'specialties': ['Oncology', 'Neurology', 'Surgery']},
        3: {'name': 'Aga Khan University Hospital', 'specialties': ['Dermatology', 'Orthopedics', 'ENT']},
        4: {'name': 'Coastline Dental Clinic', 'specialties': ['General Dentistry', 'Orthodontics']},
    }
    hospital = hospitals_data.get(hospital_id)
    if not hospital:
        flash("Hospital not found.", "error")
        return redirect(url_for('main_bp.book_appointment_select_hospital'))

    if request.method == 'POST':
        # Process booking form data here
        selected_specialty = request.form.get('specialty')
        selected_date = request.form.get('appointment_date')
        selected_time = request.form.get('appointment_time')
        # Simulate saving the appointment
        flash(f"Appointment with {selected_specialty} at {hospital['name']} on {selected_date} at {selected_time} booked successfully!", "success")
        return redirect(url_for('main_bp.patient_appointments_my'))

    return render_template('patient/appointments/book-appointment-form.html',
                           title=f'Book at {hospital["name"]}',
                           hospital=hospital)

@main_bp.route('/patient/reports/all')

def patient_reports_all():
    """
    Displays all medical reports for the patient, aggregated from all connected hospitals.
    """
    # Simulate fetching all reports
    all_reports = [
        {'id': 1, 'type': 'Lab Result', 'date': datetime(2025, 7, 28), 'hospital': 'Kenyatta National Hospital', 'description': 'Complete Blood Count (CBC)'},
        {'id': 2, 'type': 'Imaging Report', 'date': datetime(2025, 7, 25), 'hospital': 'Aga Khan University Hospital', 'description': 'Knee X-Ray Report'},
        {'id': 3, 'type': 'Consultation Summary', 'date': datetime(2025, 6, 15), 'hospital': 'Nairobi General Hospital', 'description': 'Cardiology Follow-up'},
        {'id': 4, 'type': 'Lab Result', 'date': datetime(2025, 5, 10), 'hospital': 'Coastline Dental Clinic', 'description': 'Dental X-Ray Results'},
    ]
    # In a real app, you might add filtering/sorting options
    return render_template('patient/reports/all-reports.html', title='All My Reports', reports=all_reports)

@main_bp.route('/patient/reports/hospital-view')

def patient_reports_hospital_view():
    """
    Allows patient to view reports by selecting a specific hospital.
    """
    # Simulate listing hospitals patient has reports from
    hospitals_with_reports = [
        {'id': 1, 'name': 'Nairobi General Hospital'},
        {'id': 2, 'name': 'Kenyatta National Hospital'},
        {'id': 3, 'name': 'Aga Khan University Hospital'},
        {'id': 4, 'name': 'Coastline Dental Clinic'},
    ]
    return render_template('patient/reports/reports-by-hospital.html', title='Reports by Hospital', hospitals=hospitals_with_reports)

@main_bp.route('/patient/reports/hospital/<int:hospital_id>')

def patient_reports_view_by_hospital(hospital_id):
    """
    Displays reports specific to a selected hospital.
    """
    hospital_name_map = {
        1: 'Nairobi General Hospital',
        2: 'Kenyatta National Hospital',
        3: 'Aga Khan University Hospital',
        4: 'Coastline Dental Clinic',
    }
    selected_hospital_name = hospital_name_map.get(hospital_id, 'Unknown Hospital')

    # Simulate fetching reports for a specific hospital
    reports_for_hospital = [
        {'id': 1, 'type': 'Lab Result', 'date': datetime(2025, 7, 28), 'description': 'Complete Blood Count (CBC)'}
    ] if hospital_id == 2 else [
        {'id': 2, 'type': 'Imaging Report', 'date': datetime(2025, 7, 25), 'description': 'Knee X-Ray Report'}
    ] if hospital_id == 3 else [
        {'id': 3, 'type': 'Consultation Summary', 'date': datetime(2025, 6, 15), 'description': 'Cardiology Follow-up'}
    ] if hospital_id == 1 else [
        {'id': 4, 'type': 'Lab Result', 'date': datetime(2025, 5, 10), 'description': 'Dental X-Ray Results'}
    ] if hospital_id == 4 else []

    if not reports_for_hospital:
        flash(f"No reports found for {selected_hospital_name}.", "info")

    return render_template('patient/reports/hospital-reports-list.html',
                           title=f'Reports from {selected_hospital_name}',
                           hospital_name=selected_hospital_name,
                           reports=reports_for_hospital)

@main_bp.route('/patient/imaging-results')

def patient_imaging_results():
    """Displays all imaging results."""
    # Simulate fetching imaging results
    imaging_results = [
        {'id': 1, 'date': datetime(2025, 7, 25), 'type': 'X-Ray', 'area': 'Knee', 'hospital': 'Aga Khan University Hospital', 'link': '#'},
        {'id': 2, 'date': datetime(2025, 6, 10), 'type': 'MRI', 'area': 'Brain', 'hospital': 'Nairobi General Hospital', 'link': '#'},
    ]
    return render_template('patient/reports/imaging-results.html', title='Imaging Results', results=imaging_results)

@main_bp.route('/patient/lab-results')

def patient_lab_results():
    """Displays all lab results."""
    # Simulate fetching lab results
    lab_results = [
        {'id': 1, 'date': datetime(2025, 7, 28), 'test': 'Complete Blood Count (CBC)', 'hospital': 'Kenyatta National Hospital', 'status': 'Normal', 'link': '#'},
        {'id': 2, 'date': datetime(2025, 7, 15), 'test': 'Blood Glucose', 'hospital': 'Nairobi General Hospital', 'status': 'Elevated', 'link': '#'},
    ]
    return render_template('patient/reports/lab-results.html', title='Lab Results', results=lab_results)

@main_bp.route('/patient/telehealth')

def patient_telehealth():
    """
    Patient's telehealth hub: lists upcoming sessions, provides option to join, or book new.
    """
    # Simulate upcoming telehealth sessions
    telehealth_sessions = [
        {'id': 1, 'date': datetime.now() + timedelta(hours=1), 'doctor': 'Dr. Evans Omondi', 'specialty': 'General Practice', 'hospital': 'Aga Khan University Hospital', 'status': 'Scheduled', 'meeting_link': '#'},
        {'id': 2, 'date': datetime.now() + timedelta(days=2), 'doctor': 'Dr. Ann Wanjiku', 'specialty': 'Nutrition', 'hospital': 'Kenyatta National Hospital', 'status': 'Scheduled', 'meeting_link': '#'},
    ]
    return render_template('patient/telehealth/telehealth-dashboard.html', title='Telehealth Services', sessions=telehealth_sessions)

@main_bp.route('/patient/medications/current')

def patient_medications_current():
    """Displays current and past prescriptions."""
    # Simulate prescriptions
    prescriptions = [
        {'id': 1, 'name': 'Lisinopril', 'dosage': '10mg daily', 'doctor': 'Dr. Sarah Johnson', 'hospital': 'Nairobi General Hospital', 'refills_left': 3, 'expiry': datetime(2026, 1, 15)},
        {'id': 2, 'name': 'Amoxicillin', 'dosage': '500mg three times daily', 'doctor': 'Dr. Michael Chen', 'hospital': 'Coastline Dental Clinic', 'refills_left': 0, 'expiry': datetime(2025, 8, 1)},
    ]
    return render_template('patient/medications/my-prescriptions.html', title='My Prescriptions', prescriptions=prescriptions, timedelta=timedelta)

@main_bp.route('/patient/medications/refills', methods=['GET', 'POST'])

def patient_medications_refills():
    """Allows patient to request refills."""
    # Simulate available prescriptions for refill
    refillable_prescriptions = [
        {'id': 1, 'name': 'Lisinopril', 'doctor': 'Dr. Sarah Johnson', 'hospital': 'Nairobi General Hospital', 'refills_left': 3},
        {'id': 3, 'name': 'Metformin', 'doctor': 'Dr. David Kimani', 'hospital': 'Kenyatta National Hospital', 'refills_left': 1},
    ]

    if request.method == 'POST':
        prescription_id = request.form.get('prescription_id')
        # In a real app, you'd validate the ID and process the refill request
        flash(f"Refill request for Prescription ID {prescription_id} submitted successfully!", "success")
        return redirect(url_for('main_bp.patient_medications_current'))

    return render_template('patient/medications/request-refills.html', title='Request Refills', prescriptions=refillable_prescriptions)

@main_bp.route('/patient/messages')

def patient_messages():
    """Patient's secure messaging inbox."""
    # Simulate messages
    messages = [
        {'id': 1, 'sender': 'Dr. Sarah Johnson (Nairobi General)', 'subject': 'Your recent lab results', 'date': datetime(2025, 7, 30, 14, 0), 'read': False},
        {'id': 2, 'sender': 'Admin (AstroCare Support)', 'subject': 'System Update Notification', 'date': datetime(2025, 7, 29, 10, 0), 'read': True},
        {'id': 3, 'sender': 'Billing Dept (Kenyatta National)', 'subject': 'Regarding outstanding balance', 'date': datetime(2025, 7, 28, 9, 30), 'read': False},
    ]
    return render_template('patient/messages/messages-inbox.html', title='My Messages', messages=messages)

@main_bp.route('/patient/billing')

def patient_billing():
    """Displays billing statements and payment options."""
    # Simulate billing records
    billing_records = [
        {'id': 1, 'date': datetime(2025, 7, 20), 'hospital': 'Kenyatta National Hospital', 'amount': 15000, 'status': 'Outstanding', 'service': 'Consultation & Lab Tests'},
        {'id': 2, 'date': datetime(2025, 6, 10), 'hospital': 'Nairobi General Hospital', 'amount': 5000, 'status': 'Paid', 'service': 'Dental Checkup'},
    ]
    return render_template('patient/billing/billing-payments.html', title='Billing & Payments', records=billing_records)

@main_bp.route('/patient/hospitals')

def patient_hospitals():
    """
    Provides a directory of all hospitals within the AstroCare network that the patient has interacted with,
    or can interact with, highlighting the multi-hospital system.
    """
    # Simulate hospitals in the network
    hospitals_in_network = [
        {'id': 1, 'name': 'Nairobi General Hospital', 'location': 'Nairobi', 'specialties': 'General Medicine, Cardiology, Surgery', 'link': url_for('main_bp.patient_hospitals_details', hospital_id=1)},
        {'id': 2, 'name': 'Kenyatta National Hospital', 'location': 'Nairobi', 'specialties': 'Oncology, Neurology, Emergency', 'link': url_for('main_bp.patient_hospitals_details', hospital_id=2)},
        {'id': 3, 'name': 'Aga Khan University Hospital', 'location': 'Nairobi', 'specialties': 'Multi-specialty, Research, Training', 'link': url_for('main_bp.patient_hospitals_details', hospital_id=3)},
        {'id': 4, 'name': 'Coastline Dental Clinic', 'location': 'Mombasa', 'specialties': 'Dental Care, Orthodontics', 'link': url_for('main_bp.patient_hospitals_details', hospital_id=4)},
    ]
    return render_template('patient/hospitals/hospital-directory.html', title='Our Hospital Network', hospitals=hospitals_in_network)

@main_bp.route('/patient/hospitals/<int:hospital_id>')

def patient_hospitals_details(hospital_id):
    """
    Displays details for a specific hospital, along with options to view patient's
    records from this hospital, or book appointments specific to this hospital.
    """
    # Simulate fetching specific hospital details
    hospital_details_data = {
        1: {'name': 'Nairobi General Hospital', 'location': 'Nairobi', 'contact': '+2547XXXXXXXX', 'description': 'A leading multi-specialty hospital in Nairobi, offering comprehensive medical services.', 'services': ['Emergency', 'Surgery', 'Outpatient Clinics'], 'patient_records_link': url_for('main_bp.patient_reports_view_by_hospital', hospital_id=1), 'book_appointment_link': url_for('main_bp.patient_appointments_book_at_hospital', hospital_id=1)},
        2: {'name': 'Kenyatta National Hospital', 'location': 'Nairobi', 'contact': '+2547XXXXXXXX', 'description': 'Kenya\'s largest referral hospital, known for specialized care and medical training.', 'services': ['Oncology', 'Neurology', 'Dialysis'], 'patient_records_link': url_for('main_bp.patient_reports_view_by_hospital', hospital_id=2), 'book_appointment_link': url_for('main_bp.patient_appointments_book_at_hospital', hospital_id=2)},
        3: {'name': 'Aga Khan University Hospital', 'location': 'Nairobi', 'contact': '+2547XXXXXXXX', 'description': 'An internationally accredited teaching hospital providing high-quality patient care and medical education.', 'services': ['Maternity', 'Pediatrics', 'ENT'], 'patient_records_link': url_for('main_bp.patient_reports_view_by_hospital', hospital_id=3), 'book_appointment_link': url_for('main_bp.patient_appointments_book_at_hospital', hospital_id=3)},
        4: {'name': 'Coastline Dental Clinic', 'location': 'Mombasa', 'contact': '+2547XXXXXXXX', 'description': 'Specializing in comprehensive dental health, from routine check-ups to advanced orthodontic treatments.', 'services': ['Dental Exams', 'Cleanings', 'Orthodontics'], 'patient_records_link': url_for('main_bp.patient_reports_view_by_hospital', hospital_id=4), 'book_appointment_link': url_for('main_bp.patient_appointments_book_at_hospital', hospital_id=4)},
    }
    hospital = hospital_details_data.get(hospital_id)
    if not hospital:
        flash("Hospital details not found.", "error")
        return redirect(url_for('main_bp.patient_hospitals'))

    return render_template('patient/hospitals/hospital-details.html', title=hospital['name'], hospital=hospital)


@main_bp.route('/patient/profile/details')

def patient_profile_details():
    """Displays and allows editing of patient personal details."""
    # In a real app, retrieve current_user details from DB
    return render_template('patient/profile/my-details.html', title='My Details', user=current_user)

@main_bp.route('/patient/profile/security')

def patient_profile_security():
    """Manages patient account security settings (e.g., password change)."""
    return render_template('patient/profile/security.html', title='Security Settings')

@main_bp.route('/patient/profile/preferences')

def patient_profile_preferences():
    """Manages patient preferences (e.g., notification settings)."""
    return render_template('patient/profile/preferences.html', title='Preferences')

@main_bp.route('/patient/help')

def patient_help():
    """Provides access to help resources and FAQs."""
    return render_template('patient/help/help-support.html', title='Help & Support')



@main_bp.route('/profile')
def profile():
    return render_template('profile.html', title='User Profile', user=current_user)

@main_bp.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main_bp.index'))