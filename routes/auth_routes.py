# C:\Users\ntanh\Project_Dragon_Coffe\DragonCoffee\routes\auth_routes.py

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app # Thêm current_app import
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse
# Đảm bảo đường dẫn import models và forms là chính xác với cấu trúc dự án của bạn
# Nếu models.py và forms.py nằm trong thư mục app:
# from app.models import User, Order
# from app.forms import LoginForm, RegistrationForm, UpdateProfileForm
# Nếu chúng nằm cùng cấp với routes:
from models import User, Order
from forms import LoginForm, RegistrationForm, UpdateProfileForm
# Nếu db được khởi tạo trong app/__init__.py:
# from app import db, bcrypt
# Nếu db được khởi tạo trong app.py ở thư mục gốc:
from app import db # Giả sử app.py ở thư mục gốc chứa db
# Import bcrypt nếu cần và nó được khởi tạo trong app
# from app import bcrypt


auth_bp = Blueprint('auth', __name__) # Có thể thêm url_prefix='/auth' nếu muốn đăng ký với prefix chung


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        # Nếu đã đăng nhập, chuyển hướng dựa trên vai trò
        if current_user.is_admin:
             return redirect(url_for('admin.dashboard'))
        return redirect(url_for('main.index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first() # Luôn kiểm tra email dạng lowercase

        # Sử dụng check_password từ model User
        if user is None or not user.check_password(form.password.data):
            flash('Email hoặc mật khẩu không hợp lệ.', 'danger')
            return redirect(url_for('auth.login')) # Redirect lại trang login nếu sai

        login_user(user, remember=form.remember_me.data)

        next_page = request.args.get('next')
        # Bảo mật: Kiểm tra next_page để tránh open redirect attacks
        if not next_page or urlparse(next_page).netloc != '':
            if user.is_admin:
                next_page = url_for('admin.dashboard')
            else:
                next_page = url_for('main.index')

        flash('Đăng nhập thành công.', 'success')
        return redirect(next_page)

    return render_template('login.html', title='Đăng nhập', form=form) # Thêm title nếu cần


@auth_bp.route('/logout')
@login_required # Chỉ user đã đăng nhập mới logout được
def logout():
    logout_user()
    flash('Bạn đã đăng xuất.', 'info')
    return redirect(url_for('main.index'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        # Chuyển hướng nếu đã đăng nhập
        if current_user.is_admin:
             return redirect(url_for('admin.dashboard'))
        return redirect(url_for('main.index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data.lower(), # Lưu email dạng lowercase
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            phone=form.phone.data
            # address có thể thêm ở profile hoặc form đăng ký nếu muốn
        )
        # Sử dụng set_password từ model User
        user.set_password(form.password.data)

        try: ### FIXED: Thêm try-except commit
            db.session.add(user)
            db.session.commit()
            flash('Đăng ký thành công! Bây giờ bạn có thể đăng nhập.', 'success')
            # Cân nhắc: có thể tự động login user sau khi đăng ký
            # login_user(user)
            # return redirect(url_for('main.index'))
            return redirect(url_for('auth.login'))
        except Exception as e: ### FIXED: Rollback và logging
            db.session.rollback() # Rollback nếu có lỗi
            flash(f'Lỗi khi đăng ký: {e}', 'danger') # Thông báo lỗi cụ thể (có thể ẩn chi tiết lỗi trong production)
            current_app.logger.error(f"Lỗi đăng ký user: {e}", exc_info=True) # Log lỗi chi tiết

    return render_template('register.html', title='Đăng ký', form=form)


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    # Khởi tạo form UpdateProfileForm, truyền giá trị gốc nếu cần cho validation
    # Giả sử UpdateProfileForm cần original_username và original_email trong __init__
    form = UpdateProfileForm(
        original_username=current_user.username,
        original_email=current_user.email,
        obj=current_user # Load dữ liệu hiện tại vào form cho GET request
    )

    if form.validate_on_submit(): # Chỉ chạy khi method là POST và form hợp lệ
        try: ### FIXED: Thêm try-except commit
            # Cập nhật thông tin user từ form
            current_user.username = form.username.data
            current_user.email = form.email.data.lower() # Cập nhật email dạng lowercase
            current_user.first_name = form.first_name.data
            current_user.last_name = form.last_name.data
            current_user.phone = form.phone.data
            # Giả sử UpdateProfileForm có trường address
            if hasattr(form, 'address'):
                 current_user.address = form.address.data

            # Chỉ cập nhật mật khẩu nếu người dùng nhập vào ô mật khẩu mới (nếu có trong form)
            if hasattr(form, 'password') and form.password.data:
                current_user.set_password(form.password.data)

            db.session.commit()
            flash('Hồ sơ của bạn đã được cập nhật thành công.', 'success')
            # Redirect về chính trang profile sau khi cập nhật
            return redirect(url_for('auth.profile'))
        except Exception as e: ### FIXED: Rollback và logging
            db.session.rollback()
            flash(f'Lỗi khi cập nhật hồ sơ: {e}', 'danger')
            current_app.logger.error(f"Lỗi cập nhật profile user ID {current_user.id}: {e}", exc_info=True)

    # Xử lý cho GET request (hoặc POST không hợp lệ): Hiển thị trang profile

    # Lấy 5 đơn hàng gần nhất (sửa lỗi UndefinedError và giúp template gọn hơn)
    recent_orders = []
    try:
         # Sắp xếp theo Order.created_at giảm dần, giới hạn 5
        recent_orders = Order.query.filter_by(user_id=current_user.id)\
                                   .order_by(Order.created_at.desc())\
                                   .limit(5).all()
    except Exception as e:
        flash(f'Lỗi khi tải lịch sử đơn hàng: {e}', 'warning')


    # Render template profile.html, truyền form và danh sách đơn hàng
    return render_template('profile.html',
                           title='Hồ sơ của bạn',
                           form=form,
                           recent_orders=recent_orders)
                           # Không cần truyền Order=Order nữa nếu template dùng recent_orders


# Route edit_profile có thể được coi là không cần thiết nếu /profile đã xử lý cả GET/POST
# Tuy nhiên, nếu bạn muốn một trang chỉnh sửa riêng biệt, có thể giữ lại và điều chỉnh
@auth_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    # Nên dùng UpdateProfileForm ở đây thay vì RegistrationForm
    # Khởi tạo giống như trong hàm profile
    form = UpdateProfileForm(
        original_username=current_user.username,
        original_email=current_user.email,
        obj=current_user
    )

    if form.validate_on_submit():
        try: ### FIXED: Thêm try-except commit
            current_user.username = form.username.data
            current_user.email = form.email.data.lower()
            current_user.first_name = form.first_name.data
            current_user.last_name = form.last_name.data
            current_user.phone = form.phone.data
            if hasattr(form, 'address'):
                 current_user.address = form.address.data

            # Cập nhật mật khẩu nếu có và nếu người dùng nhập
            if hasattr(form, 'password') and form.password.data:
                 current_user.set_password(form.password.data)

            db.session.commit()
            flash('Hồ sơ của bạn đã được cập nhật!', 'success')
            # Sau khi sửa thành công, quay về trang hiển thị profile chính
            return redirect(url_for('auth.profile'))
        except Exception as e: ### FIXED: Rollback và logging
            db.session.rollback()
            flash(f'Lỗi khi cập nhật hồ sơ: {e}', 'danger')
            current_app.logger.error(f"Lỗi edit profile user ID {current_user.id}: {e}", exc_info=True)


    # Cho GET request, render template 'edit_profile.html'
    return render_template('edit_profile.html',
                           title='Chỉnh sửa hồ sơ',
                           form=form)