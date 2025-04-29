import logging
from collections import defaultdict
from typing import Optional, Set, Dict, Any
from inventree.api import InvenTreeAPI
# Absolute import - Added get_final_part_data
from src.inventree_api_helpers import get_part_details, get_bom_items, get_final_part_data


def get_recursive_bom(
    api: InvenTreeAPI,
    part_id: int,
    quantity: float,
    required_components: defaultdict[int, defaultdict[int, float]],
    root_input_id: int,
    template_only_flags: defaultdict[int, bool],
    all_encountered_part_ids: Set[int],
    sub_assemblies: Optional[defaultdict[int, defaultdict[int, float]]] = None,
    include_consumables: bool = True,
    bom_consumable_status: Optional[dict[int, bool]] = None, # Track BOM line consumable status
    exclude_haip_calculation: bool = False, # New flag to exclude HAIP parts
    part_requirements_data: Optional[Dict[int, int]] = None, # New: Requirements for parts
    total_sub_assembly_reqs: Optional[Dict[int, float]] = None, # New: Aggregated requirements for sub-assemblies
    processed_net_subassemblies: Optional[Set[int]] = None, # New: Track processed sub-assemblies in Pass 2
) -> dict[int, bool]:
    """
    Recursively processes the BOM using cached data fetching functions.

    Args:
        api (InvenTreeAPI): The API connection.
        part_id (int): The current part ID to process.
        quantity (float): The quantity of this part needed.
        required_components (defaultdict[int, defaultdict[int, float]]): Accumulator for required base components.
        root_input_id (int): The root assembly ID for grouping.
        template_only_flags (defaultdict[int, bool]): Flags for template-only parts.
        all_encountered_part_ids (set[int]): Set to collect all encountered part IDs.
        sub_assemblies (defaultdict): Tracks sub-assemblies needed for each root.
        include_consumables (bool): If False, quantities for parts marked 'consumable' are ignored.
        bom_consumable_status (dict): Tracks if a part was marked consumable on any BOM line.
        exclude_haip_calculation (bool): If True, parts supplied by HAIP Solutions are excluded from quantity calculations.
        part_requirements_data (Optional[Dict[int, int]]): Dictionary mapping part IDs to their required quantity for the order. Defaults to None.
        total_sub_assembly_reqs (Optional[Dict[int, float]]): Dictionary mapping sub-assembly part IDs to their total aggregated required quantity across all parent paths. Used in Pass 2. Defaults to None.
        processed_net_subassemblies (Optional[Set[int]]): A set containing the IDs of sub-assemblies whose net requirements have already been calculated in the current Pass 2 run. Defaults to None.

    Returns:
        dict[int, bool]: The updated bom_consumable_status dictionary.
    """
    # Reason: We collect all part IDs to later fetch details in bulk, improving performance.
    all_encountered_part_ids.add(part_id)
    part_details = get_part_details(api, part_id)
    if not part_details:
        logging.warning(f"Skipping part ID {part_id} due to fetch error in recursion.")
        return

    # Initialize sub_assemblies if not provided
    if sub_assemblies is None:
        sub_assemblies = defaultdict(lambda: defaultdict(float))

    # Initialize bom_consumable_status if it's the first call
    if bom_consumable_status is None:
        bom_consumable_status = {}

    if part_details.get("assembly", False):
        logging.debug(
            f"Processing assembly: {part_details.get('name')} (ID: {part_id}), Quantity: {quantity}"
        )
        bom_items = get_bom_items(api, part_id)
        if bom_items:
            for item in bom_items:
                sub_part_id = item["sub_part"]
                all_encountered_part_ids.add(sub_part_id)
                sub_quantity_per = item["quantity"]
                allow_variants = item["allow_variants"]
                # Check the consumable status *on the BOM line itself*
                is_bom_item_consumable = item.get("consumable", False)
                # Update the tracking dictionary
                bom_consumable_status[sub_part_id] = bom_consumable_status.get(sub_part_id, False) or is_bom_item_consumable

                # --- HAIP Exclusion Check ---
                # Check *before* fetching details or adding quantities if exclusion is active
                if exclude_haip_calculation:
                    # Fetch final data specifically for this part ID (will use cache)
                    part_final_data_dict = get_final_part_data(api, (sub_part_id,)) # Use tuple for single ID
                    part_final_data = part_final_data_dict.get(sub_part_id, {})
                    is_haip = part_final_data.get('is_haip_part', False)
                    if is_haip:
                        logging.debug(f"Excluding HAIP part {sub_part_id} ('{part_final_data.get('name', 'N/A')}') from calculation based on checkbox.")
                        continue # Skip processing this BOM item entirely if it's a HAIP part

                # --- Continue processing if not excluded ---
                total_sub_quantity = quantity * sub_quantity_per
                sub_part_details = get_part_details(api, sub_part_id) # Fetch basic details
                if not sub_part_details:
                    logging.warning(
                        f"Skipping sub-part ID {sub_part_id} in BOM for {part_id} due to fetch error."
                    )
                    continue
                is_template = sub_part_details.get("is_template", False)
                is_assembly = sub_part_details.get("assembly", False)
                # Note: The part's own consumable flag (is_part_consumable) is still relevant for quantity calculation if include_consumables=False
                is_part_consumable = sub_part_details.get("consumable", False)

                if is_template and not allow_variants:
                    template_only_flags[sub_part_id] = True
                    logging.debug(
                        f"Template component (variants disallowed): {sub_part_details.get('name')} (ID: {sub_part_id}), Qty: {total_sub_quantity}, PartConsumable: {is_part_consumable}, BomItemConsumable: {is_bom_item_consumable}"
                    )
                    # Quantity calculation depends on the part's consumable flag and the include_consumables setting
                    if include_consumables or not is_part_consumable:
                        required_components[root_input_id][
                            sub_part_id
                        ] += total_sub_quantity
                    else:
                        logging.debug(f"Ignoring part-consumable template quantity for {sub_part_id}")
                elif is_assembly:
                    # This is a sub-assembly
                    # First, add it to the sub_assemblies dictionary
                    logging.debug(
                        f"Found sub-assembly: {sub_part_details.get('name')} (ID: {sub_part_id}) for root {root_input_id}, Qty: {total_sub_quantity}"
                    )
                    # Add to sub-assemblies tracking
                    sub_assemblies[root_input_id][sub_part_id] += total_sub_quantity
                    logging.info(f"REC_BOM_DEBUG: Added/Updated sub_assembly[{root_input_id}][{sub_part_id}] = {sub_assemblies[root_input_id][sub_part_id]}")

                    # Check stock for this sub-assembly first
                    in_stock = sub_part_details.get("in_stock", 0.0)
                    is_template = sub_part_details.get("is_template", False) # Re-check template status for stock calc
                    variant_stock = sub_part_details.get("variant_stock", 0.0)

                    # Calculate available stock based on parent BOM's allow_variants setting
                    if allow_variants:
                        available_stock = in_stock + variant_stock
                        logging.debug(f"Sub-assembly {sub_part_id}: Allowing variants, Available Stock = {in_stock} (in) + {variant_stock} (variant) = {available_stock}")
                    else:
                        available_stock = in_stock
                        logging.debug(f"Sub-assembly {sub_part_id}: Not allowing variants, Available Stock = {in_stock}")

                    # Fetch requirement for this sub-assembly
                    required_val = part_requirements_data.get(sub_part_id, 0) if part_requirements_data else 0
                    logging.debug(f"Sub-assembly {sub_part_id}: Required for order = {required_val}")

                    # Calculate effective available stock ('verfuegbar')
                    verfuegbar = available_stock - required_val
                    logging.debug(f"Sub-assembly {sub_part_id}: Effective Available Stock (verfuegbar) = {available_stock} - {required_val} = {verfuegbar}")

                    # Calculate how many need to be built based on effective stock and TOTAL aggregated requirement
                    # Use the aggregated requirement if provided (Pass 2), otherwise use the requirement from this specific path (Pass 1)
                    aggregated_qty = total_sub_assembly_reqs.get(sub_part_id, 0) if total_sub_assembly_reqs else total_sub_quantity
                    to_build = max(0, aggregated_qty - verfuegbar)

                    logging.debug(
                        f"Sub-assembly {sub_part_details.get('name')} (ID: {sub_part_id}): Path Need {total_sub_quantity}, Aggregated Need {aggregated_qty}, Effective Available {verfuegbar}, To Build {to_build}"
                    )

                    # Pass 2 Check: Skip if this sub-assembly's net components were already calculated
                    if processed_net_subassemblies is not None and sub_part_id in processed_net_subassemblies:
                        logging.debug(f"Skipping already processed net sub-assembly: {sub_part_id}")
                        continue # Skip to the next BOM item

                    # Only process BOM for the quantity that needs to be built
                    if to_build > 0:
                        # Pass 2: Mark this sub-assembly as processed for net calculation
                        if processed_net_subassemblies is not None:
                            processed_net_subassemblies.add(sub_part_id)
                            logging.debug(f"Marking sub-assembly {sub_part_id} as processed for net calculation.")

                        # Recursively process its BOM, but only for the quantity that needs to be built
                        logging.debug(
                            f"Recursively processing BOM for sub-assembly {sub_part_details.get('name')} (ID: {sub_part_id}), To Build Qty: {to_build}"
                        )
                        get_recursive_bom(
                            api,
                            sub_part_id,
                            to_build,  # Only process the quantity that needs to be built
                            required_components,
                            root_input_id,
                            template_only_flags,
                            all_encountered_part_ids,
                            sub_assemblies, # Pass down sub_assemblies tracker
                            include_consumables, # Pass down include_consumables flag
                            bom_consumable_status, # Pass down bom_consumable_status
                            exclude_haip_calculation, # Pass down exclude_haip_calculation flag
                            part_requirements_data, # Pass down part requirements data
                            total_sub_assembly_reqs, # Pass down aggregated requirements
                            processed_net_subassemblies=processed_net_subassemblies, # Pass down the set
                        )
                        # The recursive call modifies bom_consumable_status in place,
                        # so no explicit merging is needed here.
                    else:
                        logging.debug(
                            f"Skipping BOM processing for sub-assembly {sub_part_details.get('name')} (ID: {sub_part_id}) as sufficient stock is available"
                        )
                else: # It's a base component
                    # Get details needed for stock calculation
                    base_in_stock = sub_part_details.get("in_stock", 0.0)
                    base_variant_stock = sub_part_details.get("variant_stock", 0.0)

                    # --- BEGIN DEBUG LOGGING (Keep one instance) ---
                    logging.debug(
                        f"Base Component Check: ID={sub_part_id}, Name='{sub_part_details.get('name')}', "
                        f"AllowVariants={allow_variants}, InStock={base_in_stock}, "
                        f"VariantStock={base_variant_stock}, RawRequired={total_sub_quantity}"
                    )
                    # --- END DEBUG LOGGING ---

                    # Add the gross required quantity directly to the accumulator
                    logging.debug(
                        f"Base component: {sub_part_details.get('name')} (ID: {sub_part_id}), Gross Qty: {total_sub_quantity}, PartConsumable: {is_part_consumable}, BomItemConsumable: {is_bom_item_consumable}"
                    )
                    # Quantity calculation depends on the part's consumable flag and the include_consumables setting
                    if include_consumables or not is_part_consumable:
                        required_components[root_input_id][
                            sub_part_id
                        ] += total_sub_quantity
                    else:
                        logging.debug(f"Ignoring part-consumable base component quantity for {sub_part_id}")
        elif bom_items is None:
            logging.warning(
                f"Could not process BOM for assembly {part_id} due to fetch error."
            )
    else:
        # It's a base component itself
        logging.debug(
            f"Adding base component: {part_details.get('name')} (ID: {part_id}), Quantity: {quantity}"
        )
        # --- HAIP Exclusion Check (for top-level base component) ---
        is_haip_base = False
        if exclude_haip_calculation:
            part_final_data_dict = get_final_part_data(api, (part_id,))
            part_final_data = part_final_data_dict.get(part_id, {})
            is_haip_base = part_final_data.get('is_haip_part', False)
            if is_haip_base:
                 logging.debug(f"Excluding HAIP base part {part_id} ('{part_details.get('name', 'N/A')}') from calculation.")

        if not is_haip_base: # Only add if not excluded
            required_components[root_input_id][part_id] += quantity
    logging.info(f"REC_BOM_DEBUG: Returning from part {part_id}. Current sub_assemblies state: {dict(sub_assemblies)}")

    return bom_consumable_status # Return the updated status dictionary
