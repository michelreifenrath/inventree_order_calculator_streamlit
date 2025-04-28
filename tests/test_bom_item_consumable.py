import os
import logging
from dotenv import load_dotenv
from inventree.api import InvenTreeAPI
from inventree.part import Part

# Set up basic logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s') # Changed level to DEBUG

# Load environment variables from .env file
load_dotenv()

# InvenTree API credentials
INVENTREE_URL = os.getenv("INVENTREE_URL")
INVENTREE_TOKEN = os.getenv("INVENTREE_TOKEN")

# Check if credentials are loaded
if not INVENTREE_URL or not INVENTREE_TOKEN:
    logging.error("InvenTree URL or Token not found in environment variables.")
    exit(1)

# Instantiate the API
try:
    api = InvenTreeAPI(INVENTREE_URL, token=INVENTREE_TOKEN)
    logging.info("Successfully connected to InvenTree API.")
except Exception as e:
    logging.error(f"Failed to connect to InvenTree API: {e}")
    exit(1)

# Define the Assembly Part ID to test
ASSEMBLY_PART_ID = 1511

def test_bom_item_consumable_attribute():
    """
    Tests the presence and value of the 'consumable' attribute on BomItems
    for a specific assembly part.
    """
    try:
        # Retrieve the assembly part
        assembly_part = Part(api, pk=ASSEMBLY_PART_ID)
        if not assembly_part:
            logging.error(f"Assembly Part with ID {ASSEMBLY_PART_ID} not found.")
            return

        logging.info(f"Retrieved assembly part: {assembly_part.name} (ID: {assembly_part.pk})")

        # Fetch its BOM items
        bom_items = assembly_part.getBomItems()

        if bom_items:
            logging.info(f"Found {len(bom_items)} BOM item(s) for Part ID {ASSEMBLY_PART_ID}.")
            for bom_item in bom_items:
                # Try different methods to get sub-part name and PK
                sub_part_name = 'N/A' # Default value
                sub_part_pk = 'N/A' # Default value
                retrieval_method = "None"
                try:
                    # Attempt 1: Direct attribute access (e.g., sub_part_name)
                    sub_part_name = bom_item.sub_part_name
                    # Try to get PK from sub_part if name was found directly
                    if hasattr(bom_item, 'sub_part'):
                        sub_part_pk = bom_item.sub_part
                    retrieval_method = "Direct attribute (sub_part_name)"
                    logging.debug(f"Successfully retrieved sub-part name using direct attribute for BOM item PK: {bom_item.pk}")
                except AttributeError:
                    logging.debug(f"Attribute 'sub_part_name' not found for BOM item PK: {bom_item.pk}. Trying Part lookup via sub_part ID.")
                    try:
                        # Attempt 2: Part lookup using sub_part ID
                        if hasattr(bom_item, 'sub_part') and bom_item.sub_part:
                            sub_part_pk = bom_item.sub_part
                            part_obj = Part(api, pk=sub_part_pk)
                            sub_part_name = part_obj.name
                            retrieval_method = f"Part lookup (ID: {sub_part_pk})"
                            logging.debug(f"Successfully retrieved sub-part name using Part lookup for BOM item PK: {bom_item.pk}")
                        else:
                             logging.warning(f"BOM item PK: {bom_item.pk} has no 'sub_part' attribute or it's empty. Cannot perform Part lookup.")
                             retrieval_method = "Failed - No sub_part ID"
                    except Exception as e_part:
                        logging.error(f"Failed to retrieve sub-part name using Part lookup for BOM item PK: {bom_item.pk}, Sub-Part PK: {sub_part_pk}. Error: {e_part}")
                        retrieval_method = f"Failed - Part lookup error (ID: {sub_part_pk})"
                except Exception as e_main:
                    # Catch any other unexpected errors during name retrieval
                    logging.error(f"An unexpected error occurred retrieving sub-part name for BOM item PK: {bom_item.pk}. Error: {e_main}")
                    retrieval_method = "Failed - Unexpected error"

                # Attempt to access the 'consumable' attribute (as originally intended)
                # getattr is used to safely access the attribute, providing a default if not found
                consumable_flag = getattr(bom_item, 'consumable', 'AttributeNotFound')

                # Log the results including the retrieval method used
                logging.info(
                    f"  - BOM Item PK: {bom_item.pk}, Sub-Part: {sub_part_name} (ID: {sub_part_pk}), "
                    f"Retrieval Method: {retrieval_method}, "
                    f"Consumable Flag: {consumable_flag}"
                )
        else:
            logging.info(f"No BOM items found for Part ID {ASSEMBLY_PART_ID}.")

    except Exception as e:
        logging.error(f"An error occurred while testing Part ID {ASSEMBLY_PART_ID}: {e}")

if __name__ == "__main__":
    logging.info(f"Starting test for Assembly Part ID: {ASSEMBLY_PART_ID}")
    test_bom_item_consumable_attribute()
    logging.info("Test finished.")