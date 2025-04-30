# tests/test_efficient_po_fetch.py
import os
import logging
from collections import defaultdict
from dotenv import load_dotenv, find_dotenv
from inventree.api import InvenTreeAPI
from inventree.part import Part
from inventree.company import SupplierPart
from inventree.purchase_order import PurchaseOrderLineItem, PurchaseOrder

# --- Configuration ---
# Define PO Status Map
PO_STATUS_MAP = {
    10: "Pending",
    20: "Placed",
    25: "On Hold",
    30: "Complete",
    40: "Cancelled",
    50: "Lost",
    60: "Returned",
}
RELEVANT_PO_STATUSES = [10, 20, 25]  # Pending, Placed, On Hold
EXAMPLE_PART_IDS = [1131, 1609] # Example Part IDs to check
CHUNK_SIZE = 100 # For chunking API calls if needed

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

# --- Utility: Chunk List ---
def _chunk_list(data: list, size: int):
    """Yield successive n-sized chunks from list."""
    for i in range(0, len(data), size):
        yield data[i : i + size]

# --- Main Test Logic ---
def test_efficient_po_fetch():
    """Tests the efficient PO fetching logic."""
    log.info("--- Starting Efficient PO Fetch Test ---")

    # --- Load Environment Variables ---
    log.info("Loading environment variables...")
    dotenv_path = find_dotenv()
    if not dotenv_path:
        log.error(".env file not found!")
        return
    loaded = load_dotenv(dotenv_path=dotenv_path, verbose=True)
    if not loaded:
        log.error("Failed to load .env file.")
        return

    inventree_url = os.getenv("INVENTREE_URL")
    inventree_token = os.getenv("INVENTREE_TOKEN")

    if not inventree_url or not inventree_token:
        log.error("INVENTREE_URL or INVENTREE_TOKEN not found in .env file.")
        return

    # --- Connect to API ---
    log.info(f"Connecting to InvenTree API at {inventree_url}...")
    try:
        api = InvenTreeAPI(inventree_url, token=inventree_token)
        log.info(f"Connected to InvenTree API version: {api.api_version}")
    except Exception as e:
        log.error(f"Failed to connect to InvenTree API: {e}", exc_info=True)
        return

    # --- Efficient Fetch Implementation ---
    part_po_data = defaultdict(list)
    part_ids_to_check = EXAMPLE_PART_IDS
    log.info(f"Target Part IDs for PO check: {part_ids_to_check}")

    # 1. Get SupplierPart PKs for target parts
    all_supplier_part_pks = []
    sp_pk_to_part_id = {}
    try:
        log.info(f"Fetching SupplierParts for {len(part_ids_to_check)} parts...")
        supplier_parts_list = SupplierPart.list(
            api, part__in=part_ids_to_check, fields=["pk", "part"]
        )
        if not supplier_parts_list:
            log.warning("No SupplierParts found for the target parts.")
        else:
            all_supplier_part_pks = [sp.pk for sp in supplier_parts_list]
            sp_pk_to_part_id = {sp.pk: sp._data.get("part") for sp in supplier_parts_list}
            log.info(f"Found {len(all_supplier_part_pks)} SupplierPart PKs: {all_supplier_part_pks}")
    except Exception as e:
        log.error(f"Error fetching supplier parts: {e}", exc_info=True)
        return # Cannot proceed without supplier parts

    # 2. Fetch Relevant PO Lines directly
    relevant_lines = []
    unique_po_pks = set()
    if all_supplier_part_pks:
        log.info("Fetching relevant PO Lines directly...")
        try:
            # Fetch lines in chunks based on supplier_part PKs
            for sp_pk_chunk in _chunk_list(all_supplier_part_pks, CHUNK_SIZE):
                 lines_chunk = PurchaseOrderLineItem.list(
                    api,
                    supplier_part__in=sp_pk_chunk,
                    order__status__in=RELEVANT_PO_STATUSES,
                    fields=["pk", "order", "part", "quantity", "supplier_part"],
                 )
                 relevant_lines.extend(lines_chunk)
                 for line in lines_chunk:
                     if line.order:
                         unique_po_pks.add(line.order)

            log.info(f"Fetched {len(relevant_lines)} relevant PO lines for {len(unique_po_pks)} unique POs.")

        except Exception as e:
            log.error(f"Error fetching PO Lines directly: {e}", exc_info=True)
            # Continue, but PO data might be incomplete

    # 3. Fetch PO Details for unique POs found
    po_details = {}
    if unique_po_pks:
        log.info(f"Fetching details for {len(unique_po_pks)} unique POs...")
        po_pks_list = list(unique_po_pks)
        try:
            for po_pk_chunk in _chunk_list(po_pks_list, CHUNK_SIZE):
                orders_chunk = PurchaseOrder.list(
                    api,
                    pk__in=po_pk_chunk,
                    fields=["pk", "reference", "status"]
                )
                for order in orders_chunk:
                    status_code = order._data.get("status")
                    po_details[order.pk] = {
                        "ref": order._data.get("reference", "No Ref"),
                        "status_label": PO_STATUS_MAP.get(status_code, f"Unknown ({status_code})"),
                    }
            log.info(f"Fetched details for {len(po_details)} POs.")
        except Exception as e:
            log.error(f"Error fetching PO details: {e}", exc_info=True)
            # Continue, but PO details might be missing

    # 4. Map data back to original Part IDs
    log.info("Mapping fetched data back to original Part IDs...")
    for line in relevant_lines:
        order_pk = line._data.get("order")
        po_detail = po_details.get(order_pk)
        if not po_detail:
            log.warning(f"Skipping PO Line {line.pk} as PO details for Order PK {order_pk} were not found.")
            continue

        supplier_part_pk = line._data.get("supplier_part")
        part_field_pk = line._data.get("part") # Fallback check

        original_part_id = None
        if supplier_part_pk and supplier_part_pk in sp_pk_to_part_id:
             original_part_id = sp_pk_to_part_id.get(supplier_part_pk)
        elif part_field_pk and part_field_pk in sp_pk_to_part_id:
             # Fallback: Check if the 'part' field actually contains a SupplierPart PK we know
             original_part_id = sp_pk_to_part_id.get(part_field_pk)
             if original_part_id:
                 log.warning(f"PO Line {line.pk}: Using 'part' field ({part_field_pk}) as SupplierPart PK due to null 'supplier_part'. Mapped to Part {original_part_id}.")

        if original_part_id:
            part_po_data[original_part_id].append(
                {
                    "quantity": float(line.quantity),
                    "po_ref": po_detail["ref"],
                    "po_status": po_detail["status_label"],
                    "line_pk": line.pk, # Added for debugging
                    "order_pk": order_pk, # Added for debugging
                }
            )
        else:
             log.warning(f"Could not map PO Line {line.pk} (SupplierPart PK: {supplier_part_pk}, Part Field PK: {part_field_pk}) back to an original Part ID.")


    # --- Print Results ---
    log.info("--- Test Results ---")
    if not part_po_data:
        log.info("No relevant purchase order lines found for the target parts.")
    else:
        for part_id, po_list in part_po_data.items():
            log.info(f"Part ID: {part_id}")
            if not po_list:
                log.info("  No relevant POs found.")
            else:
                for po_info in po_list:
                    log.info(f"  - PO Ref: {po_info['po_ref']} ({po_info['po_status']}), Qty: {po_info['quantity']} (Line PK: {po_info['line_pk']}, Order PK: {po_info['order_pk']})")

    log.info("--- Test Finished ---")


if __name__ == "__main__":
    test_efficient_po_fetch()