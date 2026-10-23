import type { ValidationIssue } from "./validate";
export function ValidationPanel({
  issues,
  onFocus,
}: {
  issues: ValidationIssue[];
  onFocus: (id: string) => void;
}) {
  return (
    <section
      aria-label="Kết quả kiểm tra"
      className="max-h-36 overflow-y-auto border-t border-stone-200 bg-white p-3 text-xs"
      aria-live="polite"
    >
      {issues.length ? (
        <>
          <h2 className="mb-1 font-semibold text-red-700">
            {issues.length} lỗi cần sửa trước khi xuất bản
          </h2>
          <ul className="space-y-1">
            {issues.map((issue, i) => (
              <li key={`${i}-${issue.message}`}>
                <button
                  type="button"
                  disabled={!issue.nodeId}
                  onClick={() => onFocus(issue.nodeId!)}
                  className="text-left text-red-700 enabled:hover:underline"
                >
                  {issue.message}
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="text-emerald-700">✓ Workflow hợp lệ</p>
      )}
    </section>
  );
}
