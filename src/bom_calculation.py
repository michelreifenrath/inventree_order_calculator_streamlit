import logging
from collections import defaultdict
from typing import Optional, Set
from inventree.api import InvenTreeAPI
from src.inventree_api_helpers import get_part_details, get_bom_items # Absolute import


def get_recursive_bom(
    api: InvenTreeAPI,
    part_id: int,
    quantity: float,
    required_components: defaultdict[int, defaultdict[int, float]],
    root_input_id: int,
    template_only_flags: defaultdict[int, bool],
    all_encountered_part_ids: Set[int],
    sub_assemblies: defaultdict[int, defaultdict[int, float]] = None,
    include_consumables: bool = True,  # New parameter
) -> None:
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

    Returns:
        None
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
                total_sub_quantity = quantity * sub_quantity_per
                sub_part_details = get_part_details(api, sub_part_id)
                if not sub_part_details:
                    logging.warning(
                        f"Skipping sub-part ID {sub_part_id} in BOM for {part_id} due to fetch error."
                    )
                    continue
                is_template = sub_part_details.get("is_template", False)
                is_assembly = sub_part_details.get("assembly", False)
                is_consumable = sub_part_details.get("consumable", False) # Check if the sub-part is consumable

                if is_template and not allow_variants:
                    template_only_flags[sub_part_id] = True
                    logging.debug(
                        f"Template component (variants disallowed): {sub_part_details.get('name')} (ID: {sub_part_id}), Qty: {total_sub_quantity}, Consumable: {is_consumable}"
                    )
                    if include_consumables or not is_consumable:
                        required_components[root_input_id][
                            sub_part_id
                        ] += total_sub_quantity
                    else:
                        logging.debug(f"Ignoring consumable template quantity for {sub_part_id}")
                elif is_assembly:
                    # This is a sub-assembly
                    # First, add it to the sub_assemblies dictionary
                    logging.debug(
                        f"Found sub-assembly: {sub_part_details.get('name')} (ID: {sub_part_id}) for root {root_input_id}, Qty: {total_sub_quantity}"
                    )
                    # Add to sub-assemblies tracking
                    sub_assemblies[root_input_id][sub_part_id] += total_sub_quantity

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

                    # Calculate how many need to be built
                    to_build = max(0, total_sub_quantity - available_stock)

                    logging.debug(
                        f"Sub-assembly {sub_part_details.get('name')} (ID: {sub_part_id}): Need {total_sub_quantity}, Available {available_stock}, To Build {to_build}"
                    )

                    # Only process BOM for the quantity that needs to be built
                    if to_build > 0:
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
                            sub_assemblies,
                            include_consumables, # Pass parameter down
                        )
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
                        f"Base component: {sub_part_details.get('name')} (ID: {sub_part_id}), Gross Qty: {total_sub_quantity}, Consumable: {is_consumable}"
                    )
                    if include_consumables or not is_consumable:
                        required_components[root_input_id][
                            sub_part_id
                        ] += total_sub_quantity
                    else:
                        logging.debug(f"Ignoring consumable base component quantity for {sub_part_id}")
        elif bom_items is None:
            logging.warning(
                f"Could not process BOM for assembly {part_id} due to fetch error."
            )
    else:
        # It's a base component itself
        logging.debug(
            f"Adding base component: {part_details.get('name')} (ID: {part_id}), Quantity: {quantity}"
        )
        required_components[root_input_id][part_id] += quantity
