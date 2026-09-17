import React from 'react';
import {
  X,
  FileText,
  Download,
  Building2,
  User,
  ExternalLink,
} from '../icons/index.jsx';

const ORG_LABELS = {
  BQP: 'Lực lượng Quân đội nhân dân',
  BCA: 'Lực lượng Công an nhân dân',
  OTHER: 'Ngoài phạm vi BCA/BQP',
  UNKNOWN: 'Chưa xác định',
};

const STATUS_LABELS = {
  MATCHED: 'Đã xác định',
  AMBIGUOUS: 'Cần xác minh thêm',
  NOT_FOUND: 'Không tìm thấy',
  CONFLICT: 'Thông tin mâu thuẫn',
  PROCESSED: 'Đã xử lý',
  NEED_REVIEW: 'Cần thẩm định',
  FAILED: 'Xử lý không thành công',
};

const PARSE_STATUS_LABELS = {
  COMPLETED: 'Đã đọc xong',
  PROCESSING: 'Đang đọc tài liệu',
  FAILED: 'Không thể đọc tài liệu',
  PENDING: 'Đang chờ xử lý',
};

function formatBytes(bytes) {
  if (typeof bytes !== 'number' || Number.isNaN(bytes)) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export default function OriginalDossierModal({ isOpen, onClose, caseDetail, onOpenCompare }) {
  if (!isOpen) return null;

  const detail = caseDetail || {};
  const subject = detail.subject || {};
  const documents = Array.isArray(detail.documents) ? detail.documents : [];
  const orgType = detail.organization_type || 'UNKNOWN';
  const caseId = detail.case?.id || '';
  const caseCode = caseId ? `#HS-2026-${String(caseId).replace(/^case_/i, '').slice(0, 8).toUpperCase()}` : '—';

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-900/60 backdrop-blur-xs overflow-y-auto animate-in fade-in duration-150">
      <div className="relative w-full max-w-4xl bg-white rounded-md shadow-2xl border border-slate-200 overflow-hidden my-4 sm:my-6 max-h-[94vh] flex flex-col">
        {/* Modal Header */}
        <div className="px-4 sm:px-6 py-3.5 sm:py-4 bg-white text-slate-900 flex items-center justify-between border-b border-slate-200 flex-shrink-0">
          <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
            <div className="min-w-0">
              <h3 className="text-[15px] sm:text-[17px] font-bold tracking-tight text-slate-900 truncate">HỒ SƠ ĐỐI TƯỢNG</h3>
              <p className="text-[11.5px] sm:text-[12.5px] text-slate-500 mt-0.5 truncate">
                Mã hồ sơ: <span className="font-mono text-emerald-700 font-bold">{caseCode}</span>
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="w-8 h-8 rounded-md bg-slate-100 hover:bg-slate-200 text-slate-500 hover:text-slate-900 flex items-center justify-center transition-colors flex-shrink-0 ml-2"
            title="Đóng cửa sổ"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-4 sm:p-6 overflow-y-auto flex-1 space-y-4 sm:space-y-6 text-slate-800">
          {/* Dossier Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left Column: Personnel Identity */}
            <div className="lg:col-span-5 bg-slate-50 rounded-md border border-slate-200 p-5 space-y-4">
              <div className="flex items-center gap-4 pb-4 border-b border-slate-200">
                <div className="w-16 h-16 rounded-md bg-slate-200 border-2 border-slate-300 flex items-center justify-center flex-shrink-0">
                  <User className="w-8 h-8 text-slate-400" />
                </div>
                <div>
                  <span className="text-[11.5px] font-bold text-red-600 uppercase tracking-wider">
                    {ORG_LABELS[orgType] || ORG_LABELS.UNKNOWN}
                  </span>
                  <h4 className="text-[18px] font-bold text-slate-900 leading-tight mt-0.5">
                    {subject.name || '—'}
                  </h4>
                  <p className="text-[13px] text-slate-600 mt-1 font-medium">
                    {subject.position || 'Chưa xác định chức vụ'}
                  </p>
                </div>
              </div>

              <div className="space-y-2.5 text-[13px]">
                <div className="flex justify-between py-1 border-b border-slate-200/60">
                  <span className="text-slate-500">Mã định danh:</span>
                  <span className="font-mono font-semibold text-slate-900">{subject.code || '—'}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200/60">
                  <span className="text-slate-500">Đơn vị hiện tại:</span>
                  <span className="font-bold text-slate-900 text-right max-w-[200px]">{detail.current_unit || 'Chưa xác định đơn vị'}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200/60">
                  <span className="text-slate-500">Trạng thái đối chiếu:</span>
                  <span className="px-2 py-0.5 rounded-full text-[11.5px] font-bold border bg-slate-100 text-slate-700 border-slate-300">
                    {STATUS_LABELS[detail.resolution_status] || 'Chưa xác định'}
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200/60">
                  <span className="text-slate-500">Trạng thái hồ sơ:</span>
                  <span className="font-semibold text-slate-900">{STATUS_LABELS[detail.verification_status] || 'Chưa xác định'}</span>
                </div>
              </div>
            </div>

            {/* Right Column: Source documents */}
            <div className="lg:col-span-7 space-y-4">
              <div className="p-4 bg-white rounded-md border border-slate-200 shadow-sm space-y-3">
                <div className="flex items-center gap-2 pb-2 border-b border-slate-100">
                  <Building2 className="w-4 h-4 text-red-600" />
                  <h4 className="text-[14.5px] font-bold text-slate-900">Tài liệu nguồn đã tiếp nhận</h4>
                </div>

                {documents.length === 0 ? (
                  <p className="text-[12.5px] text-slate-500 py-2">
                    Hồ sơ được tạo từ văn bản nhập trực tiếp, không có tệp tài liệu đính kèm.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {documents.map((doc) => (
                      <div key={doc.id} className="flex items-start justify-between gap-3 p-3 bg-slate-50 rounded-md border border-slate-200 text-[12.5px]">
                        <div className="flex items-start gap-2 min-w-0">
                          <FileText className="w-4 h-4 text-slate-500 flex-shrink-0 mt-0.5" />
                          <div className="min-w-0">
                            <p className="font-semibold text-slate-900 truncate">{doc.file_name || 'Không rõ tên tệp'}</p>
                            <p className="text-slate-500">{doc.mime_type || '—'} · {formatBytes(doc.size_bytes)}</p>
                          </div>
                        </div>
                        <div className="text-right flex-shrink-0">
                          <p className="font-mono text-[11px] text-slate-600" title={doc.checksum || ''}>
                            {doc.checksum ? `Mã kiểm tra: ${doc.checksum.slice(0, 12)}…` : 'Chưa có mã kiểm tra'}
                          </p>
                          <p className="text-slate-500">{PARSE_STATUS_LABELS[doc.parse_status] || 'Chưa xử lý'}{typeof doc.parse_confidence === 'number' ? ` · ${Math.round(doc.parse_confidence * 100)}%` : ''}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <p className="text-[11.5px] text-slate-400 pt-1">
                  Chưa có bản xem trước. Mã kiểm tra được tạo từ tệp gốc để xác minh tài liệu không bị thay đổi.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Modal Footer Actions */}
        <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3 flex-shrink-0">
          <div className="text-[12.5px] text-slate-500">
            Dữ liệu hiển thị lấy trực tiếp từ hồ sơ hệ thống, phục vụ nghiệp vụ đối soát nội bộ.
          </div>

          <div className="flex items-center gap-2.5 w-full sm:w-auto justify-end">
            <button
              type="button"
              onClick={handlePrint}
              className="px-3.5 py-2 rounded-md border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-[13px] font-semibold flex items-center gap-1.5 transition-colors shadow-xs"
              title="In hoặc xuất hồ sơ ra PDF"
            >
              <Download className="w-3.5 h-3.5 text-slate-600" />
              <span>In hồ sơ (PDF)</span>
            </button>

            {onOpenCompare && (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onOpenCompare();
                }}
                className="px-4 py-2 rounded-md bg-red-50 text-red-700 border border-red-200 hover:bg-red-100 text-[13px] font-semibold flex items-center gap-1.5 transition-colors"
              >
                <span>Xem đối chiếu chi tiết</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </button>
            )}

            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-md bg-red-600 hover:bg-red-700 text-white text-[13px] font-semibold transition-colors shadow-xs"
            >
              Đóng
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
