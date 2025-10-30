// History page functionality

let currentPage = 0;
const pageSize = 50;
let currentStatus = 'all';
let selectedRecords = new Set();
let pendingAction = null;

function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString('en-US', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function updateSelectedCount() {
    const deleteBtn = document.getElementById('btn-delete-selected');
    const count = selectedRecords.size;
    deleteBtn.textContent = `Delete Selected (${count})`;
    deleteBtn.disabled = count === 0;
}

function showConfirmModal(title, message, onConfirm) {
    const modal = document.getElementById('confirm-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalMessage = document.getElementById('modal-message');
    const confirmBtn = document.getElementById('modal-confirm');

    modalTitle.textContent = title;
    modalMessage.textContent = message;
    modal.style.display = 'flex';

    pendingAction = onConfirm;
}

function hideConfirmModal() {
    const modal = document.getElementById('confirm-modal');
    modal.style.display = 'none';
    pendingAction = null;
}

async function deleteRecord(recordId) {
    try {
        const response = await fetch('/api/history/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ record_ids: [recordId] })
        });

        const data = await response.json();

        if (data.success) {
            showAlert('Record deleted successfully', 'success');
            loadHistory(currentPage);
        } else {
            showAlert(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showAlert(`Error deleting record: ${error.message}`, 'error');
    }
}

async function deleteSelected() {
    const recordIds = Array.from(selectedRecords);

    try {
        const response = await fetch('/api/history/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ record_ids: recordIds })
        });

        const data = await response.json();

        if (data.success) {
            showAlert(`Deleted ${data.deleted_count} record(s) successfully`, 'success');
            selectedRecords.clear();
            updateSelectedCount();
            loadHistory(currentPage);
        } else {
            showAlert(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showAlert(`Error deleting records: ${error.message}`, 'error');
    }
}

async function deleteAllFailed() {
    try {
        const response = await fetch('/api/history/delete-failed', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const data = await response.json();

        if (data.success) {
            showAlert(`Deleted ${data.deleted_count} failed record(s) successfully`, 'success');
            selectedRecords.clear();
            updateSelectedCount();
            loadHistory(currentPage);
        } else {
            showAlert(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        showAlert(`Error deleting failed records: ${error.message}`, 'error');
    }
}

function showAlert(message, type = 'success') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type}`;
    alertDiv.textContent = message;
    alertDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 16px 24px;
        background: ${type === 'success' ? 'var(--success)' : 'var(--error)'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 10000;
        animation: slideIn 0.3s ease-out;
    `;

    document.body.appendChild(alertDiv);

    setTimeout(() => {
        alertDiv.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => alertDiv.remove(), 300);
    }, 3000);
}

async function loadHistory(page = 0) {
    const tbody = document.getElementById('history-body');
    const prevBtn = document.getElementById('btn-prev');
    const nextBtn = document.getElementById('btn-next');

    tbody.innerHTML = `
        <tr>
            <td colspan="7" style="text-align: center; padding: 40px;">
                <span class="spinner"></span> Loading history...
            </td>
        </tr>
    `;

    try {
        const offset = page * pageSize;
        const response = await fetch(`/api/history?limit=${pageSize}&offset=${offset}&status=${currentStatus}`);
        const data = await response.json();

        if (data.error) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align: center; padding: 40px; color: var(--error);">
                        Error: ${data.error}
                    </td>
                </tr>
            `;
            return;
        }

        if (data.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align: center; padding: 40px; color: var(--text-secondary);">
                        No conversion history found
                    </td>
                </tr>
            `;
            prevBtn.disabled = page === 0;
            nextBtn.disabled = true;
            return;
        }

        tbody.innerHTML = '';
        data.forEach(record => {
            const row = document.createElement('tr');
            row.dataset.recordId = record.id;

            const statusBadge = record.success
                ? '<span class="badge badge-success">Success</span>'
                : '<span class="badge badge-error">Failed</span>';

            const errorMessage = record.error_message || '-';

            const deleteButton = `
                <button class="btn btn-sm btn-danger delete-record" data-record-id="${record.id}">
                    Delete
                </button>
            `;

            row.innerHTML = `
                <td style="text-align: center;">
                    <input type="checkbox" class="record-checkbox" data-record-id="${record.id}" ${selectedRecords.has(record.id) ? 'checked' : ''}>
                </td>
                <td>${record.pick_list_id}</td>
                <td>${record.quotation_number || '-'}</td>
                <td>${statusBadge}</td>
                <td>${formatDate(record.converted_at)}</td>
                <td style="max-width: 300px; word-wrap: break-word; font-size: 13px;">${errorMessage}</td>
                <td>${deleteButton}</td>
            `;

            tbody.appendChild(row);
        });

        // Update pagination buttons
        prevBtn.disabled = page === 0;
        nextBtn.disabled = data.length < pageSize;

    } catch (error) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" style="text-align: center; padding: 40px; color: var(--error);">
                    Error loading history: ${error.message}
                </td>
            </tr>
        `;
    }
}

function previousPage() {
    if (currentPage > 0) {
        currentPage--;
        loadHistory(currentPage);
    }
}

function nextPage() {
    currentPage++;
    loadHistory(currentPage);
}

function setStatusFilter(status) {
    currentStatus = status;
    currentPage = 0;
    selectedRecords.clear();
    updateSelectedCount();

    // Update active filter button
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.status === status) {
            btn.classList.add('active');
        }
    });

    loadHistory(0);
}

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    loadHistory(0);

    // Pagination
    document.getElementById('btn-prev').addEventListener('click', previousPage);
    document.getElementById('btn-next').addEventListener('click', nextPage);

    // Filter buttons
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            setStatusFilter(btn.dataset.status);
        });
    });

    // Select all checkbox
    document.getElementById('select-all').addEventListener('change', (e) => {
        const checkboxes = document.querySelectorAll('.record-checkbox');
        checkboxes.forEach(cb => {
            cb.checked = e.target.checked;
            const recordId = parseInt(cb.dataset.recordId);
            if (e.target.checked) {
                selectedRecords.add(recordId);
            } else {
                selectedRecords.delete(recordId);
            }
        });
        updateSelectedCount();
    });

    // Individual checkboxes (event delegation)
    document.getElementById('history-body').addEventListener('change', (e) => {
        if (e.target.classList.contains('record-checkbox')) {
            const recordId = parseInt(e.target.dataset.recordId);
            if (e.target.checked) {
                selectedRecords.add(recordId);
            } else {
                selectedRecords.delete(recordId);
            }
            updateSelectedCount();

            // Update select-all checkbox
            const allCheckboxes = document.querySelectorAll('.record-checkbox');
            const allChecked = Array.from(allCheckboxes).every(cb => cb.checked);
            document.getElementById('select-all').checked = allChecked;
        }
    });

    // Individual delete buttons (event delegation)
    document.getElementById('history-body').addEventListener('click', (e) => {
        if (e.target.classList.contains('delete-record')) {
            const recordId = parseInt(e.target.dataset.recordId);
            showConfirmModal(
                'Delete Record',
                'Are you sure you want to delete this conversion record? This action cannot be undone.',
                () => deleteRecord(recordId)
            );
        }
    });

    // Delete selected button
    document.getElementById('btn-delete-selected').addEventListener('click', () => {
        const count = selectedRecords.size;
        showConfirmModal(
            'Delete Selected Records',
            `Are you sure you want to delete ${count} selected record(s)? This action cannot be undone.`,
            () => deleteSelected()
        );
    });

    // Delete all failed button
    document.getElementById('btn-delete-all-failed').addEventListener('click', () => {
        showConfirmModal(
            '⚠️ Delete All Failed Records',
            'This will permanently delete ALL failed conversion records. This action cannot be undone. Are you sure?',
            () => deleteAllFailed()
        );
    });

    // Modal cancel button
    document.getElementById('modal-cancel').addEventListener('click', hideConfirmModal);

    // Modal confirm button
    document.getElementById('modal-confirm').addEventListener('click', () => {
        if (pendingAction) {
            pendingAction();
        }
        hideConfirmModal();
    });

    // Close modal on background click
    document.getElementById('confirm-modal').addEventListener('click', (e) => {
        if (e.target.id === 'confirm-modal') {
            hideConfirmModal();
        }
    });

    // Auto-refresh every 30 seconds
    setInterval(() => {
        loadHistory(currentPage);
    }, 30000);
});
