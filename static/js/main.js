/**
 * Dragon Coffee Shop - Main JavaScript
 * Handles client-side functionality for the main website
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize Bootstrap tooltips
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));
    
    // Initialize Bootstrap popovers
    const popoverTriggerList = document.querySelectorAll('[data-bs-toggle="popover"]');
    const popoverList = [...popoverTriggerList].map(popoverTriggerEl => new bootstrap.Popover(popoverTriggerEl));
    
    // Animate elements when they come into view
    animateOnScroll();
    
    // Handle quantity controls for product detail page
    setupQuantityControls();
    
    // Initialize category navigation on menu page
    setupCategoryNav();
    
    // Update cart badge with current items count
    updateCartBadge();
});

/**
 * Add animation classes to elements when they scroll into view
 */
function animateOnScroll() {
    const animatedElements = document.querySelectorAll('.animate-on-scroll');
    
    if (animatedElements.length === 0) return;
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animate__animated');
                
                // Add the specific animation class based on data attribute
                const animation = entry.target.dataset.animation || 'animate__fadeIn';
                entry.target.classList.add(animation);
                
                // Unobserve after animation
                observer.unobserve(entry.target);
            }
        });
    }, {
        threshold: 0.1
    });
    
    animatedElements.forEach(element => {
        observer.observe(element);
    });
}

/**
 * Set up the quantity increment/decrement controls
 */
function setupQuantityControls() {
    const decrementBtns = document.querySelectorAll('.quantity-btn.decrement');
    const incrementBtns = document.querySelectorAll('.quantity-btn.increment');
    const quantityInputs = document.querySelectorAll('.quantity-input');
    
    decrementBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const input = this.parentNode.querySelector('.quantity-input');
            const currentValue = parseInt(input.value);
            if (currentValue > 1) {
                input.value = currentValue - 1;
            }
        });
    });
    
    incrementBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const input = this.parentNode.querySelector('.quantity-input');
            const currentValue = parseInt(input.value);
            input.value = currentValue + 1;
        });
    });
    
    quantityInputs.forEach(input => {
        input.addEventListener('change', function() {
            // Ensure value is at least 1
            if (this.value < 1 || isNaN(this.value)) {
                this.value = 1;
            }
        });
    });
}

/**
 * Set up the category navigation on the menu page
 */
function setupCategoryNav() {
    const categoryLinks = document.querySelectorAll('.category-nav .nav-link');
    
    categoryLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            // Remove active class from all links
            categoryLinks.forEach(navLink => {
                navLink.classList.remove('active');
            });
            
            // Add active class to clicked link
            this.classList.add('active');
        });
    });
}

/**
 * Update the cart badge with the current number of items in cart
 */
function updateCartBadge() {
    fetch('/order/cart-count')
        .then(response => response.json())
        .then(data => {
            const badge = document.querySelector('.cart-badge');
            if (badge && data.count > 0) {
                badge.textContent = data.count;
                badge.style.display = 'block';
            } else if (badge) {
                badge.style.display = 'none';
            }
        })
        .catch(error => console.error('Error updating cart badge:', error));
}

/**
 * Add a product to the cart
 * @param {number} productId - ID of the product
 * @param {number} quantity - Quantity to add
 */
function addToCart(productId, quantity = 1, notes = '') {
    // Build form data
    const formData = new FormData();
    formData.append('product_id', productId);
    formData.append('quantity', quantity);
    if (notes) {
        formData.append('notes', notes);
    }
    
    // Send post request
    fetch('/order/add-to-cart', {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (response.ok) {
            // Show success toast
            const toast = new bootstrap.Toast(document.getElementById('cartToast'));
            toast.show();
            
            // Update cart badge
            updateCartBadge();
        } else {
            console.error('Failed to add to cart');
        }
    })
    .catch(error => console.error('Error adding to cart:', error));
}

/**
 * Handle contact form submission
 */
function submitContactForm(event) {
    event.preventDefault();
    
    const form = event.target;
    const formData = new FormData(form);
    
    fetch('/contact', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Show success message
            const successAlert = document.getElementById('contactSuccess');
            successAlert.classList.remove('d-none');
            
            // Clear form
            form.reset();
            
            // Hide success after 5 seconds
            setTimeout(() => {
                successAlert.classList.add('d-none');
            }, 5000);
        } else {
            // Show error message
            const errorAlert = document.getElementById('contactError');
            errorAlert.textContent = data.error || 'An error occurred. Please try again.';
            errorAlert.classList.remove('d-none');
            
            // Hide error after 5 seconds
            setTimeout(() => {
                errorAlert.classList.add('d-none');
            }, 5000);
        }
    })
    .catch(error => {
        console.error('Error submitting form:', error);
        
        // Show error message
        const errorAlert = document.getElementById('contactError');
        errorAlert.textContent = 'An error occurred. Please try again.';
        errorAlert.classList.remove('d-none');
    });
}
