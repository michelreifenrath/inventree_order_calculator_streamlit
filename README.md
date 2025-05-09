# InvenTree Order Calculator

This project provides an interactive Streamlit web application to calculate the required base components and sub-assemblies needed to build a set of specified top-level assembly parts, based on Bill of Materials (BOM) data fetched from an InvenTree instance. It determines the quantity of each base part to order and each sub-assembly to build by comparing the total required quantity against the current *effective* stock level (considering existing stock and quantities already allocated for other orders/builds) in InvenTree.

## Features

- Connects securely to a specified InvenTree instance using API credentials stored in a `.env` file.
- Allows users to select target assembly parts from a dropdown menu (populated from a configurable InvenTree category).
- Users can define the desired quantity for each selected assembly part.
- Multiple assembly parts can be added to the calculation list.
- Recursively calculates the total required quantity for each base component and intermediate sub-assembly based on the BOMs of the target assemblies.
- **Calculates and displays required sub-assemblies**, showing:
    - Total quantity needed across all target assemblies.
    - Current stock on hand.
    - Quantity already allocated/required for other orders/builds (fetched from InvenTree).
    - Effective available stock (`Verfügbar` = Stock - Required for Order).
    - Net quantity that needs to be built (`Zu bauen` = Total Needed - Verfügbar).
- **Calculates net base component requirements** by considering the effective available stock of intermediate sub-assemblies, preventing over-ordering of base parts.
- **Correctly handles shared sub-assemblies** by aggregating their total requirement across all parent assemblies before calculating build needs and component requirements.
- Fetches current stock levels and quantities on pending/placed purchase orders for base components from InvenTree.
- Option to exclude parts based on specific Suppliers or Manufacturers (display filter).
- Displays the final list of base parts that need to be ordered and sub-assemblies to be built.
- Allows downloading the order lists (base parts and sub-assemblies) as CSV files.
- Uses Streamlit caching (`@st.cache_data`, `@st.cache_resource`) to optimize performance by reducing redundant API calls.
- Includes a "Restart Calculation" button to clear results and start over.
- Dockerized for easy deployment and consistent environment (`Dockerfile`, `docker-compose.yml`).

## Project Structure

```
.
├── .dockerignore            # Files to ignore in Docker build context
├── .env.example             # Example environment variables file
├── .gitignore               # Git ignore rules
├── src/                     # Core application source code
│   ├── app.py                   # Main Streamlit application entrypoint
│   ├── bom_calculation.py       # Logic for recursive BOM calculation
│   ├── database_helpers.py      # Helper functions for local DB (saving/loading)
│   ├── inventree_api_helpers.py # Helper functions for InvenTree API interaction
│   ├── inventree_logic.py       # Core logic coordination (legacy/refactored)
│   ├── order_calculation.py     # Logic for calculating required order quantities
│   └── streamlit_ui_elements.py # Reusable Streamlit UI components
├── tests/                   # Pytest unit tests
│   ├── test_bom_calculation.py
│   ├── test_order_calculation.py
│   ├── test_inventree_po.py     # (Potentially temporary/utility)
│   └── validate_po_logic.py   # (Potentially temporary/utility)
├── docker-compose.yml       # Docker Compose configuration
├── Dockerfile               # Docker build instructions
├── PLANNING.md              # Project architecture and planning notes
├── README.md                # This file
├── requirements.txt         # Python dependencies
└── TASK.md                  # Task tracking for development
```

## Setup and Usage

### 1. Prerequisites

- Python 3.9+
- Docker and Docker Compose (Optional, for containerized deployment)
- Access to an InvenTree instance with API enabled.

### 2. Clone the Repository

```bash
git clone <your-repository-url>
cd inventree-order-calculator
```

### 3. Environment Variables

- Copy the example environment file:
  ```bash
  cp .env.example .env
  ```
- Edit the `.env` file with your InvenTree URL and API Token:
  ```dotenv
  INVENTREE_URL="https://your-inventree-instance.com"
  INVENTREE_TOKEN="your_api_token_here"
  # Optional: Specify the category ID for the assembly dropdown
  # TARGET_ASSEMBLY_CATEGORY_ID=191
  ```

### 4. Install Dependencies

- Create and activate a virtual environment (recommended):
  ```bash
  python -m venv .venv # Create .venv
  # On Windows
  .\.venv\Scripts\activate
  # On macOS/Linux
  source .venv/bin/activate
  ```
- Install the required Python packages:
  ```bash
  pip install -r requirements.txt
  ```

### 5. Running the Application

#### Option A: Locally with Streamlit

```bash
streamlit run src/app.py
```
The application should open automatically in your web browser.

#### Option B: Using Docker Compose

```bash
docker-compose up --build
```
Access the application at `http://localhost:8501` in your web browser.

## Running Tests

Ensure you have installed the development dependencies (including `pytest`).

```bash
pytest tests/
```

This will discover and run all unit tests in the `tests` directory.