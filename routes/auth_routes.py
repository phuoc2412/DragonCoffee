# /DragonCoffee/routes/auth_routes.py

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse
from models import User, Order, db
from forms import LoginForm, RegistrationForm, UpdateProfileForm, ForgotPasswordForm, ResetPasswordForm
from app import db # Hoặc import trực tiếp từ app.py nếu cần

try:
    from utils import send_reset_email, save_avatar_file, delete_avatar_file
except ImportError:
     raise ImportError("Could not import required functions from utils.")

auth_bp = Blueprint('auth', __name__)

# ==================== AUTHENTICATION ROUTES ====================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin or current_user.is_staff:
             return redirect(url_for('admin.dashboard'))
        return redirect(url_for('main.index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter(User.email.ilike(form.email.data)).first()

        if user is None or not user.check_password(form.password.data):
            flash('Email hoặc mật khẩu không hợp lệ.', 'danger')
            return redirect(url_for('auth.login'))

        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')

        if not next_page or urlparse(next_page).netloc != '':
            if user.is_admin or user.is_staff:
                next_page = url_for('admin.dashboard')
            else:
                next_page = url_for('main.index')
        flash('Đăng nhập thành công.', 'success')
        return redirect(next_page)
    return render_template('login.html', title='Đăng nhập', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Bạn đã đăng xuất.', 'info')
    return redirect(url_for('main.index'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        if current_user.is_admin or current_user.is_staff:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('main.index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data.lower(),
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            phone=form.phone.data
        )
        user.set_password(form.password.data)
        try:
            db.session.add(user)
            db.session.commit()
            flash('Đăng ký thành công! Bây giờ bạn có thể đăng nhập.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Lỗi khi đăng ký: {e}', 'danger')
            current_app.logger.error(f"Lỗi đăng ký user: {e}", exc_info=True)
    return render_template('register.html', title='Đăng ký', form=form)


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter(User.email.ilike(form.email.data)).first()
        if user:
            if send_reset_email(user):
                flash('Một email hướng dẫn đặt lại mật khẩu đã được gửi đến địa chỉ email của bạn.', 'info')
            else:
                flash('Lỗi khi gửi email. Vui lòng thử lại sau hoặc liên hệ hỗ trợ.', 'danger')
            return redirect(url_for('auth.login'))
        else:
            flash('Nếu địa chỉ email của bạn tồn tại trong hệ thống, bạn sẽ nhận được email hướng dẫn đặt lại mật khẩu.', 'info')
            return redirect(url_for('auth.login'))
    return render_template('forgot_password.html', title='Quên Mật Khẩu', form=form)


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    user = User.verify_reset_token(token)
    if user is None:
        flash('Link đặt lại mật khẩu không hợp lệ hoặc đã hết hạn.', 'warning')
        return redirect(url_for('auth.forgot_password'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        try:
            db.session.commit()
            flash('Mật khẩu của bạn đã được cập nhật thành công! Bây giờ bạn có thể đăng nhập.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Lỗi khi cập nhật mật khẩu: {e}', 'danger')
            current_app.logger.error(f"Lỗi reset password cho user ID {user.id}: {e}", exc_info=True)
    return render_template('reset_password.html', title='Đặt Lại Mật Khẩu', form=form, token=token)


# ==================== PROFILE ROUTES ====================

# ----- Route hiển thị Profile (Chỉ GET) -----
@auth_bp.route('/profile')
@login_required
def profile():
    """Hiển thị trang hồ sơ người dùng."""
    recent_orders = []
    try:
        recent_orders = Order.query.filter_by(user_id=current_user.id)\
                                   .order_by(Order.created_at.desc())\
                                   .limit(5).all()
    except Exception as e:
        flash(f'Lỗi khi tải lịch sử đơn hàng: {e}', 'warning')
        current_app.logger.error(f"Error fetching recent orders for user {current_user.id}: {e}")

    # === BỎ format_currency=format_currency ở đây ===
    return render_template('profile.html',
                           title='Hồ sơ của bạn',
                           user=current_user,
                           recent_orders=recent_orders)
                           # BỎ dòng format_currency=format_currency ở trên

# ----- Route chỉnh sửa Profile (GET để hiện form, POST để xử lý) -----
@auth_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Trang chỉnh sửa hồ sơ người dùng, xử lý cả file upload."""
    # Khởi tạo form (giữ nguyên)
    form = UpdateProfileForm(
        original_username=current_user.username,
        original_email=current_user.email,
        obj=current_user
    )

    if form.validate_on_submit():
        # Logic xử lý POST (giữ nguyên)
        logger = current_app.logger
        old_avatar_relative_path = current_user.avatar_url
        new_avatar_relative_path = None
        avatar_updated = False
        try:
            avatar_file = form.avatar.data
            if avatar_file:
                saved_path = save_avatar_file(avatar_file)
                if saved_path:
                    new_avatar_relative_path = saved_path
                    avatar_updated = True
                    current_user.avatar_url = new_avatar_relative_path
            current_user.username = form.username.data
            current_user.email = form.email.data.lower()
            current_user.first_name = form.first_name.data
            current_user.last_name = form.last_name.data
            current_user.phone = form.phone.data
            current_user.address = form.address.data
            if form.password.data:
                current_user.set_password(form.password.data)
            db.session.commit()
            flash('Hồ sơ của bạn đã được cập nhật!', 'success')
            if avatar_updated and old_avatar_relative_path:
                delete_avatar_file(old_avatar_relative_path)
            return redirect(url_for('auth.profile'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating profile user ID {current_user.id}: {e}", exc_info=True)
            flash(f'Lỗi khi cập nhật hồ sơ: {str(e)}', 'danger')
            if new_avatar_relative_path:
                 delete_avatar_file(new_avatar_relative_path)

    # Xử lý GET request (vẫn chỉ truyền form)
    return render_template('edit_profile.html',
                           title='Chỉnh sửa hồ sơ',
                           form=form) # <-- Không cần truyền format_currency vào trang edit form