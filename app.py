# /DragonCoffee/app.py
import os
import logging
import datetime
import locale
import random

from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager
from flask_babel import Babel, _
from flask_moment import Moment
from flask_migrate import Migrate
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail, Message
from utils import format_currency

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

class Base(DeclarativeBase):
    pass

app = Flask(__name__)

app.jinja_env.globals.update(random=random)

app.config['SECRET_KEY'] = os.environ.get("SESSION_SECRET") or 'fallback-strong-random-secret-key-123!'
if app.config['SECRET_KEY'] == 'fallback-strong-random-secret-key-123!':
     logging.warning("WARNING: Using default SECRET_KEY. Set SESSION_SECRET env variable.")

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///local_dev.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = { "pool_recycle": 300, "pool_pre_ping": True }
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config['BABEL_DEFAULT_LOCALE'] = 'vi'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'products')) # <-- Giữ lại
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'avatars')) # <-- Giữ lại
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'stories')) # <--- THÊM DÒNG NÀY

db = SQLAlchemy(app, model_class=Base)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
moment = Moment(app)

# Cấu hình Flask-Mail (Lấy từ biến môi trường)
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com') # Ví dụ Gmail
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587)) # TLS port
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', '1', 't']
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'false').lower() in ['true', '1', 't']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME') # Email dùng để gửi
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD') # Mật khẩu ứng dụng hoặc mật khẩu email
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', app.config['MAIL_USERNAME']) # Người gửi mặc định


# Kiểm tra cấu hình mail thiết yếu
if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
    logging.warning("MAIL_USERNAME hoặc MAIL_PASSWORD chưa được cấu hình trong file .env. Tính năng gửi email (VD: Reset mật khẩu) sẽ không hoạt động.")

mail = Mail(app) # Khởi tạo Flask-Mail

# Define locale selector function *before* Babel init
def select_locale():
    preferred_langs = ['vi', 'en']
    # Use request imported at the top
    best_match = request.accept_languages.best_match(preferred_langs)
    return best_match or app.config.get('BABEL_DEFAULT_LOCALE', 'vi')

# Initialize Babel with the selector function
babel = Babel(app, locale_selector=select_locale)

csrf = CSRFProtect(app)

login_manager.login_view = 'auth.login'
login_manager.login_message = _("Vui lòng đăng nhập để truy cập trang này.")
login_manager.login_message_category = "info"

try:
    # Import models TRƯỚC khi init AI services (vì AI services có thể cần models)
    from models import User
    # Các models khác được import trong chính models.py nên thường là ok
except Exception as e:
    logging.critical(f"CRITICAL ERROR: Failed to import User model BEFORE AI init: {e}", exc_info=True)

# --- Khởi tạo AI Services TRONG App Context ---
from ai_services import init_ai_services
with app.app_context():
    logging.info("Initializing AI Services...")
    try:
        init_ai_services() # Gọi hàm khởi tạo chung
        logging.info("AI Services Initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize AI services during app setup: {e}", exc_info=True)
        # Cân nhắc có nên dừng app nếu AI services là cốt lõi không
# ---------------------------------------------

# ... (Đăng ký Blueprints - nên để SAU khi init AI services nếu routes dùng services đó) ...
logging.info("Registering Blueprints...")
try:
    from routes.main_routes import main_bp
    from routes.admin_routes import admin_bp
    from routes.auth_routes import auth_bp
    from routes.order_routes import order_bp
    from routes.ai_routes import ai_bp # Blueprint cho AI

    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(auth_bp, url_prefix='/auth') # Giả sử bạn có prefix này
    app.register_blueprint(order_bp, url_prefix='/order')
    app.register_blueprint(ai_bp, url_prefix='/ai') # Đăng ký AI blueprint
    logging.info("Blueprints registered successfully.")
except ImportError as e:
     logging.critical(f"CRITICAL ERROR: Failed to import or register blueprints: {e}", exc_info=True)

@login_manager.user_loader
def load_user(user_id):
    try:
        user = db.session.get(User, int(user_id))
        return user
    except ValueError:
        logging.warning(f"Invalid user_id format passed to user_loader: {user_id}")
        return None
    except Exception as e:
         logging.error(f"Error loading user with ID {user_id}: {e}", exc_info=True)
         return None

try:
    from utils import format_currency, get_order_status_label

    @app.template_filter('format_datetime')
    def format_datetime_filter(value, format='%d/%m/%Y %H:%M'):
        if value is None: return ""
        if isinstance(value, (int, float)):
            try: value = datetime.datetime.fromtimestamp(value)
            except (ValueError, OSError): logging.warning(f"Could not convert timestamp {value}."); return value
        if isinstance(value, datetime.datetime):
            try: return value.strftime(format)
            except ValueError: logging.warning(f"Could not format datetime {value} with '{format}'."); return value
        return value

    app.template_filter('format_price')(format_currency)

except ImportError:
     logging.error("Failed to import or register template filters/globals from utils.")


# Note: Removed the incorrect Babel locale selector decorator/method call from here