
from app import db, app
from models import User

def create_default_admin():
    with app.app_context():
        # Check if admin exists
        admin = User.query.filter_by(email='admin@dragon.com').first()
        
        # Delete existing admin if exists
        if admin:
            db.session.delete(admin)
            db.session.commit()
            print("Existing admin account deleted")
            
        # Create new admin
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
        print("New admin account created!")

if __name__ == '__main__':
    create_default_admin()
