#!/bin/bash
# Start Vite server, ignoring any expo arguments
cd /app/frontend
exec node expo-shim.cjs
