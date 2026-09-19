import { Page, expect, request } from '@playwright/test';

export type TestRole = 'USER' | 'REVIEWER' | 'ADMIN';

const API = 'http://127.0.0.1:8000/api/v1';

/** The two accounts the seeder delivers (`scripts/seed_accounts.py`). */
const SEEDED = {
  USER: { username: 'user', password: 'user' },
  ADMIN: { username: 'admin', password: 'admin' },
};

/**
 * A "cán bộ thẩm định" account, provisioned the way an administrator would.
 *
 * There is no reviewer account in the delivered seed because reviewing is a
 * permission set an administrator grants, not a role that ships switched on.
 * The specs therefore create one through the real admin API rather than
 * minting a token client-side — there is no such bypass any more, which is the
 * point: nothing the browser holds decides what it may do.
 */
const REVIEWER = { username: 'e2e_reviewer', password: 'e2e-reviewer-pass' };

async function apiLogin(context: any, username: string, password: string): Promise<string> {
  const response = await context.post(`${API}/auth/login`, { data: { username, password } });
  if (!response.ok()) throw new Error(`Login failed for ${username}: ${response.status()}`);
  return (await response.json()).access_token;
}

async function ensureReviewerAccount() {
  const context = await request.newContext();
  try {
    // Already provisioned by an earlier spec in this run?
    try {
      await apiLogin(context, REVIEWER.username, REVIEWER.password);
      return;
    } catch {
      /* fall through and create it */
    }

    const adminToken = await apiLogin(context, SEEDED.ADMIN.username, SEEDED.ADMIN.password);
    const headers = { Authorization: `Bearer ${adminToken}` };

    const catalog = await (await context.get(`${API}/auth/permissions`, { headers })).json();
    const preset: string[] = catalog.presets.REVIEWER;

    const created = await context.post(`${API}/admin/users`, {
      headers,
      data: {
        display_name: 'Cán bộ thẩm định (E2E)',
        username: REVIEWER.username,
        position: 'Cán bộ thẩm định',
        department: 'Phòng Kiểm thử',
        // Required by `UserCreate`: the issued password is mailed there, so the
        // create call is a 422 without it.
        email: `${REVIEWER.username}@cabqp.local`,
        permissions: preset,
      },
    });

    if (created.ok()) {
      // The account exists with a generated password; set the fixed one the
      // specs use by resetting and then changing it as the account itself.
      const initial = (await created.json()).initial_password;
      if (!initial) {
        // By design the API returns the password only when the mail failed —
        // a delivered password is never echoed back. The specs cannot read a
        // mailbox, so provisioning needs mail switched off for the run.
        throw new Error(
          'The issued password was mailed instead of returned, so the E2E reviewer cannot be ' +
            'provisioned. Run the suite with GMAIL_USER/GMAIL_APP_PASSWORD unset.'
        );
      }
      const reviewerToken = await apiLogin(context, REVIEWER.username, initial);
      const changed = await context.post(`${API}/auth/change-password`, {
        headers: { Authorization: `Bearer ${reviewerToken}` },
        data: { current_password: initial, new_password: REVIEWER.password },
      });
      if (!changed.ok()) throw new Error(`Could not set the E2E reviewer password: ${changed.status()}`);
    } else if (created.status() !== 409) {
      throw new Error(`Could not provision the E2E reviewer: ${created.status()}`);
    }

    // Make sure the permissions are the current preset even on a reused account.
    await context.patch(`${API}/admin/users/${REVIEWER.username}`, {
      headers,
      data: { permissions: preset, is_active: true },
    });
  } finally {
    await context.dispose();
  }
}

/** Sign in through the real login form, as a person would. */
export async function signInAs(page: Page, role: TestRole) {
  if (role === 'REVIEWER') await ensureReviewerAccount();
  const credentials = role === 'REVIEWER' ? REVIEWER : SEEDED[role];

  await page.goto('/');
  await page.getByLabel('Tên đăng nhập').fill(credentials.username);
  // Not `{ exact: true }`: each field's <label> wraps its leading icon, and the
  // icons render as Material Symbols ligatures, so the label's text content is
  // "Mật khẩu" followed by the glyph name. Only the login form is on screen
  // here, so a substring match is still unambiguous.
  await page.getByLabel('Mật khẩu').fill(credentials.password);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  // The header only renders once the session resolves.
  await expect(page.getByRole('button', { name: 'Tra cứu' }).first()).toBeVisible({ timeout: 30_000 });
}

/**
 * A second tab on the *same* session, rather than a second sign-in.
 *
 * The backend allows one live session per account (SINGLE_ACTIVE_SESSION), so
 * signing in again as the same person revokes the first tab's session and the
 * first tab starts getting 401s. Two tabs sharing one session is what a person
 * actually does, and it is what the conflict spec needs: identical identity,
 * two independently stale views.
 */
export async function openTabOnSameSession(context: any, page: Page): Promise<Page> {
  const stored = await page.evaluate(() => sessionStorage.getItem('cabqp.session'));
  if (!stored) throw new Error('no session to share: sign in on the first page first');

  const next = await context.newPage();
  // sessionStorage is per-tab and cannot be written before a document exists,
  // so land on the origin first, seed the token, then boot the app.
  await next.goto('/');
  await next.evaluate((value) => sessionStorage.setItem('cabqp.session', value), stored);
  await next.reload();
  await expect(next.getByRole('button', { name: 'Tra cứu' }).first()).toBeVisible({ timeout: 30_000 });
  return next;
}

export async function submitTextQuery(page: Page, text: string) {
  // The entry panel opens in structured-form mode, so the free-text box is
  // hidden until "Tra cứu tự do" is selected.
  await page.getByRole('button', { name: 'Tra cứu tự do', exact: true }).click();

  // The top nav also has a button literally labeled "Tra cứu" (a tab that
  // just calls setCurrentNav('search') and does nothing else) and it sits
  // earlier in DOM order than the real submit button, so a plain text-based
  // locator's .first() grabs the wrong one. Scope to the actual
  // type="submit" button inside the query form instead.
  const textarea = page.locator('textarea[name="queryText"], input[name="queryText"]').first();
  await textarea.fill(text);
  await page.locator('button[type="submit"]', { hasText: 'Tra cứu' }).first().click();
}

/** Fill and submit the structured entry form. */
export async function submitForm(
  page: Page,
  fields: { fullName?: string; identifier?: string; department?: string; position?: string }
) {
  await page.getByRole('button', { name: 'Theo biểu mẫu', exact: true }).click();
  if (fields.fullName !== undefined) await page.locator('input[name="fullName"]').first().fill(fields.fullName);
  if (fields.identifier !== undefined)
    await page.locator('input[name="identifier"]').first().fill(fields.identifier);
  if (fields.position !== undefined) await page.locator('input[name="position"]').first().fill(fields.position);
  if (fields.department !== undefined)
    await page.locator('input[name="department"]').first().fill(fields.department);
  await page.locator('button[type="submit"]', { hasText: 'Tra cứu' }).first().click();
}

export async function waitForResultState(page: Page) {
  const verified = page.getByText('Đơn vị thuộc phạm vi quản lý');
  const ambiguous = page.getByText('Có nhiều kết quả phù hợp');
  const noConclusion = page.getByText('Không có trong dữ liệu quản lý CA/BQP');
  await expect(verified.or(ambiguous).or(noConclusion).first()).toBeVisible({ timeout: 45_000 });
}

/**
 * Open the review queue and page to where the newest review is.
 *
 * `GET /reviews` sorts oldest-first and the queue paginates at 50, so a review
 * created by the current spec lands on the last page — but only once there is
 * more than one page. On a freshly seeded database there is not, and the
 * pagination controls are not rendered at all, so paging is conditional rather
 * than assumed.
 */
export async function openReviewQueueAtNewest(page: Page) {
  await page.getByRole('button', { name: 'Quản trị', exact: true }).click();
  await page.getByText('Hàng đợi đối soát').click();
  await expect(page.getByRole('heading', { name: 'Hàng đợi thẩm định' })).toBeVisible({ timeout: 15_000 });
  // The heading renders before the queue request resolves, and the pagination
  // controls only exist once it has. Reading the page label any earlier finds
  // nothing and silently leaves us on page 1 — which is the wrong end of a
  // queue sorted oldest-first.
  await waitForQueueLoaded(page);

  const pageLabel = page.getByText(/Trang \d+\/\d+/);
  if ((await pageLabel.count()) === 0) return; // single page

  const totalPages = Number((await pageLabel.textContent())!.match(/Trang \d+\/(\d+)/)![1]);
  for (let current = 1; current < totalPages; current += 1) {
    await page.getByRole('button', { name: 'Sau' }).click();
    await expect(page.getByText(`Trang ${current + 1}/${totalPages}`)).toBeVisible({ timeout: 15_000 });
    await waitForQueueLoaded(page);
  }
}

/** Resolves once the review queue has rendered rows (or a genuine empty state). */
async function waitForQueueLoaded(page: Page) {
  const anyCard = page.locator('div.bg-white.border.border-slate-200.rounded-md.p-4').first();
  const emptyState = page.getByText('Không có hồ sơ thẩm định nào ở trạng thái này.');
  await expect(anyCard.or(emptyState).first()).toBeVisible({ timeout: 15_000 });
}
