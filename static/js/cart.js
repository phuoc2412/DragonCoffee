/**
 * Dragon Coffee Shop - Cart JavaScript
 * Handles client-side functionality for the shopping cart and checkout
 */

document.addEventListener('DOMContentLoaded', function() {
    // Update quantity
    const quantityInputs = document.querySelectorAll('.cart-quantity-input');
    quantityInputs.forEach(input => {
        input.addEventListener('change', function() {
            const form = this.closest('form');
            form.querySelector('.update-cart-btn').click();
        });
    });

    // Increment/decrement buttons
    const incrementBtns = document.querySelectorAll('.cart-quantity-btn.increment');
    const decrementBtns = document.querySelectorAll('.cart-quantity-btn.decrement');

    incrementBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const input = this.parentElement.querySelector('.cart-quantity-input');
            input.value = parseInt(input.value) + 1;
            input.dispatchEvent(new Event('change'));
        });
    });

    decrementBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const input = this.parentElement.querySelector('.cart-quantity-input');
            const newValue = parseInt(input.value) - 1;
            if (newValue >= 1) {
                input.value = newValue;
                input.dispatchEvent(new Event('change'));
            }
        });
    });


    // Set up update cart buttons (original function largely remains)
    setupUpdateCartButtons();

    // Set up remove from cart buttons (original function largely remains)
    setupRemoveFromCartButtons();

    // Calculate cart totals
    updateCartTotals();

    // Set up order type toggle in checkout (simplified)
    const orderTypeRadios = document.querySelectorAll('input[name="order_type"]');
    const deliveryAddressContainer = document.getElementById('delivery-address-container');
    if (orderTypeRadios && deliveryAddressContainer) {
        orderTypeRadios.forEach(radio => {
            radio.addEventListener('change', function() {
                if (this.value === 'delivery') {
                    deliveryAddressContainer.classList.remove('d-none');
                } else {
                    deliveryAddressContainer.classList.add('d-none');
                }
            });
        });
        // Initial check
        if (document.querySelector('input[name="order_type"]:checked').value === 'delivery') {
            deliveryAddressContainer.classList.remove('d-none');
        }
    }

    // Set up payment method selection in checkout (simplified)
    const paymentMethodRadios = document.querySelectorAll('input[name="payment_method"]');
    const cardDetailsContainer = document.getElementById('card-details-container');
    if (paymentMethodRadios && cardDetailsContainer) {
        paymentMethodRadios.forEach(radio => {
            radio.addEventListener('change', function() {
                if (this.value === 'card') {
                    cardDetailsContainer.classList.remove('d-none');
                } else {
                    cardDetailsContainer.classList.add('d-none');
                }
            });
        });
        // Initial check
        if (document.querySelector('input[name="payment_method"]:checked')?.value === 'card') {
            cardDetailsContainer.classList.remove('d-none');
        }
    }

    // Handle checkout form submission (original function remains)
    setupCheckoutForm();
});

/**
 * Set up the quantity increment/decrement controls in the cart
 * (This function is largely redundant now)
 */
function setupCartQuantityControls() {
    //This function is now redundant due to the new event listeners in DOMContentLoaded
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
    //This function is now largely redundant due to the new event listeners in DOMContentLoaded
}

/**
 * Set up the payment method selection in checkout
 */
function setupPaymentMethodSelection() {
    //This function is now largely redundant due to the new event listeners in DOMContentLoaded
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