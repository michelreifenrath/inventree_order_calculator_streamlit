import os
import logging
from dotenv import load_dotenv
from inventree.api import InvenTreeAPI
from inventree.part import Part
from inventree.company import SupplierPart # Corrected import location
from inventree.order import PurchaseOrder, PurchaseOrderLineItem
from collections import defaultdict

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv() # Load environment variables from .env file

INVENTREE_URL = os.getenv("INVENTREE_URL")
INVENTREE_TOKEN = os.getenv("INVENTREE_TOKEN")

TARGET_PART_ID = 1087 # The specific Part ID we are investigating
EXPECTED_PO_REF = "PO-P-000287" # The PO we expect to find for this part

PO_STATUS_MAP = {10: "Pending", 20: "In Progress", 30: "Complete", 40: "Cancelled", 50: "Lost", 60: "Returned", 70: "On Hold"}

# --- API Connection ---
if not INVENTREE_URL or not INVENTREE_TOKEN:
    logging.error("INVENTREE_URL and INVENTREE_TOKEN must be set in the .env file.")
    exit(1)

try:
    api = InvenTreeAPI(INVENTREE_URL, token=INVENTREE_TOKEN)
    logging.info(f"Connected to InvenTree API at {INVENTREE_URL}")
except Exception as e:
    logging.error(f"Failed to connect to InvenTree API: {e}", exc_info=True)
    exit(1)

# --- Validation Logic ---
sp_pk_to_part_id = {}
relevant_po_details = {}
relevant_po_pks = []
part_po_line_data = defaultdict(list)

try:
    # 1. Fetch SupplierPart for the target Part ID
    logging.info(f"Fetching SupplierParts for Part ID: {TARGET_PART_ID}...")
    supplier_parts = SupplierPart.list(api, part=TARGET_PART_ID, fields=['pk', 'part'])
    if not supplier_parts:
        logging.warning(f"No SupplierParts found for Part ID {TARGET_PART_ID}. Cannot proceed.")
        exit()

    for sp in supplier_parts:
        sp_pk_to_part_id[sp.pk] = sp._data.get('part')
    logging.info(f"Found {len(supplier_parts)} SupplierPart(s). Map created: {sp_pk_to_part_id}")

    # 2. Fetch Relevant Purchase Orders (Pending/In Progress)
    logging.info("Fetching relevant Purchase Orders (Status: Pending or In Progress)...")
    relevant_statuses = [10, 20] # 10: Pending, 20: In Progress
    relevant_orders = PurchaseOrder.list(api, status__in=relevant_statuses, fields=['pk', 'reference', 'status'])

    if relevant_orders:
        for order in relevant_orders:
            status_code = order._data.get('status')
            order_pk = order.pk
            relevant_po_pks.append(order_pk)
            relevant_po_details[order_pk] = {
                'ref': order._data.get('reference', 'No Ref'),
                'status_label': PO_STATUS_MAP.get(status_code, f"Unknown ({status_code})")
            }
        logging.info(f"Fetched details for {len(relevant_po_details)} relevant POs. PKs: {relevant_po_pks}")
        # Check if the expected PO is among the relevant ones
        found_expected_po = any(details['ref'] == EXPECTED_PO_REF for details in relevant_po_details.values())
        logging.info(f"Expected PO ({EXPECTED_PO_REF}) found among relevant POs: {found_expected_po}")
    else:
        logging.warning("No relevant Purchase Orders (Pending/In Progress) found.")
        exit() # Cannot proceed without relevant POs

    # 2b. Find the PK for the specific PO we are interested in
    target_po_pk = None
    for pk, details in relevant_po_details.items():
        if details['ref'] == EXPECTED_PO_REF:
            target_po_pk = pk
            logging.info(f"Found Target PO PK: {target_po_pk} for reference {EXPECTED_PO_REF}")
            break

    if not target_po_pk:
        logging.error(f"Could not find the PK for the expected PO ({EXPECTED_PO_REF}) even though it was listed as relevant. Exiting.")
        exit()

    # 3. Fetch PO Lines specifically for the target PO PK
    logging.info(f"Fetching PO Lines specifically for Target PO PK: {target_po_pk} ({EXPECTED_PO_REF})...")
    all_po_lines = []
    try:
        # No chunking needed as we fetch for a single PO
        # Add 'part' field to the requested fields for extra debugging info
        all_po_lines = PurchaseOrderLineItem.list(api, order=target_po_pk, fields=['pk', 'order', 'quantity', 'supplier_part', 'part'])
        if not all_po_lines:
            logging.warning(f"No PO lines found for Target PO PK {target_po_pk}.")
    except Exception as line_fetch_err:
        logging.error(f"ERROR fetching PO lines for Target PO PK {target_po_pk}: {line_fetch_err}", exc_info=True)
    logging.info(f"Fetched {len(all_po_lines)} PO lines for the target PO.")

    # 4. Process Lines for the Target PO and Link to Parts
    logging.info(f"Processing {len(all_po_lines)} fetched PO lines for target PO {target_po_pk}...")
    processed_count = 0
    found_target_link = False
    if all_po_lines:
        for line in all_po_lines:
            line_pk = line.pk
            supplier_part_pk = line._data.get('supplier_part')
            order_id = line._data.get('order')
            part_id = sp_pk_to_part_id.get(supplier_part_pk)
            po_info = relevant_po_details.get(order_id)

            # Log details for every line processed on the target PO
            line_part_field = line._data.get('part') # Get the 'part' field if available
            logging.info(f"  Line PK: {line_pk}, Order PK: {order_id}, SP PK: {supplier_part_pk}, Mapped Part ID: {part_id}, Line Part Field: {line_part_field}, PO Info Found: {po_info is not None}")

            if part_id and po_info:
                # Check if this line corresponds to our target part and expected PO
                if part_id == TARGET_PART_ID and po_info['ref'] == EXPECTED_PO_REF:
                    logging.info(f"*** SUCCESS: Found PO Line for Target Part {TARGET_PART_ID} on Expected PO {EXPECTED_PO_REF}! ***")
                    logging.info(f"    Line PK: {line_pk}, Quantity: {line.quantity}, Status: {po_info['status_label']}")
                    found_target_link = True

                # Store data (optional for validation, but good practice)
                part_po_line_data[part_id].append({
                    'quantity': line.quantity,
                    'po_ref': po_info['ref'],
                    'po_status': po_info['status_label']
                })
                processed_count += 1
            elif not part_id and supplier_part_pk in sp_pk_to_part_id:
                 logging.warning(f"Could not map SupplierPart PK {supplier_part_pk} back to a Part ID for PO Line {line_pk} (Order: {order_id}).")
            elif not po_info:
                 # This case shouldn't happen now as we only fetch lines for the target PO
                 logging.error(f"Logic Error: Found line {line_pk} for Order ID {order_id} but no details were fetched for this PO.")

        logging.info(f"Finished processing PO lines. Total linked: {processed_count}")
        if not found_target_link:
            logging.warning(f"*** FAILED: Did not find a PO Line linking Target Part {TARGET_PART_ID} to Expected PO {EXPECTED_PO_REF} via its SupplierPart(s) {list(sp_pk_to_part_id.keys())} ***")

    else:
        # Adjusted warning message
        logging.warning(f"No PO lines were fetched for the target PO ({target_po_pk}).")

except Exception as e:
    logging.error(f"An error occurred during the validation process: {e}", exc_info=True)

logging.info("Validation script finished.")