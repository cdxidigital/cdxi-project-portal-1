import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { ArrowRight, LockKey } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Login() {
    const { user, login } = useAuth();
    const nav = useNavigate();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        if (user) nav("/", { replace: true });
    }, [user, nav]);

    const submit = async (e) => {
        e.preventDefault();
        setSubmitting(true);
        const res = await login(email, password);
        setSubmitting(false);
        if (!res.ok) {
            toast.error(res.error || "Login failed");
        } else {
            nav("/", { replace: true });
        }
    };

    return (
        <div className="grain relative flex min-h-screen bg-[#08080A] text-white">
            {/* Left: info panel */}
            <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden border-r border-[#27272A] p-10 lg:flex">
                <div
                    className="absolute inset-0 opacity-40"
                    style={{
                        backgroundImage:
                            "radial-gradient(circle at 20% 20%, rgba(51,102,255,0.18), transparent 40%), radial-gradient(circle at 80% 80%, rgba(255,51,51,0.12), transparent 40%)",
                    }}
                />
                <div className="relative">
                    <div className="mono text-[11px] uppercase tracking-[0.3em] text-zinc-500">
                        cdxi · admin os
                    </div>
                    <div className="mt-3 font-display text-3xl font-bold tracking-tight">
                        Multi-Client Control Panel
                    </div>
                </div>
                <div className="relative max-w-md">
                    <p className="font-display text-4xl font-bold leading-[1.05] tracking-tight">
                        Payment unlocks progress.
                        <br />
                        Progress unlocks delivery.
                        <br />
                        <span className="text-[#00FF66]">Delivery unlocks launch.</span>
                    </p>
                    <div className="mt-10 grid grid-cols-3 gap-4 border-t border-[#27272A] pt-6">
                        <Stat label="Clients" value="∞" />
                        <Stat label="Pipeline" value="LIVE" />
                        <Stat label="Uptime" value="100%" />
                    </div>
                </div>
                <div className="relative mono text-[10px] uppercase tracking-[0.25em] text-zinc-600">
                    revenue enforcement engine · v1.0
                </div>
            </div>

            {/* Right: form */}
            <div className="relative flex w-full flex-col items-center justify-center p-6 lg:w-1/2 lg:p-16">
                <form
                    onSubmit={submit}
                    className="w-full max-w-sm"
                    data-testid="login-form"
                >
                    <div className="flex items-center gap-2 mono text-[10px] uppercase tracking-[0.3em] text-zinc-500">
                        <LockKey size={12} /> Admin access
                    </div>
                    <h1 className="font-display mt-4 text-4xl font-bold tracking-tight text-white">
                        Sign in
                    </h1>
                    <p className="mt-2 text-sm text-zinc-400">
                        Enter your admin credentials to operate the control panel.
                    </p>

                    <label className="mt-8 block">
                        <span className="mono text-[10px] uppercase tracking-[0.25em] text-zinc-500">
                            Email
                        </span>
                        <input
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                            data-testid="login-email-input"
                            className="mt-2 block h-11 w-full border border-[#27272A] bg-[#0C0C0E] px-3 text-sm text-white outline-none transition-colors focus:border-[#3366FF]"
                        />
                    </label>

                    <label className="mt-4 block">
                        <span className="mono text-[10px] uppercase tracking-[0.25em] text-zinc-500">
                            Password
                        </span>
                        <input
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                            data-testid="login-password-input"
                            className="mt-2 block h-11 w-full border border-[#27272A] bg-[#0C0C0E] px-3 text-sm text-white outline-none transition-colors focus:border-[#3366FF]"
                        />
                    </label>

                    <button
                        type="submit"
                        disabled={submitting}
                        data-testid="login-submit-button"
                        className="mt-8 inline-flex h-11 w-full items-center justify-center gap-2 bg-white px-5 text-xs uppercase tracking-[0.25em] text-black transition-colors hover:bg-zinc-200 disabled:opacity-50"
                    >
                        {submitting ? "Authenticating…" : "Enter Control Panel"}
                        <ArrowRight size={14} />
                    </button>

                    <p className="mono mt-6 text-[10px] uppercase tracking-[0.2em] text-zinc-600">
                        admin access only
                    </p>
                </form>
            </div>
        </div>
    );
}

function Stat({ label, value }) {
    return (
        <div>
            <div className="mono font-display text-xl font-bold text-white">
                {value}
            </div>
            <div className="mono mt-1 text-[10px] uppercase tracking-[0.25em] text-zinc-500">
                {label}
            </div>
        </div>
    );
}
