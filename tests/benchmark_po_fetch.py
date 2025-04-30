# tests/benchmark_po_fetch.py
import os
import logging
import timeit
from collections import defaultdict
from typing import List, Dict
from dotenv import load_dotenv, find_dotenv
from inventree.api import InvenTreeAPI
from inventree.part import Part
from inventree.company import SupplierPart
from inventree.purchase_order import PurchaseOrderLineItem, PurchaseOrder

# --- Configuration ---
# Define PO Status Map
PO_STATUS_MAP = {
    10: "Pending", 20: "Placed", 25: "On Hold", 30: "Complete",
    40: "Cancelled", 50: "Lost", 60: "Returned",
}
RELEVANT_PO_STATUSES = [10, 20, 25]  # Pending, Placed, On Hold
EXAMPLE_PART_IDS = [1131, 1609] # Example Part IDs to check
CHUNK_SIZE = 100 # For chunking API calls
NUMBER_OF_RUNS = 3 # How many times to run each method for timing

# --- Logging Setup ---
# Reduce log level for benchmark to avoid flooding console
logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)
# Keep inventree library logs quiet too
logging.getLogger("inventree").setLevel(logging.WARNING)

# --- Utility: Chunk List ---
def _chunk_list(data: list, size: int):
    """Yield successive n-sized chunks from list."""
    for i in range(0, len(data), size):
        yield data[i : i + size]

# --- Original PO Fetch Logic ---
def _fetch_purchase_order_data_original(
    api: InvenTreeAPI, part_ids_to_check: List[int]
) -> Dict[int, List[Dict[str, any]]]:
    """Original method: Fetches all relevant PO headers first."""
    log.info("[Original] Starting PO Fetch...")
    part_po_data = defaultdict(list)
    # Assume IMPORTS_AVAILABLE is True for benchmark
    if not part_ids_to_check:
        return part_po_data

    all_supplier_part_pks = []
    sp_pk_to_part_id = {}
    relevant_po_details = {}
    relevant_po_pks = []

    # Step 1: Fetch SupplierParts
    try:
        log.debug(f"[Original] Fetching SupplierParts for {len(part_ids_to_check)} parts...")
        supplier_parts_list = SupplierPart.list(
            api, part__in=part_ids_to_check, fields=["pk", "part"]
        )
        all_supplier_part_pks = [sp.pk for sp in supplier_parts_list]
        sp_pk_to_part_id = {sp.pk: sp._data.get("part") for sp in supplier_parts_list}
        log.debug(f"[Original] Fetched {len(supplier_parts_list)} supplier parts.")
    except Exception as e:
        log.error(f"[Original] Error fetching supplier parts: {e}", exc_info=True)
        return part_po_data

    # Step 2: Fetch ALL Relevant PO Headers
    try:
        log.debug("[Original] Fetching ALL relevant Purchase Order headers...")
        all_orders = PurchaseOrder.list(api, fields=["pk", "reference", "status"])
        for order in all_orders:
            status_code = order._data.get("status")
            if status_code in RELEVANT_PO_STATUSES:
                order_pk = order.pk
                relevant_po_pks.append(order_pk)
                relevant_po_details[order_pk] = {
                    "ref": order._data.get("reference", "No Ref"),
                    "status_label": PO_STATUS_MAP.get(status_code, f"Unknown ({status_code})"),
                }
        log.debug(f"[Original] Found {len(relevant_po_pks)} relevant POs headers.")
    except Exception as e:
        log.error(f"[Original] Error fetching PO headers: {e}", exc_info=True)
        return part_po_data

    # Step 3: Fetch PO Lines using order__in filter
    all_po_lines = []
    if relevant_po_pks:
        log.debug(f"[Original] Fetching PO Lines for {len(relevant_po_pks)} relevant POs...")
        try:
            for po_pk_chunk in _chunk_list(relevant_po_pks, CHUNK_SIZE):
                lines_chunk = PurchaseOrderLineItem.list(
                    api,
                    order__in=po_pk_chunk,
                    fields=["pk", "order", "part", "quantity", "supplier_part"],
                )
                all_po_lines.extend(lines_chunk)
            log.debug(f"[Original] Fetched {len(all_po_lines)} PO lines.")
        except Exception as e:
            log.error(f"[Original] Error fetching PO Lines: {e}", exc_info=True)

    # Step 4: Map PO Lines back
    for line in all_po_lines:
        order_pk = line._data.get("order")
        po_detail = relevant_po_details.get(order_pk)
        if not po_detail: continue
        supplier_part_pk = line._data.get("supplier_part")
        part_field_pk = line._data.get("part")
        original_part_id = None
        if supplier_part_pk and supplier_part_pk in sp_pk_to_part_id:
             original_part_id = sp_pk_to_part_id.get(supplier_part_pk)
        elif part_field_pk and part_field_pk in sp_pk_to_part_id:
             original_part_id = sp_pk_to_part_id.get(part_field_pk)
             # Suppress warning in benchmark
             # if original_part_id: log.warning(...)
        if original_part_id:
            part_po_data[original_part_id].append({
                "quantity": float(line.quantity),
                "po_ref": po_detail["ref"],
                "po_status": po_detail["status_label"],
            })
    log.info("[Original] Finished PO Fetch.")
    return part_po_data

# --- Efficient PO Fetch Logic ---
def _fetch_purchase_order_data_efficient(
    api: InvenTreeAPI, part_ids_to_check: List[int]
) -> Dict[int, List[Dict[str, any]]]:
    """Efficient method: Filters PO lines directly."""
    log.info("[Efficient] Starting PO Fetch...")
    part_po_data = defaultdict(list)
    # Assume IMPORTS_AVAILABLE is True for benchmark
    if not part_ids_to_check:
        return part_po_data

    # 1. Get SupplierPart PKs
    all_supplier_part_pks = []
    sp_pk_to_part_id = {}
    try:
        log.debug(f"[Efficient] Fetching SupplierParts for {len(part_ids_to_check)} parts...")
        supplier_parts_list = SupplierPart.list(
            api, part__in=part_ids_to_check, fields=["pk", "part"]
        )
        if not supplier_parts_list:
            log.debug("[Efficient] No SupplierParts found.")
        else:
            all_supplier_part_pks = [sp.pk for sp in supplier_parts_list]
            sp_pk_to_part_id = {sp.pk: sp._data.get("part") for sp in supplier_parts_list}
            log.debug(f"[Efficient] Found {len(all_supplier_part_pks)} SupplierPart PKs.")
    except Exception as e:
        log.error(f"[Efficient] Error fetching supplier parts: {e}", exc_info=True)
        return part_po_data

    # 2. Fetch Relevant PO Lines directly
    relevant_lines = []
    unique_po_pks = set()
    if all_supplier_part_pks:
        log.debug("[Efficient] Fetching relevant PO Lines directly...")
        try:
            for sp_pk_chunk in _chunk_list(all_supplier_part_pks, CHUNK_SIZE):
                 lines_chunk = PurchaseOrderLineItem.list(
                    api,
                    supplier_part__in=sp_pk_chunk,
                    order__status__in=RELEVANT_PO_STATUSES,
                    fields=["pk", "order", "part", "quantity", "supplier_part"],
                 )
                 relevant_lines.extend(lines_chunk)
                 for line in lines_chunk:
                     if line.order: unique_po_pks.add(line.order)
            log.debug(f"[Efficient] Fetched {len(relevant_lines)} relevant PO lines for {len(unique_po_pks)} unique POs.")
        except Exception as e:
            log.error(f"[Efficient] Error fetching PO Lines directly: {e}", exc_info=True)

    # 3. Fetch PO Details for unique POs found
    po_details = {}
    if unique_po_pks:
        log.debug(f"[Efficient] Fetching details for {len(unique_po_pks)} unique POs...")
        po_pks_list = list(unique_po_pks)
        try:
            for po_pk_chunk in _chunk_list(po_pks_list, CHUNK_SIZE):
                orders_chunk = PurchaseOrder.list(
                    api, pk__in=po_pk_chunk, fields=["pk", "reference", "status"]
                )
                for order in orders_chunk:
                    status_code = order._data.get("status")
                    po_details[order.pk] = {
                        "ref": order._data.get("reference", "No Ref"),
                        "status_label": PO_STATUS_MAP.get(status_code, f"Unknown ({status_code})"),
                    }
            log.debug(f"[Efficient] Fetched details for {len(po_details)} POs.")
        except Exception as e:
            log.error(f"[Efficient] Error fetching PO details: {e}", exc_info=True)

    # 4. Map data back
    for line in relevant_lines:
        order_pk = line._data.get("order")
        po_detail = po_details.get(order_pk)
        if not po_detail: continue
        supplier_part_pk = line._data.get("supplier_part")
        part_field_pk = line._data.get("part")
        original_part_id = None
        if supplier_part_pk and supplier_part_pk in sp_pk_to_part_id:
             original_part_id = sp_pk_to_part_id.get(supplier_part_pk)
        elif part_field_pk and part_field_pk in sp_pk_to_part_id:
             original_part_id = sp_pk_to_part_id.get(part_field_pk)
             # Suppress warning in benchmark
             # if original_part_id: log.warning(...)
        if original_part_id:
            part_po_data[original_part_id].append({
                "quantity": float(line.quantity),
                "po_ref": po_detail["ref"],
                "po_status": po_detail["status_label"],
            })
    log.info("[Efficient] Finished PO Fetch.")
    return part_po_data

# --- Benchmark Execution ---
def run_benchmark():
    """Loads env, connects to API, and times the two fetch methods."""
    print("--- Starting PO Fetch Benchmark ---")

    # Load Environment Variables
    print("Loading environment variables...")
    dotenv_path = find_dotenv()
    if not dotenv_path:
        print("ERROR: .env file not found!")
        return
    load_dotenv(dotenv_path=dotenv_path)
    inventree_url = os.getenv("INVENTREE_URL")
    inventree_token = os.getenv("INVENTREE_TOKEN")
    if not inventree_url or not inventree_token:
        print("ERROR: INVENTREE_URL or INVENTREE_TOKEN not found in .env file.")
        return

    # Connect to API
    print(f"Connecting to InvenTree API at {inventree_url}...")
    try:
        api = InvenTreeAPI(inventree_url, token=inventree_token)
        print(f"Connected to InvenTree API version: {api.api_version}")
    except Exception as e:
        print(f"ERROR: Failed to connect to InvenTree API: {e}")
        return

    # --- Time Original Method ---
    print(f"\nTiming Original Method ({NUMBER_OF_RUNS} runs)...")
    original_timer = timeit.Timer(
        lambda: _fetch_purchase_order_data_original(api, EXAMPLE_PART_IDS)
    )
    try:
        original_times = original_timer.repeat(repeat=NUMBER_OF_RUNS, number=1)
        original_avg = sum(original_times) / NUMBER_OF_RUNS
        print(f"Original Method Average Time: {original_avg:.4f} seconds")
    except Exception as e:
        print(f"ERROR during Original Method timing: {e}")
        original_avg = float('inf') # Indicate failure

    # --- Time Efficient Method ---
    print(f"\nTiming Efficient Method ({NUMBER_OF_RUNS} runs)...")
    efficient_timer = timeit.Timer(
        lambda: _fetch_purchase_order_data_efficient(api, EXAMPLE_PART_IDS)
    )
    try:
        efficient_times = efficient_timer.repeat(repeat=NUMBER_OF_RUNS, number=1)
        efficient_avg = sum(efficient_times) / NUMBER_OF_RUNS
        print(f"Efficient Method Average Time: {efficient_avg:.4f} seconds")
    except Exception as e:
        print(f"ERROR during Efficient Method timing: {e}")
        efficient_avg = float('inf') # Indicate failure

    # --- Compare Results ---
    print("\n--- Benchmark Summary ---")
    print(f"Original Average:  {original_avg:.4f} seconds")
    print(f"Efficient Average: {efficient_avg:.4f} seconds")
    if efficient_avg < original_avg:
        diff = original_avg - efficient_avg
        percent_faster = (diff / original_avg) * 100 if original_avg > 0 else 0
        print(f"Efficient method was {diff:.4f} seconds faster ({percent_faster:.2f}% improvement).")
    elif original_avg < efficient_avg:
        diff = efficient_avg - original_avg
        percent_slower = (diff / efficient_avg) * 100 if efficient_avg > 0 else 0
        print(f"Efficient method was {diff:.4f} seconds slower ({percent_slower:.2f}% slower).")
    else:
        print("Both methods took approximately the same time.")

    print("\n--- Benchmark Finished ---")

if __name__ == "__main__":
    run_benchmark()