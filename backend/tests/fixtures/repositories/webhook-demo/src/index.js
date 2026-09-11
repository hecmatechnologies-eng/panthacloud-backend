const express = require('express');
const app = express();

app.post('/webhooks/stripe', (req, res) => {
  res.status(200).send('received');
});

app.post('/callbacks/github', (req, res) => {
  res.status(200).send('received');
});

app.listen(3000);
