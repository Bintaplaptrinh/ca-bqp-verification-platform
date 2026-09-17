import { test, expect } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';
import { signInAs } from './helpers';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// datasets/samples/04_pdf_digital_valid.pdf — a text-layer PDF (PDF_TEXT
// routing), chosen so this spec exercises the real upload -> parse -> result
// pipeline without depending on OCR model warm-up time.
const SAMPLE_PDF = path.resolve(__dirname, '../../../datasets/samples/04_pdf_digital_valid.pdf');
const SAMPLE_XLSX = path.resolve(__dirname, '../../../datasets/samples/06_key_value_sheet.xlsx');
const SAMPLE_TXT = path.resolve(__dirname, '../../../datasets/samples/01_text_valid.txt');

test('uploading a document runs the real parse pipeline and opens the extraction review', async ({ page }) => {
  await signInAs(page, 'USER');
  await page.getByRole('button', { name: 'Tải tài liệu' }).click();

  const fileInput = page.locator('input[type="file"]').first();
  await fileInput.setInputFiles(SAMPLE_PDF);

  await expect(page.getByText('Kiểm tra thông tin nhận dạng')).toBeVisible({ timeout: 60_000 });
});

test('spreadsheet source is visible as a table inside the review modal', async ({ page }) => {
  await signInAs(page, 'USER');
  await page.getByRole('button', { name: 'Tải tài liệu' }).click();
  await page.locator('input[type="file"]').first().setInputFiles(SAMPLE_XLSX);

  const preview=page.getByTestId('source-table-preview');
  await expect(preview).toBeVisible({ timeout: 60_000 });
  await expect(preview.getByText('Họ và tên')).toBeVisible();
  await expect(preview.getByText('Đỗ Minh Quân')).toBeVisible();
  await expect(preview.getByText('Cục Kỹ thuật')).toBeVisible();
});

test('text source is readable inside the review modal', async ({ page }) => {
  await signInAs(page, 'USER');
  await page.getByRole('button', { name: 'Tải tài liệu' }).click();
  await page.locator('input[type="file"]').first().setInputFiles(SAMPLE_TXT);

  const preview=page.getByTestId('source-text-preview');
  await expect(preview).toBeVisible({ timeout: 60_000 });
  await expect(preview).toContainText('Nguyễn Văn Minh');
  await expect(preview).toContainText('Cục Kỹ thuật');
});
