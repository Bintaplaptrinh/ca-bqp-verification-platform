import React, { useState } from 'react';
import {
  Clock,
  Search,
  Filter,
  Eye,
  Layers,
  FileText,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  Download,
  RotateCcw,
  ArrowRight,
  ShieldCheck,
  Building2,
  User,
} from 'lucide-react';

export default function HistoryView({
  historyList,
  onSelectCase,
  onViewOriginalDossier,
  onViewDetailedCompare,
  onClearHistory,
  onBackToSearch,
}) {
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');

  const filteredHistory = historyList.filter((item) => {
    const matchesSearch =
      item.fullName.toLowerCase().includes(searchTerm.toLowerCase()) ||
      item.caseCode.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (item.department && item.department.toLowerCase().includes(searchTerm.toLowerCase()));

    if (statusFilter === 'ALL') return matchesSearch;
    return matchesSearch && item.statusCategory === statusFilter;
  });

  const totalCount = historyList.length;
  const verifiedCount = historyList.filter((i) => i.statusCategory === 'VERIFIED').length;
  const reviewCount = historyList.filter((i) => i.statusCategory === 'NEED_REVIEW').length;
  const noConclusionCount = historyList.filter((i) => i.statusCategory === 'NO_CONCLUSION').length;

  return (
    <div className="max-w-[1536px] w-full mx-auto px-3.5 sm:px-6 md:px-8 py-2.5 sm:py-3 h-full flex-1 flex flex-col overflow-hidden min-h-0">
      {/* Top Banner & Action */}
      <div className="flex-shrink-0 flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-slate-200">
        <div>
          <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-blue-50 border border-blue-200 text-blue-600 text-[10.5px] font-bold tracking-wider uppercase mb-1">
            <Clock className="w-3 h-3" />
            NHẬT KÝ TRA CỨU &amp; KIỂM TOÁN LƯU VẾT
          </div>
          <h1 className="text-[19px] sm:text-[22px] md:text-[24px] font-bold text-slate-900 leading-tight">
            Lịch sử tra cứu hồ sơ CA/BQP
          </h1>
          <p className="text-[12px] sm:text-[12.5px] text-slate-500 mt-0.5">
            Theo dõi, tái hiện và kiểm tra các phiên đối soát đã được lưu trữ trong hệ thống theo tiêu chuẩn Quality-first 2026.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onBackToSearch}
            className="w-full sm:w-auto px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold text-[13px] flex items-center justify-center gap-1.5 shadow-xs transition-colors cursor-pointer"
          >
            <Search className="w-3.5 h-3.5" />
            <span>Tra cứu hồ sơ mới</span>
          </button>
        </div>
      </div>

      {/* Summary KPI Cards */}
      <div className="flex-shrink-0 grid grid-cols-2 lg:grid-cols-4 gap-2.5 my-2">
        <div className="bg-white rounded-xl border border-slate-200 p-2.5 sm:p-3 shadow-xs">
          <span className="text-slate-500 text-[11.5px] block">Tổng lượt tra cứu</span>
          <div className="text-[20px] sm:text-[22px] font-bold text-slate-900 mt-0.5">{totalCount}</div>
          <span className="text-[10.5px] text-slate-400">Phiên làm việc nội bộ</span>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-2.5 sm:p-3 shadow-xs">
          <span className="text-emerald-700 font-medium text-[11.5px] block">Đã xác định (BCA/BQP)</span>
          <div className="text-[20px] sm:text-[22px] font-bold text-emerald-600 mt-0.5">{verifiedCount}</div>
          <span className="text-[10.5px] text-emerald-600/80">Khớp 100% Master Registry</span>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-2.5 sm:p-3 shadow-xs">
          <span className="text-amber-700 font-medium text-[11.5px] block">Cần xác minh thêm</span>
          <div className="text-[20px] sm:text-[22px] font-bold text-amber-600 mt-0.5">{reviewCount}</div>
          <span className="text-[10.5px] text-amber-600/80">Chuyển luồng thẩm định</span>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 p-2.5 sm:p-3 shadow-xs">
          <span className="text-slate-600 font-medium text-[11.5px] block">Chưa có kết luận</span>
          <div className="text-[20px] sm:text-[22px] font-bold text-slate-700 mt-0.5">{noConclusionCount}</div>
          <span className="text-[10.5px] text-slate-500">Giữ nguyên NOT_FOUND</span>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="flex-shrink-0 bg-white rounded-xl border border-slate-200 p-2.5 shadow-xs flex flex-col sm:flex-row items-center justify-between gap-2.5 mb-2">
        <div className="relative w-full sm:w-80">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
            <Search className="w-3.5 h-3.5" />
          </div>
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Tìm theo họ tên, mã hồ sơ hoặc đơn vị..."
            className="w-full h-8.5 pl-9 pr-3 rounded-lg border border-slate-200 hover:border-blue-400 focus:border-blue-600 focus:ring-1 focus:ring-blue-100 text-[13px] bg-slate-50/50 outline-none transition-all"
          />
        </div>

        <div className="flex flex-wrap items-center gap-1.5 w-full sm:w-auto">
          <span className="text-[12px] font-semibold text-slate-500 mr-1">
            Lọc:
          </span>
          {[
            { id: 'ALL', label: 'Tất cả' },
            { id: 'VERIFIED', label: 'Đã xác định' },
            { id: 'NEED_REVIEW', label: 'Cần xác minh' },
            { id: 'NO_CONCLUSION', label: 'Chưa có kết luận' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setStatusFilter(tab.id)}
              className={`px-2.5 py-1 rounded-lg text-[12px] font-semibold transition-all cursor-pointer ${
                statusFilter === tab.id
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* History Records Container */}
      <div className="flex-1 min-h-0 bg-white rounded-xl border border-slate-200 shadow-xs flex flex-col overflow-hidden">
        {/* Mobile View: Cards (< sm) */}
        <div className="block sm:hidden flex-1 min-h-0 overflow-y-auto divide-y divide-slate-100">
          {filteredHistory.length === 0 ? (
            <div className="py-12 text-center text-slate-500 px-4">
              <Clock className="w-8 h-8 text-slate-300 mx-auto mb-2" />
              <p className="font-semibold text-slate-700">Chưa tìm thấy bản ghi tra cứu</p>
              <p className="text-[12.5px] text-slate-400 mt-0.5">Thử điều chỉnh từ khóa tìm kiếm</p>
            </div>
          ) : (
            filteredHistory.map((item) => (
              <div key={item.id} className="p-4 space-y-3 hover:bg-slate-50/70 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-blue-600 text-[13px]">{item.caseCode}</span>
                  <span className="text-[11.5px] text-slate-400 font-mono">{item.timestamp}</span>
                </div>
                <div>
                  <div className="font-bold text-slate-900 text-[15px]">{item.fullName}</div>
                  <div className="text-[12.5px] text-slate-600 mt-0.5">
                    Năm sinh: {item.birthYear || '—'} {item.position ? `• ${item.position}` : ''}
                  </div>
                  {item.department && (
                    <div className="text-[12px] text-slate-500 mt-0.5">Đơn vị: {item.department}</div>
                  )}
                </div>
                <div className="flex items-center justify-between pt-1">
                  <div>
                    {item.statusCategory === 'VERIFIED' ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-200">
                        <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                        <span>{item.orgType === 'BQP' ? 'BQP - Đã xác định' : 'BCA - Đã xác định'}</span>
                      </span>
                    ) : item.statusCategory === 'NEED_REVIEW' ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
                        <AlertTriangle className="w-3 h-3 text-amber-600" />
                        <span>Cần xác minh</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-600 border border-slate-200">
                        <HelpCircle className="w-3 h-3 text-slate-400" />
                        <span>Chưa có kết luận</span>
                      </span>
                    )}
                  </div>
                  <span className="text-[11.5px] text-slate-500">Cán bộ {item.officer || '#9928'}</span>
                </div>
                <div className="grid grid-cols-3 gap-2 pt-2 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => onSelectCase(item)}
                    className="py-1.5 px-2 rounded-lg bg-blue-50 text-blue-700 text-[12px] font-semibold flex items-center justify-center"
                  >
                    <span>Xem lại</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => onViewOriginalDossier(item)}
                    className="py-1.5 px-2 rounded-lg border border-slate-200 text-slate-700 text-[12px] font-semibold flex items-center justify-center"
                  >
                    <span>Hồ sơ</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => onViewDetailedCompare(item)}
                    className="py-1.5 px-2 rounded-lg border border-slate-200 text-slate-700 text-[12px] font-semibold flex items-center justify-center"
                  >
                    <span>Đối chiếu</span>
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Desktop View: Table (>= sm) */}
        <div className="hidden sm:block flex-1 min-h-0 overflow-y-auto overflow-x-auto">
          <table className="w-full text-left text-[13px] border-collapse">
            <thead className="sticky top-0 bg-slate-50 z-10 shadow-xs">
              <tr className="bg-slate-50 text-slate-700 font-bold border-b border-slate-200 text-[12px]">
                <th className="py-2.5 px-3.5 w-32">Mã hồ sơ</th>
                <th className="py-2.5 px-3.5">Đối tượng xác minh</th>
                <th className="py-2.5 px-3.5">Đơn vị tra cứu</th>
                <th className="py-2.5 px-3.5 w-40">Kết quả đối soát</th>
                <th className="py-2.5 px-3.5 w-32">Thời gian</th>
                <th className="py-2.5 px-3.5 w-28">Cán bộ</th>
                <th className="py-2.5 px-3.5 w-52 text-right">Thao tác nghiệp vụ</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredHistory.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-500">
                    <Clock className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                    <p className="font-semibold text-slate-700">Chưa tìm thấy bản ghi tra cứu phù hợp</p>
                    <p className="text-[12.5px] text-slate-400 mt-0.5">
                      Thử điều chỉnh từ khóa tìm kiếm hoặc lọc theo trạng thái khác.
                    </p>
                  </td>
                </tr>
              ) : (
                filteredHistory.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-3.5 px-4 font-mono font-bold text-blue-600">
                      {item.caseCode}
                    </td>

                    <td className="py-3.5 px-4">
                      <div className="font-bold text-slate-900">{item.fullName}</div>
                      <div className="text-[12px] text-slate-500">
                        Năm sinh: {item.birthYear || '—'} {item.position ? `• ${item.position}` : ''}
                      </div>
                    </td>

                    <td className="py-3.5 px-4 text-slate-700 font-medium">
                      {item.department || '—'}
                    </td>

                    <td className="py-3.5 px-4">
                      {item.statusCategory === 'VERIFIED' ? (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11.5px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-200">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                          <span>{item.orgType === 'BQP' ? 'BQP - Đã xác định' : 'BCA - Đã xác định'}</span>
                        </span>
                      ) : item.statusCategory === 'NEED_REVIEW' ? (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11.5px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
                          <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                          <span>Cần xác minh thêm</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11.5px] font-bold bg-slate-100 text-slate-600 border border-slate-200">
                          <HelpCircle className="w-3.5 h-3.5 text-slate-400" />
                          <span>Chưa có kết luận</span>
                        </span>
                      )}
                    </td>

                    <td className="py-3.5 px-4 text-[12.5px] text-slate-500 font-mono">
                      {item.timestamp}
                    </td>

                    <td className="py-3.5 px-4 text-[12.5px] text-slate-700 font-medium">
                      {item.officer || '#9928'}
                    </td>

                    <td className="py-3.5 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          type="button"
                          onClick={() => onSelectCase(item)}
                          className="px-2.5 py-1.5 rounded-md bg-blue-50 text-blue-700 hover:bg-blue-100 text-[12px] font-semibold transition-colors"
                          title="Xem lại kết quả tra cứu này"
                        >
                          <span>Xem lại</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => onViewOriginalDossier(item)}
                          className="px-2.5 py-1.5 rounded-md border border-slate-200 hover:bg-slate-100 text-slate-700 text-[12px] font-semibold transition-colors"
                          title="Xem hồ sơ gốc trích lục"
                        >
                          <span>Hồ sơ gốc</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => onViewDetailedCompare(item)}
                          className="px-2.5 py-1.5 rounded-md border border-slate-200 hover:bg-slate-100 text-slate-700 text-[12px] font-semibold transition-colors"
                          title="Đối chiếu chi tiết thực thể"
                        >
                          <span>Đối chiếu</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Footer info & Clear button */}
        {filteredHistory.length > 0 && (
          <div className="p-4 bg-slate-50 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3 text-[12.5px] text-slate-500">
            <div>
              Hiển thị <strong>{filteredHistory.length}</strong> trên tổng số <strong>{historyList.length}</strong> hồ sơ đã tra cứu.
            </div>

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={onClearHistory}
                className="text-red-600 hover:text-red-700 font-semibold flex items-center gap-1 transition-colors text-[12.5px]"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Xóa toàn bộ lịch sử</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
