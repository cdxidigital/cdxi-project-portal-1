import React from "react";

/**
 * Minimal app-level error boundary. Prevents a single render bug from wiping
 * the entire screen in production.
 */
export default class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { error: null };
    }

    static getDerivedStateFromError(error) {
        return { error };
    }

    componentDidCatch(error, info) {
        // eslint-disable-next-line no-console
        console.error("Unhandled UI error:", error, info);
    }

    handleReload = () => {
        this.setState({ error: null });
        if (typeof window !== "undefined") {
            window.location.reload();
        }
    };

    render() {
        if (!this.state.error) return this.props.children;
        return (
            <div className="grain flex min-h-screen items-center justify-center bg-[#08080A] p-6 text-white">
                <div className="w-full max-w-md border border-[#27272A] bg-[#0C0C0E] p-8">
                    <p className="mono text-[10px] uppercase tracking-[0.3em] text-zinc-500">
                        cdxi/error/runtime
                    </p>
                    <h1 className="font-display mt-4 text-3xl font-bold tracking-tight">
                        Something went wrong
                    </h1>
                    <p className="mt-3 text-sm text-zinc-400">
                        The control panel hit an unexpected error. Try
                        reloading — your data is safe.
                    </p>
                    <button
                        onClick={this.handleReload}
                        className="mt-8 inline-flex h-11 w-full items-center justify-center bg-white text-xs uppercase tracking-[0.25em] text-black transition-colors hover:bg-zinc-200"
                        data-testid="error-boundary-reload"
                    >
                        Reload
                    </button>
                </div>
            </div>
        );
    }
}
