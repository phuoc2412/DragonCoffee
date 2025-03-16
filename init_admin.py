
from app import db, app
from models import User

def create_default_admin():
    with app.app_context():
        # Xóa admin cũ nếu tồn tại
        admin = User.query.filter_by(email='admin@dragon.com').first()
        if admin:
            db.session.delete(admin)
            db.session.commit()
            print("Đã xóa tài khoản admin cũ")
        
        # Tạo admin mới
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
        print("Đã tạo tài khoản admin mới!")
        print("Email: admin@dragon.com")
        print("Password: admin123")

if __name__ == '__main__':
    create_default_admin()
