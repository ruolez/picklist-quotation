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
        """Get products for a specific picklist"""
        with shipper_db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM dbo.pick_list_products
                WHERE id_pick_list = %s
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

            # Step 1: Fetch products from inventory
            inventory_products = self.lookup_in_inventory(barcodes)
            if not inventory_products:
                return {'success': False, 'error': 'No products found in inventory for given barcodes'}

            copied = []
            failed = []

            # Step 2: Insert each product into BackOffice
            for barcode in barcodes:
                if barcode not in inventory_products:
                    failed.append({'barcode': barcode, 'error': 'Not found in inventory'})
                    continue

                product = inventory_products[barcode]

                try:
                    with backoffice_db.get_connection() as conn:
                        cursor = conn.cursor()

                        # Get all columns except ProductID (IDENTITY column)
                        # Insert with explicit column list, excluding ProductID
                        insert_query = """
                            INSERT INTO dbo.Items_tbl (
                                ProductSKU, ProductUPC, ProductDescription, CateID, SubCateID,
                                ManuID, UnitID, ItemSize, ItemWeight, UnitPrice, UnitPriceA,
                                UnitPriceB, UnitPriceC, UnitCost, QuantOnHand, QuantOnOrder,
                                ReorderLevel, ReorderQuant, MSRPrice, MasterPackQty, InnerPackQty,
                                UnitQty, UnitID2, UnitQty2, UnitPrice2, UnitID3, UnitQty3,
                                UnitPrice3, UnitID4, UnitQty4, UnitPrice4, LastReceived, LastSold,
                                ExpDate, Discontinued, StLocationID, MinOrderQty, MaxOrderQty,
                                Taxable, SPPromoted, ItemNotes, WebDescription, ItemWebInfo,
                                WebAvailable, WebFeatured, WebNew, WebPrice, WebImage, Allergen1,
                                Allergen2, Allergen3, Allergen4, Allergen5, Allergen6, Allergen7,
                                Allergen8, Allergen9, Allergen10, AllergenFreeFrom, ItemImageLocal
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                            )
                        """

                        values = (
                            product.get('ProductSKU'), product.get('ProductUPC'),
                            product.get('ProductDescription'), product.get('CateID'),
                            product.get('SubCateID'), product.get('ManuID'), product.get('UnitID'),
                            product.get('ItemSize'), product.get('ItemWeight'),
                            product.get('UnitPrice'), product.get('UnitPriceA'),
                            product.get('UnitPriceB'), product.get('UnitPriceC'),
                            product.get('UnitCost'), product.get('QuantOnHand'),
                            product.get('QuantOnOrder'), product.get('ReorderLevel'),
                            product.get('ReorderQuant'), product.get('MSRPrice'),
                            product.get('MasterPackQty'), product.get('InnerPackQty'),
                            product.get('UnitQty'), product.get('UnitID2'), product.get('UnitQty2'),
                            product.get('UnitPrice2'), product.get('UnitID3'),
                            product.get('UnitQty3'), product.get('UnitPrice3'),
                            product.get('UnitID4'), product.get('UnitQty4'),
                            product.get('UnitPrice4'), product.get('LastReceived'),
                            product.get('LastSold'), product.get('ExpDate'),
                            product.get('Discontinued'), product.get('StLocationID'),
                            product.get('MinOrderQty'), product.get('MaxOrderQty'),
                            product.get('Taxable'), product.get('SPPromoted'),
                            product.get('ItemNotes'), product.get('WebDescription'),
                            product.get('ItemWebInfo'), product.get('WebAvailable'),
                            product.get('WebFeatured'), product.get('WebNew'),
                            product.get('WebPrice'), product.get('WebImage'),
                            product.get('Allergen1'), product.get('Allergen2'),
                            product.get('Allergen3'), product.get('Allergen4'),
                            product.get('Allergen5'), product.get('Allergen6'),
                            product.get('Allergen7'), product.get('Allergen8'),
                            product.get('Allergen9'), product.get('Allergen10'),
                            product.get('AllergenFreeFrom'), product.get('ItemImageLocal')
                        )

                        cursor.execute(insert_query, values)
                        conn.commit()
                        copied.append(barcode)

                except Exception as e:
                    failed.append({'barcode': barcode, 'error': str(e)})

            return {
                'success': len(copied) > 0,
                'copied': copied,
                'failed': failed,
                'copied_count': len(copied),
                'failed_count': len(failed)
            }

        except Exception as e:
            return {'success': False, 'error': f'Error copying products: {str(e)}'}

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
                       ShipContact, ShipCity, ShipState, ShipZipCode, ShipPhone_Number
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
        for product in products:
            barcode = product.get('barcode')
            if not barcode:
                continue  # Already added to unmatched_barcodes above

            matched = barcode_to_item.get(barcode)
            if not matched:
                unmatched_barcodes.append(f"Barcode '{barcode}' (Product: {product.get('name')})")
            else:
                matched_products.append({
                    'pick_list_product': product,
                    'item': matched
                })

        # If any products couldn't be matched, fail the conversion
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
                    0,  # SalesRepID
                    0,  # TermID
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

                    qty = product.get('amount', 1)
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

            # Get picklist products
            products = self.get_picklist_products(shipper_db, picklist_id)
            if not products:
                error_msg = "No products found in picklist"
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
