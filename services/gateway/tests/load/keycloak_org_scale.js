import http from 'k6/http';
import { check, sleep } from 'k6';

// 1. Setup function runs once to authenticate against Keycloak and retrieve the token
export function setup() {
  const loginUrl = 'http://solavie-keycloak:8080/realms/solavie/protocol/openid-connect/token';
  const payload = {
    client_id: 'dashboard',
    username: 'loadtest-user',
    password: 'LoadtestPassword123!',
    grant_type: 'password',
    scope: 'openid email profile ai-core',
  };

  const params = {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  };

  console.log(`Authenticating loadtest-user against ${loginUrl}...`);
  const response = http.post(loginUrl, payload, params);
  
  if (response.status !== 200) {
    throw new Error(`Failed to login to Keycloak: ${response.status} - ${response.body}`);
  }

  const token = JSON.parse(response.body).access_token;
  console.log('Successfully retrieved access token for load test.');
  return { token: token };
}

// 2. Load testing stages and thresholds configuration
export const options = {
  stages: [
    { duration: '5s', target: 200 },   // Ramp-up to 200 virtual users
    { duration: '10s', target: 1000 }, // Ramp-up to 1000 virtual users
    { duration: '10s', target: 1000 }, // Hold 1000 virtual users
    { duration: '5s', target: 0 },     // Ramp-down to 0
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],  // 95% of requests must complete under 500ms
    http_req_failed: ['rate<0.01'],    // Failure rate should be less than 1%
  },
};

// 3. Main virtual user execution loop
export default function (data) {
  // Call mock-completions endpoint to trigger dynamic-policy plugin resolution and direct 200 mock response
  const url = 'http://solavie-gateway:8000/api/v1/mock-completions';
  
  // Randomly distribute requests among the 500 seeded tenants
  const tenantIndex = Math.floor(Math.random() * 500);
  const tenantId = `tenant-loadtest-${tenantIndex}`;

  const params = {
    headers: {
      'Authorization': `Bearer ${data.token}`,
      'X-Tenant-ID': tenantId,
    },
  };

  const res = http.get(url, params);

  // Verify that the gateway processed the request successfully:
  // - 200 OK is expected from the mock API response directly from Kong
  // - There should be NO 401, 403, or 503 errors
  check(res, {
    'status is 200': (r) => r.status === 200,
  });

  // Small pacing delay to avoid pinning CPU locally
  sleep(0.05);
}
