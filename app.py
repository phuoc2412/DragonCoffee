import os
import logging
import datetime
import locale
import random
from flask import Flask, request, current_app, jsonify, flash, redirect, url_for, session # <-- ADD flash, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager, current_user
from flask_babel import Babel, _
from flask_moment import Moment
from flask_migrate import Migrate
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail, Message
from utils import format_currency # Ensure format_currency is available if used below
from datetime import datetime


# Assuming your models are defined and can be imported BEFORE app context
# (This is common in simple structures)
# try:
#      from models import User # Assuming User model is needed by LoginManager setup
# except ImportError as e:
#      # Log critical error but define a dummy User to allow Flask app init to proceed
#      logging.critical(f"CRITICAL ERROR: Failed to import User model BEFORE Flask app setup: {e}", exc_info=True)
#      class User: pass # Define dummy class

load_dotenv()

# --- 1. CẤU HÌNH LOGGER VÀ APP ---
# Check if MAIL_SERVER is configured before trying to init Mail
if os.environ.get('MAIL_SERVER'):
     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
else:
     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
     logging.warning("MAIL_SERVER not set. Email features might not work.")


class Base(DeclarativeBase):
    pass

app = Flask(__name__)

# --- 2. CẤU HÌNH APP (mostly unchanged) ---
app.jinja_env.globals.update(random=random, enumerate=enumerate) # Ensure enumerate is available
app.config['SECRET_KEY'] = os.environ.get("SESSION_SECRET") or 'fallback-strong-random-secret-key-123!'
if app.config['SECRET_KEY'] == 'fallback-strong-random-secret-key-123!':
    app.logger.warning("WARNING: Using default SECRET_KEY. Set SESSION_SECRET env variable.") # SỬA Ở ĐÂY

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///local_dev.db")
# app.config["SQLALCHEMY_ENGINE_OPTIONS"] = { "pool_recycle": 300, "pool_pre_ping": True } # Optional, database-specific
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False # Suppress warning
app.config['BABEL_DEFAULT_LOCALE'] = 'vi' # Set default locale
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # Max file size
# Config Chatbot
app.config['CHATBOT_ML_MODEL_CONFIDENCE_THRESHOLD'] = 0.65 # Ngưỡng tin cậy cho ML model
app.config['CHATBOT_ML_KEYWORD_FALLBACK_THRESHOLD'] = 1.5 # Ngưỡng cho fallback keyword
app.config['CHATBOT_CONTEXT_TIMEOUT_MINUTES'] = 5         # Thời gian giữ context (phút)
app.config['SHOP_HOTLINE'] = os.environ.get('SHOP_HOTLINE', '1900-DRAGON') # Lấy hotline từ env
app.config['SHOP_FEEDBACK_EMAIL'] = os.environ.get('SHOP_FEEDBACK_EMAIL', 'feedback@dragoncoffee.com')

# Create upload directories if they don't exist
upload_base = app.config['UPLOAD_FOLDER']
subfolders = ['products', 'avatars', 'stories']
for folder in subfolders:
    path = os.path.join(upload_base, folder)
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

# Mail Configuration (unchanged)
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER') # <-- Should read from env
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', '1', 't']
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'false').lower() in ['true', '1', 't']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
# Default sender can be MAIL_USERNAME if set
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', app.config.get('MAIL_USERNAME', 'noreply@example.com'))

# Check Mail credentials availability only AFTER config is loaded
if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
    app.logger.warning("MAIL_USERNAME or MAIL_PASSWORD not set in env variables. Email features might not work.") # SỬA Ở ĐÂY


# --- 3. KHỞI TẠO EXTENSIONS ---
db = SQLAlchemy(app, model_class=Base) # SQLAlchemy needs the app instance here
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app) # Init login manager with app
moment = Moment(app) # Init moment with app
mail = Mail(app)     # Init mail with app
csrf = CSRFProtect(app) # Init CSRF with app
babel = Babel(app)   # Init Babel with app instance directly


# --- 4. IMPORT MODELS (after db is created) ---
# Importing here prevents circular imports if models import db from app
try:
    # Import necessary models
    from models import User, Order, Product, Category, Location, Review, InterestingStory, InventoryItem, Employee, ContactMessage, Promotion, StockReceipt, WebVisit
    app.logger.info("Models imported successfully.") # SỬA Ở ĐÂY
except ImportError as e:
    app.logger.critical(f"CRITICAL ERROR: Failed to import models AFTER DB init: {e}", exc_info=True) # SỬA Ở ĐÂY
    raise e # Re-raise fatal error

# --- 5. IMPORT FORMS ---
try:
    # Import all necessary forms
    from forms import LoginForm, RegistrationForm, UpdateProfileForm, ContactForm, ReviewForm, ForgotPasswordForm, ResetPasswordForm, ProductForm, CategoryForm, PromotionForm, EmployeeForm, StockReceiptForm, LocationForm
    app.logger.info("Forms imported successfully.") # SỬA Ở ĐÂY
except ImportError as e:
     app.logger.critical(f"CRITICAL ERROR: Failed to import forms: {e}", exc_info=True) # SỬA Ở ĐÂY
     raise e

# --- 6. CẤU HÌNH LOGIN MANAGER (after init_app) ---
login_manager.login_view = 'auth.login' # Assuming auth_bp is registered with url_prefix='/auth'
login_manager.login_message = _("Vui lòng đăng nhập để truy cập trang này.") # Example translatable message
login_manager.login_message_category = "info" # Bootstrap category for flashing message

# --- 7. CẤU HÌNH BABEL LOCALE SELECTOR (after init_app) ---
# <<< Định nghĩa hàm trước >>>
def get_locale():
    # Supports guessing from request header (best_match), user preferences, or default
    preferred_langs = ['vi', 'en'] # Add 'en' or other supported locales
    # Check user preference if logged in (e.g. user.locale), otherwise use request header
    # locale_from_user = current_user.locale if current_user.is_authenticated and hasattr(current_user, 'locale') else None
    # if locale_from_user: return locale_from_user

    if request:
         # Use Flask-Babel's ability to guess from request.accept_languages
        best_match = request.accept_languages.best_match(preferred_langs)
        if best_match: return best_match # Use the browser's preference if it matches our supported languages

    # Fallback to the default locale if no match found
    return app.config.get('BABEL_DEFAULT_LOCALE', 'vi')

# <<< Đăng ký locale_selector AFTER init_app >>>
babel.locale_selector_func = get_locale


# --- 8. ĐỊNH NGHĨA USER LOADER ---
@login_manager.user_loader
def load_user(user_id):
    logger = current_app.logger
    if user_id is None:
        return None
    try:
        # Use db.session.get which is the recommended way
        # Return User object if found, None otherwise
        user = db.session.get(User, int(user_id))
        # logger.debug(f"load_user called with ID {user_id}. User found: {user is not None}")
        return user
    except (ValueError, TypeError):
         # Handle cases where user_id is not an integer
         logger.warning(f"Invalid user_id format passed to user_loader: {user_id}")
         return None
    except Exception as e:
        # Catch other potential database or query errors
        logger.error(f"Error loading user with ID {user_id}: {e}", exc_info=True)
        # Consider specific handling or logging based on error type
        return None

# --- Unauthorized Handler ---
# Called when login_required fails
@login_manager.unauthorized_handler
def unauthorized_callback():
    current_app.logger.warning(f"UNAUTHORIZED_CALLBACK triggered for path: {request.path}")

    # Check if the request expects JSON response (e.g., AJAX, API calls)
    # Flask provides request.is_json. Also check 'Accept' header and 'X-Requested-With'.
    is_ajax_or_wants_json = (
        request.is_json or # Explicitly application/json Content-Type
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or # Common AJAX header
        'application/json' in request.accept_mimetypes # Check Accept header
    )

    if is_ajax_or_wants_json:
        current_app.logger.info("Returning JSON 401 response for AJAX/API request.")
        # Return JSON error response for API/AJAX calls
        # Use Babel's _ for translatable messages even in JSON (optional)
        message = _("Yêu cầu xác thực. Vui lòng đăng nhập.")
        return jsonify(success=False, message=message, error_code="UNAUTHENTICATED"), 401 # Use 401 Unauthorized

    else:
        # For traditional browser requests, flash message and redirect to login page
        current_app.logger.info(f"Redirecting to login page: {login_manager.login_view}")
        flash(login_manager.login_message, login_manager.login_message_category) # Flash the message configured
        # Pass the current request URL as 'next' to return user to original page after login
        return redirect(url_for(login_manager.login_view, next=request.url))


# --- 9. KHỞI TẠO AI SERVICES (after db is ready) ---
# This function will call the init functions in the AI modules
try:
    # Import the package-level init function
    from ai_services import init_ai_services, get_response # Import get_response if you need it in global scope or template context
    app.logger.info("Imported AI services package init function.") # SỬA Ở ĐÂY

    # IMPORTANT: Initialize AI services *within* an app context
    # Use with app.app_context(): to ensure db.session and other app components are available
    # Or, pass db instance directly to init_ai_services if it expects it.
    # Based on the refined plan, init_ai_services will accept db_instance
    with app.app_context():
        app.logger.info("Initializing AI Services within app context...") # SỬA Ở ĐÂY
        try:
            # Pass the SQLAlchemy db instance to the initialization function
            init_ai_services(db) # Pass db here
            app.logger.info("AI Services Initialized successfully.") # SỬA Ở ĐÂY
        except Exception as e:
            # Log critical error but continue app startup if possible
            app.logger.critical(f"Failed to initialize AI services during app setup: {e}", exc_info=True) # SỬA Ở ĐÂY
            # Depending on criticality, you might re-raise e here if AI is essential

except ImportError as e:
    app.logger.critical(f"Could not import AI services package or its init function: {e}", exc_info=True) # SỬA Ở ĐÂY
    # Define dummy function if import fails to prevent crashes later
    init_ai_services = lambda *args, **kwargs: logging.error("AI Services not available due to import error.")


# --- 10. ĐĂNG KÝ BLUEPRINTS ---
app.logger.info("Registering Blueprints...") # SỬA Ở ĐÂY
try:
    # Import and register your blueprints
    from routes.main_routes import main_bp
    from routes.admin_routes import admin_bp
    from routes.auth_routes import auth_bp
    from routes.order_routes import order_bp
    from routes.ai_routes import ai_bp # <-- Ensure ai_bp exists and is imported

    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin') # Use a prefix for admin routes
    app.register_blueprint(auth_bp, url_prefix='/auth') # Use a prefix for authentication routes
    app.register_blueprint(order_bp, url_prefix='/order') # Use a prefix for order routes
    app.register_blueprint(ai_bp, url_prefix='/ai') # Use a prefix for AI routes

    app.logger.info("Blueprints registered successfully.") # SỬA Ở ĐÂY
except ImportError as e:
     # Log a critical error if blueprints cannot be imported
     app.logger.critical(f"CRITICAL ERROR: Failed to import or register blueprints: {e}", exc_info=True) # SỬA Ở ĐÂY
     raise e # Re-raise the error if app cannot function without routes

# --- 11. TEMPLATE FILTERS & CONTEXT PROCESSORS ---
# These should be defined AFTER app and extensions are initialized,
# but BEFORE routes might try to render templates.
try:
    # Import helper functions needed for templates
    from utils import get_order_status_label, format_currency # ensure these are available

    # Register custom Jinja2 filters
    @app.template_filter('format_datetime')
    def format_datetime_filter(value, format='%d/%m/%Y %H:%M'):
        if value is None: return ""
        if isinstance(value, (int, float)):
            try: value = datetime.fromtimestamp(value)
            except (ValueError, OSError): current_app.logger.warning(f"Could not convert timestamp {value} to datetime."); return str(value)
        if isinstance(value, datetime):
            if value.year > 1900:
                try: return value.strftime(format)
                except ValueError: current_app.logger.warning(f"Could not format datetime {value} with format '{format}'."); return str(value)
            else: return str(value)
        return value

    app.template_filter('format_price')(format_currency)

    @app.context_processor
    def inject_utility_processor():
        return dict(
            format_currency=format_currency,
            get_order_status_label=get_order_status_label,
        )

    @app.context_processor
    def inject_auth_forms():
         login_form = LoginForm()
         registration_form = RegistrationForm()
         return dict(login_form=login_form, registration_form=registration_form)

except ImportError:
     app.logger.error("Failed to import or register template filters/globals from utils.") # SỬA Ở ĐÂY
except Exception as e:
     app.logger.error(f"Error setting up template context: {e}", exc_info=True) # SỬA Ở ĐÂY

@app.before_request
def track_web_visit():
    # Bỏ qua các request cho static files và một số endpoint không cần thiết
    # Hoặc bỏ qua nếu request là từ một bot đã biết (phức tạp hơn, tạm thời bỏ qua)
    endpoint = request.endpoint
    if endpoint:
        # Các endpoint cần bỏ qua
        ignored_endpoints = ['static', 'admin.static'] # Thêm các endpoint admin.static
        ignored_prefixes = ['debugtoolbar.', 'api.','admin.api_', '_uploads.'] # Thêm tiền tố cho API và uploads nếu có

        if endpoint in ignored_endpoints or any(endpoint.startswith(prefix) for prefix in ignored_prefixes):
            return # Bỏ qua, không ghi log visit

        # Cũng có thể kiểm tra xem có phải là route chính không hay là route cho resource (CSS, JS)
        # Hoặc kiểm tra request.blueprint (ví dụ: không log cho blueprint 'admin_api')

    # Không ghi log cho các request lỗi (ví dụ 404) nếu không muốn (tùy chọn)
    # if request.routing_exception:
    #     return

    try:
        visit_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        # Xử lý trường hợp X-Forwarded-For có nhiều IP
        if visit_ip and ',' in visit_ip:
            visit_ip = visit_ip.split(',')[0].strip()
            
        new_visit = WebVisit(
            ip_address=visit_ip,
            user_agent=request.user_agent.string[:255] if request.user_agent else None, # Cắt bớt nếu quá dài
            path=request.path[:2048] if request.path else None, # Cắt bớt path nếu quá dài
            user_id=current_user.id if current_user.is_authenticated else None,
            user_email=current_user.email if current_user.is_authenticated else None,
            session_id=session.sid if session and hasattr(session, 'sid') else None
        )
        db.session.add(new_visit)
        db.session.commit()
        # Không nên log ở đây vì nó sẽ chạy cho MỌI request hợp lệ, gây spam log
        # current_app.logger.debug(f"Visit tracked: {request.path} from {visit_ip}")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error tracking web visit: {e}", exc_info=False) # Không cần full traceback mỗi lần