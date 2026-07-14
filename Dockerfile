# Use an official Python runtime with Playwright pre-installed
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install playwright browsers (base image has dependencies, this ensures Python bindings match)
RUN playwright install chromium

# Copy the current directory contents into the container at /app
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Make port 8501 available to the world outside this container
EXPOSE 8501
