from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import Product, Category, ContactMessage, Review
from forms import ContactForm
from app import db

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    featured_products = Product.query.filter_by(is_featured=True).limit(6).all()
    categories = Category.query.all()
    return render_template('index.html', featured_products=featured_products, categories=categories)

@main_bp.route('/menu')
def menu():
    category_id = request.args.get('category', type=int)
    if category_id:
        products = Product.query.filter_by(category_id=category_id, is_available=True).all()
        current_category = Category.query.get_or_404(category_id)
    else:
        products = Product.query.filter_by(is_available=True).all()
        current_category = None
    
    categories = Category.query.all()
    return render_template('menu.html', products=products, categories=categories, current_category=current_category)

@main_bp.route('/about')
def about():
    return render_template('about.html')

@main_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    form = ContactForm()
    if form.validate_on_submit():
        message = ContactMessage(
            name=form.name.data,
            email=form.email.data,
            subject=form.subject.data,
            message=form.message.data
        )
        db.session.add(message)
        db.session.commit()
        flash('Your message has been sent. Thank you!', 'success')
        return redirect(url_for('main.contact'))
    
    return render_template('contact.html', form=form)

@main_bp.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    reviews = Review.query.filter_by(product_id=product_id).order_by(Review.created_at.desc()).all()
    related_products = Product.query.filter_by(category_id=product.category_id).filter(Product.id != product_id).limit(4).all()
    
    return render_template('product_detail.html', product=product, reviews=reviews, related_products=related_products)

@main_bp.route('/locations')
def locations():
    return render_template('locations.html')

@main_bp.app_errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404

@main_bp.app_errorhandler(500)
def internal_server_error(e):
    return render_template('errors/500.html'), 500
