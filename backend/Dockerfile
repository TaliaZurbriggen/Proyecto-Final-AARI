# Imagen base: Python 3.12 en su versión liviana
FROM python:3.12-slim

# Carpeta de trabajo dentro del contenedor
WORKDIR /app

# OCR local para páginas escaneadas. El paquete de idioma español evita enviar
# el documento a un servicio externo solo para obtener su texto.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*

# Copiamos primero el archivo de dependencias
COPY requirements.txt .

# Instalamos las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el resto del código del backend
COPY . .

# Puerto en el que va a escuchar la aplicación
EXPOSE 8000

# Comando para arrancar el servidor
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
