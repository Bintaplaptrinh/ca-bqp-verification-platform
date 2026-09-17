# Bộ test đầu vào - CA/BQP Verification Platform

> Tất cả tên, mã và nội dung trong bộ này là dữ liệu GIẢ LẬP chỉ để kiểm thử phần mềm.
> Không dùng để suy luận hay xác nhận thông tin thật.

| File | Mục tiêu test | Kỳ vọng chính |
|---|---|---|
| 01_text_valid.txt | Text Unicode tiếng Việt | TEXT -> extract/normalize/resolve |
| 02_text_no_diacritics.txt | Text không dấu | Không được coi là lỗi OCR; dùng normalization/ascii_key |
| 03_docx_valid.docx | DOCX có text-layer | DOCX parser, không OCR |
| 04_pdf_digital_valid.pdf | PDF digital | PDF_TEXT, text parser |
| 05_pdf_hybrid.pdf | PDF 2 trang: digital + scan | PDF_HYBRID; route theo từng trang |
| 05_batch_mixed.xlsx | Batch có valid + lỗi + duplicate + ambiguous | TABULAR_LIST; phase-1 validation; 1 row = 1 Case sau confirm |
| 06_key_value_sheet.xlsx | Excel 2 cột label/value | KEY_VALUE_SHEET, không được coi là batch list |
| 07_scan_valid.png | Ảnh scan rõ | IMAGE -> OCR -> quality gate |
| 08_scan_low_quality.png | Ảnh xoay/mờ | OCR quality thấp; fallback hoặc NEED_REVIEW |
| 09_batch_small.csv | CSV danh sách nhỏ | TABULAR_LIST |
| 10_text_multi_subject.txt | Text tự do có 2 người (2 khối "Họ và tên:") | Tách thành 2 Case độc lập, mỗi Case đúng 1 subject_name và evidence.split_source |

## Các dòng cố ý lỗi trong 05_batch_mixed.xlsx

- Thiếu họ tên -> MISSING_REQUIRED
- CCCD `12345` -> BAD_FORMAT
- `Phòng nghiệp vụ` -> cố ý mơ hồ để test resolution/review
- Hai dòng cùng CCCD `092201112233` -> DUPLICATE_IN_FILE
- Ngày `31/02/2026` -> BAD_FORMAT

## Thứ tự test gợi ý

1. 01_text_valid.txt
2. 02_text_no_diacritics.txt
3. 03_docx_valid.docx
4. 04_pdf_digital_valid.pdf
5. 07_scan_valid.png
6. 08_scan_low_quality.png
7. 05_pdf_hybrid.pdf
8. 06_key_value_sheet.xlsx
9. 09_batch_small.csv
10. 05_batch_mixed.xlsx

Lưu ý: ELIGIBLE / NOT_ELIGIBLE phụ thuộc dữ liệu Registry/Policy/Version đang seed ở môi trường test.
Bộ fixture này chủ yếu kiểm tra routing, parsing/OCR, validation, resolution/review và batch semantics.
