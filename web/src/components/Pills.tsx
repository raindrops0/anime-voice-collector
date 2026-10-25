import { cn } from "cn";
import { UserSearchIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import type { Clip } from "../api";
import type { Roles } from "../api";
import { ignoredTip, likelyLowTip, lowHintTip, skippedTip, statusText } from "../clips";
import { pct } from "../format";
import { tr } from "../language";
import { LOOKS, type PillLook } from "../looks";
import { Avatar } from "./Avatar";
import { Tip } from "./Tip";

export function Tag({
  look,
  tip,
  className,
  children,
}: {
  look: PillLook;
  tip?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Tip text={tip}>
      <Badge
        variant="outline"
        className={cn("border-transparent tabular-nums", LOOKS[look], className)}
      >
        {children}
      </Badge>
    </Tip>
  );
}

/* The machine's guess of who someone is, shown the same way everywhere: a small avatar, "Closest" and the name,
   and the chance when there is one. */
export function Closest({
  roles,
  name,
  p,
  title,
}: {
  roles: Roles;
  name: string;
  p?: number;
  title?: string;
}) {
  return (
    <Tag look="closest" tip={title}>
      <Avatar role={roles[name]} name={name} size="xs" />
      {tr("最像", "Closest:")} {name}
      {p != null ? ` ${pct(p)}` : ""}
    </Tag>
  );
}

/* A target character's line that will be exported without text. The pill stays short; the reason is in its hint. */
export function NoText({ problem }: { problem: string }) {
  return (
    <Tag
      look="noText"
      tip={tr(
        `导出时没有文字，需要文字的导出不会带上这句。原因：${problem}`,
        `Exported without text, so exports that need text leave it out. Why: ${problem}`,
      )}
    >
      {tr("导不出文字", "No text to export")}
    </Tag>
  );
}

/* The machine's "maybe low quality" hint, on lines nobody labeled yet. A line it set aside says so in its status
   pill instead. */
export function LowHint({ clip }: { clip: Clip }) {
  if (clip.low == null || clip.label || clip.status === "likely_low") return null;
  return (
    <Tag look="lowHint" tip={lowHintTip(clip.low)}>
      {tr("可能质量低", "Maybe low quality")} {pct(clip.low)}
    </Tag>
  );
}

export function Pill({ clip }: { clip: Clip }) {
  if (clip.status === "review" && clip.familiar === false) {
    return (
      <Tag
        look="stranger"
        tip={tr(
          "跟已知角色确认过的台词都不太像",
          "Not much like any confirmed line of a known character",
        )}
      >
        <UserSearchIcon aria-hidden="true" />
        {tr("可能是没见过的人", "Maybe someone new")}
      </Tag>
    );
  }
  if (clip.status === "auto" || clip.status === "review") {
    return (
      <Tag
        look={clip.status}
        tip={tr(
          "机器猜这句是前面这个名字的概率",
          "The machine's chance that this line is the name before it",
        )}
      >
        {/* Only the chance: the color says whether the machine is sure, as on the tick boxes of Characters. */}
        {pct(clip.guess[0].p)}
      </Tag>
    );
  }
  const tip =
    clip.status === "skipped"
      ? skippedTip()
      : clip.status === "ignored"
        ? ignoredTip()
        : clip.status === "likely_low"
          ? likelyLowTip()
          : undefined;
  return (
    <Tag look={clip.status} tip={tip}>
      {statusText(clip.status)}
    </Tag>
  );
}
