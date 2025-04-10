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

    Returns:
        None
    """
    # Reason: We collect all part IDs to later fetch details in bulk, improving performance.
    all_encountered_part_ids.add(part_id)
    part_details = get_part_details(api, part_id)
    if not part_details:
        logging.warning(f"Skipping part ID {part_id} due to fetch error in recursion.")
        return

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
                if is_template and not allow_variants:
                    template_only_flags[sub_part_id] = True
                    logging.debug(
                        f"Adding template component (variants disallowed): {sub_part_details.get('name')} (ID: {sub_part_id}), Qty: {total_sub_quantity}"
                    )
                    required_components[root_input_id][
                        sub_part_id
                    ] += total_sub_quantity
                elif is_assembly:
                    # Reason: Recursion for nested assemblies
                    get_recursive_bom(
                        api,
                        sub_part_id,
                        total_sub_quantity,
                        required_components,
                        root_input_id,
                        template_only_flags,
                        all_encountered_part_ids,
                    )
                else:
                    logging.debug(
                        f"Adding base component: {sub_part_details.get('name')} (ID: {sub_part_id}), Qty: {total_sub_quantity}"
                    )
                    required_components[root_input_id][
                        sub_part_id
                    ] += total_sub_quantity
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
