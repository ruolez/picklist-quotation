from typing import Optional
from datetime import datetime, timedelta
from database import SQLiteManager, SQLServerManager


class PicklistConverter:
    def __init__(self, sqlite_manager: SQLiteManager):
        self.sqlite_manager = sqlite_manager

    def _truncate_string(self, value, max_length):
        """Safely truncate a string to max_length"""
        if value is None:
            return None
        str_value = str(value)
        return str_value[:max_length] if len(str_value) > max_length else str_value

    def get_pending_picklists(self, shipper_db: SQLServerManager) -> list:
        """Get all picklists with conversion status"""
        converted_ids = self.sqlite_manager.get_converted_picklist_ids()
        archived_ids = self.sqlite_manager.get_archived_picklist_ids()

        with shipper_db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM dbo.pick_lists")
            all_picklists = cursor.fetchall()

        # Include all picklists except archived ones, with conversion status
        result = []
        for pl in all_picklists:
            if pl['id'] not in archived_ids:
                pl_dict = dict(pl)
                pl_dict['is_converted'] = pl['id'] in converted_ids
                result.append(pl_dict)

        return result

    def get_picklist_products(self, shipper_db: SQLServerManager, picklist_id: int) -> list:
        """Get products for a specific picklist, excluding zero/null quantities"""
        with shipper_db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM dbo.pick_list_products
                WHERE id_pick_list = %s
                  AND ISNULL(amount, 0) > 0
            """, (picklist_id,))
            return cursor.fetchall()

    def match_product_by_barcode(self, backoffice_db: SQLServerManager, barcode: str) -> Optional[dict]:
        """Match product in BackOffice database using barcode/UPC"""
        with backoffice_db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM dbo.Items_tbl
                WHERE ProductUPC = %s
            """, (barcode,))
            return cursor.fetchone()

    def get_inventory_db_manager(self) -> Optional[SQLServerManager]:
        """Get inventory database manager if configured and enabled"""
        config = self.sqlite_manager.get_config()
        if not config or not config.get('inventory_enabled'):
            return None

        try:
            return SQLServerManager(
                host=config['inventory_host'],
                port=config['inventory_port'],
                user=config['inventory_user'],
                password=config['inventory_password'],
                database=config['inventory_database']
            )
        except Exception:
            return None

    def lookup_in_inventory(self, barcodes: list) -> dict:
        """
        Lookup products in inventory database by barcodes
        Returns: dict mapping barcode -> full product record
        """
        inventory_db = self.get_inventory_db_manager()
        if not inventory_db:
            return {}

        try:
            with inventory_db.get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ','.join(['%s'] * len(barcodes))
                query = f"SELECT * FROM dbo.Items_tbl WHERE ProductUPC IN ({placeholders})"
                cursor.execute(query, tuple(barcodes))
                results = cursor.fetchall()
                return {row['ProductUPC']: row for row in results}
        except Exception:
            return {}

    def check_missing_products(self, picklist_ids: list) -> dict:
        """
        Check which products from picklists are missing in BackOffice
        Returns: {
            'missing': [list of missing products],
            'total_products': count,
            'missing_count': count
        }
        """
        config = self.sqlite_manager.get_config()
        if not config:
            return {'error': 'Database configuration not found'}

        try:
            shipper_db = SQLServerManager(
                host=config['shipper_host'],
                port=config['shipper_port'],
                user=config['shipper_user'],
                password=config['shipper_password'],
                database=config['shipper_database']
            )

            backoffice_db = SQLServerManager(
                host=config['backoffice_host'],
                port=config['backoffice_port'],
                user=config['backoffice_user'],
                password=config['backoffice_password'],
                database=config['backoffice_database']
            )

            # Step 1: Collect all products from all picklists
            all_products = []  # List of (picklist_id, product) tuples
            for picklist_id in picklist_ids:
                products = self.get_picklist_products(shipper_db, picklist_id)
                for product in products:
                    all_products.append((picklist_id, product))

            total_products = len(all_products)

            # Step 2: Extract all barcodes (excluding None/empty)
            barcodes_to_check = []
            for picklist_id, product in all_products:
                barcode = product.get('barcode')
                if barcode:
                    barcodes_to_check.append(barcode)

            # Step 3: Batch query BackOffice for all barcodes at once
            matched_barcodes = set()
            if barcodes_to_check:
                with backoffice_db.get_connection() as conn:
                    cursor = conn.cursor()
                    # Build parameterized query for batch lookup
                    placeholders = ','.join(['%s'] * len(barcodes_to_check))
                    query = f"SELECT ProductUPC FROM dbo.Items_tbl WHERE ProductUPC IN ({placeholders})"
                    cursor.execute(query, tuple(barcodes_to_check))
                    results = cursor.fetchall()
                    matched_barcodes = {row['ProductUPC'] for row in results}

            # Step 4: Check inventory database for products not in BackOffice
            missing_barcodes = [bc for bc in barcodes_to_check if bc not in matched_barcodes]
            inventory_products = {}
            if missing_barcodes:
                inventory_products = self.lookup_in_inventory(missing_barcodes)

            # Step 5: Identify missing products with status
            missing_products = []
            can_copy_count = 0
            for picklist_id, product in all_products:
                barcode = product.get('barcode')

                if not barcode:
                    missing_products.append({
                        'picklist_id': picklist_id,
                        'barcode': 'N/A',
                        'name': product.get('name', 'Unknown'),
                        'amount': product.get('amount', 0),
                        'reason': 'No barcode',
                        'status': 'not_found',
                        'inventory_product': None
                    })
                elif barcode not in matched_barcodes:
                    # Check if found in inventory
                    if barcode in inventory_products:
                        missing_products.append({
                            'picklist_id': picklist_id,
                            'barcode': barcode,
                            'name': product.get('name', 'Unknown'),
                            'amount': product.get('amount', 0),
                            'reason': 'Found in Inventory',
                            'status': 'found_in_inventory',
                            'inventory_product': inventory_products[barcode]
                        })
                        can_copy_count += 1
                    else:
                        missing_products.append({
                            'picklist_id': picklist_id,
                            'barcode': barcode,
                            'name': product.get('name', 'Unknown'),
                            'amount': product.get('amount', 0),
                            'reason': 'Not found in BackOffice or Inventory',
                            'status': 'not_found',
                            'inventory_product': None
                        })

            return {
                'missing': missing_products,
                'total_products': total_products,
                'missing_count': len(missing_products),
                'can_copy_count': can_copy_count,
                'truly_missing_count': len(missing_products) - can_copy_count
            }

        except Exception as e:
            return {'error': f'Error checking products: {str(e)}'}

    def copy_products_from_inventory(self, barcodes: list) -> dict:
        """
        Copy products from Inventory database to BackOffice database
        Returns: {
            'success': bool,
            'copied': [list of successfully copied barcodes],
            'failed': [{barcode, error}, ...]
        }
        """
        config = self.sqlite_manager.get_config()
        if not config:
            return {'success': False, 'error': 'Database configuration not found'}

        inventory_db = self.get_inventory_db_manager()
        if not inventory_db:
            return {'success': False, 'error': 'Inventory database not configured or not enabled'}

        try:
            backoffice_db = SQLServerManager(
                host=config['backoffice_host'],
                port=config['backoffice_port'],
                user=config['backoffice_user'],
                password=config['backoffice_password'],
                database=config['backoffice_database']
            )

            # Step 1: Get BackOffice Items_tbl schema (excluding IDENTITY columns)
            with backoffice_db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COLUMN_NAME
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_NAME = 'Items_tbl'
                    AND COLUMNPROPERTY(OBJECT_ID(TABLE_SCHEMA + '.' + TABLE_NAME), COLUMN_NAME, 'IsIdentity') = 0
                    ORDER BY ORDINAL_POSITION
                """)
                backoffice_columns = [row['COLUMN_NAME'] for row in cursor.fetchall()]
                print(f"DEBUG: BackOffice Items_tbl has {len(backoffice_columns)} non-identity columns")

            # Step 2: Fetch products from inventory
            inventory_products = self.lookup_in_inventory(barcodes)
            if not inventory_products:
                return {'success': False, 'error': 'No products found in inventory for given barcodes'}

            copied = []
            failed = []

            # Step 3: Insert each product into BackOffice
            for barcode in barcodes:
                if barcode not in inventory_products:
                    failed.append({'barcode': barcode, 'error': 'Not found in inventory'})
                    continue

                product = inventory_products[barcode]

                try:
                    with backoffice_db.get_connection() as conn:
                        cursor = conn.cursor()

                        # Build dynamic INSERT based on available columns
                        common_columns = [col for col in backoffice_columns if col in product]

                        if not common_columns:
                            failed.append({'barcode': barcode, 'error': 'No matching columns between databases'})
                            continue

                        columns_str = ', '.join(common_columns)
                        placeholders = ', '.join(['%s'] * len(common_columns))
                        values = tuple(product[col] for col in common_columns)

                        insert_query = f"INSERT INTO dbo.Items_tbl ({columns_str}) VALUES ({placeholders})"

                        print(f"DEBUG: Inserting {len(common_columns)} columns for barcode {barcode}")

                        cursor.execute(insert_query, values)
                        conn.commit()
                        copied.append(barcode)

                except Exception as e:
                    print(f"ERROR: Failed to copy barcode {barcode}: {str(e)}")
                    failed.append({'barcode': barcode, 'error': str(e)})

            return {
                'success': len(copied) > 0,
                'copied': copied,
                'failed': failed,
                'copied_count': len(copied),
                'failed_count': len(failed)
            }

        except Exception as e:
            print(f"ERROR: copy_products_from_inventory exception: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'error': f'Error copying products: {str(e)}'}

    def auto_sync_from_inventory(self, backoffice_db: SQLServerManager, missing_barcodes: list) -> dict:
        """
        Automatically sync missing products from Inventory to BackOffice during conversion
        Returns: {
            'synced_count': int,
            'failed_count': int,
            'synced_barcodes': [list of successfully synced barcodes],
            'failed_barcodes': [list of barcodes that couldn't be synced]
        }
        """
        if not missing_barcodes:
            return {
                'synced_count': 0,
                'failed_count': 0,
                'synced_barcodes': [],
                'failed_barcodes': []
            }

        # Check if inventory database is configured
        inventory_db = self.get_inventory_db_manager()
        if not inventory_db:
            print("INFO: Inventory database not configured, skipping auto-sync")
            return {
                'synced_count': 0,
                'failed_count': len(missing_barcodes),
                'synced_barcodes': [],
                'failed_barcodes': missing_barcodes
            }

        print(f"INFO: Attempting to auto-sync {len(missing_barcodes)} missing products from Inventory")

        # Look up products in Inventory
        inventory_products = self.lookup_in_inventory(missing_barcodes)

        if not inventory_products:
            print(f"INFO: None of the missing products found in Inventory database")
            return {
                'synced_count': 0,
                'failed_count': len(missing_barcodes),
                'synced_barcodes': [],
                'failed_barcodes': missing_barcodes
            }

        # Attempt to copy found products to BackOffice
        found_barcodes = list(inventory_products.keys())
        print(f"INFO: Found {len(found_barcodes)} products in Inventory, attempting to copy to BackOffice")

        copy_result = self.copy_products_from_inventory(found_barcodes)

        synced_barcodes = copy_result.get('copied', [])
        failed_to_copy = [item['barcode'] for item in copy_result.get('failed', [])]

        # Products not found in inventory at all
        not_in_inventory = [bc for bc in missing_barcodes if bc not in inventory_products]

        all_failed = failed_to_copy + not_in_inventory

        print(f"INFO: Auto-sync complete - Synced: {len(synced_barcodes)}, Failed: {len(all_failed)}")
        if synced_barcodes:
            print(f"INFO: Successfully synced barcodes: {', '.join(synced_barcodes)}")
        if all_failed:
            print(f"INFO: Failed to sync barcodes: {', '.join(all_failed)}")

        return {
            'synced_count': len(synced_barcodes),
            'failed_count': len(all_failed),
            'synced_barcodes': synced_barcodes,
            'failed_barcodes': all_failed
        }

    def get_next_quotation_number(self, backoffice_db: SQLServerManager) -> int:
        """Get the next quotation number by finding max and adding 1"""
        with backoffice_db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MAX(CAST(QuotationNumber AS BIGINT)) AS MaxNumber
                FROM dbo.Quotations_tbl
                WHERE ISNUMERIC(QuotationNumber) = 1
            """)
            result = cursor.fetchone()
            max_number = result['MaxNumber'] if result and result['MaxNumber'] else 0
            return max_number + 1

    def get_customer_data(self, backoffice_db: SQLServerManager, customer_id: int) -> Optional[dict]:
        """Fetch customer information from Customers_tbl"""
        with backoffice_db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT BusinessName, AccountNo, ShipTo, ShipAddress1, ShipAddress2,
                       ShipContact, ShipCity, ShipState, ShipZipCode, ShipPhone_Number,
                       SalesRepID
                FROM dbo.Customers_tbl
                WHERE CustomerID = %s
            """, (customer_id,))
            return cursor.fetchone()

    def create_quotation(self, backoffice_db: SQLServerManager, picklist_id: int,
                        products: list, customer_id: int, status: int,
                        title_prefix: str) -> tuple[bool, Optional[int], Optional[str], Optional[str]]:
        """
        Create quotation from picklist products
        Returns: (success, quotation_id, quotation_number, error_message)
        """
        matched_products = []
        unmatched_barcodes = []

        # Step 1: Collect all barcodes
        barcodes_to_check = []
        for product in products:
            barcode = product.get('barcode')
            if not barcode:
                unmatched_barcodes.append(f"Product '{product.get('name')}' has no barcode")
            else:
                barcodes_to_check.append(barcode)

        # Step 2: Batch query to get all matching products from BackOffice with UnitDesc
        barcode_to_item = {}
        if barcodes_to_check:
            with backoffice_db.get_connection() as conn:
                cursor = conn.cursor()
                placeholders = ','.join(['%s'] * len(barcodes_to_check))
                query = f"""
                    SELECT i.*, u.UnitDesc
                    FROM dbo.Items_tbl i
                    LEFT JOIN dbo.Units_tbl u ON i.UnitID = u.UnitID
                    WHERE i.ProductUPC IN ({placeholders})
                """
                cursor.execute(query, tuple(barcodes_to_check))
                results = cursor.fetchall()
                # Build lookup dictionary
                for item in results:
                    barcode_to_item[item['ProductUPC']] = item

        # Step 3: Match products using the lookup dictionary
        missing_barcodes = []  # Track barcodes not found in BackOffice (for auto-sync)
        for product in products:
            barcode = product.get('barcode')
            if not barcode:
                continue  # Already added to unmatched_barcodes above

            matched = barcode_to_item.get(barcode)
            if not matched:
                missing_barcodes.append(barcode)  # Track for auto-sync
                unmatched_barcodes.append(f"Barcode '{barcode}' (Product: {product.get('name')})")
            else:
                matched_products.append({
                    'pick_list_product': product,
                    'item': matched
                })

        # Step 4: Attempt automatic sync from Inventory for missing products
        if missing_barcodes:
            print(f"INFO: {len(missing_barcodes)} products not found in BackOffice, attempting auto-sync from Inventory")
            sync_result = self.auto_sync_from_inventory(backoffice_db, missing_barcodes)

            # If any products were successfully synced, re-query BackOffice
            if sync_result['synced_count'] > 0:
                synced_barcodes = sync_result['synced_barcodes']
                print(f"INFO: Re-querying BackOffice for {len(synced_barcodes)} newly synced products")

                with backoffice_db.get_connection() as conn:
                    cursor = conn.cursor()
                    placeholders = ','.join(['%s'] * len(synced_barcodes))
                    query = f"""
                        SELECT i.*, u.UnitDesc
                        FROM dbo.Items_tbl i
                        LEFT JOIN dbo.Units_tbl u ON i.UnitID = u.UnitID
                        WHERE i.ProductUPC IN ({placeholders})
                    """
                    cursor.execute(query, tuple(synced_barcodes))
                    synced_items = cursor.fetchall()

                    # Update barcode_to_item with newly synced products
                    for item in synced_items:
                        barcode_to_item[item['ProductUPC']] = item

                # Re-match products with updated barcode_to_item
                matched_products = []
                unmatched_barcodes = []

                for product in products:
                    barcode = product.get('barcode')
                    if not barcode:
                        unmatched_barcodes.append(f"Product '{product.get('name')}' has no barcode")
                        continue

                    matched = barcode_to_item.get(barcode)
                    if not matched:
                        unmatched_barcodes.append(f"Barcode '{barcode}' (Product: {product.get('name')})")
                    else:
                        matched_products.append({
                            'pick_list_product': product,
                            'item': matched
                        })

                print(f"INFO: After auto-sync - Matched: {len(matched_products)}, Unmatched: {len(unmatched_barcodes)}")

        # If any products couldn't be matched after auto-sync, fail the conversion
        if unmatched_barcodes:
            error_msg = f"Unable to match products: {', '.join(unmatched_barcodes)}"
            return (False, None, None, error_msg)

        # All products matched, proceed with quotation creation
        try:
            # Fetch customer data
            customer = self.get_customer_data(backoffice_db, customer_id)
            if not customer:
                return (False, None, None, f"Customer ID {customer_id} not found")

            with backoffice_db.get_connection() as conn:
                cursor = conn.cursor()

                # Get next quotation number (auto-increment)
                quotation_number = str(self.get_next_quotation_number(backoffice_db))
                quotation_title = f"{title_prefix} {picklist_id}"
                quotation_date = datetime.now()
                expiration_date = quotation_date + timedelta(days=365)

                # Insert into Quotations_tbl with all fields
                cursor.execute("""
                    INSERT INTO dbo.Quotations_tbl
                    (QuotationNumber, QuotationDate, QuotationTitle, CustomerID, Status,
                     PoNumber, AutoOrderNo, ExpirationDate,
                     BusinessName, AccountNo, Shipto, ShipAddress1, ShipAddress2,
                     ShipContact, ShipCity, ShipState, ShipZipCode, ShipPhoneNo,
                     ShipperID, SalesRepID, TermID,
                     Header, Footer, Notes, Memo, flaged)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    SELECT SCOPE_IDENTITY() AS QuotationID;
                """, (
                    self._truncate_string(quotation_number, 20),
                    quotation_date,
                    self._truncate_string(quotation_title, 50),
                    customer_id,
                    status,
                    '',  # PoNumber
                    None,  # AutoOrderNo - set to NULL
                    expiration_date,
                    self._truncate_string(customer.get('BusinessName') or '', 50),
                    self._truncate_string(customer.get('AccountNo') or '', 13),
                    self._truncate_string(customer.get('ShipTo') or '', 50),
                    self._truncate_string(customer.get('ShipAddress1') or '', 50),
                    self._truncate_string(customer.get('ShipAddress2') or '', 50),
                    self._truncate_string(customer.get('ShipContact') or '', 50),
                    self._truncate_string(customer.get('ShipCity') or '', 20),
                    self._truncate_string(customer.get('ShipState') or '', 3),
                    self._truncate_string(customer.get('ShipZipCode') or '', 10),
                    self._truncate_string(customer.get('ShipPhone_Number') or '', 13),
                    0,  # ShipperID
                    customer.get('SalesRepID') or 1,  # SalesRepID (from customer, fallback to 1)
                    1,  # TermID
                    '',  # Header
                    '',  # Footer
                    '',  # Notes
                    '',  # Memo
                    0   # flaged
                ))

                result = cursor.fetchone()
                quotation_id = int(result['QuotationID'])

                # Insert quotation details
                for matched in matched_products:
                    product = matched['pick_list_product']
                    item = matched['item']

                    qty = product['amount']  # Safe because we filter out zero/null quantities
                    unit_price = item.get('UnitPrice', 0) or 0
                    unit_cost = item.get('UnitCost', 0) or 0
                    extended_price = qty * unit_price
                    extended_cost = qty * unit_cost

                    cursor.execute("""
                        INSERT INTO dbo.QuotationsDetails_tbl
                        (QuotationID, CateID, SubCateID, UnitDesc, UnitQty,
                         ProductID, ProductSKU, ProductUPC, ProductDescription, ItemSize,
                         ExpDate, ReasonID, LineMessage,
                         UnitPrice, OriginalPrice, RememberPrice, UnitCost,
                         Discount, ds_Percent, Qty, ItemWeight,
                         ExtendedPrice, ExtendedDisc, ExtendedCost,
                         PromotionID, PromotionLine, ActExtendedPrice,
                         SPPromoted, SPPromotionDescription,
                         Taxable, ItemTaxID, Catch, Flag)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        quotation_id,
                        item.get('CateID'),
                        item.get('SubCateID'),
                        self._truncate_string(item.get('UnitDesc'), 50),
                        1,  # UnitQty
                        item.get('ProductID'),
                        self._truncate_string(item.get('ProductSKU'), 20),
                        self._truncate_string(item.get('ProductUPC'), 20),
                        self._truncate_string(item.get('ProductDescription'), 50),
                        self._truncate_string(item.get('ItemSize'), 10),
                        expiration_date,  # ExpDate (1 year from today)
                        0,  # ReasonID
                        '',  # LineMessage
                        unit_price,
                        unit_price,  # OriginalPrice = UnitPrice
                        0,  # RememberPrice
                        unit_cost,
                        0,  # Discount
                        0,  # ds_Percent
                        qty,
                        item.get('ItemWeight'),
                        extended_price,
                        0,  # ExtendedDisc
                        extended_cost,
                        0,  # PromotionID
                        0,  # PromotionLine
                        extended_price,  # ActExtendedPrice = ExtendedPrice
                        0,  # SPPromoted
                        '',  # SPPromotionDescription
                        0,  # Taxable
                        0,  # ItemTaxID
                        0,  # Catch
                        0   # Flag
                    ))

                # Calculate QuotationTotal from line items
                cursor.execute("""
                    SELECT ISNULL(SUM(ExtendedPrice), 0) AS TotalAmount
                    FROM dbo.QuotationsDetails_tbl
                    WHERE QuotationID = %s
                """, (quotation_id,))
                total_result = cursor.fetchone()
                quotation_total = total_result['TotalAmount'] if total_result else 0

                # Update Quotations_tbl with QuotationTotal
                cursor.execute("""
                    UPDATE dbo.Quotations_tbl
                    SET QuotationTotal = %s
                    WHERE QuotationID = %s
                """, (quotation_total, quotation_id))

                conn.commit()
                return (True, quotation_id, quotation_number, None)

        except Exception as e:
            return (False, None, None, f"Database error: {str(e)}")

    def convert_picklist(self, picklist_id: int) -> tuple[bool, Optional[str]]:
        """
        Convert a single picklist to quotation
        Returns: (success, error_message)
        """
        config = self.sqlite_manager.get_config()
        if not config:
            return (False, "Database configuration not found")

        defaults = self.sqlite_manager.get_quotation_defaults()
        if not defaults:
            return (False, "Quotation defaults not configured")

        try:
            # Create database managers
            shipper_db = SQLServerManager(
                host=config['shipper_host'],
                port=config['shipper_port'],
                user=config['shipper_user'],
                password=config['shipper_password'],
                database=config['shipper_database']
            )

            backoffice_db = SQLServerManager(
                host=config['backoffice_host'],
                port=config['backoffice_port'],
                user=config['backoffice_user'],
                password=config['backoffice_password'],
                database=config['backoffice_database']
            )

            # Get picklist products (excludes zero/null quantity products)
            products = self.get_picklist_products(shipper_db, picklist_id)
            if not products:
                error_msg = f"Picklist #{picklist_id} has no products with quantity > 0"
                try:
                    self.sqlite_manager.log_conversion(picklist_id, False, error_message=error_msg)
                except Exception as log_error:
                    print(f"WARNING: Failed to log error to SQLite: {log_error}")
                return (False, error_msg)

            # Create quotation
            success, quotation_id, quotation_number, error_msg = self.create_quotation(
                backoffice_db,
                picklist_id,
                products,
                defaults['customer_id'],
                defaults['default_status'],
                defaults['quotation_title_prefix']
            )

            # Log conversion
            try:
                self.sqlite_manager.log_conversion(
                    picklist_id,
                    success,
                    quotation_id,
                    quotation_number,
                    error_msg
                )
            except Exception as log_error:
                print(f"WARNING: Failed to log conversion to SQLite: {log_error}")
                # Don't fail the conversion if logging fails

            return (success, error_msg)

        except Exception as e:
            error_msg = f"Conversion error: {str(e)}"
            try:
                self.sqlite_manager.log_conversion(picklist_id, False, error_message=error_msg)
            except Exception as log_error:
                print(f"WARNING: Failed to log error to SQLite: {log_error}")
            return (False, error_msg)

    def convert_all_pending(self) -> dict:
        """
        Convert all pending picklists
        Returns: dictionary with conversion results
        """
        config = self.sqlite_manager.get_config()
        if not config:
            return {'error': 'Database configuration not found'}

        try:
            shipper_db = SQLServerManager(
                host=config['shipper_host'],
                port=config['shipper_port'],
                user=config['shipper_user'],
                password=config['shipper_password'],
                database=config['shipper_database']
            )

            pending_picklists = self.get_pending_picklists(shipper_db)

            results = {
                'total_pending': len(pending_picklists),
                'converted': 0,
                'failed': 0,
                'errors': []
            }

            for picklist in pending_picklists:
                picklist_id = picklist['id']
                success, error_msg = self.convert_picklist(picklist_id)

                if success:
                    results['converted'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append({
                        'picklist_id': picklist_id,
                        'error': error_msg
                    })

            return results

        except Exception as e:
            return {'error': f'Error processing picklists: {str(e)}'}
