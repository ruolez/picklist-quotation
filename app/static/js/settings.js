// Settings page functionality

// Toast notification system (2025 Enterprise Design System)
function showToast(message, type = 'info') {
    const container = document.querySelector('.toast-container') || createToastContainer();
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icon = document.createElement('div');
    icon.className = 'toast-icon';

    const content = document.createElement('div');
    content.className = 'toast-content';

    const messageEl = document.createElement('div');
    messageEl.className = 'toast-message';
    messageEl.textContent = message;

    content.appendChild(messageEl);
    toast.appendChild(icon);
    toast.appendChild(content);
    container.appendChild(toast);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        toast.classList.add('removing');
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

function createToastContainer() {
    const container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
    return container;
}

async function loadConfig() {
    try {
        const response = await fetch('/api/config/sqlserver');
        const config = await response.json();

        if (config) {
            document.getElementById('shipper-host').value = config.shipper_host || '';
            document.getElementById('shipper-port').value = config.shipper_port || 1433;
            document.getElementById('shipper-user').value = config.shipper_user || '';
            document.getElementById('shipper-database').value = config.shipper_database || '';

            document.getElementById('backoffice-host').value = config.backoffice_host || '';
            document.getElementById('backoffice-port').value = config.backoffice_port || 1433;
            document.getElementById('backoffice-user').value = config.backoffice_user || '';
            document.getElementById('backoffice-database').value = config.backoffice_database || '';

            document.getElementById('inventory-enabled').checked = config.inventory_enabled === 1;
            document.getElementById('inventory-host').value = config.inventory_host || '';
            document.getElementById('inventory-port').value = config.inventory_port || 1433;
            document.getElementById('inventory-user').value = config.inventory_user || '';
            document.getElementById('inventory-database').value = config.inventory_database || '';
        }
    } catch (error) {
        console.error('Error loading config:', error);
    }
}

async function loadDefaults() {
    try {
        const response = await fetch('/api/config/quotation-defaults');
        const defaults = await response.json();

        if (defaults) {
            document.getElementById('customer-id').value = defaults.customer_id || '';
            document.getElementById('default-status').value = defaults.default_status || 1;
            document.getElementById('title-prefix').value = defaults.quotation_title_prefix || 'PL';
            document.getElementById('polling-interval').value = defaults.polling_interval_seconds || 60;
        }
    } catch (error) {
        console.error('Error loading defaults:', error);
    }
}

async function testShipperConnection() {
    const btn = document.getElementById('btn-test-shipper');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Testing...';

    const data = {
        host: document.getElementById('shipper-host').value,
        port: parseInt(document.getElementById('shipper-port').value),
        user: document.getElementById('shipper-user').value,
        password: document.getElementById('shipper-password').value,
        database: document.getElementById('shipper-database').value
    };

    try {
        const response = await fetch('/api/config/test-shipper', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            showToast('ShipperPlatform connection successful!', 'success');
        } else {
            showToast('ShipperPlatform connection failed: ' + (result.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        showToast('Error testing connection: ' + error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Test Connection';
    }
}

async function testBackofficeConnection() {
    const btn = document.getElementById('btn-test-backoffice');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Testing...';

    const data = {
        host: document.getElementById('backoffice-host').value,
        port: parseInt(document.getElementById('backoffice-port').value),
        user: document.getElementById('backoffice-user').value,
        password: document.getElementById('backoffice-password').value,
        database: document.getElementById('backoffice-database').value
    };

    try {
        const response = await fetch('/api/config/test-backoffice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            showToast('BackOffice connection successful!', 'success');
        } else {
            showToast('BackOffice connection failed: ' + (result.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        showToast('Error testing connection: ' + error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Test Connection';
    }
}

async function testInventoryConnection() {
    const btn = document.getElementById('btn-test-inventory');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Testing...';

    const data = {
        host: document.getElementById('inventory-host').value,
        port: parseInt(document.getElementById('inventory-port').value),
        user: document.getElementById('inventory-user').value,
        password: document.getElementById('inventory-password').value,
        database: document.getElementById('inventory-database').value
    };

    try {
        const response = await fetch('/api/config/test-inventory', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            showToast('Inventory connection successful!', 'success');
        } else {
            showToast('Inventory connection failed: ' + (result.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        showToast('Error testing connection: ' + error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Test Connection';
    }
}

async function saveDbConfig() {
    const btn = document.getElementById('btn-save-db');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Saving...';

    const config = {
        shipper_host: document.getElementById('shipper-host').value,
        shipper_port: parseInt(document.getElementById('shipper-port').value),
        shipper_user: document.getElementById('shipper-user').value,
        shipper_password: document.getElementById('shipper-password').value,
        shipper_database: document.getElementById('shipper-database').value,
        backoffice_host: document.getElementById('backoffice-host').value,
        backoffice_port: parseInt(document.getElementById('backoffice-port').value),
        backoffice_user: document.getElementById('backoffice-user').value,
        backoffice_password: document.getElementById('backoffice-password').value,
        backoffice_database: document.getElementById('backoffice-database').value,
        inventory_enabled: document.getElementById('inventory-enabled').checked ? 1 : 0,
        inventory_host: document.getElementById('inventory-host').value,
        inventory_port: parseInt(document.getElementById('inventory-port').value) || 1433,
        inventory_user: document.getElementById('inventory-user').value,
        inventory_password: document.getElementById('inventory-password').value,
        inventory_database: document.getElementById('inventory-database').value
    };

    try {
        const response = await fetch('/api/config/sqlserver', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        const result = await response.json();

        if (result.success) {
            showToast('Database configuration saved successfully!', 'success');
            // Clear password fields for security
            document.getElementById('shipper-password').value = '';
            document.getElementById('backoffice-password').value = '';
            document.getElementById('inventory-password').value = '';
        } else {
            showToast('Failed to save configuration: ' + (result.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        showToast('Error saving configuration: ' + error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Save Database Configuration';
    }
}

async function saveDefaults() {
    const btn = document.getElementById('btn-save-defaults');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Saving...';

    const defaults = {
        customer_id: parseInt(document.getElementById('customer-id').value),
        default_status: parseInt(document.getElementById('default-status').value),
        quotation_title_prefix: document.getElementById('title-prefix').value,
        polling_interval_seconds: parseInt(document.getElementById('polling-interval').value)
    };

    // Validation
    if (defaults.polling_interval_seconds < 10) {
        showToast('Polling interval must be at least 10 seconds', 'error');
        btn.disabled = false;
        btn.textContent = 'Save Defaults';
        return;
    }

    try {
        const response = await fetch('/api/config/quotation-defaults', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(defaults)
        });

        const result = await response.json();

        if (result.success) {
            showToast('Quotation defaults saved successfully!', 'success');
        } else {
            showToast('Failed to save defaults: ' + (result.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        showToast('Error saving defaults: ' + error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Save Defaults';
    }
}

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    loadConfig();
    loadDefaults();

    document.getElementById('btn-test-shipper').addEventListener('click', testShipperConnection);
    document.getElementById('btn-test-backoffice').addEventListener('click', testBackofficeConnection);
    document.getElementById('btn-test-inventory').addEventListener('click', testInventoryConnection);
    document.getElementById('btn-save-db').addEventListener('click', saveDbConfig);
    document.getElementById('btn-save-defaults').addEventListener('click', saveDefaults);
});
