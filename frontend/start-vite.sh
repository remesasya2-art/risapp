#!/bin/bash
# Start Vite ignoring any additional arguments
cd /app/frontend
exec node_modules/.bin/vite --host 0.0.0.0 --port 3000
