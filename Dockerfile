# Use the official lightweight Python image
FROM python:3.11-slim-bookworm

# Set locale to avoid potential issues in minimal environments
ENV LANG=C.UTF-8

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    ghostscript \
    qpdf \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-deu \
    tesseract-ocr-chi-sim \
    pngquant \
    unpaper \
    jbig2dec \
    libjbig2dec0 \
    libjpeg62-turbo \
    libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

# Install OCRmyPDF (installs jbig2enc via pip)
RUN pip install --no-cache-dir ocrmypdf

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all other files
COPY . .

# Expose the port Flask will run on
ENV PORT=8080
EXPOSE 8080

# Run the Flask app
CMD ["python", "server.py"]
