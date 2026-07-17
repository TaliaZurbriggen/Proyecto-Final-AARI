# Imagen base: Python 3.12 en su versión liviana
FROM python:3.12-slim

# Carpeta de trabajo dentro del contenedor
WORKDIR /app

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