/**
 * Dragon Coffee Shop - Cart JavaScript
 * Handles client-side functionality for the shopping cart and checkout
 */

document.addEventListener('DOMContentLoaded', function() {
    // Set up quantity controls in cart
    setupCartQuantityControls();
    
    // Set up order type toggle in checkout
    setupOrderTypeToggle();
    
    // Set up payment method selection in checkout
    setupPaymentMethodSelection();
    
    // Handle update cart button clicks
    setupUpdateCartButtons();
    
    // Handle remove from cart button clicks
    setupRemoveFromCartButtons();
    
    // Calculate cart totals
    updateCartTotals();
    
    // Handle checkout form submission
    setupCheckoutForm();
});

/**
 * Set up the quantity increment/decrement controls in the cart
 */
function setupCartQuantityControls() {
    const decrementBtns = document.querySelectorAll('.cart-quantity-btn.decrement');
    const incrementBtns = document.querySelectorAll('.cart-quantity-btn.increment');
    const quantityInputs = document.querySelectorAll('.cart-quantity-input');
    
    decrementBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const input = this.parentNode.querySelector('.cart-quantity-input');
            const currentValue = parseInt(input.value);
            if (currentValue > 1) {
                input.value = currentValue - 1;
                
                // Update subtotal for this item
                updateItemSubtotal(input);
                
                // Update cart totals
                updateCartTotals();
            }
        });
    });
    
    incrementBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const input = this.parentNode.querySelector('.cart-quantity-input');
            const currentValue = parseInt(input.value);
            input.value = currentValue + 1;
            
            // Update subtotal for this item
            updateItemSubtotal(input);
            
            // Update cart totals
            updateCartTotals();
        });
    });
    
    quantityInputs.forEach(input => {
        input.addEventListener('change', function() {
            // Ensure value is at least 1
            if (this.value < 1 || isNaN(this.value)) {
                this.value = 1;
            }
            
            // Update subtotal for this item
            updateItemSubtotal(this);
            
            // Update cart totals
            updateCartTotals();
        });
    });
}

/**
 * Update the subtotal for a cart item based on quantity
 */
function updateItemSubtotal(quantityInput) {
    const cartItem = quantityInput.closest('.cart-item');
    const price = parseFloat(cartItem.dataset.price);
    const quantity = parseInt(quantityInput.value);
    const subtotal = price * quantity;
    
    // Update subtotal display
    const subtotalElement = cartItem.querySelector('.cart-item-subtotal');
    if (subtotalElement) {
        subtotalElement.textContent = `$${subtotal.toFixed(2)}`;
    }
    
    // Update hidden input for form submission
    const subtotalInput = cartItem.querySelector('.cart-item-subtotal-input');
    if (subtotalInput) {
        subtotalInput.value = subtotal.toFixed(2);
    }
}

/**
 * Set up the update cart buttons
 */
function setupUpdateCartButtons() {
    const updateButtons = document.querySelectorAll('.update-cart-btn');
    
    updateButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            
            const cartItem = this.closest('.cart-item');
            const productId = cartItem.dataset.productId;
            const quantity = parseInt(cartItem.querySelector('.cart-quantity-input').value);
            
            // Create form data
            const formData = new FormData();
            formData.append('product_id', productId);
            formData.append('quantity', quantity);
            
            // Send update request
            fetch('/order/update-cart', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (response.redirected) {
                    window.location.href = response.url;
                }
            })
            .catch(error => console.error('Error updating cart:', error));
        });
    });
}

/**
 * Set up the remove from cart buttons
 */
function setupRemoveFromCartButtons() {
    const removeButtons = document.querySelectorAll('.remove-from-cart-btn');
    
    removeButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            
            if (confirm('Are you sure you want to remove this item from your cart?')) {
                const productId = this.dataset.productId;
                
                // Send remove request
                fetch(`/order/remove-from-cart/${productId}`, {
                    method: 'POST'
                })
                .then(response => {
                    if (response.redirected) {
                        window.location.href = response.url;
                    }
                })
                .catch(error => console.error('Error removing from cart:', error));
            }
        });
    });
}

/**
 * Calculate and update cart totals
 */
function updateCartTotals() {
    // Get all cart items
    const cartItems = document.querySelectorAll('.cart-item');
    let subtotal = 0;
    
    // Calculate subtotal
    cartItems.forEach(item => {
        const price = parseFloat(item.dataset.price);
        const quantity = parseInt(item.querySelector('.cart-quantity-input').value);
        subtotal += price * quantity;
    });
    
    // Update subtotal display
    const subtotalElement = document.querySelector('.cart-subtotal-value');
    if (subtotalElement) {
        subtotalElement.textContent = `$${subtotal.toFixed(2)}`;
    }
    
    // Calculate and update tax (if applicable)
    const taxRate = 0.1; // 10% tax rate
    const tax = subtotal * taxRate;
    const taxElement = document.querySelector('.cart-tax-value');
    if (taxElement) {
        taxElement.textContent = `$${tax.toFixed(2)}`;
    }
    
    // Calculate and update total
    const total = subtotal + tax;
    const totalElement = document.querySelector('.cart-total-value');
    if (totalElement) {
        totalElement.textContent = `$${total.toFixed(2)}`;
    }
    
    // Update hidden input for form submission
    const subtotalInput = document.querySelector('#subtotal-input');
    const taxInput = document.querySelector('#tax-input');
    const totalInput = document.querySelector('#total-input');
    
    if (subtotalInput) subtotalInput.value = subtotal.toFixed(2);
    if (taxInput) taxInput.value = tax.toFixed(2);
    if (totalInput) totalInput.value = total.toFixed(2);
}

/**
 * Set up the order type toggle in checkout
 */
function setupOrderTypeToggle() {
    const orderTypeRadios = document.querySelectorAll('input[name="order_type"]');
    const deliveryAddressContainer = document.querySelector('#delivery-address-container');
    
    if (!orderTypeRadios.length || !deliveryAddressContainer) return;
    
    orderTypeRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            if (this.value === 'delivery') {
                deliveryAddressContainer.classList.remove('d-none');
                document.querySelector('#address').setAttribute('required', '');
            } else {
                deliveryAddressContainer.classList.add('d-none');
                document.querySelector('#address').removeAttribute('required');
            }
        });
    });
    
    // Initial check
    if (document.querySelector('input[name="order_type"]:checked').value === 'delivery') {
        deliveryAddressContainer.classList.remove('d-none');
        document.querySelector('#address').setAttribute('required', '');
    }
}

/**
 * Set up the payment method selection in checkout
 */
function setupPaymentMethodSelection() {
    const paymentMethodRadios = document.querySelectorAll('input[name="payment_method"]');
    const cardDetailsContainer = document.querySelector('#card-details-container');
    
    if (!paymentMethodRadios.length || !cardDetailsContainer) return;
    
    paymentMethodRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            if (this.value === 'card') {
                cardDetailsContainer.classList.remove('d-none');
                document.querySelector('#card_number').setAttribute('required', '');
                document.querySelector('#card_name').setAttribute('required', '');
                document.querySelector('#card_expiry').setAttribute('required', '');
                document.querySelector('#card_cvv').setAttribute('required', '');
            } else {
                cardDetailsContainer.classList.add('d-none');
                document.querySelector('#card_number').removeAttribute('required');
                document.querySelector('#card_name').removeAttribute('required');
                document.querySelector('#card_expiry').removeAttribute('required');
                document.querySelector('#card_cvv').removeAttribute('required');
            }
        });
    });
    
    // Initial check
    if (document.querySelector('input[name="payment_method"]:checked')?.value === 'card') {
        cardDetailsContainer.classList.remove('d-none');
        document.querySelector('#card_number').setAttribute('required', '');
        document.querySelector('#card_name').setAttribute('required', '');
        document.querySelector('#card_expiry').setAttribute('required', '');
        document.querySelector('#card_cvv').setAttribute('required', '');
    }
}

/**
 * Set up the checkout form submission
 */
function setupCheckoutForm() {
    const checkoutForm = document.querySelector('#checkout-form');
    
    if (!checkoutForm) return;
    
    checkoutForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        // Disable submit button to prevent double submission
        const submitButton = checkoutForm.querySelector('button[type="submit"]');
        submitButton.disabled = true;
        submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Processing...';
        
        // Send form data
        fetch('/order/checkout', {
            method: 'POST',
            body: new FormData(checkoutForm)
        })
        .then(response => {
            if (response.redirected) {
                window.location.href = response.url;
            } else {
                return response.json();
            }
        })
        .then(data => {
            if (data && data.error) {
                // Show error message
                const errorAlert = document.querySelector('#checkout-error');
                errorAlert.textContent = data.error;
                errorAlert.classList.remove('d-none');
                
                // Re-enable submit button
                submitButton.disabled = false;
                submitButton.innerHTML = 'Place Order';
                
                // Scroll to error message
                errorAlert.scrollIntoView({ behavior: 'smooth' });
            }
        })
        .catch(error => {
            console.error('Error during checkout:', error);
            
            // Show error message
            const errorAlert = document.querySelector('#checkout-error');
            errorAlert.textContent = 'An error occurred during checkout. Please try again.';
            errorAlert.classList.remove('d-none');
            
            // Re-enable submit button
            submitButton.disabled = false;
            submitButton.innerHTML = 'Place Order';
            
            // Scroll to error message
            errorAlert.scrollIntoView({ behavior: 'smooth' });
        });
    });
}
