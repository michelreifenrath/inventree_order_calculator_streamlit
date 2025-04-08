# InvenTree Order Calculator

This project provides a Streamlit web application to calculate the required base components needed to build a set of specified assembly parts, based on Bill of Materials (BOM) data fetched from an InvenTree instance. It determines the quantity of each base part to order by comparing the total required quantity against the current stock level in InvenTree.

## Features

- Connects to a specified InvenTree instance using API credentials.
- Allows users to define a list of target assembly parts and their desired quantities via the web interface.
- Recursively calculates the total required quantity for each base component based on the BOMs of the target assemblies.
- Fetches current stock levels for base components from InvenTree.
- Displays a table listing the parts that need to be ordered (required quantity > stock quantity).
- Allows downloading the order list as a CSV file.
- Uses Streamlit caching to optimize performance by reducing redundant API calls.

## Project Structure

```
.
├── .streamlit/
│   └── secrets.toml      # API Credentials (Gitignored)
├── tests/                # Pytest unit tests
│   └── test_inventree_logic.py # Tests for core logic (to be created)
├── .gitignore            # Git ignore rules
├── .roo/
│   └── rules/
│       └── rules.md      # Roo's rules for this project
├── app.py                # Main Streamlit application file
├── calculate_order_needs.py # Original script (will likely be removed/archived later)
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
    - Create a directory named `.streamlit` in the project root.
    - Inside `.streamlit`, create a file named `secrets.toml`.
    - Add your InvenTree URL and API Token to `secrets.toml`:
      ```toml
      # .streamlit/secrets.toml
      INVENTREE_URL = "YOUR_INVENTREE_URL_HERE"
      INVENTREE_TOKEN = "YOUR_INVENTREE_TOKEN_HERE"
      ```
    - **Important:** This file is automatically ignored by Git (see `.gitignore`) to prevent accidental credential exposure.

## Usage

1.  **Run the Streamlit application:**
    ```bash
    streamlit run app.py
    ```
2.  Your web browser should automatically open to the application's URL (usually `http://localhost:8501`).
3.  The application will attempt to connect to your InvenTree instance using the credentials from `secrets.toml`.
4.  Use the sidebar to define the target assembly Part IDs and the quantity required for each.
5.  Click the "Calculate Parts Needed" button.
6.  The results table will show the base components required, their current stock, and the quantity to order.
7.  Use the "Download Results as CSV" button to save the order list.

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