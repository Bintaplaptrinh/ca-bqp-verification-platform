import { test, expect } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';
import { signInAs } from './helpers';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SAMPLE_XLSX = path.resolve(__dirname, '../../../datasets/samples/05_batch_mixed.xlsx');

test('bulk upload shows validation totals and row-level errors', async ({ page }) => {
  await signInAs(page, 'USER');
  await page.getByRole('button', { name: 'Tải tài liệu' }).click();
  await page.locator('input[type="file"]').first().setInputFiles(SAMPLE_XLSX);

  await expect(page.getByText('NHẬP DANH SÁCH NHIỀU DÒNG')).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText('Tổng số dòng')).toBeVisible();
  await expect(page.getByText('Các dòng cần kiểm tra (4)')).toBeVisible();
  await expect(page.getByText('Thiếu trường bắt buộc: họ và tên')).toBeVisible();
  await expect(page.getByText('Mã cá nhân trùng với dòng 8')).toBeVisible();
  await expect(page.getByText('Danh sách nhận diện (10)')).toBeVisible();
  // Scoped to table cells: the recent-cases panel behind the modal can list
  // the same names from earlier runs.
  await expect(page.getByRole('cell', { name: 'Nguyễn Văn Minh', exact: true })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'Bùi Anh Tuấn', exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Đóng' }).click();
  await page.getByRole('button', { name: 'Đổi tệp' }).click();
  await page.locator('input[type="file"]').first().setInputFiles(SAMPLE_XLSX);
  await expect(page.getByText('Các dòng cần kiểm tra (4)')).toBeVisible({ timeout: 60_000 });
});
