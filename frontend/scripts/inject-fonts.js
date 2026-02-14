#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const distDir = path.join(__dirname, '..', 'dist');

// CSS para cargar Ionicons desde los assets locales del bundle
// Usamos la ruta relativa a los assets que ya están en dist/
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
      
      // Insertar CSS de Ionicons después de </title> o al inicio de <head>
      if (!content.includes('Ionicons')) {
        if (content.includes('</head>')) {
          content = content.replace('</head>', ioniconsCSS + '</head>');
        }
        fs.writeFileSync(filePath, content);
        console.log(`✅ Procesado: ${file}`);
      }
    }
  });
}

console.log('🔧 Inyectando fuentes de Ionicons en archivos HTML...');
processHtmlFiles(distDir);
console.log('✅ Listo!');
