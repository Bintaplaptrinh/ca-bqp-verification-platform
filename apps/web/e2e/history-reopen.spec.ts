import { test, expect } from '@playwright/test';
import { signInAs, submitTextQuery, waitForResultState } from './helpers';

const KNOWN_MATCHED_TEXT = `HỒ SƠ KIỂM TRA - DỮ LIỆU GIẢ LẬP

Họ và tên: Nguyễn Văn Minh
CCCD: 001082946357
Chức vụ: Chuyên viên
Nhóm đối tượng: BQP
Đơn vị công tác: Cục Kỹ thuật
Ngày đánh giá: 14/09/2026

Ghi chú: Dữ liệu hoàn toàn giả lập để kiểm thử hệ thống.`;

// Regression test for the Block 1 fix: "Xem lại" used to replay a
// locally-cached row with subject_group hardcoded to null and eligibility
// hardcoded to []. This spec would have failed against that old behavior —
// it asserts the reopened case actually shows data that only a real
// GET /cases/{id} fetch can produce.
test('reopening a case from history re-fetches real case detail, not a cached placeholder', async ({ page }) => {
  await signInAs(page, 'USER');
  await submitTextQuery(page, KNOWN_MATCHED_TEXT);
  await waitForResultState(page);

  await page.getByRole('button', { name: 'Lịch sử' }).click();
  // HistoryView renders both a mobile card list (`block sm:hidden`) and a
  // desktop table (`hidden sm:block`) for the same rows. Both exist in the
  // DOM regardless of viewport, and an unscoped locator's .first() can grab
  // the CSS-hidden one depending on DOM order — narrow the viewport so only
  // the mobile card list is ever laid out, removing the ambiguity entirely.
  // Desktop regression: ensure the responsive table is not suppressed by
  // a global `.hidden` rule overriding Tailwind's `sm:block` utility.
  const desktopHistoryTable = page.locator('table');
  await expect(desktopHistoryTable).toBeVisible({ timeout: 15_000 });
  await expect(desktopHistoryTable.locator('tbody tr').first()).toBeVisible();

  await page.setViewportSize({ width: 480, height: 900 });
  await expect(page.getByText('Nguyễn Văn Minh').first()).toBeVisible({ timeout: 15_000 });

  await page.getByRole('button', { name: 'Xem lại' }).first().click();
  await waitForResultState(page);

  // The old hardcoded fallback would show 'Không đủ dữ liệu' unconditionally
  // for salary_status and never render any policy conclusion text — assert
  // the reopened view reaches the same real result state instead.
  await expect(page.getByText('Đơn vị thuộc phạm vi quản lý')).toBeVisible();
});
