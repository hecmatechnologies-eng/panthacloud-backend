const express = require('express');
const app = express();

app.get('/api/users', function getUsers(req, res) {
  res.json([]);
});

app.post('/api/users', function createUser(req, res) {
  res.status(201).json({});
});
