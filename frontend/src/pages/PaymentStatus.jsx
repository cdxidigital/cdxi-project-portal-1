import React, { useEffect, useState, useRef } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { CheckCircle, XCircle, CircleNotch } from "@phosphor-icons/react";

export default function PaymentStatus() {
    const [params] = useSearchParams();
    const nav = useNavigate();
    const sessionId = params.get("session_id");
    const [state, setState] = useState("checking"); // checking | success | failed | timeout
    const [info, setInfo] = useState(null);
    const attempts = useRef(0);

    useEffect(() => {
        if (!sessionId) {
            setState("failed");
            return;
        }
        let cancelled = false;
        let timer = null;
        const schedule = (fn, ms) => {
            timer = setTimeout(fn, ms);
        };
        const poll = async () => {
            if (cancelled) return;
            if (attempts.current >= 8) {
                setState("timeout");
                return;
            }
            attempts.current += 1;
            try {
                const { data } = await api.get(`/payments/status/${sessionId}`);
                if (cancelled) return;
                setInfo(data);
                if (data.payment_status === "paid") {
                    setState("success");
                    return;
                }
                if (data.status === "expired") {
                    setState("failed");
                    return;
                }
                schedule(poll, 2000);
            } catch {
                if (!cancelled) schedule(poll, 2500);
            }
        };
        poll();
        return () => {
            cancelled = true;
            if (timer) clearTimeout(timer);
        };
    }, [sessionId]);

    return (
        <div className="grain flex min-h-screen items-center justify-center bg-[#08080A] p-6 text-white">
            <div
                className="w-full max-w-md border border-[#27272A] bg-[#0C0C0E] p-8"
                data-testid="payment-status-panel"
            >
                <p className="mono text-[10px] uppercase tracking-[0.3em] text-zinc-500">
                    cdxi/payments/receipt
                </p>

                {state === "checking" && (
                    <>
                        <div className="mt-6 flex items-center gap-3">
                            <CircleNotch className="animate-spin" size={22} />
                            <h1 className="font-display text-3xl font-bold tracking-tight">
                                Verifying payment
                            </h1>
                        </div>
                        <p className="mt-3 text-sm text-zinc-400">
                            Stripe is confirming your transaction. This usually takes a
                            few seconds.
                        </p>
                    </>
                )}

                {state === "success" && (
                    <>
                        <div className="mt-6 flex items-center gap-3">
                            <CheckCircle weight="fill" size={26} color="#00FF66" />
                            <h1 className="font-display text-3xl font-bold tracking-tight">
                                Payment confirmed
                            </h1>
                        </div>
                        <p className="mt-3 text-sm text-zinc-400">
                            The milestone has been marked as paid. Progress is now
                            unlocked.
                        </p>
                        {info && (
                            <div className="mt-6 grid grid-cols-2 gap-0 border border-[#27272A]">
                                <Meta
                                    label="Amount"
                                    value={`$${(
                                        Number(info.amount_total || 0) / 100
                                    ).toFixed(2)}`}
                                />
                                <Meta label="Currency" value={(info.currency || "usd").toUpperCase()} />
                                <Meta label="Status" value={info.payment_status?.toUpperCase()} full />
                            </div>
                        )}
                    </>
                )}

                {state === "failed" && (
                    <>
                        <div className="mt-6 flex items-center gap-3">
                            <XCircle weight="fill" size={26} color="#FF3333" />
                            <h1 className="font-display text-3xl font-bold tracking-tight">
                                Payment failed
                            </h1>
                        </div>
                        <p className="mt-3 text-sm text-zinc-400">
                            The checkout session was cancelled or expired. You can try
                            again from the milestone.
                        </p>
                    </>
                )}

                {state === "timeout" && (
                    <>
                        <div className="mt-6 flex items-center gap-3">
                            <CircleNotch size={22} />
                            <h1 className="font-display text-3xl font-bold tracking-tight">
                                Still processing
                            </h1>
                        </div>
                        <p className="mt-3 text-sm text-zinc-400">
                            Taking longer than expected. Check back on the dashboard in a
                            moment.
                        </p>
                    </>
                )}

                <button
                    onClick={() => nav("/")}
                    className="mt-8 inline-flex h-11 w-full items-center justify-center bg-white text-xs uppercase tracking-[0.25em] text-black transition-colors hover:bg-zinc-200"
                    data-testid="payment-return-button"
                >
                    Return to Dashboard
                </button>
            </div>
        </div>
    );
}

function Meta({ label, value, full }) {
    return (
        <div
            className={`border-b border-[#27272A] p-3 last:border-b-0 md:border-b-0 md:border-r last:border-r-0 ${full ? "col-span-2 !border-r-0 border-t" : ""}`}
        >
            <div className="mono text-[10px] uppercase tracking-[0.25em] text-zinc-500">
                {label}
            </div>
            <div className="mono mt-1 text-sm text-white">{value}</div>
        </div>
    );
}
