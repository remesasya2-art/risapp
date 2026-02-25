#!/bin/bash
# Start static server serving the production build
cd /app/frontend

# Build first if dist doesn't exist
if [ ! -d "dist" ]; then
  yarn build
fi

# Serve static files
exec node serve.cjs
