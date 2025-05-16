# /DragonCoffee/routes/auth_routes.py

# THÊM jsonify VÀO ĐÂY
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse
from models import User, Order, db # db được import từ models, nơi db đã được gán từ app
from forms import LoginForm, RegistrationForm, UpdateProfileForm, ForgotPasswordForm, ResetPasswordForm

# Đảm bảo db được import một cách nhất quán (nếu không dùng factory pattern,
# import db từ models nơi nó đã được import từ app có thể ổn)
# from app import db # Hoặc cách này nếu bạn thấy an toàn hơn

try:
    from utils import send_reset_email, save_avatar_file, delete_avatar_file
except ImportError:
     current_app.logger.critical("CRITICAL: Failed to import utils in auth_routes.", exc_info=True)
     # Định nghĩa hàm placeholder để tránh crash khi gọi
     def send_reset_email(*args, **kwargs): raise NotImplementedError("send_reset_email is unavailable")
     def save_avatar_file(*args, **kwargs): raise NotImplementedError("save_avatar_file is unavailable")
     def delete_avatar_file(*args, **kwargs): raise NotImplementedError("delete_avatar_file is unavailable")

auth_bp = Blueprint('auth', __name__)

# ==================== AUTHENTICATION ROUTES ====================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET' and current_user.is_authenticated:
        # Redirect user đã login nếu họ truy cập trang login trực tiếp
        if current_user.is_admin or current_user.is_staff:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('main.index'))

    # Dùng riêng form cho POST để validate dữ liệu mới gửi lên
    if request.method == 'POST':
        form = LoginForm(request.form) # Tạo form từ dữ liệu POST
        if form.validate(): # validate() thay vì validate_on_submit() khi dùng AJAX POST thuần
            user = User.query.filter(User.email.ilike(form.email.data)).first()

            if user is None or not user.check_password(form.password.data):
                 return jsonify({'success': False, 'message': 'Email hoặc mật khẩu không hợp lệ.'}), 401 # Lỗi xác thực

            login_user(user, remember=form.remember_me.data)

            # Xác định URL redirect
            next_page_url = url_for('main.index') # Mặc định
            if user.is_admin or user.is_staff:
                 next_page_url = url_for('admin.dashboard')

            # Bạn có thể kiểm tra 'next' query param nếu muốn
            # next_page_arg = request.args.get('next')
            # if next_page_arg and urlparse(next_page_arg).netloc == '': # Kiểm tra an toàn
            #     next_page_url = next_page_arg

            return jsonify({'success': True, 'redirect': next_page_url})
        else:
            # Lỗi validation form
             return jsonify({'success': False, 'errors': form.errors}), 400

    # Xử lý GET request (Nếu truy cập trực tiếp và chưa login, redirect về home để họ click vào nút login mở modal)
    return redirect(url_for('main.index'))

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Bạn đã đăng xuất.', 'info')
    return redirect(url_for('main.index'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET' and current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        form = RegistrationForm(request.form)
        if form.validate():
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
                # Tùy chọn: Tự động đăng nhập user sau khi đăng ký
                # login_user(user)
                # flash('Đăng ký và đăng nhập thành công!', 'success')
                return jsonify({
                    'success': True,
                    'message': 'Đăng ký thành công! Vui lòng đăng nhập.', # Thay đổi message
                    'redirect': None # Không cần redirect, yêu cầu user đăng nhập
                    #'redirect': url_for('main.index') # Hoặc redirect nếu bạn auto-login
                })
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Lỗi đăng ký user: {e}", exc_info=True)
                return jsonify({'success': False, 'message': f'Lỗi khi đăng ký. Vui lòng thử lại.'}), 500
        else:
            return jsonify({'success': False, 'errors': form.errors}), 400

    # GET request: redirect về home
    return redirect(url_for('main.index'))


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
        else:
            # Vẫn hiển thị thông báo chung để tránh tiết lộ email nào tồn tại
            flash('Nếu địa chỉ email của bạn tồn tại trong hệ thống, bạn sẽ nhận được email hướng dẫn.', 'info')
        # Luôn redirect về login sau khi xử lý, ngay cả khi không tìm thấy user hoặc gửi email lỗi
        # Tránh việc user submit lại form liên tục.
        return redirect(url_for('auth.login')) # Hoặc quay lại trang chính main.index
    # Template này là trang riêng, không phải modal
    return render_template('forgot_password.html', title='Quên Mật Khẩu', form=form)


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    user = User.verify_reset_token(token)
    if user is None:
        flash('Link đặt lại mật khẩu không hợp lệ hoặc đã hết hạn.', 'warning')
        return redirect(url_for('auth.forgot_password')) # Về trang forgot password
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        try:
            db.session.commit()
            flash('Mật khẩu của bạn đã được cập nhật! Bây giờ bạn có thể đăng nhập.', 'success')
            # Chuyển về trang login để người dùng nhập mật khẩu mới
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Lỗi khi cập nhật mật khẩu.', 'danger') # Giấu chi tiết lỗi
            current_app.logger.error(f"Lỗi reset password cho user ID {user.id}: {e}", exc_info=True)
    # Template này cũng là trang riêng
    return render_template('reset_password.html', title='Đặt Lại Mật Khẩu', form=form, token=token)

# ==================== PROFILE ROUTES (GIỮ NGUYÊN) ====================
@auth_bp.route('/profile')
@login_required
def profile():
    recent_orders = []
    try:
        recent_orders = Order.query.filter_by(user_id=current_user.id)\
                                   .order_by(Order.created_at.desc())\
                                   .limit(5).all()
    except Exception as e:
        flash(f'Lỗi khi tải lịch sử đơn hàng: {e}', 'warning')
        current_app.logger.error(f"Error fetching recent orders for user {current_user.id}: {e}")
    # Format currency bây giờ được inject toàn cục qua context processor
    return render_template('profile.html',
                           title='Hồ sơ của bạn',
                           user=current_user,
                           recent_orders=recent_orders)


@auth_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = UpdateProfileForm(
        original_username=current_user.username,
        original_email=current_user.email,
        obj=current_user
    )
    if form.validate_on_submit():
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
            current_user.username = form.username.data
            current_user.email = form.email.data.lower()
            current_user.first_name = form.first_name.data
            current_user.last_name = form.last_name.data
            current_user.phone = form.phone.data
            current_user.address = form.address.data
            if form.password.data:
                current_user.set_password(form.password.data)
            if avatar_updated: # Chỉ cập nhật avatar_url nếu có ảnh mới được lưu thành công
                current_user.avatar_url = new_avatar_relative_path

            db.session.commit()
            flash('Hồ sơ của bạn đã được cập nhật!', 'success')
            # Chỉ xóa ảnh cũ nếu có ảnh mới và ảnh cũ không phải là default
            if avatar_updated and old_avatar_relative_path and 'default_' not in old_avatar_relative_path:
                 delete_avatar_file(old_avatar_relative_path)
            return redirect(url_for('auth.profile'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating profile user ID {current_user.id}: {e}", exc_info=True)
            flash(f'Lỗi khi cập nhật hồ sơ. Vui lòng thử lại.', 'danger') # Giấu chi tiết lỗi
            # Xóa ảnh mới đã upload nếu có lỗi xảy ra sau khi lưu ảnh
            if new_avatar_relative_path:
                 delete_avatar_file(new_avatar_relative_path)

    elif request.method == 'POST':
         # Log lỗi validation nếu có
         current_app.logger.warning(f"Profile edit validation failed for user {current_user.id}: {form.errors}")
         flash('Thông tin cập nhật không hợp lệ. Vui lòng kiểm tra lại các trường.', 'warning')

    # Xử lý GET request (hiển thị form)
    return render_template('edit_profile.html', title='Chỉnh sửa hồ sơ', form=form)