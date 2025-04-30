import logging
from collections import defaultdict
from typing import Optional, Callable, Dict, List, Set
from inventree.api import InvenTreeAPI
from inventree.part import Part # Added import

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

from src.inventree_api_helpers import get_final_part_data, _chunk_list # Absolute import
from src.bom_calculation import get_recursive_bom # Absolute import

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
    exclude_haip_calculation: bool = False, # New flag for HAIP calculation exclusion
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> tuple[List[Dict[str, any]], List[Dict[str, any]], Dict[int, bool]]:
    """
    Calculates the list of parts to order based on target assemblies,
    with options to exclude by supplier or manufacturer.

    Args:
        api (InvenTreeAPI): The API connection.
        target_assemblies (dict[int, float]): Mapping of assembly part IDs to quantities.
        exclude_supplier_name (Optional[str]): Supplier name to exclude (for final list filtering).
        exclude_manufacturer_name (Optional[str]): Manufacturer name to exclude (for final list filtering).
        exclude_haip_calculation (bool): If True, HAIP parts are excluded during BOM recursion.
        progress_callback (Optional[Callable]): Progress update callback.

    Returns:
        tuple[List[Dict[str, any]], List[Dict[str, any]], Dict[int, bool]]:
            - List of parts to order with details.
            - List of sub-assemblies required.
            - Dictionary mapping part IDs to their BOM-level consumable status.
    """
    if not api:
        logging.error(
            "Cannot calculate parts: InvenTree API connection is not available."
        )
        return [], [], {} # Return empty dict for consumable status
    if not target_assemblies:
        logging.info("No target assemblies provided.")
        return [], [], {} # Return empty dict for consumable status

    logging.info(f"Calculating required components for targets: {target_assemblies}")
    # Pass 1: Gross calculation to identify all parts
    gross_required_base_components: defaultdict[int, defaultdict[int, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    # Dictionary to track required sub-assemblies (populated in Pass 1)
    required_sub_assemblies: defaultdict[int, defaultdict[int, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    template_only_flags: defaultdict[int, bool] = defaultdict(bool)
    all_encountered_part_ids: Set[int] = set()
    # Set to track which parts are assemblies
    assembly_part_ids: Set[int] = set()
    # Dictionary to track BOM-level consumable status
    bom_consumable_status: Dict[int, bool] = {}

    root_assembly_ids = tuple(target_assemblies.keys())
    # Fetch root assembly names early for progress callback
    root_assembly_data = get_final_part_data(api, root_assembly_ids)

    # --- Pass 1: Recursive BOM Calculation (Gross) ---
    logging.info("Starting Pass 1: Gross BOM Calculation...")
    num_targets = len(target_assemblies)
    for index, (part_id, quantity) in enumerate(target_assemblies.items()):
        if progress_callback and num_targets > 0:
            # Progress: 10% to 40% for Pass 1
            current_progress = 10 + int(((index + 1) / num_targets) * 30)
            part_name = root_assembly_data.get(part_id, {}).get("name", f"ID {part_id}")
            progress_text = (
                f"Pass 1: Calculating BOM for '{part_name}' ({index + 1}/{num_targets})"
            )
            progress_callback(current_progress, progress_text)
        try:
            # Call get_recursive_bom WITHOUT part_requirements_data for the first pass
            get_recursive_bom(
                api,
                int(part_id),
                float(quantity),
                gross_required_base_components, # Use gross accumulator
                int(part_id),
                template_only_flags,
                all_encountered_part_ids,
                required_sub_assemblies, # Populate sub-assemblies here
                include_consumables=True,
                bom_consumable_status=bom_consumable_status, # Populate initial status
                exclude_haip_calculation=exclude_haip_calculation,
                part_requirements_data=None, # Explicitly None for Pass 1
            )
            assembly_part_ids.add(int(part_id))
        except Exception as e:
            logging.error(f"Error during Pass 1 for assembly {part_id}: {e}", exc_info=True)
            continue
    logging.info("Finished Pass 1.")

    # --- Aggregate Sub-Assembly Requirements (After Pass 1) ---
    aggregated_sub_totals: Dict[int, float] = defaultdict(float)
    sub_to_roots_map: Dict[int, Set[int]] = defaultdict(set)
    logging.info("Aggregating total requirements for each sub-assembly...")
    for root_id, subs in required_sub_assemblies.items():
        for sub_id, qty in subs.items():
            aggregated_sub_totals[sub_id] += qty
            sub_to_roots_map[sub_id].add(root_id)
    logging.info(f"Aggregated sub-assembly totals: {dict(aggregated_sub_totals)}")
    logging.info(f"Sub-assembly to root map: {dict(sub_to_roots_map)}")


    # --- Prepare for Requirement Fetching ---
    # Combine base part IDs from Pass 1 and sub-assembly IDs for requirement fetching
    all_sub_assembly_ids = {sub_id for subs in required_sub_assemblies.values() for sub_id in subs.keys()}
    # Ensure all encountered parts (base + roots + subs from pass 1) are included
    all_ids_for_requirements = all_encountered_part_ids.union(all_sub_assembly_ids).union(set(target_assemblies.keys()))
    logging.debug(f"Combined IDs for requirement fetching: {all_ids_for_requirements}")

    # --- Fetch 'Required for Order' Data (After Pass 1) ---
    if progress_callback:
        progress_callback(45, "Fetching 'required for order' data...") # Adjusted progress
    part_requirements_data = defaultdict(int)
    if all_ids_for_requirements:
        logging.info(f"Fetching requirements data for {len(all_ids_for_requirements)} parts (incl. sub-assemblies)...")
        for part_id in all_ids_for_requirements:
            try:
                part_obj = Part(api, pk=part_id)
                # logging.info(f"Processing requirements for Part ID: {part_obj.pk}") # Can be verbose
                requirements = part_obj.getRequirements()
                if isinstance(requirements, dict):
                    required_total = requirements.get('required', 0)
                    required_total_val = 0
                    try:
                        required_total_val = int(float(required_total))
                    except (ValueError, TypeError):
                         logging.warning(f"Could not convert 'required' value '{required_total}' to int for part {part_id}. Defaulting to 0.")
                         required_total_val = 0
                    part_requirements_data[part_id] = required_total_val
                else:
                     part_requirements_data[part_id] = 0
                     logging.warning(f"Requirements data for part {part_id} was not a dictionary.")
            except Exception as e:
                logging.error(f"Error fetching requirements for part {part_id}: {e}", exc_info=True)
                part_requirements_data[part_id] = 0
    logging.info("Finished fetching requirement data.")

    # --- Pass 2: Recursive BOM Calculation (Net) ---
    logging.info("Starting Pass 2: Net BOM Calculation...")
    net_required_base_components: defaultdict[int, defaultdict[int, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    # Clear BOM consumable status for the net pass - it will be repopulated based on net needs
    bom_consumable_status.clear()
    # We reuse all_encountered_part_ids (doesn't hurt to add again)
    # We reuse required_sub_assemblies (already populated)
    # We reuse template_only_flags - NO! Pass 2 needs isolated structures.

    # Initialize isolated data structures for Pass 2 internal calculations
    pass2_template_flags = defaultdict(bool)
    pass2_encountered_ids = set()
    # Pass 2 doesn't *populate* sub-assemblies, but pass an empty dict of the expected type
    pass2_sub_assemblies = defaultdict(lambda: defaultdict(float))

    processed_subassemblies_in_pass2 = set() # Initialize set for tracking processed sub-assemblies in Pass 2

    for index, (part_id, quantity) in enumerate(target_assemblies.items()):
        if progress_callback and num_targets > 0:
            # Progress: 50% to 80% for Pass 2
            current_progress = 50 + int(((index + 1) / num_targets) * 30)
            part_name = root_assembly_data.get(part_id, {}).get("name", f"ID {part_id}")
            progress_text = (
                f"Pass 2: Calculating Net BOM for '{part_name}' ({index + 1}/{num_targets})"
            )
            progress_callback(current_progress, progress_text)
        try:
            # Call get_recursive_bom WITH part_requirements_data for the second pass
            get_recursive_bom(
                api,
                int(part_id),
                float(quantity),
                net_required_base_components, # Use NET accumulator
                int(part_id),
                pass2_template_flags,       # Use isolated flags for Pass 2
                pass2_encountered_ids,      # Use isolated encountered set for Pass 2
                pass2_sub_assemblies,       # Use isolated (empty) sub-assembly dict for Pass 2
                include_consumables=True,
                bom_consumable_status=bom_consumable_status, # Repopulate status based on net
                exclude_haip_calculation=exclude_haip_calculation,
                part_requirements_data=part_requirements_data, # Pass fetched data
                total_sub_assembly_reqs=aggregated_sub_totals, # Pass aggregated totals for 'to_build' calculation
                processed_net_subassemblies=processed_subassemblies_in_pass2, # Pass the tracking set
            )
            # No need to add to assembly_part_ids again
        except Exception as e:
            logging.error(f"Error during Pass 2 for assembly {part_id}: {e}", exc_info=True)
            continue
    logging.info(f"DEBUG: net_required_base_components after Pass 2: {dict(net_required_base_components)}")
    logging.info("Finished Pass 2.")


    # --- Consolidate NET Base Components ---
    total_required_quantities = defaultdict(float)
    for components in net_required_base_components.values(): # Use NET results
        for part_id, qty in components.items():
            total_required_quantities[part_id] += qty

    logging.info(f"DEBUG: total_required_quantities after consolidation: {dict(total_required_quantities)}")

    if not total_required_quantities:
        logging.info("No base components found after NET BOM processing. Nothing to order.")
        # Still return the sub-assembly list, it might be needed even if no base parts are.
        # Fetch details for sub-assemblies if needed for the list?
        # Let's fetch details for all encountered parts anyway, needed for sub-assembly list too.
        # return [], [], bom_consumable_status # Return empty dict for consumable status? No, return the potentially repopulated one.
        pass # Continue processing for sub-assemblies

    # --- Fetch Details for All Encountered Parts (Needed for both lists) ---
    if progress_callback:
        progress_callback(85, "Fetching details for all BOM parts...") # Adjusted progress
    # Ensure all IDs from both passes and roots are included for fetching details
    all_ids_for_details = all_encountered_part_ids.union(all_sub_assembly_ids).union(set(target_assemblies.keys()))
    final_part_data = get_final_part_data(api, tuple(all_ids_for_details))

    # --- Identify Sub-Assemblies (using final_part_data) ---
    # Collect all assemblies that are not root assemblies
    # assembly_part_ids was populated in Pass 1, reuse it.
    for part_id, part_data in final_part_data.items():
         # This logic seems redundant if assembly_part_ids is correctly populated in Pass 1.
         # Let's rely on required_sub_assemblies keys for the sub-assembly list later.
         # if part_data.get("assembly", False) and part_id not in root_assembly_ids:
         #     assembly_part_ids.add(part_id) # Already done in Pass 1
         pass


    # --- Calculate Stock, Order Need (Based on NET), and Collect Assembly Usage ---
    if progress_callback:
        progress_callback(90, "Calculating stock and order amounts...") # Adjusted progress
    parts_to_order_details = {} # Store final details here {part_id: {details}}
    part_available_stock_map = {} # Store calculated available stock

    # Log sub-assembly structure identified in Pass 1
    logging.info(f"Sub-assemblies from BOM traversal (Pass 1): {dict(required_sub_assemblies)}")

    # Populate details based on NET required quantities
    for part_id, net_required in total_required_quantities.items(): # Iterate NET requirements
        part_data = final_part_data.get(part_id)
        if not part_data:
            in_stock, is_template, variant_stock = 0.0, False, 0.0
            part_name = "Unknown"
        else:
            in_stock = part_data.get("in_stock", 0.0)
            is_template = part_data.get("is_template", False)
            variant_stock = part_data.get("variant_stock", 0.0)
            part_name = part_data.get("name", "Unknown")

        # Calculate available stock
        if is_template:
            total_available_stock = in_stock + variant_stock
        else:
            total_available_stock = in_stock

        part_available_stock_map[part_id] = total_available_stock

        # Store details based on NET requirements
        parts_to_order_details[part_id] = {
            "pk": part_id,
            "name": part_name,
            "total_required": round(net_required, 3), # Use NET required quantity
            "available_stock": round(total_available_stock, 3),
            "used_in_assemblies": set(), # Initialize, will be populated next
            "purchase_orders": [],
            "manufacturer_name": part_data.get("manufacturer_name") if part_data else None,
            "supplier_names": part_data.get("supplier_names", []) if part_data else [],
            "supplier_parts": part_data.get("supplier_parts", []) if part_data else [],
            "is_part_consumable": part_data.get("consumable", False) if part_data else False,
            "is_bom_consumable": False, # Initialize, updated later from net pass bom_consumable_status
        }

    # --- Collect Root Assembly Names for NET Needed Parts ---
    # Use net_required_base_components to determine which root assembly requires which NET base component
    for root_id, base_components in net_required_base_components.items(): # Use NET results
        root_assembly_name = final_part_data.get(root_id, {}).get(
            "name", f"Unknown Assembly (ID: {root_id})"
        )
        for part_id in base_components.keys():
            if part_id in parts_to_order_details: # Check if this part is in the NET required list
                parts_to_order_details[part_id]["used_in_assemblies"].add(root_assembly_name)

    # --- Fetch Purchase Order Data for Parts Potentially Needing Order (Based on NET) ---
    if progress_callback:
        progress_callback(92, "Fetching purchase order data...") # Adjusted progress
    part_ids_potentially_needing_order = list(parts_to_order_details.keys()) # IDs from NET calculation
    part_po_data = _fetch_purchase_order_data(api, part_ids_potentially_needing_order)

    # Requirement data already fetched before Pass 2

    # --- Build Final List (Based on NET results) ---
    if progress_callback:
        progress_callback(95, "Finalizing results...")
    final_list = []
    for part_id, details in parts_to_order_details.items():
        # Format used_in_assemblies
        details["used_in_assemblies"] = ", ".join(sorted(list(details["used_in_assemblies"])))
        # Add PO data
        details["purchase_orders"] = part_po_data.get(part_id, [])
        # Add 'required_for_order' data (fetched before Pass 2)
        details["required"] = part_requirements_data.get(part_id, 0)
        # Update BOM-level consumable status from the NET pass collected dictionary
        details["is_bom_consumable"] = bom_consumable_status.get(part_id, False) # Use status from NET pass
        # Calculate Saldo
        saldo = int(details["available_stock"] - details["required"])
        details["saldo"] = saldo
        # Calculate 'to_order' based on NET total_required and saldo
        details["to_order"] = max(0, round(details["total_required"] - saldo, 3)) # total_required is already NET

        final_list.append(details)

    # --- Apply Exclusions ---
    filtered_list = []
    excluded_supplier_count = 0
    excluded_manufacturer_count = 0

    for part in final_list:
        # Check if the excluded supplier is in the list of suppliers for this part
        supplier_match = (
            exclude_supplier_name
            and exclude_supplier_name in part.get("supplier_names", []) # Check against the list
        )
        manufacturer_match = (
            exclude_manufacturer_name
            and part.get("manufacturer_name") == exclude_manufacturer_name # Use correct key
        )

        if supplier_match:
            excluded_supplier_count += 1
            logging.debug(f"Excluding part {part['pk']} due to supplier: {exclude_supplier_name}")
            continue # Skip this part

        if manufacturer_match:
            excluded_manufacturer_count += 1
            logging.debug(f"Excluding part {part['pk']} due to manufacturer: {exclude_manufacturer_name}")
            continue # Skip this part

        # Only add if there's a non-negligible quantity to order based on the new calculation
        if part.get("to_order", 0) > 0.001:
            filtered_list.append(part)
        else:
            logging.debug(f"Filtering out part {part['pk']} because calculated to_order is {part.get('to_order', 0)}")


    if excluded_supplier_count > 0:
        logging.info(f"Excluded {excluded_supplier_count} parts from supplier '{exclude_supplier_name}'.")
    if excluded_manufacturer_count > 0:
        logging.info(f"Excluded {excluded_manufacturer_count} parts from manufacturer '{exclude_manufacturer_name}'.")

    # Sort the filtered list (e.g., by name)
    filtered_list.sort(key=lambda x: x["name"])

    # --- Prepare Sub-Assembly List ---
    sub_assembly_list = []

    # Log the contents of required_sub_assemblies for debugging
    logging.info(f"Required sub-assemblies: {dict(required_sub_assemblies)}")

    # Process the sub-assemblies using the aggregated totals
    logging.info("Generating final sub-assembly list based on aggregated totals...")
    for sub_id, total_qty in aggregated_sub_totals.items():
        # Get the sub-assembly name
        sub_name = final_part_data.get(sub_id, {}).get("name", f"Unknown (ID: {sub_id})")

        # Get stock information for this sub-assembly
        sub_part_data = final_part_data.get(sub_id, {})
        in_stock = sub_part_data.get("in_stock", 0.0)
        is_template = sub_part_data.get("is_template", False)
        variant_stock = sub_part_data.get("variant_stock", 0.0)

        # Calculate available stock
        if is_template:
            total_available_stock = in_stock + variant_stock
        else:
            total_available_stock = in_stock

        # Fetch the total required quantity for this sub-assembly across the entire order (external demand)
        required_val = part_requirements_data.get(sub_id, 0)

        # Calculate 'verfuegbar' (available after fulfilling external requirements)
        verfuegbar = total_available_stock - required_val # Stock - external demand

        # Get the quantity currently being built for this sub-assembly
        building_qty = sub_part_data.get("building", 0.0)
        # Calculate how many need to be built based on the aggregated total need for *this* calculation run
        # and the stock available after external requirements ('verfuegbar')
        # Consider the quantity already in build orders as effectively 'available' for meeting the total need.
        effective_available_for_build = verfuegbar + building_qty
        to_build = max(0, total_qty - effective_available_for_build)

        # Get the names of the root assemblies requiring this sub-assembly
        parent_root_ids = sub_to_roots_map.get(sub_id, set())
        parent_assembly_names = sorted([
            final_part_data.get(root_id, {}).get("name", f"Unknown (ID: {root_id})")
            for root_id in parent_root_ids
        ])
        for_assembly_str = ", ".join(parent_assembly_names)

        logging.info(f"Adding aggregated sub-assembly to list: {sub_name} (ID: {sub_id}) x{total_qty} for [{for_assembly_str}]")

        sub_assembly_list.append({
            "pk": sub_id,
            "name": sub_name,
            "quantity": round(total_qty, 3), # Total aggregated quantity needed for this calculation
            "available_stock": round(total_available_stock, 3), # Total stock across all locations
            "verfuegbar": round(verfuegbar, 3), # Stock remaining after external requirements
            "building": round(building_qty, 3), # Add the quantity currently being built
            "to_build": round(to_build, 3), # How many to build based on aggregated need and 'verfuegbar'
            "for_assembly": for_assembly_str, # Comma-separated list of parent assemblies
            "for_assembly_id": list(parent_root_ids), # Optional: include IDs if needed elsewhere
            "required_for_order": round(required_val, 3) # External requirement value
        })

    # Sort the sub-assembly list by name
    sub_assembly_list.sort(key=lambda x: x["name"])

    # Count how many sub-assemblies need to be built
    sub_assemblies_to_build = sum(1 for item in sub_assembly_list if item["to_build"] > 0)


    if progress_callback:
        progress_callback(100, "Berechnung abgeschlossen.")
    logging.info(f"Calculation complete. Found {len(filtered_list)} parts to order and {len(sub_assembly_list)} sub-assemblies (of which {sub_assemblies_to_build} need to be built). Returning BOM consumable status: {bom_consumable_status}")
    return filtered_list, sub_assembly_list, bom_consumable_status
