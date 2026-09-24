import { test, expect } from '@playwright/test';
import { signInAs } from './helpers';

/**
 * Navigation reflects permissions. It does not enforce them: the backend suite
 * (`tests/test_local_auth.py`) pins that the same accounts get 403 from the
 * endpoints behind these menus, whatever the browser renders.
 */

test('a plain tra cứu account sees no administration menu', async ({ page }) => {
  await signInAs(page, 'USER');
  await expect(page.getByRole('button', { name: 'Quản trị', exact: true })).not.toBeVisible();
});

test('a cán bộ thẩm định sees the review queue but no registry or account management', async ({ page }) => {
  await signInAs(page, 'REVIEWER');
  const adminMenu = page.getByRole('button', { name: 'Quản trị', exact: true });
  await expect(adminMenu).toBeVisible();
  await adminMenu.click();
  await expect(page.getByText('Hàng đợi đối soát')).toBeVisible();
  await expect(page.getByText('Danh mục đơn vị')).not.toBeVisible();
  await expect(page.getByText('Quản trị tài khoản')).not.toBeVisible();
});

test('the administrator sees the full menu including account management', async ({ page }) => {
  await signInAs(page, 'ADMIN');
  const adminMenu = page.getByRole('button', { name: 'Quản trị', exact: true });
  await expect(adminMenu).toBeVisible();
  await adminMenu.click();
  await expect(page.getByText('Hàng đợi đối soát')).toBeVisible();
  await expect(page.getByText('Danh mục đơn vị')).toBeVisible();
  await expect(page.getByText('Quản trị tài khoản')).toBeVisible();
});
