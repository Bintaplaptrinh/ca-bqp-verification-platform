import React, { useState, useEffect } from 'react';
import {
  X,
  Scan,
  CheckCircle2,
  AlertCircle,
  FileText,
  Sparkles,
  ShieldCheck,
  Search,
  User,
  Calendar,
  Building2,
  Briefcase,
  Hash,
  Eye,
  RotateCcw,
} from 'lucide-react';

export default function OcrResultModal({
  isOpen,
  onClose,
  file,
  filePreviewUrl,
  extractedData,
  onConfirmAndSearch,
}) {
  if (!isOpen) return null;

  const [editableFields, setEditableFields] = useState({
    fullName: extractedData?.fullName || 'Nguyễn Văn A',
    birthYear: extractedData?.birthYear || '1985',
    position: extractedData?.position || 'Cán bộ điều tra',
    department: extractedData?.department || 'Đơn vị X - Cục CSDT',
    identifier: extractedData?.identifier || 'CA-8492',
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

  const isImage = file?.type?.startsWith('image/') || (!file && filePreviewUrl);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-900/60 backdrop-blur-xs overflow-y-auto animate-in fade-in duration-150">
      <div className="relative w-full max-w-4xl bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden my-4 sm:my-6 max-h-[94vh] flex flex-col">
        {/* Modal Header */}
        <div className="px-4 sm:px-6 py-3.5 sm:py-4 bg-slate-900 text-white flex items-center justify-between border-b border-slate-800 flex-shrink-0">
          <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
            <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-blue-600 flex items-center justify-center text-white shadow-sm flex-shrink-0">
              <Scan className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
                <h3 className="text-[15px] sm:text-[17px] font-bold tracking-tight truncate">TRÍCH XUẤT THỰC THỂ (OCR)</h3>
                <span className="hidden xs:inline-flex px-2 py-0.5 rounded text-[10px] sm:text-[11px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-400/30 items-center gap-1">
                  <Sparkles className="w-3 h-3" />
                  ĐỘ TIN CẬY {extractedData?.confidence || '99.1%'}
                </span>
              </div>
              <p className="text-[11.5px] sm:text-[12.5px] text-slate-300 mt-0.5 truncate">
                Tài liệu:{' '}
                <span className="font-semibold text-white">{file?.name || 'Tài liệu ảnh chụp'}</span> ({file ? (file.size / 1024).toFixed(1) + ' KB' : 'Chuẩn hóa số hóa'})
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 rounded-lg bg-white/10 hover:bg-white/20 text-slate-300 hover:text-white flex items-center justify-center transition-colors cursor-pointer flex-shrink-0 ml-2"
            title="Đóng cửa sổ"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 bg-slate-50/50 space-y-4 sm:space-y-6">
          {/* Top banner */}
          <div className="p-4 rounded-xl bg-blue-50/80 border border-blue-200/80 flex items-start gap-3">
            <ShieldCheck className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
            <div className="text-[13px] text-blue-900 leading-relaxed">
              <span className="font-bold">Nhận dạng thực thể tự động (Named Entity Recognition - NER):</span> Mô-đun AI OCR đã phân tích tài liệu và tự động phân loại các trường định danh. Cán bộ có thể kiểm tra và chỉnh sửa nhanh các giá trị trước khi chuyển sang bước đối soát tự động Master Unit Registry.
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
            {/* Left: Document/Image Preview */}
            <div className="md:col-span-5 flex flex-col">
              <h4 className="text-[14px] font-bold text-slate-900 mb-2.5 flex items-center gap-2">
                <Eye className="w-4 h-4 text-slate-500" />
                <span>Ảnh / Bản quét tài liệu gốc</span>
              </h4>

              <div className="flex-1 bg-slate-900 rounded-xl border border-slate-700/80 overflow-hidden relative flex items-center justify-center min-h-[260px] p-3 group">
                {filePreviewUrl ? (
                  <div className="relative w-full h-full flex items-center justify-center">
                    <img
                      src={filePreviewUrl}
                      alt="Tài liệu tải lên"
                      className="max-h-[300px] w-auto max-w-full object-contain rounded shadow-md border border-slate-700"
                    />
                    {/* Simulated OCR bounding overlay */}
                    <div className="absolute inset-0 bg-blue-500/10 pointer-events-none rounded border-2 border-dashed border-blue-400/60 animate-pulse" />
                  </div>
                ) : (
                  <div className="text-center p-6 text-slate-400">
                    <FileText className="w-16 h-16 mx-auto mb-3 text-blue-400" />
                    <p className="text-[13px] font-semibold text-slate-200">{file?.name || 'Tài liệu nghiệp vụ'}</p>
                    <p className="text-[11.5px] text-slate-400 mt-1">Đã phân tích cấu trúc văn bản PDF/Word</p>
                  </div>
                )}

                <div className="absolute bottom-2 left-2 right-2 px-2.5 py-1.5 rounded bg-slate-900/90 backdrop-blur-xs text-[11px] text-slate-300 flex items-center justify-between border border-white/10">
                  <span className="font-mono text-emerald-400">OCR SCAN: COMPLETED</span>
                  <span>5 trường dữ liệu</span>
                </div>
              </div>
            </div>

            {/* Right: Extracted & Editable Fields */}
            <div className="md:col-span-7 flex flex-col">
              <h4 className="text-[14px] font-bold text-slate-900 mb-2.5 flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-blue-600" />
                  <span>Dữ liệu trích xuất tự động</span>
                </span>
                <span className="text-[12px] font-normal text-slate-500">Cán bộ có thể chỉnh sửa trực tiếp</span>
              </h4>

              <div className="bg-white rounded-xl border border-slate-200 p-4 space-y-3.5 shadow-xs">
                {/* Họ và tên */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[12.5px] font-semibold text-slate-800 flex items-center gap-1.5">
                      <User className="w-3.5 h-3.5 text-blue-600" />
                      <span>Họ và tên</span>
                    </label>
                    <span className="text-[11px] font-semibold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                      Khớp OCR: 99.8%
                    </span>
                  </div>
                  <input
                    type="text"
                    name="fullName"
                    value={editableFields.fullName}
                    onChange={handleChange}
                    className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:border-blue-600 focus:ring-1 focus:ring-blue-200 text-[13.5px] font-semibold text-slate-900 outline-none"
                  />
                </div>

                {/* Năm sinh & Chức vụ */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-[12.5px] font-semibold text-slate-800 flex items-center gap-1.5">
                        <Calendar className="w-3.5 h-3.5 text-blue-600" />
                        <span>Năm sinh</span>
                      </label>
                      <span className="text-[11px] font-semibold text-emerald-600">99.5%</span>
                    </div>
                    <input
                      type="text"
                      name="birthYear"
                      value={editableFields.birthYear}
                      onChange={handleChange}
                      className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:border-blue-600 focus:ring-1 focus:ring-blue-200 text-[13.5px] text-slate-900 outline-none"
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-[12.5px] font-semibold text-slate-800 flex items-center gap-1.5">
                        <Briefcase className="w-3.5 h-3.5 text-blue-600" />
                        <span>Chức vụ</span>
                      </label>
                      <span className="text-[11px] font-semibold text-emerald-600">98.4%</span>
                    </div>
                    <input
                      type="text"
                      name="position"
                      value={editableFields.position}
                      onChange={handleChange}
                      className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:border-blue-600 focus:ring-1 focus:ring-blue-200 text-[13.5px] text-slate-900 outline-none"
                    />
                  </div>
                </div>

                {/* Đơn vị */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[12.5px] font-semibold text-slate-800 flex items-center gap-1.5">
                      <Building2 className="w-3.5 h-3.5 text-blue-600" />
                      <span>Đơn vị công tác / nghiệp vụ</span>
                    </label>
                    <span className="text-[11px] font-semibold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                      Khớp OCR: 98.9%
                    </span>
                  </div>
                  <input
                    type="text"
                    name="department"
                    value={editableFields.department}
                    onChange={handleChange}
                    className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:border-blue-600 focus:ring-1 focus:ring-blue-200 text-[13.5px] text-slate-900 outline-none"
                  />
                </div>

                {/* Số hiệu */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[12.5px] font-semibold text-slate-800 flex items-center gap-1.5">
                      <Hash className="w-3.5 h-3.5 text-blue-600" />
                      <span>Số hiệu / Mã định danh</span>
                    </label>
                    <span className="text-[11px] font-semibold text-emerald-600">99.9%</span>
                  </div>
                  <input
                    type="text"
                    name="identifier"
                    value={editableFields.identifier}
                    onChange={handleChange}
                    className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:border-blue-600 focus:ring-1 focus:ring-blue-200 text-[13.5px] font-mono uppercase text-slate-900 outline-none"
                  />
                </div>

                {/* Ghi chú OCR */}
                <div>
                  <label className="block text-[12.5px] font-semibold text-slate-800 mb-1">
                    Ghi chú nhận dạng
                  </label>
                  <input
                    type="text"
                    name="extraInfo"
                    value={editableFields.extraInfo}
                    onChange={handleChange}
                    className="w-full h-9 px-3 rounded-lg border border-slate-200 focus:border-blue-600 focus:ring-1 focus:ring-blue-200 text-[12.5px] text-slate-600 outline-none"
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
            className="w-full sm:w-auto px-4 py-2 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 text-[13.5px] font-semibold transition-colors cursor-pointer text-center"
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
              className="w-full sm:w-auto px-3.5 py-2 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-600 text-[13px] font-medium flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
              <span>Khôi phục gốc</span>
            </button>

            <button
              type="button"
              onClick={handleApply}
              className="w-full sm:w-auto px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-[13.5px] font-semibold flex items-center justify-center gap-2 shadow-xs transition-colors cursor-pointer"
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
