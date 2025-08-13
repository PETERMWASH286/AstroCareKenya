from flask import current_app, request, session
from flask_login import current_user, user_loaded_from_request
from flask_socketio import join_room, leave_room, emit
from app.extensions import socketio

# Add this to handle user loading in Socket.IO context
@user_loaded_from_request.connect
def load_user_from_request(app, user=None):
    return current_user


# Track joined rooms for debugging
user_rooms = {}

@socketio.on('connect', namespace='/')
def handle_connect():
    """Handle new socket connections"""
    try:
        if current_user.is_authenticated:
            user_id = current_user.id
            room_name = f"user_{user_id}"
            join_room(room_name)
            user_rooms[request.sid] = [room_name]
            
            # Confirm room join to client
            emit('room_joined', {
                'room': room_name,
                'sid': request.sid,
                'user_id': user_id
            }, room=request.sid)
            
            current_app.logger.info(f"User {user_id} connected. Rooms: {user_rooms[request.sid]}")
        else:
            current_app.logger.warning("Unauthenticated connection attempt")
            return False
    except Exception as e:
        current_app.logger.error(f"Connection error: {str(e)}")
        return False

@socketio.on('disconnect', namespace='/')
def handle_disconnect():
    """Handle socket disconnections"""
    try:
        if current_user.is_authenticated:
            user_id = current_user.id
            if request.sid in user_rooms:
                for room in user_rooms[request.sid]:
                    leave_room(room)
                del user_rooms[request.sid]
            current_app.logger.info(f"User {user_id} disconnected")
    except Exception as e:
        current_app.logger.error(f"Disconnect error: {str(e)}")

@socketio.on('join_department', namespace='/')
def handle_join_department(department_id):
    """Join a department notification room"""
    try:
        if current_user.is_authenticated:
            user_id = current_user.id
            room_name = f"department_{department_id}"
            join_room(room_name)
            
            # Track joined rooms
            if request.sid not in user_rooms:
                user_rooms[request.sid] = []
            user_rooms[request.sid].append(room_name)
            
            # Confirm room join to client
            emit('room_joined', {
                'room': room_name,
                'department_id': department_id,
                'user_id': user_id
            }, room=request.sid)
            
            current_app.logger.info(f"User {user_id} joined department room: {room_name}. All rooms: {user_rooms[request.sid]}")
    except Exception as e:
        current_app.logger.error(f"Join department error: {str(e)}")

# Add this new event for room debugging
@socketio.on('get_rooms', namespace='/')
def handle_get_rooms():
    """Return current rooms for debugging"""
    if request.sid in user_rooms:
        emit('current_rooms', {
            'sid': request.sid,
            'rooms': user_rooms[request.sid]
        }, room=request.sid)

@socketio.on('join_user_room', namespace='/')
def handle_join_user_room():
    if current_user.is_authenticated:
        user_id = current_user.id
        room_name = f"user_{user_id}"
        join_room(room_name)
        
        # Track joined rooms
        if request.sid not in user_rooms:
            user_rooms[request.sid] = []
        if room_name not in user_rooms[request.sid]:
            user_rooms[request.sid].append(room_name)
        
        # Confirm room join to client
        emit('room_joined', {
            'room': room_name,
            'user_id': user_id,
            'sid': request.sid
        }, room=request.sid)
        
        current_app.logger.info(f"User {user_id} joined personal room: {room_name}")
        current_app.logger.debug(f"All rooms for SID {request.sid}: {user_rooms[request.sid]}")
@socketio.on('leave_department', namespace='/')
def handle_leave_department(department_id):
    """Leave a department notification room"""
    if current_user.is_authenticated:
        leave_room(f"department_{department_id}")
        print(f"User {current_user.id} left department {department_id}")