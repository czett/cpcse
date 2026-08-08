FROM python:3.11-slim
WORKDIR /app

# Vollständige System-Abhängigkeiten für RDKit (Rendering, Fonts, Expat)
RUN apt-get update && apt-get install -y \
    libxrender1 \
    libxext6 \
    libexpat1 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
