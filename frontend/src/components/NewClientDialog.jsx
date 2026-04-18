import React, { useState } from "react";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, formatApiErrorDetail } from "@/lib/api";
import { toast } from "sonner";

export default function NewClientDialog({ open, onOpenChange, onCreated }) {
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [projectName, setProjectName] = useState("");
    const [totalAmount, setTotalAmount] = useState("");
    const [saving, setSaving] = useState(false);

    const reset = () => {
        setName("");
        setEmail("");
        setProjectName("");
        setTotalAmount("");
    };

    const submit = async (e) => {
        e.preventDefault();
        if (!name.trim() || !projectName.trim()) {
            toast.error("Client name and project name are required");
            return;
        }
        setSaving(true);
        try {
            const { data } = await api.post("/clients", {
                name: name.trim(),
                email: email.trim() || null,
                project_name: projectName.trim(),
                total_amount: Number(totalAmount) || 0,
            });
            toast.success(`${data.name} onboarded`);
            onCreated?.(data);
            reset();
            onOpenChange(false);
        } catch (e) {
            toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent
                data-testid="new-client-dialog"
                className="rounded-none border border-[#27272A] bg-[#0C0C0E] p-0 sm:max-w-lg"
            >
                <form onSubmit={submit}>
                    <DialogHeader className="border-b border-[#27272A] p-6">
                        <DialogTitle className="font-display text-2xl font-bold tracking-tight">
                            New Client
                        </DialogTitle>
                        <DialogDescription className="mono text-[11px] uppercase tracking-[0.2em] text-zinc-500">
                            cdxi/onboard/001
                        </DialogDescription>
                    </DialogHeader>
                    <div className="grid gap-4 p-6">
                        <FieldLabel>Client Name</FieldLabel>
                        <Input
                            data-testid="new-client-name-input"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="e.g. Christian Dix"
                            className="h-11 rounded-none border-[#27272A] bg-[#08080A] focus-visible:ring-[#3366FF]"
                            autoFocus
                        />
                        <FieldLabel>Email (optional)</FieldLabel>
                        <Input
                            data-testid="new-client-email-input"
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            placeholder="name@domain.com"
                            className="h-11 rounded-none border-[#27272A] bg-[#08080A] focus-visible:ring-[#3366FF]"
                        />
                        <FieldLabel>Project Name</FieldLabel>
                        <Input
                            data-testid="new-client-project-input"
                            value={projectName}
                            onChange={(e) => setProjectName(e.target.value)}
                            placeholder="e.g. Cosmic Blueprint"
                            className="h-11 rounded-none border-[#27272A] bg-[#08080A] focus-visible:ring-[#3366FF]"
                        />
                        <FieldLabel>Total Contract Value (USD)</FieldLabel>
                        <Input
                            data-testid="new-client-amount-input"
                            type="number"
                            min="0"
                            step="0.01"
                            value={totalAmount}
                            onChange={(e) => setTotalAmount(e.target.value)}
                            placeholder="3300.00"
                            className="mono h-11 rounded-none border-[#27272A] bg-[#08080A] focus-visible:ring-[#3366FF]"
                        />
                    </div>
                    <DialogFooter className="border-t border-[#27272A] p-5">
                        <button
                            type="button"
                            onClick={() => onOpenChange(false)}
                            className="h-10 border border-[#27272A] bg-transparent px-5 text-xs uppercase tracking-[0.2em] text-zinc-300 transition-colors hover:bg-[#1A1A1D]"
                            data-testid="new-client-cancel-button"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={saving}
                            className="h-10 bg-white px-5 text-xs uppercase tracking-[0.2em] text-black transition-colors hover:bg-zinc-200 disabled:opacity-50"
                            data-testid="new-client-submit-button"
                        >
                            {saving ? "Creating…" : "Create Client"}
                        </button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}

function FieldLabel({ children }) {
    return (
        <Label className="mono text-[10px] uppercase tracking-[0.25em] text-zinc-500">
            {children}
        </Label>
    );
}
