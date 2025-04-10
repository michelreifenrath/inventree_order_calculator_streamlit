# InvenTree Order Calculator

This project provides an interactive Streamlit web application to calculate the required base components needed to build a set of specified assembly parts, based on Bill of Materials (BOM) data fetched from an InvenTree instance. It determines the quantity of each base part to order by comparing the total required quantity against the current stock level (including parts on pending/placed purchase orders) in InvenTree.

## Features

- Connects securely to a specified InvenTree instance using API credentials stored in a `.env` file.
- Allows users to select target assembly parts from a dropdown menu (populated from a configurable InvenTree category).
- Users can define the desired quantity for each selected assembly part.
- Multiple assembly parts can be added to the calculation list.
- Recursively calculates the total required quantity for each base component based on the BOMs of the target assemblies.
- Fetches current stock levels and quantities on pending/placed purchase orders for base components from InvenTree.
- Option to exclude parts based on specific Suppliers or Manufacturers.
- Displays the final list of parts that need to be ordered, grouped by the initial input assembly, with clear quantity breakdowns.
- Allows downloading the grouped order list (including input assembly information) as a CSV file.
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
  ```dotenv
  INVENTREE_SERVER=https://your-inventree-instance.com
  INVENTREE_API_TOKEN=your_api_token_here
  # Optional: Specify the category ID for the assembly dropdown
  TARGET_ASSEMBLY_CATEGORY_ID=191
  ```

### 4. Install Dependencies

- Create and activate a virtual environment (recommended):
  ```bash
  python -m venv <your_virtual_env_name> # e.g., venv
  # On Windows
  .\<your_virtual_env_name>\Scripts\activate
  # On macOS/Linux
  source <your_virtual_env_name>/bin/activate
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