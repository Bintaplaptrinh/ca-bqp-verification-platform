import React from 'react';
import {
  X,
  FileText,
  Download,
  ShieldCheck,
  Building2,
  Calendar,
  User,
  Hash,
  Award,
  CheckCircle2,
  ExternalLink,
  Lock,
} from 'lucide-react';

export default function OriginalDossierModal({ isOpen, onClose, caseData, onOpenCompare }) {
  if (!isOpen) return null;

  const data = caseData || {
    fullName: 'Nguyễn Văn A',
    birthYear: '1985',
    department: 'Đơn vị X - Cục CSDT (Bộ Công an)',
    position: 'Cán bộ điều tra / Thiếu tá CAND',
    identifier: 'CA-8492',
    caseCode: '#HS-2026-8492',
    orgType: 'BCA',
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-900/60 backdrop-blur-xs overflow-y-auto animate-in fade-in duration-150">
      <div className="relative w-full max-w-4xl bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden my-4 sm:my-6 max-h-[94vh] flex flex-col">
        {/* Modal Header */}
        <div className="px-4 sm:px-6 py-3.5 sm:py-4 bg-slate-900 text-white flex items-center justify-between border-b border-slate-800 flex-shrink-0">
          <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
            <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-blue-600 flex items-center justify-center text-white shadow-sm flex-shrink-0">
              <FileText className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
                <h3 className="text-[15px] sm:text-[17px] font-bold tracking-tight truncate">HỒ SƠ GỐC ĐỐI TƯỢNG</h3>
                <span className="hidden xs:inline px-2 py-0.5 rounded text-[10px] sm:text-[11px] font-bold bg-blue-500/20 text-blue-300 border border-blue-400/30">
                  LƯU TRỮ MẬT
                </span>
              </div>
              <p className="text-[11.5px] sm:text-[12.5px] text-slate-300 mt-0.5 truncate">
                Mã trích lục: <span className="font-mono text-emerald-400 font-bold">{data.caseCode || '#HS-2026-8492'}</span>
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg bg-white/10 hover:bg-white/20 text-slate-300 hover:text-white flex items-center justify-center transition-colors flex-shrink-0 ml-2"
            title="Đóng cửa sổ"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-4 sm:p-6 overflow-y-auto flex-1 space-y-4 sm:space-y-6 text-slate-800">
          {/* Top Banner with Seal */}
          <div className="p-4 rounded-xl bg-amber-50/70 border border-amber-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-[13px]">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center font-bold flex-shrink-0">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div>
                <p className="font-bold text-amber-900">
                  Hồ sơ đã được số hóa và kiểm chứng tính toàn vẹn chữ ký số điện tử
                </p>
                <p className="text-amber-800 text-[12px] mt-0.5">
                  Cơ quan quản trị: Cục Tổ chức Cán bộ — Đối chiếu tự động theo Nghị định 157/2025/NĐ-CP
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-white border border-amber-300 text-amber-900 font-mono text-[11.5px] self-start sm:self-auto">
              <Lock className="w-3.5 h-3.5 text-amber-600" />
              <span>SHA256: e8f9...39b2</span>
            </div>
          </div>

          {/* Dossier Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left Column: Personnel Identity & Portrait */}
            <div className="lg:col-span-5 bg-slate-50 rounded-xl border border-slate-200 p-5 space-y-4">
              <div className="flex items-center gap-4 pb-4 border-b border-slate-200">
                <div className="w-24 h-32 rounded-lg bg-slate-200 border-2 border-slate-300 flex flex-col items-center justify-center relative overflow-hidden flex-shrink-0 shadow-inner">
                  <User className="w-12 h-12 text-slate-400" />
                  <span className="text-[10px] text-slate-500 font-bold mt-1 uppercase">Ảnh 3x4</span>
                  <div className="absolute -bottom-2 -right-2 w-10 h-10 rounded-full bg-red-600/20 border border-red-500/50 flex items-center justify-center rotate-12">
                    <span className="text-[8px] text-red-700 font-bold">DẤU LAI</span>
                  </div>
                </div>
                <div>
                  <span className="text-[11.5px] font-bold text-blue-600 uppercase tracking-wider">
                    {data.orgType === 'BQP' ? 'Lực lượng Quân đội' : 'Lực lượng Công an'}
                  </span>
                  <h4 className="text-[18px] font-bold text-slate-900 leading-tight mt-0.5">
                    {data.fullName || 'Nguyễn Văn A'}
                  </h4>
                  <p className="text-[13px] text-slate-600 mt-1 font-medium">
                    {data.position || 'Cán bộ điều tra'}
                  </p>
                  <p className="font-mono text-[12px] font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-200 mt-2 inline-block">
                    Số hiệu: {data.identifier || 'CA-8492'}
                  </p>
                </div>
              </div>

              {/* Personnel Attributes */}
              <div className="space-y-2.5 text-[13px]">
                <div className="flex justify-between py-1 border-b border-slate-200/60">
                  <span className="text-slate-500">Năm sinh:</span>
                  <span className="font-bold text-slate-900">{data.birthYear || '1985'}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200/60">
                  <span className="text-slate-500">Số CCCD:</span>
                  <span className="font-mono font-semibold text-slate-900">001085******</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200/60">
                  <span className="text-slate-500">Quê quán:</span>
                  <span className="font-medium text-slate-900">Hà Nội</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200/60">
                  <span className="text-slate-500">Ngày tuyển dụng:</span>
                  <span className="font-medium text-slate-900">15/09/2007</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200/60">
                  <span className="text-slate-500">Đơn vị quản lý:</span>
                  <span className="font-bold text-slate-900 text-right max-w-[200px]">{data.department || 'Đơn vị X - Cục CSDT'}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200/60">
                  <span className="text-slate-500">Tình trạng hồ sơ:</span>
                  <span className="px-2 py-0.5 rounded-full text-[11.5px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-200">
                    Đang hoạt động (Biên chế)
                  </span>
                </div>
              </div>
            </div>

            {/* Right Column: Original Scanned Decisions & Proofs */}
            <div className="lg:col-span-7 space-y-4">
              <div className="p-4 bg-white rounded-xl border border-slate-200 shadow-sm space-y-3">
                <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <Award className="w-4 h-4 text-blue-600" />
                    <h4 className="text-[14.5px] font-bold text-slate-900">Văn bản quyết định tiếp nhận &amp; biên chế</h4>
                  </div>
                  <span className="text-[11.5px] font-mono text-slate-500">Số: 882/QĐ-BCA-X01</span>
                </div>

                <div className="p-3.5 bg-slate-50 rounded-lg border border-slate-200 text-[12.5px] leading-relaxed text-slate-700">
                  <p className="font-semibold text-slate-900 mb-1">
                    Trích yếu Quyết định số 882/QĐ-BCA ngày 12/03/2024:
                  </p>
                  <p>
                    "Về việc tiếp nhận, điều động và bố trí công tác đối với đồng chí <strong>{data.fullName}</strong> giữ chức vụ <strong>{data.position}</strong> trực thuộc <strong>{data.department}</strong>. Hưởng lương từ ngân sách nhà nước theo thang bảng lương lực lượng vũ trang nhân dân."
                  </p>
                </div>

                <div className="flex items-center justify-between text-[12px] pt-1 text-slate-500">
                  <span>Người ký: Thượng tướng - Thứ trưởng phụ trách</span>
                  <span className="text-emerald-700 font-semibold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                    Chứng thư số hợp lệ
                  </span>
                </div>
              </div>

              {/* Scanned Document Preview Frame */}
              <div className="p-4 bg-slate-900 rounded-xl text-white space-y-3">
                <div className="flex items-center justify-between text-[13px]">
                  <span className="font-bold flex items-center gap-2">
                    <FileText className="w-4 h-4 text-emerald-400" />
                    Bản quét số hóa văn bản gốc (OCR Scan)
                  </span>
                  <span className="text-[11.5px] text-slate-400 font-mono">Trang 1 / 1 (300 DPI)</span>
                </div>

                <div className="h-40 bg-slate-800 rounded-lg border border-slate-700 p-3 flex flex-col justify-between font-serif text-[12px] text-slate-300 select-text overflow-hidden relative">
                  <div className="text-center font-bold uppercase tracking-wide text-slate-200 text-[11px] pb-1 border-b border-slate-700">
                    CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM<br />Độc lập - Tự do - Hạnh phúc
                  </div>
                  <div className="py-2 space-y-1 text-[11.5px]">
                    <p className="font-bold text-white">BỘ CÔNG AN / BỘ QUỐC PHÒNG</p>
                    <p>Căn cứ Nghị định số 157/2025/NĐ-CP ngày 15 tháng 11 năm 2025 của Chính phủ...</p>
                    <p>Điều 1: Bổ nhiệm đồng chí {data.fullName} thuộc diện hưởng chế độ lực lượng vũ trang...</p>
                  </div>
                  <div className="flex justify-between items-end pt-1 border-t border-slate-700 text-[10.5px]">
                    <span className="italic text-slate-400">Lưu: VT, X01 (02 bản)</span>
                    <div className="text-center text-red-400 font-sans font-bold text-[10px] border border-red-500/60 px-2 py-0.5 rounded bg-red-950/40">
                      [ĐÃ ĐÓNG DẤU ĐỎ &amp; KÝ SỐ CA]
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Modal Footer Actions */}
        <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3 flex-shrink-0">
          <div className="text-[12.5px] text-slate-500">
            Dữ liệu trích xuất phục vụ nghiệp vụ đối soát nội bộ. Không sao chép trái phép.
          </div>

          <div className="flex items-center gap-2.5 w-full sm:w-auto justify-end">
            {onOpenCompare && (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onOpenCompare();
                }}
                className="px-4 py-2 rounded-lg bg-blue-50 text-blue-700 border border-blue-200 hover:bg-blue-100 text-[13px] font-semibold flex items-center gap-1.5 transition-colors"
              >
                <span>Xem đối chiếu chi tiết</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </button>
            )}

            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-[13px] font-semibold transition-colors shadow-xs"
            >
              Đóng
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
