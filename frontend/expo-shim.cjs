#!/usr/bin/env node
// This script intercepts expo commands and runs vite instead
const { spawn } = require('child_process');
const path = require('path');

console.log('Starting Vite server (intercepted expo command)...');

const viteBin = path.join(__dirname, 'node_modules', '.bin', 'vite');
const vite = spawn(viteBin, ['--host', '0.0.0.0', '--port', '3000'], {
  cwd: __dirname,
  stdio: 'inherit',
  env: process.env
});

vite.on('error', (err) => {
  console.error('Failed to start Vite:', err);
  process.exit(1);
});

vite.on('exit', (code) => {
  process.exit(code || 0);
});

// Handle termination signals
process.on('SIGTERM', () => vite.kill('SIGTERM'));
process.on('SIGINT', () => vite.kill('SIGINT'));
