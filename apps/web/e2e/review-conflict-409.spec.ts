import { test, expect } from '@playwright/test';
import { openReviewQueueAtNewest, signInAs, submitTextQuery, waitForResultState } from './helpers';

// This spec triggers a real HTTP 409 (stale expected_version), not an
// identity/RBAC conflict: both tabs sign in as the same reviewer account, so
// the two requests are indistinguishable to the server except for the version
// they carry. That is the point — the version-mismatch path does not depend on
// identity, and is exactly reproducible here: open the same review in two
// tabs, decide it in the first, then submit from the second tab's stale form.
const KNOWN_AMBIGUOUS_TEXT = `Họ và tên: Trần Văn Conflict Test
Chức vụ: Chuyên viên
Đơn vị công tác: Phòng nghiệp vụ`;

test('deciding a review with a stale version shows the conflict banner instead of silently erroring', async ({ page, context }) => {
  await signInAs(page, 'REVIEWER');

  const [response] = await Promise.all([
    page.waitForResponse((res) => res.url().includes('/api/v1/cases/text') && res.request().method() === 'POST'),
    submitTextQuery(page, KNOWN_AMBIGUOUS_TEXT),
  ]);
  const { case_id: caseId } = await response.json();
  expect(caseId, 'submitting the text query should return a case_id').toBeTruthy();
  await waitForResultState(page);

  const caseIdFragment = String(caseId).replace(/^case_/i, '').slice(0, 8).toUpperCase();
  const cardSelector = (p: typeof page) =>
    p.locator('div.bg-white.border.border-slate-200.rounded-md.p-4', { hasText: `Hồ sơ #${caseIdFragment}` });

  await openReviewQueueAtNewest(page);
  const card1 = cardSelector(page);
  await expect(card1).toBeVisible({ timeout: 15_000 });

  // sessionStorage (where the dev-login token lives) is per-tab, not shared
  // across a browsing context — page2 needs its own dev-login, not just a
  // new tab navigated to the same app.
  const page2 = await context.newPage();
  await signInAs(page2, 'REVIEWER');
  await openReviewQueueAtNewest(page2);
  const card2 = cardSelector(page2);
  await expect(card2).toBeVisible({ timeout: 15_000 });

  // Tab 1 decides first — this bumps the review's version_no server-side.
  // { exact: true } matters here: "Nhận xử lý" (self-assign) also contains
  // the substring "xử lý", so a non-exact name match resolves to both buttons.
  await card1.getByRole('button', { name: 'Xử lý', exact: true }).click();
  await card1.getByRole('button', { name: 'Chưa xác định' }).click();
  await card1.getByRole('button', { name: 'Ghi quyết định' }).click();
  await expect(card1).not.toBeVisible({ timeout: 15_000 });

  // Tab 2 still holds the pre-decision version in its form state — submitting
  // now must hit the server's optimistic-lock check and surface the conflict
  // banner, not a silent failure or a stale success.
  await card2.getByRole('button', { name: 'Xử lý', exact: true }).click();
  await card2.getByRole('button', { name: 'Chưa đủ thông tin' }).click();
  await card2.getByRole('button', { name: 'Ghi quyết định' }).click();

  await expect(page2.getByText('Hồ sơ đã được người khác cập nhật')).toBeVisible({ timeout: 10_000 });
});
