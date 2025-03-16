from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField
from wtforms import IntegerField, FloatField, SelectField, DateField, FileField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Optional
from models import User

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=64)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    first_name = StringField('First Name', validators=[DataRequired(), Length(max=64)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(max=64)])
    phone = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username.')
            
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Please use a different email address.')

class ContactForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(max=64)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    subject = StringField('Subject', validators=[DataRequired(), Length(max=120)])
    message = TextAreaField('Message', validators=[DataRequired()])
    submit = SubmitField('Send Message')

class ProductForm(FlaskForm):
    name = StringField('Product Name', validators=[DataRequired(), Length(max=64)])
    description = TextAreaField('Description', validators=[Optional()])
    price = FloatField('Price', validators=[DataRequired()])
    image_url = StringField('Image URL', validators=[Optional(), Length(max=256)])
    is_available = BooleanField('Available', default=True)
    is_featured = BooleanField('Featured', default=False)
    category_id = SelectField('Category', validators=[DataRequired()], coerce=int)
    stock_quantity = IntegerField('Stock Quantity', validators=[DataRequired()], default=0)
    submit = SubmitField('Save Product')

class CategoryForm(FlaskForm):
    name = StringField('Category Name', validators=[DataRequired(), Length(max=64)])
    description = TextAreaField('Description', validators=[Optional()])
    submit = SubmitField('Save Category')

class PromotionForm(FlaskForm):
    name = StringField('Promotion Name', validators=[DataRequired(), Length(max=64)])
    description = TextAreaField('Description', validators=[Optional()])
    discount_percent = FloatField('Discount Percent', validators=[Optional()])
    discount_amount = FloatField('Discount Amount', validators=[Optional()])
    code = StringField('Promotion Code', validators=[Optional(), Length(max=20)])
    start_date = DateField('Start Date', validators=[DataRequired()])
    end_date = DateField('End Date', validators=[DataRequired()])
    is_active = BooleanField('Active', default=True)
    submit = SubmitField('Save Promotion')

class EmployeeForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(max=64)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(max=64)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    phone = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    position = StringField('Position', validators=[DataRequired(), Length(max=64)])
    hire_date = DateField('Hire Date', validators=[DataRequired()])
    salary = FloatField('Salary', validators=[Optional()])
    submit = SubmitField('Save Employee')
