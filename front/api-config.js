/* The backend serves the frontend on the same origin by default. */
var API_CONFIG = {
  BASE_URL: location.port === '8084' ? location.protocol + '//' + location.hostname + ':3000/api' : '/api',
  TIMEOUT: 30000,
  DEBUG: false
};
