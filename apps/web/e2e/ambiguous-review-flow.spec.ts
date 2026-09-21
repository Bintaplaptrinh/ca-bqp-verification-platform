import { test, expect } from '@playwright/test';
import { openReviewQueueAtNewest, signInAs, submitTextQuery, waitForResultState } from './helpers';

// Confirmed against the live backend during development of this suite:
// a unit name of "Phòng nghiệp vụ" alone (no other disambiguating signal)
// resolves AMBIGUOUS / NEED_REVIEW, landing on a real open review. The
// review's payload only carries current_unit_raw, not the subject's name
// (business_fields/person_resolution came back empty for this text-extraction
// path) — so the case_id, captured directly off the real POST response, is
// the reliable way to find this run's own card among many pre-existing ones.
const KNOWN_AMBIGUOUS_TEXT = `Họ và tên: Trần Văn Ambiguous Test
Chức vụ: Chuyên viên
Đơn vị công tác: Phòng nghiệp vụ`;

test('an ambiguous case can be self-assigned and decided from the review queue', async ({ page }) => {
  await signInAs(page, 'REVIEWER');

  const [response] = await Promise.all([
    page.waitForResponse((res) => res.url().includes('/api/v1/cases/text') && res.request().method() === 'POST'),
    submitTextQuery(page, KNOWN_AMBIGUOUS_TEXT),
  ]);
  const { case_id: caseId } = await response.json();
  expect(caseId, 'submitting the text query should return a case_id').toBeTruthy();

  await waitForResultState(page);
  await expect(page.getByText('Chưa có kết luận')).toBeVisible();
  await expect(page.getByText('Thuộc Bộ Công an hoặc Bộ Quốc phòng?')).toHaveCount(0);

  const caseIdFragment = String(caseId).replace(/^case_/i, '').slice(0, 8).toUpperCase();

  await openReviewQueueAtNewest(page);

  const reviewCard = page.locator('div.bg-white.border.border-slate-200.rounded-md.p-4', {
    hasText: `Hồ sơ #${caseIdFragment}`,
  });
  await expect(reviewCard).toBeVisible({ timeout: 15_000 });

  await reviewCard.getByRole('button', { name: 'Nhận xử lý' }).click();
  await expect(reviewCard.getByText('Đang xử lý:')).toBeVisible();

  await reviewCard.getByRole('button', { name: 'Xử lý', exact: true }).click();
  await reviewCard.getByRole('button', { name: 'Chưa xác định' }).click();
  await reviewCard.getByRole('button', { name: 'Ghi quyết định' }).click();

  await expect(reviewCard).not.toBeVisible({ timeout: 15_000 });
});
