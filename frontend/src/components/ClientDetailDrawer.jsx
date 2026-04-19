import React, { useState } from "react";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { VisuallyHidden } from "@radix-ui/react-visually-hidden";
import { api, formatCurrency, formatDate, getErrorMessage } from "@/lib/api";
import StatusBadge from "@/components/StatusBadge";
import { toast } from "sonner";
import {
    X,
    Plus,
    CheckCircle,
    Circle,
    CurrencyDollar,
    Trash,
    CreditCard,
    Lock,
} from "@phosphor-icons/react";

export default function ClientDetailDrawer({ client, onClose, onChange }) {
    const open = !!client;
    const project = client?.project;
    const milestones = project?.milestones || [];

    const [addingMilestone, setAddingMilestone] = useState(false);
    const [savingMilestone, setSavingMilestone] = useState(false);
    const [mName, setMName] = useState("");
    const [mAmount, setMAmount] = useState("");
    const [mDue, setMDue] = useState("");

    const reload = async () => {
        if (!client) return;
        try {
            const { data } = await api.get(`/clients/${client.id}`);
            onChange?.(data);
        } catch (err) {
            console.error("Failed to reload client:", err);
            toast.error("Failed to refresh client");
        }
    };

    const togglePaid = async (m) => {
        try {
            await api.patch(`/milestones/${m.id}`, {
                payment_status: m.payment_status === "paid" ? "unpaid" : "paid",
            });
            toast.success(m.payment_status === "paid" ? "Marked unpaid" : "Marked paid");
            await reload();
        } catch (e) {
            toast.error(getErrorMessage(e));
        }
    };

    const toggleCompleted = async (m) => {
        try {
            await api.patch(`/milestones/${m.id}`, { completed: !m.completed });
            await reload();
        } catch (e) {
            toast.error(getErrorMessage(e));
        }
    };

    const removeMilestone = async (m) => {
        if (!window.confirm(`Delete milestone "${m.name}"? This cannot be undone.`)) {
            return;
        }
        try {
            await api.delete(`/milestones/${m.id}`);
            toast.success("Milestone removed");
            await reload();
        } catch (e) {
            toast.error(getErrorMessage(e));
        }
    };

    const payWithStripe = async (m) => {
        try {
            const { data } = await api.post(`/milestones/${m.id}/checkout`, {
                origin_url: window.location.origin,
            });
            if (data?.url) {
                window.location.href = data.url;
            } else {
                toast.error("Stripe did not return a checkout URL");
            }
        } catch (e) {
            toast.error(getErrorMessage(e));
        }
    };

    const deleteClient = async () => {
        if (!client) return;
        if (!window.confirm(`Remove ${client.name} and all project data?`)) return;
        try {
            await api.delete(`/clients/${client.id}`);
            toast.success("Client removed");
            onChange?.(null);
            onClose();
        } catch (e) {
            toast.error(getErrorMessage(e));
        }
    };

    const addMilestone = async (e) => {
        e.preventDefault();
        if (savingMilestone) return;
        const name = mName.trim();
        const amountNum = Number(mAmount);
        if (!name || !project) {
            toast.error("Milestone name is required");
            return;
        }
        if (!Number.isFinite(amountNum) || amountNum < 0) {
            toast.error("Amount must be a non-negative number");
            return;
        }
        setSavingMilestone(true);
        try {
            await api.post(`/projects/${project.id}/milestones`, {
                name,
                amount: amountNum,
                due_date: mDue || null,
            });
            setMName("");
            setMAmount("");
            setMDue("");
            setAddingMilestone(false);
            await reload();
        } catch (e) {
            toast.error(getErrorMessage(e));
        } finally {
            setSavingMilestone(false);
        }
    };

    const firstUnpaidIdx = milestones.findIndex((m) => m.payment_status !== "paid");

    return (
        <Sheet
            open={open}
            onOpenChange={(v) => {
                if (!v) onClose();
            }}
        >
            <SheetContent
                side="right"
                data-testid="client-detail-drawer"
                className="w-full rounded-none border-l border-[#27272A] bg-[#08080A] p-0 sm:max-w-xl md:max-w-2xl"
            >
                {client && (
                    <div className="flex h-full flex-col">
                        <VisuallyHidden>
                            <SheetTitle>{client.name} details</SheetTitle>
                            <SheetDescription>
                                Manage milestones, payments and project progress for {client.name}.
                            </SheetDescription>
                        </VisuallyHidden>
                        {/* Header */}
                        <div className="flex items-start justify-between border-b border-[#27272A] p-6">
                            <div>
                                <p className="mono text-[10px] uppercase tracking-[0.25em] text-zinc-500">
                                    cdxi/client/{String(client.id).slice(0, 6)}
                                </p>
                                <h2 className="font-display mt-1 text-3xl font-bold tracking-tight text-white">
                                    {client.name}
                                </h2>
                                {client.email && (
                                    <p className="mono mt-1 text-xs text-zinc-500">
                                        {client.email}
                                    </p>
                                )}
                            </div>
                            <button
                                onClick={onClose}
                                className="h-9 w-9 border border-[#27272A] text-zinc-400 transition-colors hover:bg-[#1A1A1D] hover:text-white"
                                data-testid="drawer-close-button"
                            >
                                <X size={16} className="mx-auto" />
                            </button>
                        </div>

                        {/* Project summary */}
                        {project && (
                            <div className="grid grid-cols-3 border-b border-[#27272A]">
                                <MetaCell label="Project" value={project.name} />
                                <MetaCell
                                    label="Status"
                                    valueNode={<StatusBadge status={project.status} />}
                                />
                                <MetaCell
                                    label="Progress"
                                    value={`${project.progress}%`}
                                    mono
                                />
                            </div>
                        )}

                        {/* Body */}
                        <div className="flex-1 overflow-y-auto">
                            <div className="p-6">
                                <div className="flex items-center justify-between">
                                    <h3 className="font-display text-xl font-semibold tracking-tight">
                                        Milestones
                                    </h3>
                                    <button
                                        onClick={() => setAddingMilestone((v) => !v)}
                                        className="inline-flex h-8 items-center gap-2 border border-[#27272A] px-3 mono text-[10px] uppercase tracking-[0.2em] text-zinc-300 transition-colors hover:bg-[#1A1A1D] hover:text-white"
                                        data-testid="add-milestone-toggle"
                                    >
                                        <Plus size={12} />
                                        {addingMilestone ? "Close" : "Add"}
                                    </button>
                                </div>

                                {addingMilestone && (
                                    <form
                                        onSubmit={addMilestone}
                                        className="mt-4 grid grid-cols-1 gap-3 border border-[#27272A] bg-[#0C0C0E] p-4 sm:grid-cols-[1fr_140px_160px_auto]"
                                    >
                                        <input
                                            value={mName}
                                            onChange={(e) => setMName(e.target.value)}
                                            placeholder="Milestone name"
                                            className="h-10 border border-[#27272A] bg-[#08080A] px-3 text-sm outline-none focus:border-[#3366FF]"
                                            data-testid="milestone-name-input"
                                        />
                                        <input
                                            value={mAmount}
                                            onChange={(e) => setMAmount(e.target.value)}
                                            type="number"
                                            step="0.01"
                                            placeholder="Amount"
                                            className="mono h-10 border border-[#27272A] bg-[#08080A] px-3 text-sm outline-none focus:border-[#3366FF]"
                                            data-testid="milestone-amount-input"
                                        />
                                        <input
                                            value={mDue}
                                            onChange={(e) => setMDue(e.target.value)}
                                            type="date"
                                            className="mono h-10 border border-[#27272A] bg-[#08080A] px-3 text-sm outline-none focus:border-[#3366FF]"
                                            data-testid="milestone-due-input"
                                        />
                                        <button
                                            type="submit"
                                            disabled={savingMilestone}
                                            className="h-10 bg-white px-4 text-xs uppercase tracking-[0.2em] text-black transition-colors hover:bg-zinc-200 disabled:opacity-50"
                                            data-testid="milestone-save-button"
                                        >
                                            {savingMilestone ? "Saving…" : "Save"}
                                        </button>
                                    </form>
                                )}

                                <div className="mt-4 border border-[#27272A]">
                                    {milestones.length === 0 && (
                                        <div className="p-8 text-center mono text-xs uppercase tracking-[0.2em] text-zinc-500">
                                            No milestones yet
                                        </div>
                                    )}
                                    {milestones.map((m, idx) => {
                                        const blocked =
                                            firstUnpaidIdx !== -1 && idx > firstUnpaidIdx;
                                        const paid = m.payment_status === "paid";
                                        return (
                                            <div
                                                key={m.id}
                                                data-testid={`milestone-row-${idx}`}
                                                className={`grid grid-cols-[auto_1fr_auto] items-center gap-4 border-b border-[#27272A] p-4 last:border-b-0 ${
                                                    blocked ? "stripe-block opacity-60" : ""
                                                }`}
                                            >
                                                <button
                                                    onClick={() => toggleCompleted(m)}
                                                    title={
                                                        paid
                                                            ? "Toggle completion"
                                                            : "Payment required first"
                                                    }
                                                    disabled={!paid}
                                                    className="flex h-8 w-8 items-center justify-center text-zinc-400 transition-colors hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
                                                    data-testid={`milestone-complete-toggle-${idx}`}
                                                >
                                                    {m.completed ? (
                                                        <CheckCircle
                                                            weight="fill"
                                                            size={22}
                                                            color="#00FF66"
                                                        />
                                                    ) : (
                                                        <Circle size={22} />
                                                    )}
                                                </button>
                                                <div className="min-w-0">
                                                    <div className="flex items-center gap-2">
                                                        <span className="mono text-[10px] text-zinc-500">
                                                            M{String(idx + 1).padStart(2, "0")}
                                                        </span>
                                                        <span
                                                            className={`truncate text-sm font-medium ${
                                                                m.completed
                                                                    ? "text-zinc-400 line-through"
                                                                    : "text-white"
                                                            }`}
                                                        >
                                                            {m.name}
                                                        </span>
                                                        {blocked && (
                                                            <Lock
                                                                size={12}
                                                                className="text-zinc-500"
                                                            />
                                                        )}
                                                    </div>
                                                    <div className="mt-1 flex items-center gap-3 mono text-[11px] text-zinc-500">
                                                        <span>{formatCurrency(m.amount)}</span>
                                                        <span>·</span>
                                                        <span>{formatDate(m.due_date)}</span>
                                                        <span>·</span>
                                                        <span
                                                            className={
                                                                paid
                                                                    ? "text-emerald-400"
                                                                    : "text-yellow-300"
                                                            }
                                                        >
                                                            {paid ? "PAID" : "UNPAID"}
                                                        </span>
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    {!paid && (
                                                        <button
                                                            onClick={() => payWithStripe(m)}
                                                            className="inline-flex h-8 items-center gap-1.5 border border-[#3366FF] bg-[#3366FF]/10 px-3 mono text-[10px] uppercase tracking-[0.2em] text-[#93B1FF] transition-colors hover:bg-[#3366FF] hover:text-white"
                                                            data-testid={`milestone-stripe-button-${idx}`}
                                                        >
                                                            <CreditCard size={12} />
                                                            Stripe
                                                        </button>
                                                    )}
                                                    <button
                                                        onClick={() => togglePaid(m)}
                                                        className={`inline-flex h-8 items-center gap-1.5 border px-3 mono text-[10px] uppercase tracking-[0.2em] transition-colors ${
                                                            paid
                                                                ? "border-emerald-600/40 text-emerald-400 hover:bg-emerald-900/20"
                                                                : "border-[#27272A] text-zinc-300 hover:bg-[#1A1A1D]"
                                                        }`}
                                                        data-testid={`milestone-toggle-paid-${idx}`}
                                                    >
                                                        <CurrencyDollar size={12} />
                                                        {paid ? "Unpaid" : "Mark Paid"}
                                                    </button>
                                                    <button
                                                        onClick={() => removeMilestone(m)}
                                                        className="flex h-8 w-8 items-center justify-center border border-[#27272A] text-zinc-500 transition-colors hover:border-red-600/40 hover:text-red-500"
                                                        data-testid={`milestone-delete-${idx}`}
                                                    >
                                                        <Trash size={12} />
                                                    </button>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>

                                <div className="mt-6 border border-[#27272A] bg-[#0C0C0E] p-4">
                                    <p className="mono text-[10px] uppercase tracking-[0.25em] text-zinc-500">
                                        Core Principle
                                    </p>
                                    <p className="font-display mt-2 text-base leading-snug">
                                        Payment unlocks progress. Progress unlocks delivery.
                                        Delivery unlocks launch.
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* Footer */}
                        <div className="flex items-center justify-between border-t border-[#27272A] p-5">
                            <button
                                onClick={deleteClient}
                                className="inline-flex h-9 items-center gap-2 border border-[#27272A] px-4 mono text-[10px] uppercase tracking-[0.2em] text-zinc-400 transition-colors hover:border-red-600/40 hover:text-red-500"
                                data-testid="delete-client-button"
                            >
                                <Trash size={12} />
                                Remove Client
                            </button>
                            <button
                                onClick={onClose}
                                className="h-9 bg-white px-5 text-xs uppercase tracking-[0.2em] text-black transition-colors hover:bg-zinc-200"
                                data-testid="drawer-done-button"
                            >
                                Done
                            </button>
                        </div>
                    </div>
                )}
            </SheetContent>
        </Sheet>
    );
}

function MetaCell({ label, value, valueNode, mono: monoVal }) {
    return (
        <div className="border-r border-[#27272A] p-4 last:border-r-0">
            <div className="mono text-[10px] uppercase tracking-[0.25em] text-zinc-500">
                {label}
            </div>
            <div
                className={`mt-2 text-sm text-white ${monoVal ? "mono font-medium" : ""}`}
            >
                {valueNode || value}
            </div>
        </div>
    );
}
