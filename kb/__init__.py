"""Knowledge base: diseases, pests, crops, IPM action phrases and UI translations."""
import json
import os

KB_DIR = os.path.dirname(os.path.abspath(__file__))
I18N_DIR = os.path.join(os.path.dirname(KB_DIR), "i18n")
LANGS = {"en": "English", "hi": "हिन्दी", "te": "తెలుగు", "ta": "தமிழ்", "kn": "ಕನ್ನಡ", "mr": "मराठी"}
SPEECH_LANG = {"en": "en-IN", "hi": "hi-IN", "te": "te-IN", "ta": "ta-IN", "kn": "kn-IN", "mr": "mr-IN"}


def _load(name):
    with open(os.path.join(KB_DIR, name), encoding="utf-8") as f:
        return json.load(f)


DISEASES = _load("diseases.json")
PESTS = {k: v for k, v in _load("pests.json").items() if not k.startswith("_")}
CROPS = _load("crops.json")
ACTIONS = _load("actions.json")

UI = {}
for code in LANGS:
    with open(os.path.join(I18N_DIR, f"{code}.json"), encoding="utf-8") as f:
        UI[code] = json.load(f)


def t(key, lang="en", **kw):
    """Translate a UI string; falls back to English, then to the key itself."""
    s = UI.get(lang, {}).get(key) or UI["en"].get(key) or key
    return s.format(**kw) if kw else s


def loc(d, lang):
    """Pick a language from a {en,hi,te,ta,kn,mr} dict."""
    if not isinstance(d, dict):
        return d
    return d.get(lang) or d.get("en") or ""


def disease_name(label, lang="en"):
    d = DISEASES.get(label)
    return loc(d["name"], lang) if d else (label or "")


def crop_name(crop, lang="en"):
    c = CROPS.get(crop)
    return loc(c, lang) if c else (crop or "")


def label_crop(label):
    d = DISEASES.get(label)
    return d.get("crop") if d else None


def full_name(label, lang="en"):
    """'Tomato – Late blight' in the chosen language."""
    d = DISEASES.get(label)
    if not d:
        return label or ""
    if not d.get("crop"):
        return loc(d["name"], lang)
    return f"{crop_name(d['crop'], lang)} – {loc(d['name'], lang)}"


def labels_for_crop(crop):
    return [k for k, v in DISEASES.items() if v.get("crop") == crop]


def action_text(aid, lang, **kw):
    a = ACTIONS.get(aid)
    if not a:
        return aid
    s = loc(a, lang)
    return s.format(**kw) if kw else s


def compose_advisory(label, lang="en", confidence=1.0, include_chemical=True):
    """
    Build an Integrated Pest & Disease Management advisory for a disease/pest label.
    Order follows the IPM hierarchy: cultural -> biological -> chemical (last resort)
    -> safety -> referral -> follow-up.
    """
    d = DISEASES.get(label) or PESTS.get(label)
    if d is None:
        return None
    kind = d.get("type", "pest")
    adv = {
        "label": label,
        "name": full_name(label, lang) if label in DISEASES else loc(d["name"], lang),
        "type": kind,
        "type_text": t("type." + kind, lang),
        "pathogen": d.get("pathogen") or d.get("scientific"),
        "symptoms": d.get("symptoms"),
        "cultural": [], "biological": [], "chemical": [], "safety": [], "referral": [], "followup": [],
        "has_chemical": False,
        "notifiable": bool(d.get("notifiable")),
    }
    if kind == "healthy":
        adv["cultural"] = [action_text("H_CONTINUE", lang), action_text("H_PREVENT", lang)]
        return adv
    if kind == "background":
        return adv

    adv["cultural"] = [action_text(a, lang) for a in d.get("cultural", [])]
    adv["biological"] = [action_text(a, lang) for a in d.get("biological", [])]
    if include_chemical and d.get("chemical"):
        adv["chemical"] = [action_text("S_LAST_RESORT", lang)] + [
            action_text("X_SPRAY", lang, chem=c["chem"], dose=c["dose"], phi=c["phi"]) for c in d["chemical"]
        ]
        adv["safety"] = [action_text(a, lang) for a in ("S_PPE", "S_TIME", "S_LABEL", "S_ROTATE_MOA", "S_CONTAINER")]
        adv["has_chemical"] = True
    if d.get("referral") or confidence < 0.6:
        adv["referral"] = [action_text("R_LAB", lang), action_text("R_EXT", lang)]
    adv["followup"] = [action_text("F_3D" if d.get("spread") == "fast" else "F_7D", lang)]
    return adv


def advisory_speech(adv, lang):
    """Plain text version of an advisory for the browser's text-to-speech."""
    parts = [adv["name"] + "."]
    for sec in ("cultural", "biological", "chemical", "safety", "referral", "followup"):
        parts.extend(adv.get(sec, []))
    return " ".join(parts)
