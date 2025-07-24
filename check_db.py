from backend.sadeh_core.app import app, db
from backend.db.db.models import User, Role

with app.app_context():
    users = User.query.all()
    roles = Role.query.all()
    
    print("=== Users ===")
    if users:
        for user in users:
            print(f"Username: {user.username}, Email: {user.email}, Roles: {[r.name for r in user.roles]}")
    else:
        print("No users found in database!")
        
    print("\n=== Roles ===")
    if roles:
        for role in roles:
            print(f"Role: {role.name}, Description: {role.description}")
    else:
        print("No roles found in database!")
