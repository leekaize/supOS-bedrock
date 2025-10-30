/**
 * Robust API client with automatic retry and auth handling
 */

import { message } from 'antd';
import { API_BASE } from '../config';

class AuthAPI {
    constructor() {
        this.maxRetries = 2;
        this.isRefreshing = false;
        this.refreshPromise = null;
    }

    async checkAuth() {
        try {
            const res = await fetch(`${API_BASE}/auth/status`, {
                credentials: 'include'
            });
            const data = await res.json();
            return data.authenticated;
        } catch {
            return false;
        }
    }

    async handleUnauthorized() {
        if (this.isRefreshing) {
            return this.refreshPromise;
        }

        this.isRefreshing = true;
        this.refreshPromise = (async () => {
            try {
                const isAuth = await this.checkAuth();
                if (!isAuth) {
                    window.location.href = '/login';
                    return false;
                }
                return true;
            } finally {
                this.isRefreshing = false;
                this.refreshPromise = null;
            }
        })();

        return this.refreshPromise;
    }

    async fetchWithRetry(url, options = {}, attempt = 0) {
        const fullUrl = url.startsWith('http') ? url : `${API_BASE}${url}`;

        try {
            const res = await fetch(fullUrl, {
                ...options,
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            });

            if (res.status === 401) {
                if (attempt < this.maxRetries) {
                    const refreshed = await this.handleUnauthorized();
                    if (refreshed) {
                        return this.fetchWithRetry(url, options, attempt + 1);
                    }
                }
                throw new Error('Authentication required');
            }

            if (res.status === 500) {
                const errorData = await res.json().catch(() => ({}));
                throw new Error(errorData.error || 'Server error');
            }

            if (!res.ok) {
                const errorData = await res.json().catch(() => ({}));
                throw new Error(errorData.error || `HTTP ${res.status}`);
            }

            return res;
        } catch (error) {
            if (attempt < this.maxRetries && error.message.includes('fetch')) {
                await new Promise(resolve => setTimeout(resolve, Math.pow(2, attempt) * 500));
                return this.fetchWithRetry(url, options, attempt + 1);
            }

            throw error;
        }
    }

    async get(url) {
        const res = await this.fetchWithRetry(url);
        return res.json();
    }

    async post(url, data) {
        const res = await this.fetchWithRetry(url, {
            method: 'POST',
            body: data ? JSON.stringify(data) : undefined
        });
        return res.json();
    }
}

export const authAPI = new AuthAPI();

export async function authFetch(url, options = {}) {
    try {
        return await authAPI.fetchWithRetry(url, options);
    } catch (error) {
        message.error(error.message);
        throw error;
    }
}
