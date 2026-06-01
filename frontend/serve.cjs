const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 3000;
const DIST_DIR = path.join(__dirname, 'dist');

const MIME_TYPES = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.otf': 'font/otf',
};

const server = http.createServer((req, res) => {
  console.log(`${new Date().toISOString()} ${req.method} ${req.url}`);
  
  let filePath = req.url;
  
  // Handle query strings and hash
  filePath = filePath.split('?')[0].split('#')[0];
  
  // Default to index.html for SPA routing
  if (filePath === '/' || !filePath.includes('.')) {
    filePath = '/index.html';
  }
  
  const fullPath = path.join(DIST_DIR, filePath);
  const ext = path.extname(fullPath).toLowerCase();
  
  // Security: prevent path traversal
  if (!fullPath.startsWith(DIST_DIR)) {
    res.writeHead(403);
    res.end('Forbidden');
    return;
  }
  
  fs.readFile(fullPath, (err, data) => {
    if (err) {
      // If file not found and not an asset, serve index.html (SPA routing)
      if (err.code === 'ENOENT') {
        const indexPath = path.join(DIST_DIR, 'index.html');
        fs.readFile(indexPath, (indexErr, indexData) => {
          if (indexErr) {
            res.writeHead(500);
            res.end('Internal Server Error');
            return;
          }
          res.writeHead(200, { 'Content-Type': 'text/html' });
          res.end(indexData);
        });
        return;
      }
      res.writeHead(500);
      res.end('Internal Server Error');
      return;
    }
    
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';
    res.writeHead(200, { 'Content-Type': contentType });
    res.end(data);
  });
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Static server running at http://0.0.0.0:${PORT}`);
  console.log(`Serving files from ${DIST_DIR}`);
});
