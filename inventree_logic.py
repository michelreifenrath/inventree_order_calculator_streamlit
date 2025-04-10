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
    PO_STATUS_MAP = {10: "Pending", 20: "Placed", 25: "On Hold", 30: "Complete", 40: "Cancelled", 50: "Lost", 60: "Returned"} # Corrected based on InvenTree source

    # --- Pre-fetch Purchase Order Data (Refactored v3 - Fetch POs first) ---
    part_po_line_data = defaultdict(list) # Store {part_id: [{'quantity': qty, 'po_ref': ref, 'po_status': status}, ...]}
    all_supplier_part_pks = [] # Store all relevant SupplierPart PKs
    sp_pk_to_part_id = {} # Map SupplierPart PK back to Part ID
    relevant_po_details = {} # Store {po_pk: {'ref': ref, 'status_label': label}}
    relevant_po_pks = [] # List of relevant PO PKs
    CHUNK_SIZE = 100 # Define chunk size for API calls

    if IMPORTS_AVAILABLE:
        po_fetch_progress_step = 80 # Base progress step
        if progress_callback: progress_callback(po_fetch_progress_step, "Fetching supplier parts...")

        # --- Step 1 (Existing): Fetch SupplierParts for parts needing order ---
        try:
            parts_needing_order_ids = [pid for pid, amount in global_parts_to_order_amount.items() if amount > 0]
            if parts_needing_order_ids:
                log.info(f"Refactored PO Fetch: Fetching SupplierParts for {len(parts_needing_order_ids)} parts...")
                try:
                    # Fetch 'part' field too, to map back SP pk to original Part pk
                    supplier_parts_list = SupplierPart.list(api, part__in=parts_needing_order_ids, fields=['pk', 'part'])
                    all_supplier_part_pks = [sp.pk for sp in supplier_parts_list]
                    # Create a map from supplier_part pk back to the original part pk
                    sp_pk_to_part_id = {sp.pk: sp._data.get('part') for sp in supplier_parts_list}
                    log.info(f"Fetched {len(supplier_parts_list)} supplier parts via batch. Map created.")
                    # --- Roo Debug ---
                    log.info(f"DEBUG PO Fetch: sp_pk_to_part_id map created: {sp_pk_to_part_id}")
                    if 780 in sp_pk_to_part_id:
                        log.info(f"DEBUG PO Fetch: SupplierPart 780 maps to Part ID: {sp_pk_to_part_id.get(780)}")
                    else:
                        log.warning("DEBUG PO Fetch: SupplierPart 780 NOT found in sp_pk_to_part_id map keys!")
                    # --- End Roo Debug ---
                except Exception as batch_sp_err:
                    log.warning(f"Batch fetch for SupplierParts failed ({batch_sp_err}). PO info might be incomplete.")
                    all_supplier_part_pks = []
                    sp_pk_to_part_id = {}
            else:
                log.info("Refactored PO Fetch: No parts require ordering, skipping SupplierPart fetch.")

        except Exception as e:
            log.error(f"Error during initial supplier part fetch for POs: {e}", exc_info=True)
            # Clear potentially partial data
            all_supplier_part_pks = []
            sp_pk_to_part_id = {}

        # --- Step 2 (New): Fetch Relevant Purchase Orders (Pending/In Progress) ---
        if progress_callback: progress_callback(po_fetch_progress_step + 5, "Fetching relevant purchase orders...")
        try:
            log.info("Refactored PO Fetch: Fetching ALL Purchase Orders (API status filter unreliable)...")
            # Define desired statuses for local filtering
            relevant_statuses = [10, 20, 25] # 10: Pending, 20: Placed, 25: On Hold (Corrected based on source code)
            # Fetch ALL POs without API status filter due to observed unreliability (especially for status 70)
            # We will filter locally in the subsequent loop. This might be less efficient for large numbers of POs.
            log.warning("Fetching all POs without status filter due to API filter issues. This might be slow.")
            relevant_orders = PurchaseOrder.list(api, fields=['pk', 'reference', 'status']) # Removed status__in filter

            if relevant_orders:
                processed_relevant_count = 0
                for order in relevant_orders:
                    status_code = order._data.get('status')
                    # Explicitly check if the status is one we want, as a safeguard
                    if status_code in relevant_statuses:
                        order_pk = order.pk
                        relevant_po_pks.append(order_pk)
                        relevant_po_details[order_pk] = {
                            'ref': order._data.get('reference', 'No Ref'),
                            'status_label': PO_STATUS_MAP.get(status_code, f"Unknown ({status_code})")
                        }
                        processed_relevant_count += 1
                    else:
                        # Log if a PO with an unexpected status was returned by the API call
                        log.warning(f"API returned PO {order.pk} (Ref: {order._data.get('reference', 'N/A')}) with unexpected status {status_code} despite status__in filter. Ignoring.")
                log.info(f"Filtered {len(relevant_orders)} fetched POs down to {processed_relevant_count} POs with relevant statuses ({relevant_statuses}).") # Line number adjusted due to previous diff
            else:
                log.info("No relevant Purchase Orders (Pending/In Progress) found.")

        except Exception as e:
            log.error(f"Error fetching relevant Purchase Orders: {e}. PO info might be incomplete.", exc_info=True)
            relevant_po_details.clear()
            relevant_po_pks = [] # Ensure list is empty

        # --- Step 3 (New): Fetch PO Lines using order__in filter ---
        all_po_lines = []
        if relevant_po_pks: # Only fetch lines if we have relevant POs
            if progress_callback: progress_callback(po_fetch_progress_step + 10, f"Fetching PO lines for {len(relevant_po_pks)} POs...")
            log.info(f"Refactored PO Fetch: Fetching PO Lines for {len(relevant_po_pks)} relevant POs using order__in...")
            try:
                # Fetch PO lines in chunks based on relevant PO PKs
                for i, po_pk_chunk in enumerate(_chunk_list(relevant_po_pks, CHUNK_SIZE)):
                    log.debug(f"Fetching PO lines chunk {i+1} for {len(po_pk_chunk)} PO PKs...")
                    try:
                        # Use order__in filter - Fetch 'part' field for fallback logic
                        chunk_po_lines = PurchaseOrderLineItem.list(api, order__in=po_pk_chunk, fields=['pk', 'order', 'quantity', 'supplier_part', 'part']) # Added 'pk' and 'part'
                        if chunk_po_lines:
                            log.debug(f"Fetched {len(chunk_po_lines)} lines in chunk {i+1}.")
                            all_po_lines.extend(chunk_po_lines)
                        else:
                            log.debug(f"No lines returned for PO chunk {i+1}.")
                    except Exception as line_fetch_err:
                        log.error(f"ERROR fetching PO lines for PO chunk {i+1} (Order PKs: {po_pk_chunk}): {line_fetch_err}", exc_info=True)
                        # Continue to next chunk on error
                log.info(f"Fetched a total of {len(all_po_lines)} PO lines across all relevant POs.")
            except Exception as outer_line_fetch_err:
                log.error(f"ERROR during the PO line chunking/fetching process (order__in): {outer_line_fetch_err}", exc_info=True)
                all_po_lines = [] # Ensure list is empty if process failed
        else:
            log.info("Refactored PO Fetch: No relevant POs found, skipping PO Line fetch.")

        # --- Step 4 (New): Process Lines and Link to Parts ---
        if all_po_lines:
            if progress_callback: progress_callback(po_fetch_progress_step + 15, f"Processing {len(all_po_lines)} PO lines...")
            log.info(f"Refactored PO Fetch: Processing {len(all_po_lines)} fetched PO lines and linking to parts...")
            processed_count = 0
            skipped_count = 0
            try:
                # --- Start of Corrected Processing Loop ---
                for line in all_po_lines:
                    line_pk = line.pk # Get line PK for logging
                    supplier_part_pk = line._data.get('supplier_part')
                    order_id = line._data.get('order')
                    part_id = None # Initialize part_id

                    # Attempt 1: Use the standard supplier_part field
                    if supplier_part_pk:
                        part_id = sp_pk_to_part_id.get(supplier_part_pk)

                    # Attempt 2 (Fallback): If supplier_part is None, try using the line's 'part' field
                    if not part_id:
                        fallback_sp_pk = line._data.get('part')
                        if fallback_sp_pk:
                            part_id = sp_pk_to_part_id.get(fallback_sp_pk)
                            if part_id:
                                log.warning(f"Data Anomaly: Used fallback line.part field ({fallback_sp_pk}) to map PO Line {line_pk} to Part ID {part_id} (SP PK was None).")
                            # else: Fallback also failed, part_id remains None

                    # Now part_id is either the correctly mapped ID, the fallback mapped ID, or None
                    po_info = relevant_po_details.get(order_id) # Get pre-fetched PO details

                    # --- Roo Debug ---
                    # Check if the *resolved* part_id matches our target, regardless of how it was found
                    if part_id == 1087:
                        log.info(f"DEBUG PO Fetch (Refactored+Fallback): Processing line {line_pk} which resolved to Part ID 1087. Original SP PK: {supplier_part_pk}, Fallback PK used: {line._data.get('part') if not supplier_part_pk else 'N/A'}. Order ID: {order_id}. PO Info found: {po_info is not None}")
                    # --- End Roo Debug ---

                    if part_id and po_info: # Check if part mapping (either primary or fallback) and PO info exist
                        part_po_line_data[part_id].append({
                            'quantity': line.quantity,
                            'po_ref': po_info['ref'],
                            'po_status': po_info['status_label']
                        })
                        processed_count += 1
                    elif not part_id: # This means both primary and fallback mapping failed
                        # Log only if we expected to map this line based on *either* the SP_PK or the fallback PK
                        original_sp_pk = line._data.get('supplier_part')
                        fallback_sp_pk = line._data.get('part')
                        # Check if either the original SP PK or the fallback SP PK was in our map of relevant supplier parts
                        should_have_mapped = (original_sp_pk in sp_pk_to_part_id) or (fallback_sp_pk in sp_pk_to_part_id)

                        if should_have_mapped:
                             log.warning(f"Refactored PO Fetch: Could not map PO Line {line_pk} to a Part ID using SP PK ({original_sp_pk}) or fallback line.part PK ({fallback_sp_pk}). Skipping line.")
                        # else: # Don't log if we never expected to map this line anyway
                        #    log.debug(f"Skipping PO Line {line_pk} as neither its SP PK ({original_sp_pk}) nor fallback PK ({fallback_sp_pk}) map to a required part.")
                        skipped_count += 1 # Corrected indentation
                    elif not po_info:
                         # This case shouldn't happen with the refactored logic but good to keep
                         log.error(f"Logic Error: Found line {line_pk} for Order ID {order_id} but no details were fetched for this PO.")
                         skipped_count += 1 # Corrected indentation
                # --- End of Corrected Processing Loop ---

                log.info(f"Finished processing PO lines. Linked: {processed_count}, Skipped (no part map): {skipped_count}")
            except Exception as process_line_err:
                log.error(f"Error during PO line processing (Refactored): {process_line_err}", exc_info=True)
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

            # Build purchase_orders_info using pre-fetched data (Refactored)
            po_data_list = part_po_line_data.get(part_id, []) # Get the pre-assembled list from the refactored data structure

            # Rename keys to match expected format for final list structure used later
            purchase_orders_info = [
                {"ref": item['po_ref'], "quantity": item['quantity'], "status": item['po_status']}
                for item in po_data_list
            ]

            # --- Roo Debug Logging START ---
            if part_id == 1087:
                 log.info(f"DEBUG (Refactored): Final purchase_orders_info for Part ID {part_id}: {purchase_orders_info}")
            # --- Roo Debug Logging END ---

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
            # Log details if needed
            # if part_id_for_log == SOME_ID_TO_DEBUG:
            #      log.info(f"Checking Part ID {part_id_for_log}: Suppliers = {supplier_names_for_log}, Lowercase = {suppliers_lower_for_log}. Comparing against '{supplier_to_exclude_lower}'.")

            # Apply the filter condition
            if supplier_to_exclude_lower not in suppliers_lower_for_log:
                temp_filtered_list.append(part)
            # elif part_id_for_log == SOME_ID_TO_DEBUG: # Log if specific part is being excluded
            #      log.info(f"Excluding Part ID {part_id_for_log} because '{supplier_to_exclude_lower}' was found in {suppliers_lower_for_log}.")

        filtered_list = temp_filtered_list
        # Log the state *after* supplier filtering is complete
        supplier_filtered_ids = [p.get('pk') for p in filtered_list]
        log.info(f"After supplier filter. Remaining IDs ({len(supplier_filtered_ids)}): {supplier_filtered_ids}")
        # Example check for a specific part after filtering (can be removed or adapted)
        # if SOME_ID_TO_DEBUG not in supplier_filtered_ids and exclude_supplier_name:
        #      log.info(f"Confirmed: Part {SOME_ID_TO_DEBUG} is NOT in the list after supplier filter.")
        # elif SOME_ID_TO_DEBUG in supplier_filtered_ids and exclude_supplier_name:
        #      log.warning(f"Inconsistency: Part {SOME_ID_TO_DEBUG} IS STILL in the list after supplier filter.")

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
    # Example check for a specific part in the final list (can be removed or adapted)
    # if SOME_ID_TO_DEBUG not in final_ids and exclude_supplier_name:
    #     log.info(f"Confirmed: Part {SOME_ID_TO_DEBUG} is NOT in the final returned list.")
    # elif SOME_ID_TO_DEBUG in final_ids and exclude_supplier_name:
    #     log.warning(f"Inconsistency: Part {SOME_ID_TO_DEBUG} IS in the final returned list!")

    # --- Final Sorting ---
    final_flat_parts_list.sort(key=lambda x: x["name"])

    # --- Final Progress Update & Return ---
    if progress_callback:
        progress_callback(100, "Calculation complete!")

    log.info(f"Calculation finished. Returning {len(final_flat_parts_list)} parts to order.")
    return final_flat_parts_list
