import os
import logging
from dotenv import load_dotenv
from inventree.api import InvenTreeAPI
from inventree.order import PurchaseOrder

# --- Configuration ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
load_dotenv()  # Load environment variables from .env file

INVENTREE_URL = os.getenv("INVENTREE_URL")
INVENTREE_TOKEN = os.getenv("INVENTREE_TOKEN")

TARGET_PO_REF = "PO-P-000286"  # The specific PO reference to check

PO_STATUS_MAP = {
    10: "Pending",
    20: "In Progress",
    25: "Placed",
    30: "Complete",
    40: "Cancelled",
    50: "Lost",
    60: "Returned",
    70: "On Hold",
}

# --- API Connection ---
if not INVENTREE_URL or not INVENTREE_TOKEN:
    logging.error("INVENTREE_URL and INVENTREE_TOKEN must be set in the .env file.")
    exit(1)

try:
    api = InvenTreeAPI(INVENTREE_URL, token=INVENTREE_TOKEN)
    logging.info(f"Connected to InvenTree API at {INVENTREE_URL}")
except Exception as e:
    logging.error(f"Failed to connect to InvenTree API: {e}", exc_info=True)
    exit(1)

# --- Validation Logic: Find status for specific PO ---
logging.info(f"--- Checking Status for PO Reference: {TARGET_PO_REF} ---")

try:
    logging.info("Fetching ALL Purchase Orders to find the target...")
    # Fetch all POs - might be slow but necessary to bypass potential filter issues
    all_pos = PurchaseOrder.list(api, fields=["pk", "reference", "status"])

    found_po = False
    if all_pos:
        logging.info(
            f"Fetched {len(all_pos)} total POs. Searching for {TARGET_PO_REF}..."
        )
        for po in all_pos:
            ref = po._data.get("reference")
            if ref == TARGET_PO_REF:
                pk = po.pk
                status_code = po._data.get("status")
                status_label = PO_STATUS_MAP.get(
                    status_code, f"Unknown Code ({status_code})"
                )
                logging.info(f"*** FOUND PO ***")
                logging.info(f"  Reference: {ref}")
                logging.info(f"  PK: {pk}")
                logging.info(f"  Status Code: {status_code}")
                logging.info(f"  Status Label: {status_label}")
                found_po = True
                break  # Stop searching once found
        if not found_po:
            logging.warning(
                f"Target PO reference '{TARGET_PO_REF}' not found in the fetched list of {len(all_pos)} POs."
            )
    else:
        logging.warning("Failed to fetch any Purchase Orders from the API.")

except Exception as e:
    logging.error(
        f"An error occurred during the validation process: {e}", exc_info=True
    )

logging.info("\nValidation script (Specific PO Status Check) finished.")
