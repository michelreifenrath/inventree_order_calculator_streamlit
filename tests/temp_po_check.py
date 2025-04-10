import os
import logging
from dotenv import load_dotenv
from inventree.api import InvenTreeAPI

# Need to handle potential import errors gracefully if library structure changes
try:
    from inventree.part import Part
    from inventree.company import SupplierPart
    from inventree.purchase_order import PurchaseOrderLineItem, PurchaseOrder

    IMPORTS_OK = True
except ImportError as ie:
    IMPORTS_OK = False
    print(
        f"Import Error: {ie}. Please ensure the inventree library is installed correctly."
    )

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

if not IMPORTS_OK:
    exit(1)

# Load environment variables
load_dotenv()
INVENTREE_API_URL = os.getenv("INVENTREE_URL")
INVENTREE_API_TOKEN = os.getenv("INVENTREE_TOKEN")

if not INVENTREE_API_URL or not INVENTREE_API_TOKEN:
    log.error(
        "Error: INVENTREE_URL or INVENTREE_TOKEN not found in environment variables or .env file."
    )
    exit(1)

PART_ID_TO_CHECK = 1087
EXPECTED_PO_REF = "PO-P-000287"  # User provided reference

log.info(f"Attempting to connect to InvenTree API at {INVENTREE_API_URL}")
try:
    # Add timeout to prevent hangs
    api = InvenTreeAPI(INVENTREE_API_URL, token=INVENTREE_API_TOKEN, request_timeout=30)
    # Verify connection by checking the api_version attribute
    api_version_num = api.api_version  # Access as attribute
    if not api_version_num:
        raise ConnectionError(
            "API connection test failed - could not retrieve API version."
        )
    log.info(f"Successfully connected to InvenTree API (Version: {api_version_num}).")
except Exception as e:
    log.error(f"Failed to connect to API: {e}")
    exit(1)

try:
    log.info(f"--- Checking Part ID: {PART_ID_TO_CHECK} ---")

    # 1. Find SupplierParts for the Part ID
    log.info(f"Step 1: Finding SupplierParts for Part ID {PART_ID_TO_CHECK}...")
    supplier_parts = SupplierPart.list(api, part=PART_ID_TO_CHECK)

    if not supplier_parts:
        log.warning(
            f"No SupplierPart records found for Part ID {PART_ID_TO_CHECK}. Link chain broken here."
        )
        exit(0)

    log.info(
        f"Found {len(supplier_parts)} SupplierPart record(s): {[sp.pk for sp in supplier_parts]}"
    )
    supplier_part_pks = [sp.pk for sp in supplier_parts]

    # 2. Find PurchaseOrderLineItems linked to these SupplierParts
    log.info(
        f"Step 2: Finding PurchaseOrderLineItems for SupplierPart PKs: {supplier_part_pks}..."
    )
    # Fetch relevant fields only
    po_lines = PurchaseOrderLineItem.list(
        api,
        supplier_part__in=supplier_part_pks,
        fields=["pk", "order", "quantity", "supplier_part"],
    )

    if not po_lines:
        log.warning(
            f"No PurchaseOrderLineItems found linked to SupplierPart PKs {supplier_part_pks}. Link chain broken here."
        )
        exit(0)

    log.info(f"Found {len(po_lines)} PurchaseOrderLineItem record(s).")
    order_ids = set()
    line_details = []
    for line in po_lines:
        order_id = line._data.get("order")
        sp_pk = line._data.get("supplier_part")
        qty = line.quantity
        line_pk = line.pk
        if order_id:
            order_ids.add(order_id)
            line_details.append(
                {
                    "line_pk": line_pk,
                    "order_pk": order_id,
                    "supplier_part_pk": sp_pk,
                    "quantity": qty,
                }
            )
    log.info(f"Line details: {line_details}")
    log.info(f"Unique Purchase Order PKs found linked to lines: {list(order_ids)}")

    # 3. Find PurchaseOrders and check their status
    if not order_ids:
        log.warning("No Purchase Order PKs found from the lines. Cannot proceed.")
        exit(0)

    log.info(f"Step 3: Fetching details for Purchase Order PKs: {list(order_ids)}...")
    # Fetch relevant fields only
    purchase_orders = PurchaseOrder.list(
        api, pk__in=list(order_ids), fields=["pk", "reference", "status"]
    )

    if not purchase_orders:
        log.warning(
            f"Could not fetch details for any Purchase Order PKs: {list(order_ids)}."
        )
        exit(0)

    log.info(
        f"Found {len(purchase_orders)} Purchase Order record(s). Checking status..."
    )
    found_expected_po = False
    relevant_po_found = False
    PO_STATUS_MAP = {
        10: "Pending",
        20: "In Progress",
        30: "Complete",
        40: "Cancelled",
        50: "Lost",
        60: "Returned",
        70: "On Hold",
    }  # From inventree_logic.py

    for po in purchase_orders:
        po_pk = po.pk
        po_ref = po._data.get("reference", "N/A")
        po_status = po._data.get("status")
        po_status_label = PO_STATUS_MAP.get(
            po_status, f"Unknown ({po_status})"
        )  # Use map for consistency
        log.info(
            f"  - PO PK: {po_pk}, Reference: {po_ref}, Status Code: {po_status}, Status Label: {po_status_label}"
        )

        if po_ref == EXPECTED_PO_REF:
            found_expected_po = True
            log.info(f"    -> Found expected PO: {EXPECTED_PO_REF} (PK: {po_pk})")
            if po_status in [10, 20]:  # Check against relevant statuses used by the app
                relevant_po_found = True
                log.info(
                    f"    -> Status ({po_status} - {po_status_label}) is relevant (Pending or In Progress)."
                )
            else:
                log.warning(
                    f"    -> Status ({po_status} - {po_status_label}) is NOT relevant (Expected 10 or 20)."
                )

    if not found_expected_po:
        log.warning(
            f"Expected Purchase Order '{EXPECTED_PO_REF}' was NOT found among the linked orders."
        )
    elif not relevant_po_found:
        log.warning(
            f"Expected Purchase Order '{EXPECTED_PO_REF}' was found, but its status is not Pending (10) or In Progress (20)."
        )
    else:
        log.info(
            f"Success: Found expected PO '{EXPECTED_PO_REF}' with a relevant status (Pending or In Progress). The data link seems OK."
        )


except Exception as e:
    log.error(f"An error occurred during the check: {e}", exc_info=True)

log.info("--- Check complete ---")
