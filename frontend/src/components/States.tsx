import { AlertTriangle, LoaderCircle, RefreshCw } from "lucide-react";

export function LoadingState({ label = "正在读取本地分析仓库" }: { label?: string }) {
  return (
    <div className="state-panel" aria-live="polite">
      <LoaderCircle className="spin" size={22} />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({
  error,
  retry,
}: {
  error: Error;
  retry?: () => void;
}) {
  return (
    <div className="state-panel state-error" role="alert">
      <AlertTriangle size={22} />
      <div>
        <strong>数据加载失败</strong>
        <p>{error.message}</p>
      </div>
      {retry && (
        <button className="button-secondary" type="button" onClick={retry}>
          <RefreshCw size={15} />
          重试
        </button>
      )}
    </div>
  );
}

