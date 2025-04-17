// static/js/inventory.js

document.addEventListener('DOMContentLoaded', function() {
    console.log("Inventory page JS loaded.");

    // --- DOM Elements ---
    const searchInput = document.getElementById('inventorySearchInput');
    const statusFilter = document.getElementById('inventoryStatusFilter');
    const tableBody = document.getElementById('inventoryTableBody');
    const tableContainer = document.getElementById('inventoryTableContainer');
    const noInventoryMessage = document.getElementById('noInventoryMessage');
    const loadingSpinner = document.getElementById('loadingSpinnerInv');
    const paginationContainer = document.getElementById('paginationContainerInv');
    const exportCurrentCsvLink = document.getElementById('exportCurrentCsvLink');

    // --- Modals ---
    const historyModal = document.getElementById('historyModal');
    const updateStockModal = document.getElementById('updateStockModal');
    const updateStockForm = document.getElementById('updateStockForm');
    const batchFileInput = document.getElementById('batchFile'); // Added for batch update setup
    const batchForm = document.getElementById('batchUpdateForm'); // Added for batch update setup


    let debounceTimeoutInventory; // Timeout ID for debouncing

    // --- Hàm Fetch Data qua API ---
    function fetchInventory(query = '', status = '') {
        if (loadingSpinner) loadingSpinner.style.display = 'flex';
        if (tableBody) tableBody.innerHTML = '';
        if (noInventoryMessage) noInventoryMessage.style.display = 'none';
        if (paginationContainer) paginationContainer.style.display = 'none';

        const apiUrl = `/admin/api/search-inventory?q=${encodeURIComponent(query)}&status=${encodeURIComponent(status)}`;
        console.log("Fetching Inventory API:", apiUrl);

        fetch(apiUrl)
            .then(response => {
                if (!response.ok) { throw new Error(`Network error (${response.status})`); }
                return response.json();
            })
            .then(data => {
                if (loadingSpinner) loadingSpinner.style.display = 'none';

                if (data.success && data.html) {
                    if (tableBody) {
                        tableBody.innerHTML = data.html;
                        reinitializeBootstrapComponents(tableBody); // Re-init Tooltips for new content
                    } else { console.error("inventoryTableBody element not found!"); }

                    if (data.count === 0) {
                        if (noInventoryMessage) noInventoryMessage.style.display = 'block';
                    } else {
                        if (noInventoryMessage) noInventoryMessage.style.display = 'none';
                    }
                    // Hide static pagination container when using dynamic search/filter
                    if (paginationContainer) paginationContainer.style.display = 'none';
                } else {
                    throw new Error(data.message || "Lỗi không xác định từ API");
                }
            })
            .catch(error => {
                console.error('Fetch Inventory Error:', error);
                if (loadingSpinner) loadingSpinner.style.display = 'none';
                if (noInventoryMessage) {
                    noInventoryMessage.innerHTML = `<i class="fas fa-exclamation-circle fa-3x mb-3"></i><br>Lỗi: ${error.message}. Vui lòng thử lại.`;
                    noInventoryMessage.style.display = 'block';
                }
                if (tableBody) tableBody.innerHTML = '';
                 if (paginationContainer) paginationContainer.style.display = 'none';
            });
    }

    // --- Hàm thực hiện tìm kiếm/lọc với Debounce ---
    function performInventorySearch() {
        clearTimeout(debounceTimeoutInventory);
        debounceTimeoutInventory = setTimeout(() => {
            const query = searchInput ? searchInput.value.trim() : '';
            const status = statusFilter ? statusFilter.value : '';
            fetchInventory(query, status);

            // Cập nhật link Export
            if (exportCurrentCsvLink) {
                 const exportUrl = new URL(exportCurrentCsvLink.href, window.location.origin);
                 exportUrl.searchParams.set('search', query); // Dùng param 'search'
                 exportUrl.searchParams.set('status', status); // Dùng param 'status'
                 exportCurrentCsvLink.href = exportUrl.pathname + exportUrl.search;
                 // console.log("Updated Export URL:", exportCurrentCsvLink.href);
            }

            // Cập nhật URL trình duyệt (optional)
             const currentUrl = new URL(window.location);
             currentUrl.searchParams.set('search', query); // Đồng bộ với form GET gốc
             currentUrl.searchParams.set('status_filter', status); // Đồng bộ với form GET gốc
             currentUrl.searchParams.delete('page'); // Remove page param
             history.pushState({}, '', currentUrl);

        }, 550);
    }

    // --- Gán sự kiện cho Input và Select ---
    if (searchInput) {
        searchInput.addEventListener('input', performInventorySearch);
    }
    if (statusFilter) {
        statusFilter.addEventListener('change', performInventorySearch);
    }

    // --- Xử lý Modal History ---
    if (historyModal) {
        historyModal.addEventListener('show.bs.modal', function (event) {
            var button = event.relatedTarget;
            var itemId = button.getAttribute('data-item-id');
            var productName = button.getAttribute('data-product-name') || '[Sản phẩm không rõ]';
            var modalTitle = historyModal.querySelector('.modal-title');
            var productNameSpan = historyModal.querySelector('#historyProductName');
            var historyContentDiv = historyModal.querySelector('#historyContent');

            if(modalTitle) modalTitle.textContent = 'Lịch sử: ' + productName;
            if(productNameSpan) productNameSpan.textContent = productName;

            if (!historyContentDiv) {
                 console.error("DOM Error: #historyContent not found.");
                 if(modalTitle) modalTitle.textContent = "Lỗi UI";
                 let modalBody = historyModal.querySelector('.modal-body');
                 if(modalBody) modalBody.innerHTML = "<p class='text-danger'>Lỗi giao diện modal.</p>";
                 return;
            }

            historyContentDiv.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Đang tải...</span></div></div>';

            if (itemId) {
                const historyUrl = `/admin/inventory/${itemId}/history`;
                fetch(historyUrl)
                    .then(response => {
                        if (!response.ok) { return response.text().then(text => {throw new Error(text || `Error ${response.status}`);}) }
                        return response.text();
                     })
                    .then(html => { if(historyContentDiv) historyContentDiv.innerHTML = html; })
                    .catch(error => {
                        if(historyContentDiv) historyContentDiv.innerHTML = `<div class="alert alert-danger p-2">Không thể tải lịch sử. Lỗi: ${error.message}</div>`;
                        console.error("History Fetch Error:", error);
                    });
            } else {
                 if(historyContentDiv) historyContentDiv.innerHTML = '<div class="alert alert-danger p-2">Lỗi: Thiếu ID Item.</div>';
                 console.error("Missing 'data-item-id' for history modal.");
             }
        });
    }

    // --- Xử lý Modal Update Stock (với AJAX submit) ---
    if (updateStockModal && updateStockForm) {
        updateStockModal.addEventListener('show.bs.modal', function (event) {
            var button = event.relatedTarget;
            var productName = button.getAttribute('data-product-name');
            var currentQty = button.getAttribute('data-current-quantity');
            var currentMinQty = button.getAttribute('data-current-min-quantity') || '10'; // Default min qty if missing
            var updateUrl = button.getAttribute('data-update-url'); // Action URL from button

            const nameSpan = updateStockModal.querySelector('#updateProductName');
            const qtyInput = updateStockModal.querySelector('#updateQuantity');
            const minQtyInput = updateStockModal.querySelector('#updateMinQuantity');

            if(nameSpan) nameSpan.textContent = productName;
            if(qtyInput) qtyInput.value = currentQty;
            if(minQtyInput) {
                minQtyInput.placeholder = `Để trống nếu giữ (${currentMinQty})`;
                minQtyInput.value = ''; // Always clear the min quantity input on open
            }
            updateStockForm.action = updateUrl || '#'; // Set form action dynamically
        });

        updateStockForm.addEventListener('submit', function(e) {
             e.preventDefault();
             const formData = new FormData(updateStockForm);
             const formAction = updateStockForm.action;
             const submitButton = updateStockForm.querySelector('button[type="submit"]');
             const originalButtonText = submitButton.innerHTML;

             submitButton.disabled = true;
             submitButton.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Đang lưu...`;

             const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
             const headers = {'Content-Type': 'application/x-www-form-urlencoded'};
             if (csrfToken) { headers['X-CSRFToken'] = csrfToken; }

             fetch(formAction, {
                method: 'POST',
                body: new URLSearchParams(formData).toString(),
                headers: headers
             })
             .then(response => {
                  if (response.ok && response.redirected && response.url.includes('/admin/inventory')) {
                       return { success: true, message: "Cập nhật thành công!" };
                  }
                  return response.text().then(text => { throw new Error(text.substring(0, 200) || response.statusText || `Lỗi HTTP ${response.status}`); });
             })
             .then(result => {
                  if (result.success) {
                       var modalInstance = bootstrap.Modal.getInstance(updateStockModal);
                       if (modalInstance) modalInstance.hide();
                       performInventorySearch(); // Reload table data
                       showToastAdmin("Cập nhật tồn kho thành công!", "success");
                  } else { throw new Error(result.message || "Cập nhật thất bại."); }
              })
             .catch(error => {
                  console.error("Update Stock Submit Error:", error);
                  showToastAdmin(`Lỗi cập nhật: ${error.message}`, "danger");
              })
             .finally(() => {
                 if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.innerHTML = originalButtonText;
                 }
             });
         });
    }

    // --- Xử lý Modal Batch Update ---
    if (batchFileInput && batchForm) {
        batchForm.addEventListener('submit', function(event) {
            const submitBtn = batchForm.querySelector('button[type="submit"]');
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Đang xử lý...';
            // Submit form bình thường, xử lý ở backend
            // Nếu muốn feedback tốt hơn có thể dùng AJAX và trả về JSON kết quả
        });
    }


    // Hàm khởi tạo lại Bootstrap components
    function reinitializeBootstrapComponents(container) {
        // Tooltip
        var tooltipTriggerList = [].slice.call(container.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.forEach(function(tooltipTriggerEl) {
             var oldTooltip = bootstrap.Tooltip.getInstance(tooltipTriggerEl);
             if (oldTooltip) { oldTooltip.dispose(); }
             new bootstrap.Tooltip(tooltipTriggerEl);
         });
        // Thêm Popover hoặc components khác nếu cần
    }

    // Helper Toast cho Admin (nếu chưa có ở base.js)
    function showToastAdmin(message, type = 'info') {
        let toastContainer = document.querySelector('.toast-container.position-fixed.top-0.end-0');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
            toastContainer.style.zIndex = 1090;
            document.body.appendChild(toastContainer);
        }
        const toastId = 'admin-toast-' + Date.now();
        const bgClass = type === 'success' ? 'bg-success' : (type === 'danger' ? 'bg-danger' : (type === 'warning' ? 'bg-warning' : 'bg-info'));
        const textClass = (type === 'warning' || type === 'light') ? 'text-dark' : 'text-white';
        const iconClass = type === 'success' ? 'fas fa-check-circle' : (type === 'danger' ? 'fas fa-exclamation-triangle' : (type === 'warning' ? 'fas fa-exclamation-circle' : 'fas fa-info-circle'));

        const toastHTML = `
            <div id="${toastId}" class="toast ${bgClass} ${textClass} border-0" role="alert" aria-live="assertive" aria-atomic="true" data-bs-delay="5000">
                <div class="d-flex">
                    <div class="toast-body d-flex align-items-center">
                        <i class="${iconClass} me-2"></i>
                        <span>${message}</span>
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
            </div>`;
        toastContainer.insertAdjacentHTML('beforeend', toastHTML);
        const toastEl = document.getElementById(toastId);
        const toast = new bootstrap.Toast(toastEl);
        toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
        toast.show();
    }

    // --- KHỞI TẠO TOOLTIP BAN ĐẦU ---
     var initialTooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
     var initialTooltipList = initialTooltipTriggerList.map(function (tooltipTriggerEl) {
         return new bootstrap.Tooltip(tooltipTriggerEl)
     });

});