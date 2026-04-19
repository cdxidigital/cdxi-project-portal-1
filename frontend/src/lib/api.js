import axios from "axios";

// Fall back to same-origin in production so missing env vars don't produce
// "undefined/api" request URLs.
const RAW_BACKEND_URL =
    (typeof process !== "undefined" && process.env.REACT_APP_BACKEND_URL) || "";
const BACKEND_URL = String(RAW_BACKEND_URL).replace(/\/+$/, "");

export const API = `${BACKEND_URL}/api`;
export const TOKEN_KEY = "cdxi_token";

export const api = axios.create({
    baseURL: API,
    timeout: 30_000,
});

api.interceptors.request.use((config) => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Response interceptor: on 401 clear the stale token and bounce to login.
// Avoids the app getting stuck in a weird "logged in but every request fails"
// state after a token expires.
let authFailureHandler = null;
export function registerAuthFailureHandler(fn) {
    authFailureHandler = fn;
}

api.interceptors.response.use(
    (res) => res,
    (error) => {
        const status = error?.response?.status;
        if (status === 401) {
            localStorage.removeItem(TOKEN_KEY);
            if (typeof authFailureHandler === "function") {
                try {
                    authFailureHandler();
                } catch (e) {
                    // swallow - handler must not throw
                }
            }
        }
        return Promise.reject(error);
    },
);

export function formatApiErrorDetail(detail) {
    if (detail == null) return "Something went wrong. Please try again.";
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail))
        return detail
            .map((e) =>
                e && typeof e.msg === "string" ? e.msg : JSON.stringify(e),
            )
            .filter(Boolean)
            .join(" ");
    if (detail && typeof detail.msg === "string") return detail.msg;
    return String(detail);
}

export function getErrorMessage(err, fallback = "Something went wrong.") {
    if (!err) return fallback;
    const detail = err?.response?.data?.detail;
    if (detail != null) return formatApiErrorDetail(detail);
    if (err.message) return err.message;
    return fallback;
}

export function formatCurrency(n) {
    if (n == null || Number.isNaN(Number(n))) return "—";
    return `$${Number(n).toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}`;
}

export function formatDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
    });
}

/**
 * True if the given ISO (YYYY-MM-DD) date is strictly before today, compared
 * as a calendar date (not a timestamp). Avoids timezone-dependent flapping.
 */
export function isPastDate(iso) {
    if (!iso || typeof iso !== "string") return false;
    const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
    if (!match) return false;
    const today = new Date();
    const todayIso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
    return match[0] < todayIso;
}
