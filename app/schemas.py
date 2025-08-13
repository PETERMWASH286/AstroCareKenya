# This file is optional if all schemas are defined within their respective blueprints.
# You could put a common base schema class or shared schema components here.

# Example of a base schema (requires `ma` from extensions)
# from marshmallow import Schema, fields
# class BaseSchema(Schema):
#     id = fields.Int(dump_only=True)
#     created_at = fields.DateTime(dump_only=True)
#     updated_at = fields.DateTime(dump_only=True)

# Most schemas will likely live in app/<module>/schemas.py or app/api/vX/<module>/schemas.py
pass