# /DragonCoffee/utils.py

import os
import uuid
from datetime import datetime
from functools import wraps
from flask_mail import Message
import logging
from flask import flash, redirect, url_for, render_template, current_app, request
from flask_login import current_user
from werkzeug.utils import secure_filename

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not hasattr(current_user, 'is_admin') or not current_user.is_admin:
            flash('Bạn không có quyền truy cập trang quản trị này.', 'danger')
            login_endpoint = 'admin.login' if current_app.blueprints.get('admin') else 'auth.login'
            next_url = request.url if request else None
            return redirect(url_for(login_endpoint, next=next_url))
        return f(*args, **kwargs)
    return decorated_function

def staff_required(f):
     @wraps(f)
     def decorated_function(*args, **kwargs):
         if not current_user.is_authenticated or \
            not ( (hasattr(current_user, 'is_admin') and current_user.is_admin) or \
                  (hasattr(current_user, 'is_staff') and current_user.is_staff) ):
              flash('Bạn cần có quyền nhân viên hoặc quản trị để truy cập.', 'danger')
              return redirect(url_for('main.index'))
         return f(*args, **kwargs)
     return decorated_function

def generate_order_number():
    timestamp = datetime.utcnow().strftime('%y%m%d%H%M%S')
    random_str = str(uuid.uuid4())[:4]
    return f"ORD-{timestamp}-{random_str}"

def calculate_order_total(items):
    total = 0
    for item in items:
        total += item['price'] * item['quantity']
    return total

def get_order_status_label(status):
    status_labels = {
        'pending': 'badge bg-warning text-dark',
        'processing': 'badge bg-info text-dark',
        'ready_for_pickup': 'badge bg-primary',
        'out_for_delivery': 'badge bg-purple',
        'completed': 'badge bg-success',
        'delivered': 'badge bg-success',
        'cancelled': 'badge bg-danger',
        'failed': 'badge bg-danger'
    }
    return status_labels.get(status, 'badge bg-secondary')

def format_currency(amount):
    if amount is None:
        return "0₫"
    try:
        return f"{int(round(amount)):,}₫".replace(",", ".")
    except (ValueError, TypeError):
        return f"{amount}₫"

def send_reset_email(user, endpoint_name='auth.reset_password'):
    from app import mail
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    token = user.get_reset_token()
    try:
        reset_url = url_for(endpoint_name, token=token, _external=True)
        logger.info(f"Generated reset URL for endpoint '{endpoint_name}': {reset_url}")
        is_admin_flow = endpoint_name == 'admin.reset_password'
        subject = f"[Dragon Coffee] Yêu cầu Đặt lại Mật khẩu {'Quản trị/NV' if is_admin_flow else ''}"
        recipient_email = user.email
        greeting_name = user.username if is_admin_flow else (user.first_name or user.username)
        email_signature = "Đội ngũ Quản trị Dragon Coffee" if is_admin_flow else "Đội ngũ Dragon Coffee"
        intro_text = "Chúng tôi nhận được yêu cầu đặt lại mật khẩu cho tài khoản quản trị/nhân viên của bạn tại Dragon Coffee." if is_admin_flow else "Chúng tôi nhận được yêu cầu đặt lại mật khẩu cho tài khoản của bạn tại Dragon Coffee."

        html_body = f"""
        <p>Chào {greeting_name},</p>
        <p>{intro_text}</p>
        <p>Vui lòng nhấp vào liên kết sau để đặt lại mật khẩu của bạn. Liên kết này sẽ hết hạn sau 30 phút:</p>
        <p style="text-align:center; margin: 20px 0;">
            <a href="{reset_url}" style="background-color: #6F4E37; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold;">Đặt lại mật khẩu</a>
        </p>
        <p>Nếu bạn không yêu cầu đặt lại mật khẩu, vui lòng bỏ qua email này.</p>
        <p>Trân trọng,</p>
        <p><strong>{email_signature}</strong></p>
        """

        sender = current_app.config.get('MAIL_DEFAULT_SENDER', 'no-reply@example.com')
        msg = Message(subject=subject, sender=sender, recipients=[recipient_email])
        msg.html = html_body

        mail.send(msg)
        logger.info(f"Password reset email ({endpoint_name}) sent successfully to {recipient_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send password reset email ({endpoint_name}) to {user.email}: {e}", exc_info=True)
        return False

def send_contact_notification_email(contact_message):
    from app import mail
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    admin_email = current_app.config.get('ADMIN_EMAIL', current_app.config.get('MAIL_USERNAME'))
    if not admin_email: logger.error("ADMIN_EMAIL is not configured."); return False

    try:
        subject = f"[Dragon Coffee Contact] - {contact_message.subject}"
        sender = current_app.config.get('MAIL_DEFAULT_SENDER')
        recipients = [admin_email]

        html_body = f"""
        <h2>Có liên hệ mới từ Website Dragon Coffee</h2>
        <p><strong>Từ:</strong> {contact_message.name} ({contact_message.email})</p>
        <p><strong>Chủ đề:</strong> {contact_message.subject}</p>
        <p><strong>Ngày gửi:</strong> {contact_message.created_at.strftime('%d/%m/%Y %H:%M:%S') if contact_message.created_at else 'N/A'}</p>
        <hr>
        <p><strong>Nội dung:</strong></p>
        <div style="white-space: pre-wrap; border: 1px solid #eee; padding: 10px; background-color: #f9f9f9;">{contact_message.message}</div>
        <hr>
        <p><em>Vui lòng đăng nhập vào trang quản trị để xem chi tiết.</em></p>
        """
        text_body = f"Có liên hệ mới từ {contact_message.name} ({contact_message.email}). Chủ đề: {contact_message.subject}. Nội dung:\n{contact_message.message}"

        msg = Message(subject=subject, sender=sender, recipients=recipients, body=text_body, html=html_body)
        mail.send(msg)
        logger.info(f"Contact notification email sent successfully to {admin_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send contact notification email to {admin_email}: {e}", exc_info=True)
        return False

def send_order_status_email(order):
    from app import mail
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    user = order.customer
    if not user or not user.email: logger.warning(f"No user/email for order {order.id}"); return False

    status_map = {
        'processing': "Đang xử lý", 'ready_for_pickup': "Sẵn sàng để lấy",
        'out_for_delivery': "Đang được giao", 'completed': "Đã hoàn thành",
        'delivered': "Đã giao hàng thành công", 'cancelled': "Đã bị hủy"
    }
    status_display = status_map.get(order.status)
    if not status_display: logger.info(f"No email configured for status '{order.status}'."); return False

    subject = f"[Dragon Coffee] Đơn hàng #{order.order_number}: {status_display}"
    sender = current_app.config.get('MAIL_DEFAULT_SENDER')
    try:
        with current_app.test_request_context():
            order_url = url_for('order.order_detail', order_id=order.id, _external=True)

        html_body = f"<p>Chào {user.first_name or user.username},</p><p>Trạng thái đơn hàng <strong>#{order.order_number}</strong> đã cập nhật: <strong style='color:#6F4E37;'>{status_display}</strong>.</p>"
        if order.status == 'ready_for_pickup': html_body += "<p>Bạn có thể đến nhận hàng.</p>"
        elif order.status == 'out_for_delivery': html_body += "<p>Shipper sắp liên hệ bạn.</p>"
        elif order.status == 'cancelled': html_body += "<p>Nếu cần hỗ trợ, vui lòng liên hệ hotline.</p>"
        html_body += f"<p>Xem chi tiết: <a href='{order_url}'>{order_url}</a></p><p>Cảm ơn!</p>"
        text_body = f"Trạng thái đơn hàng #{order.order_number}: {status_display}. Chi tiết: {order_url}"
        msg = Message(subject=subject, sender=sender, recipients=[user.email], body=text_body, html=html_body)
        mail.send(msg)
        logger.info(f"Order status email SENT to {user.email} for order {order.id} (New Status: {order.status})")
        return True
    except Exception as e:
        logger.error(f"Failed to send order status email for order {order.id}: {e}", exc_info=True)
        return False

def allowed_file(filename):
    allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'webp'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def save_story_image(file_storage):
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    if not file_storage or not file_storage.filename or not allowed_file(file_storage.filename):
        if file_storage and file_storage.filename and not allowed_file(file_storage.filename):
            logger.warning(f"Invalid file type for story image: {file_storage.filename}")
            flash('Định dạng file ảnh không hợp lệ!', 'danger')
        return None

    try:
        filename = secure_filename(file_storage.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        unique_filename = f"story_{uuid.uuid4().hex[:10]}.{ext}"

        stories_folder_abs = os.path.join(current_app.root_path, current_app.config['UPLOAD_FOLDER'], 'stories')
        os.makedirs(stories_folder_abs, exist_ok=True)
        save_path_abs = os.path.join(stories_folder_abs, unique_filename)

        file_storage.save(save_path_abs)
        logger.info(f"Story image saved to: {save_path_abs}")

        # Tạo đường dẫn tương đối từ thư mục static để dùng với url_for
        upload_folder_relative_base = current_app.config['UPLOAD_FOLDER'].replace('static/', '', 1).replace('static\\', '', 1)
        relative_path = os.path.join(upload_folder_relative_base, 'stories', unique_filename).replace(os.path.sep, '/')

        logger.info(f"Relative path for url_for static: {relative_path}")
        return relative_path
    except Exception as e:
        logger.error(f"Error saving story image file: {e}", exc_info=True)
        flash('Có lỗi xảy ra khi lưu ảnh.', 'danger')
        return None

def delete_file(relative_url_path):
    # ... (giữ nguyên logic hàm delete_file của bạn) ...
    logger = current_app.logger if current_app else logging.getLogger(__name__)
    if not relative_url_path:
        logger.warning("delete_file called with empty path.")
        return False
    if relative_url_path.lower().endswith(('default_avatar.png', 'default_product.png')):
        logger.info(f"Attempted to delete default image '{relative_url_path}'. Skipped.")
        return False

    try:
        # Tách phần 'static/' khỏi đường dẫn URL để lấy đường dẫn tương đối từ root app
        static_url_path = url_for('static', filename='')[1:] # Get '/static/'
        if relative_url_path.startswith(static_url_path):
            relative_fs_path = relative_url_path[len(static_url_path):]
        elif relative_url_path.startswith('/' + static_url_path):
             relative_fs_path = relative_url_path[len('/' + static_url_path):]
        else:
             # If it doesn't start with static url path, assume it's relative from static folder directly
             relative_fs_path = relative_url_path

        file_path_abs = os.path.join(current_app.static_folder, relative_fs_path.lstrip('/\\'))
        normalized_path = os.path.normpath(file_path_abs)

        # Security check: Make sure the path is still within the static folder
        if not normalized_path.startswith(os.path.normpath(current_app.static_folder)):
             logger.error(f"Security Alert: Attempt to delete file outside static folder: '{normalized_path}'")
             return False


        if os.path.exists(normalized_path):
            os.remove(normalized_path)
            logger.info(f"Successfully deleted file: {normalized_path}")
            return True
        else:
            logger.warning(f"Attempted to delete file, but not found: {normalized_path} (Derived from URL: '{relative_url_path}')")
            return False
    except Exception as e:
        logger.error(f"Error deleting file at relative URL '{relative_url_path}' (Path: '{normalized_path}'): {e}", exc_info=True)
        return False

def save_avatar_file(file_storage):
    logger = current_app.logger # Giả sử current_app đã có logger
    if not file_storage or not file_storage.filename:
        logger.warning("Attempted to save avatar with no file storage object.")
        return None

    filename = secure_filename(file_storage.filename)
    if allowed_file(filename): # allowed_file cần được định nghĩa hoặc import
        try:
            ext = filename.rsplit('.', 1)[1].lower()
            # current_user cần được import từ flask_login hoặc có sẵn trong context
            # Sửa: nếu current_user không có sẵn, bạn cần truyền user object vào hàm này
            # hoặc tìm cách lấy user_id một cách an toàn.
            # Ví dụ đơn giản hóa:
            user_identifier = current_user.id if hasattr(current_user, 'id') else "unknown_user"
            unique_filename = f"user_{user_identifier}_{uuid.uuid4().hex[:8]}.{ext}"

            # Đường dẫn lưu avatar
            # UPLOAD_FOLDER cần được định nghĩa trong config của app
            avatar_folder_config = current_app.config.get('UPLOAD_FOLDER', 'static/uploads')
            avatar_subfolder = 'avatars'
            
            # Đường dẫn tuyệt đối
            # current_app.root_path là thư mục gốc của ứng dụng Flask
            save_dir_abs = os.path.join(current_app.root_path, avatar_folder_config, avatar_subfolder)
            os.makedirs(save_dir_abs, exist_ok=True)
            save_path_abs = os.path.join(save_dir_abs, unique_filename)

            file_storage.save(save_path_abs)
            logger.info(f"Avatar image saved for user {user_identifier} to: {save_path_abs}")

            # Tạo đường dẫn tương đối để lưu vào DB và dùng với url_for
            # Giả sử UPLOAD_FOLDER là 'static/uploads'
            # Đường dẫn tương đối từ thư mục static
            # Cần bỏ phần "static/" nếu UPLOAD_FOLDER là 'static/uploads'
            # và url_for sẽ tự thêm 'static'
            relative_path_from_static_base = os.path.join(avatar_folder_config.replace('static/', '', 1).replace('static\\', '', 1), avatar_subfolder, unique_filename).replace(os.path.sep, '/')
            
            logger.info(f"Relative URL path for avatar (from static folder): {relative_path_from_static_base}")
            return relative_path_from_static_base # Trả về đường dẫn này để lưu vào DB
        except Exception as e:
            logger.error(f"Error saving avatar file for user {user_identifier}: {e}", exc_info=True)
            flash('Có lỗi xảy ra khi lưu ảnh đại diện.', 'danger') # flash cần import
            return None
    else:
        logger.warning(f"Invalid file type attempted for avatar upload: {filename}")
        flash('Định dạng file ảnh không hợp lệ!', 'danger') # flash cần import
        return None

def delete_avatar_file(relative_url_path): # Đảm bảo hàm này cũng có
    # ... (code của hàm delete_avatar_file như cũ) ...
    logger = current_app.logger
    if not relative_url_path or 'default_avatar' in relative_url_path:
        return False
    try:
        # Nếu relative_url_path bắt đầu bằng /static/uploads/avatars/
        # thì static_folder của Flask chính là thư mục chứa 'static'
        # Nên đường dẫn file hệ thống sẽ là current_app.static_folder + phần còn lại
        # Ví dụ: current_app.static_folder = /path/to/project/static
        # relative_url_path = uploads/avatars/user_1.jpg
        
        # Giả định relative_url_path là đường dẫn TƯƠNG ĐỐI với thư mục static
        # Ví dụ: 'uploads/avatars/user_1.jpg'
        file_path_abs = os.path.join(current_app.static_folder, relative_url_path)

        if os.path.exists(file_path_abs):
            os.remove(file_path_abs)
            logger.info(f"Successfully deleted old avatar file: {file_path_abs}")
            return True
        else:
            logger.warning(f"Attempted to delete avatar, but file not found: {file_path_abs} (from relative_url_path: {relative_url_path})")
            return False
    except Exception as e:
        logger.error(f"Error deleting old avatar file '{relative_url_path}': {e}", exc_info=True)
        return False

# BỔ SUNG delete_old_image nếu bạn dùng nó ở admin_routes.py (hoặc gộp với delete_file)
def delete_old_image(relative_url_path):
    return delete_file(relative_url_path) # Đơn giản là gọi lại hàm delete_file

# BỔ SUNG save_product_image nếu dùng ở admin_routes.py
def save_product_image(file_storage):
    logger = current_app.logger
    if not file_storage or not file_storage.filename or not allowed_file(file_storage.filename):
        if file_storage and file_storage.filename and not allowed_file(file_storage.filename):
            logger.warning(f"Invalid file type for product image: {file_storage.filename}")
            flash('Định dạng file ảnh không hợp lệ!', 'danger')
        return None

    try:
        filename = secure_filename(file_storage.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        unique_filename = f"product_{uuid.uuid4().hex[:10]}.{ext}"

        # Lưu trong thư mục con 'products' của UPLOAD_FOLDER
        products_folder_abs = os.path.join(current_app.root_path, current_app.config['UPLOAD_FOLDER'], 'products')
        os.makedirs(products_folder_abs, exist_ok=True)
        save_path_abs = os.path.join(products_folder_abs, unique_filename)

        file_storage.save(save_path_abs)
        logger.info(f"Product image saved to: {save_path_abs}")

        # Đường dẫn tương đối từ 'static/'
        upload_folder_relative_base = current_app.config['UPLOAD_FOLDER'].replace('static/', '', 1).replace('static\\', '', 1)
        relative_path = os.path.join(upload_folder_relative_base, 'products', unique_filename).replace(os.path.sep, '/')

        logger.info(f"Relative URL path for product image: {relative_path}")
        return relative_path
    except Exception as e:
        logger.error(f"Error saving product image file: {e}", exc_info=True)
        flash('Có lỗi xảy ra khi lưu ảnh sản phẩm.', 'danger')
        return None