import React, { useState } from 'react';
import { Clock, Search, RotateCcw, History } from '../icons/index.jsx';
import PageHeader from './layout/PageHeader.jsx';

const RESULT_STATUS_STYLES = {
  VERIFIED: { bar: 'bg-emerald-600', text: 'text-emerald-800' },
  NEED_REVIEW: { bar: 'bg-amber-600', text: 'text-amber-800' },
  // A resolved unit outside BCA/BQP is a conclusion with evidence behind it, so it
  // reads differently from a Case that reached none. NOT_FOUND != OTHER.
  OUT_OF_SCOPE: { bar: 'bg-slate-500', text: 'text-slate-700' },
  NO_CONCLUSION: { bar: 'bg-slate-400', text: 'text-slate-600' },
};

const VERIFIED_ORG_LABELS = { BCA: 'BCA', BQP: 'BQP' };

function ResultStatus({ item }) {
  const key = RESULT_STATUS_STYLES[item.statusCategory] ? item.statusCategory : 'NO_CONCLUSION';
  const style = RESULT_STATUS_STYLES[key];
  // Name the ministry from the decision. A two-way "BQP or else BCA" test would
  // print a ministry for any other value that ever reached this branch.
  const orgLabel = VERIFIED_ORG_LABELS[item.orgType];
  const label =
    key === 'VERIFIED'
      ? `${orgLabel ? `${orgLabel} - ` : ''}Đã xác định`
      : key === 'NEED_REVIEW'
      ? 'Cần xác minh thêm'
      : key === 'OUT_OF_SCOPE'
      ? 'Ngoài phạm vi CA/BQP'
      : 'Chưa có kết luận';
  return (
    <span className={`inline-flex items-center gap-2 text-[12.5px] font-semibold ${style.text}`}>
      <span className={`w-[3px] h-3.5 flex-shrink-0 ${style.bar}`} />
      {label}
    </span>
  );
}

function SubjectFacts({ item }) {
  const facts = [
    item.birthYear ? `Năm sinh: ${item.birthYear}` : null,
    item.position ? `Chức vụ: ${item.position}` : null,
  ].filter(Boolean);
  if (facts.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-x-4 text-[12px] text-slate-500 mt-0.5">
      {facts.map((fact) => (
        <span key={fact}>{fact}</span>
      ))}
    </div>
  );
}

export default function HistoryView({
  historyList,
  totals,
  onSelectCase,
  onViewOriginalDossier,
  onViewDetailedCompare,
  onClearHistory,
  onDeleteItem,
  onRefresh,
  onBackToSearch,
}) {
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [refreshing, setRefreshing] = useState(false);

  const handleRefresh = async () => {
    if (!onRefresh) return;
    setRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setRefreshing(false);
    }
  };

  const filteredHistory = historyList.filter((item) => {
    const matchesSearch =
      String(item.fullName ?? '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      String(item.caseCode ?? '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      String(item.department ?? '').toLowerCase().includes(searchTerm.toLowerCase());

    if (statusFilter === 'ALL') return matchesSearch;
    return matchesSearch && item.statusCategory === statusFilter;
  });

  // `totals` is counted by the server over the whole queue. `historyList` is one
  // page of at most 200 rows, so counting it reported a flat 200 once the queue
  // grew past that. Fall back to the loaded rows only when the server did not
  // send totals (the offline / localStorage path), where they are all there is.
  const loadedCount = historyList.length;
  const totalCount = totals?.all ?? loadedCount;
  const verifiedCount =
    totals?.verified ?? historyList.filter((i) => i.statusCategory === 'VERIFIED').length;
  const reviewCount =
    totals?.need_review ?? historyList.filter((i) => i.statusCategory === 'NEED_REVIEW').length;
  const outOfScopeCount =
    totals?.out_of_scope ?? historyList.filter((i) => i.statusCategory === 'OUT_OF_SCOPE').length;
  const noConclusionCount =
    totals?.no_conclusion ?? historyList.filter((i) => i.statusCategory === 'NO_CONCLUSION').length;
  const hasUnloadedRows = totalCount > loadedCount;

  return (
    <div className="max-w-[1480px] w-full mx-auto px-4 sm:px-6 lg:px-8 py-3 h-full flex-1 flex flex-col overflow-hidden min-h-0">
      <PageHeader
        className="mb-2"
        trail={[{ label: 'Trang chủ', onClick: onBackToSearch }]}
        title="Lịch sử tra cứu hồ sơ"
        description="Các lượt tra cứu đã lưu trong hệ thống."
        icon={History}
        actions={
          <>
            {onRefresh && (
              <button
                type="button"
                onClick={handleRefresh}
                disabled={refreshing}
                className="px-3 py-1.5 rounded-md border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium text-xs flex items-center justify-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50"
              >
                <RotateCcw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
                <span>Tải lại</span>
              </button>
            )}
            <button
              type="button"
              onClick={onBackToSearch}
              className="px-3.5 py-1.5 rounded-md bg-red-600 hover:bg-red-700 text-white font-medium text-xs flex items-center justify-center gap-1.5 shadow-xs transition-colors cursor-pointer"
            >
              <Search className="w-3.5 h-3.5" />
              <span>Tra cứu mới</span>
            </button>
          </>
        }
      />

      {/* Summary counts */}
      <div className="flex-shrink-0 grid grid-cols-2 lg:grid-cols-5 bg-white border border-slate-200 rounded-md divide-x divide-slate-200 my-2">
        {[
          { label: 'Tổng lượt tra cứu', value: totalCount },
          { label: 'Đã xác định (BCA/BQP)', value: verifiedCount },
          { label: 'Cần xác minh thêm', value: reviewCount },
          { label: 'Ngoài phạm vi CA/BQP', value: outOfScopeCount },
          { label: 'Chưa có kết luận', value: noConclusionCount },
        ].map((stat) => (
          <div key={stat.label} className="px-3.5 py-2.5">
            <div className="text-[11.5px] text-slate-500">{stat.label}</div>
            <div className="text-[19px] font-bold text-slate-900 mt-0.5 tabular-nums">{stat.value}</div>
          </div>
        ))}
      </div>

      {/* Filter & Search Bar */}
      <div className="flex-shrink-0 bg-white rounded-md border border-slate-200 p-2.5 shadow-xs flex flex-col sm:flex-row items-center justify-between gap-2.5 mb-2">
        <div className="relative w-full sm:w-80">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
            <Search className="w-3.5 h-3.5" />
          </div>
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Tìm theo họ tên, mã hồ sơ hoặc đơn vị"
            className="w-full h-8.5 pl-9 pr-3 rounded-md border border-slate-200 hover:border-red-400 focus:border-red-600 focus:ring-1 focus:ring-red-100 text-[13px] bg-slate-50/50 outline-none transition-all"
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
            { id: 'OUT_OF_SCOPE', label: 'Ngoài phạm vi' },
            { id: 'NO_CONCLUSION', label: 'Chưa có kết luận' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setStatusFilter(tab.id)}
              className={`px-2.5 py-1 rounded-md text-[12px] font-semibold transition-all cursor-pointer ${
                statusFilter === tab.id
                  ? 'bg-red-600 text-white shadow-xs'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* History Records Container */}
      <div className="flex-1 min-h-0 bg-white rounded-md border border-slate-200 shadow-xs flex flex-col overflow-hidden">
        {/* Mobile View: Cards (< sm) */}
        <div className="block sm:hidden flex-1 min-h-0 overflow-y-auto divide-y divide-slate-100">
          {historyList.length === 0 ? (
            <div className="py-12 text-center text-slate-500 px-4">
              <Clock className="w-8 h-8 text-slate-300 mx-auto mb-2" />
              <p className="font-semibold text-slate-700">Chưa có hồ sơ tra cứu nào</p>
              <p className="text-[12.5px] text-slate-400 mt-1 mb-3">
                Thực hiện tra cứu đối tượng hoặc tải tệp tài liệu để hệ thống tự động ghi nhật ký nghiệp vụ.
              </p>
              <button
                type="button"
                onClick={onBackToSearch}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-md bg-red-600 hover:bg-red-700 text-white font-semibold text-[12px] shadow-xs cursor-pointer"
              >
                <Search className="w-3.5 h-3.5" />
                <span>Bắt đầu tra cứu</span>
              </button>
            </div>
          ) : filteredHistory.length === 0 ? (
            <div className="py-12 text-center text-slate-500 px-4">
              <Clock className="w-8 h-8 text-slate-300 mx-auto mb-2" />
              <p className="font-semibold text-slate-700">Không tìm thấy bản ghi phù hợp bộ lọc</p>
              <p className="text-[12.5px] text-slate-400 mt-0.5">Thử điều chỉnh từ khóa tìm kiếm</p>
            </div>
          ) : (
            filteredHistory.map((item) => (
              <div key={item.id} className="p-4 space-y-3 hover:bg-slate-50/70 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-red-600 text-[13px]">{item.caseCode}</span>
                  <span className="text-[11.5px] text-slate-400 font-mono">{item.timestamp}</span>
                </div>
                <div>
                  <div className="font-bold text-slate-900 text-[15px]">{item.fullName}</div>
                  <SubjectFacts item={item} />
                  {item.department && (
                    <div className="text-[12px] text-slate-500 mt-0.5">Đơn vị: {item.department}</div>
                  )}
                </div>
                <div className="flex items-center justify-between pt-1">
                  <ResultStatus item={item} />
                  <span className="text-[11.5px] text-slate-500">Cán bộ {item.officer}</span>
                </div>
                <div className="flex justify-end pt-2 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => onSelectCase(item)}
                    className="py-1.5 px-2 rounded-md bg-red-50 text-red-700 text-[12px] font-semibold flex items-center justify-center"
                  >
                    <span>Xem lại</span>
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
              <tr className="bg-slate-50 text-slate-700 font-bold border-b border-slate-200 text-[11px] uppercase tracking-wider">
                <th className="py-2.5 px-3.5 w-44">Mã hồ sơ</th>
                <th className="py-2.5 px-3.5">Đối tượng xác minh</th>
                <th className="py-2.5 px-3.5">Đơn vị tra cứu</th>
                <th className="py-2.5 px-3.5 w-40">Kết quả đối soát</th>
                <th className="py-2.5 px-3.5 w-32">Thời gian</th>
                <th className="py-2.5 px-3.5 w-28">Cán bộ</th>
                <th className="py-2.5 px-3.5 w-52 text-right">Thao tác nghiệp vụ</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {historyList.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-14 text-center text-slate-500">
                    <Clock className="w-9 h-9 text-slate-300 mx-auto mb-2" />
                    <p className="font-semibold text-[14px] text-slate-700">Chưa có hồ sơ tra cứu nào trong phiên làm việc</p>
                    <p className="text-[12.5px] text-slate-400 mt-1 mb-4">
                      Hãy thực hiện tra cứu đối tượng hoặc tải tệp hồ sơ để hệ thống tự động lưu vết và đồng bộ.
                    </p>
                    <button
                      type="button"
                      onClick={onBackToSearch}
                      className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-red-600 hover:bg-red-700 text-white font-semibold text-[13px] shadow-xs cursor-pointer"
                    >
                      <Search className="w-3.5 h-3.5" />
                      <span>Bắt đầu tra cứu ngay</span>
                    </button>
                  </td>
                </tr>
              ) : filteredHistory.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-500">
                    <Clock className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                    <p className="font-semibold text-slate-700">Không tìm thấy bản ghi phù hợp bộ lọc</p>
                    <p className="text-[12.5px] text-slate-400 mt-0.5">
                      Thử điều chỉnh từ khóa tìm kiếm hoặc lọc theo trạng thái khác.
                    </p>
                  </td>
                </tr>
              ) : (
                filteredHistory.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-3.5 px-4 font-mono font-bold text-red-600 whitespace-nowrap">
                      {item.caseCode}
                    </td>

                    <td className="py-3.5 px-4">
                      <div className="font-bold text-slate-900">{item.fullName}</div>
                      <SubjectFacts item={item} />
                    </td>

                    <td className="py-3.5 px-4 text-slate-700 font-medium">
                      {item.department || 'Chưa xác định'}
                    </td>

                    <td className="py-3.5 px-4">
                      <ResultStatus item={item} />
                    </td>

                    <td className="py-3.5 px-4 text-[12.5px] text-slate-500 font-mono">
                      {item.timestamp}
                    </td>

                    <td className="py-3.5 px-4 text-[12.5px] text-slate-700 font-medium">
                      {item.officer || 'Không rõ'}
                    </td>

                    <td className="py-3.5 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          type="button"
                          onClick={() => onSelectCase(item)}
                          className="px-2.5 py-1.5 rounded-md bg-red-50 text-red-700 hover:bg-red-100 text-[12px] font-semibold transition-colors"
                          title="Xem lại kết quả tra cứu này"
                        >
                          <span>Xem lại</span>
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
              Hiển thị <strong>{filteredHistory.length}</strong> trên <strong>{loadedCount}</strong> hồ sơ đã tải
              {hasUnloadedRows ? (
                <>
                  , tổng số <strong>{totalCount}</strong> hồ sơ trong hệ thống
                </>
              ) : null}
              .
            </div>

          </div>
        )}
      </div>
    </div>
  );
}
