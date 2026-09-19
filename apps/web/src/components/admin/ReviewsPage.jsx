import React, { useEffect, useState, useCallback, useRef } from 'react';
import axios from 'axios';
import { CheckCircle2, HelpCircle, RefreshCw, Loader2, UserCheck, UserMinus, Users, ChevronDown, ChevronUp, ListChecks } from '../../icons/index.jsx';
import PageHeader, { PageContainer } from '../layout/PageHeader.jsx';
import NotificationModal from '../NotificationModal.jsx';

const STATUS_TABS = [
  { value: 'OPEN', label: 'Đang mở' },
  { value: 'RESOLVED', label: 'Đã xử lý' },
  { value: 'DISMISSED', label: 'Đã bác bỏ' },
];

const DECISION_LABELS = {
  CONFIRM: 'Xác nhận kết quả',
  UNKNOWN: 'Chưa xác định',
  INSUFFICIENT: 'Chưa đủ thông tin',
  DISMISS: 'Bỏ qua yêu cầu',
};

const RESULT_STATUS_LABELS = {
  MATCHED: 'Đã xác định',
  AMBIGUOUS: 'Cần xác minh thêm',
  NOT_FOUND: 'Không tìm thấy',
  CONFLICT: 'Thông tin mâu thuẫn',
  PROCESSED: 'Đã xử lý',
  NEED_REVIEW: 'Cần thẩm định',
  FAILED: 'Xử lý không thành công',
};

// Why the Case was sent to review, and what the reviewer is expected to settle.
// Keys are the reason codes written by modules/cases/service.py.
const REASON_LABELS = {
  AMBIGUOUS: {
    title: 'Tên đơn vị khớp với nhiều đơn vị khác nhau',
    hint: 'Chọn đúng đơn vị công tác hiện tại trong danh sách đối chiếu bên dưới.',
  },
  NOT_FOUND: {
    title: 'Không tìm thấy đơn vị trong danh mục',
    hint: 'Đối chiếu lại tên đơn vị trên tài liệu gốc trước khi kết luận.',
  },
  CONFLICT: {
    title: 'Thông tin đơn vị mâu thuẫn giữa các nguồn',
    hint: 'Xác định đơn vị công tác hiện tại theo tài liệu gốc.',
  },
  ORGANIZATION_TYPE_UNKNOWN: {
    title: 'Chưa xác định được thuộc Bộ Công an hay Bộ Quốc phòng',
    hint: 'Đơn vị tìm được chưa gắn với tổ chức nào trong danh mục.',
  },
  DOCUMENT_PARSE_LOW_CONFIDENCE: {
    title: 'Chất lượng đọc tài liệu thấp',
    hint: 'Bản quét không rõ. Kiểm tra từng trường đã nhận dạng trước khi kết luận.',
  },
  DOCUMENT_EXTRACTION_LOW_CONFIDENCE: {
    title: 'Độ tin cậy trích xuất thông tin thấp',
    hint: 'Hệ thống không chắc về các trường đã bóc tách. Đối chiếu với tài liệu gốc.',
  },
  CURRENT_WORK_UNIT_UNCERTAIN: {
    title: 'Chưa chắc chắn đâu là đơn vị công tác hiện tại',
    hint: 'Tài liệu nhắc tới nhiều đơn vị. Xác định đơn vị hiện tại, không lấy đơn vị xuất hiện đầu tiên.',
  },
  SUBJECT_GROUP_INSUFFICIENT: {
    title: 'Chưa đủ căn cứ xác định nhóm đối tượng',
    hint: 'Bổ sung nhóm đối tượng khi ghi quyết định nếu tài liệu có căn cứ rõ ràng.',
  },
  POLICY_INSUFFICIENT_DATA: {
    title: 'Thiếu dữ kiện để áp dụng chính sách',
    hint: 'Xem phần đánh giá chính sách bên dưới để biết dữ kiện nào còn thiếu.',
  },
  PERSON_AMBIGUOUS: {
    title: 'Khớp với nhiều cá nhân trong danh mục',
    hint: 'Dùng năm sinh hoặc mã định danh để phân biệt đúng người.',
  },
  PERSON_NOT_FOUND: {
    title: 'Không tìm thấy cá nhân trong danh mục',
    hint: 'Đối chiếu lại họ tên và mã định danh trên tài liệu gốc.',
  },
  PERSON_CONFLICT: {
    title: 'Thông tin cá nhân mâu thuẫn',
    hint: 'Mã định danh và họ tên đang trỏ tới hai bản ghi khác nhau.',
  },
  MULTIPLE_SUBJECTS_OCR_UNSUPPORTED: {
    title: 'Tài liệu quét có nhiều người, hệ thống không tự tách',
    hint: 'Tách thủ công từng người thành hồ sơ riêng rồi tra cứu lại.',
  },
  MULTIPLE_SUBJECTS_AMBIGUOUS_BOUNDARY: {
    title: 'Không xác định được ranh giới giữa các hồ sơ trong tài liệu',
    hint: 'Tài liệu có nhiều người nhưng không tách được rõ ràng.',
  },
};

// How extraction.py found a given field. Unmapped rules fall through to their raw
// name rather than being hidden — a rule this build has no wording for is still
// evidence the reviewer is entitled to see.
const EVIDENCE_RULE_LABELS = {
  label_same_line: 'nhãn và giá trị trên cùng một dòng',
  inline_same_box: 'nhãn và giá trị trong cùng một ô',
  right_same_line: 'giá trị nằm bên phải nhãn',
  table_inline_cell: 'ô trong bảng',
  cccd_name_below_label: 'giá trị nằm dưới nhãn (mẫu thẻ căn cước)',
  structured_input: 'do người dùng nhập trực tiếp',
  current_marker: 'có từ khóa chỉ đơn vị hiện tại',
  single_unit_mention: 'tài liệu chỉ nhắc tới một đơn vị',
  narrative_name: 'nhận dạng từ câu văn',
  bare_name_query: 'tra cứu theo tên',
  regex_code: 'khớp mẫu mã định danh',
  regex_position: 'khớp mẫu chức vụ',
};

const QUALITY_METRIC_LABELS = {
  conf_p10: 'Độ tin cậy nhận dạng (phân vị 10)',
  conf_min: 'Độ tin cậy nhận dạng thấp nhất',
  low_conf_ratio: 'Tỷ lệ dòng có độ tin cậy thấp',
  charset_violation_ratio: 'Tỷ lệ ký tự không hợp lệ',
  diacritic_ratio: 'Tỷ lệ chữ có dấu',
  dict_hit_ratio: 'Tỷ lệ từ có trong từ điển',
  index_of_coincidence: 'Chỉ số trùng lặp ký tự',
  char_entropy: 'Độ hỗn loạn ký tự',
};

const pct = (v) => (typeof v === 'number' ? `${Math.round(v * 100)}%` : null);
const num = (v) => (typeof v === 'number' ? Number(v.toFixed(2)) : v);

function fieldEvidenceText(evidence) {
  if (!evidence || typeof evidence !== 'object') return evidence ? String(evidence) : null;
  const parts = [];
  if (evidence.rule) parts.push(EVIDENCE_RULE_LABELS[evidence.rule] || evidence.rule);
  if (typeof evidence.line === 'number') parts.push(`dòng ${evidence.line}`);
  if (typeof evidence.page === 'number') parts.push(`trang ${evidence.page}`);
  if (typeof evidence.ocr_confidence === 'number') parts.push(`độ tin cậy nhận dạng ${pct(evidence.ocr_confidence)}`);
  return parts.length > 0 ? parts.join(', ') : null;
}
const dateTime = (v) => {
  if (!v) return null;
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString('vi-VN');
};

function Field({ label, value }) {
  const empty = value === null || value === undefined || value === '';
  return (
    <div>
      <span className="font-semibold text-slate-800">{label}:</span>{' '}
      <span className={empty ? 'text-slate-400' : 'text-slate-700'}>{empty ? 'Không có' : value}</span>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <p className="font-semibold text-slate-800 mb-1">{title}</p>
      {children}
    </div>
  );
}

// A confidence reported next to the gate it was measured against, so the reviewer
// sees how far short the Case fell instead of only that it fell short.
function GatedConfidence({ label, value, threshold }) {
  const shown = pct(value);
  if (shown === null) return <Field label={label} value={null} />;
  const failed = typeof threshold === 'number' && value < threshold;
  return (
    <div>
      <span className="font-semibold text-slate-800">{label}:</span>{' '}
      <span className={failed ? 'text-red-700 font-semibold' : 'text-slate-700'}>{shown}</span>
      {typeof threshold === 'number' && (
        <span className="text-slate-400"> (ngưỡng {pct(threshold)}{failed ? ', chưa đạt' : ''})</span>
      )}
    </div>
  );
}

// Debounced live search against POST /lookup/unit for the CONFIRM decision's
// unit picker. That endpoint runs a full Resolver.resolve() per call — it is
// a resolve endpoint repurposed for autocomplete, not a dedicated one, so
// this stays a simple suggestion list rather than a polished combobox.
function UnitPicker({ apiBaseUrl, value, onChange }) {
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!query.trim() || query.trim().length < 3) {
      setSuggestions([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await axios.post(`${apiBaseUrl}/api/v1/lookup/unit`, { unit_name: query.trim() });
        const candidates = Array.isArray(res.data?.candidates) ? res.data.candidates : [];
        const best = res.data?.unit_id
          ? [{ unit_id: res.data.unit_id, canonical_name: res.data.canonical_name, organization_type: res.data.organization_type, score: 100 }]
          : [];
        setSuggestions([...best, ...candidates].slice(0, 8));
      } catch {
        setSuggestions([]);
      } finally {
        setSearching(false);
      }
    }, 350);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query, apiBaseUrl]);

  return (
    <div className="relative">
      <input
        value={value ? `${value}` : query}
        onChange={(e) => { onChange(''); setQuery(e.target.value); }}
        placeholder="Nhập tên đơn vị để tìm kiếm"
        className="w-full text-xs border border-slate-200 rounded-md px-2.5 py-1.5 outline-none focus:border-red-400"
      />
      {searching && <Loader2 className="w-3.5 h-3.5 animate-spin absolute right-2 top-1.5 text-slate-400" />}
      {suggestions.length > 0 && !value && (
        <div className="absolute z-10 mt-1 w-full bg-white border border-slate-200 rounded-md shadow-lg max-h-48 overflow-y-auto">
          {suggestions.map((c, idx) => (
            <button
              key={`${c.unit_id}-${idx}`}
              type="button"
              onClick={() => { onChange(c.unit_id); setQuery(c.canonical_name || c.unit_id); setSuggestions([]); }}
              className="w-full text-left px-2.5 py-1.5 text-xs hover:bg-red-50 border-b border-slate-100 last:border-0"
            >
              <span className="font-semibold text-slate-800">{c.canonical_name || c.unit_id}</span>
              <span className="text-slate-400"> ({c.organization_type}, điểm {num(c.score)})</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function DecisionForm({ item, apiBaseUrl, onDone, onConflict }) {
  const [decision, setDecision] = useState('CONFIRM');
  const [unitId, setUnitId] = useState('');
  const [subjectGroup, setSubjectGroup] = useState('');
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await axios.post(`${apiBaseUrl}/api/v1/reviews/${item.id}/decision`, {
        decision,
        unit_id: unitId || null,
        subject_group: subjectGroup || null,
        note,
        expected_version: item.version,
      });
      onDone();
    } catch (e) {
      if (e?.response?.status === 409) {
        onConflict();
        return;
      }
      setError(e?.response?.data?.detail?.message || e?.response?.data?.detail || e.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mt-3 pt-3 border-t border-slate-100 space-y-2.5">
      <NotificationModal open={Boolean(error)} title="Không thể ghi quyết định" message={error} onClose={() => setError(null)} />
      <div className="flex flex-wrap gap-2">
        {['CONFIRM', 'UNKNOWN', 'INSUFFICIENT', 'DISMISS'].map((d) => (
          <button
            key={d}
            onClick={() => setDecision(d)}
            className={`px-3 py-1.5 rounded-md text-xs font-semibold border transition-colors ${
              decision === d ? 'bg-red-600 border-red-600 text-white' : 'bg-white border-slate-200 text-slate-600 hover:border-slate-300'
            }`}
          >
            {DECISION_LABELS[d]}
          </button>
        ))}
      </div>
      {decision === 'CONFIRM' && (
        <div className="grid grid-cols-2 gap-2">
          <UnitPicker apiBaseUrl={apiBaseUrl} value={unitId} onChange={setUnitId} />
          <input
            value={subjectGroup}
            onChange={(e) => setSubjectGroup(e.target.value)}
            placeholder="Nhóm đối tượng (không bắt buộc)"
            className="text-xs border border-slate-200 rounded-md px-2.5 py-1.5 outline-none focus:border-red-400"
          />
        </div>
      )}
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Ghi chú thẩm định"
        rows={2}
        className="w-full text-xs border border-slate-200 rounded-md px-2.5 py-1.5 outline-none focus:border-red-400 resize-none"
      />
      <button
        onClick={submit}
        disabled={submitting}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-900 text-white text-xs font-semibold disabled:opacity-50"
      >
        {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
        Ghi quyết định
      </button>
    </div>
  );
}

function ReassignForm({ item, apiBaseUrl, isAdmin, currentUsername, onDone, onConflict }) {
  const [assignee, setAssignee] = useState(item.assigned_to || '');
  const [coverageGroup, setCoverageGroup] = useState(item.coverage_group || '');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const assign = async (body) => {
    setSubmitting(true);
    setError(null);
    try {
      await axios.post(`${apiBaseUrl}/api/v1/reviews/${item.id}/assign`, {
        ...body,
        expected_version: item.version,
      });
      onDone();
    } catch (e) {
      if (e?.response?.status === 409) {
        onConflict();
        return;
      }
      setError(e?.response?.data?.detail?.message || e?.response?.data?.detail || e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const isMine = item.assigned_to === currentUsername;
  const isUnclaimed = !item.assigned_to;

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      {isUnclaimed && (
        <button
          onClick={() => assign({ assigned_to: currentUsername })}
          disabled={submitting}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-semibold hover:bg-emerald-100 disabled:opacity-50"
        >
          <UserCheck className="w-3.5 h-3.5" /> Nhận xử lý
        </button>
      )}
      {isMine && (
        <button
          onClick={() => assign({ assigned_to: null })}
          disabled={submitting}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-50 text-slate-600 border border-slate-200 text-xs font-semibold hover:bg-slate-100 disabled:opacity-50"
        >
          <UserMinus className="w-3.5 h-3.5" /> Trả lại hàng đợi
        </button>
      )}
      {isAdmin && (
        <div className="flex items-center gap-1.5">
          <input
            value={assignee}
            onChange={(e) => setAssignee(e.target.value)}
            placeholder="Chuyển cho (username)"
            className="text-xs border border-slate-200 rounded-md px-2 py-1 w-36 outline-none focus:border-red-400"
          />
          <input
            value={coverageGroup}
            onChange={(e) => setCoverageGroup(e.target.value)}
            placeholder="coverage_group"
            className="text-xs border border-slate-200 rounded-md px-2 py-1 w-28 outline-none focus:border-red-400"
          />
          <button
            onClick={() => assign({ assigned_to: assignee || null, coverage_group: coverageGroup || undefined })}
            disabled={submitting}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-red-50 text-red-700 border border-red-200 text-xs font-semibold hover:bg-red-100 disabled:opacity-50"
          >
            <Users className="w-3.5 h-3.5" /> Chuyển
          </button>
        </div>
      )}
      <NotificationModal open={Boolean(error)} title="Không thể phân công xử lý" message={error} onClose={() => setError(null)} />
    </div>
  );
}

// The queue row's headline: who the review is about and what has to be settled.
// Falls back to the raw reason code when a Case was flagged for a reason this
// build has no wording for, rather than hiding it.
function ReviewSummary({ item }) {
  const subject = item.payload?.subject || {};
  const facts = [
    subject.subject_code ? `Mã định danh: ${subject.subject_code}` : null,
    subject.birth_year ? `Năm sinh: ${subject.birth_year}` : null,
    subject.position ? `Chức vụ: ${subject.position}` : null,
  ].filter(Boolean);
  const reason = REASON_LABELS[item.reason];

  return (
    <div>
      <p className="text-sm font-bold text-slate-900 truncate">
        {subject.name || 'Chưa nhận dạng được đối tượng'}
      </p>
      {facts.length > 0 && (
        <div className="flex flex-wrap gap-x-4 text-[11.5px] text-slate-500 mt-0.5">
          {facts.map((fact) => (
            <span key={fact}>{fact}</span>
          ))}
        </div>
      )}
      <div className="mt-1.5 border-l-2 border-amber-500 pl-2.5">
        <p className="text-xs font-semibold text-slate-800">{reason?.title || item.reason}</p>
        {reason?.hint && <p className="text-[11.5px] text-slate-500 mt-0.5">{reason.hint}</p>}
      </div>
    </div>
  );
}

function ReviewDetailPanel({ item, apiBaseUrl }) {
  const [full, setFull] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const payload = item.payload || {};
  const candidates = Array.isArray(payload.top_candidates) ? payload.top_candidates : [];

  const loadFull = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${apiBaseUrl}/api/v1/cases/${item.case_id}`);
      setFull(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  const subject = payload.subject || {};
  const resolution = payload.resolution || {};
  const confidence = payload.confidence || {};
  const thresholds = payload.thresholds || {};
  const caseInfo = payload.case || {};
  const parseQuality = payload.parse_quality || {};
  const fieldConfidence = payload.field_confidence || {};
  const fieldEvidence = payload.field_evidence || {};
  const businessFields = payload.business_fields || {};
  const personResolution = payload.person_resolution || null;
  const formerUnits = Array.isArray(payload.former_units) ? payload.former_units : [];
  // FAIL first: the metric that sent the Case here is the one being looked for.
  const qualityMetrics = Object.entries(parseQuality.metrics || {}).sort(
    ([, a], [, b]) => (a?.state === 'FAIL' ? 0 : 1) - (b?.state === 'FAIL' ? 0 : 1),
  );
  const batchWarnings = Array.isArray(payload.batch_warnings) ? payload.batch_warnings : [];

  return (
    <div className="mt-3 pt-3 border-t border-slate-100 space-y-3.5 text-xs">
      <p className="text-slate-400">
        Dữ liệu dưới đây được lưu tại thời điểm hồ sơ được chuyển sang thẩm định.
      </p>

      <Section title="Thông tin đối tượng">
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          <Field label="Họ và tên" value={subject.name} />
          <Field label="Mã định danh" value={subject.subject_code} />
          <Field label="Năm sinh" value={subject.birth_year} />
          <Field label="Chức vụ" value={subject.position} />
        </div>
      </Section>

      <Section title="Đơn vị ghi trên tài liệu">
        <div className="space-y-1">
          <Field label="Đơn vị hiện tại" value={payload.current_unit_raw} />
          <Field label="Đơn vị từng công tác" value={formerUnits.length > 0 ? formerUnits.join(', ') : null} />
        </div>
      </Section>

      <Section title="Kết quả đối soát tự động">
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          <Field label="Trạng thái" value={RESULT_STATUS_LABELS[resolution.status] || resolution.status} />
          <Field label="Tổ chức" value={resolution.organization_type} />
          <Field label="Đơn vị chuẩn hóa" value={resolution.canonical_name} />
          <Field label="Mã đơn vị" value={resolution.unit_id} />
          <Field label="Cách đối chiếu" value={resolution.match_method} />
          <Field label="Điểm đối chiếu" value={num(resolution.score)} />
          <Field label="Khoảng cách với ứng viên kế tiếp" value={num(resolution.margin)} />
          <Field label="Phiên bản danh mục" value={resolution.registry_version} />
          <Field label="Nhóm đối tượng" value={payload.subject_group} />
          <Field label="Cách xác định nhóm" value={payload.subject_group_method} />
        </div>
      </Section>

      <Section title="Độ tin cậy so với ngưỡng">
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          <GatedConfidence label="Trích xuất thông tin" value={confidence.extraction} threshold={thresholds.extraction_min} />
          <GatedConfidence label="Đọc tài liệu" value={payload.parse_confidence} threshold={thresholds.parse_min} />
          <GatedConfidence label="Xác định đơn vị hiện tại" value={confidence.relation} threshold={0.7} />
          <Field label="Đối chiếu đơn vị" value={pct(confidence.resolution)} />
          <Field label="Nhóm đối tượng" value={pct(confidence.subject_group)} />
          <Field label="Kết luận tổng hợp" value={pct(confidence.decision)} />
        </div>
      </Section>

      <Section title="Chất lượng đọc tài liệu">
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          <Field label="Cách đọc" value={payload.parse_method} />
          <Field label="Kết quả kiểm tra chất lượng" value={parseQuality.gate_result} />
          <Field label="Phiên bản ngưỡng" value={parseQuality.threshold_version || thresholds.threshold_version} />
        </div>
        {parseQuality.critical_disagreement === true && (
          <div className="mt-1.5 text-red-700 font-semibold">
            Hai bộ nhận dạng đọc ra thông tin định danh khác nhau. Không dùng kết quả nhận dạng làm căn cứ, phải đối chiếu tài liệu gốc.
          </div>
        )}
        {qualityMetrics.length > 0 && (
          <div className="mt-1.5 border border-slate-200 rounded-md overflow-hidden">
            {qualityMetrics.map(([name, metric]) => (
              <div key={name} className="flex items-start justify-between gap-3 px-2.5 py-1.5 border-b border-slate-100 last:border-0 bg-white">
                <div className="min-w-0">
                  <div className="font-medium text-slate-700">{QUALITY_METRIC_LABELS[name] || name}</div>
                  {metric.reason && <div className="text-slate-400">{metric.reason}</div>}
                </div>
                <div className="flex-shrink-0 text-right">
                  <div className={metric.state === 'FAIL' ? 'text-red-700 font-semibold' : 'text-slate-500'}>
                    {metric.state}
                  </div>
                  {metric.value !== null && metric.value !== undefined && (
                    <div className="text-slate-400">
                      {typeof metric.value === 'number' ? metric.value.toFixed(3) : String(metric.value)}
                      {metric.threshold ? ` (ngưỡng ${metric.threshold})` : ''}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>

      {Object.keys(fieldConfidence).length > 0 && (
        <Section title="Độ tin cậy từng trường">
          <div className="border border-slate-200 rounded-md overflow-hidden">
            {Object.entries(fieldConfidence).map(([field, value]) => (
              <div key={field} className="flex items-start justify-between gap-3 px-2.5 py-1.5 border-b border-slate-100 last:border-0 bg-white">
                <div className="min-w-0">
                  <div className="font-medium text-slate-700">{field}</div>
                  {fieldEvidenceText(fieldEvidence[field]) && (
                    <div className="text-slate-400 break-words">Căn cứ: {fieldEvidenceText(fieldEvidence[field])}</div>
                  )}
                </div>
                <span className={typeof value === 'number' && value < 0.7 ? 'text-red-700 font-semibold flex-shrink-0' : 'text-slate-500 flex-shrink-0'}>
                  {pct(value) ?? String(value)}
                </span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {personResolution && (
        <Section title="Đối chiếu cá nhân trong danh mục">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            <Field label="Trạng thái" value={RESULT_STATUS_LABELS[personResolution.status] || personResolution.status} />
            <Field label="Cách đối chiếu" value={personResolution.match_method} />
            <Field label="Điểm đối chiếu" value={num(personResolution.score)} />
            <Field label="Phiên bản danh mục" value={personResolution.registry_version} />
          </div>
        </Section>
      )}

      {Object.keys(businessFields).length > 0 && (
        <Section title="Dữ kiện nghiệp vụ đã nhận">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            {Object.entries(businessFields).map(([field, value]) => (
              <Field
                key={field}
                label={field}
                value={typeof value === 'object' && value !== null ? JSON.stringify(value) : value}
              />
            ))}
          </div>
        </Section>
      )}

      {batchWarnings.length > 0 && (
        <Section title="Cảnh báo khi tiếp nhận">
          <div className="border border-amber-200 bg-[#FDF0BE]/50 rounded-md overflow-hidden">
            {batchWarnings.map((w, idx) => (
              <div key={idx} className="px-2.5 py-1.5 border-b border-amber-200/60 last:border-0 text-amber-900">
                <span className="font-semibold">{w.code}</span>
                {w.message_vi ? <span> {w.message_vi}</span> : null}
                {w.column ? <span className="text-amber-700"> (cột {w.column})</span> : null}
              </div>
            ))}
          </div>
        </Section>
      )}

      {candidates.length > 0 && (
        <Section title="Các đơn vị/cá nhân được đối chiếu">
          <div className="border border-slate-200 rounded-md overflow-hidden">
            {candidates.slice(0, 5).map((c, idx) => (
              <div key={idx} className="flex items-center justify-between gap-3 px-2.5 py-1.5 border-b border-slate-100 last:border-0 bg-white">
                <span className="min-w-0 truncate">{c.full_name || c.canonical_name || c.canonical_unit_name || 'Không rõ tên'}</span>
                <span className="text-slate-400 flex-shrink-0">
                  {c.organization_type ? `${c.organization_type}, ` : ''}điểm {num(c.score) ?? 'không có'}
                </span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {Array.isArray(payload.policy_assessments) && payload.policy_assessments.length > 0 && (
        <Section title="Đánh giá chính sách">
          <div className="border border-slate-200 rounded-md overflow-hidden">
            {payload.policy_assessments.map((a, idx) => (
              <div key={idx} className="px-2.5 py-1.5 border-b border-slate-100 last:border-0 bg-white">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-medium">{a.policy_id}</span>
                  <span className="text-slate-500 flex-shrink-0">{a.status}</span>
                </div>
                {a.reason && <div className="text-slate-400">{a.reason}</div>}
              </div>
            ))}
          </div>
        </Section>
      )}

      <Section title="Nguồn hồ sơ">
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          <Field label="Người tạo" value={caseInfo.created_by} />
          <Field label="Hình thức tiếp nhận" value={caseInfo.input_type} />
          <Field label="Thời điểm tiếp nhận" value={dateTime(caseInfo.created_at)} />
          <Field label="Ngày hiệu lực xét" value={payload.as_of_date} />
          {payload.bulk_source && <Field label="Nguồn nhập theo lô" value={JSON.stringify(payload.bulk_source)} />}
          {payload.split_source && <Field label="Tách từ tài liệu nhiều người" value={JSON.stringify(payload.split_source)} />}
        </div>
      </Section>

      {!full && (
        <button
          onClick={loadFull}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-slate-200 text-slate-600 text-xs font-semibold hover:bg-slate-50 disabled:opacity-50"
        >
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
          Xem thông tin hồ sơ mới nhất
        </button>
      )}
      <NotificationModal open={Boolean(error)} title="Không thể tải hồ sơ" message={error} onClose={() => setError(null)} />
      {full && (
        <div className="border border-red-200 bg-red-50/40 rounded-md p-2.5 space-y-1.5">
          <p className="font-semibold text-red-800">Thông tin mới nhất, có thể khác dữ liệu ban đầu nếu hồ sơ đã được xử lý lại</p>
          <div className="grid grid-cols-2 gap-2 text-slate-700">
            <Field label="Kết quả" value={RESULT_STATUS_LABELS[full.resolution_status] || full.resolution_status} />
            <Field label="Tổ chức" value={full.organization_type} />
            <Field label="Đơn vị hiện tại" value={full.current_unit} />
            <Field label="Trạng thái hồ sơ" value={RESULT_STATUS_LABELS[full.case?.workflow_status] || full.case?.workflow_status} />
          </div>
        </div>
      )}
    </div>
  );
}

const PAGE_SIZE = 50;

export function ReviewsPage({ apiBaseUrl, user }) {
  const [status, setStatus] = useState('OPEN');
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [detailId, setDetailId] = useState(null);
  const [conflictBanner, setConflictBanner] = useState(false);

  // Renders the admin-only reassign form. The server enforces the same rule
  // independently in POST /reviews/{id}/assign, which refuses a coverage-group
  // change or a third-party assignment from a non-administrator.
  const isAdmin = !!user?.isAdmin;
  const currentUsername = user?.username;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${apiBaseUrl}/api/v1/reviews`, { params: { status, page, page_size: PAGE_SIZE } });
      setItems(res.data?.items || []);
      setTotal(res.data?.total || 0);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }, [apiBaseUrl, status, page]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setPage(1); }, [status]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const handleConflict = () => {
    setConflictBanner(true);
    load();
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <PageContainer className="py-3 sm:py-4">
        <PageHeader
          trail={[{ label: 'Trang chủ' }, { label: 'Quản trị' }]}
          title="Hàng đợi thẩm định"
          description="Các hồ sơ cần cán bộ kiểm tra vì hệ thống chưa đủ căn cứ để tự kết luận."
          icon={ListChecks}
          actions={
            <button onClick={load} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-slate-300 bg-white text-xs font-medium text-slate-700 hover:bg-slate-50">
              <RefreshCw className="w-4 h-4" /> Tải lại
            </button>
          }
        />

        <NotificationModal
          open={conflictBanner}
          title="Hồ sơ đã được xử lý"
          message="Hồ sơ đã được người khác cập nhật. Dữ liệu mới nhất đã được tải lại. Vui lòng kiểm tra lại trước khi thao tác tiếp."
          tone="warning"
          onClose={() => setConflictBanner(false)}
        />

        <div className="flex gap-1.5 mb-4">
          {STATUS_TABS.map((t) => (
            <button
              key={t.value}
              onClick={() => setStatus(t.value)}
              className={`px-3.5 py-1.5 rounded-md text-sm font-semibold transition-colors ${
                status === t.value ? 'bg-red-600 text-white' : 'bg-white text-slate-600 border border-slate-200 hover:border-slate-300'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <NotificationModal open={Boolean(error)} title="Không thể tải hàng đợi" message={error} onClose={() => setError(null)} />

        {loading ? (
          <div className="flex items-center gap-3 text-slate-500 text-sm py-10 justify-center">
            <Loader2 className="w-4 h-4 animate-spin" /> Đang tải
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-slate-400">
            <HelpCircle className="w-8 h-8 mb-2" />
            <p className="text-sm">Không có hồ sơ thẩm định nào ở trạng thái này.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {items.map((item) => (
              <div key={item.id} className="bg-white border border-slate-200 rounded-md p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <ReviewSummary item={item} />
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1.5 text-[11.5px] text-slate-500">
                      <span>Hồ sơ #{String(item.case_id ?? '').replace(/^case_/i, '').slice(0, 8).toUpperCase()}</span>
                      <span>Tiếp nhận: {dateTime(item.created_at) || 'Không rõ'}</span>
                      {item.coverage_group && <span>Phạm vi: {item.coverage_group}</span>}
                      <span>{item.assigned_to ? `Đang xử lý: ${item.assigned_to}` : 'Chưa có người nhận'}</span>
                    </div>
                    {item.status && item.status !== 'OPEN' && (
                      <div className="mt-2 border-l-2 border-slate-300 pl-2.5 text-[11.5px] text-slate-600">
                        <div>
                          {item.status === 'DISMISSED' ? 'Đã bác bỏ' : 'Đã xử lý'} bởi{' '}
                          <span className="font-semibold text-slate-800">{item.reviewed_by || 'không rõ'}</span>
                          {dateTime(item.reviewed_at) ? ` lúc ${dateTime(item.reviewed_at)}` : ''}
                        </div>
                        <div className="text-slate-500">
                          Ghi chú: {item.decision_note ? item.decision_note : 'không có'}
                        </div>
                      </div>
                    )}
                    {status === 'OPEN' && (
                      <ReassignForm
                        item={item}
                        apiBaseUrl={apiBaseUrl}
                        isAdmin={isAdmin}
                        currentUsername={currentUsername}
                        onDone={load}
                        onConflict={handleConflict}
                      />
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
                    <button
                      onClick={() => setDetailId(detailId === item.id ? null : item.id)}
                      className="text-xs font-semibold text-slate-500 hover:text-slate-700 flex items-center gap-1"
                    >
                      {detailId === item.id ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                      Chi tiết
                    </button>
                    {status === 'OPEN' && (
                      <button
                        onClick={() => setOpenId(openId === item.id ? null : item.id)}
                        className="text-xs font-semibold text-red-600 hover:text-red-700"
                      >
                        {openId === item.id ? 'Đóng' : 'Xử lý'}
                      </button>
                    )}
                  </div>
                </div>
                {detailId === item.id && <ReviewDetailPanel item={item} apiBaseUrl={apiBaseUrl} />}
                {openId === item.id && (
                  <DecisionForm
                    item={item}
                    apiBaseUrl={apiBaseUrl}
                    onDone={() => { setOpenId(null); load(); }}
                    onConflict={handleConflict}
                  />
                )}
              </div>
            ))}
          </div>
        )}

        {!loading && total > PAGE_SIZE && (
          <div className="flex items-center justify-between mt-4 text-sm text-slate-600">
            <span>
              Trang {page}/{totalPages}, {total} hồ sơ (cũ nhất trước)
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-3 py-1.5 rounded-md border border-slate-200 text-slate-600 font-semibold disabled:opacity-40 hover:bg-slate-50"
              >
                Trước
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="px-3 py-1.5 rounded-md border border-slate-200 text-slate-600 font-semibold disabled:opacity-40 hover:bg-slate-50"
              >
                Sau
              </button>
            </div>
          </div>
        )}
      </PageContainer>
    </div>
  );
}
