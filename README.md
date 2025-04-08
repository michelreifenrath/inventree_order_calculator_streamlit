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

## Running with Docker

You can build and run this application using Docker and Docker Compose. Make sure you have both installed.

**Method 1: Using Docker Compose (Recommended)**

This is the easiest way to run the application with Docker.

1.  **Ensure `.env` file exists:** Make sure you have created the `.env` file in the project root directory with your InvenTree credentials as described in the [Setup](#setup) section.
2.  **Start the application:** Navigate to the project's root directory in your terminal and run:
    ```bash
    docker-compose up --build
    ```
    - `docker-compose up`: Starts the services defined in `docker-compose.yml`.
    - `--build`: Builds the Docker image before starting the container (necessary the first time or if you change the code/Dockerfile).
3.  **Access the application:** Open your web browser and go to `http://localhost:8501`.
4.  **Stop the application:** Press `Ctrl+C` in the terminal where `docker-compose up` is running, or run the following command from another terminal in the same directory:
    ```bash
    docker-compose down
    ```

5.  **Updating the Application:**
    When you want to update the application with the latest code changes from your Git repository:
    a.  Pull the latest changes into your local project directory:
        ```bash
        git pull origin master # Or 'main' depending on your branch name
        ```
    b.  Rebuild the Docker image and restart the container with the new code:
        ```bash
        docker-compose up --build -d # The '-d' runs it in detached mode (background)
        ```
    ```

**Method 2: Using Docker commands directly**

1.  **Build the Docker image:**
    Navigate to the project's root directory and run:
    ```bash
    docker build -t inventree-order-calculator .
    ```

2.  **Run the Docker container:**
    You need to pass your InvenTree credentials (from the `.env` file) and map the Streamlit port (8501).
    ```bash
    # Make sure your .env file exists in the current directory
    docker run --rm -p 8501:8501 --env-file .env inventree-order-calculator
    ```
    - `--rm`: Automatically removes the container when it exits.
    - `-p 8501:8501`: Maps port 8501 on your host machine to port 8501 inside the container.
    - `--env-file .env`: Loads environment variables from your local `.env` file into the container. **Ensure your `.env` file is present in the directory where you run this command.**

3.  Access the application in your browser at `http://localhost:8501`.

## Development

- **Testing:** Run unit tests using `pytest`:
  ```bash
  pytest
  ```
- **Formatting:** Ensure code is formatted with `black`:
  ```bash
  black .
  ```
## Publishing to GitHub

To publish this project to a GitHub repository:

1.  **Create a new repository on GitHub:** Go to [GitHub.com](https://github.com) and create a new, empty repository. Do *not* initialize it with a README, .gitignore, or license.
2.  **Commit your local changes:** Make sure all your desired files are added and committed locally. If you haven't committed the Docker changes yet:
    ```bash
    git add .
    git commit -m "feat: Add Docker support with Dockerfile and Docker Compose"
    ```
3.  **Link your local repository to GitHub:** Replace `<YOUR_GITHUB_REPO_URL>` with the URL provided by GitHub for your new repository (usually ends in `.git`).
    ```bash
    git remote add origin <YOUR_GITHUB_REPO_URL>
    ```
4.  **Push your code to GitHub:** Push your local `master` (or `main`) branch to the remote repository.
    ```bash
    git push -u origin master # Or 'main'
    ```

## Contributing

Please refer to `PLANNING.md` and `TASK.md` for ongoing work and project guidelines. Follow the established code style and testing practices.
Please refer to `PLANNING.md` and `TASK.md` for ongoing work and project guidelines. Follow the established code style and testing practices.