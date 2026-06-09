import http from 'k6/http';
import { check } from 'k6';

// 1. Rate-based load testing configuration to prevent CPU starvation on local machine
export const options = {
  scenarios: {
    login_stress: {
      executor: 'constant-arrival-rate',
      rate: 100,              // 100 login requests per second
      timeUnit: '1s',
      duration: '10s',        // Total 10 seconds (1000 logins total)
      preAllocatedVUs: 100,   // Start with 100 virtual users
      maxVUs: 500,            // Scale up to 500 VUs if needed to maintain rate
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<500'],  // 95% of login requests must complete under 500ms
    http_req_failed: ['rate<0.01'],    // Failure rate should be less than 1%
  },
};

// 2. Main virtual user execution loop - performs login requests to Keycloak
export default function () {
  const loginUrl = 'http://solavie-keycloak:8080/realms/solavie/protocol/openid-connect/token';
  const payload = {
    client_id: 'dashboard',
    username: 'loadtest-user',
    password: 'LoadtestPassword123!',
    grant_type: 'password',
    scope: 'openid email profile organization:*',
  };

  const params = {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  };

  // Perform the login POST request
  const res = http.post(loginUrl, payload, params);

  // Check if authentication succeeded
  check(res, {
    'status is 200': (r) => r.status === 200,
    'has access token': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body && body.access_token !== undefined;
      } catch (e) {
        return false;
      }
    }
  });
}
