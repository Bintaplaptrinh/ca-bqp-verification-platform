import React, { useEffect, useId, useRef } from 'react';

function messageText(value) {
  if (value == null) return '';
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  if (Array.isArray(value)) return value.map((item) => messageText(item?.msg || item?.message || item)).filter(Boolean).join('; ');
  if (value instanceof Error) return value.message;
  if (typeof value === 'object') {
    if (value.message) return messageText(value.message);
    if (value.detail) return messageText(value.detail);
  }
  return 'Đã xảy ra lỗi. Vui lòng thử lại.';
}

/**
 * A single, accessible notification pattern for functional notices and errors.
 * The optional primary action makes the same dialog suitable for confirmations.
 */
export default function NotificationModal({
  open = true,
  title = 'Thông báo',
  message = /** @type {string | null | undefined} */ (null),
  children = /** @type {React.ReactNode} */ (null),
  primaryLabel = /** @type {string | null | undefined} */ (null),
  onPrimary = /** @type {(() => void) | undefined} */ (undefined),
  primaryDisabled = false,
  closeLabel = 'Đóng',
  onClose,
  tone = 'error',
  closeOnBackdrop = true,
}) {
  const dialogRef = useRef(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  if (!open) return null;

  const primaryTone = tone === 'success'
    ? 'btn-success'
    : 'btn-error bg-brand-red! border-brand-red! text-white! hover:bg-brand-darkred!';
  const displayedMessage = messageText(message);

  return (
    <dialog
      ref={dialogRef}
      className="modal modal-open"
      aria-labelledby={titleId}
      aria-describedby={displayedMessage ? descriptionId : undefined}
      onCancel={(event) => {
        event.preventDefault();
        onClose?.();
      }}
    >
      <div className="modal-box w-[min(92vw,420px)] select-text! rounded-box bg-base-100 p-0 text-base-content shadow-2xl">
        <div className="px-5 pt-5 text-center">
          <h2 id={titleId} className="text-lg font-bold">{title}</h2>
          {displayedMessage && (
            <p id={descriptionId} className="mt-3 whitespace-pre-line text-sm leading-relaxed text-base-content/70">
              {displayedMessage}
            </p>
          )}
          {children && <div className="mt-3 text-left text-sm text-base-content/70">{children}</div>}
        </div>

        <div className="modal-action mt-5 grid grid-cols-1 gap-2 px-5 pb-5">
          {primaryLabel && (
            <button
              type="button"
              className={`btn btn-block select-text! ${primaryTone}`}
              disabled={primaryDisabled}
              onClick={onPrimary}
            >
              {primaryLabel}
            </button>
          )}
          <button type="button" className="btn btn-block select-text! bg-base-200" onClick={onClose}>
            {closeLabel}
          </button>
        </div>
      </div>

      <form method="dialog" className="modal-backdrop">
        <button
          type="button"
          aria-label="Bỏ qua lớp phủ"
          onClick={() => closeOnBackdrop && onClose?.()}
        >
          Đóng
        </button>
      </form>
    </dialog>
  );
}
