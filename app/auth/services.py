from flask import current_app, g
from flask_jwt_extended import create_access_token, create_refresh_token
from datetime import timedelta, datetime # Import timedelta for token expiry
from app.extensions import db # Import db extension
from app.auth.models import User, Role, Permission # Import auth models
# from app.utils.enums import UserStatus # Example if using enums for status

class AuthService:
    """Business logic for Authentication and core User management."""

    @staticmethod
    def authenticate_user(username, password):
        user = User.query.filter_by(username=username).first()
        if user and user.is_active and user.check_password(password):
            return user
        return None

    @staticmethod
    def create_new_user(username, email, password, role_name='Patient'):
        """Creates a new user with a specified role."""
        if User.query.filter_by(username=username).first():
            raise ValueError("Username already exists")
        if User.query.filter_by(email=email).first():
            raise ValueError("Email already exists")

        role = Role.query.filter_by(name=role_name).first()
        if not role:
            # If the role doesn't exist, raise an error or assign a default fallback
             print(f"Warning: Role '{role_name}' not found. Assigning default role.")
             role = Role.query.filter_by(default=True).first()
             if not role:
                  raise RuntimeError("Default role not found. Cannot create user.")


        user = User(username=username, email=email)
        user.password = password # Use the setter to hash the password
        user.roles.append(role) # Assign the role

        db.session.add(user)
        db.session.commit()
        return user

    @staticmethod
    def generate_tokens(user):
        """Generates JWT access and refresh tokens for a user."""
        # The identity should contain minimal, non-sensitive data needed to identify the user
        # The user ID is usually sufficient.
        identity = {'id': user.id}

        # Configure token lifetimes (e.g., 15 minutes access, 30 days refresh)
        access_token_expires = timedelta(minutes=15)
        refresh_token_expires = timedelta(days=30)

        access_token = create_access_token(
            identity=identity,
            expires_delta=access_token_expires,
            # Optional: Add custom claims if needed (e.g., user roles, permissions)
            # additional_claims={'roles': [r.name for r in user.roles]}
        )
        refresh_token = create_refresh_token(
            identity=identity,
            expires_delta=refresh_token_expires
        )

        return access_token, refresh_token

    # Add more service methods for:
    # - Password reset (request, verify token, set new password)
    # - Email confirmation
    # - User activation/deactivation
    # - Assigning/removing roles
    # - Fetching user details (potentially including related patient/staff profiles)