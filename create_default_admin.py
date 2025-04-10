# File: create_default_admin.py

from app import app, db  # Import app và db từ module chính
from models import User  # Import model User

def create_default_admin():
    target_email = 'admin@dragon.com'
    target_password = 'admin123'
    # Có thể đặt username trùng với email cho nhất quán
    # Hoặc đặt là 'admin' nếu bạn muốn và chắc chắn logic login tìm cả hai
    target_username = target_email

    with app.app_context():
        # Kiểm tra lại lần cuối xem user đã tồn tại chưa (dựa trên email hoặc username)
        # Xóa đi nếu bạn muốn đảm bảo chỉ có 1 bản ghi mới nhất theo script
        existing_user_by_email = User.query.filter_by(email=target_email).first()
        if existing_user_by_email:
            print(f"Tìm thấy user hiện có với email {target_email}. Đang xóa...")
            db.session.delete(existing_user_by_email)
            db.session.commit() # Commit việc xóa

        existing_user_by_username = User.query.filter_by(username=target_username).first()
        if existing_user_by_username:
            print(f"Tìm thấy user hiện có với username {target_username}. Đang xóa...")
            db.session.delete(existing_user_by_username)
            db.session.commit() # Commit việc xóa


        # Tạo admin mới như bạn muốn
        print(f"Đang tạo người dùng mới với Email/Username: {target_email}...")
        new_admin = User(
            # Sử dụng email làm username luôn cho đơn giản khi đăng nhập
            username=target_username,
            email=target_email,
            first_name='Admin',
            last_name='User',
            is_admin=True,
            is_staff=True
        )
        # Đặt mật khẩu
        new_admin.set_password(target_password)

        # Lưu vào DB
        db.session.add(new_admin)
        try:
            db.session.commit()
            print("-" * 30)
            print(">>> Đã tạo tài khoản admin mới thành công! <<<")
            print(f"   Email đăng nhập: {target_email}")
            print(f"   Mật khẩu: {target_password}")
            print("-" * 30)
        except Exception as e:
            db.session.rollback() # Hoàn tác nếu có lỗi
            print(f"Lỗi khi tạo người dùng admin: {e}")
            print("!!! Vui lòng kiểm tra lại CSDL hoặc lỗi phía trên. !!!")


if __name__ == '__main__':
    create_default_admin()