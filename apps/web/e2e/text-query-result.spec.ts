import { test, expect } from '@playwright/test';
import { signInAs, submitTextQuery, waitForResultState } from './helpers';

// datasets/samples/01_text_valid.txt — a BQP-scoped fixture confirmed (via a
// direct backend call during development of this suite) to resolve MATCHED/BQP
// against this repo's seeded registry.
const KNOWN_MATCHED_TEXT = `HỒ SƠ KIỂM TRA - DỮ LIỆU GIẢ LẬP

Họ và tên: Nguyễn Văn Minh
CCCD: 001082946357
Chức vụ: Chuyên viên
Nhóm đối tượng: BQP
Đơn vị công tác: Cục Kỹ thuật
Ngày đánh giá: 14/09/2026

Ghi chú: Dữ liệu hoàn toàn giả lập để kiểm thử hệ thống.`;

test('text query resolves to a verified result with real backend data', async ({ page }) => {
  await signInAs(page, 'USER');
  await submitTextQuery(page, KNOWN_MATCHED_TEXT);
  await waitForResultState(page);

  await expect(page.getByText('Đơn vị thuộc phạm vi quản lý')).toBeVisible();
  await expect(page.getByText('Nguyễn Văn Minh', { exact: true })).toBeVisible();
});
