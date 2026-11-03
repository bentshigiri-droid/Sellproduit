import hashlib
import os
import re

from flask import Flask, jsonify, redirect, request, session

app = Flask(__name__, static_folder="static", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "change-me-en-production")

FREE_LIMIT = 2   # analyses gratuites
PACK_SIZE = 5    # analyses obtenues pour 500 FCFA
PAYMENT_LINK = os.environ.get("PAYMENT_LINK", "https://REMPLACE-PAR-TON-LIEN-DE-PAIEMENT")
CODES_FILE = os.path.join(os.path.dirname(__file__), "codes.txt")

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


@app.get("/pay")
def pay():
    return redirect(PAYMENT_LINK)


@app.post("/api/redeem")
def redeem():
    """Après paiement, tu envoies un code au client ; il le saisit ici pour obtenir 5 analyses."""
    code = str((request.get_json(silent=True) or {}).get("code", "")).strip().upper()
    try:
        with open(CODES_FILE, encoding="utf-8") as f:
            codes = [line.strip().upper() for line in f if line.strip()]
    except FileNotFoundError:
        codes = []
    if not code or code not in codes:
        return jsonify({"error": "Code invalide ou déjà utilisé", "credits": credits()}), 400
    codes.remove(code)  # un code = une utilisation
    with open(CODES_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(codes) + ("\n" if codes else ""))
    session["paid"] = session.get("paid", 0) + PACK_SIZE
    return jsonify({"ok": True, "credits": credits()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
