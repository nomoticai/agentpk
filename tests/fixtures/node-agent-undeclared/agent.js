const axios = require('axios');

async function run() {
  const data = await axios.get('https://api.example.com/data');
  // Undeclared write operation
  await axios.post('https://api.example.com/write', { data: 'secret' });
  return data;
}

module.exports = { run };
