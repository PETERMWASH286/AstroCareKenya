from celery import Celery
from flask import current_app
from app.appointments.models import Appointment
from app.extensions import db
from app.notifications.models import PatientSMSLog, SMSBroadcast
from app.notifications.sms_services import send_sms
from datetime import datetime, timedelta, timezone

from app.patients.models import Patient

# Create Celery instance
celery = Celery(__name__)


# Helper functions
def get_patients_by_group(group_id):
    if group_id == 'all':
        return Patient.query.all()
    elif group_id == 'appointments':
        return Patient.query.join(Appointment).filter(
            Appointment.status == 'scheduled',
            Appointment.scheduled_for > datetime.utcnow()
        ).distinct().all()
    elif group_id == 'new_patients':
        return Patient.query.filter(
            Patient.created_at > datetime.utcnow() - timedelta(days=30)
        ).all()
    return []

def get_patients_by_ids(patient_ids):
    return Patient.query.filter(Patient.id.in_(patient_ids)).all()

@celery.task
def queue_sms_broadcast(broadcast_id):
    try:
        with current_app.app_context():
            # First log the broadcast ID
            current_app.logger.info(f"Processing broadcast_id: {broadcast_id}")
            
            # Get broadcast from DB
            broadcast = SMSBroadcast.query.get(broadcast_id)
            if not broadcast:
                current_app.logger.error(f"Broadcast {broadcast_id} not found")
                return
                
            current_app.logger.info(
                f"Broadcast {broadcast.id} status: {broadcast.status}, "
                f"scheduled: {broadcast.scheduled_time}"
            )
            
            # IMMEDIATE EXECUTION FOR PAST SCHEDULES
            if broadcast.status == 'scheduled' and broadcast.scheduled_time < datetime.utcnow():
                current_app.logger.warning(
                    f"Executing PAST scheduled broadcast {broadcast.id} "
                    f"(scheduled: {broadcast.scheduled_time}, now: {datetime.utcnow()})"
                )
                send_sms_broadcast(broadcast.id)
                return
                
            # NORMAL EXECUTION FLOW
            if broadcast.status == 'pending' or (broadcast.status == 'scheduled' and broadcast.scheduled_time <= datetime.utcnow()):
                send_sms_broadcast(broadcast.id)
            elif broadcast.status == 'scheduled':
                # Calculate delay in seconds
                delay = (broadcast.scheduled_time - datetime.utcnow()).total_seconds()
                current_app.logger.info(
                    f"Rescheduling broadcast {broadcast.id} in "
                    f"{delay:.0f} seconds ({broadcast.scheduled_time})"
                )
                # Reschedule with countdown
                queue_sms_broadcast.apply_async(
                    args=[broadcast_id], 
                    countdown=delay
                )
            else:
                current_app.logger.warning(
                    f"Ignoring broadcast {broadcast.id} with status: {broadcast.status}"
                )
    except Exception as e:
        current_app.logger.exception(f"Error in queue_sms_broadcast: {str(e)}")
        
def send_sms_broadcast(broadcast_id):
    if not broadcast_id:  # Add null check
        current_app.logger.error("Null broadcast_id received")
        return
    try:
        with current_app.app_context():
            broadcast = SMSBroadcast.query.get(broadcast_id)
            if not broadcast:
                current_app.logger.error(f"Broadcast {broadcast_id} not found")
                return
            
            current_app.logger.info(f"Processing broadcast {broadcast_id} - {broadcast.message[:30]}...")
            
            # Update status to processing
            broadcast.status = 'processing'
            db.session.commit()
            current_app.logger.info("Status updated to 'processing'")
            
            # Get patients
            if broadcast.recipient_type == 'group':
                patients = get_patients_by_group(broadcast.group_id)
            else:
                patients = get_patients_by_ids(broadcast.patient_ids)
            
            current_app.logger.info(f"Found {len(patients)} recipients")
            
            # Prepare data for sending
            phone_numbers = [p.phone for p in patients]
            
            # Send SMS
            current_app.logger.info("Sending SMS...")
            result = send_sms(phone_numbers, broadcast.message)
            
            # Log results
            if result['success']:
                current_app.logger.info(f"SMS sent successfully to {len(result['response']['SMSMessageData']['Recipients'])} recipients")
                
                # ... rest of logging code ...
                
                broadcast.status = 'completed'
                broadcast.sent_at = datetime.utcnow()
            else:
                current_app.logger.error(f"SMS broadcast failed: {result.get('error', 'Unknown error')}")
                broadcast.status = 'failed'
            
            db.session.commit()
            current_app.logger.info(f"Status updated to '{broadcast.status}'")
            
    except Exception as e:
        current_app.logger.exception(f"Exception in send_sms_broadcast: {str(e)}")
        try:
            db.session.rollback()
            broadcast.status = 'failed'
            db.session.commit()
        except:
            current_app.logger.error("Failed to update status to 'failed'")