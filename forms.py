from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField, SelectField, IntegerField, FloatField, DateField, FileField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Optional, NumberRange, URL
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
     # --- THÊM TRƯỜNG NÀY VÀO ---
    min_quantity = IntegerField('Tồn kho tối thiểu',
                                validators=[Optional(), # Cho phép để trống
                                            NumberRange(min=0, message='Số lượng tối thiểu phải lớn hơn hoặc bằng 0')],
                                default=10) # Đặt giá trị mặc định (ví dụ 10)
    # --------------------------

    submit = SubmitField('Lưu sản phẩm')

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
    is_staff = BooleanField('Is Staff', default=False) # <---- ĐÃ THÊM DÒNG NÀY
    submit = SubmitField('Save Employee')

class ReviewForm(FlaskForm):
    """Form for submitting product reviews"""
    # name = StringField('Your Name', validators=[DataRequired(), Length(max=100)]) # <--- ĐÃ XÓA dòng này
    rating = SelectField('Rating', choices=[(1, '1 Star'), (2, '2 Stars'), (3, '3 Stars'), (4, '4 Stars'), (5, '5 Stars')], coerce=int, validators=[DataRequired()])
    # ĐỔI TÊN TRƯỜNG 'comment' THÀNH 'content' ĐỂ KHỚP VỚI DATABASE VÀ MODEL
    content = TextAreaField('Your Review', validators=[Length(max=500)]) # <--- ĐỔI TÊN THÀNH 'content'

    submit = SubmitField('Submit Review')


# --- THÊM ĐOẠN CODE NÀY VÀO CUỐI FILE forms.py ---

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField, PasswordField
from wtforms.validators import DataRequired, Length, Email, Optional, EqualTo, ValidationError
# Import User model để kiểm tra email/username đã tồn tại chưa
# Giả sử model nằm trong thư mục gốc hoặc 'app'
try:
    from models import User
except ImportError:
    from app.models import User # Thử import từ app nếu cách trên không được

class UpdateProfileForm(FlaskForm):
    username = StringField('Tên đăng nhập',
                           validators=[DataRequired(message="Vui lòng nhập tên đăng nhập."),
                                       Length(min=3, max=20, message="Tên đăng nhập phải từ 3 đến 20 ký tự.")])
    email = StringField('Email',
                        validators=[DataRequired(message="Vui lòng nhập email."),
                                    Email(message="Địa chỉ email không hợp lệ.")])
    first_name = StringField('Tên',
                             validators=[Optional(), # Cho phép để trống
                                         Length(max=64)])
    last_name = StringField('Họ',
                            validators=[Optional(), # Cho phép để trống
                                        Length(max=64)])
    phone = StringField('Số điện thoại',
                        validators=[Optional(), # Cho phép để trống
                                    Length(min=9, max=15, message="Số điện thoại không hợp lệ.")])
    address = TextAreaField('Địa chỉ',
                            validators=[Optional(), # Cho phép để trống
                                        Length(max=255)])
    # Trường mật khẩu là tùy chọn khi cập nhật
    password = PasswordField('Mật khẩu mới (để trống nếu không đổi)',
                            validators=[Optional(),
                                        Length(min=6, message='Mật khẩu phải có ít nhất 6 ký tự.'),
                                        EqualTo('password2', message='Mật khẩu không khớp.')])
    password2 = PasswordField('Xác nhận mật khẩu mới', validators=[Optional()])

    submit = SubmitField('Cập nhật hồ sơ')

    # Lưu ý: Cần khởi tạo form với username/email gốc để validator hoạt động đúng
    def __init__(self, original_username, original_email, *args, **kwargs):
        super(UpdateProfileForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_email = original_email

    # Validator tùy chỉnh để kiểm tra username đã tồn tại (nhưng cho phép giữ nguyên)
    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError('Tên đăng nhập này đã được người khác sử dụng. Vui lòng chọn tên khác.')

    # Validator tùy chỉnh để kiểm tra email đã tồn tại (nhưng cho phép giữ nguyên)
    def validate_email(self, email):
        # Chuyển sang chữ thường trước khi kiểm tra
        check_email = email.data.lower()
        if check_email != self.original_email.lower():
            user = User.query.filter_by(email=check_email).first()
            if user:
                raise ValidationError('Địa chỉ email này đã được người khác sử dụng. Vui lòng chọn email khác.')

# --- KẾT THÚC PHẦN THÊM VÀO ---

class InterestingStoryForm(FlaskForm):
    title = StringField('Tiêu đề', validators=[DataRequired(message="Vui lòng nhập tiêu đề."), Length(max=200)])
    content = TextAreaField('Nội dung câu chuyện', validators=[DataRequired(message="Nội dung không được để trống.")])
    image_url = StringField('URL Hình ảnh (Tùy chọn)', validators=[Optional(), URL(message="URL hình ảnh không hợp lệ."), Length(max=256)])
    submit = SubmitField('Lưu thay đổi')