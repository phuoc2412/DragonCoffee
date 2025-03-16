
from app import db
from models import User

def create_default_admin():
    # Check if admin exists
    admin = User.query.filter_by(email='admin@dragon.com').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@dragon.com',
            first_name='Admin',
            last_name='User',
            is_admin=True,
            is_staff=True
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("Default admin account created!")
    else:
        print("Admin account already exists!")

if __name__ == '__main__':
    create_default_admin()
