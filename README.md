# RIS App

Aplicación de negocios digitales (risappbr.com).

## Stack

- Backend: FastAPI (Python)
- Frontend: React + Vite
- Base de datos: MongoDB
- Despliegue: Railway

## Estructura

- backend/ — API FastAPI (rutas, servicios y modelos)
- frontend/ — interfaz React/Vite

## Desarrollo

Backend:

```bash
cd backend
pip install -r requirements.txt
uvicorn server:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Notas

Las variables de entorno (conexión a MongoDB, claves de servicios, URL del frontend, etc.) se configuran en el entorno de despliegue. No subir credenciales al repositorio.
