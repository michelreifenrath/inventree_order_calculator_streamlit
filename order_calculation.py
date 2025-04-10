import logging
from collections import defaultdict
from typing import Optional, Callable, Dict, List, Set
from inventree.api import InvenTreeAPI

# Import necessary classes conditionally
try:
    from inventree.company import SupplierPart
    from inventree.purchase_order import PurchaseOrderLineItem, PurchaseOrder

    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False
    logging.warning(
        "Could not import SupplierPart/PurchaseOrder related classes. PO checks will be skipped."
    )

from inventree_api_helpers import get_final_part_data, _chunk_list
from bom_calculation import get_recursive_bom

# Define PO Status Map (copied from original logic)
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


def _fetch_purchase_order_data(
    api: InvenTreeAPI, part_ids_to_check: List[int]
) -> Dict[int, List[Dict[str, any]]]:
    """Fetches relevant purchase order data for the given part IDs."""
    part_po_data = defaultdict(list)
    if not IMPORTS_AVAILABLE or not part_ids_to_check:
        return part_po_data

    CHUNK_SIZE = 100
    all_supplier_part_pks = []
    sp_pk_to_part_id = {}
    relevant_po_details = {}
    relevant_po_pks = []

    # Step 1: Fetch SupplierParts for parts needing order
    try:
        logging.info(
            f"PO Fetch: Fetching SupplierParts for {len(part_ids_to_check)} parts..."
        )
        supplier_parts_list = SupplierPart.list(
            api, part__in=part_ids_to_check, fields=["pk", "part"]
        )
        all_supplier_part_pks = [sp.pk for sp in supplier_parts_list]
        sp_pk_to_part_id = {sp.pk: sp._data.get("part") for sp in supplier_parts_list}
        logging.info(f"Fetched {len(supplier_parts_list)} supplier parts.")
    except Exception as e:
        logging.error(f"Error fetching supplier parts for POs: {e}", exc_info=True)
        return part_po_data # Return empty if supplier parts fail

    # Step 2: Fetch Relevant Purchase Orders
    try:
        logging.info("PO Fetch: Fetching relevant Purchase Orders...")
        # Fetch all POs and filter locally due to potential API filter issues
        all_orders = PurchaseOrder.list(api, fields=["pk", "reference", "status"])
        for order in all_orders:
            status_code = order._data.get("status")
            if status_code in RELEVANT_PO_STATUSES:
                order_pk = order.pk
                relevant_po_pks.append(order_pk)
                relevant_po_details[order_pk] = {
                    "ref": order._data.get("reference", "No Ref"),
                    "status_label": PO_STATUS_MAP.get(
                        status_code, f"Unknown ({status_code})"
                    ),
                }
        logging.info(f"Found {len(relevant_po_pks)} relevant POs.")
    except Exception as e:
        logging.error(f"Error fetching relevant Purchase Orders: {e}", exc_info=True)
        return part_po_data # Return empty if POs fail

    # Step 3: Fetch PO Lines using order__in filter
    all_po_lines = []
    if relevant_po_pks:
        logging.info(
            f"PO Fetch: Fetching PO Lines for {len(relevant_po_pks)} relevant POs..."
        )
        try:
            for po_pk_chunk in _chunk_list(relevant_po_pks, CHUNK_SIZE):
                lines_chunk = PurchaseOrderLineItem.list(
                    api,
                    order__in=po_pk_chunk,
                    fields=["pk", "order", "part", "quantity", "supplier_part"],
                )
                all_po_lines.extend(lines_chunk)
            logging.info(f"Fetched {len(all_po_lines)} PO lines.")
        except Exception as e:
            logging.error(f"Error fetching PO Lines: {e}", exc_info=True)
            # Continue without PO line info if fetching fails

    # Step 4: Map PO Lines back to original Part IDs
    for line in all_po_lines:
        order_pk = line._data.get("order")
        po_detail = relevant_po_details.get(order_pk)
        if not po_detail:
            continue

        # Handle potential anomaly where supplier_part is null but part holds the SupplierPart PK
        supplier_part_pk = line._data.get("supplier_part")
        part_field_pk = line._data.get("part") # This might hold the SupplierPart PK

        original_part_id = None
        if supplier_part_pk and supplier_part_pk in sp_pk_to_part_id:
             original_part_id = sp_pk_to_part_id.get(supplier_part_pk)
        elif part_field_pk and part_field_pk in sp_pk_to_part_id:
             # Fallback: Check if the 'part' field actually contains a SupplierPart PK we know
             original_part_id = sp_pk_to_part_id.get(part_field_pk)
             if original_part_id:
                 logging.warning(f"PO Line {line.pk}: Using 'part' field ({part_field_pk}) as SupplierPart PK due to null 'supplier_part'. Mapped to Part {original_part_id}.")

        if original_part_id:
            part_po_data[original_part_id].append(
                {
                    "quantity": float(line.quantity),
                    "po_ref": po_detail["ref"],
                    "po_status": po_detail["status_label"],
                }
            )
        # else: log if line couldn't be mapped?

    return part_po_data


def calculate_required_parts(
    api: InvenTreeAPI,
    target_assemblies: Dict[int, float],
    exclude_supplier_name: Optional[str] = None,
    exclude_manufacturer_name: Optional[str] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> List[Dict[str, any]]:
    """
    Calculates the list of parts to order based on target assemblies,
    with options to exclude by supplier or manufacturer.

    Args:
        api (InvenTreeAPI): The API connection.
        target_assemblies (dict[int, float]): Mapping of assembly part IDs to quantities.
        exclude_supplier_name (Optional[str]): Supplier name to exclude.
        exclude_manufacturer_name (Optional[str]): Manufacturer name to exclude.
        progress_callback (Optional[Callable]): Progress update callback.

    Returns:
        List[Dict[str, any]]: List of parts to order with details including pk, name,
                              total_required, available_stock, to_order,
                              used_in_assemblies, purchase_orders.
    """
    if not api:
        logging.error(
            "Cannot calculate parts: InvenTree API connection is not available."
        )
        return []
    if not target_assemblies:
        logging.info("No target assemblies provided.")
        return []

    logging.info(f"Calculating required components for targets: {target_assemblies}")
    required_base_components: defaultdict[int, defaultdict[int, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    template_only_flags: defaultdict[int, bool] = defaultdict(bool)
    all_encountered_part_ids: Set[int] = set()

    root_assembly_ids = tuple(target_assemblies.keys())
    # Fetch root assembly names early for progress callback
    root_assembly_data = get_final_part_data(api, root_assembly_ids)

    # --- Recursive BOM Calculation ---
    num_targets = len(target_assemblies)
    for index, (part_id, quantity) in enumerate(target_assemblies.items()):
        if progress_callback and num_targets > 0:
            current_progress = 10 + int(((index + 1) / num_targets) * 30)
            part_name = root_assembly_data.get(part_id, {}).get("name", f"ID {part_id}")
            progress_text = (
                f"Calculating BOM for '{part_name}' ({index + 1}/{num_targets})"
            )
            progress_callback(current_progress, progress_text)
        try:
            get_recursive_bom(
                api,
                int(part_id),
                float(quantity),
                required_base_components,
                int(part_id),
                template_only_flags,
                all_encountered_part_ids,
            )
        except Exception as e:
            logging.error(f"Error processing assembly {part_id}: {e}", exc_info=True)
            continue

    # --- Consolidate Base Components ---
    total_required_quantities = defaultdict(float)
    for components in required_base_components.values():
        for part_id, qty in components.items():
            total_required_quantities[part_id] += qty

    if not total_required_quantities:
        logging.info("No base components found after BOM processing. Nothing to order.")
        return []

    # --- Fetch Details for All Encountered Parts ---
    if progress_callback:
        progress_callback(40, "Fetching details for all BOM parts...")
    all_encountered_part_ids.update(root_assembly_ids)
    final_part_data = get_final_part_data(api, tuple(all_encountered_part_ids))

    # --- Calculate Stock, Order Need, and Collect Assembly Usage ---
    if progress_callback:
        progress_callback(60, "Calculating stock and order amounts...")
    parts_to_order_details = {} # Store final details here {part_id: {details}}
    part_available_stock_map = {} # Store calculated available stock

    for part_id, total_required in total_required_quantities.items():
        part_data = final_part_data.get(part_id)
        if not part_data:
            in_stock, is_template, variant_stock = 0.0, False, 0.0
            part_name = "Unknown"
        else:
            in_stock = part_data.get("in_stock", 0.0)
            is_template = part_data.get("is_template", False)
            variant_stock = part_data.get("variant_stock", 0.0)
            part_name = part_data.get("name", "Unknown")

        template_only = template_only_flags.get(part_id, False)
        if template_only:
            total_available_stock = in_stock
        elif is_template:
            total_available_stock = in_stock + variant_stock
        else:
            total_available_stock = in_stock

        part_available_stock_map[part_id] = total_available_stock # Store for later use
        global_to_order = total_required - total_available_stock
        order_qty = round(global_to_order, 3) if global_to_order > 0.001 else 0.0

        if order_qty > 0:
             parts_to_order_details[part_id] = {
                 "pk": part_id, # Use part_id as pk
                 "name": part_name,
                 "total_required": round(total_required, 3),
                 "available_stock": round(total_available_stock, 3),
                 "to_order": order_qty,
                 "used_in_assemblies": set(), # Initialize as set
                 "purchase_orders": [], # Initialize as list
                 # Add manufacturer/supplier if needed later
                 "manufacturer": part_data.get("manufacturer_name", "") if part_data else "",
                 "supplier": part_data.get("supplier_name", "") if part_data else "",
             }

    # --- Collect Root Assembly Names for Needed Parts ---
    for root_id, base_components in required_base_components.items():
        root_assembly_name = final_part_data.get(root_id, {}).get(
            "name", f"Unknown Assembly (ID: {root_id})"
        )
        for part_id in base_components.keys():
            if part_id in parts_to_order_details: # Check if this part needs ordering
                parts_to_order_details[part_id]["used_in_assemblies"].add(root_assembly_name)

    # --- Fetch Purchase Order Data for Parts Needing Order ---
    if progress_callback:
        progress_callback(80, "Fetching purchase order data...")
    part_ids_needing_order = list(parts_to_order_details.keys())
    part_po_data = _fetch_purchase_order_data(api, part_ids_needing_order)

    # --- Build Final List ---
    if progress_callback:
        progress_callback(95, "Finalizing results...")
    final_list = []
    for part_id, details in parts_to_order_details.items():
        # Format used_in_assemblies
        details["used_in_assemblies"] = ", ".join(sorted(list(details["used_in_assemblies"])))
        # Add PO data
        details["purchase_orders"] = part_po_data.get(part_id, [])
        final_list.append(details)

    # Sort the final list (e.g., by name)
    final_list.sort(key=lambda x: x["name"])

    if progress_callback:
        progress_callback(100, "Berechnung abgeschlossen.")
    logging.info(f"Calculation complete. Found {len(final_list)} parts to order.")
    return final_list
