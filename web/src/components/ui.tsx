"use client";

import { ApiError } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";
import type { ButtonHTMLAttributes, ReactNode } from "react";

export function cx(...c: (string | false | null | undefined)[]): string {
  return c.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "quiet";

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" }) {
  return (
    <button
      {...rest}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "min-h-9 px-3 text-sm" : "min-h-11 px-4 text-[0.95rem]",
        variant === "primary" && "bg-accent text-accent-ink hover:opacity-90",
        variant === "secondary" && "border border-line-strong bg-surface text-ink hover:bg-surface-2",
        variant === "ghost" && "text-accent hover:bg-accent-soft",
        variant === "quiet" && "text-ink-2 underline underline-offset-4 hover:text-ink",
        className,
      )}
    />
  );
}

export function Card({ children, className, as: As = "section", ...rest }: {
  children: ReactNode;
  className?: string;
  as?: "section" | "div" | "article" | "aside";
} & React.HTMLAttributes<HTMLElement>) {
  return (
    <As {...rest} className={cx("rounded-2xl border border-line bg-surface p-4 sm:p-6", className)}>
      {children}
    </As>
  );
}

export function H1({ children, className }: { children: ReactNode; className?: string }) {
  return <h1 className={cx("text-2xl font-semibold tracking-tight text-ink sm:text-3xl", className)}>{children}</h1>;
}

export function H2({ children, className, id }: { children: ReactNode; className?: string; id?: string }) {
  return (
    <h2 id={id} className={cx("text-lg font-semibold text-ink sm:text-xl", className)}>
      {children}
    </h2>
  );
}

export function H3({ children, className }: { children: ReactNode; className?: string }) {
  return <h3 className={cx("text-base font-semibold text-ink", className)}>{children}</h3>;
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brass">{children}</p>;
}

export type ProvKind = "recorded" | "calculated" | "source" | "template";

/** Provenance label shown next to every value or sentence. */
export function Prov({ kind, className }: { kind: ProvKind; className?: string }) {
  const { t } = usePrefs();
  return (
    <span
      className={cx(
        `tag-${kind}`,
        "inline-flex shrink-0 items-center rounded px-1.5 py-0.5 text-[0.68rem] font-semibold uppercase tracking-wide leading-none",
        className,
      )}
      title={t(`prov.${kind}.d`)}
    >
      {t(`prov.${kind}`)}
    </span>
  );
}

export function Chip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-full border border-line-strong px-2.5 py-0.5 text-xs font-medium text-ink-2",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Notice({ children, className, role }: { children: ReactNode; className?: string; role?: string }) {
  return (
    <div role={role} className={cx("rounded-xl border border-notice-line bg-notice px-4 py-3 text-sm text-ink", className)}>
      {children}
    </div>
  );
}

export function Loading() {
  const { t } = usePrefs();
  return (
    <p className="py-8 text-center text-sm text-muted" role="status" aria-live="polite">
      {t("common.loading")}
    </p>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = usePrefs();
  const msg =
    error instanceof ApiError
      ? error.status === 0
        ? t("common.network")
        : error.message
      : error instanceof Error
        ? error.message
        : String(error);
  return (
    <div role="alert" className="rounded-xl border border-line-strong bg-surface-2 px-4 py-3 text-sm">
      <p className="font-semibold">{t("common.error")}</p>
      <p className="mt-1 text-ink-2">{msg}</p>
      {onRetry && (
        <Button size="sm" className="mt-3" onClick={onRetry}>
          {t("common.retry")}
        </Button>
      )}
    </div>
  );
}

export function Field({ label, htmlFor, children, hint }: { label: string; htmlFor: string; children: ReactNode; hint?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium text-ink">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  );
}

export const inputCls =
  "min-h-11 w-full rounded-lg border border-line-strong bg-surface px-3 text-base text-ink placeholder:text-muted";

/** Western-digit numeric text that keeps its direction inside Arabic text. */
export function Num({ children }: { children: ReactNode }) {
  return (
    <bdi dir="ltr" className="tabular-nums">
      {children}
    </bdi>
  );
}
