import React, { useCallback, useEffect, useState } from "react";
import {
    api,
    formatCurrency,
    formatDate,
    getErrorMessage,
    isPastDate,
} from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import KpiCard from "@/components/KpiCard";
import StatusBadge from "@/components/StatusBadge";
import NewClientDialog from "@/components/NewClientDialog";
import ClientDetailDrawer from "@/components/ClientDetailDrawer";
import {
    Plus,
    SignOut,
    Stack,
    CurrencyCircleDollar,
    Warning,
    ArrowUpRight,
    CircleNotch,
} from "@phosphor-icons/react";

export default function Dashboard() {
    const { user, logout } = useAuth();
    const [clients, setClients] = useState([]);
    const [kpis, setKpis] = useState(null);
    const [loading, setLoading] = useState(true);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [activeClient, setActiveClient] = useState(null);

    const refreshKpis = useCallback(async () => {
        try {
            const { data } = await api.get("/kpis");
            setKpis(data);
        } catch (err) {
            console.warn("KPI refresh failed:", err?.message || err);
        }
    }, []);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const [cRes, kRes] = await Promise.all([
                api.get("/clients"),
                api.get("/kpis"),
            ]);
            setClients(cRes.data);
            setKpis(kRes.data);
        } catch (err) {
            if (err?.response?.status !== 401) {
                toast.error(getErrorMessage(err, "Failed to load dashboard"));
            }
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const openClient = (c) => setActiveClient(c);

    const onDrawerChange = (updated) => {
        if (updated === null) {
            setActiveClient(null);
            load();
            return;
        }
        setActiveClient(updated);
        setClients((prev) =>
            prev.map((c) => (c.id === updated.id ? updated : c)),
        );
        refreshKpis();
    };

    return (
        <div className="grain min-h-screen bg-[#08080A] text-white">
            {/* Header */}
            <header className="border-b border-[#27272A] bg-[#08080A]">
                <div className="mx-auto flex max-w-[1400px] items-center justify-between px-6 py-5 md:px-10">
                    <div className="flex items-center gap-4">
                        <div className="flex h-10 w-10 items-center justify-center border border-[#27272A] bg-[#0C0C0E]">
                            <span className="mono font-display text-xl font-black">
                                c
                            </span>
                        </div>
                        <div>
                            <div className="font-display text-xl font-bold leading-none tracking-tight">
                                cdxi Admin OS
                            </div>
                            <div className="mono mt-1 text-[10px] uppercase tracking-[0.3em] text-zinc-500">
                                Multi-Client Control Panel
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        <div className="mono hidden text-right text-[10px] uppercase tracking-[0.25em] text-zinc-500 sm:block">
                            <div>{user?.email}</div>
                            <div className="text-emerald-400">● online</div>
                        </div>
                        <button
                            onClick={() => setDialogOpen(true)}
                            data-testid="new-client-button"
                            className="inline-flex h-10 items-center gap-2 bg-white px-4 text-xs uppercase tracking-[0.25em] text-black transition-colors hover:bg-zinc-200"
                        >
                            <Plus size={14} weight="bold" />
                            New Client
                        </button>
                        <button
                            onClick={logout}
                            data-testid="logout-button"
                            aria-label="Sign out"
                            className="flex h-10 w-10 items-center justify-center border border-[#27272A] text-zinc-400 transition-colors hover:bg-[#1A1A1D] hover:text-white"
                            title="Sign out"
                        >
                            <SignOut size={14} />
                        </button>
                    </div>
                </div>
            </header>

            <main className="mx-auto max-w-[1400px] px-6 py-8 md:px-10 md:py-10">
                {/* Overlines */}
                <div className="flex items-baseline justify-between">
                    <div>
                        <p className="mono text-[10px] uppercase tracking-[0.3em] text-zinc-500">
                            cdxi/ops/overview
                        </p>
                        <h1 className="font-display mt-2 text-4xl font-bold leading-none tracking-tight sm:text-5xl">
                            Control Centre
                        </h1>
                    </div>
                    <div className="hidden text-right md:block">
                        <p className="mono text-[10px] uppercase tracking-[0.25em] text-zinc-500">
                            {new Date().toLocaleDateString("en-GB", {
                                weekday: "long",
                                day: "2-digit",
                                month: "long",
                                year: "numeric",
                            })}
                        </p>
                    </div>
                </div>

                {/* KPI cards */}
                <section
                    className="mt-8 grid grid-cols-1 gap-0 border border-[#27272A] md:grid-cols-3"
                    data-testid="kpi-grid"
                >
                    <div className="border-b border-[#27272A] md:border-b-0 md:border-r">
                        <KpiCard
                            testId="kpi-active-projects"
                            label="Active Projects"
                            value={kpis ? kpis.active_projects : "—"}
                            sub={`${kpis?.total_clients ?? 0} total clients`}
                            icon={<Stack size={14} />}
                        />
                    </div>
                    <div className="border-b border-[#27272A] md:border-b-0 md:border-r">
                        <KpiCard
                            testId="kpi-revenue-pipeline"
                            label="Revenue Pipeline"
                            value={
                                kpis
                                    ? formatCurrency(kpis.revenue_pipeline)
                                    : "—"
                            }
                            sub="outstanding unpaid"
                            icon={<CurrencyCircleDollar size={14} />}
                        />
                    </div>
                    <div>
                        <KpiCard
                            testId="kpi-overdue-payments"
                            label="Overdue Payments"
                            value={
                                kpis ? formatCurrency(kpis.overdue_payments) : "—"
                            }
                            sub="past due date"
                            tone={kpis && kpis.overdue_payments > 0 ? "danger" : "default"}
                            icon={<Warning size={14} />}
                        />
                    </div>
                </section>

                {/* Clients table */}
                <section className="mt-10">
                    <div className="flex items-center justify-between border-b border-[#27272A] pb-3">
                        <h2 className="font-display text-xl font-semibold tracking-tight">
                            Clients
                        </h2>
                        <p className="mono text-[10px] uppercase tracking-[0.25em] text-zinc-500">
                            {clients.length} record{clients.length === 1 ? "" : "s"}
                        </p>
                    </div>

                    <div className="border border-t-0 border-[#27272A]">
                        {/* Header */}
                        <div className="hidden grid-cols-[1.3fr_1.3fr_1fr_1.4fr_1fr_1fr_40px] gap-4 border-b border-[#27272A] bg-[#0C0C0E] px-5 py-3 mono text-[10px] uppercase tracking-[0.25em] text-zinc-500 md:grid">
                            <div>Client</div>
                            <div>Project</div>
                            <div>Status</div>
                            <div>Progress</div>
                            <div>Next Payment</div>
                            <div>Due</div>
                            <div />
                        </div>

                        {loading && (
                            <div
                                className="flex items-center justify-center gap-2 p-10 mono text-xs uppercase tracking-[0.25em] text-zinc-500"
                                data-testid="clients-loading"
                            >
                                <CircleNotch className="animate-spin" size={14} />
                                Loading
                            </div>
                        )}

                        {!loading && clients.length === 0 && (
                            <div
                                className="p-10 text-center mono text-xs uppercase tracking-[0.25em] text-zinc-500"
                                data-testid="clients-empty"
                            >
                                No clients yet. Click <span className="text-white">+ New Client</span> to onboard one.
                            </div>
                        )}

                        {!loading &&
                            clients.map((c, idx) => (
                                <ClientRow
                                    key={c.id}
                                    client={c}
                                    idx={idx}
                                    onOpen={() => openClient(c)}
                                />
                            ))}
                    </div>
                </section>

                <footer className="mt-16 flex flex-col items-start justify-between gap-3 border-t border-[#27272A] pt-6 sm:flex-row sm:items-center">
                    <div className="mono text-[10px] uppercase tracking-[0.3em] text-zinc-600">
                        cdxi · business operating system · revenue enforcement engine
                    </div>
                    <div className="mono text-[10px] uppercase tracking-[0.25em] text-zinc-600">
                        v1.0 · ops://live
                    </div>
                </footer>
            </main>

            <NewClientDialog
                open={dialogOpen}
                onOpenChange={setDialogOpen}
                onCreated={(c) => {
                    setClients((prev) => [c, ...prev]);
                    refreshKpis();
                }}
            />

            <ClientDetailDrawer
                client={activeClient}
                onClose={() => setActiveClient(null)}
                onChange={onDrawerChange}
            />
        </div>
    );
}

function ClientRow({ client, idx, onOpen }) {
    const p = client.project;
    const progress = p?.progress ?? 0;
    const status = p?.status ?? "Not Started";
    const overdue =
        status !== "Completed" &&
        p?.next_due &&
        p?.next_payment != null &&
        isPastDate(p.next_due);
    const fillClass =
        status === "Completed"
            ? "completed"
            : overdue
              ? "delayed"
              : "";
    return (
        <button
            onClick={onOpen}
            data-testid={`client-row-${idx}`}
            className="group grid w-full grid-cols-1 items-center gap-2 border-b border-[#27272A] px-5 py-4 text-left transition-colors last:border-b-0 hover:bg-[#0F0F12] md:grid-cols-[1.3fr_1.3fr_1fr_1.4fr_1fr_1fr_40px] md:gap-4"
        >
            <div className="flex items-baseline gap-3">
                <span className="mono text-[10px] text-zinc-500">
                    {String(idx + 1).padStart(2, "0")}
                </span>
                <span className="truncate text-sm font-medium text-white">
                    {client.name}
                </span>
            </div>
            <div className="truncate text-sm text-zinc-300">{p?.name || "—"}</div>
            <div>
                <StatusBadge status={status} testId={`client-row-${idx}-status`} />
            </div>
            <div className="flex items-center gap-3">
                <div className="progress-bar-track h-1.5 w-full">
                    <div
                        className={`progress-bar-fill h-full ${fillClass}`}
                        style={{ width: `${progress}%` }}
                    />
                </div>
                <span className="mono w-10 shrink-0 text-right text-[11px] text-zinc-400">
                    {progress}%
                </span>
            </div>
            <div className="mono text-sm text-white">
                {p?.next_payment != null ? formatCurrency(p.next_payment) : "—"}
            </div>
            <div
                className={`mono text-sm ${
                    overdue ? "text-red-500" : "text-zinc-300"
                }`}
            >
                {formatDate(p?.next_due)}
            </div>
            <div className="hidden justify-end md:flex">
                <ArrowUpRight
                    size={16}
                    className="text-zinc-600 transition-colors group-hover:text-white"
                />
            </div>
        </button>
    );
}
