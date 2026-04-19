import React from "react";
import "@/App.css";
import {
    BrowserRouter,
    Routes,
    Route,
    Navigate,
    useLocation,
} from "react-router-dom";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import PaymentStatus from "@/pages/PaymentStatus";
import ErrorBoundary from "@/components/ErrorBoundary";
import { Toaster } from "@/components/ui/sonner";

function Protected({ children }) {
    const { user, checking } = useAuth();
    const location = useLocation();
    if (checking) {
        return (
            <div className="flex min-h-screen items-center justify-center bg-[#08080A] text-zinc-500 mono text-xs uppercase tracking-[0.25em]">
                Booting…
            </div>
        );
    }
    if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
    return children;
}

function AppRoutes() {
    return (
        <Routes>
            <Route path="/login" element={<Login />} />
            <Route
                path="/"
                element={
                    <Protected>
                        <Dashboard />
                    </Protected>
                }
            />
            <Route
                path="/payment-status"
                element={
                    <Protected>
                        <PaymentStatus />
                    </Protected>
                }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
    );
}

export default function App() {
    return (
        <div className="App">
            <ErrorBoundary>
                <BrowserRouter>
                    <AuthProvider>
                        <AppRoutes />
                        <Toaster
                            theme="dark"
                            position="top-right"
                            toastOptions={{
                                style: {
                                    background: "#0C0C0E",
                                    border: "1px solid #27272A",
                                    color: "#ffffff",
                                    borderRadius: "0",
                                    fontFamily: "IBM Plex Sans, sans-serif",
                                },
                            }}
                        />
                    </AuthProvider>
                </BrowserRouter>
            </ErrorBoundary>
        </div>
    );
}
