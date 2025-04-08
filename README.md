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

## Project Structure

```
.
├── .venv/                # Python virtual environment (Gitignored)
├── archive/              # Archived scripts
│   └── calculate_order_needs.py # Original script
├── tests/                # Pytest unit tests
│   └── test_inventree_logic.py # Tests for core logic
├── .env                  # Environment variables (API Credentials - Gitignored)
├── .gitignore            # Git ignore rules
├── .roo/
│   └── rules/
│       └── rules.md      # Roo's rules for this project
├── app.py                # Main Streamlit application file
├── IDEA.md               # Initial idea and plan description
├── inventree_logic.py    # Core logic for InvenTree interaction and BOM calculation
├── PLANNING.md           # Project planning details
├── README.md             # This file
├── requirements.txt      # Python dependencies
└── TASK.md               # Task tracking
```

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd inventree-order-calculator
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure API Credentials:**
    - Create a file named `.env` in the project root directory.
    - Add your InvenTree URL and API Token to the `.env` file:
      ```dotenv
      # .env
      INVENTREE_URL="YOUR_INVENTREE_URL_HERE"
      INVENTREE_TOKEN="YOUR_INVENTREE_TOKEN_HERE"
      ```
    - **Important:** This file is automatically ignored by Git (see `.gitignore`) to prevent accidental credential exposure.

## Usage

1.  **Run the Streamlit application:**
    ```bash
    streamlit run app.py
    ```
2.  Your web browser should automatically open to the application's URL (usually `http://localhost:8501`).
3.  The application will attempt to connect to your InvenTree instance using the credentials loaded from the `.env` file.
4.  Use the sidebar to select the target parts from the dropdown list (populated from Category 191) and enter the quantity required for each. Use the "Add Row" / "Remove Last" buttons to manage the list.
5.  Click the "Teilebedarf berechnen" (Calculate Parts Needed) button.
6.  The results section will show the base components required, their current stock, and the quantity to order, **grouped by the input assembly** with colored headers.
7.  Use the "Download Results (with group info) as CSV" button to save the complete order list, including the input assembly context for each part.
8.  Use the "Berechnung zurücksetzen" (Reset Calculation) button to clear the results and start a new calculation.

## Development

- **Testing:** Run unit tests using `pytest`:
  ```bash
  pytest
  ```
- **Formatting:** Ensure code is formatted with `black`:
  ```bash
  black .
  ```

## Contributing

Please refer to `PLANNING.md` and `TASK.md` for ongoing work and project guidelines. Follow the established code style and testing practices.