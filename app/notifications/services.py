from datetime import datetime, timedelta

from flask import current_app, request
from flask_socketio import emit
from app.auth.models import User
from app.notifications.models import Notification, NotificationRead
from app.extensions import db
from app.extensions import socketio


class NotificationService:

    @staticmethod
    def send_notification(title, message, recipient_type, recipient_id=None, 
                          notification_type='info', icon='bell', action_url=None, 
                          expires_in=24, sender_id=None):
        """
        Send notification to users
        recipient_type: 'user', 'department', 'all'
        """
        
        # Create notification
        notification = Notification(
            title=title,
            message=message,
            type=notification_type,
            icon=icon,
            action_url=action_url,
            sender_id=sender_id,
            expires_at=datetime.utcnow() + timedelta(hours=expires_in)
        )
        
        if recipient_type == 'user':
            notification.user_id = recipient_id
        elif recipient_type == 'department':
            notification.department_id = recipient_id
        else:
            notification.is_broadcast = True
            
        db.session.add(notification)
        db.session.flush()  # Get ID before commit
        
        # Determine recipients
        recipients = []
        if recipient_type == 'user':
            recipients = [User.query.get(recipient_id)]
        elif recipient_type == 'department':
            recipients = User.query.filter_by(department_id=recipient_id).all()
        else:  # broadcast
            recipients = User.query.all()
        
        # Create read records
        for user in recipients:
            read_record = NotificationRead(
                user_id=user.id,
                notification_id=notification.id
            )
            db.session.add(read_record)
        
        db.session.commit()
        

        
        if recipient_type == 'user':
            current_app.logger.debug(f"Targeting user room: {recipient_id}")
        elif recipient_type == 'department':
            current_app.logger.debug(f"Targeting department room: department_{recipient_id}")
            current_app.logger.debug(f"Department recipients: {[u.id for u in recipients]}")
        # Prepare notification data
        notification_data = {
            'id': notification.id,
            'title': title,
            'message': message,
            'icon': icon,
            'type': notification_type,
            'action_url': action_url,
            'created_at': notification.created_at.isoformat(),
            'sender_id': sender_id,
            'sender_name': User.query.get(sender_id).username if sender_id else 'System',

        }

        
        try:
            if recipient_type == 'user':
                socketio.emit('new_notification', notification_data, 
                             room=f"user_{recipient_id}", namespace='/')
                current_app.logger.debug(f"Emitted to user_{recipient_id}")
                
                # Send test event to same room
                socketio.emit('test_event', {
                    'test': 'USER_ROOM_TEST',
                    'room': f"user_{recipient_id}",
                    'user_id': recipient_id
                }, room=f"user_{recipient_id}", namespace='/')
                
            elif recipient_type == 'department':
                socketio.emit('new_notification', notification_data, 
                             room=f"department_{recipient_id}", namespace='/')
                current_app.logger.debug(f"Emitted to department_{recipient_id}")
                
                # Send test event to same room
                socketio.emit('test_event', {
                    'test': 'DEPT_ROOM_TEST',
                    'room': f"department_{recipient_id}",
                    'dept_id': recipient_id
                }, room=f"department_{recipient_id}", namespace='/')
                
            else:  # broadcast
                socketio.emit('new_notification', notification_data, namespace='/')
                current_app.logger.debug("Broadcasted notification")
                
            return notification
            
        except Exception as e:
            current_app.logger.error(f"Notification emit failed: {str(e)}")
            
            # Add detailed error information
            current_app.logger.error(f"Recipient type: {recipient_type}, ID: {recipient_id}")
            current_app.logger.error(f"Notification data: {notification_data}")
            
            # Attempt to send error to client
            try:
                emit('notification_error', {
                    'error': str(e),
                    'recipient': recipient_id,
                    'type': recipient_type
                }, room=request.sid)
            except:
                pass
            
            return None