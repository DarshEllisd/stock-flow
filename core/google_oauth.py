"""
Google sign-in (OAuth 2.0 authorization code flow with PKCE).

Buyers and sellers live in separate tables, so the sign-in page sends the chosen
user_type along; on the callback we find (or create) that kind of account by the
Google-verified email and start the usual session (user_id / user_type / user_name).
"""

import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

from core.views import _get_or_create_wallet, _get_user_model, _login_session


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
SESSION_KEY = "google_oauth"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _redirect_uri(request) -> str:
    return request.build_absolute_uri(reverse("google_callback"))


def _exchange_code(code: str, redirect_uri: str, code_verifier: str) -> dict:
    """Swap the authorization code for tokens at Google's token endpoint."""
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }).encode("utf-8")
    req = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Google token error {e.code}: {error_body}")


def _id_token_claims(id_token: str) -> dict:
    """Decode and check the ID token.

    The token comes straight from Google's token endpoint over TLS, so (per OpenID
    Connect Core 3.1.3.7) we validate its claims rather than its signature.
    """
    try:
        payload = id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        raise RuntimeError("Malformed ID token from Google.")

    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise RuntimeError("ID token was not issued by Google.")
    if claims.get("aud") != settings.GOOGLE_CLIENT_ID:
        raise RuntimeError("ID token was issued for a different app.")
    if int(claims.get("exp", 0)) < time.time():
        raise RuntimeError("ID token has expired.")
    return claims


def google_login(request):
    user_type = request.GET.get("user_type", "").strip().lower()
    if not _get_user_model(user_type):
        messages.error(request, "Please choose whether you are signing in as a buyer or a seller.")
        return redirect("signin_page")

    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        messages.error(request, "Google sign-in is not configured yet.")
        return redirect("signin_page")

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    request.session[SESSION_KEY] = {
        "state": state,
        "code_verifier": code_verifier,
        "user_type": user_type,
    }

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": _redirect_uri(request),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": _b64url(hashlib.sha256(code_verifier.encode("ascii")).digest()),
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return redirect(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}")


def google_callback(request):
    # One-time use: whatever happens below, this login attempt is consumed.
    pending = request.session.pop(SESSION_KEY, None)

    if request.GET.get("error"):
        messages.error(request, "Google sign-in was cancelled.")
        return redirect("signin_page")

    code = request.GET.get("code", "")
    state = request.GET.get("state", "")
    if not pending or not code or not secrets.compare_digest(state, pending.get("state", "")):
        messages.error(request, "Your sign-in session expired. Please try again.")
        return redirect("signin_page")

    try:
        tokens = _exchange_code(code, _redirect_uri(request), pending["code_verifier"])
        claims = _id_token_claims(tokens.get("id_token", ""))
    except RuntimeError:
        messages.error(request, "Could not complete Google sign-in. Please try again.")
        return redirect("signin_page")

    email = str(claims.get("email", "")).strip().lower()
    if not email or not claims.get("email_verified"):
        messages.error(request, "Your Google account email is not verified.")
        return redirect("signin_page")

    user_type = pending["user_type"]
    user_model = _get_user_model(user_type)
    user = user_model.objects.filter(email=email).first()
    if user:
        messages.success(request, f"Welcome back, {user.name}!")
    else:
        name = str(claims.get("name") or email.split("@")[0]).strip()[:255]
        user = user_model.objects.create(name=name, email=email)
        _get_or_create_wallet(user)
        messages.success(request, f"Welcome to StockFlow, {user.name}!")

    _login_session(request, user, user_type)
    return redirect("home")
