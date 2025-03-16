/**
 * Dragon Coffee Shop - Inventory Management JavaScript
 */

document.addEventListener('DOMContentLoaded', function() {
    // Inventory search and filter functionality
    setupInventorySearch();
    
    // Batch update functionality
    setupBatchUpdate();
    
    // Stock update form submission
    setupStockUpdateForms();
    
    // Stock history chart
    setupStockHistoryCharts();
});

/**
 * Set up inventory search and filtering
 */
function setupInventorySearch() {
    const inventorySearch = document.getElementById('inventorySearch');
    const inventoryTable = document.getElementById('inventoryTable');
    const inventoryFilter = document.getElementById('inventoryFilter');
    
    if (inventorySearch && inventoryTable) {
        inventorySearch.addEventListener('input', function() {
            filterInventory();
        });
    }
    
    if (inventoryFilter && inventoryTable) {
        inventoryFilter.addEventListener('change', function() {
            filterInventory();
        });
    }
    
    function filterInventory() {
        const searchTerm = inventorySearch.value.toLowerCase();
        const filterValue = inventoryFilter.value;
        const rows = inventoryTable.querySelectorAll('tbody tr');
        
        rows.forEach(row => {
            const productName = row.querySelector('td:first-child').textContent.toLowerCase();
            const category = row.querySelector('td:nth-child(2)').textContent.toLowerCase();
            const statusMatch = filterValue === 'all' || row.dataset.status === filterValue;
            
            if ((productName.includes(searchTerm) || category.includes(searchTerm)) && statusMatch) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });
    }
}

/**
 * Set up batch update functionality
 */
function setupBatchUpdate() {
    const batchFileInput = document.getElementById('batchFile');
    const batchForm = document.querySelector('#batchUpdateModal form');
    
    if (batchFileInput && batchForm) {
        batchFileInput.addEventListener('change', handleBatchFileUpload);
        batchForm.addEventListener('submit', handleBatchFormSubmit);
    }
    
    // Show more products in batch update modal
    const showMoreBtn = document.querySelector('#batchUpdateModal .btn-link');
    if (showMoreBtn) {
        showMoreBtn.addEventListener('click', function() {
            loadMoreProductsForBatchUpdate(this);
        });
    }
}

/**
 * Handle CSV file upload for batch inventory update
 */
function handleBatchFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    if (file.type !== 'text/csv' && !file.name.endsWith('.csv')) {
        alert('Please upload a CSV file');
        event.target.value = '';
        return;
    }
    
    const reader = new FileReader();
    reader.onload = function(e) {
        const contents = e.target.result;
        parseCSVForBatchUpdate(contents);
    };
    reader.readAsText(file);
}

/**
 * Parse CSV content for batch update
 */
function parseCSVForBatchUpdate(csvContent) {
    const lines = csvContent.split('\n');
    const header = lines[0].split(',');
    
    // Check if the CSV has the required columns
    const productIdIndex = header.findIndex(col => col.trim().toLowerCase() === 'product_id');
    const quantityIndex = header.findIndex(col => col.trim().toLowerCase() === 'quantity');
    
    if (productIdIndex === -1 || quantityIndex === -1) {
        alert('CSV file must contain product_id and quantity columns');
        return;
    }
    
    // Update form values based on CSV content
    for (let i = 1; i < lines.length; i++) {
        if (!lines[i].trim()) continue;
        
        const values = lines[i].split(',');
        const productId = values[productIdIndex].trim();
        const quantity = values[quantityIndex].trim();
        
        const input = document.querySelector(`input[name="quantity_${productId}"]`);
        if (input) {
            input.value = quantity;
        }
    }
}

/**
 * Handle batch update form submission
 */
function handleBatchFormSubmit(event) {
    event.preventDefault();
    
    const formData = new FormData(event.target);
    const updates = [];
    
    // Collect all inventory updates from the form
    for (const [name, value] of formData.entries()) {
        if (name.startsWith('quantity_')) {
            const id = name.replace('quantity_', '');
            updates.push({ id, quantity: value });
        }
    }
    
    if (updates.length === 0) {
        alert('No inventory updates specified');
        return;
    }
    
    // Send batch update request to server
    fetch('/admin/inventory/batch-update', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ updates }),
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('Cập nhật tồn kho thành công');
            window.location.reload();
        } else {
            alert('Lỗi cập nhật tồn kho: ' + data.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Không thể cập nhật tồn kho. Vui lòng thử lại.');
    });
}

/**
 * Load more products for batch update
 */
function loadMoreProductsForBatchUpdate(button) {
    const table = button.closest('table');
    const tbody = table.querySelector('tbody');
    const lastRow = button.closest('tr');
    
    // Make an AJAX request to get more products
    fetch('/admin/api/inventory-items?skip=' + (table.querySelectorAll('tr').length - 1))
        .then(response => response.json())
        .then(data => {
            if (data.items && data.items.length > 0) {
                // Create rows for additional products
                data.items.forEach(item => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td>${item.product_name}</td>
                        <td>${item.quantity} ${item.unit || 'units'}</td>
                        <td>
                            <input type="number" class="form-control" name="quantity_${item.id}" value="${item.quantity}" min="0">
                        </td>
                    `;
                    tbody.insertBefore(tr, lastRow);
                });
                
                // Update or remove the "Show More" button
                if (data.has_more) {
                    lastRow.querySelector('button').textContent = 'Xem thêm sản phẩm';
                } else {
                    lastRow.remove();
                }
            } else {
                lastRow.remove();
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Không thể tải thêm sản phẩm');
        });
}

/**
 * Set up stock update forms
 */
function setupStockUpdateForms() {
    const forms = document.querySelectorAll('.inventory-update-form');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(event) {
            event.preventDefault();
            
            const inventoryId = form.dataset.inventoryId;
            const quantity = form.querySelector('input[name="quantity"]').value;
            
            // Send AJAX request to update inventory
            fetch(form.action, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `quantity=${quantity}`,
            })
            .then(response => response.text())
            .then(() => {
                // Close modal and reload page
                const modal = bootstrap.Modal.getInstance(document.getElementById(`updateStockModal${inventoryId}`));
                modal.hide();
                window.location.reload();
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Không thể cập nhật tồn kho. Vui lòng thử lại.');
            });
        });
    });
}

/**
 * Set up stock history charts
 */
function setupStockHistoryCharts() {
    // This would be implemented if we had stock history data
    // For now, we'll just show a placeholder
    const historyModals = document.querySelectorAll('[id^="historyModal"]');
    
    historyModals.forEach(modal => {
        const modalBody = modal.querySelector('.modal-body');
        const productId = modal.id.replace('historyModal', '');
        
        // Create a placeholder for the chart
        const chartContainer = document.createElement('div');
        chartContainer.id = `stockChart${productId}`;
        chartContainer.style.height = '300px';
        modalBody.innerHTML = '';
        modalBody.appendChild(chartContainer);
        
        // Create placeholder data - this would come from the server in a real implementation
        const dates = [];
        const quantities = [];
        
        // Generate placeholder data for the last 7 days
        const today = new Date();
        for (let i = 6; i >= 0; i--) {
            const date = new Date(today);
            date.setDate(date.getDate() - i);
            dates.push(date.toLocaleDateString());
            
            // Random quantity for demonstration
            quantities.push(Math.floor(Math.random() * 100) + 20);
        }
        
        // Create and render the chart
        new Chart(chartContainer, {
            type: 'line',
            data: {
                labels: dates,
                datasets: [{
                    label: 'Mức tồn kho',
                    data: quantities,
                    borderColor: '#4e73df',
                    backgroundColor: 'rgba(78, 115, 223, 0.05)',
                    borderWidth: 2,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Số lượng'
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Ngày'
                        }
                    }
                }
            }
        });
    });
}