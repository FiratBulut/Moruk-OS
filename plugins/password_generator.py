"""
Moruk OS - Password Generator Plugin v2
Generiert sichere Passwörter mit Konfigurationsoptionen.
"""

PLUGIN_NAME = "password_generator"
PLUGIN_DESCRIPTION = "Generiert sichere Passwörter mit Konfigurationsoptionen."
PLUGIN_PARAMS = {
    "length": "Passwort-Länge (default: 16)",
    "chars": "Zeichentypen: letters, digits, symbols, all",
    "count": "Anzahl zu generieren (default: 1)",
}

import secrets
import string


def execute(params):
    try:
        length = int(params.get("length", 16))
        chars = params.get("chars", "all")
        count = int(params.get("count", 1))

        if length < 4 or length > 128:
            return {"success": False, "result": "Length must be between 4 and 128"}
        if count < 1 or count > 20:
            return {"success": False, "result": "Count must be between 1 and 20"}

        # Build character pool
        pool = ""
        if chars in ("all", "letters"):
            pool += string.ascii_letters
        if chars in ("all", "digits"):
            pool += string.digits
        if chars in ("all", "symbols"):
            pool += string.punctuation
        if not pool:
            pool = string.ascii_letters + string.digits

        passwords = []
        for _ in range(count):
            # Ensure at least one char from each requested type
            pwd_chars = []
            if chars in ("all", "letters"):
                pwd_chars.append(secrets.choice(string.ascii_uppercase))
                pwd_chars.append(secrets.choice(string.ascii_lowercase))
            if chars in ("all", "digits"):
                pwd_chars.append(secrets.choice(string.digits))
            if chars in ("all", "symbols"):
                pwd_chars.append(secrets.choice(string.punctuation))
            # Fill rest
            remaining = length - len(pwd_chars)
            pwd_chars += [secrets.choice(pool) for _ in range(max(remaining, 0))]
            secrets.SystemRandom().shuffle(pwd_chars)
            passwords.append("".join(pwd_chars[:length]))

        strength = (
            "💪 Strong" if length >= 16 else "🟡 Medium" if length >= 10 else "🔴 Weak"
        )

        lines = [f"🔑 Generated {count} password(s) — {strength}"]
        lines.append(f"Length: {length} | Chars: {chars}")
        lines.append("─" * 40)
        for i, pwd in enumerate(passwords, 1):
            lines.append(f"  {i}. {pwd}")

        return {"success": True, "result": "\n".join(lines), "passwords": passwords}

    except ValueError as e:
        return {"success": False, "result": f"Invalid parameter: {e}"}
    except Exception as e:
        return {"success": False, "result": f"Error: {e}"}
