# inventree_logic.py
import os
import sys
import logging
from collections import defaultdict
from typing import List, Dict, Optional, Tuple, Callable
from inventree.api import InvenTreeAPI
from inventree.part import Part
# Import SupplierPart for type hinting if needed, handle potential ImportError later
try:
    from inventree.company import SupplierPart, Company
    from inventree.purchase_order import PurchaseOrderLineItem, PurchaseOrder
    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False
    # Initialize logger early to log the warning
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    log = logging.getLogger(__name__)
    log.warning("Could not import SupplierPart/Company/PurchaseOrder related classes. PO/Supplier checks might be limited.")


from streamlit import cache_data, cache_resource  # Streamlit caching importieren

# Configure logging (ensure it's configured even if imports fail)
if 'log' not in locals():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    log = logging.getLogger(__name__)

# Import API helper functions
from inventree_api_helpers import (
    # Assuming connect_to_inventree is only used here via api object passed in
    get_part_details,
    get_bom_items,
    # get_parts_in_category, # Not used directly in this file anymore
    get_final_part_data,
    _chunk_list # Import the chunking helper
)
# Import purchase order classes conditionally for PO fetching logic
# Already handled by the try/except block at the top


# --- BOM Calculation Logic ---

def get_recursive_bom(
    api: InvenTreeAPI,
    part_id: int,
    quantity: float,
    required_components: defaultdict[int, defaultdict[int, float]],
    root_input_id: int,
    template_only_flags: defaultdict[int, bool],
    all_encountered_part_ids: set[int], # New parameter to collect all IDs
):
    """Recursively processes the BOM using cached data fetching functions."""
    # Uses get_part_details and get_bom_items imported from inventree_api_helpers
    all_encountered_part_ids.add(part_id) # Add current part ID
    part_details = get_part_details(api, part_id)
    if not part_details:
        log.warning(f"Skipping part ID {part_id} due to fetch error in recursion.")
        return

    if part_details["assembly"]:
        log.debug(f"Processing assembly: {part_details['name']} (ID: {part_id}), Quantity: {quantity}")
        bom_items = get_bom_items(api, part_id)
        if bom_items:
            for item in bom_items:
                sub_part_id = item["sub_part"]
                all_encountered_part_ids.add(sub_part_id) # Add sub-part ID
                sub_quantity_per = item["quantity"]
                allow_variants = item["allow_variants"]
                total_sub_quantity = quantity * sub_quantity_per
                sub_part_details = get_part_details(api, sub_part_id) # Fetch details of sub-part
                if not sub_part_details:
                    log.warning(f"Skipping sub-part ID {sub_part_id} in BOM for {part_id} due to fetch error.")
                    continue
                is_template = sub_part_details.get("is_template", False)
                is_assembly = sub_part_details.get("assembly", False)
                if is_template and not allow_variants:
                    template_only_flags[sub_part_id] = True
                    log.debug(f"Adding template component (variants disallowed): {sub_part_details['name']} (ID: {sub_part_id}), Qty: {total_sub_quantity}")
                    required_components[root_input_id][sub_part_id] += total_sub_quantity
                elif is_assembly:
                    # Recurse if it's another assembly
                    get_recursive_bom(api, sub_part_id, total_sub_quantity, required_components, root_input_id, template_only_flags, all_encountered_part_ids) # Pass the set down
                else:
                    # Add base component requirement
                    log.debug(f"Adding base component: {sub_part_details['name']} (ID: {sub_part_id}), Qty: {total_sub_quantity}")
                    required_components[root_input_id][sub_part_id] += total_sub_quantity
        elif bom_items is None:
            log.warning(f"Could not process BOM for assembly {part_id} due to fetch error.")
    else:
        # It's a base component itself
        log.debug(f"Adding base component: {part_details['name']} (ID: {part_id}), Quantity: {quantity}")
        required_components[root_input_id][part_id] += quantity


# --- Main Calculation Function ---
def calculate_required_parts(
    api: InvenTreeAPI,
    target_assemblies: dict[int, float],
    exclude_supplier_name: Optional[str] = None, # New parameter
    exclude_manufacturer_name: Optional[str] = None, # New parameter
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> List[Dict[str, any]]:
    """
    Calculates the list of parts to order based on target assemblies,
    with options to exclude by supplier or manufacturer.
    """
    if not api:
        log.error("Cannot calculate parts: InvenTree API connection is not available.")
        return []
    if not target_assemblies:
        log.info("No target assemblies provided.")
        return []

    log.info(f"Calculating required components for targets: {target_assemblies}")
    required_base_components: defaultdict[int, defaultdict[int, float]] = defaultdict(lambda: defaultdict(float))
    template_only_flags: defaultdict[int, bool] = defaultdict(bool)
    all_encountered_part_ids: set[int] = set() # Initialize the set to collect all IDs

    # --- Get Names for Root Input Assemblies ---
    root_assembly_ids = tuple(target_assemblies.keys())
    # Fetch data including manufacturer and supplier names
    # Fetch data only for root assemblies initially, full data fetch moved after recursion
    root_assembly_data = get_final_part_data(api, root_assembly_ids)

    # --- Perform Recursive BOM Calculation ---
    num_targets = len(target_assemblies)
    for index, (part_id, quantity) in enumerate(target_assemblies.items()):
        log.info(f"Processing target assembly ID: {part_id}, Quantity: {quantity}")
        if progress_callback and num_targets > 0:
            current_progress = 10 + int(((index + 1) / num_targets) * 30)
            part_name = root_assembly_data.get(part_id, {}).get("name", f"ID {part_id}")
            progress_text = f"Calculating BOM for '{part_name}' ({index + 1}/{num_targets})"
            progress_callback(current_progress, progress_text)
        try:
            # Pass the new set to the recursive function
            get_recursive_bom(api, int(part_id), float(quantity), required_base_components, int(part_id), template_only_flags, all_encountered_part_ids)
        except ValueError:
            log.error(f"Invalid ID ({part_id}) or Quantity ({quantity}). Skipping.")
            continue
        except Exception as e:
            log.error(f"Error processing assembly {part_id}: {e}", exc_info=True)
            continue

    # --- Consolidate Base Components ---
    # Calculate total required quantity for each unique BASE part across all root assemblies
    total_required_quantities = defaultdict(float)
    for components in required_base_components.values():
        for part_id, qty in components.items():
            total_required_quantities[part_id] += qty

    log.info(f"Total unique base components required: {len(total_required_quantities)}")
    if not total_required_quantities:
        log.info("No base components found after BOM processing. Nothing to order.")
        return []

    # --- Get Final Data for ALL Encountered Parts ---
    if progress_callback: progress_callback(40, "Fetching details for all BOM parts...")
    # Add root assembly IDs to the set as well, in case they are needed directly
    all_encountered_part_ids.update(root_assembly_ids)
    if not all_encountered_part_ids:
         log.warning("No parts encountered during BOM traversal. This is unexpected.")
         return []
    log.info(f"Total unique parts encountered in BOMs (incl. assemblies): {len(all_encountered_part_ids)}")
    # Fetch data for ALL parts found during recursion
    final_part_data = get_final_part_data(api, tuple(all_encountered_part_ids))
    # Note: root_assembly_data is now a subset of final_part_data, can potentially remove its separate fetch later if not needed before recursion.

    # --- Calculate GLOBAL order need (using BASE components only) ---
    # This part remains the same, iterating over the base components that need ordering

    # --- Calculate GLOBAL order need ---
    if progress_callback: progress_callback(60, "Calculating order amounts...")
    global_parts_to_order_amount = {}
    part_available_stock = {}
    log.info("Calculating global order quantities and available stock...")
    for part_id, total_required in total_required_quantities.items():
        part_data = final_part_data.get(part_id)
        if not part_data:
            log.warning(f"Missing final data for Part ID {part_id} during global calculation. Assuming 0 stock.")
            in_stock, is_template, variant_stock = 0.0, False, 0.0
        else:
            in_stock = part_data.get("in_stock", 0.0)
            is_template = part_data.get("is_template", False)
            variant_stock = part_data.get("variant_stock", 0.0)

        template_only = template_only_flags.get(part_id, False)
        if template_only: total_available_stock = in_stock
        elif is_template: total_available_stock = in_stock + variant_stock
        else: total_available_stock = in_stock
        log.debug(f"Part {part_id} ({part_data.get('name', 'N/A') if part_data else 'N/A'}) - Available Stock: {total_available_stock} (Template Only: {template_only}, Is Template: {is_template})")

        part_available_stock[part_id] = total_available_stock
        global_to_order = total_required - total_available_stock
        global_parts_to_order_amount[part_id] = round(global_to_order, 3) if global_to_order > 0.001 else 0.0

    # --- Collect root assembly names for needed parts ---
    part_to_root_assemblies = defaultdict(set)
    for root_id, base_components in required_base_components.items():
        # Use the comprehensive final_part_data to get root assembly names
        root_assembly_name = final_part_data.get(root_id, {}).get("name", f"Unknown Assembly (ID: {root_id})")
        for part_id in base_components.keys(): # Iterate over base components for this root
            if global_parts_to_order_amount.get(part_id, 0.0) > 0: # Check if this base part needs ordering
                 part_to_root_assemblies[part_id].add(root_assembly_name)

    # --- Build the final FLAT list ---
    final_flat_parts_list = []
    log.info("Building final flat list with assembly context...")
    PO_STATUS_MAP = {10: "Pending", 20: "In Progress", 30: "Complete", 40: "Cancelled", 50: "Lost", 60: "Returned", 70: "On Hold"}

    # --- Pre-fetch Purchase Order Data (Optimized v2) ---
    unique_order_ids_to_fetch = set()
    part_po_line_data = defaultdict(list) # Store {part_id: [{'quantity': qty, 'order_id': oid}, ...]}
    fetched_po_details = {} # Store {order_id: {'ref': ref, 'status_code': code, 'status_label': label}}
    all_supplier_part_pks = [] # Store all relevant SupplierPart PKs
    CHUNK_SIZE = 100 # Define chunk size for PO fetching as well

    if IMPORTS_AVAILABLE:
        po_fetch_progress_step = 80
        if progress_callback: progress_callback(po_fetch_progress_step, "Fetching supplier parts...")
        try:
            parts_needing_order_ids = [pid for pid, amount in global_parts_to_order_amount.items() if amount > 0]
            if parts_needing_order_ids:
                log.info(f"Optimized PO Fetch: Fetching SupplierParts for {len(parts_needing_order_ids)} parts...")
                # Attempt batch fetch for SupplierParts using part__in
                try:
                    # Fetch 'part' field too, to map back SP pk to original Part pk
                    supplier_parts_list = SupplierPart.list(api, part__in=parts_needing_order_ids, fields=['pk', 'part'])
                    all_supplier_part_pks = [sp.pk for sp in supplier_parts_list]
                    # Create a map from supplier_part pk back to the original part pk
                    sp_pk_to_part_id = {sp.pk: sp._data.get('part') for sp in supplier_parts_list}
                    log.info(f"Fetched {len(supplier_parts_list)} supplier parts via batch.")
                except Exception as batch_sp_err:
                    log.warning(f"Batch fetch for SupplierParts failed ({batch_sp_err}). Individual fetch might be slow.")
                    # Fallback or error handling if batch fails - for now, we'll proceed, PO info might be incomplete
                    all_supplier_part_pks = []
                    sp_pk_to_part_id = {}


                # Fetch all relevant PO Lines in one batch using collected SupplierPart PKs
                if all_supplier_part_pks:
                    log.info(f"Optimized PO Fetch: Fetching PO Lines for {len(all_supplier_part_pks)} SupplierParts...")
                    if progress_callback: progress_callback(po_fetch_progress_step + 5, "Fetching purchase order lines...")
                    all_po_lines = []
                    try:
                        # Fetch PO lines in chunks
                        for sp_pk_chunk in _chunk_list(all_supplier_part_pks, CHUNK_SIZE):
                             log.debug(f"Fetching PO lines for chunk of {len(sp_pk_chunk)} SupplierPart PKs...")
                             chunk_po_lines = PurchaseOrderLineItem.list(api, supplier_part__in=sp_pk_chunk, fields=['order', 'quantity', 'supplier_part'])
                             if chunk_po_lines:
                                 all_po_lines.extend(chunk_po_lines)
                        log.info(f"Fetched a total of {len(all_po_lines)} PO lines across all chunks.")

                        # Process the fetched lines
                        for line in all_po_lines:
                            order_id = line._data.get('order')
                            supplier_part_pk = line._data.get('supplier_part')
                            part_id = sp_pk_to_part_id.get(supplier_part_pk) # Find original part_id

                            if order_id and part_id:
                                unique_order_ids_to_fetch.add(order_id)
                                part_po_line_data[part_id].append({'quantity': line.quantity, 'order_id': order_id})
                    except Exception as chunked_line_err:
                         log.error(f"Error during chunked PO line fetch: {chunked_line_err}", exc_info=True)
                         # Clear data as it might be incomplete
                         unique_order_ids_to_fetch.clear()
                         part_po_line_data.clear()

        except Exception as e:
            log.error(f"Error during initial supplier part fetch for POs: {e}", exc_info=True)
            # Clear data as it might be incomplete
            unique_order_ids_to_fetch.clear()
            part_po_line_data.clear()

        # Fetch details for unique POs
        if unique_order_ids_to_fetch:
            log.info(f"Fetching details for {len(unique_order_ids_to_fetch)} unique Purchase Orders...")
            if progress_callback: progress_callback(90, f"Fetching {len(unique_order_ids_to_fetch)} PO details...")
            order_ids_list = list(unique_order_ids_to_fetch)
            try:
                 # Fetch PO details in chunks
                 for order_id_chunk in _chunk_list(order_ids_list, CHUNK_SIZE):
                     log.debug(f"Fetching PO details for chunk of {len(order_id_chunk)} Order PKs...")
                     chunk_orders = PurchaseOrder.list(api, pk__in=order_id_chunk, fields=['pk', 'reference', 'status'])
                     if chunk_orders:
                         for order in chunk_orders:
                             status_code = order._data.get('status')
                             # Only store details for relevant statuses
                             if status_code in [10, 20]: # Pending or In Progress
                                 fetched_po_details[order.pk] = {
                                     'ref': order._data.get('reference', 'No Ref'),
                                     'status_code': status_code,
                                     'status_label': PO_STATUS_MAP.get(status_code, f"Unknown ({status_code})")
                                 }
                 log.info(f"Fetched details for {len(fetched_po_details)} relevant POs across all chunks.")
            except Exception as e:
                 log.error(f"Error during chunked PO detail fetch: {e}. PO info might be incomplete.", exc_info=True)
                 # Individual fallback is removed to avoid potential hangs if batch fails massively

    # --- Assemble Final List using pre-fetched data ---
    if progress_callback: progress_callback(98, "Assembling final list...")
    for part_id, global_to_order in global_parts_to_order_amount.items():
         if global_to_order > 0:
            # Use the comprehensive final_part_data here as well
            part_data = final_part_data.get(part_id)
            if not part_data:
                # This log might indicate an issue if a base component wasn't fetched
                log.error(f"Data inconsistency: Missing final data for required base component ID {part_id}.")
                part_name, total_required, manufacturer_name, supplier_names = f"Error (ID: {part_id})", 0.0, None, []
            else:
                part_name = part_data.get("name", f"Unknown (ID: {part_id})")
                total_required = total_required_quantities[part_id] # Still use the calculated total for base part
                manufacturer_name = part_data.get("manufacturer_name")
                supplier_names = part_data.get("supplier_names", []) # Get supplier names from the comprehensive data

            used_in_assemblies_str = ", ".join(sorted(list(part_to_root_assemblies.get(part_id, set()))))

            # Build purchase_orders_info using pre-fetched details
            purchase_orders_info = []
            if part_id in part_po_line_data:
                for line_data in part_po_line_data[part_id]:
                    order_id = line_data['order_id']
                    if order_id in fetched_po_details: # Check if PO details were fetched and relevant
                        po_detail = fetched_po_details[order_id]
                        purchase_orders_info.append({
                            "ref": po_detail['ref'],
                            "quantity": line_data['quantity'],
                            "status": po_detail['status_label']
                        })

            # Append data for this part
            final_flat_parts_list.append({
                "pk": part_id,
                "name": part_name,
                "total_required": round(total_required, 3),
                "available_stock": round(part_available_stock.get(part_id, 0.0), 3),
                "to_order": round(global_to_order, 3),
                "used_in_assemblies": used_in_assemblies_str,
                "purchase_orders": purchase_orders_info,
                "manufacturer_name": manufacturer_name,
                "supplier_names": supplier_names,
            })
    # End of loop

    # --- Filtering based on Supplier and Manufacturer ---
    filtered_list = final_flat_parts_list
    original_count = len(filtered_list)
    parts_removed_count = 0

    # Filter by Supplier
    if exclude_supplier_name:
        supplier_to_exclude_lower = exclude_supplier_name.strip().lower()
        log.info(f"Filtering out parts from supplier: '{exclude_supplier_name}'")
        # Add detailed logging before filtering
        temp_filtered_list = []
        for part in filtered_list:
            part_id_for_log = part.get("pk")
            supplier_names_for_log = part.get("supplier_names", [])
            suppliers_lower_for_log = [s.lower() for s in supplier_names_for_log]
            # Log details specifically for part 1516 or any part being filtered
            if part_id_for_log == 1516:
                 log.info(f"Checking Part ID {part_id_for_log}: Suppliers = {supplier_names_for_log}, Lowercase = {suppliers_lower_for_log}. Comparing against '{supplier_to_exclude_lower}'.")

            # Apply the filter condition
            if supplier_to_exclude_lower not in suppliers_lower_for_log:
                temp_filtered_list.append(part)
            elif part_id_for_log == 1516: # Log if 1516 is being excluded
                 log.info(f"Excluding Part ID {part_id_for_log} because '{supplier_to_exclude_lower}' was found in {suppliers_lower_for_log}.")

        filtered_list = temp_filtered_list
        # Log the state *after* supplier filtering is complete
        supplier_filtered_ids = [p.get('pk') for p in filtered_list]
        log.info(f"After supplier filter. Remaining IDs ({len(supplier_filtered_ids)}): {supplier_filtered_ids}")
        if 1516 not in supplier_filtered_ids and exclude_supplier_name and exclude_supplier_name.strip().lower() == "haip solutions gmbh":
             log.info("Confirmed: Part 1516 is NOT in the list after supplier filter.")
        elif 1516 in supplier_filtered_ids and exclude_supplier_name and exclude_supplier_name.strip().lower() == "haip solutions gmbh":
             log.warning("Inconsistency: Part 1516 IS STILL in the list after supplier filter, despite logs indicating exclusion.")

        parts_removed_supplier = original_count - len(filtered_list)
        if parts_removed_supplier > 0:
            log.info(f"Removed {parts_removed_supplier} parts based on supplier filter.")
            parts_removed_count += parts_removed_supplier

    # Filter by Manufacturer (on the already potentially filtered list)
    if exclude_manufacturer_name:
        manufacturer_to_exclude_lower = exclude_manufacturer_name.strip().lower()
        log.info(f"Filtering out parts from manufacturer: '{exclude_manufacturer_name}'")
        current_count_before_mfg = len(filtered_list)
        filtered_list = [
            part for part in filtered_list
            if str(part.get("manufacturer_name", "")).strip().lower() != manufacturer_to_exclude_lower
        ]
        parts_removed_manufacturer = current_count_before_mfg - len(filtered_list)
        if parts_removed_manufacturer > 0:
             log.info(f"Removed {parts_removed_manufacturer} parts based on manufacturer filter.")
             parts_removed_count += parts_removed_manufacturer

    if parts_removed_count > 0:
         log.info(f"Total parts removed by filters: {parts_removed_count}. Final list size: {len(filtered_list)}")

    final_flat_parts_list = filtered_list # Assign the potentially manufacturer-filtered list

    # Log the final list before returning
    final_ids = [p.get('pk') for p in final_flat_parts_list]
    log.info(f"Final list being returned by calculate_required_parts. IDs ({len(final_ids)}): {final_ids}")
    if 1516 not in final_ids and exclude_supplier_name and exclude_supplier_name.strip().lower() == "haip solutions gmbh":
        log.info("Confirmed: Part 1516 is NOT in the final returned list.")
    elif 1516 in final_ids and exclude_supplier_name and exclude_supplier_name.strip().lower() == "haip solutions gmbh":
        log.warning("Inconsistency: Part 1516 IS in the final returned list!")

    # --- Final Sorting ---
    final_flat_parts_list.sort(key=lambda x: x["name"])

    # --- Final Progress Update & Return ---
    if progress_callback:
        progress_callback(100, "Calculation complete!")

    log.info(f"Calculation finished. Returning {len(final_flat_parts_list)} parts to order.")
    return final_flat_parts_list
