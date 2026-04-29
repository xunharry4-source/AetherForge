const http = require('http');
const server = http.createServer((req, res) => {
  res.writeHead(200);
  res.end('hello');
});
server.listen(5005, '127.0.0.1', () => {
  console.log('Node server bound to port 5005');
  server.close();
});
server.on('error', (e) => {
  console.error('Node server error:', e.message);
});
