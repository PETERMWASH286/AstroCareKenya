from app.extensions import ma
from marshmallow import fields, validate

# Schema for incoming login requests (used in routes.py)
class LoginSchema(ma.Schema):
    username = fields.Str(required=True, validate=validate.Length(min=1)) # Basic validation
    password = fields.Str(required=True, load_only=True) # password is load_only

# Schema for outgoing token responses (used in routes.py)
class TokenSchema(ma.Schema):
    access_token = fields.Str(dump_only=True)
    refresh_token = fields.Str(dump_only=True)
    # Optional: Include a nested user schema if you return user details on login
    # user = fields.Nested('UserSchema', dump_only=True) # Forward reference to UserSchema