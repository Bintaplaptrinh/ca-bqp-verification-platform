import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import {
  Shield,
  ShieldCheck,
  Search,
  Clock,
  ChevronDown,
  User,
  Calendar,
  Briefcase,
  Building2,
  Hash,
  RotateCcw,
  UploadCloud,
  FileCheck,
  FolderOpen,
  Scan,
  X,
  Database,
  Cpu,
  Lock,
  Edit3,
  ArrowLeft,
  MoreVertical,
  Download,
  Share2,
  Check,
  Info,
  Award,
  Loader2,
  CheckCircle2,
  Server,
  AlertTriangle,
  HelpCircle,
  Eye,
  ArrowRight,
  CreditCard,
  FileText,
  UserCheck,
  AlertCircle,
  Settings,
  LogOut,
  ExternalLink,
  Layers,
  Image as ImageIcon,
  FileImage,
  ChevronRight,
} from '../icons/index.jsx';
import AppHeader from './layout/AppHeader.jsx';
import AppNavigation from './layout/AppNavigation.jsx';
import AppFooter from './layout/AppFooter.jsx';
import PageHeader, { PageContainer } from './layout/PageHeader.jsx';

import OriginalDossierModal from './OriginalDossierModal.jsx';
import DetailedComparisonModal from './DetailedComparisonModal.jsx';
import HistoryView from './HistoryView.jsx';
import OcrResultModal from './OcrResultModal.jsx';
import { ReviewsPage } from './admin/ReviewsPage.jsx';
import { RegistryAdminPage } from './admin/RegistryAdminPage.jsx';
import { PersonRegistryAdminPage } from './admin/PersonRegistryAdminPage.jsx';
import { AuditPage } from './admin/AuditPage.jsx';
import { UsersAdminPage } from './admin/UsersAdminPage.jsx';
import { can, getAccessToken } from '../auth.ts';
import { P } from '../permissions.ts';

// Default FastAPI backend URL
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// Builds the same currentCaseData shape from a real GET /cases/{id} response,
// shared by the live-search success path and the History "Xem lại" reopen
// path so there is exactly one place that maps backend fields to UI state.
function buildCaseResultFromDetail(caseId, caseDetail) {
  const res = caseDetail?.result;
  const extracted = caseDetail?.extracted || {};
  return {
    case_code: `#HS-2026-${String(caseId).replace(/^case_/i, '').slice(0, 8).toUpperCase()}`,
    case_id: caseId,
    organization_type: caseDetail?.organization_type || res?.organization_type || 'OTHER',
    resolution_status: caseDetail?.resolution_status || res?.resolution_status || 'MATCHED',
    workflow_status: caseDetail?.case?.workflow_status || caseDetail?.workflow_status || 'PROCESSED',
    unit_id: res?.unit_id,
    current_unit: caseDetail?.current_unit || res?.evidence?.canonical_name || '',
    fullName: caseDetail?.subject?.name || extracted.subject_name || '',
    subject_group: caseDetail?.subject_group || null,
    subject_group_method: res?.evidence?.subject_group_method || null,
    subject_group_confidence: res?.evidence?.subject_group_confidence ?? null,
    taxonomy_version: res?.taxonomy_version || null,
    salary_status: caseDetail?.salary_status || 'Không đủ dữ liệu',
    score: res?.score ? `${Math.round(res.score * 100)}%` : 'Chưa có',
    evidence: res?.evidence || [],
    topCandidates: Array.isArray(res?.top_candidates) ? res.top_candidates : [],
    eligibility: Array.isArray(caseDetail?.eligibility) ? caseDetail.eligibility : [],
  };
}

// Why subject_group came out null/positive — surfaced in the UI instead of a
// blank "Chưa xác định", per the classifier's own abstain reasons
// (subject_group/service.py). UI-transparency only: this never changes what
// the classifier decides, only how its decision is explained.
const SUBJECT_GROUP_METHOD_LABELS = {
  INSUFFICIENT_EVIDENCE: 'Không đủ căn cứ văn bản để phân loại nhóm đối tượng',
  INVALID_EXPLICIT_GROUP: 'Giá trị nhóm đối tượng khai báo không hợp lệ',
  RULE_TEXT: 'Suy luận từ từ khóa trong văn bản',
  EXPLICIT_FIELD: 'Khai báo trực tiếp trong hồ sơ',
};

const ROLE_LABELS = {
  USER: 'Cán bộ tra cứu',
  REVIEWER: 'Cán bộ thẩm định',
  ADMIN: 'Quản trị viên',
};

const SOURCE_KIND_LABELS = {
  MASTER_REGISTRY: 'Danh mục đơn vị nghiệp vụ',
  PERSON_REGISTRY: 'Danh mục đối tượng nghiệp vụ',
  PROVIDED: 'Nguồn được cung cấp',
  IMPORTED: 'Dữ liệu nhập vào',
};

const POLICY_STATUS_LABELS = {
  ELIGIBLE: 'Đủ điều kiện',
  NOT_ELIGIBLE: 'Không đủ điều kiện',
  INSUFFICIENT_DATA: 'Chưa đủ dữ liệu',
  UNKNOWN: 'Chưa xác định',
};

function resolvedStateFromDetail(caseDetail) {
  const res = caseDetail?.result;
  const org = caseDetail?.organization_type || res?.organization_type || 'OTHER';
  if (caseDetail?.resolution_status === 'MATCHED' && (org === 'BCA' || org === 'BQP')) return 'verified';
  if (caseDetail?.resolution_status === 'AMBIGUOUS' || caseDetail?.case?.workflow_status === 'NEED_REVIEW') return 'needs-verification';
  return 'no-conclusion';
}

// Attach the session token to every request. The token is an opaque session
// id: it says who is calling, never what they may do. The server reads the
// account's permissions on each request and answers 403 on its own.
axios.interceptors.request.use((cfg) => {
  const token = getAccessToken();
  if (token) cfg.headers = { ...cfg.headers, Authorization: `Bearer ${token}` };
  return cfg;
});

// A session the server has ended (logout elsewhere, deactivated account,
// expiry) must not leave the UI pretending to be signed in.
axios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) window.location.reload();
    return Promise.reject(error);
  }
);

// Initial history starts completely clean and dynamically records user operations or backend cases
const DEFAULT_HISTORY = [];

function UploadStatusBadge({ data, compact = false }) {
  const confidence = data?.confidence && data.confidence !== 'Chưa có' ? data.confidence : null;
  const confidenceNumber = confidence ? Number.parseFloat(String(confidence).replace('%', '')) : null;
  const qualityLabel = Number.isFinite(confidenceNumber)
    ? confidenceNumber >= 90
      ? 'Chất lượng trích xuất tốt'
      : confidenceNumber >= 70
      ? 'Chất lượng trích xuất khá'
      : 'Nên kiểm tra lại dữ liệu'
    : 'Đã trích xuất';
  const sizeClass = compact ? 'text-[10.5px] px-1.5' : 'text-[11px] px-2';

  if (!data) {
    return (
      <span className={`inline-flex items-center gap-1 py-0.5 rounded border border-slate-200 bg-slate-50 text-slate-600 font-bold ${sizeClass}`}>
        <Clock className="w-3 h-3" />
        <span>Chờ kết quả phân tích</span>
      </span>
    );
  }

  if (data.isBulk) {
    return (
      <span className={`inline-flex items-center gap-1 py-0.5 rounded border border-red-200 bg-red-50 text-red-700 font-bold ${sizeClass}`}>
        <Layers className="w-3 h-3" />
        <span>Danh sách nhiều dòng</span>
      </span>
    );
  }

  if (data.qualityGate === 'FAIL') {
    return (
      <span className={`inline-flex items-center gap-1 py-0.5 rounded border border-amber-200 bg-[#FDF0BE] text-amber-700 font-bold ${sizeClass}`}>
        <AlertTriangle className="w-3 h-3" />
        <span>Cần kiểm tra{confidence ? ` (${confidence})` : ''}</span>
      </span>
    );
  }

  if (confidence) {
    return (
      <span className={`inline-flex items-center gap-1 py-0.5 rounded border border-emerald-200 bg-emerald-50 text-emerald-700 font-bold ${sizeClass}`}>
        <CheckCircle2 className="w-3 h-3" />
        <span>{qualityLabel}</span>
      </span>
    );
  }

  return (
    <span className={`inline-flex items-center gap-1 py-0.5 rounded border border-slate-200 bg-slate-50 text-slate-600 font-bold ${sizeClass}`}>
      <Info className="w-3 h-3" />
      <span>Đã trích xuất</span>
    </span>
  );
}

/**
 * Map the entry form onto the API's structured fields.
 *
 * `text` is still sent and still stored as the Case's raw text: it is the
 * narrative the extractor falls back on. The structured fields outrank it —
 * `extract()` ranks a `structured` value above anything it reads out of prose —
 * which is what makes an operator's correction actually take effect.
 */
const CORRECTED_FIELD_LABELS = {
  subject_name: 'Họ và tên',
  subject_code: 'Mã số cán bộ',
  position: 'Chức vụ',
  unit_name: 'Đơn vị công tác',
};

/**
 * States that this result rests on operator-corrected input.
 *
 * `fields` comes from the server's own diff against the original Case's stored
 * extraction, so it reports what the pipeline actually read before the edit —
 * not what the browser happened to be displaying.
 */
function CorrectionNotice({ fields }) {
  if (!fields || fields.length === 0) return null;
  const labels = fields.map((f) => CORRECTED_FIELD_LABELS[f] || f).join(', ');
  return (
    <div className="rounded-md border border-amber-300 bg-[#FDF0BE] px-4 py-3 text-sm text-amber-900">
      <strong className="font-semibold">Kết quả dựa trên thông tin đã hiệu đính.</strong>{' '}
      Cán bộ đã sửa: {labels}. Hồ sơ gốc do hệ thống đọc được vẫn lưu riêng để đối chiếu.
    </div>
  );
}

function structuredPayload(values) {
  const lines = [
    values.fullName && `Họ và tên: ${values.fullName.trim()}`,
    values.birthYear && `Năm sinh: ${values.birthYear.trim()}`,
    values.identifier && `Mã số cán bộ: ${values.identifier.trim()}`,
    values.position && `Chức vụ: ${values.position.trim()}`,
    values.department && `Đơn vị công tác: ${values.department.trim()}`,
    values.extraInfo && values.extraInfo.trim(),
  ].filter(Boolean);

  const payload = {
    text: lines.join('\n') || values.queryText.trim(),
    input_mode: 'FORM',
    subject_name: values.fullName.trim() || null,
    subject_code: values.identifier.trim() || null,
    unit_name: values.department.trim() || null,
    position: values.position.trim() || null,
  };
  if (values.birthYear && values.birthYear.trim()) {
    payload.business_fields = { birth_year: Number(values.birthYear.trim()) };
  }
  return payload;
}

export default function CABQPVerification({ user, onLogout }) {
  const roles = user?.roles instanceof Set ? user.roles : new Set();
  // What the navigation offers. The server decides what actually happens: each
  // of these screens calls endpoints that re-check the same permission, so a
  // caller who reaches one another way gets 403 rather than data.
  const canReview = can(user, P.REVIEW_QUEUE, P.REVIEW_DECIDE);
  const canAdminUnits = can(user, P.REGISTRY_ADMIN);
  const canAdminPersons = can(user, P.PERSON_REGISTRY_ADMIN);
  const canViewAudit = can(user, P.AUDIT_VIEW);
  const canAdminUsers = can(user, P.USER_ADMIN);

  // App view states: 'initial' | 'loading' | 'verified' | 'needs-verification' | 'no-conclusion'
  const [appState, setAppState] = useState('initial');
  // 'search' | 'history' | 'reviews' | 'admin-units' | 'admin-persons' | 'admin-audit'
  const [currentNav, setCurrentNav] = useState('search');
  const [apiError, setApiError] = useState(null);
  const [activeTab, setActiveTab] = useState('manual');
  const [sidebarTab, setSidebarTab] = useState('manual');
  const [isDragging, setIsDragging] = useState(false);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [filePreviewUrl, setFilePreviewUrl] = useState(null);
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractedData, setExtractedData] = useState(null);
  const [pendingCaseId, setPendingCaseId] = useState(null);
  // 'form' = structured entry with required fields; 'text' = free-text lookup.
  const [entryMode, setEntryMode] = useState('form');
  // Fields the server reported as operator-corrected on the current result.
  const [correctedFields, setCorrectedFields] = useState([]);
  const [isOcrModalOpen, setIsOcrModalOpen] = useState(false);
  const [uploadMessage, setUploadMessage] = useState(null);
  const mainFileInputRef = useRef(null);
  const sidebarFileInputRef = useRef(null);

  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  // Modals state for "Xem hồ sơ gốc" & "Đối chiếu chi tiết" — both render the
  // real GET /cases/{id} response (modalCaseDetail), never a synthetic object.
  const [isOriginalDossierOpen, setIsOriginalDossierOpen] = useState(false);
  const [isDetailedCompareOpen, setIsDetailedCompareOpen] = useState(false);
  const [modalCaseDetail, setModalCaseDetail] = useState(null);
  const [modalLoadError, setModalLoadError] = useState(null);
  const [modalCaseData, setModalCaseData] = useState(null);

  // Persistent Search & Verification History: automatically purges legacy mock records
  const [historyList, setHistoryList] = useState(() => {
    try {
      const saved = localStorage.getItem('cabqp_verification_history');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) {
          // Purge legacy mock cases (hs-1, hs-2, hs-3, hs-4) and mock names
          const realCases = parsed.filter(
            (item) =>
              !['hs-1', 'hs-2', 'hs-3', 'hs-4'].includes(item.id) &&
              item.fullName !== 'Nguyễn Văn A' &&
              item.fullName !== 'Phạm Quốc Dũng' &&
              item.fullName !== 'Trần Văn Bình' &&
              item.fullName !== 'Lê Hoàng D'
          );
          return realCases;
        }
      }
    } catch (e) {
      console.warn('Cannot read history from localStorage:', e);
    }
    return DEFAULT_HISTORY;
  });

  // Sync real cases from the backend database — on mount and every time the
  // Lịch sử tab is opened, so newly created/updated cases show up without a
  // full page reload (this view is not a static snapshot).
  const syncHistoryFromBackend = useCallback(() => {
    return axios
      .get(`${API_BASE_URL}/api/v1/cases`, { params: { page_size: 200 }, timeout: 5000 })
      .then((res) => {
        if (res.data && Array.isArray(res.data.items)) {
          const backendMapped = res.data.items.map((c) => ({
            id: c.id,
            caseCode: `#HS-2026-${c.id.replace(/^case_/i, '').slice(0, 8).toUpperCase()}`,
            fullName: c.subject_name || 'Chưa nhận dạng được đối tượng',
            birthYear: c.birth_year || '',
            department: c.current_unit || 'Chưa xác định đơn vị',
            position: c.position || '',
            identifier: c.subject_code || '',
            orgType: c.organization_type || 'UNKNOWN',
            statusCategory:
              c.resolution_status === 'MATCHED' && ['BCA', 'BQP'].includes(c.organization_type)
                ? 'VERIFIED'
                : ['AMBIGUOUS', 'CONFLICT'].includes(c.resolution_status)
                ? 'NEED_REVIEW'
                : 'NO_CONCLUSION',
            appState:
              c.resolution_status === 'MATCHED' && ['BCA', 'BQP'].includes(c.organization_type)
                ? 'verified'
                : ['AMBIGUOUS', 'CONFLICT'].includes(c.resolution_status)
                ? 'needs-verification'
                : 'no-conclusion',
            timestamp: new Date(c.created_at).toLocaleString('vi-VN'),
            officer: c.created_by || '',
          }));
          setHistoryList(backendMapped);
        }
      })
      .catch(() => {
        // Standalone or backend offline mode
      });
  }, []);

  useEffect(() => {
    syncHistoryFromBackend();
  }, [syncHistoryFromBackend]);

  useEffect(() => {
    if (currentNav === 'history') syncHistoryFromBackend();
  }, [currentNav, syncHistoryFromBackend]);

  // Save history updates
  useEffect(() => {
    try {
      localStorage.setItem('cabqp_verification_history', JSON.stringify(historyList));
    } catch (e) {
      console.warn('Cannot save history to localStorage:', e);
    }
  }, [historyList]);

  // Form input state: starts completely dynamic and empty
  const [formValues, setFormValues] = useState({
    queryText: '',
    fullName: '',
    birthYear: '',
    position: '',
    department: '',
    identifier: '',
    extraInfo: '',
  });

  const [errors, setErrors] = useState({});

  // Dynamic API response state
  const [currentCaseData, setCurrentCaseData] = useState(null);

  // Fluid continuous progress animation (appState === 'loading')
  const [loadingProgress, setLoadingProgress] = useState(0);

  useEffect(() => {
    if (appState === 'loading') {
      setLoadingProgress(0);
      let start = null;
      let frameId;
      const duration = 1800; // 1.8 seconds smooth flow

      const step = (timestamp) => {
        if (!start) start = timestamp;
        const elapsed = timestamp - start;
        const t = Math.min(elapsed / duration, 1);
        
        // Cubic easing curve for ultra-smooth fluid progress
        const eased = 1 - Math.pow(1 - t, 2.2);
        const progress = Math.min(Math.round(eased * 93 * 10) / 10, 93);
        
        setLoadingProgress(progress);

        if (t < 1) {
          frameId = requestAnimationFrame(step);
        }
      };

      frameId = requestAnimationFrame(step);
      return () => {
        if (frameId) cancelAnimationFrame(frameId);
      };
    } else {
      setLoadingProgress(0);
    }
  }, [appState]);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormValues((prev) => ({ ...prev, [name]: value }));

    if (name === 'birthYear') {
      const trimmed = value.trim();
      if (trimmed && !/^\d+$/.test(trimmed)) {
        setErrors((prev) => ({
          ...prev,
          birthYear: 'Năm sinh chỉ gồm các chữ số (ví dụ: 1985)',
        }));
        return;
      } else if (trimmed.length > 4) {
        setErrors((prev) => ({
          ...prev,
          birthYear: 'Năm sinh không hợp lệ (phải đúng 4 chữ số, ví dụ 1985)',
        }));
        return;
      } else if (trimmed.length === 4) {
        const year = parseInt(trimmed, 10);
        if (year < 1920 || year > 2026) {
          setErrors((prev) => ({
            ...prev,
            birthYear: 'Năm sinh phải từ năm 1920 đến 2026',
          }));
          return;
        }
      }
    }

    if (errors[name]) {
      setErrors((prev) => ({ ...prev, [name]: '' }));
    }
  };

  // Helper to record new case in history
  // Open "Xem hồ sơ gốc" / "Đối chiếu chi tiết" — both fetch the real case
  // detail by id rather than accepting a synthetic object, so the modals
  // never show fabricated fields.
  const openCaseModal = async (caseId, which) => {
    if (!caseId) return;
    setModalLoadError(null);
    try {
      const detailRes = await axios.get(`/api/v1/cases/${caseId}`, { timeout: 5000 });
      setModalCaseDetail(detailRes.data);
      if (which === 'dossier') setIsOriginalDossierOpen(true);
      else setIsDetailedCompareOpen(true);
    } catch (err) {
      setModalLoadError(
        err?.response?.data?.detail?.message || err?.response?.data?.detail || 'Không tải được hồ sơ.'
      );
    }
  };

  const handleOpenOriginalDossier = (caseId = currentCaseData?.case_id) => openCaseModal(caseId, 'dossier');
  const handleOpenDetailedCompare = (caseId = currentCaseData?.case_id) => openCaseModal(caseId, 'compare');

  // Handle selecting a past search from History — re-fetches the real case
  // detail instead of replaying the thin locally-cached row, so subject_group/
  // eligibility/salary_status reflect what the backend actually holds today.
  const handleSelectHistoryCase = async (item) => {
    if (!item?.id) return;
    setApiError(null);
    setCurrentNav('search');
    setAppState('loading');
    try {
      const detailRes = await axios.get(`/api/v1/cases/${item.id}`, { timeout: 5000 });
      const caseDetail = detailRes.data;
      const extracted = caseDetail.extracted || {};
      setFormValues((prev) => ({
        ...prev,
        queryText: caseDetail.subject?.name || prev.queryText,
        fullName: caseDetail.subject?.name || extracted.subject_name || '',
        position: extracted.position || '',
        department: extracted.current_unit_raw || '',
        identifier: extracted.subject_code || '',
      }));
      setCurrentCaseData(buildCaseResultFromDetail(item.id, caseDetail));
      setAppState(resolvedStateFromDetail(caseDetail));
    } catch (err) {
      setApiError(
        err?.response?.data?.detail?.message || err?.response?.data?.detail || 'Không tải được hồ sơ đã lưu.'
      );
      setAppState('initial');
    }
  };

  const handleClearHistory = () => {
    if (window.confirm('Bạn có chắc chắn muốn xóa toàn bộ lịch sử tra cứu trên thiết bị này?')) {
      setHistoryList([]);
      localStorage.removeItem('cabqp_verification_history');
    }
  };

  const handleDeleteHistoryItem = (id) => {
    setHistoryList((prev) => prev.filter((item) => item.id !== id));
  };

  const handleExportPdf = () => {
    window.print();
  };

  // OCR & document extraction processor: uploads the file to the real backend
  // (PaddleOCR for images/scans, PDF/DOCX parsers otherwise) and shows what the
  // pipeline actually extracted. There is no client-side guessing from the file
  // name or a regex over raw bytes — those produced fabricated names (e.g. a
  // PDF named "05_pdf_hybrid.pdf" showed up as person name "05 Hybrid").
  const handleProcessFile = async (file) => {
    if (!file) return;

    if (file.size > 25 * 1024 * 1024) {
      alert('Dung lượng tệp vượt quá giới hạn 25MB. Vui lòng chọn tệp nhỏ hơn.');
      return;
    }

    setUploadedFile(file);
    // A newly selected file must never inherit confidence or fields from the
    // previously processed file while its own backend result is pending.
    setExtractedData(null);
    setIsExtracting(true);
    setUploadMessage('Đang phân tích hình ảnh/tài liệu và trích xuất thực thể');
    setPendingCaseId(null);

    if (filePreviewUrl) {
      URL.revokeObjectURL(filePreviewUrl);
    }
    const canPreviewInBrowser =
      file.type?.startsWith('image/') ||
      file.type === 'application/pdf' ||
      file.name?.toLowerCase().endsWith('.pdf');
    if (canPreviewInBrowser) {
      const url = URL.createObjectURL(file);
      setFilePreviewUrl(url);
    } else {
      setFilePreviewUrl(null);
    }

    try {
      const formData = new FormData();
      formData.append('file', file);
      let uploadRes;
      try {
        uploadRes = await axios.post(`/api/v1/cases/file`, formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
            'Idempotency-Key': `web-${Date.now()}-${Math.random().toString(36).substring(7)}`,
          },
          timeout: 120000,
        });
      } catch (uploadError) {
        const detail = uploadError?.response?.data?.detail || '';
        const detailText =
          typeof detail === 'string' ? detail : JSON.stringify(detail);
        const isTabularList =
          uploadError?.response?.status === 422 &&
          (
            detail?.code === 'TABULAR_LIST' ||
            /TABULAR_LIST|multi-row tabular list|\/api\/v1\/bulk/i.test(detailText)
          );
        if (!isTabularList) {
          throw uploadError;
        }

        const bulkForm = new FormData();
        bulkForm.append('file', file);
        const bulkRes = await axios.post('/api/v1/bulk', bulkForm, {
          headers: { 'Content-Type': 'multipart/form-data' },
          timeout: 120000,
        });
        const bulkDetail = bulkRes.data?.duplicate_file
          ? (await axios.get(`/api/v1/bulk/${bulkRes.data.job_id}`)).data
          : null;
        const bulkData = {
          isBulk: true,
          jobId: bulkRes.data.job_id,
          status: bulkDetail?.job?.status || bulkRes.data.status,
          profile: bulkRes.data.profile || null,
          validation: bulkRes.data.validation || bulkDetail?.job?.validation || {},
          mapping: bulkRes.data.mapping || bulkDetail?.job?.mapping || {},
          job: bulkDetail?.job || null,
          rows: bulkDetail?.rows || bulkRes.data.rows || [],
          errors: bulkDetail?.errors || [],
          duplicateFile: Boolean(bulkRes.data.duplicate_file),
        };
        setIsExtracting(false);
        setExtractedData(bulkData);
        setUploadMessage(`Đã nhận diện bảng danh sách: ${file.name}`);
        setIsOcrModalOpen(true);
        return;
      }
      const caseId = uploadRes?.data?.case_id;
      if (!caseId) throw new Error('Hệ thống không tạo được mã hồ sơ. Vui lòng thử lại.');

      // Document processing runs async on the worker; poll the case until the
      // extraction result lands instead of guessing a fixed delay.
      let caseDetail = null;
      for (let attempt = 0; attempt < 40; attempt += 1) {
        const detailRes = await axios.get(`/api/v1/cases/${caseId}`, { timeout: 5000 });
        caseDetail = detailRes.data;
        if (caseDetail?.extracted || caseDetail?.case?.workflow_status === 'FAILED') break;
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }

      const ex = caseDetail?.extracted;
      const evidence = caseDetail?.result?.evidence;
      const failed = caseDetail?.case?.workflow_status === 'FAILED';
      const splitSource = evidence?.split_source;
      const blockCount = splitSource?.block_count || 1;
      const isMultiSubject = blockCount > 1;

      const extracted = {
        fullName: ex?.subject_name || '',
        birthYear: '',
        department: ex?.current_unit_raw || '',
        position: ex?.position || '',
        identifier: ex?.subject_code || '',
        extraInfo: failed
          ? `Xử lý tài liệu thất bại: ${file.name}`
          : isMultiSubject
            ? `Tài liệu có ${blockCount} người, đây là hồ sơ số ${splitSource.block_index + 1}/${blockCount}. Hệ thống đã tự động đọc tệp: ${file.name}`
            : ex
              ? `Hệ thống đã tự động đọc tệp: ${file.name}`
              : `Chưa trích xuất được thực thể từ: ${file.name} (vui lòng nhập tay hoặc thử lại)`,
        confidence:
          evidence?.parse_confidence != null
            ? `${Math.round(evidence.parse_confidence * 100)}%`
            : 'Chưa có',
        extractionCompleteness:
          ex?.extraction_confidence != null
            ? `${Math.round(ex.extraction_confidence * 100)}%`
            : 'Chưa có',
        parseMethod: evidence?.parse_method || 'PARSER',
        qualityGate: evidence?.parse_quality?.gate_result || null,
        docType: file.type?.startsWith('image/')
          ? 'Ảnh thẻ / Bản chụp tài liệu số hóa'
          : 'Tài liệu nghiệp vụ định dạng số',
        isMultiSubject,
        blockIndex: splitSource?.block_index,
        blockCount,
        sourcePreviewRows: evidence?.parse_evidence?.source_preview_rows || [],
        sourcePreviewText: evidence?.parse_evidence?.source_preview_text || '',
      };

      setIsExtracting(false);
      setExtractedData(extracted);
      setPendingCaseId(caseId);
      setFormValues((prev) => ({
        ...prev,
        fullName: extracted.fullName || prev.fullName,
        department: extracted.department || prev.department,
        position: extracted.position || prev.position,
        identifier: extracted.identifier || prev.identifier,
        extraInfo: extracted.extraInfo || prev.extraInfo,
      }));
      setUploadMessage(
        failed
          ? `Xử lý tài liệu thất bại: ${file.name}`
          : isMultiSubject
            ? `Tài liệu "${file.name}" có ${blockCount} người. Hệ thống đã tách thành ${blockCount} hồ sơ riêng biệt. Xem tại mục Lịch sử.`
            : `Đã xử lý tài liệu: ${file.name}`
      );
      setIsOcrModalOpen(true);
      if (isMultiSubject) {
        // Sibling cases already exist in the backend by the time this one's polling
        // finished; pull them into history now so "Lịch sử" doesn't require a manual
        // refresh to reveal the other people found in this document.
        syncHistoryFromBackend();
      }
    } catch (err) {
      setIsExtracting(false);
      setUploadMessage('Không thể đọc tài liệu. Vui lòng kiểm tra tệp và thử lại.');
      setExtractedData(null);
    }
  };

  const handleClearUploadedFile = () => {
    setUploadedFile(null);
    if (filePreviewUrl) {
      URL.revokeObjectURL(filePreviewUrl);
      setFilePreviewUrl(null);
    }
    setExtractedData(null);
    setUploadMessage(null);
    setPendingCaseId(null);
    if (mainFileInputRef.current) mainFileInputRef.current.value = '';
    if (sidebarFileInputRef.current) sidebarFileInputRef.current.value = '';
  };

  // Browsers do not emit `change` when the user chooses the same path twice.
  // Clear the native input before opening it so closing the result modal and
  // selecting the same document always runs the upload flow again.
  const openFilePicker = (inputRef) => {
    if (!inputRef.current) return;
    inputRef.current.value = '';
    inputRef.current.click();
  };

  // Perform search / verification with API and offline fallback
  // `options.values` lets a caller (the OCR review modal) hand corrected fields
  // straight in. Reading them from state instead would race setFormValues, which
  // is why an earlier version needed a setTimeout and still dropped edits.
  const handleSearch = async (e, options = {}) => {
    if (e) e.preventDefault();

    const values = { ...formValues, ...(options.values || {}) };
    const correctedFrom = options.correctedFrom || null;
    const isCurrentUpload =
      !correctedFrom && (appState === 'initial' ? activeTab : sidebarTab) === 'upload';
    const usingForm = entryMode === 'form' || Boolean(correctedFrom);

    // If on upload tab but no file selected, open picker or use filled form
    if (isCurrentUpload && !uploadedFile && !values.fullName.trim()) {
      if (appState === 'initial' && mainFileInputRef.current) {
        openFilePicker(mainFileInputRef);
      } else if (sidebarFileInputRef.current) {
        openFilePicker(sidebarFileInputRef);
      }
      return;
    }

    if (!isCurrentUpload && !usingForm && !values.queryText.trim()) {
      setErrors((prev) => ({ ...prev, queryText: 'Vui lòng nhập thông tin cần tra cứu' }));
      return;
    }

    // Form mode carries the same requirements the API enforces: something to
    // identify the person by, and a unit to resolve. Checked here only so the
    // operator sees which box is missing — the server refuses either way.
    if (!isCurrentUpload && usingForm) {
      const identityMissing = !values.identifier.trim() && !values.fullName.trim();
      const unitMissing = !values.department.trim();
      if (identityMissing || unitMissing) {
        setErrors((prev) => ({
          ...prev,
          identifier: identityMissing ? 'Nhập mã số cán bộ hoặc họ và tên' : undefined,
          fullName: identityMissing ? 'Nhập họ và tên hoặc mã số cán bộ' : undefined,
          department: unitMissing ? 'Đơn vị công tác là bắt buộc' : undefined,
        }));
        return;
      }
      setErrors((prev) => ({ ...prev, identifier: undefined, fullName: undefined, department: undefined }));
    }

    // Strict validation for birthYear if provided
    if (values.birthYear && values.birthYear.trim()) {
      const yearStr = values.birthYear.trim();
      const yearNum = parseInt(yearStr, 10);
      if (!/^\d{4}$/.test(yearStr) || isNaN(yearNum) || yearNum < 1920 || yearNum > 2026) {
        setErrors((prev) => ({
          ...prev,
          birthYear: 'Năm sinh không hợp lệ (phải gồm đúng 4 chữ số, từ 1920 đến 2026)',
        }));
        return;
      }
    }

    setApiError(null);
    setAppState('loading');
    setCurrentNav('search');

    const startTime = Date.now();

    // 1. Try real FastAPI backend API if available
    try {
      let caseId = null;

      const idempotency = () => ({
        'Idempotency-Key': `web-${Date.now()}-${Math.random().toString(36).substring(7)}`,
      });

      if (correctedFrom) {
        // The operator edited what OCR read. Submit those values as a new Case
        // linked to the original, so the machine's first reading stays on record
        // and the server can report exactly which fields a human overrode.
        const response = await axios.post(
          `/api/v1/cases/text`,
          { ...structuredPayload(values), corrected_from_case_id: correctedFrom },
          { headers: idempotency(), timeout: 30000 }
        );
        caseId = response?.data?.case_id;
        setCorrectedFields(response?.data?.corrected_fields || []);
      } else if (isCurrentUpload && uploadedFile && pendingCaseId) {
        // The file was already uploaded and OCR'd when it was selected
        // (handleProcessFile) — reuse that case instead of re-uploading and
        // re-running OCR a second time.
        caseId = pendingCaseId;
        setCorrectedFields([]);
      } else if (isCurrentUpload && uploadedFile) {
        const formData = new FormData();
        formData.append('file', uploadedFile);
        if (values.birthYear) {
          formData.append('as_of_date', `${values.birthYear}-01-01`);
        }
        const response = await axios.post(`/api/v1/cases/file`, formData, {
          headers: { 'Content-Type': 'multipart/form-data', ...idempotency() },
          timeout: 120000,
        });
        caseId = response?.data?.case_id;
        setCorrectedFields([]);
      } else if (usingForm) {
        const response = await axios.post(`/api/v1/cases/text`, structuredPayload(values), {
          headers: idempotency(),
          timeout: 30000,
        });
        caseId = response?.data?.case_id;
        setCorrectedFields([]);
      } else {
        const response = await axios.post(
          `/api/v1/cases/text`,
          { text: values.queryText.trim(), input_mode: 'TEXT' },
          { headers: idempotency(), timeout: 30000 }
        );
        caseId = response?.data?.case_id;
        setCorrectedFields([]);
      }

      if (caseId) {
        // Document cases process asynchronously on the worker (OCR can take
        // 10-40s); poll until the verification result lands instead of a
        // single GET with a short timeout, which used to fail closed into
        // the fabricated offline fallback below on every real OCR upload.
        let caseDetail = null;
        for (let attempt = 0; attempt < 60; attempt += 1) {
          const detailRes = await axios.get(`/api/v1/cases/${caseId}`, { timeout: 5000 });
          caseDetail = detailRes.data;
          if (caseDetail?.result || caseDetail?.case?.workflow_status === 'FAILED') break;
          await new Promise((resolve) => setTimeout(resolve, 1500));
        }
        const resolvedState = resolvedStateFromDetail(caseDetail);

        const extracted = caseDetail.extracted || {};
        setFormValues((prev) => ({
          ...prev,
          fullName: extracted.subject_name || prev.fullName,
          position: extracted.position || prev.position,
          department: extracted.current_unit_raw || prev.department,
          identifier: extracted.subject_code || prev.identifier,
        }));

        const caseResult = buildCaseResultFromDetail(caseId, caseDetail);

        const remainingTime = Math.max(0, 1600 - (Date.now() - startTime));
        setTimeout(() => {
          setCurrentCaseData(caseResult);
          setAppState(resolvedState);
          syncHistoryFromBackend();
        }, remainingTime);
        return;
      }
    } catch (backendErr) {
      console.error('Không thể tra cứu qua API:', backendErr);
      setApiError(
        backendErr?.response?.data?.detail?.message ||
        backendErr?.response?.data?.detail ||
        'Không thể kết nối hệ thống đối chiếu. Vui lòng thử lại.'
      );
      setAppState('initial');
      return;
    }

    // The backend call above completed without throwing but returned no
    // usable case_id — never fabricate a verdict client-side. Surface the
    // same error state the network-failure catch above uses.
    setApiError('Không nhận được kết quả hợp lệ từ hệ thống đối chiếu. Vui lòng thử lại.');
    setAppState('initial');
  };

  const handleReset = () => {
    setFormValues({
      queryText: '',
      fullName: '',
      birthYear: '',
      position: '',
      department: '',
      identifier: '',
      extraInfo: '',
    });
    setErrors({});
    setUploadedFile(null);
    setCurrentCaseData(null);
  };

  return (
    <div className="h-screen w-full flex flex-col bg-slate-100 text-slate-900 font-sans antialiased select-none overflow-hidden">
      <AppHeader
        user={user}
        roleLabel={ROLE_LABELS[['ADMIN', 'REVIEWER', 'USER'].find((r) => roles.has(r))] || 'Cán bộ nghiệp vụ'}
        onHome={() => {
          setAppState('initial');
          setCurrentNav('search');
        }}
        onLogout={onLogout}
      />
      <AppNavigation
        currentNav={currentNav}
        onNavigate={setCurrentNav}
        historyCount={historyList.length}
        adminEntries={[
          { nav: 'reviews', label: 'Hàng đợi đối soát', allowed: canReview },
          { nav: 'admin-units', label: 'Danh mục đơn vị', allowed: canAdminUnits },
          { nav: 'admin-persons', label: 'Danh mục cá nhân', allowed: canAdminPersons },
          { nav: 'admin-audit', label: 'Nhật ký kiểm toán', allowed: canViewAudit },
          { nav: 'admin-users', label: 'Quản trị tài khoản', allowed: canAdminUsers },
        ].filter((entry) => entry.allowed)}
      />

      {/* Main Body */}
      <main className="flex-1 w-full flex flex-col relative z-10 overflow-hidden min-h-0">
        {currentNav === 'reviews' ? (
          <ReviewsPage apiBaseUrl={API_BASE_URL} user={user} />
        ) : currentNav === 'admin-units' ? (
          <RegistryAdminPage apiBaseUrl={API_BASE_URL} />
        ) : currentNav === 'admin-persons' ? (
          <PersonRegistryAdminPage apiBaseUrl={API_BASE_URL} />
        ) : currentNav === 'admin-audit' ? (
          <AuditPage apiBaseUrl={API_BASE_URL} />
        ) : currentNav === 'admin-users' ? (
          <UsersAdminPage apiBaseUrl={API_BASE_URL} />
        ) : currentNav === 'history' ? (
          <HistoryView
            historyList={historyList}
            onSelectCase={handleSelectHistoryCase}
            onRefresh={syncHistoryFromBackend}
            onBackToSearch={() => {
              setCurrentNav('search');
              setAppState('initial');
            }}
          />
        ) : appState === 'initial' ? (
          <div className="flex-1 min-h-0 overflow-y-auto">
            <PageContainer className="py-3 sm:py-4">
              <PageHeader
                trail={[{ label: 'Trang chủ' }]}
                title="Tra cứu đối tượng CA/BQP"
                description="Nhập thông tin hoặc tải tài liệu để xác định đơn vị công tác thuộc Bộ Công an hay Bộ Quốc phòng."
                icon={Search}
              />

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 items-start">
                <section className="lg:col-span-8 bg-white border border-slate-200 rounded-md shadow-xs p-3 sm:p-4">
                  <div className="flex border-b border-slate-200 -mx-3 sm:-mx-4 px-3 sm:px-4 mb-3">
                    {[
                      { id: 'manual', label: 'Nhập thông tin', icon: Edit3 },
                      { id: 'upload', label: 'Tải tài liệu', icon: UploadCloud },
                    ].map((tab) => (
                      <button
                        key={tab.id}
                        type="button"
                        onClick={() => setActiveTab(tab.id)}
                        className={`flex items-center gap-1.5 px-3.5 pt-1.5 pb-2 mr-1 text-xs sm:text-[13px] font-semibold border-b-2 transition-colors cursor-pointer ${
                          activeTab === tab.id
                            ? 'text-red-600 border-red-600 bg-red-50/70'
                            : 'text-slate-600 border-transparent hover:text-slate-900'
                        }`}
                      >
                        <tab.icon className="w-4 h-4" />
                        <span>{tab.label}</span>
                      </button>
                    ))}
                  </div>


                  {activeTab === 'manual' ? (
                    <form onSubmit={handleSearch} noValidate>
                      {apiError && (
                        <div className="mb-3 rounded-md bg-red-50 px-3 py-2.5 text-xs leading-relaxed text-red-700">
                          {String(apiError)}
                        </div>
                      )}
                      <div className="mb-3 inline-flex rounded-md border border-slate-200 bg-slate-50 p-0.5">
                        {[
                          { id: 'form', label: 'Theo biểu mẫu' },
                          { id: 'text', label: 'Tra cứu tự do' },
                        ].map((mode) => (
                          <button
                            key={mode.id}
                            type="button"
                            onClick={() => { setEntryMode(mode.id); setErrors({}); }}
                            className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
                              entryMode === mode.id
                                ? 'bg-white text-red-700 shadow-xs'
                                : 'text-slate-500 hover:text-slate-700'
                            }`}
                          >
                            {mode.label}
                          </button>
                        ))}
                      </div>

                      <div className={entryMode === 'text' ? 'mb-3' : 'hidden'}>
                        <label className="mb-1.5 block text-[13px] font-semibold text-slate-900">
                          Thông tin cần tra cứu
                        </label>
                        <textarea
                          name="queryText"
                          rows={6}
                          value={formValues.queryText}
                          onChange={handleInputChange}
                          placeholder="Ví dụ: Nguyễn Văn A, sinh năm 1985, số hiệu 012345, hiện công tác tại"
                          className={`w-full min-h-[150px] resize-y rounded-md border bg-white p-3.5 text-sm leading-6 text-slate-900 outline-none transition-all ${
                            errors.queryText
                              ? 'border-red-400 focus:ring-1 focus:ring-red-500'
                              : 'border-slate-300 focus:border-red-500 focus:ring-1 focus:ring-red-500'
                          }`}
                        />
                        {errors.queryText && <p className="mt-1 text-xs font-medium text-red-500">{errors.queryText}</p>}
                        <p className="mt-1.5 text-[11.5px] leading-relaxed text-slate-500">
                          Có thể nhập tên, mã cá nhân, đơn vị, chức vụ hoặc nội dung mô tả bất kỳ. Hệ thống sẽ tự trích xuất thông tin.
                        </p>
                      </div>

                      <div className={entryMode === 'form' ? '' : 'hidden'}>
                      <p className="mb-2.5 rounded-md bg-red-50 px-3 py-2 text-[11.5px] leading-relaxed text-red-800">
                        Bắt buộc: <strong>mã số cán bộ</strong> hoặc <strong>họ và tên</strong> (ít nhất một),
                        và <strong>đơn vị công tác</strong>.
                      </p>
                      {/* Row 1: Họ và tên (Full width) */}
                      <div className="mb-2.5">
                        <label className="block text-xs sm:text-[13px] font-semibold text-slate-900 mb-0.5">
                          Họ và tên <span className="text-red-500">*</span>
                        </label>
                        <input
                          type="text"
                          name="fullName"
                          value={formValues.fullName}
                          onChange={handleInputChange}
                          placeholder="Nhập họ và tên đối tượng"
                          className={`w-full h-8.5 sm:h-9 px-3 rounded-md border text-xs sm:text-sm bg-white transition-all outline-none ${
                            errors.fullName
                              ? 'border-red-500 focus:ring-1 focus:ring-red-500 text-red-600'
                              : 'border-slate-300 focus:border-red-500 focus:ring-1 focus:ring-red-500 text-slate-900'
                          }`}
                        />
                        {errors.fullName && (
                          <p className="text-xs text-red-500 mt-1 font-medium">
                            {errors.fullName}
                          </p>
                        )}
                      </div>

                      {/* Row 2: Năm sinh & Chức vụ (2 columns on sm+, 1 on mobile) */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 sm:gap-3 mb-2.5">
                        <div>
                          <label className="block text-xs sm:text-[13px] font-semibold text-slate-900 mb-0.5">
                            Năm sinh
                          </label>
                          <input
                            type="text"
                            name="birthYear"
                            value={formValues.birthYear}
                            onChange={handleInputChange}
                            placeholder="Năm sinh (VD: 1990)"
                            maxLength={5}
                            className={`w-full h-8.5 sm:h-9 px-3 rounded-md border text-xs sm:text-sm bg-white transition-all outline-none ${
                              errors.birthYear
                                ? 'border-red-500 focus:ring-1 focus:ring-red-500 text-red-600 bg-red-50/20'
                                : 'border-slate-300 focus:border-red-500 focus:ring-1 focus:ring-red-500 text-slate-900'
                            }`}
                          />
                          {errors.birthYear && (
                            <p className="text-xs text-red-500 mt-1 font-medium flex items-center gap-1">
                              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                              <span>{errors.birthYear}</span>
                            </p>
                          )}
                        </div>

                        <div>
                          <label className="block text-xs sm:text-[13px] font-semibold text-slate-900 mb-0.5">
                            Chức vụ
                          </label>
                          <input
                            type="text"
                            name="position"
                            value={formValues.position}
                            onChange={handleInputChange}
                            placeholder="Chức vụ / Vị trí công tác"
                            className="w-full h-8.5 sm:h-9 px-3 rounded-md border border-slate-300 focus:border-red-500 focus:ring-1 focus:ring-red-500 text-xs sm:text-sm bg-white text-slate-900 transition-all outline-none"
                          />
                        </div>
                      </div>

                      {/* Row 3: Đơn vị & Số hiệu / Mã định danh (2 columns on sm+, 1 on mobile) */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 sm:gap-3 mb-2.5">
                        <div>
                          <label className="block text-xs sm:text-[13px] font-semibold text-slate-900 mb-0.5">
                            Đơn vị công tác <span className="text-red-500">*</span>
                          </label>
                          <div className="relative">
                            <input
                              list="department-options"
                              type="text"
                              name="department"
                              value={formValues.department}
                              onChange={handleInputChange}
                              placeholder="Nhập hoặc chọn đơn vị"
                              className={`w-full h-8.5 sm:h-9 px-3 pr-8 rounded-md border text-xs sm:text-sm bg-white transition-all outline-none ${
                                errors.department
                                  ? 'border-red-500 focus:ring-1 focus:ring-red-500 text-red-600'
                                  : 'border-slate-300 focus:border-red-500 focus:ring-1 focus:ring-red-500 text-slate-900'
                              }`}
                            />
                            <datalist id="department-options">
                              <option value="Công an quận Hoàng Mai (Hà Nội)" />
                              <option value="Học viện An ninh Nhân dân" />
                              <option value="Quân khu 7 (Bộ Quốc phòng)" />
                              <option value="Bộ Tư lệnh Cảnh sát Cơ động" />
                              <option value="Cục Tác chiến - BQP" />
                              <option value="Sư đoàn 312 (Quân đoàn 12)" />
                              <option value="Cục Cảnh sát Hình sự (C02)" />
                              <option value="Công an TP Hà Nội" />
                              <option value="Công an TP Hồ Chí Minh" />
                            </datalist>
                            <div className="absolute inset-y-0 right-0 pr-2.5 flex items-center pointer-events-none text-slate-400">
                              <Building2 className="w-3.5 h-3.5" />
                            </div>
                          </div>
                          {errors.department && (
                            <p className="text-xs text-red-500 mt-1 font-medium">{errors.department}</p>
                          )}
                        </div>

                        <div>
                          <label className="block text-xs sm:text-[13px] font-semibold text-slate-900 mb-0.5">
                            Mã số cán bộ <span className="text-red-500">*</span>
                          </label>
                          <input
                            type="text"
                            name="identifier"
                            value={formValues.identifier}
                            onChange={handleInputChange}
                            placeholder="Số hiệu / Mã định danh / CCCD"
                            className={`w-full h-8.5 sm:h-9 px-3 rounded-md border text-xs sm:text-sm bg-white transition-all outline-none uppercase ${
                              errors.identifier
                                ? 'border-red-500 focus:ring-1 focus:ring-red-500 text-red-600'
                                : 'border-slate-300 focus:border-red-500 focus:ring-1 focus:ring-red-500 text-slate-900'
                            }`}
                          />
                          {errors.identifier && (
                            <p className="text-xs text-red-500 mt-1 font-medium">{errors.identifier}</p>
                          )}
                        </div>
                      </div>

                      {/* Row 4: Thông tin bổ sung (Full width textarea) */}
                      <div className="mb-3">
                        <label className="block text-xs sm:text-[13px] font-semibold text-slate-900 mb-0.5">
                          Thông tin bổ sung
                        </label>
                        <textarea
                          name="extraInfo"
                          rows={2}
                          value={formValues.extraInfo}
                          onChange={handleInputChange}
                          placeholder="Nhập số quyết định, phân công, ghi chú hồ sơ vụ việc hoặc dấu hiệu nghiệp vụ khác"
                          className="w-full h-15 sm:h-16 p-2.5 rounded-md border border-slate-300 focus:border-red-500 focus:ring-1 focus:ring-red-500 text-xs sm:text-sm bg-white text-slate-900 transition-all outline-none resize-none leading-relaxed"
                        />
                      </div>
                      </div>

                      {/* Row 5: Action buttons */}
                      <div className="flex flex-wrap items-center gap-2.5 pt-0.5">
                        <button
                          type="submit"
                          className="h-8.5 sm:h-9 px-5 rounded-md bg-red-600 hover:bg-red-700 active:bg-red-800 text-white font-semibold text-xs sm:text-sm flex items-center justify-center gap-1.5 shadow-xs transition-colors cursor-pointer"
                        >
                          <Search className="w-3.5 h-3.5" />
                          <span>Tra cứu</span>
                        </button>

                        <button
                          type="button"
                          onClick={handleReset}
                          className="h-8.5 sm:h-9 px-4 rounded-md bg-white border border-slate-200 hover:bg-slate-50 active:bg-slate-100 text-slate-700 font-medium text-xs sm:text-sm flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
                        >
                          <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
                          <span>Xóa làm lại</span>
                        </button>
                      </div>
                    </form>
                  ) : (
                    /* Upload Tab */
                    <div className="space-y-2.5">
                      {/* Hidden File Input */}
                      <input
                        ref={mainFileInputRef}
                        type="file"
                        className="hidden"
                        accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.txt,.json,.csv,.log"
                        onChange={(e) => {
                          if (e.target.files && e.target.files[0]) {
                            handleProcessFile(e.target.files[0]);
                          }
                        }}
                      />

                      {/* Dropzone Container */}
                      <div
                        onDragOver={(e) => {
                          e.preventDefault();
                          setIsDragging(true);
                        }}
                        onDragLeave={() => setIsDragging(false)}
                        onDrop={(e) => {
                          e.preventDefault();
                          setIsDragging(false);
                          if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                            handleProcessFile(e.dataTransfer.files[0]);
                          }
                        }}
                        className={`relative border-2 border-dashed rounded-md p-3 text-center transition-all ${
                          isDragging
                            ? 'border-red-500 bg-red-50/60'
                            : uploadedFile
                            ? 'border-emerald-400 bg-emerald-50/20'
                            : 'border-slate-200 hover:border-red-400 bg-slate-50/40'
                        }`}
                      >
                        {isExtracting ? (
                          <div className="py-4 flex flex-col items-center justify-center space-y-2">
                            <div className="w-8 h-8 rounded-full border-2 border-red-600 border-t-transparent animate-spin flex items-center justify-center">
                              <Scan className="w-4 h-4 text-red-600" />
                            </div>
                            <div>
                              <p className="text-[13px] font-bold text-red-900">Đang đọc nội dung tài liệu</p>
                              <p className="text-[11.5px] text-slate-500">Trích xuất: Họ tên, Năm sinh, Đơn vị, Chức vụ</p>
                            </div>
                          </div>
                        ) : uploadedFile ? (
                          <div className="flex flex-col sm:flex-row items-center gap-3 text-left p-1">
                            {/* Thumbnail / Icon preview */}
                            <div className="relative w-16 h-16 sm:w-20 sm:h-20 rounded-md overflow-hidden border border-slate-200 bg-slate-100 flex-shrink-0 flex items-center justify-center shadow-inner">
                              {filePreviewUrl && uploadedFile.type?.startsWith('image/') ? (
                                <img
                                  src={filePreviewUrl}
                                  alt="Tài liệu tải lên"
                                  className="w-full h-full object-cover"
                                />
                              ) : (
                                <div className="flex flex-col items-center justify-center text-slate-400">
                                  <FileText className="w-7 h-7 text-red-500 mb-0.5" />
                                  <span className="text-[9px] font-bold uppercase">{uploadedFile.name.split('.').pop()}</span>
                                </div>
                              )}
                              <div className="absolute top-1 right-1 px-1 py-0.2 rounded bg-black/60 text-[9px] font-semibold text-white">
                                {uploadedFile.type?.startsWith('image/') ? 'Ảnh' : (uploadedFile.name.split('.').pop() || 'Tệp').toUpperCase()}
                              </div>
                            </div>

                            {/* Extracted overview card */}
                            <div className="flex-1 min-w-0 space-y-1">
                              <div className="flex flex-wrap items-center justify-between gap-1.5">
                                <div>
                                  <h4 className="text-[13px] font-bold text-slate-900 truncate max-w-xs sm:max-w-md">
                                    {uploadedFile.name}
                                  </h4>
                                  <p className="text-[11px] text-slate-500">
                                    {(uploadedFile.size / 1024).toFixed(1)} KB
                                  </p>
                                </div>
                                <UploadStatusBadge data={extractedData} />
                              </div>

                              {/* Key Extracted Info Chips */}
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 pt-0.5 text-[11.5px]">
                                <div className="bg-white px-2 py-1 rounded border border-slate-200">
                                  <span className="text-slate-400 text-[10px] block">Họ tên:</span>
                                  <span className="font-bold text-slate-900 truncate block">{formValues.fullName || 'Chưa có'}</span>
                                </div>
                                <div className="bg-white px-2 py-1 rounded border border-slate-200">
                                  <span className="text-slate-400 text-[10px] block">Đơn vị:</span>
                                  <span className="font-bold text-slate-900 truncate block">{formValues.department || 'Chưa có'}</span>
                                </div>
                              </div>

                              {/* Controls */}
                              <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                                <button
                                  type="button"
                                  onClick={() => setIsOcrModalOpen(true)}
                                  className="px-2.5 py-1 rounded bg-red-50 hover:bg-red-100 text-red-700 font-semibold text-[11.5px] flex items-center gap-1 transition-all cursor-pointer"
                                >
                                  <Eye className="w-3 h-3" />
                                  <span>Xem dữ liệu trích xuất</span>
                                </button>
                                <button
                                  type="button"
                                  onClick={() => openFilePicker(mainFileInputRef)}
                                  className="px-2.5 py-1 rounded border border-slate-200 hover:bg-slate-50 text-slate-700 font-semibold text-[11.5px] flex items-center gap-1 transition-all cursor-pointer"
                                >
                                  <FolderOpen className="w-3 h-3 text-slate-400" />
                                  <span>Đổi tệp</span>
                                </button>
                                <button
                                  type="button"
                                  onClick={handleClearUploadedFile}
                                  className="px-2.5 py-1 rounded border border-red-200 hover:bg-red-50 text-red-600 font-semibold text-[11.5px] flex items-center gap-1 transition-all cursor-pointer"
                                >
                                  <X className="w-3 h-3" />
                                  <span>Xóa</span>
                                </button>
                              </div>
                            </div>
                          </div>
                        ) : (
                          <div
                            onClick={() => openFilePicker(mainFileInputRef)}
                            className="cursor-pointer py-2.5 flex flex-col items-center justify-center space-y-1.5"
                          >
                            <div className="w-10 h-10 rounded-full bg-red-50 text-red-600 flex items-center justify-center">
                              <UploadCloud className="w-5 h-5" />
                            </div>
                            <div>
                              <p className="text-[13px] font-bold text-slate-900">
                                Nhấp để chọn ảnh hoặc kéo thả tài liệu vào đây
                              </p>
                              <p className="text-[11.5px] text-slate-500 mt-0.5">
                                Ảnh chụp CCCD/Thẻ ngành, PDF, DOCX tối đa 25MB
                              </p>
                            </div>
                            <div className="pt-0.5">
                              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-white border border-slate-200 text-slate-700 font-semibold text-[12px] shadow-xs hover:bg-slate-50">
                                <FolderOpen className="w-3.5 h-3.5 text-red-600" />
                                <span>Chọn ảnh / tài liệu từ máy</span>
                              </span>
                            </div>
                          </div>
                        )}
                      </div>


                      {/* Action buttons */}
                      <div className="flex items-center gap-3 pt-1">
                        <button
                          type="button"
                          onClick={handleSearch}
                          className="h-10 sm:h-10.5 px-6 rounded-md bg-red-600 hover:bg-red-700 text-white font-semibold text-[13.5px] sm:text-[14px] flex items-center justify-center gap-2 shadow-xs transition-all cursor-pointer"
                        >
                          <Scan className="w-4 h-4" />
                          <span>Trích xuất &amp; Tra cứu</span>
                        </button>

                        <button
                          type="button"
                          onClick={handleClearUploadedFile}
                          className="h-10 sm:h-10.5 px-5 rounded-md border border-slate-200 hover:bg-slate-50 text-slate-700 font-medium text-[13.5px] sm:text-[14px] flex items-center justify-center gap-2 transition-all cursor-pointer"
                        >
                          <RotateCcw className="w-4 h-4 text-slate-400" />
                          <span>Làm lại</span>
                        </button>
                      </div>
                    </div>
                  )}
                </section>

                <RecentCasesPanel
                  items={historyList}
                  onOpen={handleSelectHistoryCase}
                  onShowAll={() => setCurrentNav('history')}
                />
              </div>
            </PageContainer>
          </div>
        ) : (
          /* Two-Column Workspace Layout for Loading & Result States */
          <div className="max-w-[1480px] w-full mx-auto px-4 sm:px-6 lg:px-8 py-3 flex-1 flex flex-col lg:flex-row gap-3 min-h-0 overflow-y-auto lg:overflow-hidden lg:h-full">
            {/* Mobile Toggle for Search Form (< lg) */}
            <div className="flex-shrink-0 lg:hidden w-full">
              <button
                type="button"
                onClick={() => setIsMobileSidebarOpen(!isMobileSidebarOpen)}
                className="w-full py-2 px-3 rounded-md bg-white border border-slate-200 text-slate-700 font-semibold text-[13px] flex items-center justify-between shadow-xs cursor-pointer"
              >
                <div className="flex items-center gap-2">
                  <Edit3 className="w-3.5 h-3.5 text-red-600" />
                  <span>{isMobileSidebarOpen ? 'Thu gọn biểu mẫu tra cứu' : 'Chỉnh sửa thông tin tra cứu'}</span>
                </div>
                <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform ${isMobileSidebarOpen ? 'rotate-180' : ''}`} />
              </button>
            </div>

            {/* Left Search Sidebar */}
            <aside className={`w-full lg:w-[350px] xl:w-[370px] flex-shrink-0 bg-white rounded-md border border-slate-200 shadow-xs p-3.5 flex flex-col min-h-0 ${
              isMobileSidebarOpen ? 'flex max-h-[500px] lg:max-h-none overflow-y-auto lg:overflow-hidden lg:h-full' : 'hidden lg:flex lg:h-full lg:overflow-hidden'
            }`}>
              <div className="flex-shrink-0 flex items-start gap-2 mb-2 pb-2 border-b border-slate-200">
                <div className="w-1 h-4 bg-red-600 rounded-full mt-0.5 flex-shrink-0" />
                <div>
                  <h3 className="text-[14px] font-bold text-slate-900">Tra cứu thông tin</h3>
                  <p className="text-[11px] text-slate-500 leading-tight">
                    Nhập thông tin hoặc tải tài liệu để hệ thống xác minh.
                  </p>
                </div>
              </div>

              {/* Segmented Control */}
              <div className="flex-shrink-0 flex items-center p-0.5 bg-slate-100 rounded-md mb-2.5 border border-slate-200/60">
                <button
                  type="button"
                  onClick={() => setSidebarTab('manual')}
                  className={`flex-1 py-1 px-2.5 rounded text-[12px] font-semibold flex items-center justify-center gap-1 transition-all cursor-pointer ${
                    sidebarTab === 'manual'
                      ? 'bg-white text-red-600 shadow-xs border border-slate-200'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <Edit3 className="w-3 h-3" />
                  <span>Nhập thông tin</span>
                </button>
                <button
                  type="button"
                  onClick={() => setSidebarTab('upload')}
                  className={`flex-1 py-1 px-2.5 rounded text-[12px] font-semibold flex items-center justify-center gap-1 transition-all cursor-pointer ${
                    sidebarTab === 'upload'
                      ? 'bg-white text-red-600 shadow-xs border border-slate-200'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <UploadCloud className="w-3 h-3" />
                  <span>Tải tài liệu</span>
                </button>
              </div>

              <div className="flex-1 min-h-0 overflow-y-auto pr-1 space-y-3">

              {sidebarTab === 'manual' ? (
                <form onSubmit={handleSearch} className="space-y-3">
                  {apiError && (
                    <div className="rounded-md bg-red-50 px-3 py-2.5 text-xs leading-relaxed text-red-700">
                      {String(apiError)}
                    </div>
                  )}
                  <div>
                    <label className="mb-1.5 block text-[12.5px] font-semibold text-slate-900">
                      Thông tin cần tra cứu
                    </label>
                    <textarea
                      name="queryText"
                      rows={8}
                      value={formValues.queryText}
                      onChange={handleInputChange}
                      placeholder="Nhập tên, mã cá nhân, đơn vị, chức vụ hoặc nội dung mô tả"
                      className={`w-full min-h-[190px] resize-y rounded-md border bg-white p-3 text-[13.5px] leading-6 text-slate-900 outline-none transition-all ${
                        errors.queryText
                          ? 'border-red-400 focus:ring-1 focus:ring-red-500'
                          : 'border-slate-300 focus:border-red-500 focus:ring-1 focus:ring-red-500'
                      }`}
                    />
                    {errors.queryText && <p className="mt-1 text-[11.5px] font-medium text-red-500">{errors.queryText}</p>}
                    <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">
                      Hệ thống tự trích xuất các trường cần thiết từ nội dung này.
                    </p>
                  </div>

                  <div className="hidden">
                  <div>
                    <label className="block text-[12.5px] font-semibold text-slate-900 mb-1">
                      Họ và tên <span className="text-red-500">*</span>
                    </label>
                    <input
                      type="text"
                      name="fullName"
                      value={formValues.fullName}
                      onChange={handleInputChange}
                      placeholder="Nhập họ và tên"
                      className="w-full h-10 px-3 rounded-md border border-slate-300 focus:border-red-500 focus:ring-1 focus:ring-red-500 text-[13.5px] bg-white text-slate-900 outline-none"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-2.5">
                    <div>
                      <label className="block text-[12.5px] font-semibold text-slate-900 mb-1">Năm sinh</label>
                      <input
                        type="text"
                        name="birthYear"
                        value={formValues.birthYear}
                        onChange={handleInputChange}
                        placeholder="Năm sinh"
                        maxLength={5}
                        className={`w-full h-10 px-3 rounded-md border text-[13.5px] bg-white outline-none transition-all ${
                          errors.birthYear
                            ? 'border-red-500 focus:ring-1 focus:ring-red-500 text-red-600 bg-red-50/20'
                            : 'border-slate-300 focus:border-red-500 focus:ring-1 focus:ring-red-500 text-slate-900'
                        }`}
                      />
                      {errors.birthYear && (
                        <p className="text-[11.5px] text-red-500 mt-1 font-medium leading-tight">
                          {errors.birthYear}
                        </p>
                      )}
                    </div>

                    <div>
                      <label className="block text-[12.5px] font-semibold text-slate-900 mb-1">Chức vụ</label>
                      <input
                        type="text"
                        name="position"
                        value={formValues.position}
                        onChange={handleInputChange}
                        placeholder="Chức vụ"
                        className="w-full h-10 px-3 rounded-md border border-slate-300 focus:border-red-500 focus:ring-1 focus:ring-red-500 text-[13.5px] bg-white text-slate-900 outline-none"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-[12.5px] font-semibold text-slate-900 mb-1">Đơn vị</label>
                    <div className="relative">
                      <input
                        list="sidebar-department-options"
                        type="text"
                        name="department"
                        value={formValues.department}
                        onChange={handleInputChange}
                        placeholder="Nhập hoặc chọn đơn vị"
                        className="w-full h-10 px-3 pr-7 rounded-md border border-slate-300 focus:border-red-500 focus:ring-1 focus:ring-red-500 text-[13.5px] bg-white text-slate-900 outline-none"
                      />
                      <datalist id="sidebar-department-options">
                        <option value="Công an quận Hoàng Mai (Hà Nội)" />
                        <option value="Học viện An ninh Nhân dân" />
                        <option value="Quân khu 7 (Bộ Quốc phòng)" />
                        <option value="Bộ Tư lệnh Cảnh sát Cơ động" />
                        <option value="Cục Tác chiến - BQP" />
                      </datalist>
                      <div className="absolute inset-y-0 right-0 pr-2.5 flex items-center pointer-events-none text-slate-400">
                        <ChevronDown className="w-3.5 h-3.5" />
                      </div>
                    </div>
                  </div>

                  <div>
                    <label className="block text-[12.5px] font-semibold text-slate-900 mb-1">
                      Số hiệu / Mã định danh
                    </label>
                    <input
                      type="text"
                      name="identifier"
                      value={formValues.identifier}
                      onChange={handleInputChange}
                      placeholder="Số hiệu / Mã định danh"
                      className="w-full h-10 px-3 rounded-md border border-slate-300 focus:border-red-500 focus:ring-1 focus:ring-red-500 text-[13.5px] bg-white text-slate-900 outline-none uppercase"
                    />
                  </div>

                  <div>
                    <label className="block text-[12.5px] font-semibold text-slate-900 mb-1">Thông tin bổ sung</label>
                    <textarea
                      name="extraInfo"
                      value={formValues.extraInfo}
                      onChange={handleInputChange}
                      rows={2}
                      placeholder="Ghi chú hồ sơ hoặc quyết định"
                      className="w-full p-2.5 rounded-md border border-slate-300 focus:border-red-500 focus:ring-1 focus:ring-red-500 text-[13px] bg-white text-slate-900 outline-none resize-none"
                    />
                  </div>
                  </div>

                  <div className="pt-2 flex items-center gap-2">
                    <button
                      type="submit"
                      className="flex-1 h-10 rounded-md bg-red-600 hover:bg-red-700 text-white font-semibold text-[13.5px] flex items-center justify-center gap-1.5 shadow-sm transition-all"
                    >
                      <Search className="w-4 h-4" />
                      <span>Tra cứu</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleReset}
                      className="h-10 px-3.5 rounded-md border border-slate-200 hover:bg-slate-50 text-slate-700 font-semibold text-[13px] flex items-center justify-center gap-1.5 transition-all"
                    >
                      <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
                      <span>Xóa</span>
                    </button>
                  </div>
                </form>
              ) : (
                <div className="py-2 space-y-3">
                  {/* Hidden Sidebar File Input */}
                  <input
                    ref={sidebarFileInputRef}
                    type="file"
                    className="hidden"
                    accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.txt,.json,.csv,.log"
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        handleProcessFile(e.target.files[0]);
                      }
                    }}
                  />

                  {/* Dropzone Container */}
                  <div
                    onClick={() => !uploadedFile && openFilePicker(sidebarFileInputRef)}
                    onDragOver={(e) => {
                      e.preventDefault();
                      setIsDragging(true);
                    }}
                    onDragLeave={() => setIsDragging(false)}
                    onDrop={(e) => {
                      e.preventDefault();
                      setIsDragging(false);
                      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                        handleProcessFile(e.dataTransfer.files[0]);
                      }
                    }}
                    className={`border-2 border-dashed rounded-md p-3.5 text-center transition-all ${
                      isDragging
                        ? 'border-red-500 bg-red-50/60'
                        : uploadedFile
                        ? 'border-emerald-300 bg-emerald-50/20'
                        : 'border-slate-200 hover:border-red-400 bg-slate-50/50 cursor-pointer'
                    }`}
                  >
                    {isExtracting ? (
                      <div className="py-4 flex flex-col items-center justify-center space-y-2">
                        <div className="w-8 h-8 rounded-full border-2 border-red-600 border-t-transparent animate-spin flex items-center justify-center">
                          <Scan className="w-4 h-4 text-red-600" />
                        </div>
                        <p className="text-[12px] font-bold text-red-900">Đang đọc nội dung tài liệu</p>
                      </div>
                    ) : uploadedFile ? (
                      <div className="space-y-2 text-left">
                        <div className="flex items-center gap-2.5">
                          <div className="w-12 h-12 rounded-md border border-slate-200 bg-slate-100 flex-shrink-0 flex items-center justify-center overflow-hidden">
                            {filePreviewUrl && uploadedFile.type?.startsWith('image/') ? (
                              <img src={filePreviewUrl} alt="Scan" className="w-full h-full object-cover" />
                            ) : (
                              <FileText className="w-6 h-6 text-red-500" />
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-[12.5px] font-bold text-slate-900 truncate">{uploadedFile.name}</p>
                            <p className="text-[11px] text-slate-500">{(uploadedFile.size / 1024).toFixed(1)} KB</p>
                            <div className="mt-0.5">
                              <UploadStatusBadge data={extractedData} compact />
                            </div>
                          </div>
                        </div>

                        {/* Extracted field preview */}
                        <div className="p-2 rounded bg-white border border-slate-200 text-[11.5px] space-y-1">
                          <div className="flex justify-between">
                            <span className="text-slate-500">Họ tên:</span>
                            <span className="font-bold text-slate-900 truncate">{formValues.fullName || 'Chưa có'}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-slate-500">Đơn vị:</span>
                            <span className="font-bold text-slate-900 truncate max-w-[130px]">{formValues.department || 'Chưa có'}</span>
                          </div>
                        </div>

                        {/* Action buttons */}
                        <div className="grid grid-cols-3 gap-1.5 pt-1">
                          <button
                            type="button"
                            onClick={() => setIsOcrModalOpen(true)}
                            className="flex-1 py-1 px-2 rounded bg-red-50 hover:bg-red-100 text-red-700 font-semibold text-[11px] flex items-center justify-center gap-1"
                          >
                            <Eye className="w-3 h-3" />
                            <span>Xem thông tin đã nhận dạng</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => openFilePicker(sidebarFileInputRef)}
                            className="py-1 px-2 rounded border border-slate-200 hover:bg-slate-50 text-slate-700 font-medium text-[11px]"
                          >
                            Đổi tệp
                          </button>
                          <button
                            type="button"
                            onClick={handleClearUploadedFile}
                            className="py-1 px-2 rounded border border-red-200 hover:bg-red-50 text-red-600 font-medium text-[11px]"
                          >
                            Xóa
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="py-2">
                        <UploadCloud className="w-7 h-7 text-red-600 mx-auto mb-1" />
                        <p className="text-[12.5px] font-semibold text-slate-900">Tải ảnh thẻ / Quyết định</p>
                        <p className="text-[11px] text-slate-500 mt-0.5">JPG, PNG, PDF, Word &lt; 25MB</p>
                        <span className="mt-2 inline-flex items-center gap-1 text-[11px] text-red-600 font-semibold hover:underline">
                          <FolderOpen className="w-3 h-3" />
                          <span>Chọn tệp tải lên</span>
                        </span>
                      </div>
                    )}
                  </div>


                  {/* Main Action Button */}
                  <button
                    type="button"
                    onClick={handleSearch}
                    className="w-full h-10 rounded-md bg-red-600 hover:bg-red-700 text-white font-semibold text-[13px] flex items-center justify-center gap-1.5 shadow-sm transition-all"
                  >
                    <Scan className="w-4 h-4" />
                    <span>Trích xuất &amp; Tra cứu</span>
                  </button>
                </div>
              )}
              </div>
            </aside>

            {/* Main Dynamic Panel */}
            <div className="flex-1 flex flex-col min-w-0 min-h-0 lg:h-full overflow-y-auto lg:overflow-hidden">
              {/* Metadata Bar */}
              <div className="flex-shrink-0 flex flex-wrap items-center justify-between gap-2 pb-2 mb-2 border-b border-slate-200 select-none">
                <div className="flex items-center gap-2.5">
                  <button
                    type="button"
                    onClick={() => setAppState('initial')}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-slate-200 hover:bg-slate-50 text-[12.5px] font-semibold text-slate-700 transition-colors group cursor-pointer"
                    title="Quay lại biểu mẫu tra cứu"
                  >
                    <ArrowLeft className="w-3.5 h-3.5 group-hover:-translate-x-0.5 transition-transform text-slate-500" />
                    <span>Tra cứu mới</span>
                  </button>

                  <div className="h-3.5 w-[1px] bg-slate-200" />

                  <span className="font-mono text-slate-900 font-bold text-[12.5px]">
                    {currentCaseData?.case_code || 'Chưa có'}
                  </span>
                  <span className="hidden sm:inline h-3.5 w-[1px] bg-slate-200" />
                  <span className="hidden sm:inline text-[11.5px] text-slate-500">
                    {new Date().toLocaleDateString('vi-VN')}
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-[11.5px] border font-bold flex items-center gap-1.5 ${
                      appState === 'loading'
                        ? 'bg-red-50 text-red-600 border-red-200'
                        : appState === 'verified'
                        ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                        : appState === 'needs-verification'
                        ? 'bg-[#FDF0BE] text-amber-800 border-amber-200'
                        : 'bg-slate-100 text-slate-600 border-slate-200'
                    }`}
                  >
                    {appState === 'loading' && <span className="w-1.5 h-1.5 rounded-full bg-red-600 animate-ping"></span>}
                    {appState === 'loading'
                      ? 'Đang xử lý'
                      : appState === 'verified'
                      ? 'Đã xác định đơn vị'
                      : appState === 'needs-verification'
                      ? 'Cần xác minh'
                      : 'Không tìm thấy'}
                  </span>
                </div>
              </div>

              {/* Dynamic View States */}
              <div className="flex-1 min-h-0 overflow-y-auto pr-1">
                {/* STATE 2: LOADING */}
                {appState === 'loading' && (
                  <div className="bg-white rounded-md border border-slate-200 shadow-sm p-6 sm:p-8 relative overflow-hidden flex-1 flex flex-col justify-between">
                    <div className="text-center mb-8 max-w-[620px] mx-auto">
                      {/* Dynamic Alert Status for Processing */}
                      <div className="inline-flex items-center gap-2.5 px-4 py-2 rounded-md bg-red-50/90 border border-red-200 text-red-800 shadow-xs mb-3">
                        <Loader2 className="w-4 h-4 text-red-600 animate-spin flex-shrink-0" />
                        <span className="text-[12px] font-bold uppercase tracking-wider text-red-600">
                          Đang xử lý:
                        </span>
                        <span className="text-[13px] font-semibold text-slate-900 min-w-[280px] text-left">
                          {loadingProgress < 33
                            ? 'Tiếp nhận và kiểm tra thông tin hồ sơ'
                            : loadingProgress < 66
                            ? 'Nhận dạng thông tin nhân sự'
                            : 'Đối chiếu với danh mục đơn vị'}
                        </span>
                      </div>

                      <h2 className="text-[20px] font-bold text-slate-900">Đang phân tích thông tin</h2>
                      <p className="text-[14.5px] text-slate-500 mt-1.5 leading-relaxed">
                        Hệ thống đang tiếp nhận, trích xuất và đối chiếu dữ liệu để xác định kết quả.
                      </p>
                    </div>

                    {/* Stepper with ultra-smooth 60fps dynamic active state */}
                    <div className="max-w-[760px] mx-auto mb-8 sm:mb-10 px-2 sm:px-6 w-full">
                      <div className="relative flex items-center justify-between">
                        {/* Background track running exactly from center of step 1 to center of step 4 */}
                        <div className="absolute left-[40px] right-[40px] sm:left-[48px] sm:right-[48px] top-4 sm:top-5 h-[3px] bg-slate-200 rounded-full z-0 overflow-hidden">
                          <div
                            className="h-full bg-red-600 rounded-full transition-[width] duration-75 ease-linear relative overflow-hidden"
                            style={{ width: `${loadingProgress}%` }}
                          >
                            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/40 to-transparent animate-shimmer" />
                          </div>
                        </div>

                        {/* Step 1: Tiếp nhận */}
                        <div className="relative z-10 flex flex-col items-center w-20 sm:w-24 text-center">
                          <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-full bg-red-600 text-white flex items-center justify-center font-bold text-[12px] sm:text-[14px] shadow-sm ring-4 ring-white">
                            <Check className="w-4 h-4 sm:w-5 sm:h-5" />
                          </div>
                          <span className="text-[11px] sm:text-[13px] font-bold text-slate-900 mt-1.5 sm:mt-2">Tiếp nhận</span>
                          <span className="text-[10px] sm:text-[11.5px] text-emerald-600 font-semibold hidden xs:block sm:block">Hoàn tất</span>
                        </div>

                        {/* Step 2: Trích xuất */}
                        <div className="relative z-10 flex flex-col items-center w-20 sm:w-24 text-center">
                          <div className={`w-8 h-8 sm:w-10 sm:h-10 rounded-full flex items-center justify-center font-bold text-[12px] sm:text-[14px] ring-4 ring-white transition-all duration-300 ${
                            loadingProgress >= 66
                              ? 'bg-red-600 text-white shadow-sm'
                              : loadingProgress >= 33
                              ? 'bg-white border-2 border-red-600 text-red-600 shadow-md ring-offset-2 ring-offset-red-50'
                              : 'bg-white border border-slate-300 text-slate-400'
                          }`}>
                            {loadingProgress >= 66 ? <Check className="w-4 h-4 sm:w-5 sm:h-5" /> : '2'}
                          </div>
                          <span className={`text-[11px] sm:text-[13px] mt-1.5 sm:mt-2 transition-colors ${
                            loadingProgress >= 33 ? 'font-bold text-red-600' : 'font-medium text-slate-500'
                          }`}>
                            Trích xuất
                          </span>
                          <span className={`text-[10px] sm:text-[11.5px] hidden xs:block sm:block transition-colors ${
                            loadingProgress >= 66
                              ? 'text-emerald-600 font-semibold'
                              : loadingProgress >= 33
                              ? 'text-red-600 font-semibold animate-pulse'
                              : 'text-slate-400'
                          }`}>
                            {loadingProgress >= 66 ? 'Hoàn tất' : loadingProgress >= 33 ? 'Đang xử lý' : 'Chờ xử lý'}
                          </span>
                        </div>

                        {/* Step 3: Đối chiếu */}
                        <div className="relative z-10 flex flex-col items-center w-20 sm:w-24 text-center">
                          <div className={`w-8 h-8 sm:w-10 sm:h-10 rounded-full flex items-center justify-center font-bold text-[12px] sm:text-[14px] ring-4 ring-white transition-all duration-300 ${
                            loadingProgress >= 66
                              ? 'bg-white border-2 border-red-600 text-red-600 shadow-md ring-offset-2 ring-offset-red-50'
                              : 'bg-white border border-slate-300 text-slate-400 font-medium'
                          }`}>
                            3
                          </div>
                          <span className={`text-[11px] sm:text-[13px] mt-1.5 sm:mt-2 transition-colors ${
                            loadingProgress >= 66 ? 'font-bold text-red-600' : 'font-medium text-slate-500'
                          }`}>
                            Đối chiếu
                          </span>
                          <span className={`text-[10px] sm:text-[11.5px] hidden xs:block sm:block transition-colors ${
                            loadingProgress >= 66 ? 'text-red-600 font-semibold animate-pulse' : 'text-slate-400'
                          }`}>
                            {loadingProgress >= 66 ? 'Đang xử lý' : 'Chờ xử lý'}
                          </span>
                        </div>

                        {/* Step 4: Kết quả */}
                        <div className="relative z-10 flex flex-col items-center w-20 sm:w-24 text-center">
                          <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-full bg-white border border-slate-300 text-slate-400 flex items-center justify-center font-medium text-[12px] sm:text-[14px] ring-4 ring-white">
                            4
                          </div>
                          <span className="text-[11px] sm:text-[13px] font-medium text-slate-500 mt-1.5 sm:mt-2">Kết quả</span>
                          <span className="text-[10px] sm:text-[11.5px] text-slate-400 hidden xs:block sm:block">Chờ xử lý</span>
                        </div>
                      </div>
                    </div>

                    <div className="mt-6 p-4 rounded-md bg-red-50/70 border border-red-200/80 flex items-start gap-3">
                      <Info className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
                      <div>
                        <h5 className="text-[13.5px] font-bold text-slate-900">Lưu ý nghiệp vụ</h5>
                        <p className="text-[12.5px] text-slate-600 mt-0.5">
                          Hệ thống không tự kết luận khi thiếu căn cứ. Các trường hợp này sẽ được chuyển cho cán bộ thẩm định.
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* STATE 3: VERIFIED SUCCESS */}
                {appState === 'verified' && (() => {
                  const currentOrg =
                    currentCaseData?.organization_type ||
                    ((formValues.department || '').toLowerCase().includes('quân') ||
                    (formValues.department || '').toLowerCase().includes('bqp') ||
                    (formValues.identifier || '').toUpperCase().startsWith('BQP-')
                      ? 'BQP'
                      : 'BCA');
                  const isBqp = currentOrg === 'BQP';
                  const eligibility = Array.isArray(currentCaseData?.eligibility) ? currentCaseData.eligibility : [];
                  const subjectGroup = currentCaseData?.subject_group || null;
                  const subjectGroupMethod = currentCaseData?.subject_group_method || null;
                  const subjectGroupConfidence = currentCaseData?.subject_group_confidence;
                  const taxonomyVersion = currentCaseData?.taxonomy_version || null;
                  const salaryStatus = currentCaseData?.salary_status || 'Không đủ dữ liệu';
                  const hasPolicyConclusion = eligibility.some((item) =>
                    ['ELIGIBLE', 'NOT_ELIGIBLE', 'NOT_APPLICABLE'].includes(item?.status)
                  );
                  const canonicalUnit = currentCaseData?.current_unit || formValues.department || 'Chưa xác định đơn vị';

                  return (
                    <div className="space-y-5">
                      <CorrectionNotice fields={correctedFields} />
                      {/* Success Banner */}
                      <div className="relative overflow-hidden rounded-md bg-white border border-slate-200 shadow-sm">
                        <div className="p-5 sm:p-6 flex items-start gap-4">
                          <div className={`w-14 h-14 rounded-md flex items-center justify-center flex-shrink-0 ${
                            isBqp ? 'bg-emerald-50 text-emerald-600' : 'bg-red-50 text-red-600'
                          }`}>
                            <ShieldCheck className="w-8 h-8" />
                          </div>
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2 mb-1">
                              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider ${
                                isBqp ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'
                              }`}>
                                <CheckCircle2 className="w-3 h-3" />
                                Kết quả đối chiếu chuẩn
                              </span>
                            </div>
                            <h2 className="text-[21px] sm:text-[24px] font-bold text-slate-900 leading-tight">
                              Đơn vị thuộc phạm vi quản lý{' '}
                              <span className={isBqp ? 'text-emerald-700' : 'text-red-700'}>
                                {isBqp ? 'Bộ Quốc phòng' : 'Bộ Công an'}
                              </span>
                            </h2>
                            <p className="text-[13.5px] text-slate-600 mt-1.5 leading-relaxed">
                              Đã đối chiếu và xác định đơn vị <strong className="text-slate-800">{canonicalUnit}</strong> thuộc {isBqp ? 'Bộ Quốc phòng' : 'Bộ Công an'}.
                              {!subjectGroup && ' Chưa đủ dữ liệu để xác định nhóm đối tượng và chế độ, quyền lợi.'}
                            </p>
                          </div>
                        </div>
                      </div>

                      {/* 2-Column Info Grid */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                        {/* Left: Thông tin định danh */}
                        <div className="bg-white rounded-md border border-slate-200 shadow-sm overflow-hidden">
                          <div className="px-5 py-4 flex items-center gap-2.5 border-b border-slate-100 bg-slate-50/60">
                            <User className="w-4 h-4 text-slate-400" />
                            <h3 className="text-[15px] font-bold text-slate-900">Thông tin định danh</h3>
                          </div>

                          <div className="px-5 pt-4 pb-1">
                            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Họ và tên</span>
                            <p className="text-[19px] font-bold text-slate-900 leading-tight mt-0.5">
                              {formValues.fullName || currentCaseData?.fullName || 'Chưa cung cấp'}
                            </p>
                          </div>

                          <div className="px-5 pb-4 divide-y divide-slate-100 text-[13.5px] mt-2">
                            <div className="py-2.5 flex justify-between items-center">
                              <span className="text-slate-500 font-medium">Năm sinh</span>
                              <span className="text-slate-900 font-semibold">
                                {formValues.birthYear
                                  ? `${formValues.birthYear} (${new Date().getFullYear() - parseInt(formValues.birthYear, 10)} tuổi)`
                                  : 'Chưa rõ năm sinh'}
                              </span>
                            </div>
                            <div className="py-2.5 flex justify-between items-center">
                              <span className="text-slate-500 font-medium">Giới tính</span>
                              <span className="text-slate-500 font-medium">Chưa có dữ liệu</span>
                            </div>
                            <div className="py-2.5 flex justify-between items-center gap-4">
                              <span className="text-slate-500 font-medium flex-shrink-0">Đơn vị</span>
                              <span className="text-slate-900 font-semibold text-right truncate">
                                {canonicalUnit}
                              </span>
                            </div>
                            <div className="py-2.5 flex justify-between items-center">
                              <span className="text-slate-500 font-medium">Chức vụ</span>
                              <span className="text-slate-900 font-semibold">
                                {formValues.position || 'Chưa có dữ liệu'}
                              </span>
                            </div>
                            <div className="py-2.5 flex justify-between items-center">
                              <span className="text-slate-500 font-medium">Mã định danh</span>
                              {formValues.identifier ? (
                                <span className="font-mono text-red-700 font-bold bg-red-50 px-2 py-0.5 rounded border border-red-200 text-[12.5px]">
                                  {formValues.identifier}
                                </span>
                              ) : (
                                <span className="text-slate-500 font-medium">Chưa có dữ liệu</span>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Right: Nhóm đối tượng và kết quả policy */}
                        <div className="bg-white rounded-md border border-slate-200 shadow-sm overflow-hidden">
                          <div className="px-5 py-4 flex items-center gap-2.5 border-b border-slate-100 bg-slate-50/60">
                            <Award className="w-4 h-4 text-slate-400" />
                            <h3 className="text-[15px] font-bold text-slate-900">Nhóm đối tượng &amp; chế độ</h3>
                          </div>

                          <div className="px-5 pt-4 pb-1 flex flex-wrap items-center gap-2">
                            <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[13px] font-bold border ${
                              subjectGroup
                                ? 'bg-red-50 text-red-800 border-red-200'
                                : 'bg-[#FDF0BE] text-amber-800 border-amber-200'
                            }`}>
                              {subjectGroup ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Info className="w-3.5 h-3.5" />}
                              {subjectGroup || 'Chưa xác định nhóm đối tượng'}
                            </span>
                            {typeof subjectGroupConfidence === 'number' && (
                              <span className="text-[11px] font-semibold text-slate-500">
                                Độ tin cậy: {Math.round(subjectGroupConfidence * 100)}%
                              </span>
                            )}
                          </div>
                          {(subjectGroupMethod || taxonomyVersion) && (
                            <div className="px-5 pb-1 text-[11.5px] text-slate-500 leading-snug">
                              {subjectGroupMethod && (SUBJECT_GROUP_METHOD_LABELS[subjectGroupMethod] || subjectGroupMethod)}
                              {taxonomyVersion && <span className="ml-1 text-slate-400">(bộ tiêu chí {taxonomyVersion})</span>}
                            </div>
                          )}

                          <div className="px-5 pb-4 divide-y divide-slate-100 text-[13.5px] mt-2">
                            <div className="py-2.5 flex justify-between items-center">
                              <span className="text-slate-500 font-medium">Tình trạng lương</span>
                              <span className={salaryStatus === 'Có' ? 'text-emerald-700 font-semibold' : 'text-slate-700 font-semibold'}>{salaryStatus}</span>
                            </div>
                            <div className="py-2.5 flex justify-between items-center">
                              <span className="text-slate-500 font-medium">Đánh giá chính sách</span>
                              <span className="text-slate-900 font-semibold">{hasPolicyConclusion ? 'Đã có kết quả' : 'Chưa đủ dữ liệu'}</span>
                            </div>
                            <div className="py-2.5">
                              <span className="text-slate-500 font-medium block mb-1">Kết luận</span>
                              {eligibility.length > 0 ? (
                                <div className="space-y-1.5">
                                  {eligibility.map((item, index) => (
                                    <div key={`${item.policy_id || 'policy'}-${index}`} className="text-[13px] leading-snug">
                                      <span className="font-semibold text-slate-800">{item.policy_id}</span>
                                      {item.policy_version && <span className="font-mono text-[10.5px] text-slate-400 ml-1">v{item.policy_version}</span>}
                                      <span className="text-slate-600">: {item.reason || POLICY_STATUS_LABELS[item.status] || 'Chưa xác định'}</span>
                                      {item.evidence?.as_of_date && (
                                        <span className="text-slate-400 text-[11px] ml-1">(tính đến {item.evidence.as_of_date})</span>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <span className="text-slate-600 font-medium text-[13px] leading-snug block">
                                  Chưa có căn cứ để kết luận người này thuộc nhóm nào, hưởng lương hay đủ điều kiện hưởng chế độ. Cần bổ sung dữ liệu nghiệp vụ.
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Căn cứ đối chiếu */}
                      <div className="bg-white rounded-md border border-slate-200 p-5 shadow-sm">
                        <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-100">
                          <h3 className="text-[16px] font-bold text-slate-900">Căn cứ đối chiếu</h3>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
                          {[
                            { icon: User, label: formValues.fullName ? `Họ tên: ${formValues.fullName}` : 'Chưa có họ tên', verified: Boolean(formValues.fullName) },
                            {
                              icon: Calendar,
                              label: formValues.birthYear ? `Năm sinh: ${formValues.birthYear}` : 'Chưa có năm sinh',
                              verified: Boolean(formValues.birthYear),
                            },
                            {
                              icon: Building2,
                              label: `Đơn vị: ${canonicalUnit}`,
                              verified: true,
                            },
                            {
                              icon: Hash,
                              label: formValues.identifier ? `Mã: ${formValues.identifier}` : 'Chưa có mã định danh',
                              verified: Boolean(formValues.identifier),
                            },
                          ].map(({ icon: Icon, label, verified }, i) => (
                            <div key={i} className={`p-3 rounded-md border flex items-start gap-2 ${verified ? 'bg-emerald-50/60 border-emerald-200' : 'bg-slate-50 border-slate-200'}`}>
                              {verified ? <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" /> : <Info className="w-4 h-4 text-slate-400 flex-shrink-0 mt-0.5" />}
                              <div className="min-w-0">
                                <Icon className={`w-3.5 h-3.5 mb-1 ${verified ? 'text-emerald-500' : 'text-slate-400'}`} />
                                <p className={`text-[12.5px] font-semibold leading-snug truncate ${verified ? 'text-emerald-900' : 'text-slate-600'}`}>{label}</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Nguồn dữ liệu */}
                      <div className="bg-white rounded-md border border-slate-200 p-5 shadow-sm">
                        <div className="pb-3 mb-3 border-b border-slate-100">
                          <h3 className="text-base sm:text-lg font-bold text-slate-900">Nguồn dữ liệu &amp; Xuất xứ thẩm định</h3>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
                          <div className="p-3 bg-slate-50 rounded-md border border-slate-200">
                            <span className="text-slate-500 text-xs block">Nguồn cơ sở dữ liệu:</span>
                            <span className="font-bold text-slate-900 mt-0.5 block">{SOURCE_KIND_LABELS[currentCaseData?.evidence?.unit_source_kind] || SOURCE_KIND_LABELS[currentCaseData?.evidence?.source_kind] || 'Danh mục đơn vị nghiệp vụ'}</span>
                          </div>
                          <div className="p-3 bg-slate-50 rounded-md border border-slate-200">
                            <span className="text-slate-500 text-xs block">Phiên bản danh mục:</span>
                            <span className="font-mono font-bold text-slate-900 mt-0.5 block">{currentCaseData?.evidence?.registry_version || 'Chưa có'}</span>
                          </div>
                          <div className="p-3 bg-slate-50 rounded-md border border-slate-200">
                            <span className="text-slate-500 text-xs block">Căn cứ quy định:</span>
                            <span className="font-bold text-slate-900 mt-0.5 block">{eligibility.length > 0 ? eligibility.map((item) => item.policy_id).filter(Boolean).join(', ') : 'Chưa có căn cứ chính sách'}</span>
                          </div>
                          <div className="p-3 bg-slate-50 rounded-md border border-slate-200">
                            <span className="text-slate-500 text-xs block">Phiên bản bộ tiêu chí:</span>
                            <span className="font-mono font-bold text-slate-900 mt-0.5 block">{taxonomyVersion || 'Chưa có'}</span>
                          </div>
                        </div>

                        {eligibility.some((item) => item.evidence && Object.keys(item.evidence).length > 0) && (
                          <div className="mt-4 pt-3 border-t border-slate-100 space-y-2">
                            <span className="text-slate-500 text-xs font-semibold uppercase tracking-wide">Căn cứ chi tiết theo từng quy định</span>
                            {eligibility.filter((item) => item.evidence).map((item, idx) => (
                              <div key={`${item.policy_id || 'policy'}-evidence-${idx}`} className="text-[12.5px] bg-slate-50 rounded-md border border-slate-200 p-3">
                                <div className="font-semibold text-slate-800 mb-1">
                                  {item.policy_id} {item.policy_version && <span className="font-mono text-[11px] text-slate-400">v{item.policy_version}</span>}
                                </div>
                                <div className="grid grid-cols-2 gap-1.5 text-slate-600">
                                  {item.evidence?.source_ref && <div><span className="text-slate-400">Nguồn:</span> {item.evidence.source_ref}</div>}
                                  {item.evidence?.as_of_date && <div><span className="text-slate-400">Tính đến:</span> {item.evidence.as_of_date}</div>}
                                  {item.evidence?.scope_only !== undefined && (
                                    <div><span className="text-slate-400">Chỉ phạm vi áp dụng:</span> {item.evidence.scope_only ? 'Có' : 'Không'}</div>
                                  )}
                                  {item.evidence?.facts_used && Object.keys(item.evidence.facts_used).length > 0 && (
                                    <div className="col-span-2"><span className="text-slate-400">Dữ kiện sử dụng:</span> {JSON.stringify(item.evidence.facts_used)}</div>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Action Bar for Verified Result */}
                      <div className="pt-2 flex flex-col sm:flex-row items-stretch sm:items-center justify-end gap-2.5 sm:gap-3">
                        <button
                          type="button"
                          onClick={handleExportPdf}
                          className="px-4 py-2.5 rounded-md border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-sm font-semibold flex items-center justify-center gap-1.5 shadow-xs transition-colors cursor-pointer"
                          title="In hoặc lưu kết quả thẩm định ra PDF"
                        >
                          <Download className="w-4 h-4 text-slate-500" />
                          <span>Xuất biên bản (PDF)</span>
                        </button>
                      </div>
                    </div>
                  );
                })()}

                {/* STATE 4: NEEDS VERIFICATION */}
                {appState === 'needs-verification' && (
                  <NeedsVerificationView
                    candidateName={formValues.fullName}
                    formValues={formValues}
                    currentCaseData={currentCaseData}
                    onViewOriginalDossier={handleOpenOriginalDossier}
                    onViewDetailedCompare={handleOpenDetailedCompare}
                  />
                )}

                {/* STATE 5: NO CONCLUSION */}
                {appState === 'no-conclusion' && (
                  <NoConclusionView
                    formValues={formValues}
                    onRetrySearch={() => {
                      setAppState('initial');
                    }}
                    onEditInfo={() => {
                      setAppState('initial');
                    }}
                  />
                )}
              </div>
            </div>
          </div>
        )}
      </main>

      <AppFooter />

      {modalLoadError && (
        <div className="fixed bottom-4 right-4 z-[60] max-w-sm rounded-md border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-800 shadow-lg">
          <div className="flex items-start justify-between gap-3">
            <span>{modalLoadError}</span>
            <button type="button" onClick={() => setModalLoadError(null)} className="text-red-500 hover:text-red-700">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Modals for Xem hồ sơ gốc & Đối chiếu chi tiết — both render the real
          case detail fetched by openCaseModal(); no client-side approval
          step here, decisions go through the Review queue's real endpoint. */}
      <OriginalDossierModal
        isOpen={isOriginalDossierOpen}
        onClose={() => setIsOriginalDossierOpen(false)}
        caseDetail={modalCaseDetail}
        onOpenCompare={() => {
          setIsOriginalDossierOpen(false);
          setIsDetailedCompareOpen(true);
        }}
      />

      <DetailedComparisonModal
        isOpen={isDetailedCompareOpen}
        onClose={() => setIsDetailedCompareOpen(false)}
        caseDetail={modalCaseDetail}
      />

      {/* OCR Result & Entity Extraction Review Modal */}
      <OcrResultModal
        isOpen={isOcrModalOpen}
        onClose={() => setIsOcrModalOpen(false)}
        file={uploadedFile}
        filePreviewUrl={filePreviewUrl}
        extractedData={extractedData}
        onConfirmBulk={async (jobId, mapping) => {
          const response = await axios.post(`/api/v1/bulk/${jobId}/confirm`, { mapping }, { timeout: 10000 });
          setUploadMessage('Danh sách đã được tiếp nhận và đang chờ xử lý.');
          return response.data;
        }}
        onConfirmAndSearch={(updatedFields) => {
          // Pass the edited values straight into handleSearch rather than
          // writing state and hoping React has flushed before the call — the
          // previous setTimeout(60) version silently searched on stale values.
          setFormValues((prev) => ({ ...prev, ...updatedFields }));
          setIsOcrModalOpen(false);
          handleSearch(null, { values: updatedFields, correctedFrom: pendingCaseId });
        }}
      />
    </div>
  );
}

const RECENT_STATUS = {
  VERIFIED: { label: 'Đã xác định', className: 'bg-emerald-100 text-emerald-800' },
  NEED_REVIEW: { label: 'Cần xác minh', className: 'bg-amber-100 text-amber-800' },
  NO_CONCLUSION: { label: 'Chưa có kết luận', className: 'bg-slate-100 text-slate-600' },
};

// Latest cases from the same backend-synced list the Lịch sử tab shows.
function RecentCasesPanel({ items, onOpen, onShowAll }) {
  const recent = items.slice(0, 8);
  return (
    <aside className="lg:col-span-4 bg-white border border-slate-200 rounded-md shadow-xs flex flex-col min-h-0">
      <div className="px-3 sm:px-4 py-2.5 border-b border-slate-200 flex items-center justify-between">
        <h2 className="text-[13px] font-bold text-slate-900">Hồ sơ tra cứu gần đây</h2>
        {items.length > 0 && (
          <button
            type="button"
            onClick={onShowAll}
            className="text-[11.5px] font-semibold text-blue-600 hover:text-blue-800 hover:underline"
          >
            Xem tất cả
          </button>
        )}
      </div>
      {recent.length === 0 ? (
        <p className="px-4 py-8 text-center text-xs text-slate-400">Chưa có hồ sơ nào.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {recent.map((item) => {
            const status = RECENT_STATUS[item.statusCategory] || RECENT_STATUS.NO_CONCLUSION;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onOpen(item)}
                  className="w-full text-left px-3 sm:px-4 py-2 hover:bg-slate-50 flex items-center gap-2 cursor-pointer"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[12.5px] font-semibold text-slate-900 truncate">{item.fullName}</span>
                      <span className={`flex-shrink-0 px-1.5 py-0.5 rounded text-[10.5px] font-medium ${status.className}`}>
                        {status.label}
                      </span>
                    </div>
                    <div className="mt-0.5 flex items-center justify-between gap-2 text-[11px] text-slate-500">
                      <span className="truncate">{item.department}</span>
                      <span className="flex-shrink-0 font-mono">{item.timestamp}</span>
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-400 flex-shrink-0" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}

// Sub-Component: Needs Verification View
function NeedsVerificationView({ candidateName, formValues, currentCaseData, onViewOriginalDossier, onViewDetailedCompare }) {
  const [selectedRow, setSelectedRow] = useState(1);
  const [detailTab, setDetailTab] = useState('identity');

  const displayName = candidateName || formValues?.fullName || 'Đối tượng xác minh';
  const displayYear = formValues?.birthYear || 'Chưa có';

  // Real candidates come from the resolver's top_candidates. The resolver takes one
  // of two shapes depending on how the search was run:
  //  - unit-name lookup (PersonResolver not involved): same person on every row,
  //    only the matched unit/org/score differ -> canonical_name/unit_id.
  //  - person-name lookup (PersonResolver): a different real person matched on every
  //    row -> full_name/canonical_unit_name/canonical_unit_id.
  // Normalize both into the exact fields the view below renders, so nothing past
  // this point needs to branch on which resolver produced the data.
  const rawCandidates = Array.isArray(currentCaseData?.topCandidates) ? currentCaseData.topCandidates : [];
  const isPersonLookup = rawCandidates.some((c) => c.full_name || c.canonical_unit_name);

  if (rawCandidates.length === 0) {
    return (
      <div className="rounded-md bg-white p-6 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-md bg-slate-100 text-slate-500">
            <HelpCircle className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h2 className="text-lg font-bold text-slate-900">Chưa đủ dữ liệu để xác định</h2>
            <p className="mt-1 text-sm leading-relaxed text-slate-600">
              Hệ thống chưa tìm thấy ứng viên hoặc đơn vị đủ tin cậy để đối chiếu. Hãy bổ sung mã cá nhân,
              tên đơn vị đầy đủ, chức vụ hoặc tài liệu có căn cứ rõ hơn.
            </p>
            {formValues?.queryText && (
              <div className="mt-4 rounded-md bg-slate-50 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Nội dung đã tra cứu</p>
                <p className="mt-1 whitespace-pre-wrap text-sm text-slate-800">{formValues.queryText}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  const groupColors = {
    BCA: 'bg-red-50 text-red-700 border-red-200',
    BQP: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    OTHER: 'bg-slate-50 text-slate-600 border-slate-200',
  };
  const candidates = rawCandidates.map((c, idx) => ({
    id: idx + 1,
    subjectName: isPersonLookup ? c.full_name || 'Chưa có' : displayName,
    subjectYear: isPersonLookup ? c.birth_year || 'Chưa rõ' : displayYear,
    unitName: c.canonical_name || c.canonical_unit_name || c.unit_id || c.canonical_unit_id || 'Không rõ đơn vị',
    unitId: c.unit_id || c.canonical_unit_id || 'Chưa có',
    orgType: c.organization_type || 'OTHER',
    orgBadgeClass: groupColors[c.organization_type] || groupColors.OTHER,
    score: typeof c.score === 'number' ? `${Math.round(c.score)}%` : c.score ?? 'Chưa có',
  }));
  const selectedCandidate = candidates.find((c) => c.id === selectedRow) || candidates[0];

  return (
    <div className="space-y-5">
      {/* Candidate Table */}
      <div className="bg-white rounded-md border border-slate-200 shadow-sm p-5">
        <div className="mb-4 flex items-start gap-3">
          <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md bg-[#FDF0BE] text-amber-600">
            <AlertTriangle className="h-[18px] w-[18px]" />
          </div>
          <div className="min-w-0 pt-0.5">
            <h2 className="text-[16px] font-bold text-slate-900">Có nhiều kết quả phù hợp</h2>
            <p className="mt-0.5 text-[12.5px] leading-relaxed text-slate-500">
              Chọn một ứng viên bên dưới để kiểm tra trước khi đưa ra kết luận.
            </p>
          </div>
        </div>
        <div className="mb-4 rounded-md border border-red-100 bg-red-50/60 px-4 py-3 text-sm">
          <span className="text-slate-500">Thông tin đã nhập:</span>{' '}
          <strong className="text-slate-900">{displayName}</strong>
          {displayYear !== 'Chưa có' && <span className="text-slate-600">, năm sinh {displayYear}</span>}
        </div>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <h3 className="text-[16px] font-bold text-slate-900">
              {isPersonLookup ? `Đối tượng khớp (${candidates.length} kết quả)` : `Đơn vị khớp (${candidates.length} kết quả)`}
            </h3>
            <span className="text-[12px] text-slate-500">
              {isPersonLookup ? 'Từ danh mục đối tượng, xếp theo mức độ phù hợp' : 'Từ danh mục đơn vị, xếp theo mức độ phù hợp'}
            </span>
          </div>

        </div>

        {/* Mobile Candidates List (< sm) */}
        <div className="block sm:hidden divide-y divide-slate-100 border border-slate-200 rounded-md overflow-hidden">
          {candidates.map((cand) => {
            const isSelected = cand.id === selectedRow;
            return (
              <div
                key={cand.id}
                onClick={() => setSelectedRow(cand.id)}
                className={`p-3.5 space-y-2 cursor-pointer transition-colors ${
                  isSelected ? 'bg-red-50/80' : 'hover:bg-slate-50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-bold text-slate-900 text-[14px]">{isPersonLookup ? cand.subjectName : cand.unitName}</span>
                  <span className="text-slate-500 text-[12px] font-mono">#{cand.id}</span>
                </div>
                {isPersonLookup && (
                  <div className="text-[12.5px] text-slate-600">Đơn vị: {cand.unitName}</div>
                )}
                <div className="flex items-center gap-2.5 text-[12.5px] text-slate-600">
                  <span>Độ tin cậy: <strong>{cand.score}</strong></span>
                  <span className="w-px h-3 bg-slate-300" />
                  <span>Mã đơn vị: {cand.unitId}</span>
                </div>
                <div>
                  <span className={`inline-block px-2.5 py-0.5 rounded-full text-[11.5px] font-semibold border ${cand.orgBadgeClass}`}>
                    {cand.orgType}
                  </span>
                </div>
              </div>
            );
          })}
          {candidates.length === 0 && (
            <div className="p-6 text-center text-slate-400 text-[13px]">Không tìm thấy kết quả phù hợp.</div>
          )}
        </div>

        {/* Desktop Candidates Table (>= sm) */}
        <div className="hidden sm:block overflow-x-auto border border-slate-200 rounded-md">
          <table className="w-full text-left text-[13.5px] border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-[12.5px] font-bold text-slate-600">
                <th className="py-3 px-4 w-12 text-center">#</th>
                {isPersonLookup && <th className="py-3 px-4">Họ và tên</th>}
                <th className="py-3 px-4">Đơn vị khớp</th>
                <th className="py-3 px-4">Mã đơn vị</th>
                <th className="py-3 px-4">Độ tin cậy</th>
                <th className="py-3 px-4">Tổ chức</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {candidates.map((cand) => {
                const isSelected = cand.id === selectedRow;
                return (
                  <tr
                    key={cand.id}
                    onClick={() => setSelectedRow(cand.id)}
                    className={`cursor-pointer transition-colors ${
                      isSelected ? 'bg-red-50/80 font-medium' : 'hover:bg-slate-50'
                    }`}
                  >
                    <td className="py-3 px-4 text-center font-bold relative">
                      <span className={isSelected ? 'text-red-600' : 'text-slate-400'}>{cand.id}</span>
                    </td>
                    {isPersonLookup && <td className="py-3 px-4 font-bold text-slate-900">{cand.subjectName}</td>}
                    <td className="py-3 px-4 font-bold text-slate-900">{cand.unitName}</td>
                    <td className="py-3 px-4 text-slate-500 font-mono text-[12px]">{cand.unitId}</td>
                    <td className="py-3 px-4 text-slate-800">{cand.score}</td>
                    <td className="py-3 px-4">
                      <span className={`inline-block px-2.5 py-0.5 rounded-full text-[12px] font-semibold border ${cand.orgBadgeClass}`}>
                        {cand.orgType}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {candidates.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-slate-400">Không tìm thấy kết quả phù hợp.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-white rounded-md border border-slate-200 shadow-sm p-5">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <span className="px-2.5 py-0.5 rounded-md bg-red-100 text-red-600 font-bold text-[12px] border border-red-200">
              Hồ sơ #{selectedRow}
            </span>
            <h3 className="text-[16px] font-bold text-slate-900">Thông tin chi tiết đối chiếu</h3>
          </div>
        </div>

        <div className="flex items-center gap-6 border-b border-slate-200 pt-2 text-[13.5px]">
          <button
            onClick={() => setDetailTab('identity')}
            className={`pb-2.5 font-semibold transition-all relative ${
              detailTab === 'identity' ? 'text-red-600' : 'text-slate-500 hover:text-slate-900'
            }`}
          >
            Định danh
            {detailTab === 'identity' && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-red-600 rounded-full" />
            )}
          </button>
          <button
            onClick={() => setDetailTab('group')}
            className={`pb-2.5 font-medium transition-all relative ${
              detailTab === 'group' ? 'text-red-600 font-semibold' : 'text-slate-500 hover:text-slate-900'
            }`}
          >
            Nhóm đối tượng
            {detailTab === 'group' && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-red-600 rounded-full" />
            )}
          </button>
          <button
            onClick={() => setDetailTab('benefit')}
            className={`pb-2.5 font-medium transition-all relative ${
              detailTab === 'benefit' ? 'text-red-600 font-semibold' : 'text-slate-500 hover:text-slate-900'
            }`}
          >
            Chế độ
            {detailTab === 'benefit' && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-red-600 rounded-full" />
            )}
          </button>
        </div>

        <div className="py-4">
          {detailTab === 'identity' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-[13.5px]">
              <div className="p-3 bg-slate-50 rounded-md border border-slate-200">
                <span className="text-slate-500 text-[12px] block">
                  {isPersonLookup ? `Họ và tên (khớp #${selectedRow}):` : 'Họ và tên (đã nhập):'}
                </span>
                <span className="font-bold text-slate-900 mt-0.5 block">{selectedCandidate?.subjectName ?? 'Chưa có'}</span>
              </div>
              <div className="p-3 bg-slate-50 rounded-md border border-slate-200">
                <span className="text-slate-500 text-[12px] block">
                  {isPersonLookup ? 'Năm sinh (khớp):' : 'Năm sinh (đã nhập):'}
                </span>
                <span className="font-bold text-slate-900 mt-0.5 block">{selectedCandidate?.subjectYear ?? 'Chưa có'}</span>
              </div>
              <div className="p-3 bg-slate-50 rounded-md border border-slate-200">
                <span className="text-slate-500 text-[12px] block">Mã hồ sơ:</span>
                <span className="font-mono font-bold text-red-600 mt-0.5 block">
                  {formValues?.identifier || currentCaseData?.case_code || 'Chưa có'}
                </span>
              </div>
              <div className="p-3 bg-slate-50 rounded-md border border-slate-200">
                <span className="text-slate-500 text-[12px] block">Đơn vị đang xem (khớp #{selectedRow}):</span>
                <span className="font-bold text-slate-900 mt-0.5 block">{selectedCandidate?.unitName ?? 'Chưa có'}</span>
              </div>
            </div>
          )}

          {detailTab === 'group' && (
            <div className="p-4 bg-[#FDF0BE] border border-amber-200 rounded-md text-[13px] text-amber-900">
              <p className="font-bold">Chi tiết khớp đơn vị #{selectedRow}:</p>
              <p className="mt-1">
                Mã đơn vị <strong>{selectedCandidate?.unitId ?? 'Chưa có'}</strong>, tổ chức{' '}
                <strong>{selectedCandidate?.orgType ?? 'chưa xác định'}</strong>, mức độ phù hợp{' '}
                <strong>{selectedCandidate?.score ?? 'Chưa có'}</strong>. Có nhiều hơn một đơn vị khớp tên nên hệ thống
                không tự động kết luận CA/BQP. Cần thẩm định thủ công để chọn đúng đơn vị công tác hiện tại.
              </p>
            </div>
          )}

          {detailTab === 'benefit' && (
            <div className="p-4 bg-slate-50 border border-slate-200 rounded-md text-[13px] text-slate-900 space-y-2">
              {(currentCaseData?.subject_group_method || currentCaseData?.taxonomy_version) && (
                <p className="text-[11.5px] text-slate-500 pb-1 border-b border-slate-200">
                  {currentCaseData?.subject_group_method &&
                    (SUBJECT_GROUP_METHOD_LABELS[currentCaseData.subject_group_method] || currentCaseData.subject_group_method)}
                  {currentCaseData?.taxonomy_version && (
                    <span className="ml-1 text-slate-400">(bộ tiêu chí {currentCaseData.taxonomy_version})</span>
                  )}
                </p>
              )}
              {Array.isArray(currentCaseData?.eligibility) && currentCaseData.eligibility.length > 0 ? (
                <div className="space-y-2">
                  {currentCaseData.eligibility.map((e, i) => (
                    <div key={i} className="border-b border-slate-200 pb-2 last:border-0 last:pb-0">
                      <div className="flex items-center justify-between">
                        <span className="font-medium">
                          {e.policy_id}{e.policy_version && <span className="font-mono text-[10.5px] text-slate-400 ml-1">v{e.policy_version}</span>}
                        </span>
                        <span className="text-slate-500">{POLICY_STATUS_LABELS[e.status] || 'Chưa xác định'}{e.reason ? `: ${e.reason}` : ''}</span>
                      </div>
                      {e.evidence?.as_of_date && (
                        <p className="text-[11px] text-slate-400 mt-0.5">Tính đến: {e.evidence.as_of_date}</p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <>
                  <p className="font-bold">Tình trạng chế độ chi trả:</p>
                  <p className="mt-1 text-slate-500">
                    Chưa đủ dữ liệu để đánh giá chế độ cho hồ sơ này hoặc chưa xác định được phạm vi tổ chức.
                  </p>
                </>
              )}
            </div>
          )}
        </div>

        <div className="pt-3 border-t border-slate-100 flex flex-col sm:flex-row items-stretch sm:items-center justify-end gap-2.5 sm:gap-3">
          <button
            type="button"
            onClick={() => onViewOriginalDossier && onViewOriginalDossier(currentCaseData?.case_id)}
            disabled={!currentCaseData?.case_id}
            className="px-4 py-2 rounded-md border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-[13px] font-semibold flex items-center justify-center transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span>Xem hồ sơ gốc</span>
          </button>
          <button
            type="button"
            onClick={() => onViewDetailedCompare && onViewDetailedCompare(currentCaseData?.case_id)}
            disabled={!currentCaseData?.case_id}
            className="px-4 py-2 rounded-md bg-red-600 hover:bg-red-700 text-white text-[13px] font-semibold flex items-center justify-center shadow-sm transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span>Đối chiếu chi tiết</span>
          </button>
        </div>
      </div>
    </div>
  );
}

// Sub-Component: No Conclusion View
function NoConclusionView({ formValues, onRetrySearch, onEditInfo }) {
  return (
    <div className="space-y-5">
      {/* Neutral Banner */}
      <div className="rounded-md bg-slate-50 border border-slate-300 p-6 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-full bg-white text-slate-500 flex items-center justify-center border border-slate-300 shadow-sm flex-shrink-0">
            <HelpCircle className="w-7 h-7" />
          </div>
          <div>
            <span className="inline-block px-2 py-0.5 rounded text-[11.5px] font-bold uppercase tracking-wider bg-white border border-slate-300 text-slate-600 mb-1">
              KẾT QUẢ ĐỐI SOÁT
            </span>
            <h2 className="text-[22px] sm:text-[24px] md:text-[26px] font-bold text-slate-900 leading-tight">
              Không có trong dữ liệu quản lý CA/BQP
            </h2>
            <p className="text-[14px] text-slate-600 mt-1 leading-relaxed">
              Không tìm thấy hồ sơ trùng khớp trong dữ liệu quản lý hiện có của Bộ Công an hoặc Bộ Quốc phòng{formValues.identifier ? ` đối với mã định danh "${formValues.identifier}"` : ''}. Kết quả này xác định đối tượng không thuộc phạm vi theo dữ liệu hiện có; không đồng nghĩa với xác nhận pháp lý rằng hồ sơ không tồn tại.
            </p>
          </div>
        </div>
      </div>

      {/* Searched Chips */}
      <div className="bg-white rounded-md border border-slate-200 p-5 shadow-sm">
        <h4 className="text-[14.5px] font-bold text-slate-900 mb-3">Thông tin đã tra cứu</h4>
        <div className="flex flex-wrap gap-2.5">
          <div className="px-3 py-1.5 bg-white border border-slate-200 rounded-md text-[13px] shadow-sm">
            <span className="text-slate-400 mr-1.5">Họ tên:</span>
            <strong className="text-slate-900 font-bold">{formValues.fullName || 'Chưa nhập'}</strong>
          </div>
          <div className="px-3 py-1.5 bg-white border border-slate-200 rounded-md text-[13px] shadow-sm">
            <span className="text-slate-400 mr-1.5">Năm sinh:</span>
            <strong className="text-slate-900 font-bold">{formValues.birthYear || 'Chưa cung cấp'}</strong>
          </div>
          <div className="px-3 py-1.5 bg-white border border-slate-200 rounded-md text-[13px] shadow-sm">
            <span className="text-slate-400 mr-1.5">Đơn vị:</span>
            <strong className="text-slate-900 font-bold">{formValues.department || 'Chưa chọn'}</strong>
          </div>
          <div className="px-3 py-1.5 bg-white border border-slate-200 rounded-md text-[13px] shadow-sm">
            <span className="text-slate-400 mr-1.5">Chức vụ:</span>
            <strong className="text-slate-900 font-bold">{formValues.position || 'Chưa nhập'}</strong>
          </div>
          <div className="px-3 py-1.5 bg-white border border-slate-200 rounded-md text-[13px] shadow-sm">
            <span className="text-slate-400 mr-1.5">Mã định danh:</span>
            <strong className="text-red-600 font-mono font-bold">{formValues.identifier || 'Chưa cung cấp'}</strong>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-md border border-slate-200 p-4 shadow-sm">
        <p className="text-[13px] text-slate-600">
          Có thể tra cứu lại với họ tên đầy đủ, mã số cán bộ hoặc tên đơn vị cấp trên, hoặc tải tài liệu gốc để hệ thống đọc thông tin.
        </p>
        <div className="mt-3 pt-3 border-t border-slate-100 flex flex-col sm:flex-row items-stretch sm:items-center justify-end gap-2.5 sm:gap-3">
          <button
            type="button"
            onClick={onRetrySearch}
            className="px-4 py-2 rounded-md border border-slate-200 hover:bg-slate-50 text-slate-800 font-semibold text-[13.5px] flex items-center justify-center"
          >
            <span>Tra cứu lại</span>
          </button>

          <button
            type="button"
            onClick={onEditInfo}
            className="px-5 py-2 rounded-md bg-red-600 hover:bg-red-700 text-white font-semibold text-[13.5px] flex items-center justify-center shadow-sm"
          >
            <span>Bổ sung thông tin</span>
          </button>
        </div>
      </div>
    </div>
  );
}
