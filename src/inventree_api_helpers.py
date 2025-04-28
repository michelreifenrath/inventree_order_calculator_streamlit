# inventree_api_helpers.py
import logging
from typing import List, Dict, Optional, Tuple
from inventree.api import InvenTreeAPI
from inventree.part import Part

# Import SupplierPart for type hinting if needed, handle potential ImportError later
try:
    from inventree.company import SupplierPart, Company

    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False
    # Initialize logger early to log the warning
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    log = logging.getLogger(__name__)
    log.warning(
        "Could not import SupplierPart/Company related classes. Supplier checks might be limited."
    )

from streamlit import cache_data, cache_resource

# Configure logging (ensure it's configured even if imports fail)
if "log" not in locals():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    log = logging.getLogger(__name__)


# --- Utility Functions ---
def _chunk_list(data: list, size: int):
    """Yield successive n-sized chunks from list."""
    for i in range(0, len(data), size):
        yield data[i : i + size]


# --- API Connection ---
@cache_resource
def connect_to_inventree(url: str, token: str) -> Optional[InvenTreeAPI]:
    """Connects to the InvenTree API and returns the API object."""
    log.info("Attempting to connect to InvenTree API...")
    try:
        api = InvenTreeAPI(url, token=token)
        log.info(f"Connected to InvenTree API version: {api.api_version}")
        return api
    except Exception as e:
        log.error(f"Failed to connect to InvenTree API: {e}", exc_info=True)
        return None


# --- Data Fetching Helpers ---


@cache_data(ttl=600)
def get_part_details(_api: InvenTreeAPI, part_id: int) -> Optional[Dict[str, any]]:
    """Gets part details (assembly, name, stock, template status, variant stock) from API."""
    log.debug(f"Fetching part details from API for: {part_id}")
    try:
        if not _api:
            log.error("API object is invalid in get_part_details.")
            return None
        part = Part(_api, pk=part_id)
        # Check if part object was successfully created and has data
        if not part or not hasattr(part, "_data") or not part._data:
            log.warning(
                f"Could not retrieve valid part details for ID {part_id} from API."
            )
            return None

        details = {
            "assembly": part.assembly,
            "name": part.name,
            "in_stock": float(part._data.get("in_stock", 0) or 0),
            "is_template": bool(part._data.get("is_template", False)),
            "variant_stock": float(part._data.get("variant_stock", 0) or 0),
        }
        return details
    except Exception as e:
        log.error(f"Error fetching part details for ID {part_id}: {e}")
        return None


@cache_data(ttl=600)
def get_bom_items(_api: InvenTreeAPI, part_id: int) -> Optional[List[Dict[str, any]]]:
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
        if not part or not hasattr(part, "_data") or not part._data:
            log.warning(
                f"Could not retrieve valid part object for BOM fetch for ID {part_id}."
            )
            return None  # Indicate failure if part object is invalid

        bom_items_raw = part.getBomItems()
        if bom_items_raw:
            bom_data = [
                {
                    "sub_part": item.sub_part,
                    "quantity": float(item.quantity),
                    "consumable": getattr(item, 'consumable', False), # Added consumable flag
                    "allow_variants": bool(
                        getattr(item, "allow_variants", True)
                    ),  # Assume True if attr missing
                }
                for item in bom_items_raw
            ]
            return bom_data
        else:
            log.debug(f"Assembly {part_id} has an empty BOM.")
            return []  # Return empty list
    except Exception as e:
        log.error(f"Error fetching BOM items for part ID {part_id}: {e}")
        return None  # Indicate failure


@cache_data(ttl=600)
def get_parts_in_category(
    _api: InvenTreeAPI, category_id: int
) -> Optional[List[Dict[str, any]]]:
    """Fetches parts belonging to a specific category using Part.list()."""
    log.info(f"Fetching parts from API for category ID: {category_id}")
    try:
        if not _api:
            log.error("API object is invalid in get_parts_in_category.")
            return None
        # Fetch only pk and name for efficiency
        parts_list = list(Part.list(_api, category=category_id, fields=["pk", "name"]))
        if not parts_list:
            log.info(f"No parts found in category {category_id}.")
            return []
        # Ensure data is in the expected dict format
        result_list = [
            {"pk": part.pk, "name": part.name}
            for part in parts_list
            if part.pk and part.name
        ]
        log.info(
            f"Successfully fetched {len(result_list)} parts from category {category_id}."
        )
        result_list.sort(key=lambda x: x["name"])  # Sort alphabetically
        return result_list
    except Exception as e:
        log.error(
            f"Error fetching parts for category ID {category_id}: {e}", exc_info=True
        )
        return None


@cache_data(ttl=300)  # Shorter TTL as supplier info might change more often?
def get_final_part_data(
    _api: InvenTreeAPI, part_ids: Tuple[int, ...]
) -> Dict[int, Dict[str, any]]:
    """Fetches final data (name, stock, template, manufacturer, suppliers) for a tuple of part IDs."""
    final_data = {}
    if not part_ids:
        return final_data
    part_ids_list = list(part_ids)

    log.info(
        f"Fetching final details (incl. manufacturer, suppliers) for {len(part_ids_list)} base components..."
    )

    # --- Default structure for error cases ---
    def get_default_data(p_id):
        return {
            "name": f"Unknown (ID: {p_id})",
            "in_stock": 0.0,
            "is_template": False,
            "variant_stock": 0.0,
            "manufacturer_name": None,
            "supplier_names": [],  # Default empty list for suppliers
        }

    # --- Fetch Base Part Data (including manufacturer) ---
    part_objects: Dict[int, Part] = {}  # Store Part objects for supplier fetching
    try:
        if not _api:
            log.error("API object is invalid in get_final_part_data.")
            for part_id in part_ids_list:
                final_data[part_id] = get_default_data(part_id)
            return final_data

        # Fetch base fields including manufacturer name
        # Requesting 'pk' ensures we get Part objects back, not just dicts
        parts_details_list = list(
            Part.list(
                _api,
                pk__in=part_ids_list,
                fields=[
                    "pk",
                    "name",
                    "in_stock",
                    "is_template",
                    "variant_stock",
                    "manufacturer_name",
                ],
            )
        )

        if parts_details_list:
            for part in parts_details_list:
                if (
                    not part
                    or not part.pk
                    or not hasattr(part, "_data")
                    or not part._data
                ):
                    log.warning(
                        f"Received invalid part object for ID {part.pk if part else 'N/A'} during batch fetch."
                    )
                    if (
                        part and part.pk and part.pk not in final_data
                    ):  # Add default if not already added by missed_ids
                        final_data[part.pk] = get_default_data(part.pk)
                    continue  # Skip this invalid part object

                part_objects[part.pk] = part  # Store the valid Part object
                stock = part._data.get("in_stock", 0) or 0
                variant_stock = part._data.get("variant_stock", 0) or 0
                is_template = part._data.get("is_template", False)
                manufacturer_name = part._data.get("manufacturer_name")
                final_data[part.pk] = {
                    "name": part.name,
                    "in_stock": float(stock) if stock is not None else 0.0,
                    "is_template": bool(is_template),
                    "variant_stock": float(variant_stock),
                    "manufacturer_name": manufacturer_name,
                    "supplier_names": [],  # Initialize suppliers list
                }
            log.info(f"Successfully fetched base details for {len(final_data)} parts.")

            # Handle parts requested but not found by the API
            fetched_ids = set(final_data.keys())
            missed_ids = set(part_ids_list) - fetched_ids
            if missed_ids:
                log.warning(
                    f"Could not fetch base details for some part IDs: {missed_ids}"
                )
                for missed_id in missed_ids:
                    if missed_id not in final_data:  # Ensure default is added only once
                        final_data[missed_id] = get_default_data(missed_id)
        else:
            log.warning("pk__in filter returned no base part results.")
            for part_id in part_ids_list:
                final_data[part_id] = get_default_data(part_id)

    except Exception as e:
        log.error(
            f"Error fetching batch base part data: {e}. Returning defaults.",
            exc_info=True,
        )
        for part_id in part_ids_list:
            if part_id not in final_data:
                final_data[part_id] = get_default_data(part_id)
            else:  # Ensure defaults are complete even if partially filled before error
                final_data[part_id].setdefault("manufacturer_name", None)
                final_data[part_id].setdefault("supplier_names", [])

    # --- Fetch Supplier Data using Part objects (Corrected Approach) ---
    if (
        IMPORTS_AVAILABLE and part_objects
    ):  # Only proceed if imports worked and we have parts
        part_ids_to_fetch_suppliers = list(part_objects.keys())
        CHUNK_SIZE = 100  # Define a chunk size for API calls
        log.info(
            f"Batch fetching supplier information for {len(part_ids_to_fetch_suppliers)} parts in chunks of {CHUNK_SIZE}..."
        )

        supplier_parts_map = {}  # {part_id: [SupplierPart objects]}
        all_supplier_pks = set()
        supplier_part_fetch_error = False
        total_sps_fetched = 0

        try:
            # Fetch all relevant SupplierParts in chunks
            for id_chunk in _chunk_list(part_ids_to_fetch_suppliers, CHUNK_SIZE):
                log.debug(
                    f"Fetching SupplierParts for chunk of {len(id_chunk)} part IDs..."
                )
                chunk_supplier_parts = SupplierPart.list(
                    _api, part__in=id_chunk, fields=["pk", "part", "supplier", "SKU"]
                )
                if chunk_supplier_parts:
                    total_sps_fetched += len(chunk_supplier_parts)
                    for sp in chunk_supplier_parts:
                        original_part_id = sp.part  # Get the original Part PK
                        if original_part_id not in supplier_parts_map:
                            supplier_parts_map[original_part_id] = []
                        supplier_parts_map[original_part_id].append(sp)
                        if sp.supplier:
                            all_supplier_pks.add(
                                sp.supplier
                            )  # Collect unique Company PKs
                # Add a small delay or check API rate limits if needed, though unlikely for internal server

            if total_sps_fetched > 0:
                log.info(
                    f"Fetched a total of {total_sps_fetched} SupplierPart links across all chunks."
                )
            else:
                log.info(
                    "No SupplierPart links found for the requested parts across all chunks."
                )

        except Exception as e:
            log.error(f"Error during chunked SupplierPart fetch: {e}", exc_info=True)
            supplier_part_fetch_error = True  # Flag error to skip company fetch

        # Fetch Company details for all unique suppliers found
        company_pk_to_name = {}
        if all_supplier_pks and not supplier_part_fetch_error:
            log.info(
                f"Batch fetching names for {len(all_supplier_pks)} unique suppliers in chunks of {CHUNK_SIZE}..."
            )
            supplier_pks_list = list(all_supplier_pks)
            try:
                # Fetch Company names in chunks
                for pk_chunk in _chunk_list(supplier_pks_list, CHUNK_SIZE):
                    log.debug(
                        f"Fetching Company names for chunk of {len(pk_chunk)} PKs..."
                    )
                    chunk_companies = Company.list(
                        _api, pk__in=pk_chunk, fields=["pk", "name"]
                    )
                    if chunk_companies:
                        for comp in chunk_companies:
                            if comp and comp.pk and comp.name:
                                company_pk_to_name[comp.pk] = comp.name
                log.info(
                    f"Fetched names for {len(company_pk_to_name)} suppliers across all chunks."
                )
            except Exception as e:
                log.error(
                    f"Error during chunked Company name fetch: {e}", exc_info=True
                )
                # Proceed with potentially incomplete company names if this fails

        # Map supplier names back to the final_data structure
        log.info("Mapping supplier names back to parts...")
        for part_id in part_ids_to_fetch_suppliers:
            names = set()
            if part_id in supplier_parts_map:
                for sp in supplier_parts_map[part_id]:
                    supplier_pk = sp.supplier
                    supplier_name = company_pk_to_name.get(supplier_pk)
                    if supplier_name:
                        names.add(supplier_name.strip())
                        log.debug(
                            f"Part ID {part_id}: Mapped supplier '{supplier_name}' via SupplierPart PK {sp.pk}"
                        )
                    elif supplier_pk:
                        log.debug(
                            f"Part ID {part_id}: SupplierPart PK {sp.pk} linked to Company PK {supplier_pk}, but name not found in batch result."
                        )
                    # else: No supplier PK linked to this SP

            # Update the final_data dict for this part_id, ensuring it exists
            if part_id in final_data:
                final_data[part_id]["supplier_names"] = sorted(list(names))
            else:
                # This case should ideally not happen if part_objects was populated correctly
                log.warning(
                    f"Part ID {part_id} was in fetch list but not in final_data. Setting default supplier names."
                )
                final_data[part_id] = get_default_data(
                    part_id
                )  # Add default if missing
                final_data[part_id]["supplier_names"] = sorted(list(names))

        log.info("Finished mapping supplier names.")

    elif not IMPORTS_AVAILABLE:
        log.warning(
            "Skipping supplier info fetch because necessary classes could not be imported."
        )
    elif not part_objects:
        log.info("Skipping supplier info fetch because no valid base parts were found.")

    log.info("Finished fetching final part data.")
    return final_data
