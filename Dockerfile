# Use the official lightweight Python image
FROM python:3.10-slim

# Install poppler so pdfinfo is available
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all other files
COPY . .

# Expose the port Flask will run on
ENV PORT=5000
EXPOSE 5000

# Run the Flask app
CMD ["python", "server.py"]
