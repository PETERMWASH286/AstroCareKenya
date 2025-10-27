# app/commands.py
import click
from flask import current_app
from flask.cli import with_appcontext

from app.extensions import db
from app.auth.models import User, Role
from app.super_admin.models import Hospital
from app.user_management.create_privileges import create_initial_privileges
from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker

# --- Seed Privileges Command ---
@click.command('seed-privileges')
@with_appcontext
def seed_privileges():
    """Seed initial privileges into the database."""
    create_initial_privileges()
    click.echo('✅ Privileges seeded.')

# --- Seed Roles Command ---
@click.command('seed-roles')
@with_appcontext
def seed_roles():
    """Seed default roles into the database."""
    # Assuming Role.insert_roles() handles permissions and defaults
    Role.insert_roles()
    click.echo('✅ Roles seeded.')

# --- Seed Departments Command ---
@click.command('seed-departments')
@with_appcontext
def seed_departments():
    """Seed default departments into the database."""
    from app.user_management.models import Department  # avoid circular import
    departments = [
        "General Medicine", "Pediatrics", "Surgery", "Pharmacy",
        "Laboratory", "Radiology", "Human Resources", "Billing",
        "Doctor", "Clinical Officer", "Receptionist", "Nursing", "Administrator",
    ]
    created = 0
    for name in departments:
        if not Department.query.filter_by(name=name).first():
            dept = Department(name=name)
            db.session.add(dept)
            created += 1
    db.session.commit()
    click.echo(f'✅ Departments seeded: {created}')

# --- Init DB Command ---
@click.command('init-db')
@with_appcontext
def init_db():
    """Initialize the database: create tables, seed roles, departments, and privileges."""
    # Create all tables
    db.create_all()
    click.echo('Initialized the database schema.')

    # Seed default roles
    Role.insert_roles()
    click.echo('Inserted default roles.')

    # Seed default departments
    from app.user_management.models import Department
    departments = [
        "General Medicine", "Pediatrics", "Surgery", "Pharmacy",
        "Laboratory", "Radiology", "Human Resources", "Billing",
        "Doctor", "Clinical Officer", "Receptionist", "Nursing", "Administrator",
    ]
    dept_created = 0
    for name in departments:
        if not Department.query.filter_by(name=name).first():
            db.session.add(Department(name=name))
            dept_created += 1
    db.session.commit()
    click.echo(f'Inserted {dept_created} departments.')

    # Seed basic privileges
    create_initial_privileges()
    click.echo('Inserted initial privileges.')

# --- Drop DB Command ---
@click.command('drop-db')
@with_appcontext
def drop_db():
    """Drop all tables in the database."""
    db.drop_all()
    click.echo('Dropped all tables.')

@click.command('create-admin')
@click.argument('username')
@click.argument('email')
@click.argument('password')
@with_appcontext
def create_admin(username, email, password):
    """Create a new admin user."""
    try:
        user = create_admin_user(username, email, password)
        click.echo(f"Admin user '{user.username}' created successfully.")
    except ValueError as ve:
        click.echo(str(ve), err=True)

def create_admin_user(username, email, password):
    admin_role = Role.query.filter_by(name='Administrator').first()
    if not admin_role:
        raise ValueError("Administrator role not found. Run 'seed_roles' first.")
    if User.query.filter_by(username=username).first():
        raise ValueError(f"User '{username}' already exists.")
    if User.query.filter_by(email=email).first():
        raise ValueError(f"Email '{email}' already exists.")

    user = User(username=username, email=email)
    user.password = password
    user.roles.append(admin_role)
    db.session.add(user)
    db.session.commit()
    return user

# --- Seed Departments Command ---
@click.command('seed-departments')
@with_appcontext
def seed_departments_command():
    """Seed default departments into the database."""
    from app.user_management.models import Department  # import here to avoid circular import issues

    departments = [
        "General Medicine", "Pediatrics", "Surgery", "Pharmacy",
        "Laboratory", "Radiology", "Human Resources", "Billing",
        "Doctor", "Clinical Officer", "Receptionist", "Nursing", "Administrator",
    ]

    added_count = 0
    for name in departments:
        if not Department.query.filter_by(name=name).first():
            db.session.add(Department(name=name))
            added_count += 1

    db.session.commit()
    click.echo(f"✅ Seeded {added_count} new department(s).")



@click.command('seed-services')
@with_appcontext
def seed_services_command():
    """Seed default medical services into the database."""
    from app.patients.models import Service  # Import inside to avoid circular imports

    all_services = [
        # Consultation Services
        {'id': 1, 'name': 'General Consultation', 'category': 'Consultation', 
         'price': 1500, 'desc': 'Basic doctor consultation'},
        {'id': 2, 'name': 'Specialist Consultation', 'category': 'Consultation',
         'price': 3000, 'desc': 'Consultation with specialist doctor'},
        {'id': 3, 'name': 'Pediatric Consultation', 'category': 'Consultation',
         'price': 2500, 'desc': 'Child health specialist consultation'},
        {'id': 4, 'name': 'Cardiology Consultation', 'category': 'Consultation',
         'price': 4000, 'desc': 'Heart specialist consultation'},

        # Laboratory Services
        {
            'id': 5,
            'name': 'Basic Blood Test',
            'category': 'Laboratory',
            'price': 800,
            'desc': 'Complete blood count (CBC)',
            'predefined': [
                {
                    "value": "WBC: 4.5-11.0 x10³/μL (Normal)\nRBC: 4.2-5.9 x10⁶/μL\nHGB: 13.5-17.5 g/dL\nPlatelets: 150-450 x10³/μL",
                    "text": "Normal CBC Results"
                },
                {
                    "value": "WBC: 15.2 x10³/μL (High)\nNeutrophils: 85% (Increased)\nLymphocytes: 10%\nPossible bacterial infection",
                    "text": "Leukocytosis - Possible Infection"
                }
            ]
        },
        {
            'id': 6,
            'name': 'Malaria Test',
            'category': 'Laboratory',
            'price': 500,
            'desc': 'Malaria parasite detection',
            'predefined': [
                {
                    "value": "Malaria Parasites: Not Detected\nMethod: Rapid Diagnostic Test & Microscopy\nResult: Negative",
                    "text": "Negative for Malaria"
                },
                {
                    "value": "Plasmodium falciparum: Detected\nParasite Density: 2% (+)\nRecommend: Artemisinin-based therapy",
                    "text": "Positive for P.falciparum"
                }
            ]
        },
        {
            'id': 7,
            'name': 'HIV Screening',
            'category': 'Laboratory',
            'price': 1000,
            'desc': 'HIV 1 & 2 antibodies test',
            'predefined': [
                {
                    "value": "HIV-1/2 Antibodies: Non-Reactive\nMethod: Fourth Generation ELISA\nConclusion: Negative",
                    "text": "HIV Negative"
                },
                {
                    "value": "HIV-1 Antibodies: Reactive\nRecommend: Confirmatory Western Blot\nCounseling provided",
                    "text": "Preliminary Positive - Needs Confirmation"
                }
            ]
        },
        {
            'id': 8,
            'name': 'Urinalysis',
            'category': 'Laboratory',
            'price': 600,
            'desc': 'Complete urine analysis',
            'predefined': [
                {
                    "value": "Color: Yellow\nAppearance: Clear\nProtein: Negative\nGlucose: Negative\nWBC: 0-2/hpf\nRBC: None",
                    "text": "Normal Urinalysis"
                },
                {
                    "value": "WBC: >50/hpf\nNitrites: Positive\nLeukocyte esterase: Positive\nDiagnosis: UTI",
                    "text": "Urinary Tract Infection"
                }
            ]
        },
        {
            'id': 9,
            'name': 'Lipid Profile',
            'category': 'Laboratory',
            'price': 2500,
            'desc': 'Cholesterol and triglycerides test',
            'predefined': [
                {
                    "value": "Total Cholesterol: <200 mg/dL\nLDL: <100 mg/dL\nHDL: >60 mg/dL\nTriglycerides: <150 mg/dL",
                    "text": "Normal Lipid Profile"
                },
                {
                    "value": "Total Cholesterol: 280 mg/dL\nLDL: 190 mg/dL\nHDL: 35 mg/dL\nRecommend: Statin therapy",
                    "text": "Hyperlipidemia Detected"
                }
            ]
        },

        # Radiology/Imaging Services
        {
            'id': 10,
            'name': 'X-Ray (Chest)',
            'category': 'Radiology',
            'price': 4500,
            'desc': 'Standard chest X-ray',
            'predefined': [
                {
                    "value": "Lung fields: Clear\nCardiac silhouette: Normal\nMediastinum: Unremarkable\nNo acute cardiopulmonary findings",
                    "text": "Normal Chest X-ray"
                },
                {
                    "value": "Right lower lobe consolidation\nAir bronchograms present\nImpression: Pneumonia",
                    "text": "Pneumonia Findings"
                }
            ]
        },
        {
            'id': 11,
            'name': 'Ultrasound (Abdomen)',
            'category': 'Radiology',
            'price': 6500,
            'desc': 'Abdominal ultrasound scan',
            'predefined': [
                {
                    "value": "Liver: Normal echotexture\nGallbladder: No stones\nPancreas: Unremarkable\nKidneys: Normal size & shape",
                    "text": "Normal Abdominal Ultrasound"
                },
                {
                    "value": "Gallbladder: Multiple calculi\nWall thickening >3mm\nDiagnosis: Cholelithiasis with cholecystitis",
                    "text": "Gallbladder Stones"
                }
            ]
        },
        {
            'id': 12,
            'name': 'MRI Scan',
            'category': 'Radiology',
            'price': 25000,
            'desc': 'Full body MRI scan',
            'predefined': [
                {
                    "value": "Brain: Normal parenchyma\nNo mass lesions\nVentricles: Normal size\nCerebellum: Unremarkable",
                    "text": "Normal Brain MRI"
                },
                {
                    "value": "L4-L5: Disc herniation compressing nerve root\nImpression: Sciatica etiology",
                    "text": "Herniated Disc"
                }
            ]
        },
        {
            'id': 13,
            'name': 'CT Scan (Head)',
            'category': 'Radiology',
            'price': 18000,
            'desc': 'Head CT scan',
            'predefined': [
                {
                    "value": "No intracranial hemorrhage\nVentricles: Normal size\nGrey-white differentiation: Preserved\nNo mass effect",
                    "text": "Normal Head CT"
                },
                {
                    "value": "Left parietal hypodensity\nEffacement of sulci\nMidline shift 5mm\nImpression: Acute ischemic stroke",
                    "text": "Ischemic Stroke"
                }
            ]
        },
        {
            'id': 14,
            'name': 'Mammography',
            'category': 'Radiology',
            'price': 12000,
            'desc': 'Breast cancer screening',
            'predefined': [
                {
                    "value": "Breast composition: Mostly fatty\nNo masses or distortions\nNo suspicious calcifications\nBI-RADS 1: Negative",
                    "text": "Normal Mammogram"
                },
                {
                    "value": "Cluster of microcalcifications (BI-RADS 4)\nRecommend: Biopsy for histopathology",
                    "text": "Suspicious Calcifications"
                }
            ]
        },

        # Pharmacy Services
        {'id': 15, 'name': 'Basic Medication', 'category': 'Pharmacy',
         'price': 500, 'desc': 'Generic prescription drugs'},
        {'id': 16, 'name': 'Antibiotics Course', 'category': 'Pharmacy',
         'price': 1500, 'desc': 'Full course of antibiotics'},
        {'id': 17, 'name': 'Chronic Medication', 'category': 'Pharmacy',
         'price': 3000, 'desc': 'Monthly chronic disease medication'}
    ]

    added_count = 0
    updated_count = 0
    
    for service_data in all_services:
        # Try to find existing service by ID first
        service = Service.query.get(service_data['id'])
        
        if not service:
            # If not found by ID, check by name
            service = Service.query.filter_by(name=service_data['name']).first()
        
        if service:
            # Update existing service
            service.category = service_data['category']
            service.price = service_data['price']
            service.description = service_data['desc']
            service.predefined_results = service_data.get('predefined', [])
            updated_count += 1
        else:
            # Create new service with explicit ID
            service = Service(
                id=service_data['id'],
                name=service_data['name'],
                category=service_data['category'],
                price=service_data['price'],
                description=service_data['desc'],
                predefined_results=service_data.get('predefined', [])
            )
            db.session.add(service)
            added_count += 1

    db.session.commit()
    click.echo(f"✅ Services: {added_count} added, {updated_count} updated. Total: {Service.query.count()}")


@click.command('seed-all-tenants')
@with_appcontext
def seed_all_tenants():
    """Seed data to all tenant databases"""
    # Get all hospitals from central database
    hospitals = Hospital.query.all()
    
    if not hospitals:
        click.echo("❌ No hospitals found in central database")
        return
    
    click.echo(f"Found {len(hospitals)} hospitals to seed")
    
    for hospital in hospitals:
        try:
            click.echo(f"\nSeeding tenant: {hospital.name} ({hospital.subdomain})")
            
            # Create engine for tenant database
            engine = create_engine(hospital.db_uri)
            
            # Create session directly without scoped_session
            Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
            session = Session()
            
            try:
                # Use the session directly for tenant operations
                seed_privileges_for_tenant(session)
                seed_roles_for_tenant(session)
                seed_departments_for_tenant(session)
                seed_services_for_tenant(session)
                
                session.commit()
                click.echo(f"✅ Successfully seeded {hospital.name}")
            except Exception as e:
                session.rollback()
                click.echo(f"❌ Error seeding {hospital.name}: {str(e)}")
                import traceback
                click.echo(traceback.format_exc())  # Add detailed traceback
            finally:
                session.close()
                engine.dispose()
        except Exception as e:
            click.echo(f"❌ Failed to connect to {hospital.name} database: {str(e)}")
            import traceback
            click.echo(traceback.format_exc())  # Add detailed traceback

# Update all seed functions to accept session parameter
def seed_privileges_for_tenant(session):
    """Seed privileges for current tenant session"""
    from app.user_management.create_privileges import create_initial_privileges
    create_initial_privileges(session)  # Update function to accept session
    click.echo("  - Seeded privileges")

def seed_roles_for_tenant(session):
    """Seed roles for current tenant session"""
    from app.auth.models import Role
    
    # Define roles data
    roles_data = {
        'Patient': (0, True),
        'Registration': (0, False),
        'Nurse': (0, False),
        'Doctor': (0, False),
        'Pharmacist': (0, False),
        'Lab Tech': (0, False),
        'Radiologist': (0, False),
        'Billing Officer': (0, False),
        'Admin': (0, False),
        'Board Memember': (0, False),
        'IT Specialist': (0, False), # ADDED: IT Role


    }
    
    created = 0
    updated = 0
    
    for role_name, (permissions, is_default) in roles_data.items():
        # Check if role exists
        role = session.query(Role).filter_by(name=role_name).first()
        
        if not role:
            # Create new role
            role = Role(
                name=role_name,
                permissions=permissions,
                default=is_default
            )
            session.add(role)
            created += 1
        else:
            # Update existing role
            if role.permissions != permissions or role.default != is_default:
                role.permissions = permissions
                role.default = is_default
                updated += 1
    
    session.commit()
    click.echo(f"  - Seeded roles: {created} created, {updated} updated")

def seed_departments_for_tenant(session):
    """Seed departments for current tenant session"""
    from app.user_management.models import Department
    departments = [
        "General Medicine", "Pediatrics", "Surgery", "Pharmacy",
        "Laboratory", "Radiology", "Human Resources", "Billing",         "Cardiology", "Dermatology", "Neurology", "Orthopedics", 
        "Ophthalmology", "ENT (Ear, Nose & Throat)", "Dentistry",
        "Psychiatry", "Obstetrics & Gynecology", "Urology",
        "Gastroenterology", "Endocrinology", "Oncology",
        "Pulmonology", "Nephrology", "Rheumatology",
        "Doctor", "Clinical Officer", "Receptionist", "Nursing", "Administrator", "Board Memember", "Information Technology",
    ]
    created = 0
    for name in departments:
        if not session.query(Department).filter_by(name=name).first():
            dept = Department(name=name)
            session.add(dept)
            created += 1
    session.commit()
    click.echo(f"  - Seeded {created} departments")

def seed_services_for_tenant(session):
    """Seed medical services for current tenant session"""
    from app.patients.models import Service
    # ... (copy your existing seed_services_command logic here) ...
    # This should be the same as your existing seed_services_command function body
    # without the click decorators and @with_appcontext
    
    all_services = [
        # Consultation Services
        {'id': 1, 'name': 'General Consultation', 'category': 'Consultation', 
         'price': 1500, 'desc': 'Basic doctor consultation'},
        {'id': 2, 'name': 'Specialist Consultation', 'category': 'Consultation',
         'price': 3000, 'desc': 'Consultation with specialist doctor'},
        {'id': 3, 'name': 'Pediatric Consultation', 'category': 'Consultation',
         'price': 2500, 'desc': 'Child health specialist consultation'},
        {'id': 4, 'name': 'Cardiology Consultation', 'category': 'Consultation',
         'price': 4000, 'desc': 'Heart specialist consultation'},

        # Laboratory Services
        {
            'id': 5,
            'name': 'Basic Blood Test',
            'category': 'Laboratory',
            'price': 800,
            'desc': 'Complete blood count (CBC)',
            'predefined': [
                {
                    "value": "WBC: 4.5-11.0 x10³/μL (Normal)\nRBC: 4.2-5.9 x10⁶/μL\nHGB: 13.5-17.5 g/dL\nPlatelets: 150-450 x10³/μL",
                    "text": "Normal CBC Results"
                },
                {
                    "value": "WBC: 15.2 x10³/μL (High)\nNeutrophils: 85% (Increased)\nLymphocytes: 10%\nPossible bacterial infection",
                    "text": "Leukocytosis - Possible Infection"
                }
            ]
        },
        {
            'id': 6,
            'name': 'Malaria Test',
            'category': 'Laboratory',
            'price': 500,
            'desc': 'Malaria parasite detection',
            'predefined': [
                {
                    "value": "Malaria Parasites: Not Detected\nMethod: Rapid Diagnostic Test & Microscopy\nResult: Negative",
                    "text": "Negative for Malaria"
                },
                {
                    "value": "Plasmodium falciparum: Detected\nParasite Density: 2% (+)\nRecommend: Artemisinin-based therapy",
                    "text": "Positive for P.falciparum"
                }
            ]
        },
        {
            'id': 7,
            'name': 'HIV Screening',
            'category': 'Laboratory',
            'price': 1000,
            'desc': 'HIV 1 & 2 antibodies test',
            'predefined': [
                {
                    "value": "HIV-1/2 Antibodies: Non-Reactive\nMethod: Fourth Generation ELISA\nConclusion: Negative",
                    "text": "HIV Negative"
                },
                {
                    "value": "HIV-1 Antibodies: Reactive\nRecommend: Confirmatory Western Blot\nCounseling provided",
                    "text": "Preliminary Positive - Needs Confirmation"
                }
            ]
        },
        {
            'id': 8,
            'name': 'Urinalysis',
            'category': 'Laboratory',
            'price': 600,
            'desc': 'Complete urine analysis',
            'predefined': [
                {
                    "value": "Color: Yellow\nAppearance: Clear\nProtein: Negative\nGlucose: Negative\nWBC: 0-2/hpf\nRBC: None",
                    "text": "Normal Urinalysis"
                },
                {
                    "value": "WBC: >50/hpf\nNitrites: Positive\nLeukocyte esterase: Positive\nDiagnosis: UTI",
                    "text": "Urinary Tract Infection"
                }
            ]
        },
        {
            'id': 9,
            'name': 'Lipid Profile',
            'category': 'Laboratory',
            'price': 2500,
            'desc': 'Cholesterol and triglycerides test',
            'predefined': [
                {
                    "value": "Total Cholesterol: <200 mg/dL\nLDL: <100 mg/dL\nHDL: >60 mg/dL\nTriglycerides: <150 mg/dL",
                    "text": "Normal Lipid Profile"
                },
                {
                    "value": "Total Cholesterol: 280 mg/dL\nLDL: 190 mg/dL\nHDL: 35 mg/dL\nRecommend: Statin therapy",
                    "text": "Hyperlipidemia Detected"
                }
            ]
        },

        # Radiology/Imaging Services
        {
            'id': 10,
            'name': 'X-Ray (Chest)',
            'category': 'Radiology',
            'price': 4500,
            'desc': 'Standard chest X-ray',
            'predefined': [
                {
                    "value": "Lung fields: Clear\nCardiac silhouette: Normal\nMediastinum: Unremarkable\nNo acute cardiopulmonary findings",
                    "text": "Normal Chest X-ray"
                },
                {
                    "value": "Right lower lobe consolidation\nAir bronchograms present\nImpression: Pneumonia",
                    "text": "Pneumonia Findings"
                }
            ]
        },
        {
            'id': 11,
            'name': 'Ultrasound (Abdomen)',
            'category': 'Radiology',
            'price': 6500,
            'desc': 'Abdominal ultrasound scan',
            'predefined': [
                {
                    "value": "Liver: Normal echotexture\nGallbladder: No stones\nPancreas: Unremarkable\nKidneys: Normal size & shape",
                    "text": "Normal Abdominal Ultrasound"
                },
                {
                    "value": "Gallbladder: Multiple calculi\nWall thickening >3mm\nDiagnosis: Cholelithiasis with cholecystitis",
                    "text": "Gallbladder Stones"
                }
            ]
        },
        {
            'id': 12,
            'name': 'MRI Scan',
            'category': 'Radiology',
            'price': 25000,
            'desc': 'Full body MRI scan',
            'predefined': [
                {
                    "value": "Brain: Normal parenchyma\nNo mass lesions\nVentricles: Normal size\nCerebellum: Unremarkable",
                    "text": "Normal Brain MRI"
                },
                {
                    "value": "L4-L5: Disc herniation compressing nerve root\nImpression: Sciatica etiology",
                    "text": "Herniated Disc"
                }
            ]
        },
        {
            'id': 13,
            'name': 'CT Scan (Head)',
            'category': 'Radiology',
            'price': 18000,
            'desc': 'Head CT scan',
            'predefined': [
                {
                    "value": "No intracranial hemorrhage\nVentricles: Normal size\nGrey-white differentiation: Preserved\nNo mass effect",
                    "text": "Normal Head CT"
                },
                {
                    "value": "Left parietal hypodensity\nEffacement of sulci\nMidline shift 5mm\nImpression: Acute ischemic stroke",
                    "text": "Ischemic Stroke"
                }
            ]
        },
        {
            'id': 14,
            'name': 'Mammography',
            'category': 'Radiology',
            'price': 12000,
            'desc': 'Breast cancer screening',
            'predefined': [
                {
                    "value": "Breast composition: Mostly fatty\nNo masses or distortions\nNo suspicious calcifications\nBI-RADS 1: Negative",
                    "text": "Normal Mammogram"
                },
                {
                    "value": "Cluster of microcalcifications (BI-RADS 4)\nRecommend: Biopsy for histopathology",
                    "text": "Suspicious Calcifications"
                }
            ]
        },

        # Pharmacy Services
        {'id': 15, 'name': 'Basic Medication', 'category': 'Pharmacy',
         'price': 500, 'desc': 'Generic prescription drugs'},
        {'id': 16, 'name': 'Antibiotics Course', 'category': 'Pharmacy',
         'price': 1500, 'desc': 'Full course of antibiotics'},
        {'id': 17, 'name': 'Chronic Medication', 'category': 'Pharmacy',
         'price': 3000, 'desc': 'Monthly chronic disease medication'}
    ]

    added_count = 0
    updated_count = 0
    
    for service_data in all_services:
        # Use session.query() directly
        service = session.query(Service).get(service_data['id'])
        
        if not service:
            # If not found by ID, check by name
            service = session.query(Service).filter_by(name=service_data['name']).first()
        
        if service:
            # Update existing service
            service.category = service_data['category']
            service.price = service_data['price']
            service.description = service_data['desc']
            service.predefined_results = service_data.get('predefined', [])
            updated_count += 1
        else:
            # Create new service with explicit ID
            service = Service(
                id=service_data['id'],
                name=service_data['name'],
                category=service_data['category'],
                price=service_data['price'],
                description=service_data['desc'],
                predefined_results=service_data.get('predefined', [])
            )
            session.add(service)
            added_count += 1
    
    session.commit()
    # END of copied content
    
    click.echo(f"  - Seeded services: {added_count} added, {updated_count} updated")


@click.command('migrate-tenants')
@with_appcontext
def migrate_tenants():
    """Apply migrations to all tenant databases using SQLAlchemy metadata"""
    from app.super_admin.models import Hospital
    from sqlalchemy import create_engine, inspect
    from app.extensions import db as _db
    import traceback
    
    # Get all hospitals from central database
    hospitals = Hospital.query.all()
    
    if not hospitals:
        click.echo("❌ No hospitals found in central database")
        return
    
    click.echo(f"Found {len(hospitals)} hospitals to migrate")
    
    # Backup original SQLALCHEMY_DATABASE_URI
    original_uri = current_app.config['SQLALCHEMY_DATABASE_URI']
    
    for hospital in hospitals:
        try:
            click.echo(f"\nMigrating tenant: {hospital.name} ({hospital.subdomain})")
            
            # Create engine for tenant database
            engine = create_engine(hospital.db_uri)
            
            # Check if database exists and is accessible
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            # Get current tables in tenant database
            inspector = inspect(engine)
            existing_tables = set(inspector.get_table_names())
            
            # Get all tables defined in our models
            metadata = _db.metadata
            expected_tables = set(metadata.tables.keys())
            
            # Find missing tables
            missing_tables = expected_tables - existing_tables
            
            if missing_tables:
                click.echo(f"  - Creating {len(missing_tables)} missing tables")
                # Create missing tables
                metadata.create_all(bind=engine, tables=[
                    metadata.tables[table] for table in missing_tables
                ])
            
            # Find existing tables that need migration
            # Find existing tables that need migration
            for table_name in existing_tables & expected_tables:
                table = metadata.tables[table_name]
                # Compare columns
                existing_columns = {c['name'] for c in inspector.get_columns(table_name)}
                expected_columns = {c.name for c in table.columns}
                
                # 1. Add missing columns
                missing_columns = expected_columns - existing_columns
                if missing_columns:
                    click.echo(f"  - Adding {len(missing_columns)} columns to {table_name}")
                    with engine.begin() as connection:
                        for column_name in missing_columns:
                            column = table.columns[column_name]
                            alter_stmt = text(f"ALTER TABLE {table_name} ADD COLUMN {column.name} {column.type}")
                            connection.execute(alter_stmt)

                # 2. Drop extra columns
                # 2. Drop extra columns
                extra_columns = existing_columns - expected_columns
                if extra_columns:
                    click.echo(f"  - Dropping {len(extra_columns)} columns from {table_name}")
                    with engine.begin() as connection:
                        for column_name in extra_columns:
                            # 2a. Drop foreign key constraints referencing this column
                            fks = inspector.get_foreign_keys(table_name)
                            for fk in fks:
                                if column_name in fk.get("constrained_columns", []):
                                    fk_name = fk["name"]
                                    click.echo(f"    - Dropping foreign key {fk_name} on {table_name}.{column_name}")
                                    connection.execute(text(f"ALTER TABLE {table_name} DROP FOREIGN KEY {fk_name}"))

                            # 2b. Now safe to drop column
                            alter_stmt = text(f"ALTER TABLE {table_name} DROP COLUMN {column_name}")
                            connection.execute(alter_stmt)


            
            click.echo(f"✅ Successfully migrated {hospital.name}")
            
        except Exception as e:
            click.echo(f"❌ Error migrating {hospital.name}: {str(e)}")
            click.echo(traceback.format_exc())
    
    # Restore original configuration
    current_app.config['SQLALCHEMY_DATABASE_URI'] = original_uri
    click.echo("\n✅ All tenant migrations complete")

# --- Registering Commands ---
def register_commands(app):
    """Attach custom CLI commands to the Flask app."""
    app.cli.add_command(migrate_tenants)  # Add this line
    app.cli.add_command(seed_all_tenants)  # Add this line
    app.cli.add_command(seed_privileges)
    app.cli.add_command(init_db)
    app.cli.add_command(drop_db)
    app.cli.add_command(create_admin)
    app.cli.add_command(seed_departments_command)
    app.cli.add_command(seed_services_command)  # Add this line