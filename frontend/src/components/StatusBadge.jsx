import React from "react";

const MAP = {
    "Not Started": { dot: "#71717A", text: "text-zinc-400", label: "NOT STARTED" },
    "In Progress": { dot: "#FFCC00", text: "text-yellow-300", label: "IN PROGRESS" },
    Completed: { dot: "#00FF66", text: "text-emerald-400", label: "COMPLETED" },
    Delayed: { dot: "#FF3333", text: "text-red-500", label: "DELAYED" },
};

export default function StatusBadge({ status, testId }) {
    const m = MAP[status] || MAP["Not Started"];
    return (
        <span
            data-testid={testId}
            className={`inline-flex items-center gap-2 border border-[#27272A] bg-[#0F0F12] px-2 py-1 text-[10px] font-medium uppercase tracking-[0.18em] mono ${m.text}`}
        >
            <span
                className="h-1.5 w-1.5"
                style={{ background: m.dot }}
                aria-hidden
            />
            {m.label}
        </span>
    );
}
