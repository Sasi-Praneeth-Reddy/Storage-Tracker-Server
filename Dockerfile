# Use a tiny version of Python to save disk space!
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install packages
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and ONLY the Chromium browser (and its OS dependencies)
# This prevents downloading Firefox/WebKit which saves gigabytes of space.
RUN playwright install chromium --with-deps

# Copy the current directory contents into the container at /app
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Make port 8501 available to the world outside this container
EXPOSE 8501
