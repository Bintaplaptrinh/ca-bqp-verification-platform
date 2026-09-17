import { test, expect } from '@playwright/test';
import { signInAs } from './helpers';

/**
 * The administrator issues an account from the officer's administrative
 * particulars and receives the generated password once.
 */
test('an administrator issues an account and is shown its password once', async ({ page }) => {
  await signInAs(page, 'ADMIN');

  await page.getByRole('button', { name: 'Quản trị', exact: true }).click();
  await page.getByText('Quản trị tài khoản').click();
  await expect(page.getByRole('heading', { name: 'Quản trị tài khoản' })).toBeVisible();

  // A distinct code per run keeps repeated local runs from colliding on the
  // derived login id.
  const code = `E2E${Date.now().toString().slice(-8)}`;
  await page.getByLabel('Họ và tên *').fill('Phạm Thị Kiểm Thử');
  await page.getByLabel('Mã số cán bộ').fill(code);
  await page.getByLabel('Năm sinh').fill('1992');
  await page.getByLabel('Chức vụ').fill('Chuyên viên');
  await page.getByLabel('Phòng/Ban').fill('Phòng Kiểm thử');
  // The password is emailed, so an address is required.
  await page.getByLabel('Thư điện tử *').fill(`${code.toLowerCase()}@cabqp.local`);

  await page.getByRole('button', { name: 'Cấp tài khoản', exact: true }).click();

  // Delivery succeeded, so the screen confirms where it went and shows no password.
  await expect(page.getByText(/Đã gửi mật khẩu tới/)).toBeVisible({ timeout: 20_000 });
  // The login id is shown in the one-time notice, and the account now appears
  // in the list below it.
  await expect(page.getByRole('code').filter({ hasText: code.toLowerCase() })).toBeVisible();
  await expect(page.getByRole('table').getByText(code.toLowerCase(), { exact: true })).toBeVisible();
  // The display name is not unique across runs; the derived login id is.
});

test('the reviewer preset is applied as permissions, not as a role', async ({ page }) => {
  await signInAs(page, 'ADMIN');
  await page.getByRole('button', { name: 'Quản trị', exact: true }).click();
  await page.getByText('Quản trị tài khoản').click();

  await page.getByPlaceholder('Tìm theo tên, mã số, phòng ban').fill('user');
  await expect(page.getByText('Cán bộ tra cứu').first()).toBeVisible({ timeout: 20_000 });

  // Opening an account's permission editor shows the preset buttons an
  // administrator uses to grant "cán bộ thẩm định".
  await page.getByRole('button', { name: /\d+ quyền \(chỉnh sửa\)/ }).first().click();
  // Scope to the row editor: the create form above carries the same preset buttons.
  const editor = page.getByRole('table');
  await expect(editor.getByRole('button', { name: 'Cán bộ thẩm định', exact: true })).toBeVisible();
  await expect(editor.getByText('Ra quyết định thẩm định')).toBeVisible();
});
