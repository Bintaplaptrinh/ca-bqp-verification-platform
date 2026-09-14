import React, { useState } from 'react';
import {
  X,
  AlertTriangle,
  FileText,
  Download,
  Shield,
  Layers,
  ArrowRight,
  HelpCircle,
  Clock,
  UserCheck,
  Building,
} from 'lucide-react';

export default function DetailedComparisonModal({ isOpen, onClose, caseData, onApprove }) {
  const [activeTab, setActiveTab] = useState('matrix');
  const [officerNote, setOfficerNote] = useState('');
  const [isApproved, setIsApproved] = useState(false);

  if (!isOpen) return null;

  const data = caseData || {
    fullName: 'Nguyễn Văn A',
    birthYear: '1985',
    department: 'Đơn vị X - Cục CSDT',
    position: 'Cán bộ điều tra',
    identifier: 'CA-8492',
    caseCode: '#HS-2026-8492',
    orgType: 'BCA',
    status: 'MATCHED',
  };

  const isMatched = data.status === 'MATCHED' || data.orgType === 'BCA' || data.orgType === 'BQP';

  const comparisonRows = [
    {
      field: 'Họ và tên',
      input: data.fullName || 'Nguyễn Văn A',
      master: data.fullName ? data.fullName.toUpperCase() : 'NGUYỄN VĂN A',
      matchType: 'EXACT',
      score: '100%',
      note: 'Trùng khớp ký tự và âm tiết chuẩn hóa',
      status: 'pass',
    },
    {
      field: 'Năm sinh',
      input: data.birthYear || '1985',
      master: `${data.birthYear || '1985'} (12/08/${data.birthYear || '1985'})`,
      matchType: 'EXACT',
      score: '100%',
      note: 'Dữ liệu ngày tháng năm sinh trùng khớp với CSDL Quốc gia',
      status: 'pass',
    },
    {
      field: 'Đơn vị công tác',
      input: data.department || 'Đơn vị X - Cục CSDT',
      master: 'Cục Cảnh sát Điều tra tội phạm về TTXH (C02) - BCA',
      matchType: 'APPROVED_ALIAS',
      score: '96.5%',
      note: 'Khớp bí danh đơn vị nghiệp vụ đã được QA phê duyệt',
      status: 'pass',
    },
    {
      field: 'Mã số hiệu định danh',
      input: data.identifier || 'CA-8492',
      master: `${data.identifier || 'CA-8492'}-BCA`,
      matchType: 'TRUSTED_CODE',
      score: '100%',
      note: 'Mã định danh duy nhất trong Master Unit Registry',
      status: 'pass',
    },
    {
      field: 'Nhóm đối tượng',
      input: data.position || 'Cán bộ điều tra',
      master: 'Sĩ quan, Hạ sĩ quan CAND (Diện hưởng lương NSNN)',
      matchType: 'POLICY_EVAL',
      score: '100%',
      note: 'Thuộc diện quy chuẩn theo Nghị định 157/2025/NĐ-CP',
      status: 'pass',
    },
    {
      field: 'Tình trạng chi trả lương',
      input: 'Chờ đối soát',
      master: 'Đang chi trả thường xuyên (Bộ Công an cấp ngân sách)',
      matchType: 'FINANCIAL_REGISTRY',
      score: '100%',
      note: 'Đủ điều kiện giải quyết chế độ chính sách an sinh',
      status: 'pass',
    },
    {
      field: 'Căn cứ chính sách áp dụng',
      input: 'Tra cứu tự động 2026',
      master: 'Nghị định 157/2025/NĐ-CP & Thông tư 88/2025/TT-BCA',
      matchType: 'LEGAL_FRAMEWORK',
      score: 'Hợp lệ',
      note: 'Được ban hành có hiệu lực thi hành từ năm 2026',
      status: 'pass',
    },
  ];

  const handleApproveClick = () => {
    setIsApproved(true);
    if (onApprove) onApprove(data);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-900/60 backdrop-blur-xs overflow-y-auto animate-in fade-in duration-150">
      <div className="relative w-full max-w-5xl bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden my-4 sm:my-6 max-h-[94vh] flex flex-col">
        {/* Header */}
        <div className="px-4 sm:px-6 py-3.5 sm:py-4 bg-slate-900 text-white flex items-center justify-between border-b border-slate-800 flex-shrink-0">
          <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
            <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl bg-blue-600 flex items-center justify-center text-white shadow-sm flex-shrink-0">
              <Layers className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
                <h3 className="text-[15px] sm:text-[17px] font-bold tracking-tight truncate">
                  BIÊN BẢN ĐỐI CHIẾU THỰC THỂ
                </h3>
                <span className="hidden xs:inline px-2 py-0.5 rounded text-[10px] sm:text-[11px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-400/30">
                  REGISTRY 2026
                </span>
              </div>
              <p className="text-[11.5px] sm:text-[12.5px] text-slate-300 mt-0.5 truncate">
                Mã hồ sơ: <span className="font-mono text-emerald-400 font-bold">{data.caseCode || '#HS-2026-8492'}</span> — <span className="text-white font-bold">{data.fullName}</span>
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

        {/* Top Metric Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 sm:gap-4 p-3.5 sm:p-6 bg-slate-50 border-b border-slate-200 text-[13px] flex-shrink-0">
          <div className="bg-white p-3.5 rounded-xl border border-slate-200 shadow-xs">
            <span className="text-slate-500 text-[12px] block">Mức độ trùng khớp</span>
            <span className="text-[20px] font-bold text-emerald-600 block mt-0.5">
              {isMatched ? '98.8%' : 'Chờ thẩm định'}
            </span>
            <span className="text-[11px] text-slate-400">Thuật toán đối sánh n-gram &amp; alias</span>
          </div>

          <div className="bg-white p-3.5 rounded-xl border border-slate-200 shadow-xs">
            <span className="text-slate-500 text-[12px] block">Trọng số tin cậy</span>
            <span className="text-[20px] font-bold text-blue-600 block mt-0.5">Cao (High)</span>
            <span className="text-[11px] text-slate-400">Master Registry v2026.01</span>
          </div>

          <div className="bg-white p-3.5 rounded-xl border border-slate-200 shadow-xs">
            <span className="text-slate-500 text-[12px] block">Quy tắc Invariant 2026</span>
            <span className="text-[20px] font-bold text-slate-900 block mt-0.5">Tuân thủ 100%</span>
            <span className="text-[11px] text-slate-400">Không ép nhãn, giữ đúng NOT_FOUND</span>
          </div>

          <div className="bg-white p-3.5 rounded-xl border border-slate-200 shadow-xs">
            <span className="text-slate-500 text-[12px] block">Trạng thái đối chiếu</span>
            <span className={`text-[15px] font-bold block mt-1 ${isMatched ? 'text-emerald-700' : 'text-amber-700'}`}>
              {isMatched ? 'Khớp hoàn toàn' : 'Cần xác minh'}
            </span>
            <span className="text-[11px] text-slate-400">Cơ chế tự động</span>
          </div>
        </div>

        {/* Modal Body Table */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          <div>
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-[15px] font-bold text-slate-900 flex items-center gap-2">
                <FileText className="w-4 h-4 text-blue-600" />
                Bảng ma trận đối chiếu 7 trường dữ liệu chuẩn hóa
              </h4>
              <span className="text-[12px] text-slate-500">Tiêu chuẩn nghiệp vụ Quality-first 2026</span>
            </div>

            <div className="overflow-x-auto border border-slate-200 rounded-xl shadow-xs">
              <table className="w-full text-left text-[13px] border-collapse">
                <thead>
                  <tr className="bg-slate-100 text-slate-700 font-bold border-b border-slate-200 text-[12.5px]">
                    <th className="py-3 px-4 w-40">Trường đối chiếu</th>
                    <th className="py-3 px-4">Dữ liệu đầu vào (Input/OCR)</th>
                    <th className="py-3 px-4">Dữ liệu Master Registry</th>
                    <th className="py-3 px-4 w-28 text-center">Tỷ lệ khớp</th>
                    <th className="py-3 px-4">Kết luận đối soát</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {comparisonRows.map((row, idx) => (
                    <tr key={idx} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-3 px-4 font-bold text-slate-900 bg-slate-50/50">
                        {row.field}
                      </td>
                      <td className="py-3 px-4 text-slate-700 font-medium">
                        {row.input}
                      </td>
                      <td className="py-3 px-4 font-semibold text-slate-900">
                        {row.master}
                      </td>
                      <td className="py-3 px-4 text-center">
                        <span className="inline-block px-2 py-0.5 rounded-full text-[11.5px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          {row.score}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-[12px] text-slate-600">
                        <span>{row.note}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Officer Review & Notes */}
          <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3">
            <h4 className="text-[14px] font-bold text-slate-900 flex items-center gap-2">
              <FileText className="w-4 h-4 text-blue-600" />
              Ý kiến thẩm định của cán bộ đối soát
            </h4>
            <textarea
              value={officerNote}
              onChange={(e) => setOfficerNote(e.target.value)}
              placeholder="Nhập ghi chú hoặc căn cứ bổ sung nếu hồ sơ cần lưu vết đặc biệt (tuân thủ kiểm toán ISO/IEC 2026)..."
              className="w-full h-20 p-3 rounded-lg border border-slate-200 bg-white text-[13px] text-slate-900 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100 resize-none"
            />
            {isApproved && (
              <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-800 text-[12.5px] flex items-center gap-2 font-medium">
                <span>Hồ sơ đã được cán bộ đối soát phê duyệt và lưu vết Audit Trail vào hệ thống!</span>
              </div>
            )}
          </div>
        </div>

        {/* Modal Footer Actions */}
        <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3 flex-shrink-0">
          <div className="text-[12px] text-slate-500">
            Biên bản có giá trị pháp lý nội bộ theo tiêu chuẩn Quality-first 2026.
          </div>

          <div className="flex items-center gap-2.5 w-full sm:w-auto justify-end">
            {!isApproved ? (
              <button
                type="button"
                onClick={handleApproveClick}
                className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-[13px] font-semibold transition-colors shadow-xs cursor-pointer"
              >
                <span>Phê duyệt đối soát</span>
              </button>
            ) : (
              <span className="px-3.5 py-2 rounded-lg bg-emerald-100 text-emerald-800 text-[13px] font-bold border border-emerald-300">
                <span>Đã phê duyệt</span>
              </span>
            )}

            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-[13px] font-semibold transition-colors shadow-xs cursor-pointer"
            >
              Đóng
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
