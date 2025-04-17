# START OF FILE forms.py

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed # DI CHUYỂN LÊN ĐÂY
from wtforms import (StringField, PasswordField, BooleanField, SubmitField,
                     TextAreaField, SelectField, IntegerField, FloatField, DateField)
from wtforms.validators import (DataRequired, Email, EqualTo, Length,
                                ValidationError, Optional, NumberRange, URL)
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
    price = FloatField('Price', validators=[DataRequired(), NumberRange(min=0)])

    image_file = FileField('Ảnh Sản phẩm (Upload)', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Chỉ cho phép upload ảnh!')
    ])
    image_url = StringField('Hoặc nhập URL Ảnh', validators=[Optional(), URL(), Length(max=256)])

    is_available = BooleanField('Available', default=True)
    is_featured = BooleanField('Featured', default=False)
    category_id = SelectField('Category', validators=[DataRequired()], coerce=int)
    stock_quantity = IntegerField('Stock Quantity', validators=[DataRequired(), NumberRange(min=0)], default=0)
    min_quantity = IntegerField('Tồn kho tối thiểu',
                                validators=[Optional(), NumberRange(min=0)], default=10)
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
    position = StringField('Position', validators=[DataRequired(), Length(max=64)])
    hire_date = DateField('Hire Date', validators=[DataRequired()])
    salary = FloatField('Salary', validators=[Optional()])
    is_staff = BooleanField('Is Staff', default=False)
    submit = SubmitField('Save Employee Info')

class ReviewForm(FlaskForm):
    """Form for submitting product reviews"""
    rating = SelectField('Rating', choices=[(1, '1 Star'), (2, '2 Stars'), (3, '3 Stars'), (4, '4 Stars'), (5, '5 Stars')], coerce=int, validators=[DataRequired()])
    content = TextAreaField('Your Review', validators=[Length(max=500)])
    submit = SubmitField('Submit Review')

class UpdateProfileForm(FlaskForm):
    username = StringField('Tên đăng nhập',
                           validators=[DataRequired(message="Vui lòng nhập tên đăng nhập."),
                                       Length(min=3, max=20, message="Tên đăng nhập phải từ 3 đến 20 ký tự.")])
    email = StringField('Email',
                        validators=[DataRequired(message="Vui lòng nhập email."),
                                    Email(message="Địa chỉ email không hợp lệ.")])
    first_name = StringField('Tên',
                             validators=[Optional(), Length(max=64)])
    last_name = StringField('Họ',
                            validators=[Optional(), Length(max=64)])
    phone = StringField('Số điện thoại',
                        validators=[Optional(),
                                    Length(min=9, max=15, message="Số điện thoại không hợp lệ.")])

    address = TextAreaField('Địa chỉ',
                            validators=[Optional(), Length(max=255)],
                            render_kw={"rows": 3, "placeholder": "Nhập địa chỉ nhận hàng..."})

    avatar = FileField('Ảnh đại diện mới (Để trống nếu không đổi)',
                       validators=[
                           Optional(),
                           FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Chỉ cho phép tải lên ảnh!')
                       ])

    password = PasswordField('Mật khẩu mới (để trống nếu không đổi)',
                             validators=[Optional(),
                                         Length(min=6, message='Mật khẩu phải có ít nhất 6 ký tự.'),
                                         EqualTo('password2', message='Mật khẩu không khớp.')])
    password2 = PasswordField('Xác nhận mật khẩu mới', validators=[Optional()])

    submit = SubmitField('Cập nhật hồ sơ')

    def __init__(self, original_username, original_email, *args, **kwargs):
        super(UpdateProfileForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_email = original_email

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError('Tên đăng nhập này đã được người khác sử dụng. Vui lòng chọn tên khác.')

    def validate_email(self, email):
        check_email = email.data.lower()
        if check_email != self.original_email.lower():
            user = User.query.filter_by(email=check_email).first()
            if user:
                raise ValidationError('Địa chỉ email này đã được người khác sử dụng. Vui lòng chọn email khác.')

class InterestingStoryForm(FlaskForm):
    title = StringField('Tiêu đề', validators=[DataRequired(message="Vui lòng nhập tiêu đề."), Length(max=200)])
    content = TextAreaField('Nội dung câu chuyện', validators=[DataRequired(message="Nội dung không được để trống.")])

    image_file = FileField('Ảnh minh họa (Tùy chọn)', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Chỉ cho phép tải lên ảnh!')
    ])

    submit = SubmitField('Lưu thay đổi')

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired("Vui lòng nhập địa chỉ email."), Email("Địa chỉ email không hợp lệ.")])
    submit = SubmitField('Gửi yêu cầu đặt lại mật khẩu')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('Mật khẩu mới', validators=[DataRequired("Vui lòng nhập mật khẩu mới."), Length(min=6, message='Mật khẩu phải có ít nhất 6 ký tự.')])
    password2 = PasswordField('Xác nhận mật khẩu mới', validators=[DataRequired("Vui lòng xác nhận mật khẩu mới."), EqualTo('password', message='Mật khẩu không khớp.')])
    submit = SubmitField('Đặt lại mật khẩu')

class StockReceiptForm(FlaskForm):
    inventory_item_id = SelectField('Sản phẩm (Trong kho)', validators=[DataRequired("Vui lòng chọn sản phẩm.")], coerce=int)
    quantity_added = IntegerField('Số lượng nhập', validators=[DataRequired("Nhập số lượng."), NumberRange(min=1, message="Số lượng phải lớn hơn 0.")])
    supplier = StringField('Nhà cung cấp (Tùy chọn)', validators=[Optional(), Length(max=128)])
    unit_cost = FloatField('Giá nhập / đơn vị (Tùy chọn)', validators=[Optional(), NumberRange(min=0)])
    notes = TextAreaField('Ghi chú (Tùy chọn)')
    submit = SubmitField('Xác nhận Nhập kho')

class LocationForm(FlaskForm):
    name = StringField('Tên chi nhánh',
                       validators=[DataRequired("Vui lòng nhập tên chi nhánh."),
                                   Length(max=100)])
    address = TextAreaField('Địa chỉ đầy đủ',
                            validators=[DataRequired("Vui lòng nhập địa chỉ.")])
    phone = StringField('Số điện thoại',
                        validators=[Optional(), Length(max=30)])
    hours = TextAreaField('Giờ mở cửa',
                          validators=[Optional()],
                          description="Nhập dạng text, ví dụ: T2-T6: 7h-22h | T7-CN: 8h-23h")
    latitude = FloatField('Vĩ độ (Latitude)',
                           validators=[Optional(), NumberRange(min=-90, max=90)])
    longitude = FloatField('Kinh độ (Longitude)',
                            validators=[Optional(), NumberRange(min=-180, max=180)])
    map_embed_url = TextAreaField('URL Nhúng Google Maps',
                                  validators=[Optional(), URL(message="URL không hợp lệ.")],
                                  description="Dán CHỈ phần URL trong thẻ <iframe> từ Google Maps.")
    is_active = BooleanField('Đang hoạt động', default=True)
    submit = SubmitField('Lưu địa điểm')