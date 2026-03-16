const axios = require('axios');

async function run() {
  const data = await axios.get('https://api.example.com/data');
  return data;
}

module.exports = { run };
