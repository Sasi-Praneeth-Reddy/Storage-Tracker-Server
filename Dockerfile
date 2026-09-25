# Stage 1: Build React Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Python Backend & Scrapers
FROM python:3.10-slim
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install packages
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and ONLY the Chromium browser (and its OS dependencies)
RUN playwright install chromium --with-deps

# Copy the current directory contents into the container at /app
COPY . .

# Copy compiled frontend from Stage 1
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose ports: 8000 for React+FastAPI (v2), 8501 for Streamlit (v1)
EXPOSE 8000 8501

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
