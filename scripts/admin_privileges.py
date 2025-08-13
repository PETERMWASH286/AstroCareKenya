from app.extensions import db
from app.auth.models import Role
from app.user_management.models import Privilege

# 1. Load the Admin role
admin = Role.query.filter_by(name='Admin').first()

# 2. Load all privileges
all_privs = Privilege.query.all()

# 3. Assign any missing ones
for p in all_privs:
    if p not in admin.privileges:
        admin.privileges.append(p)

# 4. Commit
db.session.commit()

print(f"Assigned {len(all_privs)} privileges to Admin.")
