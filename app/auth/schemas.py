from app.extensions import ma # Import Marshmallow instance
from marshmallow import fields, validate
# from marshmallow_sqlalchemy import SQLAlchemyAutoSchema # If you want to autogenerate schemas from models

# Example schema for Role (needed for User schema if you nest it)
class RoleSchema(ma.Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(required=True)

# Example schema for User data serialization/deserialization
class UserSchema(ma.Schema):
    id = fields.Int(dump_only=True)
    username = fields.Str(required=True, validate=validate.Length(min=4))
    email = fields.Email(required=True)
    is_active = fields.Bool(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    # Add role information (nested schema)
    roles = fields.Nested(RoleSchema, many=True, dump_only=True) # many=True because a user can have multiple roles

    class Meta:
        # Optional: Fields to exclude by default
        # exclude = ('password_hash',)
        pass


# Schema for incoming login requests (only includes necessary fields)
class LoginSchema(ma.Schema):
    username = fields.Str(required=True)
    password = fields.Str(required=True, load_only=True) # load_only=True means password is for loading input, not included in output


# Schema for API login response (includes tokens)
class TokenSchema(ma.Schema):
    access_token = fields.Str(dump_only=True)
    refresh_token = fields.Str(dump_only=True)
    # Optional: Include user details in the login response
    # user = fields.Nested(UserSchema, dump_only=True)