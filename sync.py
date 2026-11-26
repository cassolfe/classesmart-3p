import os
import re
import requests
from datetime import datetime, timedelta

# --- 1. CREDENZIALI LETTE DAL CLOUD (GITHUB SECRETS) ---
CV_USER = os.environ.get("CV_USER")
CV_PASS = os.environ.get("CV_PASS")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
# --- 2. ORARIO SETTIMANALE 3P ---
# Giorni: 0=Lunedi, 1=Martedi, 2=Mercoledi, 3=Giovedi, 4=Venerdi, 5=Sabato
ORARIO_CLASSE = {
    "ITALIANO": [0, 2, 3],
    "LETTERATURA": [0, 2, 3],
    "LATINO": [4],
    "INGLESE": [0, 1, 3, 5],
    "STRANIERA": [0, 1, 3, 5],
    "FRANCESE": [1, 2, 3],
    "STORIA": [1, 2],
    "FILOSOFIA": [0, 2, 3],
    "MATEMATICA": [0, 1, 4, 5],
    "FISICA": [0, 5],
    "SCIENZE": [0, 1, 2],
    "NATURALI": [0, 1, 2],
    "ARTE": [1, 2],
    "DISEGNO": [1, 2],
    "MOTORIE": [4],
    "FISICA_ED": [4],
    "RELIGIONE": [3],
    "CATTOLICA": [3]
}

PAROLE_CHIAVE_COMPITI = [
    r"\beserciz[io]\b", r"\bes\.", r"\bpag\.", r"\bpp\.", r"\bpagina\b",
    r"\bstudiare\b", r"\bstudia\b", r"\bripassare\b", r"\bripasso\b",
    r"\bleggere\b", r"\blettura\b", r"\btradurre\b", r"\bversione\b",
    r"\bcompit[io]\b", r"\bper casa\b", r"\bscheda\b", r"\bproblemi\b"
]

PAROLE_CHIAVE_VERIFICHE = [
    r"\bverific[ah]\b", r"\bcompito in classe\b", r"\btest\b",
    r"\binterrogazion[ei]\b", r"\bprova scritta\b", r"\bprova orale\b"
]
# ---------------------------------

BASE_CV = "https://web.spaggiari.eu/rest/v1"
HEADERS_CV = {
    "User-Agent": "CVVS/std/4.1.7 Android/10",
    "Z-Dev-Apikey": "Tg1NWEwNGIgIC0K"
}

def estrai_solo_compito(testo):
    if not testo:
        return None
    
    # 1. Cerca se c'e una sezione esplicita tipo "Per casa:", "Compiti:", "Esercizi:"
    match_esplicito = re.search(
        r"(?:per\s+casa|compit[io]|eserciz[io]|per\s+la\s+prossima\s+volta|per\s+luned[iì]|per\s+marted[iì]|per\s+mercoled[iì]|per\s+gioved[iì]|per\s+venerd[iì]|per\s+sabato)\s*[:\-]?\s*(.+)$",
        testo,
        re.IGNORECASE | re.DOTALL
    )
    if match_esplicito:
        estratto = match_esplicito.group(0).strip()
        if len(estratto) > 4:
            return estratto[0].upper() + estratto[1:]

    # 2. Altrimenti divide la lezione in singole frasi (su punto, punto e virgola o a capo)
    # e tiene SOLO le frasi che contengono parole da compito
    frasi = re.split(r'(?<=[.;!\n])\s+', testo.strip())
    frasi_compito = [
        f.strip() for f in frasi
        if any(re.search(p, f.lower()) for p in PAROLE_CHIAVE_COMPITI)
    ]

    if frasi_compito:
        risultato = " ".join(frasi_compito)
        return risultato[0].upper() + risultato[1:]

    return None

def is_vera_verifica(testo):
    if not testo:
        return False
    t = testo.lower()
    return any(re.search(p, t) for p in PAROLE_CHIAVE_VERIFICHE)

def trova_giorni_materia(materia_cv):
    m = materia_cv.upper()
    if "EDUCAZIONE FISICA" in m or "SCIENZE MOTORIE" in m:
        return [4]
    if "STORIA DELL'ARTE" in m or "DISEGNO" in m or "ARTE" in m:
        return [1, 2]
    for chiave, giorni in ORARIO_CLASSE.items():
        if chiave in m:
            return giorni
    return None

def calcola_scadenza(data_lezione_str, materia_cv, testo_argomento):
    data_lez = datetime.strptime(data_lezione_str, "%Y-%m-%d")
    testo_lower = testo_argomento.lower()
    
    giorni_nomi = {
        "luned": 0, "marted": 1, "mercoled": 2,
        "gioved": 3, "venerd": 4, "sabato": 5
    }
    for prefisso, num_giorno in giorni_nomi.items():
        if f"per {prefisso}" in testo_lower or f"di {prefisso}" in testo_lower:
            for offset in range(1, 8):
                cand = data_lez + timedelta(days=offset)
                if cand.weekday() == num_giorno:
                    return cand.strftime("%Y-%m-%d")

    giorni_materia = trova_giorni_materia(materia_cv)
    if giorni_materia:
        for offset in range(1, 8):
            cand = data_lez + timedelta(days=offset)
            if cand.weekday() in giorni_materia:
                return cand.strftime("%Y-%m-%d")

    prossima = data_lez + timedelta(days=2)
    if prossima.weekday() == 6:
        prossima += timedelta(days=1)
    return prossima.strftime("%Y-%m-%d")

def login_classeviva():
    print("1. Accesso a ClasseViva in corso...")
    url = f"{BASE_CV}/auth/login"
    payload = {"ident": None, "pass": CV_PASS, "uid": CV_USER}
    res = requests.post(url, json=payload, headers=HEADERS_CV, timeout=10)
    if res.status_code != 200:
        raise Exception(f"Errore Login ClasseViva ({res.status_code}): {res.text}")
    data = res.json()
    student_id = ''.join(filter(str.isdigit, data["ident"]))
    print(f"   Accesso riuscito! ID studente: {student_id}")
    return data["token"], student_id

def scarica_e_salva():
    token, student_id = login_classeviva()
    auth_headers = {**HEADERS_CV, "Z-Auth-Token": token}
    
    oggi = datetime.now()
    inizio = (oggi - timedelta(days=7)).strftime("%Y%m%d")
    fine = (oggi + timedelta(days=30)).strftime("%Y%m%d")

    print("2. Scarico lezioni e agenda...")
    res_lez = requests.get(f"{BASE_CV}/students/{student_id}/lessons/{inizio}/{fine}", headers=auth_headers, timeout=10)
    lezioni = res_lez.json().get("lessons", [])

    res_ag = requests.get(f"{BASE_CV}/students/{student_id}/agenda/all/{inizio}/{fine}", headers=auth_headers, timeout=10)
    agenda = res_ag.json().get("agenda", [])
    print(f"   Trovate {len(lezioni)} lezioni e {len(agenda)} voci in agenda.")

    print("3. Invio lezioni e isolo solo i compiti...")
    sb_headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }

    lista_lezioni = []
    compiti_estratti = []

    for l in lezioni:
        lista_lezioni.append({
            "id": str(l["evtId"]),
            "data": l["evtDate"],
            "materia": l["subjectDesc"],
            "argomento": l["lessonArg"],
            "autore": l.get("authorName", "")
        })

        solo_compito = estrai_solo_compito(l["lessonArg"])
        if solo_compito:
            scadenza = calcola_scadenza(l["evtDate"], l["subjectDesc"], l["lessonArg"])
            # Salviamo solo il compito pulito + l'intera lezione separata dal marcatore |||LEZIONE|||
            descrizione_completa = f"{solo_compito}|||LEZIONE|||{l['evtDate']}|{l['lessonArg']}"
            compiti_estratti.append({
                "id": f"lez_{l['evtId']}",
                "data_scadenza": scadenza,
                "materia": l["subjectDesc"],
                "descrizione": descrizione_completa,
                "tipo": "compito",
                "fonte": "estratto_lezione"
            })

    if lista_lezioni:
        r1 = requests.post(f"{SUPABASE_URL}/rest/v1/lezioni", json=lista_lezioni, headers=sb_headers, timeout=10)
        print(f"   Risposta tabella lezioni: {r1.status_code}")

    lista_compiti = []
    for a in agenda:
        note = a["notes"]
        tipo_voce = "verifica" if is_vera_verifica(note) else "compito"
        lista_compiti.append({
            "id": str(a["evtId"]),
            "data_scadenza": a["evtDatetimeBegin"][:10],
            "materia": a.get("subjectDesc") or "Generale",
            "descrizione": note,
            "tipo": tipo_voce,
            "fonte": "agenda_ufficiale"
        })

    tutti_i_compiti = lista_compiti + compiti_estratti

    if tutti_i_compiti:
        r2 = requests.post(f"{SUPABASE_URL}/rest/v1/compiti", json=tutti_i_compiti, headers=sb_headers, timeout=10)
        print(f"   Risposta tabella compiti: {r2.status_code} (di cui {len(compiti_estratti)} estratti dalle lezioni!)")

    print("4. Sincronizzazione completata con successo!")

if __name__ == "__main__":
    scarica_e_salva()
