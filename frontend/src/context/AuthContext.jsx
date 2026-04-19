import React, {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";
import {
    api,
    TOKEN_KEY,
    getErrorMessage,
    registerAuthFailureHandler,
} from "@/lib/api";

const AuthContext = createContext(null);

/**
 * AuthContext state:
 *   user    -> object when authenticated, null when unauthenticated.
 *   checking -> true only while we verify an existing token on mount.
 */
export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [checking, setChecking] = useState(true);
    const bootstrappedRef = useRef(false);

    const clearSession = useCallback(() => {
        localStorage.removeItem(TOKEN_KEY);
        setUser(null);
    }, []);

    const bootstrap = useCallback(async () => {
        const token = localStorage.getItem(TOKEN_KEY);
        if (!token) {
            setUser(null);
            setChecking(false);
            return;
        }
        try {
            const { data } = await api.get("/auth/me");
            setUser(data);
        } catch (err) {
            console.warn("Auth bootstrap failed:", err?.message || err);
            localStorage.removeItem(TOKEN_KEY);
            setUser(null);
        } finally {
            setChecking(false);
        }
    }, []);

    useEffect(() => {
        // StrictMode mounts effects twice in dev - only bootstrap once.
        if (bootstrappedRef.current) return;
        bootstrappedRef.current = true;
        bootstrap();
    }, [bootstrap]);

    // Let the axios 401 interceptor force-logout here.
    useEffect(() => {
        registerAuthFailureHandler(() => {
            setUser(null);
        });
    }, []);

    const login = useCallback(async (email, password) => {
        try {
            const { data } = await api.post("/auth/login", { email, password });
            localStorage.setItem(TOKEN_KEY, data.access_token);
            setUser(data.user);
            return { ok: true };
        } catch (err) {
            return { ok: false, error: getErrorMessage(err, "Login failed") };
        }
    }, []);

    const logout = useCallback(async () => {
        try {
            await api.post("/auth/logout");
        } catch (err) {
            console.warn("Logout request failed:", err?.message || err);
        }
        clearSession();
    }, [clearSession]);

    const value = useMemo(
        () => ({ user, checking, login, logout }),
        [user, checking, login, logout],
    );

    return (
        <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
    );
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) {
        throw new Error("useAuth must be used within an AuthProvider");
    }
    return ctx;
}
