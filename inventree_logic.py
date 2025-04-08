# inventree_logic.py
import os
import sys
import logging
from collections import defaultdict
from typing import List, Dict, Optional, Tuple # Added List, Dict, Optional, Tuple
from inventree.api import InvenTreeAPI
from inventree.part import Part
from streamlit import cache_data, cache_resource  # Streamlit caching importieren

# Configure logging (kann auch in der Streamlit App konfiguriert werden)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

# --- Helper Functions (angepasst für Streamlit Caching) ---


# Cache API connection - hält die Verbindung über Re-Runs offen
@cache_resource
def connect_to_inventree(url, token):
    """Connects to the InvenTree API and returns the API object."""
    log.info("Attempting to connect to InvenTree API...")
    try:
        api = InvenTreeAPI(url, token=token)
        log.info(f"Connected to InvenTree API version: {api.api_version}")
        return api
    except Exception as e:
        log.error(f"Failed to connect to InvenTree API: {e}", exc_info=True)
        # In Streamlit, it's better to raise the exception or return None and handle it in the UI
        return None


# Cache data fetching functions - vermeidet wiederholte API calls für gleiche Inputs
@cache_data(ttl=600)  # Cache results for 10 minutes
def get_part_details(_api: InvenTreeAPI, part_id: int) -> Optional[Dict[str, any]]: # Use Optional/Dict
    """Gets part details (assembly, name, stock) from API."""
    log.debug(f"Fetching part details from API for: {part_id}")
    try:
        # Stelle sicher, dass _api ein gültiges API-Objekt ist
        if not _api:
            log.error("API object is invalid in get_part_details.")
            return None
        part = Part(_api, pk=part_id)
        if not part or not part.pk:
            log.warning(f"Could not retrieve part details for ID {part_id} from API.")
            return None

        details = {
            "assembly": part.assembly,
            "name": part.name,
            "in_stock": float(
                part._data.get("in_stock", 0) or 0
            ),  # Reason: Ensure float type. `get` returns 0 if key missing. `or 0` handles potential None value if key exists but is null.
        }
        return details
    except Exception as e:
        log.error(f"Error fetching part details for ID {part_id}: {e}")
        return None


@cache_data(ttl=600)
def get_bom_items(_api: InvenTreeAPI, part_id: int) -> Optional[List[Dict[str, any]]]: # Use Optional/List/Dict
    """Gets BOM items for a part ID from API."""
    log.debug(f"Fetching BOM from API for: {part_id}")
    try:
        if not _api:
            log.error("API object is invalid in get_bom_items.")
            return None
        # Check if it's an assembly first (using cached detail fetch)
        part_details = get_part_details(_api, part_id)
        if not part_details or not part_details["assembly"]:
            log.debug(f"Part {part_id} is not an assembly or details failed. No BOM.")
            return []  # Return empty list for non-assemblies

        part = Part(_api, pk=part_id)  # Re-fetch Part object to call method
        bom_items_raw = part.getBomItems()
        if bom_items_raw:
            bom_data = [
                {"sub_part": item.sub_part, "quantity": float(item.quantity)}
                for item in bom_items_raw
            ]
            return bom_data
        else:
            log.debug(f"Assembly {part_id} has an empty BOM.")
            return []  # Return empty list
    except Exception as e:
        log.error(f"Error fetching BOM items for part ID {part_id}: {e}")
        return None  # Indicate failure

@cache_data(ttl=600) # Cache results for 10 minutes
def get_parts_in_category(
    _api: InvenTreeAPI, category_id: int
) -> Optional[List[Dict[str, any]]]:
    """
    Fetches parts belonging to a specific category using Part.list().

    Args:
        _api (InvenTreeAPI): The connected InvenTree API object.
        category_id (int): The ID of the category to fetch parts from.

    Returns:
        Optional[List[Dict[str, any]]]: A list of dictionaries, each containing 'pk' and 'name'
                                         for a part in the category, or None if an error occurs.
                                         Returns an empty list if the category is empty or no parts are found.
    """
    log.info(f"Fetching parts from API for category ID: {category_id}")
    try:
        if not _api:
            log.error("API object is invalid in get_parts_in_category.")
            return None

        # Fetch parts using Part.list with category filter and specific fields
        # Reason: Use list() to evaluate the potential generator returned by Part.list immediately.
        # Reason: Specify fields=['pk', 'name'] for efficiency, only fetching required data.
        parts_list = list(
            Part.list(_api, category=category_id, fields=["pk", "name"])
        )

        if not parts_list:
            log.info(f"No parts found in category {category_id}.")
            return [] # Return empty list if category is empty

        # Convert Part objects to simple dictionaries (although fields should limit this)
        result_list = [
            {"pk": part.pk, "name": part.name}
            for part in parts_list if part.pk and part.name # Basic validation
        ]

        log.info(f"Successfully fetched {len(result_list)} parts from category {category_id}.")
        # Sort parts alphabetically by name for consistent dropdown order
        result_list.sort(key=lambda x: x["name"])
        return result_list

    except Exception as e:
        log.error(f"Error fetching parts for category ID {category_id}: {e}", exc_info=True)
        return None # Indicate failure



def get_recursive_bom(
    api: InvenTreeAPI,
    part_id: int,
    quantity: float,
    required_components: defaultdict[int, float],
):
    """
    Recursively processes the BOM using cached data fetching functions.
    NOTE: This function itself is NOT cached with @cache_data because its side effect
          is modifying the 'required_components' dictionary, and caching might lead
          to stale results if underlying BOMs change rapidly between runs within the ttl.
          The caching happens on the lower-level fetch functions.
    """
    part_details = get_part_details(api, part_id)  # Uses cached function
    if not part_details:
        log.warning(f"Skipping part ID {part_id} due to fetch error in recursion.")
        return

    if part_details["assembly"]:
        log.debug(
            f"Processing assembly: {part_details['name']} (ID: {part_id}), Quantity: {quantity}"
        )
        bom_items = get_bom_items(api, part_id)  # Uses cached function
        if bom_items:  # Check if BOM fetch succeeded and is not empty
            for item in bom_items:
                sub_part_id = item["sub_part"]
                sub_quantity_per = item["quantity"]
                total_sub_quantity = quantity * sub_quantity_per
                get_recursive_bom(
                    api, sub_part_id, total_sub_quantity, required_components
                )
        elif bom_items is None:  # BOM fetch failed
            log.warning(
                f"Could not process BOM for assembly {part_id} due to fetch error."
            )
    else:
        log.debug(
            f"Adding base component: {part_details['name']} (ID: {part_id}), Quantity: {quantity}"
        )
        required_components[part_id] += quantity


@cache_data(ttl=600)
def get_final_part_data(_api: InvenTreeAPI, part_ids: Tuple[int, ...]) -> Dict[int, Dict[str, any]]: # Use Tuple/Dict
    """Fetches final data (name, stock) for a tuple of part IDs. Uses tuple for cacheability."""
    final_data = {}
    if not part_ids:
        return final_data
    # Convert tuple back to list for the API call if needed by the library
    part_ids_list = list(part_ids)

    log.info(
        f"Fetching final details (name, stock) for {len(part_ids_list)} base components..."
    )
    try:
        if not _api:
            log.error("API object is invalid in get_final_part_data.")
            # Provide default unknown data on error
            for part_id in part_ids_list:
                final_data[part_id] = {
                    "name": f"Unknown (ID: {part_id})",
                    "in_stock": 0.0,
                }
            return final_data

        # Use list() to potentially evaluate the generator if Part.list returns one
        # Reason: Use `pk__in` for efficient batch fetching of multiple parts by their primary keys. `list()` evaluates the potential generator.
        parts_details = list(Part.list(_api, pk__in=part_ids_list))
        if parts_details:
            for part in parts_details:
                stock = part._data.get("in_stock", 0)
                final_data[part.pk] = {
                    "name": part.name,
                    "in_stock": (
                        float(stock) if stock is not None else 0.0
                    ),  # Reason: Ensure float type and handle potential None value for stock.
                }
            log.info(f"Successfully fetched batch details for {len(final_data)} parts.")
            # Check for missed IDs
            fetched_ids = set(final_data.keys())
            missed_ids = set(part_ids_list) - fetched_ids
            if missed_ids:
                log.warning(
                    f"Could not fetch batch details for some part IDs: {missed_ids}"
                )
                for missed_id in missed_ids:
                    final_data[missed_id] = {
                        "name": f"Unknown (ID: {missed_id})",
                        "in_stock": 0.0,
                    }
        else:
            log.warning("pk__in filter returned no results for final data fetch.")
            for part_id in part_ids_list:
                final_data[part_id] = {
                    "name": f"Unknown (ID: {part_id})",
                    "in_stock": 0.0,
                }

    except Exception as e:
        log.error(
            f"Error fetching batch final part data: {e}. Returning defaults.",
            exc_info=True,
        )
        for part_id in part_ids_list:
            final_data[part_id] = {"name": f"Unknown (ID: {part_id})", "in_stock": 0.0}

    log.info("Finished fetching final part data.")
    return final_data


# --- Main Calculation Function ---
def calculate_required_parts(
    api: InvenTreeAPI, target_assemblies: dict[int, float]
) -> List[Dict[str, any]]: # Use List/Dict
    """
    Calculates the list of parts to order based on target assemblies.
    Returns a list of dictionaries, where each dictionary represents a part to order.
    """
    if not api:
        log.error("Cannot calculate parts: InvenTree API connection is not available.")
        return []  # Return empty list if API failed

    if not target_assemblies:
        log.info("No target assemblies provided.")
        return []

    log.info(f"Calculating required components for targets: {target_assemblies}")
    required_base_components = defaultdict(float)

    # --- Perform Recursive BOM Calculation ---
    for part_id, quantity in target_assemblies.items():
        log.info(f"Processing target assembly ID: {part_id}, Quantity: {quantity}")
        try:
            # Pass only valid IDs (int) and quantities (float)
            get_recursive_bom(
                api, int(part_id), float(quantity), required_base_components
            )
        except ValueError:
            log.error(f"Invalid ID ({part_id}) or Quantity ({quantity}). Skipping.")
            continue
        except Exception as e:
            log.error(f"Error processing assembly {part_id}: {e}", exc_info=True)
            # Decide if you want to stop or continue processing others
            continue  # Continue with the next assembly

    log.info(f"Total unique base components required: {len(required_base_components)}")
    if not required_base_components:
        log.info("No base components found. Nothing to order.")
        return []

    # --- Get Final Data (Names & Stock) ---
    base_component_ids = list(required_base_components.keys())
    # Pass as tuple for cache key compatibility
    final_part_data = get_final_part_data(api, tuple(base_component_ids))

    # --- Calculate Order List ---
    parts_to_order = []
    log.info("Calculating final order quantities...")
    for part_id, required_qty in required_base_components.items():
        part_data = final_part_data.get(part_id)
        if not part_data:  # Handle cases where final data fetch failed for an ID
            log.warning(f"Missing final data for Part ID {part_id}. Using defaults.")
            part_data = {"name": f"Unknown (ID: {part_id})", "in_stock": 0.0}

        in_stock = part_data.get("in_stock", 0.0)  # Default to 0 if missing
        part_name = part_data.get("name", f"Unknown (ID: {part_id})")
        to_order = required_qty - in_stock

        # Reason: Use a small tolerance (0.001) for floating-point comparison instead of `> 0` to avoid issues with tiny precision errors leading to unnecessary orders.
        if to_order > 0.001:
            parts_to_order.append(
                {
                    "pk": part_id,
                    "name": part_name,
                    "required": round(required_qty, 3),
                    "in_stock": round(in_stock, 3),
                    "to_order": round(to_order, 3),
                }
            )

    # Sort by name
    parts_to_order.sort(key=lambda x: x["name"])
    log.info(f"Calculation finished. Parts to order: {len(parts_to_order)}")
    return parts_to_order


# (Die Funktion save_results_to_markdown kann hier bleiben oder in die Streamlit App verschoben werden,
#  wenn du einen Download-Button möchtest)
