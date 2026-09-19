import React from 'react';
import { X, FileText } from '../icons/index.jsx';

const ORG_LABELS = {
  BQP: 'Bộ Quốc phòng',
  BCA: 'Bộ Công an',
  OTHER: 'Ngoài phạm vi BCA/BQP',
  UNKNOWN: 'Chưa xác định',
};

const STATUS_LABELS = {
  MATCHED: 'Đã xác định',
  AMBIGUOUS: 'Cần xác minh thêm',
  NOT_FOUND: 'Không tìm thấy',
  CONFLICT: 'Thông tin mâu thuẫn',
  UNKNOWN: 'Chưa xác định',
};

const MATCH_METHOD_LABELS = {
  EXACT_CODE: 'Khớp chính xác theo mã',
  EXACT_NAME: 'Khớp chính xác theo tên',
  FUZZY_NAME: 'Khớp gần đúng theo tên',
  BM25: 'Khớp theo nội dung',
};

const POLICY_STATUS_LABELS = {
  ELIGIBLE: 'Đủ điều kiện',
  NOT_ELIGIBLE: 'Không đủ điều kiện',
  INSUFFICIENT_DATA: 'Chưa đủ dữ liệu',
  UNKNOWN: 'Chưa xác định',
};

// The case API expresses matching score and candidate margin on a 0–100 scale.
// Decision confidence is the exception: it is a probability on a 0–1 scale.
// Keep the conversions separate so a score such as 98.5 is not rendered as
// 9,850% while a confidence such as 0.985 is still rendered as 99%.
function formatPercentage(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'Chưa có';
  return `${Math.round(value)}%`;
}

function formatProbability(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return 'Chưa có';
  return `${Math.round(value * 100)}%`;
}

export default function DetailedComparisonModal({ isOpen, onClose, caseDetail }) {
  if (!isOpen) return null;

  const detail = caseDetail || {};
  const subject = detail.subject || {};
  const result = detail.result || {};
  const eligibility = Array.isArray(detail.eligibility) ? detail.eligibility : [];
  const topCandidates = Array.isArray(result.top_candidates) ? result.top_candidates : [];
  const orgType = detail.organization_type || 'UNKNOWN';
  const isMatched = detail.resolution_status === 'MATCHED';
  const caseId = detail.case?.id || '';
  const caseCode = caseId ? `#HS-2026-${String(caseId).replace(/^case_/i, '').slice(0, 8).toUpperCase()}` : 'Chưa có';

  const comparisonRows = [
    { field: 'Họ và tên', value: subject.name || 'Chưa cung cấp' },
    { field: 'Chức vụ', value: subject.position || 'Chưa cung cấp' },
    { field: 'Mã định danh', value: subject.code || 'Chưa cung cấp' },
    { field: 'Đơn vị hiện tại (chuẩn hóa)', value: detail.current_unit || 'Chưa xác định' },
    { field: 'Tổ chức', value: ORG_LABELS[orgType] || ORG_LABELS.UNKNOWN },
    { field: 'Trạng thái đối chiếu', value: STATUS_LABELS[detail.resolution_status] || 'Chưa xác định' },
    { field: 'Cách đối chiếu', value: MATCH_METHOD_LABELS[result.match_method] || 'Đối chiếu tự động' },
    { field: 'Nhóm đối tượng', value: detail.subject_group || 'Chưa xác định' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-900/60 backdrop-blur-xs overflow-y-auto animate-in fade-in duration-150">
      <div className="relative w-full max-w-5xl bg-white rounded-md shadow-2xl border border-slate-200 overflow-hidden my-4 sm:my-6 max-h-[94vh] flex flex-col">
        {/* Header */}
        <div className="px-4 sm:px-6 py-3.5 sm:py-4 bg-white text-slate-900 flex items-center justify-between border-b border-slate-200 flex-shrink-0">
          <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
            <div className="min-w-0">
              <h3 className="text-[15px] sm:text-[17px] font-bold tracking-tight text-slate-900 truncate">
                ĐỐI CHIẾU CHI TIẾT
              </h3>
              <p className="text-[11.5px] sm:text-[12.5px] text-slate-500 mt-0.5 truncate">
                Mã hồ sơ: <span className="font-mono text-emerald-700 font-bold">{caseCode}</span>, <span className="text-slate-900 font-bold">{subject.name || 'Chưa cung cấp'}</span>
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

        {/* Top Metric Cards — real values only */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 sm:gap-4 p-3.5 sm:p-6 bg-slate-50 border-b border-slate-200 text-[13px] flex-shrink-0">
          <div className="bg-white p-3.5 rounded-md border border-slate-200 shadow-xs">
            <span className="text-slate-500 text-[12px] block">Mức độ phù hợp</span>
            <span className="text-[20px] font-bold text-emerald-600 block mt-0.5">{formatPercentage(result.score)}</span>
            <span className="text-[11px] text-slate-400">{MATCH_METHOD_LABELS[result.match_method] || 'Đối chiếu tự động'}</span>
          </div>

          <div className="bg-white p-3.5 rounded-md border border-slate-200 shadow-xs">
            <span className="text-slate-500 text-[12px] block">Độ tin cậy quyết định</span>
            <span className="text-[20px] font-bold text-red-600 block mt-0.5">{formatProbability(result.decision_confidence)}</span>
            <span className="text-[11px] text-slate-400">Phiên bản danh mục: {result.registry_version || 'Chưa có'}</span>
          </div>

          <div className="bg-white p-3.5 rounded-md border border-slate-200 shadow-xs">
            <span className="text-slate-500 text-[12px] block">Chênh lệch kết quả</span>
            <span className="text-[20px] font-bold text-slate-900 block mt-0.5">{formatPercentage(result.margin)}</span>
            <span className="text-[11px] text-slate-400">Khoảng cách với ứng viên thứ 2</span>
          </div>

          <div className="bg-white p-3.5 rounded-md border border-slate-200 shadow-xs">
            <span className="text-slate-500 text-[12px] block">Trạng thái đối chiếu</span>
            <span className={`text-[15px] font-bold block mt-1 ${isMatched ? 'text-emerald-700' : 'text-amber-700'}`}>
              {STATUS_LABELS[detail.resolution_status] || 'Chưa xác định'}
            </span>
            <span className="text-[11px] text-slate-400">Phiên bản bộ tiêu chí: {result.taxonomy_version || 'Chưa có'}</span>
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          <div>
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-[15px] font-bold text-slate-900 flex items-center gap-2">
                <FileText className="w-4 h-4 text-red-600" />
                Thông tin hồ sơ (dữ liệu thật từ hệ thống)
              </h4>
            </div>

            <div className="overflow-x-auto border border-slate-200 rounded-md shadow-xs">
              <table className="w-full text-left text-[13px] border-collapse">
                <thead>
                  <tr className="bg-slate-100 text-slate-700 font-bold border-b border-slate-200 text-[12.5px]">
                    <th className="py-3 px-4 w-56">Trường</th>
                    <th className="py-3 px-4">Giá trị</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {comparisonRows.map((row, idx) => (
                    <tr key={idx} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-3 px-4 font-bold text-slate-900 bg-slate-50/50">{row.field}</td>
                      <td className="py-3 px-4 font-semibold text-slate-900">{row.value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {topCandidates.length > 0 && (
            <div>
              <h4 className="text-[15px] font-bold text-slate-900 mb-3">Các kết quả có khả năng phù hợp</h4>
              <div className="overflow-x-auto border border-slate-200 rounded-md shadow-xs">
                <table className="w-full text-left text-[13px] border-collapse">
                  <thead>
                    <tr className="bg-slate-100 text-slate-700 font-bold border-b border-slate-200 text-[12.5px]">
                      <th className="py-2.5 px-4">Tên/Đơn vị</th>
                      <th className="py-2.5 px-4">Tổ chức</th>
                      <th className="py-2.5 px-4 text-right">Điểm</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {topCandidates.map((c, idx) => (
                      <tr key={idx}>
                        <td className="py-2.5 px-4">{c.full_name || c.canonical_name || c.canonical_unit_name || 'Chưa có'}</td>
                        <td className="py-2.5 px-4">{c.organization_type || 'Chưa có'}</td>
                        <td className="py-2.5 px-4 text-right font-mono">{typeof c.score === 'number' ? `${Math.round(c.score)}%` : (c.score ?? 'Chưa có')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {eligibility.length > 0 && (
            <div>
              <h4 className="text-[15px] font-bold text-slate-900 mb-3">Đánh giá chế độ, chính sách</h4>
              <div className="overflow-x-auto border border-slate-200 rounded-md shadow-xs">
                <table className="w-full text-left text-[13px] border-collapse">
                  <thead>
                    <tr className="bg-slate-100 text-slate-700 font-bold border-b border-slate-200 text-[12.5px]">
                      <th className="py-2.5 px-4">Quy định</th>
                      <th className="py-2.5 px-4">Kết luận</th>
                      <th className="py-2.5 px-4">Phiên bản</th>
                      <th className="py-2.5 px-4">Lý do</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {eligibility.map((e, idx) => (
                      <tr key={idx}>
                        <td className="py-2.5 px-4 font-semibold">{e.policy_id}</td>
                        <td className="py-2.5 px-4">{POLICY_STATUS_LABELS[e.status] || 'Chưa xác định'}</td>
                        <td className="py-2.5 px-4 font-mono text-[12px]">{e.policy_version || 'Chưa có'}</td>
                        <td className="py-2.5 px-4 text-slate-600">{e.reason || 'Chưa có'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer Actions */}
        <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3 flex-shrink-0">
          <div className="text-[12px] text-slate-500">
            Toàn bộ dữ liệu được lấy trực tiếp từ hồ sơ hệ thống. Quyết định nghiệp vụ được thực hiện tại hàng đợi thẩm định.
          </div>

          <div className="flex items-center gap-2.5 w-full sm:w-auto justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-md bg-red-600 hover:bg-red-700 text-white text-[13px] font-semibold transition-colors shadow-xs cursor-pointer"
            >
              Đóng
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
