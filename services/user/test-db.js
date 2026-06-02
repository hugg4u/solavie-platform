const { Client } = require('pg');

const client = new Client({
  connectionString: "postgresql://solavie_user:solavie_user_password@localhost:5432/solavie_user_db?schema=public"
});

client.connect()
  .then(() => {
    console.log("SUCCESS: Connected successfully to PostgreSQL via TCP!");
    return client.query("SELECT 1");
  })
  .then((res) => {
    console.log("Query result:", res.rows);
    return client.end();
  })
  .catch(err => {
    console.error("FAILURE: Connection error details:", err);
    process.exit(1);
  });
