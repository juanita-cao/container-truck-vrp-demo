import { Alert, Button } from "@arco-design/web-react";
import { useTranslation } from "react-i18next";
import { ApiError } from "../api/client";

/** 把后端返回的错误代码渲染成当前语言的文案；未知代码退回通用提示。 */
export function ErrorNote({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t, i18n } = useTranslation();
  const code = error instanceof ApiError ? error.code : "UNKNOWN";
  const key = `errors.${code}`;
  const text = i18n.exists(key) ? t(key) : t("errors.UNKNOWN");
  return <Alert type="warning" content={text} action={onRetry ? <Button size="mini" onClick={onRetry}>{t("common.retry")}</Button> : undefined} />;
}
