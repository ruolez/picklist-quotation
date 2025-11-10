// Picklists page functionality
console.log('[PICKLISTS.JS] File loaded - version 20251029-1845');

let picklists = [];
let selectedIds = new Set();
let showArchived = false;
let sortColumn = 'id'; // default sort by ID
let sortDirection = 'desc'; // desc = newest first

function showAlert(message, type = 'info') {
    const alertContainer = document.getElementById('alert-container');
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.innerHTML = message;

    alertContainer.innerHTML = '';
    alertContainer.appendChild(alert);

    setTimeout(() => {
        alert.remove();
    }, 8000);
}

function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString('en-US', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function sortPicklists(data) {
    return data.sort((a, b) => {
        let aVal, bVal;

        switch(sortColumn) {
            case 'id':
                aVal = a.id || a.pick_list_id || 0;
                bVal = b.id || b.pick_list_id || 0;
                break;
            case 'date':
                aVal = new Date(a.cdate || a.archived_at || 0);
                bVal = new Date(b.cdate || b.archived_at || 0);
                break;
            case 'products':
                // For now, product count is not available, so keep original order
                return 0;
            case 'status':
                aVal = a.is_locked ? 1 : 0;
                bVal = b.is_locked ? 1 : 0;
                break;
            default:
                return 0;
        }

        if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
        if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
        return 0;
    });
}

function setSortColumn(column) {
    if (sortColumn === column) {
        // Toggle direction if clicking same column
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        sortColumn = column;
        sortDirection = 'asc';
    }
    updateSortIndicators();
    loadPicklists();
}

function updateSortIndicators() {
    // Remove all sort indicators
    document.querySelectorAll('.sort-indicator').forEach(indicator => {
        indicator.textContent = '';
    });

    // Add indicator to current sort column
    const indicator = document.getElementById(`sort-${sortColumn}`);
    if (indicator) {
        indicator.textContent = sortDirection === 'asc' ? ' ↑' : ' ↓';
    }
}

async function loadPicklists() {
    const tbody = document.getElementById('picklists-body');
    tbody.innerHTML = `
        <tr>
            <td colspan="6" style="text-align: center; padding: 40px;">
                <span class="spinner"></span> Loading picklists...
            </td>
        </tr>
    `;

    try {
        const endpoint = showArchived ? '/api/picklists/archived' : '/api/picklists/pending';
        const response = await fetch(endpoint);
        const data = await response.json();

        if (data.error) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="text-align: center; padding: 40px; color: var(--error);">
                        Error: ${data.error}
                    </td>
                </tr>
            `;
            return;
        }

        picklists = sortPicklists(data);

        if (picklists.length === 0) {
            const message = showArchived
                ? 'No archived picklists found.'
                : 'No pending picklists found. All picklists have been converted!';
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="text-align: center; padding: 40px; color: var(--text-secondary);">
                        ${message}
                    </td>
                </tr>
            `;
            return;
        }

        // Load product counts for each picklist
        tbody.innerHTML = '';
        for (const picklist of picklists) {
            const row = document.createElement('tr');
            row.id = `row-${picklist.id}`;

            const isChecked = selectedIds.has(picklist.id);

            // Get product count
            let productCount = '...';
            try {
                const config = await fetch('/api/config/sqlserver');
                const configData = await config.json();
                if (configData) {
                    // We'll show a placeholder for now
                    productCount = '-';
                }
            } catch (e) {
                productCount = '-';
            }

            let statusBadge, actionButton;

            if (showArchived) {
                statusBadge = '<span class="badge badge-warning">Archived</span>';
                actionButton = `
                    <button class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="unarchiveSingle(${picklist.pick_list_id || picklist.id})">
                        Unarchive
                    </button>
                `;
            } else if (picklist.is_converted) {
                statusBadge = '<span class="badge badge-success">✓ Converted</span>';
                actionButton = `
                    <button class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="archiveSingle(${picklist.id})">
                        Archive
                    </button>
                `;
            } else {
                statusBadge = picklist.is_locked
                    ? '<span class="badge badge-warning">Locked</span>'
                    : '<span class="badge badge-info">Ready</span>';
                actionButton = `
                    <button class="btn btn-primary" style="padding: 6px 12px; font-size: 12px; margin-right: 8px;" onclick="convertSingle(${picklist.id})">
                        Convert Now
                    </button>
                    <button class="btn btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="archiveSingle(${picklist.id})">
                        Archive
                    </button>
                `;
            }

            const picklistId = picklist.pick_list_id || picklist.id;

            row.innerHTML = `
                <td>
                    <input type="checkbox" class="picklist-checkbox" data-id="${picklistId}" ${isChecked ? 'checked' : ''}>
                </td>
                <td><strong>${picklistId}</strong></td>
                <td>${formatDate(picklist.cdate || picklist.archived_at)}</td>
                <td>${productCount}</td>
                <td>${statusBadge}</td>
                <td>
                    ${actionButton}
                </td>
            `;

            tbody.appendChild(row);
        }

        // Attach checkbox event listeners
        document.querySelectorAll('.picklist-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', handleCheckboxChange);
        });

        updateSelectedCount();

    } catch (error) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" style="text-align: center; padding: 40px; color: var(--error);">
                    Error loading picklists: ${error.message}
                </td>
            </tr>
        `;
    }
}

function handleCheckboxChange(event) {
    const id = parseInt(event.target.dataset.id);
    if (event.target.checked) {
        selectedIds.add(id);
    } else {
        selectedIds.delete(id);
    }
    updateSelectedCount();
}

function updateSelectedCount() {
    const count = selectedIds.size;
    document.getElementById('selected-count').textContent = count;
    document.getElementById('btn-convert-selected').disabled = count === 0 || showArchived;
    document.getElementById('btn-archive-selected').disabled = count === 0;

    // Update button text based on view
    const archiveBtn = document.getElementById('btn-archive-selected');
    archiveBtn.textContent = showArchived ? 'Unarchive Selected' : 'Archive Selected';

    // Hide/show convert button based on view
    const convertBtn = document.getElementById('btn-convert-selected');
    convertBtn.style.display = showArchived ? 'none' : 'inline-block';
}

function selectAll() {
    selectedIds.clear();
    picklists.forEach(pl => selectedIds.add(pl.id));
    document.querySelectorAll('.picklist-checkbox').forEach(cb => cb.checked = true);
    document.getElementById('checkbox-all').checked = true;
    updateSelectedCount();
}

function deselectAll() {
    selectedIds.clear();
    document.querySelectorAll('.picklist-checkbox').forEach(cb => cb.checked = false);
    document.getElementById('checkbox-all').checked = false;
    updateSelectedCount();
}

async function convertSelected() {
    console.log('[convertSelected] Function called, selectedIds:', Array.from(selectedIds));
    if (selectedIds.size === 0) {
        console.log('[convertSelected] No IDs selected, returning');
        return;
    }

    const btn = document.getElementById('btn-convert-selected');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Checking products...';

    const resultsDiv = document.getElementById('conversion-results');
    resultsDiv.innerHTML = '';

    try {
        // First, check for missing products
        console.log('Checking products for picklists:', Array.from(selectedIds));
        const checkResponse = await fetch('/api/check-products', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ picklist_ids: Array.from(selectedIds) })
        });

        console.log('Check response status:', checkResponse.status, checkResponse.ok);

        if (!checkResponse.ok) {
            const errorText = await checkResponse.text();
            console.error('Check response failed:', errorText);
            resultsDiv.innerHTML = `<div class="alert alert-error">Server error: ${checkResponse.status}</div>`;
            btn.disabled = false;
            btn.innerHTML = originalText;
            return;
        }

        const checkData = await checkResponse.json();
        console.log('Check products response data:', checkData);

        if (checkData.success === false) {
            console.log('Check products reported error:', checkData.error);
            resultsDiv.innerHTML = `<div class="alert alert-error">Error checking products: ${checkData.error}</div>`;
            btn.disabled = false;
            btn.innerHTML = originalText;
            return;
        }

        // If there are missing products, show them and ask user
        if (checkData.missing_count > 0) {
            console.log('Missing products found, showing modal:', checkData.missing_count);
            showMissingProductsModal(
                checkData.missing,
                checkData.total_products,
                checkData.missing_count,
                checkData.can_copy_count || 0,
                checkData.truly_missing_count || checkData.missing_count
            );
            btn.disabled = false;
            btn.innerHTML = originalText;
            return;
        }

        console.log('No missing products, proceeding with conversion');

        // No missing products, proceed with conversion
        btn.innerHTML = '<span class="spinner"></span> Converting...';

        const response = await fetch('/api/convert/selected', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ picklist_ids: Array.from(selectedIds) })
        });

        const data = await response.json();

        if (data.success && data.results) {
            const results = data.results;
            let alertType = 'success';
            let message = `Conversion complete: ${results.converted} converted, ${results.failed} failed`;

            if (results.failed > 0) {
                alertType = 'warning';
                message += '<br><br><strong>Errors:</strong><ul style="margin-top: 8px;">';
                results.errors.forEach(err => {
                    message += `<li>Picklist ${err.picklist_id}: ${err.error}</li>`;
                });
                message += '</ul>';
            }

            resultsDiv.innerHTML = `<div class="alert alert-${alertType}">${message}</div>`;

            // Reload the picklists
            selectedIds.clear();
            setTimeout(() => {
                loadPicklists();
            }, 2000);

        } else {
            resultsDiv.innerHTML = `<div class="alert alert-error">Conversion failed: ${data.error || 'Unknown error'}</div>`;
        }

    } catch (error) {
        console.error('[convertSelected] Error caught:', error);
        console.error('[convertSelected] Error stack:', error.stack);
        resultsDiv.innerHTML = `<div class="alert alert-error">Error: ${error.message}</div>`;
    } finally {
        console.log('[convertSelected] Finally block - resetting button');
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

async function convertSingle(picklistId) {
    console.log('[convertSingle] Called with picklistId:', picklistId);

    if (!confirm(`Convert picklist ${picklistId} to quotation?`)) {
        console.log('[convertSingle] User cancelled confirmation');
        return;
    }

    const row = document.getElementById(`row-${picklistId}`);
    const actionCell = row.querySelector('td:last-child');
    const originalHtml = actionCell.innerHTML;

    actionCell.innerHTML = '<span class="spinner"></span>';
    console.log('[convertSingle] Spinner shown, calling /api/check-products');

    try {
        // First, check for missing products
        const checkResponse = await fetch('/api/check-products', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ picklist_ids: [picklistId] })
        });

        console.log('[convertSingle] Check response received:', checkResponse.status);

        const checkData = await checkResponse.json();
        console.log('[convertSingle] Check data parsed:', checkData);

        if (!checkData.success) {
            console.log('[convertSingle] Check failed:', checkData.error);
            showAlert(`Error checking products: ${checkData.error}`, 'error');
            actionCell.innerHTML = originalHtml;
            return;
        }

        // If there are missing products, show them
        if (checkData.missing_count > 0) {
            console.log('[convertSingle] Missing products found:', checkData.missing_count);
            console.log('[convertSingle] Calling showMissingProductsModal...');
            showMissingProductsModal(
                checkData.missing,
                checkData.total_products,
                checkData.missing_count,
                checkData.can_copy_count || 0,
                checkData.truly_missing_count || checkData.missing_count
            );
            console.log('[convertSingle] Modal function returned, restoring button');
            actionCell.innerHTML = originalHtml;
            return;
        }

        console.log('[convertSingle] No missing products, proceeding with conversion');

        // No missing products, proceed with conversion
        const response = await fetch('/api/convert/selected', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ picklist_ids: [picklistId] })
        });

        const data = await response.json();

        if (data.success && data.results) {
            const results = data.results;
            if (results.converted > 0) {
                showAlert(`Picklist ${picklistId} converted successfully!`, 'success');
                setTimeout(() => {
                    loadPicklists();
                }, 1500);
            } else {
                const error = results.errors[0]?.error || 'Unknown error';
                showAlert(`Picklist ${picklistId} conversion failed: ${error}`, 'error');
                actionCell.innerHTML = originalHtml;
            }
        } else {
            showAlert(`Conversion failed: ${data.error || 'Unknown error'}`, 'error');
            actionCell.innerHTML = originalHtml;
        }

    } catch (error) {
        showAlert(`Error: ${error.message}`, 'error');
        actionCell.innerHTML = originalHtml;
    }
}

async function archiveSelected() {
    if (selectedIds.size === 0) return;

    if (!confirm(`Archive ${selectedIds.size} picklist(s)? They will be hidden from the pending list.`)) {
        return;
    }

    try {
        const response = await fetch('/api/archive/selected', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ picklist_ids: Array.from(selectedIds) })
        });

        const data = await response.json();

        if (data.success) {
            showAlert(data.message, 'success');
            selectedIds.clear();
            setTimeout(() => {
                loadPicklists();
            }, 1500);
        } else {
            showAlert(`Archive failed: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        showAlert(`Error: ${error.message}`, 'error');
    }
}

async function unarchiveSelected() {
    if (selectedIds.size === 0) return;

    try {
        const response = await fetch('/api/archive/unarchive', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ picklist_ids: Array.from(selectedIds) })
        });

        const data = await response.json();

        if (data.success) {
            showAlert(data.message, 'success');
            selectedIds.clear();
            setTimeout(() => {
                loadPicklists();
            }, 1500);
        } else {
            showAlert(`Unarchive failed: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        showAlert(`Error: ${error.message}`, 'error');
    }
}

async function archiveSingle(picklistId) {
    if (!confirm(`Archive picklist ${picklistId}?`)) {
        return;
    }

    try {
        const response = await fetch('/api/archive/selected', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ picklist_ids: [picklistId] })
        });

        const data = await response.json();

        if (data.success) {
            showAlert(`Picklist ${picklistId} archived successfully!`, 'success');
            setTimeout(() => {
                loadPicklists();
            }, 1500);
        } else {
            showAlert(`Archive failed: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        showAlert(`Error: ${error.message}`, 'error');
    }
}

async function unarchiveSingle(picklistId) {
    try {
        const response = await fetch('/api/archive/unarchive', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ picklist_ids: [picklistId] })
        });

        const data = await response.json();

        if (data.success) {
            showAlert(`Picklist ${picklistId} unarchived successfully!`, 'success');
            setTimeout(() => {
                loadPicklists();
            }, 1500);
        } else {
            showAlert(`Unarchive failed: ${data.error || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        showAlert(`Error: ${error.message}`, 'error');
    }
}

function showMissingProductsModal(missing, totalProducts, missingCount, canCopyCount, trulyMissingCount) {
    console.log('showMissingProductsModal called with:', { missing, totalProducts, missingCount, canCopyCount, trulyMissingCount });

    // Separate products by status
    const foundInInventory = missing.filter(p => p.status === 'found_in_inventory');
    const notFound = missing.filter(p => p.status === 'not_found');

    // Create modal HTML with status column
    let productsHtml = '<table style="width: 100%; border-collapse: collapse; margin-top: 16px;"><thead><tr>' +
        '<th style="text-align: left; padding: 8px; border-bottom: 2px solid var(--outline);">Picklist</th>' +
        '<th style="text-align: left; padding: 8px; border-bottom: 2px solid var(--outline);">Barcode</th>' +
        '<th style="text-align: left; padding: 8px; border-bottom: 2px solid var(--outline);">Product Name</th>' +
        '<th style="text-align: left; padding: 8px; border-bottom: 2px solid var(--outline);">Qty</th>' +
        '<th style="text-align: left; padding: 8px; border-bottom: 2px solid var(--outline);">Status</th>' +
        '</tr></thead><tbody>';

    // Show products found in inventory first (green)
    foundInInventory.forEach(product => {
        productsHtml += `<tr style="background-color: #e8f5e9;">
            <td style="padding: 8px; border-bottom: 1px solid var(--outline);">${product.picklist_id}</td>
            <td style="padding: 8px; border-bottom: 1px solid var(--outline);"><code>${product.barcode}</code></td>
            <td style="padding: 8px; border-bottom: 1px solid var(--outline);">${product.name}</td>
            <td style="padding: 8px; border-bottom: 1px solid var(--outline);">${product.amount}</td>
            <td style="padding: 8px; border-bottom: 1px solid var(--outline);"><span style="color: var(--success);">✓ ${product.reason}</span></td>
        </tr>`;
    });

    // Show products not found anywhere (red)
    notFound.forEach(product => {
        productsHtml += `<tr style="background-color: #ffebee;">
            <td style="padding: 8px; border-bottom: 1px solid var(--outline);">${product.picklist_id}</td>
            <td style="padding: 8px; border-bottom: 1px solid var(--outline);"><code>${product.barcode}</code></td>
            <td style="padding: 8px; border-bottom: 1px solid var(--outline);">${product.name}</td>
            <td style="padding: 8px; border-bottom: 1px solid var(--outline);">${product.amount}</td>
            <td style="padding: 8px; border-bottom: 1px solid var(--outline);"><span style="color: var(--error);">✗ ${product.reason}</span></td>
        </tr>`;
    });

    productsHtml += '</tbody></table>';

    // Build message based on status
    let messageHtml = '';
    if (canCopyCount > 0 && trulyMissingCount > 0) {
        messageHtml = `<p style="margin-bottom: 16px;">
            <strong>${missingCount} out of ${totalProducts} products</strong> are not in BackOffice:<br>
            • <span style="color: var(--success);">${canCopyCount} found in Inventory</span> (can be copied)<br>
            • <span style="color: var(--error);">${trulyMissingCount} not found anywhere</span> (blocking)
        </p>`;
    } else if (canCopyCount > 0) {
        messageHtml = `<p style="margin-bottom: 16px;">
            <strong>${canCopyCount} out of ${totalProducts} products</strong> are not in BackOffice but <span style="color: var(--success);">found in Inventory</span>.
            Click "Copy from Inventory" to add them to BackOffice.
        </p>`;
    } else {
        messageHtml = `<p style="margin-bottom: 16px;">
            <strong>${trulyMissingCount} out of ${totalProducts} products</strong> cannot be found in BackOffice or Inventory.
            These products must be added manually before conversion can proceed.
        </p>`;
    }

    // Add copy button if there are products to copy
    const copyButtonHtml = canCopyCount > 0
        ? `<button class="btn btn-primary" onclick="copyProductsFromInventory()" id="btn-copy-inventory">Copy from Inventory (${canCopyCount})</button>`
        : '';

    const modalHtml = `
        <div class="modal-overlay" id="missing-products-modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2 style="margin: 0;">⚠️ Missing Products</h2>
                    <button class="modal-close" onclick="closeMissingProductsModal()">&times;</button>
                </div>
                <div class="modal-body">
                    ${messageHtml}
                    ${productsHtml}
                </div>
                <div class="modal-footer">
                    ${copyButtonHtml}
                    <button class="btn btn-secondary" onclick="closeMissingProductsModal()">Close</button>
                </div>
            </div>
        </div>
    `;

    // Remove existing modal if present
    const existingModal = document.getElementById('missing-products-modal');
    if (existingModal) {
        console.log('Removing existing modal');
        existingModal.remove();
    }

    // Add modal to page
    console.log('Adding modal to document.body');
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    console.log('Modal added, checking if it exists:', !!document.getElementById('missing-products-modal'));
}

function closeMissingProductsModal() {
    const modal = document.getElementById('missing-products-modal');
    if (modal) {
        modal.remove();
    }
}

async function copyProductsFromInventory() {
    const btn = document.getElementById('btn-copy-inventory');
    if (!btn) return;

    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Copying...';

    try {
        // Get all products with status 'found_in_inventory'
        const modal = document.getElementById('missing-products-modal');
        const tbody = modal.querySelector('tbody');
        const rows = tbody.querySelectorAll('tr[style*="background-color: #e8f5e9"]'); // Green rows

        // Extract barcodes from green rows
        const barcodes = Array.from(rows).map(row => {
            const barcodeCell = row.querySelector('code');
            return barcodeCell ? barcodeCell.textContent : null;
        }).filter(barcode => barcode !== null);

        if (barcodes.length === 0) {
            showAlert('No products to copy', 'error');
            btn.disabled = false;
            btn.innerHTML = originalText;
            return;
        }

        console.log('Copying barcodes:', barcodes);

        // Call API to copy products
        const response = await fetch('/api/copy-products-from-inventory', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ barcodes })
        });

        const result = await response.json();

        if (!result.success) {
            showAlert(`Copy failed: ${result.error || 'Unknown error'}`, 'error');
            btn.disabled = false;
            btn.innerHTML = originalText;
            return;
        }

        // Show success message
        if (result.copied_count > 0) {
            showAlert(`Successfully copied ${result.copied_count} product(s) from Inventory to BackOffice!`, 'success');
        }

        if (result.failed_count > 0) {
            const failedBarcodes = result.failed.map(f => f.barcode).join(', ');
            showAlert(`Failed to copy ${result.failed_count} product(s): ${failedBarcodes}`, 'error');
        }

        // Close modal and allow user to retry conversion
        if (result.copied_count > 0) {
            setTimeout(() => {
                closeMissingProductsModal();
            }, 2000);
        } else {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }

    } catch (error) {
        console.error('Error copying products:', error);
        showAlert(`Error: ${error.message}`, 'error');
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    console.log('[DOMContentLoaded] Event fired');
    loadPicklists();

    const convertBtn = document.getElementById('btn-convert-selected');
    console.log('[DOMContentLoaded] Convert button found:', !!convertBtn);

    document.getElementById('btn-select-all').addEventListener('click', selectAll);
    document.getElementById('btn-deselect-all').addEventListener('click', deselectAll);

    if (convertBtn) {
        convertBtn.addEventListener('click', (e) => {
            console.log('[CLICK EVENT] Button clicked!', e);
            convertSelected();
        });
        console.log('[DOMContentLoaded] Convert button listener attached');
    }

    document.getElementById('btn-refresh').addEventListener('click', loadPicklists);

    document.getElementById('btn-archive-selected').addEventListener('click', () => {
        if (showArchived) {
            unarchiveSelected();
        } else {
            archiveSelected();
        }
    });

    document.getElementById('show-archived').addEventListener('change', (e) => {
        showArchived = e.target.checked;
        selectedIds.clear();
        loadPicklists();
    });

    document.getElementById('checkbox-all').addEventListener('change', (e) => {
        if (e.target.checked) {
            selectAll();
        } else {
            deselectAll();
        }
    });

    // Auto-refresh every 60 seconds
    setInterval(() => {
        loadPicklists();
    }, 60000);
});
