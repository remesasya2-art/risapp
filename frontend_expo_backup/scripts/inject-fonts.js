#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const distDir = path.join(__dirname, '..', 'dist');
const BUILD_VERSION = Date.now(); // Timestamp único para cada build

// CSS para cargar Ionicons desde los assets locales del bundle
const ioniconsCSS = `
<link rel="preconnect" href="https://unpkg.com">
<style>
@font-face {
  font-family: 'Ionicons';
  src: url('/assets/node_modules/@expo/vector-icons/build/vendor/react-native-vector-icons/Fonts/Ionicons.6148e7019854f3bde85b633cb88f3c25.ttf') format('truetype');
  font-weight: normal;
  font-style: normal;
}
</style>
`;

// Meta tags para forzar NO CACHE
const noCacheMeta = `
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<meta name="build-version" content="${BUILD_VERSION}">
`;

// Buscar todos los archivos HTML en dist
function processHtmlFiles(dir) {
  const files = fs.readdirSync(dir);
  
  files.forEach(file => {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    
    if (stat.isDirectory()) {
      processHtmlFiles(filePath);
    } else if (file.endsWith('.html')) {
      let content = fs.readFileSync(filePath, 'utf8');
      
      // Insertar meta tags de no-cache después de <head>
      if (!content.includes('build-version')) {
        content = content.replace('<head>', '<head>' + noCacheMeta);
      }
      
      // Insertar CSS de Ionicons antes de </head>
      if (!content.includes('Ionicons')) {
        if (content.includes('</head>')) {
          content = content.replace('</head>', ioniconsCSS + '</head>');
        }
      }
      
      fs.writeFileSync(filePath, content);
      console.log(`✅ Procesado: ${file}`);
    }
  });
}

console.log('🔧 Inyectando fuentes y meta tags de no-cache...');
console.log(`📦 Build version: ${BUILD_VERSION}`);
processHtmlFiles(distDir);
console.log('✅ Listo!');
