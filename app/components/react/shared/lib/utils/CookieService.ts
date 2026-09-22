// CookieService.ts
class CookieService {
    private static decodeQuotedCookieValue(value: string): string {
        const trimmed = value.trim();
        const unquoted = (
            trimmed.startsWith('"') && trimmed.endsWith('"')
                ? trimmed.slice(1, -1)
                : trimmed
        );

        return unquoted.replace(/\\([0-3][0-7][0-7]|["\\])/g, (_match, group: string) => {
            if (group === '"' || group === '\\') {
                return group;
            }
            return String.fromCharCode(Number.parseInt(group, 8));
        });
    }

    // Get a cookie by name with a type-safe return
    static getCookie(cookieName: string): string | null {
        const name = `${cookieName}=`;
        const cookieArray = document.cookie.split(';');
        for (let i = 0; i < cookieArray.length; i += 1) {
            const cookie = cookieArray[i].trim();
            if (cookie.startsWith(name)) {
                return cookie.substring(name.length, cookie.length);
            }
        }
        return null;
    }

    static getCookieValueJson<T>(name: string): T | null {
        const cookieValue = this.getCookie(name);
        if (!cookieValue) {
            return null;
        }

        const tryParse = (value: string): T | null => {
            const normalized = value.startsWith('j:') ? value.slice(2) : value;
            const decodedQuoted = this.decodeQuotedCookieValue(normalized);

            try {
                const parsed = JSON.parse(decodedQuoted) as unknown;
                if (typeof parsed === 'string') {
                    return JSON.parse(parsed) as T;
                }
                return parsed as T;
            } catch {
                return null;
            }
        };

        const direct = tryParse(cookieValue);
        if (direct !== null) {
            return direct;
        }

        try {
            return tryParse(decodeURIComponent(cookieValue));
        } catch {
            return null;
        }
    }

    // Set a cookie with expiration time in days
    static setCookie(name: string, value: string, days: number): void {
        let expires = '';
        if (days) {
            const date = new Date();
            date.setTime(date.getTime() + days * 24 * 60 * 60 * 1000);
            expires = `; expires=${date.toUTCString()}`;
        }
        document.cookie = `${name}=${value || ''}${expires}; path=/`;
    }

    // Delete a cookie by setting max age to a negative value
    static deleteCookie(name: string): void {
        document.cookie = `${name}=; Max-Age=-99999999;`;
    }
}

export default CookieService;
