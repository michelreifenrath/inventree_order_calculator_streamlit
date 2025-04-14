# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Create data directory for SQLite database
RUN mkdir -p /app/data

# Copy the requirements file into the container at /app
COPY requirements.txt ./

# Install any needed packages specified in requirements.txt
# Use --no-cache-dir to reduce image size
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /app
# This respects the .dockerignore file
COPY . .

# Make port 8501 available to the world outside this container
# This is the default port for Streamlit
EXPOSE 8501

# Define environment variable for Streamlit
# Ensures Streamlit runs in headless mode correctly within Docker
ENV STREAMLIT_SERVER_HEADLESS=true
ENV PYTHONPATH=/app

# Run app.py when the container launches
# Use the array form to avoid shell processing issues
CMD ["streamlit", "run", "src/app.py"]
