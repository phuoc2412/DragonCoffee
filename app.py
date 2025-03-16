import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

# Initialize extensions
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

# Create the app
app = Flask(__name__)

# Configure the app
app.secret_key = os.environ.get("SESSION_SECRET", "dragon_coffee_secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/dragon_coffee")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize extensions with the app
db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

# Create database tables within app context
with app.app_context():
    # Import models to ensure they're registered with SQLAlchemy
    import models
    # Create all tables
    db.create_all()

# Import and register blueprints
from routes.main_routes import main_bp
from routes.admin_routes import admin_bp
from routes.auth_routes import auth_bp
from routes.order_routes import order_bp

app.register_blueprint(main_bp)
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(order_bp, url_prefix='/order')

# Configure user loader for flask-login
from models import User

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
