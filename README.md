# InvenTree Order Calculator

This project provides a Streamlit web application to calculate the required base components needed to build a set of specified assembly parts, based on Bill of Materials (BOM) data fetched from an InvenTree instance. It determines the quantity of each base part to order by comparing the total required quantity against the current stock level in InvenTree.

## Features

- Connects to a specified InvenTree instance using API credentials.
- Allows users to select target parts from a predefined InvenTree category (currently Category 191) using a dropdown menu in the sidebar.
- Users can define the desired quantity for each selected part.
- Multiple parts can be added to the list.
- Recursively calculates the total required quantity for each base component based on the BOMs of the target assemblies.
- Fetches current stock levels for base components from InvenTree.
- Displays the parts that need to be ordered, **grouped by the initial input assembly**, with color-highlighted headers for each group.
- Allows downloading the **grouped order list** (including input assembly information) as a CSV file.
- Uses Streamlit caching to optimize performance by reducing redundant API calls.
- Includes parts currently on Purchase Orders with statuses "Pending" (10), "Placed" (20), or "On Hold" (25) in the stock availability calculation.

## Project Structure

```
.
├── .venv/                   # Python virtual environment (Gitignored)
├── archive/                 # Archived scripts
│   └── calculate_order_needs.py
├── tests/                   # Pytest unit tests
│   ├── test_bom_calculation.py
│   ├── test_order_calculation.py
│   └── test_inventree_logic.py (legacy)
├── .env                     # Environment variables (API Credentials - Gitignored)
├── .gitignore
├── .roo/
│   └── rules/
│       └── rules.md
├── app.py                   # Main Streamlit application
├── bom_calculation.py       # Recursive BOM calculation logic
├── order_calculation.py     # Order quantity calculation logic
├── inventree_api_helpers.py # API helper functions
├── streamlit_ui_elements.py # UI components for Streamlit
├── IDEA.md
├── PLANNING.md
├── README.md
├── requirements.txt
└── TASK.md
```

## Setup

_Fortsetzung unverändert..._