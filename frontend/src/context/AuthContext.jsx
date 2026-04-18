import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, TOKEN_KEY, formatApiErrorDetail } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [checking, setChecking] = useState(true);

    const bootstrap = useCallback(async () => {
        const token = localStorage.getItem(TOKEN_KEY);
        if (!token) {
            setUser(false);
            setChecking(false);
            return;
        }
        try {
            const { data } = await api.get("/auth/me");
            setUser(data);
        } catch (err) {
            console.warn("Auth bootstrap failed:", err?.message || err);
            localStorage.removeItem(TOKEN_KEY);
            setUser(false);
        } finally {
            setChecking(false);
        }
    }, []);

    useEffect(() => {
        bootstrap();
    }, [bootstrap]);

    const login = async (email, password) => {
        try {
            const { data } = await api.post("/auth/login", { email, password });
            localStorage.setItem(TOKEN_KEY, data.access_token);
            setUser(data.user);
            return { ok: true };
        } catch (e) {
            return {
                ok: false,
                error: formatApiErrorDetail(e.response?.data?.detail) || e.message,
            };
        }
    };

    const logout = async () => {
        try {
            await api.post("/auth/logout");
        } catch (err) {
            console.warn("Logout request failed:", err?.message || err);
        }
        localStorage.removeItem(TOKEN_KEY);
        setUser(false);
    };

    return (
        <AuthContext.Provider value={{ user, checking, login, logout }}>
            {children}
        </AuthContext.Provider>
    );
}

export const useAuth = () => useContext(AuthContext);
