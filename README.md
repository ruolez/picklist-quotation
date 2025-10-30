# Picklist to Quotation Converter

Modern web application that automatically monitors picklists in the ShipperPlatform database and converts them into quotations in the BackOffice database.

## Features

- **Automatic Monitoring:** Background service polls ShipperPlatform database at configurable intervals
- **Smart Product Matching:** Matches products using barcode/UPC lookup
- **Manual Trigger:** Convert picklists on-demand with a single button click
- **Real-time Dashboard:** View statistics and conversion status
- **Conversion History:** Complete audit trail with timestamps and error details
- **Web-based Configuration:** Easy setup through browser interface
- **Material Design 3 UI:** Clean, professional, responsive interface
- **No Caching:** Instant UI updates without refresh delays

## Technology Stack

- **Backend:** Python 3.11 + Flask
- **Frontend:** Vanilla JavaScript, HTML5, CSS3 (Material Design 3)
- **Databases:**
  - SQLite: Local configuration and tracking
  - MS SQL Server: ShipperPlatform and BackOffice databases
- **Connectivity:** pymssql + FreeTDS for MS SQL Server
- **Deployment:** Docker + Docker Compose
- **Port:** Auto-detected (5000-5100 range)

## Quick Start

### Production Installation (Ubuntu 24 LTS)

For a clean Ubuntu 24 server, use the automated installer:

```bash
curl -fsSL https://raw.githubusercontent.com/ruolez/picklist-quotation/main/install.sh | sudo bash
```

The installer will:
- Auto-detect and confirm your server IP address
- Install Docker and Docker Compose if needed
- Configure the application to run on port 80
- Set up CORS for your IP address
- Create systemd service for auto-start

**Installer Options:**
1. **Install** - Fresh installation
2. **Update** - Pull latest from GitHub (backs up data first)
3. **Remove** - Complete uninstallation

### Development Installation

#### Prerequisites

- Docker and Docker Compose installed
- Access to ShipperPlatform and BackOffice MS SQL Server databases
- Network connectivity to database servers

#### Installation

1. Clone the repository:
```bash
git clone https://github.com/ruolez/picklist-quotation.git
cd picklist-quotation
```

2. Build and start the Docker container:
```bash
docker-compose up -d --build
```

3. Access the application:
```
http://localhost:5000
```

If port 5000 is in use, the application will automatically find the next available port between 5000-5100. Check the Docker logs to see which port was selected:
```bash
docker logs picklist-quotation-converter
```

### Initial Configuration

1. Navigate to **Settings** page
2. Configure **ShipperPlatform Database:**
   - Host, Port, Username, Password, Database Name
   - Click "Test Connection" to verify
3. Configure **BackOffice Database:**
   - Host, Port, Username, Password, Database Name
   - Click "Test Connection" to verify
4. Click **Save Database Configuration**
5. Configure **Quotation Defaults:**
   - Customer ID (from Customers_tbl)
   - Default Status (e.g., 1 = Pending)
   - Quotation Title Prefix (e.g., "PL")
   - Polling Interval (in seconds, minimum 10)
6. Click **Save Defaults**

## How It Works

### Workflow

1. **Monitoring:**
   - Background service polls `pick_lists` table in ShipperPlatform
   - Identifies picklists not yet converted (based on local tracking)

2. **Product Matching:**
   - Reads products from `pick_list_products` for each picklist
   - Matches products to `Items_tbl` in BackOffice using barcode/UPC
   - Fails conversion if any products can't be matched

3. **Quotation Creation:**
   - Inserts new record into `Quotations_tbl`
   - Inserts product lines into `QuotationsDetails_tbl`
   - Generates unique quotation number
   - Logs conversion in local SQLite database

4. **Tracking:**
   - Successfully converted picklists are tracked locally
   - Prevents duplicate conversions
   - Maintains full audit trail

### Database Schema

**ShipperPlatform:**
- `pick_lists` - Picklist headers
- `pick_list_products` - Products in each picklist

**BackOffice:**
- `Quotations_tbl` - Quotation headers
- `QuotationsDetails_tbl` - Quotation line items
- `Items_tbl` - Product catalog (for matching)
- `Customers_tbl` - Customer information

**Local SQLite:**
- `config` - Database connection settings
- `quotation_defaults` - Default quotation values
- `conversion_tracking` - Conversion history and tracking

## Usage

### Dashboard

- **Statistics:** View total converted, pending, failed, and success rate
- **Polling Service:**
  - Start/Stop auto-polling
  - Status indicator shows if service is running
- **Manual Trigger:**
  - Click "Convert Pending Picklists" to process immediately
  - View conversion results with error details

### History

- View complete conversion history
- See successful and failed conversions
- Error messages for failed conversions
- Pagination support (50 records per page)
- Auto-refreshes every 30 seconds

### Settings

- Configure MS SQL Server connections
- Test connections before saving
- Set quotation defaults
- Configure polling interval
- All settings stored securely

## API Endpoints

### Configuration
- `GET /api/config/sqlserver` - Get database config (no passwords)
- `POST /api/config/sqlserver` - Save database config
- `POST /api/config/test-shipper` - Test ShipperPlatform connection
- `POST /api/config/test-backoffice` - Test BackOffice connection
- `GET /api/config/quotation-defaults` - Get defaults
- `POST /api/config/quotation-defaults` - Save defaults

### Operations
- `POST /api/convert/trigger` - Trigger manual conversion
- `GET /api/convert/status` - Get conversion status
- `POST /api/poller/start` - Start auto-polling
- `POST /api/poller/stop` - Stop auto-polling
- `GET /api/poller/status` - Get polling status

### Data
- `GET /api/dashboard/stats` - Dashboard statistics
- `GET /api/history` - Conversion history (paginated)
- `GET /api/picklists/pending` - List unconverted picklists
- `GET /health` - Health check

## Project Structure

```
picklist-quotation/
├── docker-compose.yml           # Docker configuration
├── Dockerfile                   # Python + FreeTDS image
├── requirements.txt             # Python dependencies
├── README.md                    # This file
├── dbschema.md                  # Database schema documentation
├── .gitignore                   # Git ignore rules
├── app/
│   ├── __init__.py
│   ├── main.py                  # Flask app + API endpoints
│   ├── database.py              # SQLite + MS SQL managers
│   ├── converter.py             # Conversion logic
│   ├── poller.py               # Background polling service
│   ├── static/
│   │   ├── css/style.css       # Material Design 3 styles
│   │   └── js/
│   │       ├── dashboard.js
│   │       ├── history.js
│   │       └── settings.js
│   └── templates/
│       ├── index.html          # Dashboard
│       ├── history.html        # History page
│       └── settings.html       # Settings page
└── data/
    ├── app.db                  # SQLite database (auto-created)
    └── .gitkeep
```

## Field Mappings

### Quotations_tbl
- `QuotationNumber` - Generated (e.g., "PL-123-20251029143045")
- `QuotationDate` - Current datetime
- `QuotationTitle` - From settings prefix + picklist ID
- `CustomerID` - From settings
- `Status` - From settings
- Other fields - NULL or from customer lookup

### QuotationsDetails_tbl
- `QuotationID` - From inserted quotation
- `ProductID`, `ProductSKU`, `ProductUPC`, `ProductDescription` - From Items_tbl match
- `Qty` - From pick_list_products.amount
- `UnitPrice`, `UnitCost` - From Items_tbl
- `ExtendedPrice` - Calculated (Qty × UnitPrice)
- `CateID`, `SubCateID`, `ItemSize`, `ItemWeight` - From Items_tbl
- Other fields - NULL or defaults

## Troubleshooting

### Connection Issues

**MS SQL Server connection fails:**
- Verify host and port are correct
- Check firewall rules allow connection
- Ensure SQL Server allows remote connections
- Verify credentials have appropriate permissions

**Application won't start:**
- Check Docker logs: `docker logs picklist-quotation-converter`
- Ensure port is available
- Verify Docker has sufficient resources

### Conversion Issues

**Products not matching:**
- Verify barcodes in `pick_list_products.barcode` match `Items_tbl.ProductUPC`
- Check for leading/trailing spaces in barcodes
- Ensure products exist in Items_tbl

**Conversions failing:**
- Check History page for error messages
- Verify Customer ID exists in Customers_tbl
- Ensure BackOffice database connection is working
- Check database permissions for INSERT operations

### Performance

**Polling too frequent:**
- Increase polling interval in Settings
- Check database server load
- Consider stopping auto-polling and using manual trigger

**Slow conversions:**
- Check network latency to database servers
- Verify database indexes on ProductUPC field
- Monitor database server performance

## Docker Commands

**View logs:**
```bash
docker logs -f picklist-quotation-converter
```

**Restart container:**
```bash
docker-compose restart
```

**Stop container:**
```bash
docker-compose down
```

**Rebuild after code changes:**
```bash
docker-compose up -d --build
```

**Access container shell:**
```bash
docker exec -it picklist-quotation-converter bash
```

## Data Persistence

The `data/` directory is mounted as a Docker volume, ensuring:
- Configuration persists across container restarts
- Conversion history is preserved
- No data loss during updates

To backup data:
```bash
cp data/app.db data/app.db.backup
```

## Security Notes

- Database passwords are stored in SQLite (not exposed via API GET requests)
- Run behind nginx reverse proxy in production
- Use HTTPS for production deployments
- Restrict network access to application port
- Regularly backup SQLite database
- Use read-only database credentials if possible

## Development

**Local development without Docker:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app/main.py
```

**Live reload:**
The Docker configuration mounts the `app/` directory as a volume, enabling live code reload during development.

## License

Internal use only.

## Support

For issues or questions, contact the development team.
