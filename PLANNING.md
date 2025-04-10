# Project Planning: InvenTree Order Calculator

## 1. Architecture & Goals

- **Goal:** Develop an interactive Streamlit web application to calculate required parts based on InvenTree Bill of Materials (BOM).
- **Architecture:**
    - **Frontend:** Streamlit (`app.py`) for UI, input handling, and displaying results.
    - **Backend Logic:** Separate Python module (`inventree_logic.py`) containing core functions for InvenTree API interaction, BOM calculation, and data processing.
    - **Configuration:** Environment variables loaded via `.env` file (using `python-dotenv`) for API credentials.
    - **Data Handling:** Pandas DataFrames for displaying results in tables. Streamlit caching (`@cache_data`, `@cache_resource`) for performance optimization.
- **Key Features:**
    - Secure InvenTree API connection.
    - User interface to input target assembly Part IDs and quantities.
    - Button to trigger the calculation.
    - Display results (parts to order) in a table.
    - Download results as CSV.
    - (Optional) Status/logging display.
    - (Optional) Auto-refresh or manual refresh button.

## 2. Technology Stack

- **Language:** Python 3.x
- **Web Framework:** Streamlit
- **API Interaction:** `inventree` library
- **Data Manipulation:** `pandas` (primarily for Streamlit display)
- **Testing:** `pytest` (to be added)
- **Formatting:** `black` (implied by PEP8 rule)
- **Dependency Management:** `pip` and `requirements.txt`

## 3. File Structure

```
.
├── .dockerignore            # Files to ignore in Docker build context
├── .env.example             # Example environment variables file
├── .gitignore               # Git ignore rules
├── .venv/                   # Python virtual environment (Gitignored)
├── archive/                 # Archived scripts (Gitignored)
├── docu/                    # Documentation files (Gitignored)
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
│   └── ... (other test files)
├── .roo/
│   └── rules/
│       └── rules.md         # Roo AI rules for this project
├── docker-compose.yml       # Docker Compose configuration
├── Dockerfile               # Docker build instructions
├── PLANNING.md              # This file
├── README.md                # Project overview and setup instructions
├── requirements.txt         # Python dependencies
└── TASK.md                  # Task tracking
```

## 4. Style & Conventions

- Follow PEP8.
- Use `black` for formatting.
- Use type hints.
- Write Google-style docstrings for all functions.
- Use `pydantic` for data validation if complex data structures arise (currently not planned but good practice).
- Use relative imports within the project where applicable.
- Add `# Reason:` comments for non-obvious logic.

## 5. Constraints & Considerations

- **Secrets Management:** Ensure API keys are never committed to Git. Use `.env` file and `.gitignore`.
- **Error Handling:** Implement robust error handling for API calls and calculations. Provide informative messages to the user in the Streamlit UI.
- **Performance:** Utilize Streamlit caching effectively to avoid redundant API calls, especially for `get_part_details` and `get_bom_items`. Be mindful of cache invalidation needs if data changes frequently.
- **Scalability:** The recursive BOM calculation could be slow for very deep or complex BOMs. Consider potential optimizations if performance becomes an issue (e.g., iterative approach, limiting recursion depth).
- **Testing:** Add comprehensive unit tests for `inventree_logic.py`. Mock InvenTree API responses for reliable testing.