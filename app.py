import hashlib
import os
import re

import requests
from flask import Flask, jsonify, redirect, request, session

app = Flask(__name__, static_folder="static", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "change-me-en-production")

FREE_LIMIT = 2   # analyses gratuites
PACK_SIZE = 5    # analyses obtenues pour 500 FCFA
SASPAY_API = "https://api.saspay.me/api/v1"
SASPAY_API_KEY = os.environ.get("SASPAY_API_KEY", "")  # clé secrète sk_live_... (jamais dans le navigateur)
SITE_URL = os.environ.get("SITE_URL", "http://localhost:5000").rstrip("/")  # adresse publique de ton site
PRICE, CURRENCY = "500.00", "XOF"
CREDITED_FILE = os.path.join(os.path.dirname(__file__), "credited_ids.txt")

HOT = ["budget", "finance", "dashboard", "ai", "ia", "chatgpt", "freelance", "business",
       "tiktok", "instagram", "fitness", "crypto", "trading", "notion", "etsy", "amazon",
       "side hustle", "passive", "argent", "money", "productivity", "planner", "tracker",
       "entrepreneur", "marketing", "seo", "debt", "savings", "épargne", "tontine"]
SATURATED = ["ebook", "e-book", "guide", "planner", "template", "checklist", "journal",
             "course", "masterclass", "bundle"]
BENEFIT = ["pour", "for", "sans", "without", "en 7", "in 7", "jours", "days", "step",
           "étape", "complete", "ultimate", "simple", "fast", "rapide", "cheat", "playbook",
           "système", "system"]


def clamp(n):
    return max(5, min(97, round(n)))


def analyse(title, fmt):
    t = title.lower()
    words = t.split()
    j = int(hashlib.md5(t.encode()).hexdigest(), 16) % 9 - 4
    hot = sum(1 for k in HOT if k in t)
    sat = sum(1 for k in SATURATED if k in t)
    ben = sum(1 for k in BENEFIT if k in t)
    has_digit = bool(re.search(r"\d", t))

    demand = clamp(35 + hot * 14 + (8 if fmt in ("sheet", "tpl") else 0) + j)
    compet = clamp(30 + hot * 9 + sat * 10 + (10 if fmt == "pdf" else 0)
                   - max(0, len(words) - 5) * 5 + j)
    clarity = clamp(25 + min(len(words), 9) * 5 + ben * 9 + (10 if has_digit else 0)
                    + (-20 if len(words) > 14 else 0) + (-25 if len(words) < 3 else 0))
    uniq = clamp(100 - compet + (10 if len(words) >= 6 else 0) + (5 if ben > 1 else 0))
    score = clamp(demand * 0.35 + (100 - compet) * 0.25 + clarity * 0.25 + uniq * 0.15)

    tips = []
    if len(words) < 5:
        tips.append("Allonge ton titre : précise la cible et le résultat promis.")
    if not has_digit:
        tips.append("Ajoute un chiffre ou une durée (ex : « en 7 jours »).")
    if compet > 65:
        tips.append("Niche très encombrée : vise un sous-public (étudiants, freelances, mamans…).")
    if hot == 0:
        tips.append("Ajoute un mot-clé que les gens cherchent vraiment (budget, IA, business…).")
    if not tips:
        tips.append("Bon titre ! Teste-le avec une vignette claire et 5 mots-clés SEO.")

    return {
        "score": score,
        "bars": [["Demande du marché", demand], ["Faible concurrence", 100 - compet],
                 ["Clarté du titre", clarity], ["Différenciation", uniq]],
        "tips": tips,
    }


def credits():
    used, paid = session.get("used", 0), session.get("paid", 0)
    return {"free": max(0, FREE_LIMIT - used), "paid": paid}


@app.route("/")
def home():
    return app.send_static_file("index.html")


@app.get("/api/credits")
def get_credits():
    return jsonify(credits())


@app.post("/api/analyse")
def api_analyse():
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()[:120]
    if len(title) < 3:
        return jsonify({"error": "Titre trop court"}), 400
    c = credits()
    if c["free"] + c["paid"] <= 0:
        return jsonify({"error": "Crédits épuisés", "credits": c}), 402
    if c["free"] > 0:
        session["used"] = session.get("used", 0) + 1
    else:
        session["paid"] = session.get("paid", 0) - 1
    result = analyse(title, data.get("fmt", "other"))
    result["credits"] = credits()
    return jsonify(result)


def saspay(method, path, **kw):
    r = requests.request(method, SASPAY_API + path, timeout=20,
                         headers={"Authorization": "Bearer " + SASPAY_API_KEY}, **kw)
    try:
        body = r.json()
    except ValueError:
        body = {}
    return r.status_code, (body.get("data", body) if isinstance(body, dict) else {})


def error_text(d):
    """Extrait le message d'erreur renvoyé par SasPay (sans jamais afficher la clé)."""
    e = d.get("error") if isinstance(d, dict) else None
    while isinstance(e, dict) and "error" in e:
        e = e["error"]
    if isinstance(e, dict):
        e = e.get("message") or e.get("detail") or e.get("code")
    return str(e or (d.get("message") or d.get("detail") if isinstance(d, dict) else "") or "pas de détail")[:200]


def already_credited(cid):
    try:
        with open(CREDITED_FILE, encoding="utf-8") as f:
            return cid in f.read().split()
    except FileNotFoundError:
        return False


@app.post("/api/checkout")
def api_checkout():
    """Crée une page de paiement SasPay et renvoie son adresse."""
    if not SASPAY_API_KEY:
        return jsonify({"error": "la variable SASPAY_API_KEY est absente sur Render"}), 500
    try:
        status, d = saspay("POST", "/checkout-sessions/", json={
            "amount": PRICE, "currency": CURRENCY,
            "description": "SellScore : %d analyses" % PACK_SIZE,
            "return_url": SITE_URL + "/paid",
        })
    except requests.RequestException as e:
        return jsonify({"error": "SasPay injoignable (%s)" % type(e).__name__}), 502
    if status not in (200, 201) or not d.get("checkout_url"):
        return jsonify({"error": "SasPay a répondu %s : %s" % (status, error_text(d))}), 502
    session["checkout_id"] = d["id"]
    return jsonify({"checkout_url": d["checkout_url"]})


@app.get("/paid")
def paid():
    """Le client revient ici après paiement : on revérifie auprès de SasPay avant de créditer."""
    cid, ok = session.get("checkout_id"), False
    if cid and not already_credited(cid):
        try:
            status, d = saspay("GET", "/checkout-sessions/%s/status/" % cid)
            ok = status == 200 and (d.get("status") == "PAID" or d.get("transaction_status") == "SUCCESS")
        except requests.RequestException:
            ok = False
        if ok:
            with open(CREDITED_FILE, "a", encoding="utf-8") as f:
                f.write(cid + "\n")
            session.pop("checkout_id", None)
            session["paid"] = session.get("paid", 0) + PACK_SIZE
    return redirect("/?pay=ok" if ok else "/?pay=no")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
