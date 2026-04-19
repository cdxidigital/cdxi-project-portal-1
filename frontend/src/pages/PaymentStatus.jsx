import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { CheckCircle, CircleNotch, XCircle } from "@phosphor-icons/react";

const MAX_POLL_ATTEMPTS = 8;
const POLL_INTERVAL_OK = 2000;
const POLL_INTERVAL_ERR = 2500;

function formatAmount(amountTotal, fallbackCurrency = "usd") {
    if (amountTotal == null || Number.isNaN(Number(amountTotal))) return "—";
    const value = Number(amountTotal) / 100;
    return `${(fallbackCurrency || "usd").toUpperCase() === "USD" ? "$" : ""}${value.toFixed(2)}`;
}

export default function PaymentStatus() {
    const [params] = useSearchParams();
    const nav = useNavigate();
    const sessionId = params.get("session_id");

    // states: checking | success | failed | timeout
    const [state, setState] = useState(sessionId ? "checking" : "failed");
    const [info, setInfo] = useState(null);

    // Track attempts + pending timeout so we can fully clean up on unmount.
    const attemptsRef = useRef(0);
    const timerRef = useRef(null);
    const cancelledRef = useRef(false);

    useEffect(() => {
        if (!sessionId) return undefined;
        cancelledRef.current = false;
        attemptsRef.current = 0;

        const schedule = (fn, ms) => {
            timerRef.current = setTimeout(fn, ms);
        };

        const poll = async () => {
            if (cancelledRef.current) return;
            if (attemptsRef.current >= MAX_POLL_ATTEMPTS) {
                setState("timeout");
                return;
            }
            attemptsRef.current += 1;
            try {
                const { data } = await api.get(`/payments/status/${sessionId}`);
                if (cancelledRef.current) return;
                setInfo(data);
                if (data.payment_status === "paid") {
                    setState("success");
                    return;
                }
                if (data.status === "expired") {
                    setState("failed");
                    return;
                }
                schedule(poll, POLL_INTERVAL_OK);
            } catch {
                if (cancelledRef.current) return;
                schedule(poll, POLL_INTERVAL_ERR);
            }
        };

        poll();

        return () => {
            cancelledRef.current = true;
            if (timerRef.current) {
                clearTimeout(timerRef.current);
                timerRef.current = null;
            }
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
                            Stripe is confirming your transaction. This usually takes a few seconds.
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
                            The milestone has been marked as paid. Progress is now unlocked.
                        </p>
                        {info && (
                            <div className="mt-6 grid grid-cols-2 gap-0 border border-[#27272A]">
                                <Meta
                                    label="Amount"
                                    value={formatAmount(info.amount_total, info.currency)}
                                />
                                <Meta
                                    label="Currency"
                                    value={(info.currency || "usd").toUpperCase()}
                                />
                                <Meta
                                    label="Status"
                                    value={(info.payment_status || "").toUpperCase()}
                                    full
                                />
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
                            {sessionId
                                ? "The checkout session was cancelled or expired. You can try again from the milestone."
                                : "No checkout session was provided. Return to the dashboard to retry."}
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
                            Taking longer than expected. Check back on the dashboard in a moment.
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
