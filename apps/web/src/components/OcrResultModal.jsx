import React, { useState, useEffect } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  FileText,
  Search,
  User,
  Calendar,
  Building2,
  Briefcase,
  Hash,
  Eye,
  RotateCcw,
} from '../icons/index.jsx';

export default function OcrResultModal({
  isOpen,
  onClose,
  file,
  filePreviewUrl,
  extractedData,
  onConfirmBulk,
  onConfirmAndSearch,
}) {
  if (!isOpen) return null;

  const [editableFields, setEditableFields] = useState({
    fullName: extractedData?.fullName || '',
    birthYear: extractedData?.birthYear || '',
    position: extractedData?.position || '',
    department: extractedData?.department || '',
    identifier: extractedData?.identifier || '',
    extraInfo: extractedData?.extraInfo || '',
  });

  useEffect(() => {
    if (extractedData) {
      setEditableFields({
        fullName: extractedData.fullName || '',
        birthYear: extractedData.birthYear || '',
        position: extractedData.position || '',
        department: extractedData.department || '',
        identifier: extractedData.identifier || '',
        extraInfo: extractedData.extraInfo || '',
      });
    }
  }, [extractedData]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setEditableFields((prev) => ({ ...prev, [name]: value }));
  };

  const handleApply = () => {
    onConfirmAndSearch(editableFields);
    onClose();
  };

  const isImage = file?.type?.startsWith('image/');
  const isPdf =
    file?.type === 'application/pdf' || file?.name?.toLowerCase().endsWith('.pdf');
  const sourcePreviewRows = extractedData?.sourcePreviewRows || [];
  const sourcePreviewText = extractedData?.sourcePreviewText || '';
  const extractedBadge = (
    <span className="text-[11px] font-medium text-emerald-600 flex items-center gap-1">
      <CheckCircle2 className="w-3 h-3 text-emerald-500" />
      <span>Trích xuất</span>
    </span>
  );

  if (extractedData?.isBulk) {
    return (
      <BulkResultModal
        file={file}
        data={extractedData}
        onClose={onClose}
        onConfirm={onConfirmBulk}
      />
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-900/50 backdrop-blur-xs overflow-y-auto animate-in fade-in duration-150">
      <div className="relative w-full max-w-4xl bg-white rounded-md shadow-xl border border-slate-200 overflow-hidden my-4 sm:my-6 max-h-[94vh] flex flex-col">
        {/* Modal Header */}
        <div className="px-5 py-4 bg-white text-slate-900 flex items-center justify-between border-b border-slate-200 flex-shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-md bg-slate-100 flex items-center justify-center text-slate-700 flex-shrink-0">
              <span className="material-symbols-outlined text-[18px] leading-none flex items-center" aria-hidden="true">document_scanner</span>
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-[16px] font-bold tracking-tight text-slate-900 truncate">Kiểm tra thông tin nhận dạng</h3>
                <span className={`hidden xs:inline-flex px-2 py-0.5 rounded text-[11px] font-semibold border items-center ${
                  extractedData?.qualityGate === 'FAIL'
                    ? 'bg-[#FDF0BE] text-amber-800 border-amber-200'
                    : 'bg-emerald-50 text-emerald-800 border-emerald-200'
                }`}>
                  {extractedData?.qualityGate === 'FAIL' ? 'Cần kiểm tra' : 'Độ tin cậy'} {extractedData?.confidence || '—'}
                </span>
              </div>
              <p className="text-[12px] text-slate-500 mt-0.5 truncate">
                Tài liệu:{' '}
                <span className="font-semibold text-slate-800">{file?.name || 'Tài liệu ảnh chụp'}</span> ({file ? (file.size / 1024).toFixed(1) + ' KB' : 'Chuẩn hóa số hóa'})
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-md bg-slate-100 hover:bg-slate-200 text-slate-500 hover:text-slate-800 flex items-center justify-center transition-colors cursor-pointer flex-shrink-0 ml-2"
            title="Đóng cửa sổ"
          >
            <span className="material-symbols-outlined text-[20px] leading-none flex items-center" aria-hidden="true">close</span>
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 bg-slate-50/40 space-y-5">
          {extractedData?.isMultiSubject && (
            <div className="p-3.5 rounded-md border border-red-200 bg-red-50/70 flex items-start gap-2.5">
              <User className="w-4.5 h-4.5 text-red-600 flex-shrink-0 mt-0.5" />
              <div className="text-[12.5px] leading-relaxed text-red-900">
                <span className="font-bold">
                  Tài liệu này có {extractedData.blockCount} người.
                </span>{' '}
                Hệ thống đã tự động tách thành {extractedData.blockCount} hồ sơ riêng biệt — đây là hồ sơ{' '}
                <span className="font-semibold">#{extractedData.blockIndex + 1}/{extractedData.blockCount}</span>.
                Các hồ sơ còn lại đã được tạo và có thể xem tại mục <span className="font-semibold">Lịch sử</span>.
              </div>
            </div>
          )}

          {/* Top banner */}
          <div className={`px-4 py-3 rounded-md flex items-start gap-3 ${
            extractedData?.qualityGate === 'FAIL'
              ? 'bg-[#FDF0BE]/80'
              : 'bg-slate-100/70'
          }`}>
            {extractedData?.qualityGate === 'FAIL' ? (
              <AlertTriangle className="w-[18px] h-[18px] text-amber-600 flex-shrink-0 mt-0.5" />
            ) : (
              <CheckCircle2 className="w-[18px] h-[18px] text-slate-600 flex-shrink-0 mt-0.5" />
            )}
            <div className={`text-[12.5px] leading-relaxed ${extractedData?.qualityGate === 'FAIL' ? 'text-amber-900' : 'text-slate-700'}`}>
              <div className="font-bold text-[13px] mb-0.5">
                {extractedData?.qualityGate === 'FAIL' ? 'Ảnh có chất lượng thấp' : 'Đã trích xuất thông tin'}
              </div>
              <div className="font-normal">
                {extractedData?.qualityGate === 'FAIL'
                  ? 'Một số thông tin có thể chưa chính xác. Vui lòng kiểm tra và chỉnh sửa dữ liệu trước khi đối chiếu.'
                  : 'Vui lòng kiểm tra lại thông tin đã nhận dạng trước khi đối chiếu.'}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-12 gap-5">
            {/* Left: Document/Image Preview */}
            <div className="md:col-span-5 flex flex-col">
              <h4 className="text-[13.5px] font-bold text-slate-800 mb-2 flex items-center gap-1.5">
                <Eye className="w-4 h-4 text-slate-400" />
                <span>Văn bản gốc</span>
              </h4>

              <div className="flex-1 bg-slate-100/70 rounded-md border border-slate-200 overflow-hidden relative flex items-center justify-center min-h-[260px] p-2.5">
                {filePreviewUrl && isImage ? (
                  <div className="relative w-full h-full flex items-center justify-center">
                    <img
                      src={filePreviewUrl}
                      alt="Tài liệu tải lên"
                      className="max-h-[300px] w-auto max-w-full object-contain rounded shadow-2xs border border-slate-200 bg-white"
                    />
                  </div>
                ) : filePreviewUrl && isPdf ? (
                  <iframe
                    src={filePreviewUrl}
                    title={`Xem trước ${file?.name || 'tài liệu PDF'}`}
                    className="w-full h-[360px] rounded bg-white border border-slate-200"
                  />
                ) : sourcePreviewRows.length > 0 ? (
                  <div data-testid="source-table-preview" className="w-full h-[360px] overflow-auto rounded-md border border-slate-200 bg-white self-start">
                    <table className="min-w-full text-[12px] text-left">
                      <tbody>
                        {sourcePreviewRows.map((row, rowIndex) => (
                          <tr key={rowIndex} className="border-b border-slate-100 last:border-0">
                            <td className="sticky left-0 w-9 px-2 py-2 text-center text-slate-400 bg-slate-50 border-r border-slate-100">{rowIndex + 1}</td>
                            {row.map((cell, cellIndex) => (
                              <td key={cellIndex} className={`px-3 py-2 min-w-32 text-slate-800 border-r border-slate-100 last:border-r-0 ${cellIndex === 0 ? 'font-semibold' : ''}`}>{cell || '—'}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : sourcePreviewText ? (
                  <div data-testid="source-text-preview" className="w-full h-[360px] overflow-auto rounded-md border border-slate-200 bg-white self-start">
                    <pre className="p-4 pb-14 whitespace-pre-wrap break-words font-sans text-[12.5px] leading-6 text-slate-800">{sourcePreviewText}</pre>
                  </div>
                ) : (
                  <div className="text-center p-6 text-slate-400">
                    <FileText className="w-12 h-12 mx-auto mb-2 text-slate-400" />
                    <p className="text-[13px] font-semibold text-slate-700">{file?.name || 'Tài liệu nghiệp vụ'}</p>
                    <p className="text-[11.5px] text-slate-400 mt-1">Đã phân tích cấu trúc văn bản</p>
                  </div>
                )}

                <div className="absolute bottom-2 left-2 right-2 px-2.5 py-1.5 rounded-md bg-white/95 backdrop-blur-xs text-[11px] text-slate-600 flex items-center justify-between border border-slate-200 shadow-2xs">
                  <span className="font-mono font-medium text-slate-700">
                    Đã đọc xong tài liệu
                  </span>
                  <span className="text-slate-500">
                    {[editableFields.fullName, editableFields.birthYear, editableFields.position, editableFields.department, editableFields.identifier].filter(Boolean).length} trường
                  </span>
                </div>
              </div>
            </div>

            {/* Right: Extracted & Editable Fields */}
            <div className="md:col-span-7 flex flex-col">
              <h4 className="text-[13.5px] font-bold text-slate-800 mb-2 flex items-center justify-between">
                <span>Dữ liệu trích xuất</span>
                <span className="text-[11.5px] font-normal text-slate-400">Có thể chỉnh sửa trực tiếp</span>
              </h4>

              <div className="bg-white rounded-md border border-slate-200 p-3.5 space-y-3 shadow-2xs">
                {/* Họ và tên */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[12px] font-semibold text-slate-700 flex items-center gap-1.5">
                      <User className="w-3.5 h-3.5 text-slate-400" />
                      <span>Họ và tên</span>
                    </label>
                    {editableFields.fullName && (
                      extractedBadge
                    )}
                  </div>
                  <input
                    type="text"
                    name="fullName"
                    value={editableFields.fullName}
                    onChange={handleChange}
                    placeholder="Không nhận dạng được trong tài liệu"
                    className="w-full h-9 px-3 rounded-md border border-slate-200 hover:border-slate-300 focus:border-red-600 focus:ring-1 focus:ring-red-100 text-[13px] font-medium text-slate-900 outline-none placeholder:font-normal placeholder:text-slate-400 transition-all"
                  />
                </div>

                {/* Năm sinh & Chức vụ */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-[12px] font-semibold text-slate-700 flex items-center gap-1.5">
                        <Calendar className="w-3.5 h-3.5 text-slate-400" />
                        <span>Năm sinh</span>
                      </label>
                      {editableFields.birthYear && (
                        extractedBadge
                      )}
                    </div>
                    <input
                      type="text"
                      name="birthYear"
                      value={editableFields.birthYear}
                      onChange={handleChange}
                      placeholder="Không có trong tài liệu"
                      className="w-full h-9 px-3 rounded-md border border-slate-200 hover:border-slate-300 focus:border-red-600 focus:ring-1 focus:ring-red-100 text-[13px] text-slate-900 outline-none placeholder:text-slate-400 transition-all"
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-[12px] font-semibold text-slate-700 flex items-center gap-1.5">
                        <Briefcase className="w-3.5 h-3.5 text-slate-400" />
                        <span>Chức vụ</span>
                      </label>
                      {editableFields.position && (
                        extractedBadge
                      )}
                    </div>
                    <input
                      type="text"
                      name="position"
                      value={editableFields.position}
                      onChange={handleChange}
                      placeholder="Không có trong tài liệu"
                      className="w-full h-9 px-3 rounded-md border border-slate-200 hover:border-slate-300 focus:border-red-600 focus:ring-1 focus:ring-red-100 text-[13px] text-slate-900 outline-none placeholder:text-slate-400 transition-all"
                    />
                  </div>
                </div>

                {/* Đơn vị */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[12px] font-semibold text-slate-700 flex items-center gap-1.5">
                      <Building2 className="w-3.5 h-3.5 text-slate-400" />
                      <span>Đơn vị công tác / nghiệp vụ</span>
                    </label>
                    {editableFields.department && (
                      extractedBadge
                    )}
                  </div>
                  <input
                    type="text"
                    name="department"
                    value={editableFields.department}
                    onChange={handleChange}
                    placeholder="Không nhận dạng được trong tài liệu"
                    className="w-full h-9 px-3 rounded-md border border-slate-200 hover:border-slate-300 focus:border-red-600 focus:ring-1 focus:ring-red-100 text-[13px] text-slate-900 outline-none placeholder:text-slate-400 transition-all"
                  />
                </div>

                {/* Số hiệu */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[12px] font-semibold text-slate-700 flex items-center gap-1.5">
                      <Hash className="w-3.5 h-3.5 text-slate-400" />
                      <span>Số hiệu / Mã định danh</span>
                    </label>
                    {editableFields.identifier && (
                      extractedBadge
                    )}
                  </div>
                  <input
                    type="text"
                    name="identifier"
                    value={editableFields.identifier}
                    onChange={handleChange}
                    className="w-full h-9 px-3 rounded-md border border-slate-200 hover:border-slate-300 focus:border-red-600 focus:ring-1 focus:ring-red-100 text-[13px] font-mono uppercase text-slate-900 outline-none transition-all"
                  />
                </div>

                {/* Ghi chú OCR */}
                <div>
                  <label className="block text-[12px] font-semibold text-slate-700 mb-1">
                    Ghi chú nhận dạng
                  </label>
                  <input
                    type="text"
                    name="extraInfo"
                    value={editableFields.extraInfo}
                    onChange={handleChange}
                    className="w-full h-9 px-3 rounded-md border border-slate-200 hover:border-slate-300 focus:border-red-600 focus:ring-1 focus:ring-red-100 text-[12px] text-slate-600 outline-none transition-all"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-4 sm:px-6 py-3.5 sm:py-4 bg-white border-t border-slate-200 flex flex-col-reverse sm:flex-row items-stretch sm:items-center justify-between gap-2.5 sm:gap-3 flex-shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="w-full sm:w-auto px-4 py-2 rounded-md border border-slate-200 hover:bg-slate-50 text-slate-700 text-[13.5px] font-semibold transition-colors cursor-pointer text-center"
          >
            Hủy bỏ
          </button>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 sm:gap-3">
            <button
              type="button"
              onClick={() => {
                // Reset to raw extracted data
                if (extractedData) {
                  setEditableFields({
                    fullName: extractedData.fullName || '',
                    birthYear: extractedData.birthYear || '',
                    position: extractedData.position || '',
                    department: extractedData.department || '',
                    identifier: extractedData.identifier || '',
                    extraInfo: extractedData.extraInfo || '',
                  });
                }
              }}
              className="w-full sm:w-auto px-3.5 py-2 rounded-md border border-slate-200 hover:bg-slate-50 text-slate-600 text-[13px] font-medium flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
              <span>Khôi phục gốc</span>
            </button>

            <button
              type="button"
              onClick={handleApply}
              className="w-full sm:w-auto px-5 py-2 rounded-md bg-red-600 hover:bg-red-700 text-white text-[13.5px] font-semibold flex items-center justify-center gap-2 shadow-xs transition-colors cursor-pointer"
            >
              <Search className="w-4 h-4" />
              <span>Áp dụng &amp; Đối soát ngay</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

const BULK_FIELDS = [
  ['subject_name', 'Họ và tên'],
  ['subject_code', 'CCCD / Mã định danh'],
  ['position', 'Chức vụ'],
  ['subject_group', 'Nhóm đối tượng'],
  ['unit_name', 'Đơn vị công tác'],
  ['unit_code', 'Mã đơn vị'],
  ['as_of_date', 'Ngày đánh giá'],
];

function BulkResultModal({ file, data, onClose, onConfirm }) {
  const [mapping, setMapping] = useState(data.mapping || {});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const headers = data.profile?.headers || Object.keys(mapping);
  const details = data.profile?.mapping_details || {};
  const validation = data.validation || {};
  const rows = data.rows || [];
  const alreadyProcessed = ['QUEUED', 'PROCESSING', 'COMPLETED', 'COMPLETED_WITH_ERRORS'].includes(data.status);
  const hasMappingConfidence = headers.some((header) => details[header]?.confidence != null);
  const statusLabel = {
    QUEUED: 'Đang chờ xử lý',
    PROCESSING: 'Đang xử lý',
    COMPLETED: 'Đã xử lý xong',
    COMPLETED_WITH_ERRORS: 'Đã xử lý, có dòng lỗi',
    FAILED: 'Xử lý thất bại',
  }[data.status] || data.status;

  const handleConfirm = async () => {
    setSubmitting(true);
    setSubmitError('');
    try {
      await onConfirm(data.jobId, mapping);
      onClose();
    } catch (error) {
      setSubmitError(error?.response?.data?.detail || error.message || 'Không thể xác nhận danh sách');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-900/60 backdrop-blur-xs overflow-y-auto">
      <div className="relative w-full max-w-5xl bg-white rounded-md shadow-2xl border border-slate-200 overflow-hidden my-4 max-h-[94vh] flex flex-col">
        <div className="px-5 py-4 bg-white text-slate-900 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-md bg-red-50 border border-red-200 flex items-center justify-center text-red-600"><FileText className="w-5 h-5 text-red-600" /></div>
            <div className="min-w-0">
              <h3 className="text-[17px] font-bold text-slate-900">NHẬP DANH SÁCH NHIỀU DÒNG</h3>
              <p className="text-xs text-slate-500 truncate">{file?.name}</p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="w-8 h-8 rounded-md bg-slate-100 hover:bg-slate-200 text-slate-500 hover:text-slate-900 flex items-center justify-center"><span className="material-symbols-outlined text-[20px] leading-none flex items-center" aria-hidden="true">close</span></button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 sm:p-6 bg-slate-50 space-y-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              ['Tổng số dòng', validation.rows ?? data.job?.total_rows ?? 0],
              ['Lỗi', validation.errors ?? data.job?.failed ?? 0],
              ['Cảnh báo', validation.warnings ?? 0],
              ['Trùng bỏ qua', validation.skipped_duplicates ?? data.job?.skipped ?? 0],
            ].map(([label, value]) => (
              <div key={label} className="bg-white border border-slate-200 rounded-md p-3">
                <div className="text-xs text-slate-500">{label}</div>
                <div className="text-xl font-bold text-slate-900 mt-1">{value}</div>
              </div>
            ))}
          </div>

          {data.duplicateFile && (
            <div className="p-3 rounded-md bg-[#FDF0BE] border border-amber-200 text-sm text-amber-800">
              Tệp này đã được nhập trước đó. Đang hiển thị lần xử lý hiện có: <strong>{statusLabel}</strong>.
            </div>
          )}

          {data.errors?.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-md p-4">
              <h4 className="font-bold text-red-900 mb-2">Các dòng cần kiểm tra ({data.errors.length})</h4>
              <ul className="space-y-1.5 text-sm text-red-800">
                {data.errors.map((error, index) => (
                  <li key={`${error.row_index}-${error.code}-${index}`}>
                    <strong>Dòng {error.row_index}:</strong> {error.message_vi || error.message}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {rows.length > 0 && (
            <div className="bg-white border border-slate-200 rounded-md overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-200">
                <h4 className="font-bold text-slate-900">Danh sách nhận diện ({rows.length})</h4>
                <p className="text-xs text-slate-500 mt-0.5">Kiểm tra họ tên và thông tin từng dòng trước khi sử dụng kết quả.</p>
              </div>
              <div className="overflow-x-auto max-h-72 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-slate-50 text-slate-600">
                    <tr><th className="text-left px-4 py-2">Dòng</th><th className="text-left px-4 py-2">Họ và tên</th><th className="text-left px-4 py-2">Mã cá nhân</th><th className="text-left px-4 py-2">Đơn vị</th><th className="text-left px-4 py-2">Trạng thái</th></tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const status = {
                        SUCCEEDED: ['Đã tạo hồ sơ', 'text-emerald-700 bg-emerald-50'],
                        FAILED: ['Có lỗi', 'text-red-700 bg-red-50'],
                        SKIPPED_DUPLICATE: ['Trùng, đã bỏ qua', 'text-amber-700 bg-[#FDF0BE]'],
                        PENDING: ['Chờ xử lý', 'text-slate-600 bg-slate-100'],
                      }[row.status] || [row.status, 'text-slate-600 bg-slate-100'];
                      return (
                        <tr key={row.row_index} className="border-t border-slate-100">
                          <td className="px-4 py-2 text-slate-500">{row.row_index}</td>
                          <td className="px-4 py-2 font-semibold text-slate-900">{row.subject_name || '—'}</td>
                          <td className="px-4 py-2 text-slate-700 whitespace-nowrap">{row.subject_code || '—'}</td>
                          <td className="px-4 py-2 text-slate-700">{row.unit_name || '—'}</td>
                          <td className="px-4 py-2 whitespace-nowrap"><span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${status[1]}`}>{status[0]}</span></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {headers.length > 0 && (
            <div className="bg-white border border-slate-200 rounded-md overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-200">
                <h4 className="font-bold text-slate-900">Kiểm tra ánh xạ cột</h4>
                <p className="text-xs text-slate-500 mt-0.5">Độ tin cậy chỉ đánh giá việc nhận diện tên cột, không đánh giá dữ liệu từng dòng.</p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-slate-600"><tr><th className="text-left px-4 py-2">Cột gốc</th><th className="text-left px-4 py-2">Trường hệ thống</th>{hasMappingConfidence && <th className="text-right px-4 py-2">Độ tin cậy</th>}</tr></thead>
                  <tbody>
                    {headers.map((header) => (
                      <tr key={header} className="border-t border-slate-100">
                        <td className="px-4 py-2 font-medium text-slate-800">{header}</td>
                        <td className="px-4 py-2">
                          <select disabled={alreadyProcessed} value={mapping[header] || ''} onChange={(event) => setMapping((current) => ({ ...current, [header]: event.target.value || null }))} className="w-full h-9 rounded-md border border-slate-200 px-2 bg-white disabled:bg-slate-100">
                            <option value="">— Bỏ qua —</option>
                            {BULK_FIELDS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                          </select>
                        </td>
                        {hasMappingConfidence && <td className="px-4 py-2 text-right font-semibold text-slate-700">{details[header]?.confidence != null ? `${Math.round(details[header].confidence * 100)}%` : '—'}</td>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {submitError && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-md p-3">{submitError}</div>}
        </div>

        <div className="px-5 py-4 bg-white border-t border-slate-200 flex justify-between gap-3">
          <button type="button" onClick={onClose} className="px-4 py-2 rounded-md border border-slate-200 font-semibold text-slate-700">Đóng</button>
          {!alreadyProcessed && (
            <button type="button" disabled={submitting} onClick={handleConfirm} className="px-5 py-2 rounded-md bg-red-600 hover:bg-red-700 disabled:bg-red-300 text-white font-semibold">
              {submitting ? 'Đang xác nhận…' : 'Xác nhận cột và xử lý danh sách'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
