# tests/test_get_requirements.py
"""
Test script to verify the inventree.part.Part.getRequirements() method.

This script connects to an InvenTree instance using credentials from environment
variables, fetches a specific part, calls its getRequirements() method,
and prints the result.
"""

import os
import sys
from dotenv import load_dotenv
from inventree.api import InvenTreeAPI
from inventree.part import Part
from inventree.base import InventreeObject
from requests.exceptions import ConnectionError

# Add src directory to sys.path to allow importing helper modules if needed later
# Although not strictly required by the current task description, it's good practice
# for tests that might evolve to use other parts of the application.
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# --- Configuration ---
PART_ID_TO_TEST = 1879 # Part ID to test getRequirements() on

def main():
    """
    Main function to test getRequirements().
    """
    print("--- Starting test_get_requirements script ---")

    # Load environment variables from .env file
    load_dotenv()

    # Retrieve InvenTree connection details
    inventree_url = os.getenv("INVENTREE_URL")
    inventree_token = os.getenv("INVENTREE_TOKEN")

    if not inventree_url or not inventree_token:
        print("Error: INVENTREE_URL and INVENTREE_TOKEN must be set in environment variables or .env file.")
        sys.exit(1)

    print(f"Connecting to InvenTree at: {inventree_url}")

    try:
        # Instantiate the API
        api = InvenTreeAPI(inventree_url, token=inventree_token)
        print("Successfully connected to InvenTree API.")

        # Fetch the Part object
        print(f"Attempting to retrieve Part with ID: {PART_ID_TO_TEST}")
        # Fetch the Part object using Part.list() which returns a list
        print(f"Attempting to retrieve Part with ID: {PART_ID_TO_TEST} using Part.list()")
        parts_list = Part.list(api, pk=PART_ID_TO_TEST)

        # Check if the list is empty (part not found)
        if not parts_list:
            print(f"Error: Part with ID {PART_ID_TO_TEST} not found.")
            sys.exit(1)

        # Get the part object from the list (assuming ID is unique)
        part = parts_list[0]

        # Proceed with the retrieved part
        print(f"Successfully retrieved Part: '{part.name}' (ID: {part.pk})")
        print(f"Description: {part.description}")

        # Call getRequirements()
        print("\nCalling part.getRequirements()...")
        requirements_data = part.getRequirements()

        # Print the result
        print("\n--- Requirements Data ---")
        if isinstance(requirements_data, dict):
            # Pretty print if it's a dictionary
            import json
            print(json.dumps(requirements_data, indent=4))
        elif isinstance(requirements_data, list) and all(isinstance(item, InventreeObject) for item in requirements_data):
             print(f"Received a list of {len(requirements_data)} InventreeObject(s):")
             for item in requirements_data:
                 print(f"- {item.__class__.__name__} (PK: {getattr(item, 'pk', 'N/A')})") # Basic representation
        else:
            print(requirements_data)
        print("--- End Requirements Data ---")

    except ConnectionError as conn_err:
        print(f"\nError connecting to InvenTree API at {inventree_url}: {conn_err}")
        print("Please check the URL and network connectivity.")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
        # Consider more specific exception handling based on inventree-python library
        # e.g., handling specific API errors if the library raises them.
        sys.exit(1)

    print("\n--- test_get_requirements script finished successfully ---")

if __name__ == "__main__":
    main()