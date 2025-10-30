// Dashboard functionality

let pollerInterval = null;

function showAlert(message, type = 'info') {
    const alertContainer = document.getElementById('alert-container');
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;

    alertContainer.innerHTML = '';
    alertContainer.appendChild(alert);

    setTimeout(() => {
        alert.remove();
    }, 5000);
}

async function loadStats() {
    try {
        const response = await fetch('/api/dashboard/stats');
        const data = await response.json();

        document.getElementById('stat-converted').textContent = data.total_converted || 0;
        document.getElementById('stat-pending').textContent = data.pending_count || 0;
        document.getElementById('stat-failed').textContent = data.total_failed || 0;

        // Calculate success rate
        if (data.total_attempts > 0) {
            const successRate = ((data.total_converted / data.total_attempts) * 100).toFixed(1);
            document.getElementById('stat-success-rate').textContent = successRate + '%';
        } else {
            document.getElementById('stat-success-rate').textContent = '0%';
        }
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

async function loadPollerStatus() {
    try {
        const response = await fetch('/api/poller/status');
        const data = await response.json();

        const statusElement = document.getElementById('poller-status');
        const startBtn = document.getElementById('btn-start-poller');
        const stopBtn = document.getElementById('btn-stop-poller');

        if (data.running) {
            statusElement.className = 'status-indicator running';
            statusElement.innerHTML = `
                <span class="status-dot green"></span>
                <span>Running (polling every ${data.interval_seconds}s)</span>
            `;
            startBtn.disabled = true;
            stopBtn.disabled = false;
        } else {
            statusElement.className = 'status-indicator stopped';
            statusElement.innerHTML = `
                <span class="status-dot gray"></span>
                <span>Stopped</span>
            `;
            startBtn.disabled = false;
            stopBtn.disabled = true;
        }
    } catch (error) {
        console.error('Error loading poller status:', error);
    }
}

async function startPoller() {
    try {
        const response = await fetch('/api/poller/start', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            showAlert('Auto-polling started successfully', 'success');
            loadPollerStatus();
        } else {
            showAlert(data.message || 'Failed to start polling', 'error');
        }
    } catch (error) {
        showAlert('Error starting poller: ' + error.message, 'error');
    }
}

async function stopPoller() {
    try {
        const response = await fetch('/api/poller/stop', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            showAlert('Auto-polling stopped', 'info');
            loadPollerStatus();
        } else {
            showAlert(data.message || 'Failed to stop polling', 'error');
        }
    } catch (error) {
        showAlert('Error stopping poller: ' + error.message, 'error');
    }
}

async function triggerConversion() {
    const btn = document.getElementById('btn-convert');
    const resultsDiv = document.getElementById('conversion-results');

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Converting...';
    resultsDiv.innerHTML = '';

    try {
        const response = await fetch('/api/convert/trigger', { method: 'POST' });
        const data = await response.json();

        if (data.success && data.results) {
            const results = data.results;

            if (results.error) {
                resultsDiv.innerHTML = `<div class="alert alert-error">${results.error}</div>`;
            } else {
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

                // Reload stats
                loadStats();
            }
        } else {
            resultsDiv.innerHTML = `<div class="alert alert-error">Conversion failed: ${data.error || 'Unknown error'}</div>`;
        }
    } catch (error) {
        resultsDiv.innerHTML = `<div class="alert alert-error">Error: ${error.message}</div>`;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Convert Pending Picklists';
    }
}

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadPollerStatus();

    document.getElementById('btn-start-poller').addEventListener('click', startPoller);
    document.getElementById('btn-stop-poller').addEventListener('click', stopPoller);
    document.getElementById('btn-convert').addEventListener('click', triggerConversion);

    // Auto-refresh stats every 30 seconds
    setInterval(() => {
        loadStats();
        loadPollerStatus();
    }, 30000);
});
