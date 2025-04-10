# Project Tasks

## Current Task (2025-04-08)
- Create initial project structure for Streamlit App based on `IDEA.md`.
- Refactor `calculate_order_needs.py` logic into `inventree_logic.py`.
- Create Streamlit UI in `app.py`.
- Set up configuration (`.streamlit/secrets.toml`, `.gitignore`, `requirements.txt`).
- Create basic project files (`README.md`, `PLANNING.md`).
- Create `tests/` directory.
- Initialize Git repository and make initial commit.

## Future Tasks / Discovered During Work
- **Feature:** Add options to exclude parts by supplier ("HAIP Solutions GmbH") and/or manufacturer (2025-04-09).
- **Style (`app.py`):** Add Type Hints and Google-style Docstrings to functions.
- **Style (All):** Add `# Reason:` comments for non-obvious logic (e.g., float tolerance in `inventree_logic.py`).
- **Modularity:** Decide fate of `calculate_order_needs.py` (archive or delete).
- **Documentation:** Update file structure diagrams in `README.md` and `PLANNING.md` to reflect `.env` usage.
- **Formatting:** Run `black .` on the project.
- **Deployment:** Publish the project to a GitHub repository.
- **Feature:** Handle Part Variants in Stock Calculation (2025-04-09).
- **Bug Investigation:** Part 1087 not shown as 'on order' despite being on PO PO-P-000287 (Status: In Progress). Likely cause: Data linking issue (Part -> SupplierPart -> POLine) in InvenTree. User to verify links in GUI. (2025-04-10)

## Completed Tasks
- Check if the project fulfills the project rules (2025-04-08).
- **Feature:** Add a "Restart Calculation" button to `app.py` to allow users to clear results and start over (2025-04-08).
- **Feature:** Replace Part ID input with dropdown from Category 191 (all parts) (2025-04-08). Ref: `FEATURE_PLAN_CategoryDropdown.md`
- **Feature:** Sort and group the output list of required parts by their parent input assembly part, with color highlighting. (2025-04-08)
- **Deployment:** Implement the app as a Docker container (`Dockerfile`, `.dockerignore`, `docker-compose.yml`) (2025-04-08).
- **Feature:** Add options to exclude parts by supplier ("HAIP Solutions GmbH") and/or manufacturer (2025-04-09). (Includes fix for supplier fetching logic).
- **Refactoring:** Split `app.py` und `inventree_logic.py` (2025-04-09). Created `streamlit_ui_elements.py` and `inventree_api_helpers.py`.
- **Bugfix:** Supplier exclusion ("HAIP Solutions GmbH") not working / slow (2025-04-09). (Fixed by using `SupplierPart.list(part__in=...)`, chunking API calls).
- **Refactoring:** Further split `inventree_logic.py` into `bom_calculation.py` and `order_calculation.py` to comply with 300-line rule (2025-04-10).
- **Testing:** Added Pytest unit tests for `get_recursive_bom` and `calculate_required_parts` with normal, edge, and failure cases (2025-04-10).
- **Compliance:** Fixed project rule violations (file size, missing tests) (2025-04-10).