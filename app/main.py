from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import socket
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SQLiteManager, SQLServerManager
from converter import PicklistConverter
from poller import PollingService

app = Flask(__name__)

# Configure CORS - allow requests from the configured host
allowed_origin = os.environ.get('ALLOWED_ORIGIN', '*')
CORS(app, origins=allowed_origin, supports_credentials=True)

# Initialize managers
sqlite_manager = SQLiteManager()
converter = PicklistConverter(sqlite_manager)
poller = PollingService(converter, sqlite_manager)


def add_no_cache_headers(response):
    """Add no-cache headers to prevent caching"""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


app.after_request(add_no_cache_headers)


# HTML Pages
@app.route('/')
def index():
    """Picklists page (default landing page)"""
    return render_template('picklists.html')


@app.route('/history')
def history():
    """History page"""
    return render_template('history.html')


@app.route('/picklists')
def picklists():
    """Picklists page"""
    return render_template('picklists.html')


@app.route('/settings')
def settings():
    """Settings page"""
    return render_template('settings.html')


# Configuration API Endpoints
@app.route('/api/config/sqlserver', methods=['GET'])
def get_sqlserver_config():
    """Get MS SQL Server configuration (without passwords)"""
    config = sqlite_manager.get_config()
    if config:
        # Remove passwords before sending
        safe_config = {
            'shipper_host': config.get('shipper_host'),
            'shipper_port': config.get('shipper_port'),
            'shipper_user': config.get('shipper_user'),
            'shipper_database': config.get('shipper_database'),
            'backoffice_host': config.get('backoffice_host'),
            'backoffice_port': config.get('backoffice_port'),
            'backoffice_user': config.get('backoffice_user'),
            'backoffice_database': config.get('backoffice_database'),
            'inventory_host': config.get('inventory_host'),
            'inventory_port': config.get('inventory_port'),
            'inventory_user': config.get('inventory_user'),
            'inventory_database': config.get('inventory_database'),
            'inventory_enabled': config.get('inventory_enabled', 0)
        }
        return jsonify(safe_config)
    return jsonify(None)


@app.route('/api/config/sqlserver', methods=['POST'])
def save_sqlserver_config():
    """Save MS SQL Server configuration"""
    data = request.json
    try:
        sqlite_manager.save_config(data)
        return jsonify({'success': True, 'message': 'Configuration saved'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config/test-shipper', methods=['POST'])
def test_shipper_connection():
    """Test ShipperPlatform database connection"""
    data = request.json
    try:
        db = SQLServerManager(
            host=data['host'],
            port=data['port'],
            user=data['user'],
            password=data['password'],
            database=data['database']
        )
        success, error = db.test_connection()
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': error})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config/test-backoffice', methods=['POST'])
def test_backoffice_connection():
    """Test BackOffice database connection"""
    data = request.json
    try:
        db = SQLServerManager(
            host=data['host'],
            port=data['port'],
            user=data['user'],
            password=data['password'],
            database=data['database']
        )
        success, error = db.test_connection()
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': error})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config/test-inventory', methods=['POST'])
def test_inventory_connection():
    """Test Inventory database connection"""
    data = request.json
    try:
        db = SQLServerManager(
            host=data['host'],
            port=data['port'],
            user=data['user'],
            password=data['password'],
            database=data['database']
        )
        success, error = db.test_connection()
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': error})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config/quotation-defaults', methods=['GET'])
def get_quotation_defaults():
    """Get quotation default settings"""
    defaults = sqlite_manager.get_quotation_defaults()
    return jsonify(defaults)


@app.route('/api/config/quotation-defaults', methods=['POST'])
def save_quotation_defaults():
    """Save quotation default settings"""
    data = request.json
    try:
        sqlite_manager.save_quotation_defaults(data)
        return jsonify({'success': True, 'message': 'Defaults saved'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Conversion API Endpoints
@app.route('/api/convert/trigger', methods=['POST'])
def trigger_conversion():
    """Manually trigger picklist conversion"""
    try:
        results = converter.convert_all_pending()
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/check-products', methods=['POST'])
def check_products():
    """Check for missing products before conversion"""
    try:
        data = request.json
        picklist_ids = data.get('picklist_ids', [])

        if not picklist_ids:
            return jsonify({'success': False, 'error': 'No picklist IDs provided'}), 400

        result = converter.check_missing_products(picklist_ids)

        if 'error' in result:
            return jsonify({'success': False, 'error': result['error']}), 500

        return jsonify({
            'success': True,
            'missing': result['missing'],
            'total_products': result['total_products'],
            'missing_count': result['missing_count'],
            'can_copy_count': result.get('can_copy_count', 0),
            'truly_missing_count': result.get('truly_missing_count', result['missing_count'])
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/copy-products-from-inventory', methods=['POST'])
def copy_products_from_inventory():
    """Copy missing products from Inventory database to BackOffice"""
    try:
        data = request.json
        barcodes = data.get('barcodes', [])

        if not barcodes:
            return jsonify({'success': False, 'error': 'No barcodes provided'}), 400

        result = converter.copy_products_from_inventory(barcodes)

        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error', 'Unknown error')}), 500

        return jsonify({
            'success': True,
            'copied': result['copied'],
            'failed': result['failed'],
            'copied_count': result['copied_count'],
            'failed_count': result['failed_count']
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/convert/selected', methods=['POST'])
def convert_selected():
    """Convert specific picklists by ID"""
    try:
        data = request.json
        picklist_ids = data.get('picklist_ids', [])

        if not picklist_ids:
            return jsonify({'success': False, 'error': 'No picklist IDs provided'}), 400

        results = {
            'total': len(picklist_ids),
            'converted': 0,
            'failed': 0,
            'errors': []
        }

        for picklist_id in picklist_ids:
            success, error_msg = converter.convert_picklist(picklist_id)
            if success:
                results['converted'] += 1
            else:
                results['failed'] += 1
                results['errors'].append({
                    'picklist_id': picklist_id,
                    'error': error_msg
                })

        return jsonify({'success': True, 'results': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/archive/selected', methods=['POST'])
def archive_selected():
    """Archive specific picklists by ID"""
    try:
        data = request.json
        picklist_ids = data.get('picklist_ids', [])

        if not picklist_ids:
            return jsonify({'success': False, 'error': 'No picklist IDs provided'}), 400

        for picklist_id in picklist_ids:
            sqlite_manager.archive_picklist(picklist_id)

        return jsonify({
            'success': True,
            'message': f'Archived {len(picklist_ids)} picklist(s)'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/archive/unarchive', methods=['POST'])
def unarchive_selected():
    """Unarchive specific picklists by ID"""
    try:
        data = request.json
        picklist_ids = data.get('picklist_ids', [])

        if not picklist_ids:
            return jsonify({'success': False, 'error': 'No picklist IDs provided'}), 400

        for picklist_id in picklist_ids:
            sqlite_manager.unarchive_picklist(picklist_id)

        return jsonify({
            'success': True,
            'message': f'Unarchived {len(picklist_ids)} picklist(s)'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/convert/status', methods=['GET'])
def get_conversion_status():
    """Get current conversion status"""
    try:
        config = sqlite_manager.get_config()
        defaults = sqlite_manager.get_quotation_defaults()

        if not config or not defaults:
            return jsonify({
                'configured': False,
                'message': 'Database configuration or defaults not set'
            })

        # Try to get pending picklists count
        shipper_db = SQLServerManager(
            host=config['shipper_host'],
            port=config['shipper_port'],
            user=config['shipper_user'],
            password=config['shipper_password'],
            database=config['shipper_database']
        )

        pending_picklists = converter.get_pending_picklists(shipper_db)

        return jsonify({
            'configured': True,
            'pending_count': len(pending_picklists)
        })
    except Exception as e:
        return jsonify({'configured': False, 'error': str(e)}), 500


# Polling API Endpoints
@app.route('/api/poller/start', methods=['POST'])
def start_poller():
    """Start background polling service"""
    success, message = poller.start()
    return jsonify({'success': success, 'message': message})


@app.route('/api/poller/stop', methods=['POST'])
def stop_poller():
    """Stop background polling service"""
    success, message = poller.stop()
    return jsonify({'success': success, 'message': message})


@app.route('/api/poller/status', methods=['GET'])
def get_poller_status():
    """Get polling service status"""
    status = poller.get_status()
    return jsonify(status)


# Dashboard and Data API Endpoints
@app.route('/api/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    """Get dashboard statistics"""
    try:
        stats = sqlite_manager.get_stats()

        # Get pending count if database is configured
        config = sqlite_manager.get_config()
        pending_count = 0

        if config:
            try:
                shipper_db = SQLServerManager(
                    host=config['shipper_host'],
                    port=config['shipper_port'],
                    user=config['shipper_user'],
                    password=config['shipper_password'],
                    database=config['shipper_database']
                )
                pending_picklists = converter.get_pending_picklists(shipper_db)
                pending_count = len(pending_picklists)
            except:
                pass

        return jsonify({
            'total_converted': stats['total_converted'],
            'total_failed': stats['total_failed'],
            'total_attempts': stats['total_attempts'],
            'pending_count': pending_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/history', methods=['GET'])
def get_history():
    """Get conversion history with pagination and optional status filter"""
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    status = request.args.get('status', 'all', type=str)

    try:
        history = sqlite_manager.get_conversion_history(limit, offset, status)
        return jsonify(history)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/history/delete', methods=['POST'])
def delete_history():
    """Delete specific conversion tracking records"""
    data = request.get_json()
    record_ids = data.get('record_ids', [])

    if not record_ids:
        return jsonify({'error': 'No record IDs provided'}), 400

    try:
        deleted_count = sqlite_manager.delete_conversion_records(record_ids)
        return jsonify({
            'success': True,
            'deleted_count': deleted_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/history/delete-failed', methods=['POST'])
def delete_all_failed():
    """Delete all failed conversion records"""
    try:
        deleted_count = sqlite_manager.delete_all_failed_conversions()
        return jsonify({
            'success': True,
            'deleted_count': deleted_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/picklists/pending', methods=['GET'])
def get_pending_picklists():
    """List unconverted picklists"""
    try:
        config = sqlite_manager.get_config()
        if not config:
            return jsonify({'error': 'Database not configured'}), 400

        shipper_db = SQLServerManager(
            host=config['shipper_host'],
            port=config['shipper_port'],
            user=config['shipper_user'],
            password=config['shipper_password'],
            database=config['shipper_database']
        )

        pending = converter.get_pending_picklists(shipper_db)
        return jsonify(pending)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/picklists/archived', methods=['GET'])
def get_archived_picklists():
    """List archived picklists"""
    try:
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        archived = sqlite_manager.get_archived_picklists(limit, offset)
        return jsonify(archived)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})


def find_available_port(start_port=5000, end_port=5100):
    """Find an available port in the specified range"""
    for port in range(start_port, end_port):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    return start_port


if __name__ == '__main__':
    port = find_available_port()
    print(f"Starting Picklist-Quotation Converter on port {port}")
    app.run(host='0.0.0.0', port=port, debug=True)
