import React from "react";

export default function KpiCard({ label, value, sub, tone = "default", icon, testId }) {
    const toneClass =
        tone === "danger"
            ? "text-red-500"
            : tone === "warn"
              ? "text-yellow-300"
              : "text-white";
    return (
        <div
            data-testid={testId}
            className="relative flex flex-col justify-between border border-[#27272A] bg-[#0C0C0E] p-5 md:p-6 transition-colors hover:bg-[#121214]"
        >
            <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-[0.25em] text-zinc-500 font-medium">
                    {label}
                </span>
                {icon ? <span className="text-zinc-500">{icon}</span> : null}
            </div>
            <div className="mt-8">
                <div
                    className={`font-display font-bold leading-none text-4xl md:text-5xl ${toneClass}`}
                >
                    {value}
                </div>
                {sub ? (
                    <div className="mt-3 mono text-[11px] uppercase tracking-[0.2em] text-zinc-500">
                        {sub}
                    </div>
                ) : null}
            </div>
        </div>
    );
}
