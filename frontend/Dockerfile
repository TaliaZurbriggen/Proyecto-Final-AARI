# Imagen base: Node.js en su versión liviana
FROM node:20-alpine

# Carpeta de trabajo dentro del contenedor
WORKDIR /app

# Copiamos primero los archivos de dependencias
COPY package.json package-lock.json ./

# Instalamos las dependencias
RUN npm install

# Copiamos el resto del código del frontend
COPY . .

# Puerto en el que corre Vite por defecto
EXPOSE 5173

# Comando para levantar el servidor de desarrollo
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]