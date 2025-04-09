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
- **Style (`app.py`):** Add Type Hints and Google-style Docstrings to functions.
- **Style (All):** Add `# Reason:` comments for non-obvious logic (e.g., float tolerance in `inventree_logic.py`).
- **Testing:** Create unit tests for `inventree_logic.py` in `tests/` (mocking API calls).
- **Modularity:** Decide fate of `calculate_order_needs.py` (archive or delete).
- **Documentation:** Update file structure diagrams in `README.md` and `PLANNING.md` to reflect `.env` usage.
- **Formatting:** Run `black .` on the project.
- **Deployment:** Publish the project to a GitHub repository.
- **Feature:** Handle Part Variants in Stock Calculation (2025-04-09).
## Completed Tasks
- Check if the project fulfills the project rules (2025-04-08).
- (Move completed tasks here)
- **Feature:** Add a "Restart Calculation" button to `app.py` to allow users to clear results and start over (2025-04-08).
- **Feature:** Replace Part ID input with dropdown from Category 191 (all parts) (2025-04-08). Ref: `FEATURE_PLAN_CategoryDropdown.md`
- **Feature:** Sort and group the output list of required parts by their parent input assembly part, with color highlighting. (2025-04-08)
- **Deployment:** Implement the app as a Docker container (`Dockerfile`, `.dockerignore`, `docker-compose.yml`) (2025-04-08).