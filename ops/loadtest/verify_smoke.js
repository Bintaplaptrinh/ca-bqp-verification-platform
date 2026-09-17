import http from 'k6/http';
import { check, sleep } from 'k6';

// Config is entirely env-var driven — no target host, RPS, or duration is
// baked into the script, per this project's no-hardcoded-values convention.
// Defaults describe a light smoke load, not a claimed production capacity
// number; tune VUS/DURATION against real traffic before treating any result
// here as a capacity guarantee.
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const AUTH_HEADER = __ENV.AUTH_HEADER || 'Bearer smoke-test';
const VUS = Number(__ENV.VUS || 5);
const DURATION = __ENV.DURATION || '30s';

export const options = {
  vus: VUS,
  duration: DURATION,
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(95)<3000'],
  },
};

const headers = { 'Content-Type': 'application/json', Authorization: AUTH_HEADER };

export default function () {
  const lookupRes = http.post(
    `${BASE_URL}/api/v1/lookup/unit`,
    JSON.stringify({ unit_name: 'Cong an' }),
    { headers }
  );
  check(lookupRes, { 'lookup/unit status 200': (r) => r.status === 200 });

  const textRes = http.post(
    `${BASE_URL}/api/v1/cases/text`,
    JSON.stringify({ text: 'Ho va ten: K6 Smoke Test\nDon vi cong tac: Cuc Ky thuat' }),
    { headers: { ...headers, 'Idempotency-Key': `k6-${__VU}-${__ITER}-${Date.now()}` } }
  );
  check(textRes, { 'cases/text status 200': (r) => r.status === 200 });

  if (textRes.status === 200) {
    const caseId = JSON.parse(textRes.body).case_id;
    if (caseId) {
      const getRes = http.get(`${BASE_URL}/api/v1/cases/${caseId}`, { headers });
      check(getRes, { 'cases/{id} status 200': (r) => r.status === 200 });
    }
  }

  sleep(1);
}
