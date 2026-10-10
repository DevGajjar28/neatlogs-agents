import { cn } from "@/lib/utils";

type MonoProps = React.HTMLAttributes<HTMLSpanElement> & {
  as?: "span" | "code" | "div";
};

export function Mono({ as: Comp = "span", className, ...props }: MonoProps) {
  return (
    <Comp
      className={cn(
        "font-mono text-[12px] leading-4 tracking-tight text-[var(--text)] tabular-nums",
        className,
      )}
      {...props}
    />
  );
}
