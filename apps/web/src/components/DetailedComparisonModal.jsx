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
  AMBIGUOUS: 'Chưa đủ căn cứ',
  NOT_FOUND: 'Không tìm thấy',
  CONFLICT: 'Thông tin mâu thuẫn',
  UNKNOWN: 'Chưa xác định',
};

const MATCH_METHOD_LABELS = {
  EXACT_CODE: 'Khớp chính xác theo mã',
  EXACT_NAME: 'Khớp chính xác theo tên',
  CANONICAL_EXACT: 'Khớp chính xác theo tên chuẩn',
  APPROVED_ALIAS: 'Khớp theo tên gọi đã phê duyệt',
  ASCII_FOLDED: 'Khớp tên không dấu',
  ASCII_FOLDED_ALIAS: 'Khớp tên gọi không dấu',
  TRUSTED_CODE: 'Khớp theo mã đơn vị',
  HYBRID_FUZZY_BM25_SEMANTIC: 'Đối chiếu tổng hợp',
  TOP_RANKED_HIGH_CONFIDENCE: 'Kết quả phù hợp nhất',
};

const POLICY_STATUS_LABELS = {
  ELIGIBLE: 'Đủ điều kiện',
  NOT_ELIGIBLE: 'Không đủ điều kiện',
  INSUFFICIENT_DATA: 'Chưa đủ dữ liệu',
  UNKNOWN: 'Chưa xác định',
};

export default function DetailedComparisonModal({ isOpen, onClose, caseDetail }) {
  if (!isOpen) return null;

  const detail = caseDetail || {};
  const subject = detail.subject || {};
  const result = detail.result || {};
  const eligibility = Array.isArray(detail.eligibility) ? detail.eligibility : [];
  const topCandidates = Array.isArray(result.top_candidates) ? result.top_candidates : [];
  const preferredCandidate = topCandidates[0] || null;
  const orgType = detail.organization_type || 'UNKNOWN';
  const isMatched = detail.resolution_status === 'MATCHED';
  const inScope =
    typeof detail.in_scope === 'boolean'
      ? detail.in_scope
      : isMatched && ['BCA', 'BQP'].includes(orgType)
        ? true
        : isMatched && orgType === 'OTHER'
          ? false
          : null;
  const conclusion =
    inScope === true
      ? `Đơn vị thuộc ${ORG_LABELS[orgType] || 'phạm vi BCA/BQP'}`
      : inScope === false
        ? 'Đơn vị không thuộc Bộ Quốc phòng hay Bộ Công an'
        : 'Chưa có kết luận';
  const caseId = detail.case?.id || '';
  const caseCode = caseId
    ? `#HS-2026-${String(caseId).replace(/^case_/i, '').slice(0, 8).toUpperCase()}`
    : 'Chưa có';

  const comparisonRows = [
    { field: 'Họ và tên', value: subject.name || 'Chưa cung cấp' },
    { field: 'Chức vụ', value: subject.position || 'Chưa cung cấp' },
    { field: 'Mã định danh', value: subject.code || 'Chưa cung cấp' },
    { field: 'Đơn vị hiện tại', value: detail.current_unit || 'Chưa xác định' },
    { field: 'Cơ quan quản lý', value: ORG_LABELS[orgType] || ORG_LABELS.UNKNOWN },
    { field: 'Trạng thái', value: STATUS_LABELS[detail.resolution_status] || 'Chưa xác định' },
    { field: 'Cách đối chiếu', value: MATCH_METHOD_LABELS[result.match_method] || 'Đối chiếu tự động' },
    { field: 'Nhóm đối tượng', value: detail.subject_group || 'Chưa xác định' },
  ];

  const preferredName =
    preferredCandidate?.full_name ||
    preferredCandidate?.canonical_name ||
    preferredCandidate?.canonical_unit_name ||
    null;
  const preferredOrg = preferredCandidate?.organization_type || 'UNKNOWN';
  const preferredUnitId = preferredCandidate?.unit_id || preferredCandidate?.canonical_unit_id || null;

  return (
    <div className="modal modal-open" role="dialog" aria-modal="true" aria-labelledby="comparison-modal-title">
      <div className="modal-box flex max-h-[94vh] w-11/12 max-w-5xl flex-col overflow-hidden bg-white p-0 text-black">
        <header className="flex shrink-0 items-center justify-between border-b border-base-300 px-5 py-4">
          <div className="min-w-0">
            <h3 id="comparison-modal-title" className="truncate text-lg font-bold">
              Thông tin chi tiết
            </h3>
            <p className="mt-0.5 truncate text-sm text-base-content/60">
              Mã hồ sơ: <span className="font-mono font-semibold">{caseCode}</span>
              {subject.name ? ` · ${subject.name}` : ''}
            </p>
          </div>
          <button type="button" onClick={onClose} className="btn btn-circle btn-ghost btn-sm" aria-label="Đóng">
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          <div
            role="alert"
            className="alert border border-base-300 bg-white text-black"
          >
            <div>
              <p className={`text-2xl font-bold ${inScope === true ? 'text-success' : inScope === false ? 'text-error' : 'text-warning'}`}>
                {conclusion}
              </p>
            </div>
          </div>

          <section className="card card-border bg-base-100">
            <div className="card-body">
              <h4 className="card-title text-base">
                <FileText className="h-4 w-4" />
                Thông tin hồ sơ
              </h4>
              <dl className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
                {comparisonRows.map((row) => (
                  <div key={row.field} className="border-b border-base-200 pb-3">
                    <dt className="text-xs font-semibold uppercase tracking-wide text-base-content/55">
                      {row.field}
                    </dt>
                    <dd className="mt-1 font-semibold text-base-content">{row.value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </section>

          {preferredCandidate && (
            <details className="collapse collapse-arrow border border-base-300 bg-base-100">
              <summary className="collapse-title font-semibold">Thông tin đối chiếu bổ sung</summary>
              <div className="collapse-content">
                <p className="mb-3 text-sm text-base-content/70">
                  {isMatched
                    ? 'Hệ thống sử dụng kết quả phù hợp nhất để đưa ra kết luận; không yêu cầu cán bộ chọn lại giữa các ứng viên.'
                    : 'Kết quả gần nhất được giữ làm căn cứ tham khảo; dữ liệu hiện có chưa đủ để kết luận.'}
                </p>
                <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-base-content/60">{isMatched ? 'Kết quả được ưu tiên' : 'Kết quả gần nhất'}</dt>
                    <dd className="font-semibold">{preferredName || 'Chưa có'}</dd>
                  </div>
                  <div>
                    <dt className="text-base-content/60">Cơ quan quản lý</dt>
                    <dd className="font-semibold">{ORG_LABELS[preferredOrg] || ORG_LABELS.UNKNOWN}</dd>
                  </div>
                  {preferredUnitId && (
                    <div>
                      <dt className="text-base-content/60">Mã đơn vị</dt>
                      <dd className="font-mono font-semibold">{preferredUnitId}</dd>
                    </div>
                  )}
                </dl>
              </div>
            </details>
          )}

          {eligibility.length > 0 && (
            <details className="collapse collapse-arrow border border-base-300 bg-base-100">
              <summary className="collapse-title font-semibold">Đánh giá chế độ, chính sách</summary>
              <div className="collapse-content space-y-3">
                {eligibility.map((item, index) => (
                  <div key={`${item.policy_id || 'policy'}-${index}`} className="rounded-box bg-base-200 p-3 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-semibold">{item.policy_id || 'Quy định'}</span>
                      <span className="badge badge-neutral badge-soft">
                        {POLICY_STATUS_LABELS[item.status] || 'Chưa xác định'}
                      </span>
                    </div>
                    {item.reason && <p className="mt-2 text-base-content/70">{item.reason}</p>}
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>

        <footer className="modal-action m-0 shrink-0 border-t border-base-300 px-5 py-4">
          <button type="button" onClick={onClose} className="btn btn-primary">
            Đóng
          </button>
        </footer>
      </div>
      <button type="button" className="modal-backdrop" onClick={onClose} aria-label="Đóng cửa sổ">
        close
      </button>
    </div>
  );
}
