import os
import sys
import logging
from collections import defaultdict
from inventree.api import InvenTreeAPI
from inventree.part import Part
from inventree.base import InventreeObject  # Needed for type hinting

# --- Configuration ---
INVENTREE_URL = os.getenv("INVENTREE_URL")
INVENTREE_TOKEN = os.getenv("INVENTREE_TOKEN")

# Define the target assemblies by their specific Part IDs and the quantity required for each
# Found via previous MCP tool usage:
# Blackbird v2: pk 1110
# Blackbullet v2: pk 1400
TARGET_ASSEMBLY_IDS = {
    1110: 2,  # BlackBird_V2
    1400: 2,  # BlackBullet_V2
    1344: 3,
    # Add more assemblies here by ID if needed, e.g., 9999: 5
}

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

# --- Constants ---
OUTPUT_MARKDOWN_FILE = "order_list_blackbird_blackbullet.md"

# --- Caches ---
# Store fetched part details (assembly status, name, stock) and BOM items
part_cache = {}  # {part_id: {'assembly': bool, 'name': str, 'in_stock': float}}
bom_cache = {}  # {part_id: list_of_bom_item_dicts}

# --- Helper Functions ---

# Removed find_part_id function as we are using hardcoded IDs now


def get_part_details_cached(api: InvenTreeAPI, part_id: int) -> dict | None:
    """Gets part details (assembly, name, stock) from cache or API."""
    if part_id in part_cache:
        log.debug(f"Cache hit for part details: {part_id}")
        return part_cache[part_id]

    log.debug(f"Cache miss for part details: {part_id}. Fetching from API.")
    try:
        part = Part(api, pk=part_id)
        if not part or not part.pk:
            log.warning(f"Could not retrieve part details for ID {part_id} from API.")
            part_cache[part_id] = None  # Cache the failure to avoid retries
            return None

        details = {
            "assembly": part.assembly,
            "name": part.name,
            "in_stock": float(
                part._data.get("in_stock", 0) or 0
            ),  # Ensure float, handle None
        }
        part_cache[part_id] = details
        return details
    except Exception as e:
        log.error(f"Error fetching part details for ID {part_id}: {e}")
        part_cache[part_id] = None  # Cache the failure
        return None


def get_bom_items_cached(api: InvenTreeAPI, part_id: int) -> list | None:
    """Gets BOM items for a part ID from cache or API."""
    if part_id in bom_cache:
        log.debug(f"Cache hit for BOM: {part_id}")
        return bom_cache[part_id]

    log.debug(f"Cache miss for BOM: {part_id}. Fetching from API.")
    try:
        # Need part details first to check if it's an assembly
        part_details = get_part_details_cached(api, part_id)
        if not part_details or not part_details["assembly"]:
            log.debug(f"Part {part_id} is not an assembly or details failed. No BOM.")
            bom_cache[part_id] = []  # Cache empty list for non-assemblies
            return []

        part = Part(api, pk=part_id)  # Re-fetch Part object to call method
        bom_items_raw = part.getBomItems()
        if bom_items_raw:
            # Store relevant info (sub_part ID and quantity)
            bom_data = [
                {"sub_part": item.sub_part, "quantity": float(item.quantity)}
                for item in bom_items_raw
            ]
            bom_cache[part_id] = bom_data
            return bom_data
        else:
            log.debug(f"Assembly {part_id} has an empty BOM.")
            bom_cache[part_id] = []  # Cache empty list
            return []
    except Exception as e:
        log.error(f"Error fetching BOM items for part ID {part_id}: {e}")
        bom_cache[part_id] = None  # Cache the failure
        return None


def get_recursive_bom_cached(
    api: InvenTreeAPI,
    part_id: int,
    quantity: float,
    required_components: defaultdict[int, float],
):
    """
    Recursively processes the BOM using cached data, aggregating required base components.
    """
    part_details = get_part_details_cached(api, part_id)
    if not part_details:
        log.warning(f"Skipping part ID {part_id} due to fetch error.")
        return

    if part_details["assembly"]:
        log.debug(
            f"Processing assembly: {part_details['name']} (ID: {part_id}), Quantity: {quantity}"
        )
        bom_items = get_bom_items_cached(api, part_id)
        if bom_items:  # Check if BOM fetch succeeded and is not empty
            for item in bom_items:
                sub_part_id = item["sub_part"]
                sub_quantity_per = item["quantity"]
                total_sub_quantity = quantity * sub_quantity_per
                # Recursively process the sub-part
                get_recursive_bom_cached(
                    api, sub_part_id, total_sub_quantity, required_components
                )
        elif bom_items is None:  # BOM fetch failed
            log.warning(
                f"Could not process BOM for assembly {part_id} due to fetch error."
            )
        # If bom_items is [], it's an empty BOM, do nothing further for this branch
    else:
        # This is a base component
        log.debug(
            f"Adding base component: {part_details['name']} (ID: {part_id}), Quantity: {quantity}"
        )
        required_components[part_id] += quantity


def get_final_part_data(api: InvenTreeAPI, part_ids: list[int]) -> dict[int, dict]:
    """Fetches final data (name, stock) for a list of part IDs in a single batch."""
    final_data = {}
    if not part_ids:
        return final_data

    log.info(
        f"Fetching final details (name, stock) for {len(part_ids)} base components..."
    )
    try:
        parts_details = Part.list(api, pk__in=part_ids)
        if parts_details:
            for part in parts_details:
                stock = part._data.get("in_stock", 0)
                final_data[part.pk] = {
                    "name": part.name,
                    "in_stock": float(stock) if stock is not None else 0.0,
                }
            log.info(f"Successfully fetched batch details for {len(final_data)} parts.")
            # Check if any IDs were missed (shouldn't happen with pk__in if parts exist)
            missed_ids = set(part_ids) - set(final_data.keys())
            if missed_ids:
                log.warning(
                    f"Could not fetch batch details for some part IDs: {missed_ids}"
                )
                # Optionally add fallback logic here if needed, but pk__in should be reliable
                for missed_id in missed_ids:
                    final_data[missed_id] = {
                        "name": f"Unknown (ID: {missed_id})",
                        "in_stock": 0.0,
                    }

        else:
            log.warning(
                "pk__in filter returned no results for final data fetch. This might indicate issues."
            )
            # Provide default unknown data for all requested IDs
            for part_id in part_ids:
                final_data[part_id] = {
                    "name": f"Unknown (ID: {part_id})",
                    "in_stock": 0.0,
                }

    except Exception as e:
        log.error(
            f"Error fetching batch final part data: {e}. Returning defaults.",
            exc_info=True,
        )
        # Provide default unknown data on error
        for part_id in part_ids:
            final_data[part_id] = {"name": f"Unknown (ID: {part_id})", "in_stock": 0.0}

    log.info("Finished fetching final part data.")
    return final_data


def save_results_to_markdown(parts_to_order: list[dict], filename: str):
    """Formats the order list and saves it to a Markdown file."""
    log.info(f"Saving results to Markdown file: {filename}")
    try:
        md_content = []
        md_content.append("# Calculated Parts to Order")
        md_content.append(f"\nBased on target assemblies: `{TARGET_ASSEMBLY_IDS}`\n")

        if not parts_to_order:
            md_content.append("All required components are in stock. No orders needed.")
        else:
            # Create table header
            md_content.append(
                "| PK   | Name                                               | Required | In Stock | To Order |"
            )
            md_content.append(
                "| :--- | :------------------------------------------------- | :------- | :------- | :------- |"
            )
            # Add table rows
            for item in parts_to_order:
                # Format floats for printing
                req_str = f"{item['required']:.3f}".rstrip("0").rstrip(".")
                stock_str = f"{item['in_stock']:.3f}".rstrip("0").rstrip(".")
                order_str = f"{item['to_order']:.3f}".rstrip("0").rstrip(".")
                # Escape pipe characters in names if necessary
                name_escaped = item["name"].replace("|", "\\|")
                md_content.append(
                    f"| {item['pk']:<4} | {name_escaped:<50} | {req_str:<8} | {stock_str:<8} | {order_str:<8} |"
                )

            md_content.append(
                f"\nFound {len(parts_to_order)} components that need ordering."
            )
            md_content.append(
                "\n**Note:** Fractional quantities might need rounding based on purchasing units."
            )

        # Write to file
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(md_content))
        log.info(f"Successfully saved results to {filename}")

    except Exception as e:
        log.error(
            f"Error saving results to Markdown file {filename}: {e}", exc_info=True
        )


# --- Main Script Logic ---


def main():
    log.info("Starting InvenTree Order Calculation Script")

    # Validate configuration
    if not INVENTREE_URL or not INVENTREE_TOKEN:
        log.error(
            "INVENTREE_URL and INVENTREE_TOKEN environment variables must be set."
        )
        sys.exit(1)

    # Connect to InvenTree
    try:
        api = InvenTreeAPI(INVENTREE_URL, token=INVENTREE_TOKEN)
        log.info(f"Connected to InvenTree API version: {api.api_version}")
    except Exception as e:
        log.error(f"Failed to connect to InvenTree API: {e}", exc_info=True)
        sys.exit(1)

    # --- 1. Use Predefined Target Assembly IDs ---
    # We use the TARGET_ASSEMBLY_IDS dictionary defined above
    if not TARGET_ASSEMBLY_IDS:
        log.error("TARGET_ASSEMBLY_IDS dictionary is empty. Exiting.")
        sys.exit(1)
    else:
        log.info(f"Using predefined target assembly IDs: {TARGET_ASSEMBLY_IDS}")

    # --- 2. Calculate Required Base Components (using caching) ---
    required_base_components = defaultdict(float)
    # Clear caches at the start of each run
    part_cache.clear()
    bom_cache.clear()
    log.info("Calculating required components recursively (with caching)...")
    for (
        part_id,
        quantity,
    ) in TARGET_ASSEMBLY_IDS.items():  # Use the ID-based dictionary directly
        log.info(f"Processing target assembly ID: {part_id}, Quantity: {quantity}")
        get_recursive_bom_cached(
            api, part_id, float(quantity), required_base_components
        )

    log.info(f"Total unique base components required: {len(required_base_components)}")
    if not required_base_components:
        log.info("No base components found. Nothing to order.")
        sys.exit(0)

    # --- 3. Get Final Data (Names & Stock) for Base Components ---
    base_component_ids = list(required_base_components.keys())
    final_part_data = get_final_part_data(api, base_component_ids)

    # --- 4. Calculate Order List ---
    parts_to_order = []
    log.info("Calculating final order quantities...")
    for part_id, required_qty in required_base_components.items():
        part_data = final_part_data.get(
            part_id, {"name": f"Unknown (ID: {part_id})", "in_stock": 0.0}
        )
        in_stock = part_data["in_stock"]
        part_name = part_data["name"]
        to_order = required_qty - in_stock
        if to_order > 0:
            parts_to_order.append(
                {
                    "pk": part_id,
                    "name": part_name,
                    "required": round(required_qty, 3),  # Round for display
                    "in_stock": round(in_stock, 3),
                    "to_order": round(to_order, 3),
                }
            )

    # Sort by name for readability
    parts_to_order.sort(key=lambda x: x["name"])

    # --- 5. Print Results ---
    if not parts_to_order:
        log.info("All required components are in stock. No orders needed.")
    else:
        log.info("--- Parts to Order ---")
        # Simple print format
        print(
            f"{'PK':<6} | {'Name':<50} | {'Required':<10} | {'In Stock':<10} | {'To Order':<10}"
        )
        print("-" * 90)
        for item in parts_to_order:
            # Format floats for printing
            req_str = f"{item['required']:.3f}".rstrip("0").rstrip(".")
            stock_str = f"{item['in_stock']:.3f}".rstrip("0").rstrip(".")
            order_str = f"{item['to_order']:.3f}".rstrip("0").rstrip(".")
            print(
                f"{item['pk']:<6} | {item['name']:<50} | {req_str:<10} | {stock_str:<10} | {order_str:<10}"
            )
        print("-" * 90)
        log.info(f"Found {len(parts_to_order)} components that need ordering.")

        # --- 6. Save Results to Markdown ---
        save_results_to_markdown(parts_to_order, OUTPUT_MARKDOWN_FILE)

    log.info("Script finished.")


if __name__ == "__main__":
    # --- Setup Environment Variables (Example - Replace or remove in production) ---
    # You should set these in your environment or use a .env file with python-dotenv
    # Example:
    # os.environ["INVENTREE_URL"] = "YOUR_INVENTREE_INSTANCE_URL"
    # os.environ["INVENTREE_TOKEN"] = "YOUR_INVENTREE_API_TOKEN"
    # ---

    main()
