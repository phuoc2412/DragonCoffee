// static/js/admin/inventory.js

document.addEventListener('DOMContentLoaded', function() {

    const searchInput = document.getElementById('inventorySearchInput');
    const statusFilter = document.getElementById('inventoryStatusFilter');
    const tableBody = document.getElementById('inventoryTableBody');
    const tableContainer = document.getElementById('inventoryTableContainer');
    const noInventoryMessage = document.getElementById('noInventoryMessage');
    const loadingSpinner = document.getElementById('loadingSpinnerInv');
    const paginationContainer = document.getElementById('paginationContainerInv');
    const exportCurrentCsvLink = document.getElementById('exportCurrentCsvLink');
    const historyModal = document.getElementById('historyModal');
    const updateStockModal = document.getElementById('updateStockModal');
    const updateStockForm = document.getElementById('updateStockForm');
    const batchFileInput = document.getElementById('batchFile');
    const batchForm = document.getElementById('batchUpdateForm');

    let debounceTimeoutInventory;

    // === XỬ LÝ CHO QR CODE MODAL ===
    const qrCodeModalElement = document.getElementById('qrCodeModal');
    let qrCodeModalInstance = null;
    if (qrCodeModalElement) {
        qrCodeModalInstance = new bootstrap.Modal(qrCodeModalElement, {
            keyboard: true,
        });
    }
    const qrProductNameModalSpan = document.getElementById('qrProductNameModal');
    const qrImageModalImg = document.getElementById('qrImageModal');
    const qrImageContainer = document.getElementById('qrImageContainer');
    const qrLoadingSpinner = qrImageContainer ? qrImageContainer.querySelector('.qr-image-loading') : null;

    function fetchInventory(query = '', status = '') {
        if (loadingSpinner) loadingSpinner.style.display = 'flex';
        if (tableBody) tableBody.innerHTML = '';
        if (noInventoryMessage) noInventoryMessage.style.display = 'none';
        if (paginationContainer) paginationContainer.style.display = 'none';

        const apiUrl = `/admin/api/search-inventory?q=${encodeURIComponent(query)}&status=${encodeURIComponent(status)}`;

        fetch(apiUrl)
            .then(response => {
                if (!response.ok) { throw new Error(`Lỗi mạng (${response.status})`); }
                return response.json();
            })
            .then(data => {
                if (loadingSpinner) loadingSpinner.style.display = 'none';

                if (data.success && data.html) {
                    if (tableBody) {
                        tableBody.innerHTML = data.html;
                        reinitializeBootstrapComponents(tableBody);
                    }
                    if (data.count === 0) {
                        if (noInventoryMessage) {
                           const noInvTextSpan = document.getElementById('noInventoryText');
                           if(noInvTextSpan) noInvTextSpan.textContent = (query || (status && status !== 'all')) ? 'Không tìm thấy mặt hàng nào khớp với bộ lọc.' : 'Chưa có dữ liệu tồn kho.';
                           noInventoryMessage.style.display = 'block';
                        }
                    } else {
                        if (noInventoryMessage) noInventoryMessage.style.display = 'none';
                    }
                    if (paginationContainer) paginationContainer.style.display = 'none';
                } else {
                    throw new Error(data.message || "Lỗi không xác định từ API");
                }
            })
            .catch(error => {
                console.error('Fetch Inventory Error:', error);
                if (loadingSpinner) loadingSpinner.style.display = 'none';
                if (noInventoryMessage) {
                    const noInvTextSpan = document.getElementById('noInventoryText');
                    if(noInvTextSpan) noInvTextSpan.innerHTML = `<i class="fas fa-exclamation-circle fa-3x mb-3"></i><br>Lỗi: ${error.message}. Vui lòng thử lại.`;
                    noInventoryMessage.style.display = 'block';
                }
                if (tableBody) tableBody.innerHTML = '';
                 if (paginationContainer) paginationContainer.style.display = 'none';
            });
    }

    function performInventorySearch() {
        clearTimeout(debounceTimeoutInventory);
        debounceTimeoutInventory = setTimeout(() => {
            const query = searchInput ? searchInput.value.trim() : '';
            const status = statusFilter ? statusFilter.value : '';
            fetchInventory(query, status);

            if (exportCurrentCsvLink) {
                 const exportUrl = new URL(exportCurrentCsvLink.href, window.location.origin);
                 exportUrl.searchParams.set('search', query);
                 exportUrl.searchParams.set('status', status);
                 exportCurrentCsvLink.href = exportUrl.pathname + exportUrl.search;
            }

             const currentUrl = new URL(window.location);
             currentUrl.searchParams.set('search', query);
             currentUrl.searchParams.set('status_filter', status);
             currentUrl.searchParams.delete('page');
             history.pushState({}, '', currentUrl);

        }, 550);
    }

    if (searchInput) {
        searchInput.addEventListener('input', performInventorySearch);
    }
    if (statusFilter) {
        statusFilter.addEventListener('change', performInventorySearch);
    }

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
                return;
            }

            historyContentDiv.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary" role="status"><span class="visually-hidden">Đang tải...</span></div></div>';

            if (itemId) {
                const historyUrl = `/admin/inventory/${itemId}/history`;
                fetch(historyUrl)
                    .then(response => {
                        if (!response.ok) { return response.text().then(text => {throw new Error(text || `Lỗi ${response.status}`);}) }
                        return response.text();
                     })
                    .then(html => { if(historyContentDiv) historyContentDiv.innerHTML = html; })
                    .catch(error => { if(historyContentDiv) historyContentDiv.innerHTML = `<div class="alert alert-danger p-2">Không thể tải lịch sử. Lỗi: ${error.message}</div>`; });
            } else { if(historyContentDiv) historyContentDiv.innerHTML = '<div class="alert alert-danger p-2">Lỗi: Thiếu ID Item.</div>'; }
        });
    }

    if (updateStockModal && updateStockForm) {
        updateStockModal.addEventListener('show.bs.modal', function (event) {
            var button = event.relatedTarget;
            var productName = button.getAttribute('data-product-name');
            var currentQty = button.getAttribute('data-current-quantity');
            var currentMinQty = button.getAttribute('data-current-min-quantity') || '10';
            var updateUrl = button.getAttribute('data-update-url');

            const nameSpan = updateStockModal.querySelector('#updateProductName');
            const qtyInput = updateStockModal.querySelector('#updateQuantity');
            const minQtyInput = updateStockModal.querySelector('#updateMinQuantity');

            if(nameSpan) nameSpan.textContent = productName;
            if(qtyInput) qtyInput.value = currentQty;
            if(minQtyInput) { minQtyInput.placeholder = `Để trống nếu giữ (${currentMinQty})`; minQtyInput.value = '';}

            if (updateUrl) { updateStockForm.action = updateUrl; }
             else { updateStockForm.action = '#'; console.error("Missing update URL for modal form."); }
        });

        updateStockForm.addEventListener('submit', function(e) {
             e.preventDefault();
             const formData = new FormData(updateStockForm);
             const formAction = updateStockForm.action;
             const submitButton = updateStockForm.querySelector('button[type="submit"]');
             const originalButtonText = 'Lưu thay đổi';

             if (!formAction || formAction === '#') {
                showToastAdmin("Lỗi cấu hình form, không thể gửi.", "danger");
                return;
             }

             submitButton.disabled = true;
             submitButton.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Đang lưu...`;

             const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
             const headers = { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'};
             if (csrfToken) { headers['X-CSRFToken'] = csrfToken; }

             fetch(formAction, {
                method: 'POST',
                body: new URLSearchParams(formData).toString(),
                headers: {
                    ...headers,
                    'Content-Type': 'application/x-www-form-urlencoded'
                 }
             })
             .then(response => {
                  if (response.ok) {
                       return response.json().catch(() => ({ success: true, message: "Cập nhật thành công (không có phản hồi JSON)!"}));
                  } else {
                      return response.json().then(errData => {
                           throw new Error(errData.message || response.statusText || `Lỗi HTTP ${response.status}`);
                      }).catch(() => {
                           throw new Error(response.statusText || `Lỗi HTTP ${response.status}`);
                      });
                  }
             })
             .then(result => {
                  if (result && result.success !== false) {
                       var modalInstance = bootstrap.Modal.getInstance(updateStockModal);
                       if (modalInstance) modalInstance.hide();
                       performInventorySearch();
                       showToastAdmin(result.message || "Cập nhật tồn kho thành công!", "success");
                  } else {
                      throw new Error(result.message || "Cập nhật thất bại.");
                  }
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

    if (batchFileInput && batchForm) {
        batchForm.addEventListener('submit', function(event) {
            const submitBtn = batchForm.querySelector('button[type="submit"]');
            if (submitBtn) {
               submitBtn.disabled = true;
               submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Đang xử lý...';
            }
        });
    }

    if (inventoryTableBody && qrCodeModalInstance && qrProductNameModalSpan && qrImageModalImg && qrImageContainer && qrLoadingSpinner) {
        inventoryTableBody.addEventListener('click', function(event) {
            const viewQrButton = event.target.closest('.view-qr-btn');
            if (viewQrButton) {
                const productId = viewQrButton.dataset.productId;
                let productName = viewQrButton.dataset.productName;

                if (!productId || !productName) {
                    console.error("Nút QR thiếu data-product-id hoặc data-product-name!");
                    if (typeof showToastAdmin === 'function') {
                        showToastAdmin("Lỗi: Không tìm thấy thông tin sản phẩm cho QR.", "danger");
                    }
                    return;
                }
                if (productName.includes('Lỗi SP')) productName = `SP ID: ${productId}`;

                qrProductNameModalSpan.textContent = productName;
                qrImageModalImg.src = '#';
                qrImageModalImg.style.display = 'none';
                qrLoadingSpinner.style.display = 'inline-block';
                qrImageContainer.innerHTML = '';
                qrImageContainer.appendChild(qrLoadingSpinner);
                const newImgTag = document.createElement('img');
                newImgTag.id = 'qrImageModal';
                newImgTag.alt = 'QR Code';
                newImgTag.classList.add('img-fluid');
                newImgTag.style.maxWidth = '250px';
                newImgTag.style.display = 'none';
                qrImageContainer.appendChild(newImgTag);
                const freshQrImageModalImg = document.getElementById('qrImageModal');


                const qrImageUrl = `/admin/inventory/qr-code/${productId}?t=${new Date().getTime()}`;

                freshQrImageModalImg.onload = function() {
                    qrLoadingSpinner.style.display = 'none';
                    this.style.display = 'block';
                };
                freshQrImageModalImg.onerror = function() {
                    qrLoadingSpinner.style.display = 'none';
                    const errorP = document.createElement('p');
                    errorP.classList.add('text-danger','m-0','p-3');
                    errorP.textContent = 'Lỗi tải ảnh QR.';
                    qrImageContainer.innerHTML = '';
                    qrImageContainer.appendChild(errorP);
                    qrImageContainer.appendChild(this); // keep the img tag for next try if needed
                    this.style.display = 'none';
                };
                freshQrImageModalImg.src = qrImageUrl;
                qrCodeModalInstance.show();
            }
        });
    } else {
        console.warn("Một vài phần tử cho Modal QR không tìm thấy. Kiểm tra ID HTML.");
    }

    const printQrModalBtn = document.getElementById('printQrModalBtn');
    if (printQrModalBtn && qrProductNameModalSpan) {
        printQrModalBtn.addEventListener('click', function() {
            const currentQrImageModalImg = document.getElementById('qrImageModal');
            const productName = qrProductNameModalSpan.textContent;
            const qrImgSrc = currentQrImageModalImg ? currentQrImageModalImg.src : null;

            if (!qrImgSrc || qrImgSrc === '#' || qrImgSrc.endsWith('/#')) {
                if (typeof showToastAdmin === 'function') showToastAdmin("Lỗi: Không có ảnh QR để in.", "warning");
                return;
            }

            const printWindow = window.open('', '_blank', 'height=500,width=500');
            if (!printWindow) {
                if (typeof showToastAdmin === 'function') showToastAdmin("Không thể mở cửa sổ in. Vui lòng kiểm tra cài đặt trình duyệt.", "danger");
                return;
            }

            printWindow.document.write('<html><head><title>In Mã QR - ' + productName + '</title>');
            printWindow.document.write('<style>' +
                'body { text-align: center; font-family: Arial, sans-serif; margin: 20px; }' +
                'img { max-width: 90%; max-height: 350px; border: 1px solid #ccc; margin-top: 15px; display: block; margin-left: auto; margin-right: auto; }' +
                'h4 { margin-bottom: 10px; font-size: 16px; }' +
                'p.scan-text { font-size: 12px; color: #555; margin-top: 5px; }' +
                '</style></head><body>');
            printWindow.document.write('<h4>' + productName + '</h4>');
            printWindow.document.write('<img src="' + qrImgSrc + '" alt="QR Code">');
            printWindow.document.write('<p class="scan-text">Quét mã để truy cập nhanh.</p>');
            printWindow.document.write('</body></html>');
            printWindow.document.close();
            printWindow.focus();

            const imageToPrint = printWindow.document.querySelector('img');
            if (imageToPrint) {
                if (imageToPrint.complete) {
                    printWindow.print();
                    printWindow.close();
                } else {
                    imageToPrint.onload = function() {
                        printWindow.print();
                        printWindow.close();
                    };
                    setTimeout(() => {
                         if (!printWindow.closed) {
                             try { printWindow.print(); printWindow.close(); }
                             catch (e) { if (!printWindow.closed) printWindow.close(); }
                         }
                    }, 1500);
                }
            } else {
                printWindow.print();
                printWindow.close();
            }
        });
    }

    function reinitializeBootstrapComponents(container) {
        var tooltipTriggerList = [].slice.call(container.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.forEach(function(tooltipTriggerEl) {
             var oldTooltip = bootstrap.Tooltip.getInstance(tooltipTriggerEl);
             if (oldTooltip) { oldTooltip.dispose(); }
             new bootstrap.Tooltip(tooltipTriggerEl);
         });
    }

    function showToastAdmin(message, type = 'info') {
        let toastContainer = document.querySelector('.toast-container.position-fixed.top-0.end-0');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
            toastContainer.style.zIndex = 1090;
            document.body.appendChild(toastContainer);
        }
        const toastId = 'admin-toast-' + Date.now();
        const bgClass = type === 'success' ? 'bg-success' : (type === 'danger' ? 'bg-danger' : (type === 'warning' ? 'bg-warning text-dark' : 'bg-info'));
        const textClass = (type === 'warning' || type === 'light') ? '' : 'text-white';
        const iconClass = type === 'success' ? 'fas fa-check-circle' : (type === 'danger' ? 'fas fa-exclamation-triangle' : (type === 'warning' ? 'fas fa-exclamation-circle' : 'fas fa-info-circle'));
        const btnCloseClass = (type === 'warning' || type === 'light') ? '' : 'btn-close-white';

        const toastHTML = `
            <div id="${toastId}" class="toast ${bgClass} ${textClass} border-0" role="alert" aria-live="assertive" aria-atomic="true" data-bs-delay="5000">
                <div class="d-flex">
                    <div class="toast-body d-flex align-items-center">
                        <i class="${iconClass} me-2"></i>
                        <span>${message}</span>
                    </div>
                    <button type="button" class="btn-close ${btnCloseClass} me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
            </div>`;
        toastContainer.insertAdjacentHTML('beforeend', toastHTML);
        const toastEl = document.getElementById(toastId);
        if(toastEl){
           const toast = new bootstrap.Toast(toastEl);
           toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
           toast.show();
        }
    }

     var initialTooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
     var initialTooltipList = initialTooltipTriggerList.map(function (tooltipTriggerEl) {
         return new bootstrap.Tooltip(tooltipTriggerEl);
     });

});