/**
 * Dragon Coffee Shop - Admin Panel JavaScript
 * Handles client-side functionality for the admin dashboard and POS system
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize Bootstrap tooltips
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));
    
    // Initialize sidebar toggle for mobile
    setupSidebarToggle();
    
    // Initialize charts for dashboard
    initCharts();
    
    // Setup POS system if on POS page
    if (document.querySelector('.pos-container')) {
        setupPOS();
    }
    
    // Setup inventory management if on inventory page
    if (document.querySelector('.inventory-table')) {
        setupInventoryManagement();
    }
    
    // Setup order management if on orders page
    if (document.querySelector('.orders-table')) {
        setupOrderManagement();
    }
    
    // Setup confirmation for delete actions
    setupDeleteConfirmations();
});

/**
 * Set up the mobile sidebar toggle
 */
function setupSidebarToggle() {
    const sidebarToggle = document.querySelector('.sidebar-toggle');
    const sidebar = document.querySelector('.admin-sidebar');
    
    if (!sidebarToggle || !sidebar) return;
    
    sidebarToggle.addEventListener('click', function() {
        sidebar.classList.toggle('show');
    });
    
    // Close sidebar when clicking outside on mobile
    document.addEventListener('click', function(event) {
        const isClickInsideSidebar = sidebar.contains(event.target);
        const isClickOnToggle = sidebarToggle.contains(event.target);
        
        if (!isClickInsideSidebar && !isClickOnToggle && sidebar.classList.contains('show')) {
            sidebar.classList.remove('show');
        }
    });
}

/**
 * Initialize dashboard charts
 */
function initCharts() {
    // Sales Chart
    const salesChartCanvas = document.getElementById('salesChart');
    if (salesChartCanvas) {
        // Get chart data from the data attribute
        const chartData = JSON.parse(salesChartCanvas.dataset.chart || '{"labels":[],"values":[]}');
        
        new Chart(salesChartCanvas, {
            type: 'line',
            data: {
                labels: chartData.labels,
                datasets: [{
                    label: 'Sales',
                    data: chartData.values,
                    backgroundColor: 'rgba(139, 0, 0, 0.1)',
                    borderColor: '#8B0000',
                    borderWidth: 2,
                    tension: 0.4,
                    pointBackgroundColor: '#8B0000',
                    pointRadius: 4
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (label) {
                                    label += ': ';
                                }
                                if (context.parsed.y !== null) {
                                    label += new Intl.NumberFormat('en-US', {
                                        style: 'currency',
                                        currency: 'USD'
                                    }).format(context.parsed.y);
                                }
                                return label;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: {
                            display: false
                        }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return '$' + value;
                            }
                        }
                    }
                }
            }
        });
    }
    
    // Products Chart
    const productsChartCanvas = document.getElementById('productsChart');
    if (productsChartCanvas) {
        // Get chart data from the data attribute
        const chartData = JSON.parse(productsChartCanvas.dataset.chart || '{"labels":[],"values":[]}');
        
        new Chart(productsChartCanvas, {
            type: 'bar',
            data: {
                labels: chartData.labels,
                datasets: [{
                    label: 'Products Sold',
                    data: chartData.values,
                    backgroundColor: '#FF4500',
                    borderColor: '#FF4500',
                    borderWidth: 1
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true
                    },
                    y: {
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });
    }
}

/**
 * Set up the POS system functionality
 */
function setupPOS() {
    // Elements
    const categoryButtons = document.querySelectorAll('.pos-category-btn');
    const searchInput = document.querySelector('#pos-search');
    const productsContainer = document.querySelector('.pos-product-grid');
    const cartItemsContainer = document.querySelector('.pos-cart-items');
    const cartTotalElement = document.querySelector('.pos-cart-total-amount');
    const orderTypeOptions = document.querySelectorAll('.pos-order-type-option');
    const paymentMethodOptions = document.querySelectorAll('.pos-payment-method');
    const checkoutButton = document.querySelector('.pos-checkout-btn');
    const clearCartButton = document.querySelector('.pos-clear-btn');
    
    // Cart state
    let cart = [];
    let selectedOrderType = 'dine-in';
    let selectedPaymentMethod = 'cash';
    
    // Initialize
    loadProducts();
    
    // Event listeners
    categoryButtons.forEach(button => {
        button.addEventListener('click', function() {
            // Remove active class from all buttons
            categoryButtons.forEach(btn => btn.classList.remove('active'));
            
            // Add active class to clicked button
            this.classList.add('active');
            
            // Load products for this category
            const categoryId = this.dataset.categoryId;
            loadProducts(categoryId);
        });
    });
    
    searchInput.addEventListener('input', function() {
        const query = this.value.trim();
        
        if (query.length >= 2) {
            // Get the selected category
            const activeCategory = document.querySelector('.pos-category-btn.active');
            const categoryId = activeCategory ? activeCategory.dataset.categoryId : '';
            
            // Load products with search query
            loadProducts(categoryId, query);
        } else if (query.length === 0) {
            // Load all products for the selected category
            const activeCategory = document.querySelector('.pos-category-btn.active');
            const categoryId = activeCategory ? activeCategory.dataset.categoryId : '';
            
            loadProducts(categoryId);
        }
    });
    
    orderTypeOptions.forEach(option => {
        option.addEventListener('click', function() {
            // Remove active class from all options
            orderTypeOptions.forEach(opt => opt.classList.remove('active'));
            
            // Add active class to clicked option
            this.classList.add('active');
            
            // Update selected order type
            selectedOrderType = this.dataset.type;
        });
    });
    
    paymentMethodOptions.forEach(option => {
        option.addEventListener('click', function() {
            // Remove active class from all options
            paymentMethodOptions.forEach(opt => opt.classList.remove('active'));
            
            // Add active class to clicked option
            this.classList.add('active');
            
            // Update selected payment method
            selectedPaymentMethod = this.dataset.method;
        });
    });
    
    if (clearCartButton) {
        clearCartButton.addEventListener('click', function() {
            // Clear cart
            cart = [];
            renderCart();
        });
    }
    
    if (checkoutButton) {
        checkoutButton.addEventListener('click', function() {
            if (cart.length === 0) {
                alert('Cart is empty! Please add items before checkout.');
                return;
            }
            
            // Calculate total
            const total = cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
            
            // Prepare order data
            const orderData = {
                items: cart,
                total_amount: total,
                order_type: selectedOrderType,
                payment_method: selectedPaymentMethod,
                notes: document.querySelector('#pos-order-notes')?.value || ''
            };
            
            // Send order to server
            fetch('/admin/api/create-order', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(orderData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Show success message
                    alert(`Order #${data.order_number} created successfully!`);
                    
                    // Clear cart
                    cart = [];
                    renderCart();
                    
                    // Reset notes
                    if (document.querySelector('#pos-order-notes')) {
                        document.querySelector('#pos-order-notes').value = '';
                    }
                } else {
                    alert('Failed to create order: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(error => {
                console.error('Error creating order:', error);
                alert('An error occurred while creating the order.');
            });
        });
    }
    
    /**
     * Load products from API
     */
    function loadProducts(categoryId = '', query = '') {
        // Show loading
        productsContainer.innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary" role="status"></div><p class="mt-2">Loading products...</p></div>';
        
        // Build URL
        let url = '/admin/api/products';
        const params = new URLSearchParams();
        if (categoryId) params.append('category_id', categoryId);
        if (query) params.append('q', query);
        if (params.toString()) url += '?' + params.toString();
        
        // Fetch products
        fetch(url)
            .then(response => response.json())
            .then(products => {
                if (products.length === 0) {
                    productsContainer.innerHTML = '<div class="text-center py-5"><p>No products found.</p></div>';
                    return;
                }
                
                // Render products
                productsContainer.innerHTML = '';
                products.forEach(product => {
                    const productCard = document.createElement('div');
                    productCard.className = 'pos-product-card';
                    productCard.dataset.productId = product.id;
                    
                    productCard.innerHTML = `
                        <img src="${product.image_url || 'https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd'}" 
                             alt="${product.name}" class="pos-product-image">
                        <div class="pos-product-info">
                            <div class="pos-product-title">${product.name}</div>
                            <div class="pos-product-price">$${product.price.toFixed(2)}</div>
                        </div>
                    `;
                    
                    // Add click event
                    productCard.addEventListener('click', function() {
                        addToCart(product);
                    });
                    
                    productsContainer.appendChild(productCard);
                });
            })
            .catch(error => {
                console.error('Error loading products:', error);
                productsContainer.innerHTML = '<div class="text-center py-5"><p>Error loading products. Please try again.</p></div>';
            });
    }
    
    /**
     * Add a product to the cart
     */
    function addToCart(product) {
        // Check if product already in cart
        const existingItemIndex = cart.findIndex(item => item.product_id === product.id);
        
        if (existingItemIndex !== -1) {
            // Increment quantity
            cart[existingItemIndex].quantity += 1;
        } else {
            // Add new item
            cart.push({
                product_id: product.id,
                name: product.name,
                price: product.price,
                quantity: 1,
                notes: ''
            });
        }
        
        // Update cart display
        renderCart();
    }
    
    /**
     * Render the cart
     */
    function renderCart() {
        if (!cartItemsContainer) return;
        
        if (cart.length === 0) {
            cartItemsContainer.innerHTML = '<div class="text-center py-4"><p>Cart is empty</p></div>';
            cartTotalElement.textContent = '$0.00';
            return;
        }
        
        // Clear cart
        cartItemsContainer.innerHTML = '';
        
        // Add each item
        cart.forEach((item, index) => {
            const cartItem = document.createElement('div');
            cartItem.className = 'pos-cart-item';
            
            cartItem.innerHTML = `
                <div class="pos-cart-product">
                    <div class="pos-cart-product-name">${item.name}</div>
                    <div class="pos-cart-product-price">$${item.price.toFixed(2)}</div>
                </div>
                <div class="pos-cart-quantity">
                    <button type="button" class="pos-cart-quantity-btn" data-action="decrease" data-index="${index}">-</button>
                    <input type="number" class="pos-cart-quantity-input" value="${item.quantity}" min="1" data-index="${index}">
                    <button type="button" class="pos-cart-quantity-btn" data-action="increase" data-index="${index}">+</button>
                </div>
                <div class="pos-cart-subtotal">$${(item.price * item.quantity).toFixed(2)}</div>
                <div class="pos-cart-remove" data-index="${index}">×</div>
            `;
            
            cartItemsContainer.appendChild(cartItem);
        });
        
        // Add event listeners
        document.querySelectorAll('.pos-cart-quantity-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const index = parseInt(this.dataset.index);
                const action = this.dataset.action;
                
                if (action === 'decrease') {
                    if (cart[index].quantity > 1) {
                        cart[index].quantity -= 1;
                    } else {
                        cart.splice(index, 1);
                    }
                } else if (action === 'increase') {
                    cart[index].quantity += 1;
                }
                
                renderCart();
            });
        });
        
        document.querySelectorAll('.pos-cart-quantity-input').forEach(input => {
            input.addEventListener('change', function() {
                const index = parseInt(this.dataset.index);
                const quantity = parseInt(this.value);
                
                if (quantity >= 1) {
                    cart[index].quantity = quantity;
                } else {
                    this.value = 1;
                    cart[index].quantity = 1;
                }
                
                renderCart();
            });
        });
        
        document.querySelectorAll('.pos-cart-remove').forEach(btn => {
            btn.addEventListener('click', function() {
                const index = parseInt(this.dataset.index);
                cart.splice(index, 1);
                renderCart();
            });
        });
        
        // Update total
        const total = cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
        cartTotalElement.textContent = `$${total.toFixed(2)}`;
    }
}

/**
 * Set up inventory management functionality
 */
function setupInventoryManagement() {
    const inventoryForms = document.querySelectorAll('.inventory-update-form');
    
    inventoryForms.forEach(form => {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const inventoryId = this.dataset.inventoryId;
            const quantityInput = this.querySelector('input[name="quantity"]');
            const quantity = parseInt(quantityInput.value);
            
            if (isNaN(quantity) || quantity < 0) {
                alert('Please enter a valid quantity.');
                return;
            }
            
            // Submit form
            this.submit();
        });
    });
}

/**
 * Set up order management functionality
 */
function setupOrderManagement() {
    const statusSelects = document.querySelectorAll('.order-status-select');
    
    statusSelects.forEach(select => {
        select.addEventListener('change', function() {
            const form = this.closest('form');
            form.submit();
        });
    });
}

/**
 * Set up confirmation dialogs for delete actions
 */
function setupDeleteConfirmations() {
    const deleteButtons = document.querySelectorAll('[data-confirm]');
    
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            const message = this.dataset.confirm || 'Are you sure you want to delete this item?';
            
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });
}
