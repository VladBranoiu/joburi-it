#!/usr/bin/env python3
"""Strânge anunțuri IT (programator / developer, QA / tester, sisteme / rețele / cloud / securitate, date / BI,
IT support / helpdesk) din Brașov, Bacău, Moinești, București + Ilfov și remote, de pe eJobs, BestJobs, OLX, LinkedIn,
EduJobs (+ publi24), posturi.gov.ro, ANOFM și Hipo, caută reputația firmelor (UndeLucram, opțional Google), dă fiecărui
anunț un scor și salvează totul în data/joburi.json + data/joburi.js (citit de index.html).

Rulare: python3 colector.py              (toate sursele + recenzii)
        python3 colector.py ejobs olx    (doar unele surse)
        python3 colector.py recenzii     (doar reîmprospătează recenziile)
Doar biblioteca standard Python + curl.
"""
import html
import json
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CACHE = DATA / "cache"
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
EUR = CFG["curs_eur_ron"]
NOW_DT = datetime.now(timezone.utc)
NOW = NOW_DT.isoformat(timespec="seconds")
ZILE_PASTRARE_EXPIRATE = 30  # anunțurile expirate se șterg după atâtea zile, ca pagina să rămână ușoară


# ---------------------------------------------------------------- utilitare

def fetch(url, as_json=True, retries=2, data=None, headers=(), cookies=None):
    """GET/POST prin curl (OLX blochează clientul HTTP din Python, dar acceptă curl)."""
    cmd = ["curl", "-sS", "-L", "--compressed", "--max-time", "30", "-A", UA,
           "-H", "Accept-Language: ro-RO,ro;q=0.9", "-w", "\n%{http_code}"]
    for h in headers:
        cmd += ["-H", h]
    if cookies:
        cmd += ["-b", str(cookies), "-c", str(cookies)]
    if data is not None:
        cmd += ["-H", "Content-Type: application/json", "--data-binary", json.dumps(data)]
    for incercare in range(retries + 1):
        r = subprocess.run(cmd + [url], capture_output=True, text=True, encoding="utf-8", errors="replace")
        body, _, code = r.stdout.rpartition("\n")
        time.sleep(CFG["pauza_intre_cereri_sec"])
        if r.returncode == 0 and code.startswith("2"):
            return json.loads(body) if as_json else body
        err = f"HTTP {code}" if r.returncode == 0 else r.stderr.strip()
        if incercare == retries:
            raise RuntimeError(f"{err} la {url[:90]}")
        print(f"   ! reîncerc ({err})")
        time.sleep(3)


def fara_diacritice(s, lower=True):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower() if lower else s


def text_din_html(s):
    s = re.sub(r"<(br|/p|/li|/div|li|/h\d)[^>]*>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def repara_codificare(s):
    """„dezvoltÄ soluÈii” (UTF-8 citit ca Latin-1, cum vine de la Hipo) -> „dezvoltă soluții”."""
    for cod in ("latin-1", "cp1252"):
        try:
            return s.encode(cod).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return s


def din_majuscule(s):
    """„REFERENT DE SPECIALITATE” -> „Referent de specialitate” (ANOFM scrie totul cu majuscule)."""
    s = (s or "").strip()
    return s[:1].upper() + s[1:].lower() if s.isupper() else s


def cache_get(key, loader, max_zile=None):
    f = CACHE / (re.sub(r"[^a-zA-Z0-9_-]", "_", key) + ".json")
    if f.exists() and (max_zile is None or time.time() - f.stat().st_mtime < max_zile * 86400):
        return json.loads(f.read_text(encoding="utf-8"))
    val = loader()
    f.write_text(json.dumps(val, ensure_ascii=False), encoding="utf-8")
    return val


def zile_de_la(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (NOW_DT - (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))).days  # „2026-09-23” fără oră
    except (ValueError, AttributeError):
        return None


# ------------------------------------------------------------------ salariu

NET_DIN_BRUT = 0.585  # aproximativ, pentru salarii mici/medii în 2026


def parse_salariu(text):
    """'4000 - 4500 RON' / '750 - 1200 EUR' / '2800 - 3000 €/luna' -> (min, max) în lei net, sau (None, None)."""
    if not text:
        return None, None
    t = text.replace(".", "").replace("\xa0", " ")
    if re.search(r"/\s*(ora|h\b|zi\b)|pe (ora|zi)\b", fara_diacritice(t)):
        return None, None  # plată pe oră / pe zi: nu o putem compara corect
    nums = [int(n.replace(" ", "")) for n in re.findall(r"\d{1,2} \d{3}|\d{3,6}", t)]
    if not nums:
        return None, None
    lo, hi = min(nums[:2]), max(nums[:2])
    eur = bool(re.search(r"eur|€", t, re.I))
    if not eur and not re.search(r"ron|lei", t, re.I) and hi < 1800:
        eur = True  # fără monedă și sumă mică: aproape sigur EUR
    k = EUR if eur else 1
    if re.search(r"brut", t, re.I):
        k *= NET_DIN_BRUT
    lo, hi = round(lo * k), round(hi * k)
    if hi < 2000 or lo > 70000:  # sub salariul minim net sau absurd -> probabil altceva (bonus, diurnă)
        return None, None
    return lo, hi


RE_SAL_DESC = re.compile(
    r"(salari\w*|venit\w*|castig\w*|remunera\w*|oferim|pachet salarial)[^\n]{0,50}?"
    r"(\d{1,2}[. ]?\d{3})(\s*(-|–|pana la|si)\s*(\d{1,2}[. ]?\d{3}))?\s*(lei|ron|euro|eur|€)[^\n]{0,12}")


def salariu_din_descriere(desc):
    m = RE_SAL_DESC.search(fara_diacritice(desc))
    if not m:
        return None, None, ""
    return (*parse_salariu(m.group(0)), m.group(0).strip()[:80])


# ----------------------------------------------------------- clasificare
# Toate regulile lucrează pe text fără diacritice, cu litere mici.

# --- ce post e; titlul se verifică pe bucăți („Tehnician IT / Helpdesk”: fiecare bucată e un post)
TEH = (r"(java|python|\.net|dotnet|c#|c\+\+|javascript|typescript|\bjs\b|react|angular|vue(\.?js)?|node(\.?js)?|php|"
       r"laravel|symfony|golang|\bgo\b|rust|ruby|rails|scala|kotlin|swift|flutter|xamarin|django|spring|salesforce|"
       r"abap|odoo|wordpress|magento|shopify|front[- ]?end|back[- ]?end|full[- ]?stack|\bweb\b|mobile|android|\bios\b|"
       r"embedded|firmware|unity|unreal|\brpa\b|uipath|power ?apps|sharepoint|dynamics|cobol|pl/?sql|perl|elixir|"
       r"dart|software)")
RE_DEV = re.compile(
    r"\bdevelop(er|ers)\b|\bdev\b|dezvoltator\w*|programator\w*|programmer\w*|\bcoder\b|"
    r"software (engineer|developer|architect|programmer|development)|inginer\w* (de )?(dezvoltare )?(software|programare|aplicatii)|"
    + TEH + r"\s+(\w+\s+)?(engine\w*|developer|dev|programmer|programator|specialist|expert|architect|consultant)\b|"
    r"(engineer|inginer\w*|lead|expert|specialist) (\w+ )?" + TEH)
RE_QA = re.compile(r"\btester\w*|(engineer|developer) in test|\btestare\b|\btesting\b|test automation|automation (tester|qa|test\w*)|software test\w*|"
                   r"\bqa (automation|manual|tester|software|web|mobile)|(manual|automation|software) qa\b|\bsdet\b|"
                   r"quality assurance (automation|software|tester)|testare (software|automata|manuala|aplicatii)")
RE_DATE = re.compile(r"\b(it|technical) business analyst|\bdata( (&|and) \w+)? (analyst|engineer|scientist|architect|"
                     r"specialist|modeler|steward|developer|ops|expert)\b|"
                     r"analist\w* (de )?date|\bbi (\w+ )?(developer|analyst|engineer|specialist|consultant|expert)|"
                     r"business intelligence|power ?bi|tableau|\betl\b|\bdwh\b|data warehouse|\bdba\b|"
                     r"database (administrator|developer|engineer|specialist)|(administrator|specialist) (de )?baze? de date|"
                     r"\bsql (developer|specialist|engineer)|machine learning|\bml (engineer|ops)|mlops|"
                     r"\bai (engineer|developer|specialist)|big data|analytics engineer|\bdata & analytics")
RE_INFRA = re.compile(
    r"devops|\bsre\b|site reliability|cloud (engineer|architect|specialist|administrator|ops|support|consultant)|"
    r"\b(aws|azure|gcp|kubernetes|linux|windows|vmware|citrix|m365|office 365) (\w+ )?(engineer|administrator|admin|"
    r"specialist|architect|expert|consultant)|sysadmin|system\w* administrator|admin\w* (de )?(sistem\w*|retea|retele|"
    r"it|server\w*|linux|windows|infrastructur\w*|network)|network (engineer|administrator|specialist|technician|"
    r"architect|admin)|inginer\w* (de )?(retea|retele|sistem\w*)|infrastructur\w* (it|engineer|specialist|administrator)|"
    r"(it|ict) infrastructur\w*|platform engineer|cyber\w*|securitat\w* (a )?informati\w*|identity (& |and )?access|"
    r"security (system )?admin\w*|system\w* admin\b|"
    r"network (and |& )?(security )?(design )?(expert|engineer|architect)|securitate (a )?(cibernetica|informatica|it|sistemelor)|"
    r"(information|it|cloud|network|application|security) security|security (engineer|analyst|specialist|architect|"
    r"administrator|consultant|operations)|\bsoc (analyst|engineer|specialist)|\bnoc\b|penetration|pentest\w*|"
    r"middleware|mainframe|release engineer|build engineer|it operations|virtualiz\w*")
RE_SUPORT = re.compile(
    r"\bit support|support (it|informatic)|suport (it|informatic)|help ?desk|service ?desk|desktop support|"
    r"(it|technical|tehnic) (customer )?support|suport tehnic|application support|suport aplicatii|"
    r"(end[- ]?user|field|onsite|on[- ]site|deskside) support|tehnician\w* (\w+ )?(it|calculatoare|pc|retea|retele|"
    r"hardware|sisteme de calcul|echipamente de calcul|suport)|informatician\w*|\binformati(c|q)\w*|"
    r"operator\w* calculator\w* electronic|\b(it|ict)\b|calculatoare|computer|hardware")
# titluri care pot fi și altceva („QA Engineer” la o fabrică, „System Engineer” la aeronave, „Technical Support”
# pentru utilaje): intră doar dacă textul anunțului vorbește de IT
RE_AMBIGUU = {"qa": re.compile(r"\bqa\b|quality assurance|test (engineer|specialist|analyst)|inginer\w* (de )?test\w*"),
              "infra": re.compile(r"system\w* engineer|inginer\w* (de )?sistem\w*|solutions? engineer|"
                                  r"integration engineer|security (officer|specialist)"),
              "date": re.compile(r"business analyst|analist (de )?business|system\w* analyst|analist (de )?sistem\w*|"
                                 r"data analyst")}
RE_IT_IN_TEXT = re.compile(r"software|\bit\b|calculatoare|\bretea\b|retele|network|server\w*|windows|linux|cloud|"
                           r"programare|programming|\bapi\b|\bsql\b|jira|selenium|cypress|postman|cod(ul)? sursa|"
                           r"source code|helpdesk|ticket\w*|active directory|office 365|microsoft 365|hardware|devops|"
                           r"test cases|cazuri de test|python|java|javascript|\.net|agile|scrum|aplicatii (web|mobile|"
                           r"software)|web applications?|erp|database|baze de date")
# vânzări, recrutare, marketing, design, profesori, achiziții de IT: au „IT” în titlu, dar nu sunt posturi IT
RE_EXCLUS_TITLU = re.compile(
    r"recrut\w*|recruit\w*|talent acquisition|sourcer|\bhr\b|resurse umane|\bsales\b|vanzari|vanzator\w*|"
    r"account (manager|executive)|key account|business develop\w*|pre[- ]?sales?|marketing|\bseo\b|social media|"
    r"copywrit\w*|content|graphic|grafic\w*|designer\w*|\bux\b|\bui\b|achizit\w*|procurement|buyer|purchas\w*|"
    r"audit\w*|legal|juridic\w*|avocat\w*|profesor\w*|teacher|educator\w*|trainer|formator|lector\w*|invatator\w*|"
    r"translator|traducator\w*|call center|(customer|client\w*) (service|care|support|success)|relatii (cu )?clienti|"
    r"real estate|imobiliar\w*|(product|recipe|food|culinary|textile|fashion|packaging|formula\w*|cosmetic\w*) "
    r"develop\w*|develop\w* (de )?produs\w*|consultant\w* (sap|erp|crm|functional)|functional consultant|"
    r"(sap|erp|crm) (\w+ )?consultant|\boperator\w* (de )?(introducere|date|call|productie)|data entry|"
    r"(scrum master|product owner|project manager|manager de proiect|delivery manager)|"
    r"\boperator\w*(?! calculator\w* electronic)(?! suport tehnic)|"
    r"retel\w* (\w+ )?(electric\w*|hidraul\w*|termic\w*|gaz\w*|apa|canal\w*|telecomunicatii)")
# „Programator CNC”, „Programator mașini cu comandă numerică”, „Programator PLC / automatizări”: altă meserie
RE_EXCLUS_PROGRAMATOR = re.compile(r"\bcnc\b|strung\w*|freza\w*|frezor\w*|masin\w*|unelte|comanda numerica|"
                                   r"electroeroziune|sudur\w*|welding|robot\w*|\bplc\b|automatiz\w*|automation engineer|"
                                   r"productie|production|programari|programarilor|lucrari|croitor\w*|\bcad\b|\bcam\b")
# muncă fizică, vânzări pe teren sau „joburi” de antrenat AI: scot tot anunțul, chiar dacă o bucată sună bine
RE_EXCLUS_TOT_TITLUL = re.compile(
    r"muncitor\w*|manipulant\w*|stivuitor\w*|\bpicker|\bpacker|ambalator\w*|sortator\w*|\bhamal|"
    r"\bsofer\w*|\bdriver\b(?! develop)|\bcurier\w*|\bcourier|livrator\w*|ospatar\w*|bucatar\w*|barista|"
    r"femeie de serviciu|ingrijitor\w*|\bpaznic|agent de (paza|securitate)|necalificat\w*|area sales|"
    r"sales (manager|representative|rep|agent|executive)|(agent|reprezentant|consilier|consultant|director)\w* "
    r"(de )?vanzari|key account|business development|casier\w*|lucrator\w* comercial|"
    r"\bcnc\b|strung\w*|comanda numerica|\bmmc\b|\bplc\b|electroeroziune|imobiliar\w*|real estate|"
    r"electrician\w*|montaj\w*|instalat\w*|sisteme de securitate|\bcctv\b|incendiu|alarm\w*|"
    r"trainer|profesor\w*|meditati\w*|inginer\w* (de )?vanzari|solicit\w* (un )?(angajare|loc|job|post)|"
    r"\bofer (servicii|serviciile|meditatii|ajutor)|"
    r"contributor|annotat\w*|ai trainer|ai tutor|ai training|(train|training|evaluate|evaluating) (ai|llm)|"
    r"\brater\b|data label\w*|outlier|transcri\w*|mystery|"
    r"^\W*caut (un |o )?(loc de munca|job|serviciu|de lucru)")
# „Contabil intern” e contabil angajat al firmei, nu stagiar; doar „internship”, „student” și „practică” sunt stagii
RE_INTERNSHIP = re.compile(r"internship|summer intern|intern program|\bstudent\w*|stagiu de practica|\bpractica\b|"
                           r"(software|developer|development|it|qa|testing|devops|cloud|data|security|network|support|"
                           r"engineering|web|java|python|\.net|frontend|backend) interns?\b|[-–(]\s*interns?\b|"
                           r"^\W*interns?\b")
# „Tehnician IT / Helpdesk”, „Programator, Analist programator”: fiecare bucată e alt post
RE_BUCATI_TITLU = re.compile(r"\s*[,;/|()]\s*|\s+[-–—]\s+|\s+(?:si|sau|or|and)\s+")
# post la stat cu titlu general („Referent de specialitate gradul III”): îl recunoaștem după compartiment
RE_COMPARTIMENT = re.compile(
    r"(compartiment\w*|serviciu\w*|birou\w*|directi\w*|departament\w*|biroului|serviciului)\s+(\w+[\s-]+){0,2}?"
    r"(informatic\w*|\bit\b|tehnologia informatiei|\btic\b|\bit&c\b|sisteme informatice|comunicatii)")

TIPURI = ("qa", "date", "infra", "dev", "suport")  # la egalitate câștigă primul (Data Engineer -> date, nu dev)
RE_TIP = {"qa": RE_QA, "date": RE_DATE, "infra": RE_INFRA, "dev": RE_DEV, "suport": RE_SUPORT}


def text_e_it(desc):
    """Textul anunțului vorbește de IT (cel puțin două cuvinte diferite: „server”, „Windows”, „tichete”…)."""
    return len({m.group(0) for m in RE_IT_IN_TEXT.finditer(desc)}) >= 2


def categorii_bucata(b, desc=None):
    """Ce fel de post IT e o bucată de titlu (poate fi și nimic). Cu `desc`, titlurile care pot fi și altă meserie
    („QA Engineer”, „System Engineer”) trec doar dacă textul e despre IT; fără text (la căutare) trec deocamdată."""
    if RE_EXCLUS_TITLU.search(b):
        return []
    for c in TIPURI:
        m = RE_TIP[c].search(b)
        if m and not (re.search(r"programator|programmer|\bdev", m.group(0)) and RE_EXCLUS_PROGRAMATOR.search(b)):
            return [c]
    for c, rx in RE_AMBIGUU.items():
        if rx.search(b):
            return [c] if desc is None or text_e_it(desc) else []
    m = RE_COMPARTIMENT.search(b)
    if m:
        return ["suport"]
    return []


def bucati_titlu(titlu):
    return [b for b in RE_BUCATI_TITLU.split(fara_diacritice(titlu)) if b and b.strip()]


def e_job_potrivit(titlu, desc=None):
    """Titlul cere un post IT: programator / developer, QA, sisteme și rețele, date, IT support
    (nu vânzări de IT, recrutori, programator CNC, profesor de informatică…)."""
    if RE_EXCLUS_TOT_TITLUL.search(fara_diacritice(titlu)):
        return False
    d = fara_diacritice(desc) if desc is not None else None
    return any(categorii_bucata(b, d) for b in bucati_titlu(titlu))


RE_TITLU_GENERAL = re.compile(r"^\W*((oferta|anunt) (de )?)?(loc(uri)? de munca|angaj\w*|job\w*|post\w* vacant\w*|"
                              r"recrut\w*|cautam|hiring)( (urgent|personal|colegi?|colega|oameni|in|brasov|bacau|"
                              r"bucuresti|moinesti|acum|part[- ]time|full[- ]time|nou|noi))*\W*$")
# „Angajăm tehnician IT cu experiență…”, „căutăm un coleg pe postul de programator”: meseria din prima parte a textului
RE_ROL_IN_TEXT = re.compile(r"\b(angaj\w*|cautam|recrutam|selectam)\s+(un |o |doi |doua |urgent )?(coleg\w* |persoan\w* )?"
                            r"((pe )?(post(ul)?|pozitia) de |pentru (postul|pozitia) de )?(?P<rol>[\w#+.-]+( [\w#+.-]+){0,3})")


def e_job_potrivit_sau_text(titlu, desc):
    """Pentru anunțurile mici cu titlu general („Ofertă loc de muncă”), meseria e în text: „Angajăm programator…”."""
    if e_job_potrivit(titlu, desc):
        return True
    if not RE_TITLU_GENERAL.search(fara_diacritice(titlu).strip()):
        return False
    m = RE_ROL_IN_TEXT.search(fara_diacritice(desc or "")[:600])
    return bool(m) and e_job_potrivit(m.group("rol"), desc)


def tip_post(titlu, desc=""):
    """dev / qa / infra / date / suport; dacă titlul e general („Concurs posturi vacante”), ne uităm în text."""
    numar = {}
    for b in bucati_titlu(titlu):
        for c in categorii_bucata(b):
            numar[c] = numar.get(c, 0) + 1
    if not numar:
        m = RE_FUNCTIE_DESC.search(fara_diacritice(desc))
        for c in categorii_bucata(m.group(0)) if m else []:
            numar[c] = numar.get(c, 0) + 1
    return max(TIPURI, key=lambda c: (numar.get(c, 0), -TIPURI.index(c))) if numar else "suport"


# --- nivelul postului
RE_CONDUCERE = re.compile(r"\bdirector\w*|\bdirectoare\b|\bhead\b|\bsef\w*|\bcto\b|\bcio\b|\bciso\b|\bchief\b|"
                          r"\bvp\b|vice president|\bmanager\w*|team lead\w*|teamlead\w*|"
                          r"\blider\w*|\bleader\w*|supervisor\w*|coordonator (de )?echipa|"
                          r"team coordinator|engineering manager")
RE_CONDUCERE_OK = re.compile(r"product manager")  # nu conduc oameni
RE_SENIOR = re.compile(r"\bsenior\b|\bsr\b\.?|\bexperienced\b|\bexpert\b|cu experienta|\blead\b|\bprincipal\b|"
                       r"\bstaff (software )?engineer|architect\w*|arhitect\w*|"
                       r"(grad\w*|treapta|specialitate) (profesional )?(i ?a|superior)\b")
RE_MEDIU = re.compile(r"\bmid\b|mid[- ]level|\bmedior\b|\bmiddle\b|\bintermediate\b|\bregular\b")
RE_JUNIOR = re.compile(r"\bjunior\b|\bjr\b\.?|entry[- ]level|\bdebutant\w*|\bstagiar\w*|\btrainee\b|\bgraduate\b|"
                       r"\babsolvent\w*|fara experienta|\bincepator\w*|\bbeginner\b|\bassociate\b|"
                       r"(grad\w*|treapta) (profesional )?(ii|iii|debutant)\b")
ORDINE_NIVEL = ["junior", "mediu", "senior", "conducere"]


def nivel_bucata(b):
    if RE_CONDUCERE.search(b) and not RE_CONDUCERE_OK.search(b):
        return "conducere"
    if RE_SENIOR.search(b):
        return "senior"
    if RE_JUNIOR.search(b):
        return "junior"
    if RE_MEDIU.search(b):
        return "mediu"
    return None


def nivel_din_titlu(titlu):
    """Cel mai „mic” nivel dintre bucățile bune ale titlului („Contabil șef / Contabil cu experiență” -> senior,
    „Junior Disponent (MRP Controller)” -> junior)."""
    niv = [nivel_bucata(b) for b in bucati_titlu(titlu) if categorii_bucata(b)]
    if not niv:
        niv = [nivel_bucata(fara_diacritice(titlu))]
    cunoscute = [n for n in niv if n]
    if "junior" in cunoscute:
        return "junior"
    if not cunoscute or len(cunoscute) < len(niv):
        return None  # „Contabil / Expert contabil”: se caută și un contabil obișnuit
    return min(cunoscute, key=ORDINE_NIVEL.index)


def nivel_din_sursa(text):
    """Nivelul scris de site: eJobs „Entry-Level (< 2 ani)”, LinkedIn „Începător”, ANOFM „Experiență medie…”."""
    t = fara_diacritice(text or "")
    if not t:
        return None
    if re.search(r"fara experienta|entry|incepator|internship|stagiu|stagiar|junior|absolvent|putina|mai putin de|< ?2", t):
        return "junior"
    if re.search(r"mid|medi[ue]|intermediar|asociat|associate|2 ?- ?5", t):
        return "mediu"
    if re.search(r"senior|avansat|expert|peste|> ?5|director|executiv|manager", t):
        return "senior"
    m = re.match(r"\s*(\d+)\s*(\+|-|ani)", t)
    if m:
        return "junior" if int(m.group(1)) <= 1 else "mediu" if int(m.group(1)) <= 4 else "senior"
    return None


RE_FARA_EXPERIENTA = re.compile(
    r"fara experienta|nu (este |e )?necesar\w* experienta|nu (se )?(cere|solicita|necesita) experienta|"
    r"experienta (anterioara )?(nu este|nu e) (necesara|obligatorie)|no (prior |previous )?experience (is )?"
    r"(required|needed|necessary)|experience is not (required|mandatory)|entry[- ]level|proaspat absolvent\w*|"
    r"recent graduate|fresh graduate|graduate program\w*|\babsolvent\w* (de |ai )?(facultat|studii|universit)|"
    r"\b0 ?[-–] ?[12] (ani|an|years?)\b|less than (1|one|2|two) years?|te (formam|pregatim|instruim)|"
    r"we (will )?train you|full training|on[- ]the[- ]job training|perioada de (formare|instruire)")
RE_ANI_EXPERIENTA = re.compile(
    r"(?P<sub1>(mai putin de|sub|less than|under|pana la|up to) )?"
    r"\b(?P<n1>\d{1,2})\s*(\+|plus)?\s*([-–]|to|pana la)?\s*(\d{1,2})?\s*(ani|an|years?|yrs)\b\s+(\w+\s+){0,3}?"
    r"(de\s+)?(experienta|experience|vechime)|"
    r"(experienta|experience|vechime)\s+([\w:,()-]+\s+){0,8}?(?P<sub2>(mai putin de|sub|less than|under|pana la|up to) )?"
    r"(intre )?\b(?P<n2>\d{1,2})\s*(\+|plus)?\s*((-|–|si|to|and)\s*\d{1,2}\s*)?(ani|an|years?|yrs)\b")
# „Suntem o companie cu peste 20 de ani de experiență” vorbește despre firmă, nu despre candidat
RE_EXPERIENTA_FIRMA = re.compile(r"(companie|compania|firma|societate|company|grup|group|noastra|our|avem|we have|"
                                 r"suntem|we are|traditie|istoric|pe piata|on the market|lider)\W+(\w+\W+){0,4}$")


def ani_experienta(desc):
    """Câți ani de experiență cere anunțul (primul număr găsit lângă „experiență”), sau None."""
    for m in RE_ANI_EXPERIENTA.finditer(desc):
        g = "n1" if m.group("n1") else "n2"
        if int(m.group(g)) > 10:
            continue
        if RE_EXPERIENTA_FIRMA.search(desc[max(0, m.start() - 50):m.start(g)]):
            continue
        return 0 if m.group("sub1" if g == "n1" else "sub2") else int(m.group(g))
    return None


# --- limbi străine
LIMBI = {
    "germana": (r"german\w*|deutsch\w*", "germană"), "franceza": (r"french|francez\w*|francais\w*", "franceză"),
    "italiana": (r"italian\w*", "italiană"), "spaniola": (r"spanish|spaniol\w*|espanol", "spaniolă"),
    "olandeza": (r"dutch|olandez\w*|neerlandez\w*|flamand\w*|flemish", "olandeză"),
    "maghiara": (r"hungarian|maghiar\w*", "maghiară"), "poloneza": (r"polish|polonez\w*", "poloneză"),
    "ceha": (r"czech|ceha|cehe", "cehă"), "slovaca": (r"slovak\w*|slovac\w*", "slovacă"),
    "portugheza": (r"portugues\w*|portughez\w*", "portugheză"), "suedeza": (r"swedish|suedez\w*", "suedeză"),
    "daneza": (r"danish|danez\w*", "daneză"), "norvegiana": (r"norwegian|norvegian\w*", "norvegiană"),
    "finlandeza": (r"finnish|finlandez\w*", "finlandeză"), "greaca": (r"greek|greaca", "greacă"),
    "turca": (r"turkish|turca", "turcă"), "rusa": (r"russian|rusa", "rusă"),
    "ucraineana": (r"ukrainian|ucrainean\w*", "ucraineană"), "bulgara": (r"bulgarian|bulgara", "bulgară"),
    "sarba": (r"serbian|sarba", "sârbă"), "croata": (r"croatian|croata", "croată"),
    "japoneza": (r"japanese|japonez\w*", "japoneză"), "chineza": (r"chinese|mandarin|chinez\w*", "chineză"),
    "araba": (r"arabic|araba", "arabă"), "ebraica": (r"hebrew|ebraic\w*", "ebraică"),
    "engleza": (r"english|englez\w*", "engleză"),
}
RE_LIMBA = {k: re.compile(r"\b(" + rx + r")\b") for k, (rx, _) in LIMBI.items()}
# în titlu orice limbă e o cerință („Credit Analyst - German”), dar nu „firmă germană”
RE_LIMBA_FIRMA = re.compile(r"^\W*(firm\w*|compan\w*|company|grup\w*|group|multinational\w*|client\w*|investitor\w*|"
                            r"piata|market|capital)\b")
RE_LIMBA_FIRMA_INAINTE = re.compile(r"(firm\w*|compan\w*|grup\w*|multinational\w*|client\w*|investitor\w*|"
                                    r"capital)\W+$")
RE_CTX_LIMBA_INAINTE = re.compile(r"(limb\w*|cunoa?st\w*|vorbit\w*|vorbes\w*|fluent\w*|nivel\w*|speak\w*|"
                                  r"knowledge of|command of|fluency in|proficien\w*|written and spoken|"
                                  r"scris si vorbit)\W+(\w+\W+){0,3}?$")
RE_CTX_LIMBA_DUPA = re.compile(r"^\W*(\w+\W+){0,1}?(language|speaker|speaking|skills|fluent\w*|nivel\w*|level|b1|b2|"
                               r"c1|c2|avansat\w*|mediu|scris|vorbit|conversational|native|nativ\w*|proficien\w*|"
                               r"obligatori\w*|is a must)\b")
RE_LIMBA_OPTIONALA = re.compile(r"avantaj\w*|advantage\w*|un plus|a plus|an asset|nice to have|good to have|"
                                r"preferabil\w*|prefer\w*|desirable|desired|welcome|beneficial|ideally|constituie un|"
                                r"bonus|optional\w*")
LIMBI_STIUTE = {fara_diacritice(x) for x in CFG.get("limbi_straine_cunoscute", {}).get("limbi", ["engleza"])}


def limbi_cerute(titlu, desc, din_sursa=()):
    """(limbile cerute în titlu, limbile cerute în text sau de site), fără cele pe care le știi."""
    in_titlu = set()
    in_text = {k for nume in din_sursa for k, rx in RE_LIMBA.items() if rx.search(fara_diacritice(nume))}
    for k, rx in RE_LIMBA.items():
        for m in rx.finditer(titlu):
            if not (RE_LIMBA_FIRMA.search(titlu[m.end():m.end() + 30]) or
                    RE_LIMBA_FIRMA_INAINTE.search(titlu[max(0, m.start() - 25):m.start()])):
                in_titlu.add(k)
        for m in rx.finditer(desc):
            inainte, dupa = desc[max(0, m.start() - 60):m.start()], desc[m.end():m.end() + 40]
            if not (RE_CTX_LIMBA_INAINTE.search(inainte) or RE_CTX_LIMBA_DUPA.search(dupa)):
                continue  # „companie germană”, „clienți din Italia”
            # „…constituie un avantaj” contează doar în aceeași propoziție
            inceput = max(desc.rfind(c, 0, m.start()) for c in "\n.;") + 1
            sfarsit = min([x for x in (desc.find(c, m.end()) for c in "\n.;") if x >= 0] or [len(desc)])
            if RE_LIMBA_OPTIONALA.search(desc[inceput:sfarsit]):
                continue
            in_text.add(k)
    return in_titlu - LIMBI_STIUTE, (in_text - in_titlu) - LIMBI_STIUTE


# --- străinătate, program, contract, beneficii
TARI = (r"(germania|olanda|belgia|franta|italia|spania|austria|danemarca|suedia|norvegia|elvetia|"
        r"polonia|cehia|anglia|marea britanie|irlanda|luxemburg|finlanda|scandinavia|grecia|ungaria)")
RE_STRAINATATE_TITLU = re.compile(r"strainatate|abroad|\b" + TARI + r"\b")
# în descriere cerem context de muncă; altfel prindem „studii efectuate în străinătate”, „companie elvețiană”
RE_STRAINATATE_DESC = re.compile(r"(locul de munca|munca|lucru|job|angajare|postul|relocare|instalare|mutare)\s+"
                                 r"(\w+\s+){0,3}in " + TARI + r"\b")
RE_NEG_STRAINATATE = re.compile(r"\b(fara|nu|nici)\s+(\w+\s+){0,3}(strainatate|" + TARI[1:-1] + r")")

RE_PROGRAM_BUN = re.compile(
    r"(de )?luni\s*(-|–|pana)\s*(vineri|vi)|\bl\s*[-–]\s*v\b|lu\s*[-–]\s*vi|weekend(ul|uri)? libere?|"
    r"sambata si duminica liber\w*|\b8 ore\b|program fix|program normal|ture? de zi|program de zi|"
    r"fara ture de noapte|nu (se )?lucreaza (noaptea|in weekend)|monday\s*(-|–|to)\s*friday|"
    r"\b0?[5-9][:.]?[03]0\s*[-–]\s*1[4-8][:.]?[03]0\b")
RE_PROGRAM_RAU = re.compile(
    r"(tura|ture|program) de noapte|\bnoaptea\b|12\s*/\s*24|24\s*/\s*48|12\s*/\s*12|"
    r"weekend(ul)? lucr|lucru (si )?in weekend|sambata (lucr|inclus)|program prelungit|"
    r"disponibilitate.{0,30}(weekend|noapte|ore suplimentare)|ture de 12|\b(2|3|doua|trei) (schimburi|ture)\b|"
    r"ture rotative|(program|lucru) in (trei )?ture|night shift")
RE_NEG_PROGRAM = re.compile(r"\b(fara|nu (se )?(lucreaza|lucram|lucrezi|lucra)|nu|exclus)\s+(\w+\s+){0,3}"
                            r"(noapte|noaptea|weekend\w*|sambata|duminica)")

RE_DETERMINAT = re.compile(r"perioada determinata( - \d+ luni)?|contract (pe|de) \d+ (luni|ani|an)|\bsezonier\w*|"
                           r"temporar vacant|"
                           r"perioada limitata|contract temporar|\b\d+[- ](month|months|luni|year|an)\s+contract|"
                           r"contract\s+(of\s+)?\d+\s*(months?|years?)|fixed[- ]term|\btemporary\b|"
                           r"maternity (leave )?(cover|replacement)|inlocuire concediu|concediu (de )?(maternitate|"
                           r"crestere)")
RE_ABONAMENT = re.compile(r"abonament\w*\s+(\w+\s+){0,2}(medical\w*|la clinica|de sanatate|servicii medicale)|"
                          r"asigurare (medicala|de sanatate) (privata|suplimentara)|private (health|medical)|"
                          r"health (insurance|subscription)|medical (insurance|subscription)")
RE_TICHETE = re.compile(r"tichete|bonuri de masa|card de masa|tichet de masa|meal (tickets|vouchers)")
RE_HIBRID = re.compile(r"\bhibrid\w*|\bhybrid\b|\bremote\b|work(ing)? from home|(lucru|lucrezi|lucra|munca|munci|"
                       r"lucreaza) (\w+ )?de acasa|(zi|zile) (\w+ ){0,2}de acasa|telemunc\w*|\bwfh\b|home ?office|"
                       r"(munca|lucru|lucrul) la distanta")
# „Fully remote”, „100% remote”, „lucru de acasă”: se poate lucra numai de acasă, de oriunde din țară
RE_DOAR_REMOTE = re.compile(r"(fully|full|100 ?%|complet|exclusiv|totally|entirely|permanent\w*) ?(-|\s)?(remote|de acasa)|"
                            r"remote[- ](first|only)|work (fully )?remotely|\(remote\)|\bremote (position|role|job|"
                            r"contract|opportunity)|remote,? (romania|in romania|from romania|anywhere)|"
                            r"(location|locatie|loc de munca)\W+remote|^\W*remote\b|[-–|]\s*remote\s*$")
RE_NEG_HIBRID = re.compile(r"\b(fara|nu|not|no|non)[\s-]+(\w+\s+){0,2}(hibrid|hybrid|remote|telemunc\w*|de acasa)|"
                           r"fully on[- ]?site|100% (on[- ]?site|la birou)")
_CERT = r"\b(certificar\w*|certification\w*|certificat\w*|aws|azure|ccna|ccnp|itil|istqb|comptia|cursuri|courses?|training\w*)\b"
_PLATIT = (r"(sprijin\w*|suport\w*|support\w*|sponsor\w*|platit\w*|plata\w*|paid|decont\w*|finant\w*|acoper\w*|"
           r"cover\w*|reimburs\w*|subventi\w*|buget\w*|budget\w*)")
RE_CERTIFICARE = re.compile(_CERT + r"[^\n]{0,60}?" + _PLATIT + r"|" + _PLATIT + r"[^\n]{0,60}?" + _CERT +
                            r"|udemy|pluralsight|coursera|learning (budget|platform)|training budget")
RE_AGENTIE = re.compile(r"recru\w*|work ?force|work agency|\bagency\b|\bagenti[ea]\b|staffing|\bstaff\b|human|"
                        r"\bhr\b|\bpersonal\b|\bjobs?\b|plasare|interim|headhunt\w*|executive search|talent|"
                        r"adecco|randstad|manpower|gi group|lugera|trenkwalder|\bhays\b|michael page|\bantal\b|"
                        r"grafton|kelly services")


def plus(motive, puncte, text):
    motive.append({"p": puncte, "t": text})
    return puncte


def clasifica(job, firme):
    """Adaugă tip (dev / qa / infra / date / suport), nivel, etichete, motive (cu puncte), scor și `exclus`.
    Folosește titlul + descrierea anunțului (nu și descrierea firmei) + datele site-ului + reputația firmei."""
    titlu = fara_diacritice(job["titlu"])
    desc = fara_diacritice(job.get("descriere", ""))
    txt = titlu + "\n" + desc

    etichete, motive = [], []
    scor = 50

    # --- zona (bonusurile se aleg în config.json)
    bonus, zona = max(((ZONE[z].get("bonus", 0), ZONE[z]["eticheta"]) for z in job["zone"] if z in ZONE), default=(0, ""))
    if bonus:
        scor += plus(motive, bonus, f"Zona: {zona}")

    # --- postul
    tip = tip_post(titlu, desc)
    exclus = None
    m_int = RE_STRAINATATE_TITLU.search(titlu) or RE_STRAINATATE_DESC.search(RE_NEG_STRAINATATE.sub(" ", desc))
    if m_int:
        exclus = "job în străinătate"
        scor += plus(motive, -40, f"Job în străinătate („{m_int.group(0)[:40]}”)")
    if RE_INTERNSHIP.search(titlu) or (job["sursa"] == "LinkedIn" and job.get("nivel_sursa") in ("Stagiar", "Internship")):
        exclus = exclus or "internship"
        scor += plus(motive, -20, "Internship / stagiu de practică (de obicei pentru studenți)")

    # --- nivelul: titlul, apoi textul anunțului (câți ani de experiență cere), apoi ce a bifat firma pe site
    nivel, de_unde = nivel_din_titlu(job["titlu"]), "scris în titlu"
    if nivel == "conducere":
        exclus = exclus or "post de conducere"
        scor += plus(motive, -20, "Post de conducere (șef, manager, director)")
    ani = ani_experienta(desc)
    m_fara = RE_FARA_EXPERIENTA.search(desc)
    if not nivel and m_fara:
        nivel, de_unde = "junior", f"„{m_fara.group(0)}”"
    elif not nivel and ani is not None:
        nivel = "junior" if ani <= 1 else "mediu" if ani <= 4 else "senior"
        de_unde = f"cere {ani} {'an' if ani == 1 else 'ani'} de experiență"
    elif not nivel and job.get("nivel_sursa"):
        nivel, de_unde = nivel_din_sursa(job["nivel_sursa"]), f"după {job['sursa']}: {job['nivel_sursa']}"
    if nivel == "junior":
        etichete.append("junior")
        scor += plus(motive, 6, f"Potrivit pentru junior ({de_unde})")
    elif nivel == "senior":
        etichete.append("senior")
        scor += plus(motive, -8, f"Post de senior, cere multă experiență ({de_unde})")
    elif nivel == "mediu" and ani is not None and ani >= 2:
        scor += plus(motive, -3, f"Cere minim {ani} ani de experiență")

    # --- limbi străine pe care nu le știi
    l_titlu, l_text = limbi_cerute(titlu, desc, job.get("limbi_sursa") or [])
    if l_titlu:
        etichete.append("altă limbă")
        scor += plus(motive, -10, "Cere limba " + " și ".join(LIMBI[k][1] for k in sorted(l_titlu)) + " (scris în titlu)")
    elif l_text:
        etichete.append("altă limbă")
        scor += plus(motive, -6, "Cere limba " + " și ".join(LIMBI[k][1] for k in sorted(l_text)))

    # --- program
    bune = {m.group(0) for m in RE_PROGRAM_BUN.finditer(txt)}
    rele = {m.group(0) for m in RE_PROGRAM_RAU.finditer(RE_NEG_PROGRAM.sub(" ", txt))}
    if bune:
        etichete.append("program bun")
        scor += plus(motive, 8, "Program de zi / L–V („" + ", ".join(sorted(bune))[:60] + "”)")
    if rele:
        etichete.append("noapte/weekend")
        scor += plus(motive, -12, "Se lucrează în ture, noaptea sau în weekend („" + ", ".join(sorted(rele))[:60] + "”)")
    m_hib = RE_HIBRID.search(RE_NEG_HIBRID.sub(" ", txt))
    if job.get("hibrid_sursa") or m_hib:
        etichete.append("hibrid/remote")
        scor += plus(motive, 4, "Se poate lucra și de acasă (hibrid / remote)" +
                     (f" („{m_hib.group(0)}”)" if m_hib and not job.get("hibrid_sursa") else ""))

    m_det = RE_DETERMINAT.search(txt)
    if m_det:
        etichete.append("contract temporar")
        scor += plus(motive, -6, f"Contract doar pe o perioadă ({m_det.group(0)})")

    # --- beneficii
    if RE_ABONAMENT.search(txt):
        etichete.append("abonament medical")
        scor += plus(motive, 4, "Abonament medical / asigurare de sănătate")
    if RE_TICHETE.search(txt):
        etichete.append("tichete de masă")
        scor += plus(motive, 2, "Tichete de masă")
    if RE_CERTIFICARE.search(txt):
        etichete.append("certificări")
        scor += plus(motive, 3, "Firma plătește cursuri sau certificări (AWS, Azure, ISTQB, CCNA…)")

    # --- salariu (lei net pe lună)
    lo, hi = job.get("sal_min"), job.get("sal_max")
    if hi:
        pct = 12 if hi >= 15000 else 9 if hi >= 11000 else 6 if hi >= 8000 else 2 if hi >= 5500 else \
            0 if hi >= 3500 else -6
        sursa = " (scris în descriere)" if job.get("sal_din_descriere") else ""
        scor += plus(motive, pct, f"Salariu {lo}–{hi} lei net{sursa}" if lo != hi else f"Salariu {hi} lei net{sursa}")
    else:
        plus(motive, 0, "Salariul nu e scris în anunț")

    # --- firma
    firma_n = fara_diacritice(job.get("firma", ""))
    preferat = next((f for f in CFG["firme_preferate"]
                     if re.search(r"\b" + re.escape(fara_diacritice(f)) + r"\b", firma_n + " " + titlu)), None)
    if preferat:
        etichete.append("firmă preferată")
        scor += plus(motive, 8, f"Firmă din lista preferată ({preferat.upper() if len(preferat) <= 4 else preferat.title()})")
    elif job.get("firma_confirmata") and RE_AGENTIE.search(firma_n):
        etichete.append("agenție")
        scor += plus(motive, -6, "Agenție de recrutare, nu angajatorul direct")

    rep = firme.get(cheie_firma(job.get("firma", ""))) if job.get("firma_confirmata") else None
    ul = (rep or {}).get("undelucram") or {}
    if ul.get("nota") and ul.get("evaluari"):
        n, e = ul["nota"], ul["evaluari"]
        pct = 8 if n >= 4.0 else 4 if n >= 3.5 else 0 if n >= 3.0 else -6 if n >= 2.5 else -10
        if e < 5:
            pct = round(pct / 2)
        scor += plus(motive, pct, f"Angajații dau firmei nota {n:.1f} din 5 ({e} păreri pe UndeLucram)".replace(".", ",", 1))
    g = (rep or {}).get("google") or {}
    if g.get("nota") and g.get("evaluari", 0) >= 10:
        pct = 2 if g["nota"] >= 4.5 else -2 if g["nota"] < 3.5 else 0
        scor += plus(motive, pct, f"Clienții dau nota {g['nota']:.1f} pe Google ({g['evaluari']} recenzii)".replace(".", ",", 1))

    # --- vechimea anunțului
    zile = zile_de_la(job.get("reimprospatat") or job.get("publicat") or job.get("prima_data") or NOW)
    if zile is not None and zile > 45:
        scor += plus(motive, -4, f"Anunț vechi ({zile} zile), poate e deja ocupat")

    scor = max(0, min(100, scor))
    verdict = "Foarte potrivit" if scor >= 80 else "Potrivit" if scor >= 65 else \
        "Merită verificat" if scor >= 50 else "Slab"
    job.update(tip=tip, nivel=nivel, etichete=etichete, motive=motive, scor=scor, verdict=verdict, exclus=exclus)
    return job


# ------------------------------------------------------------ localități

def _curata(p):
    """„Județul Brașov” / „Brașov County” / „Ghimbav 507075” / „Zona metropolitană Brașov” -> „brasov”, „brasov”,
    „ghimbav”, „brasov”."""
    p = re.sub(r"\b(judetul|judet|jud|municipiul|mun|orasul|oras|comuna|com|satul|sat|county|romania|rumunia|"
               r"zona metropolitana|metropolitan area)\b\.?|\d+", " ", p)
    return re.sub(r"\s+", " ", p).strip(" .-")


ZONE = {k: v for k, v in CFG["zone"].items() if not k.startswith("_")}
REMOTE = "remote"  # zona joburilor de acasă, de oriunde din țară
TOATE_JUDETELE = {_curata(fara_diacritice(j)) for j in (
    "Alba", "Arad", "Argeș", "Bacău", "Bihor", "Bistrița-Năsăud", "Botoșani", "Brașov", "Brăila", "București",
    "Bucharest", "Buzău", "Călărași", "Caraș-Severin", "Cluj", "Constanța", "Covasna", "Dâmbovița", "Dolj", "Galați",
    "Giurgiu", "Gorj", "Harghita", "Hunedoara", "Ialomița", "Iași", "Ilfov", "Maramureș", "Mehedinți", "Mureș", "Neamț",
    "Olt", "Prahova", "Sălaj", "Satu Mare", "Sibiu", "Suceava", "Teleorman", "Timiș", "Tulcea", "Vâlcea", "Vaslui",
    "Vrancea")}
JUDETE_ZONA = {z: {_curata(fara_diacritice(j)) for j in v.get("judete", [])} for z, v in ZONE.items()}
JUDET_IMPLICIT = {}  # o localitate necunoscută din județ intră la prima zonă care are județul
LOC_ZONA = {}
for _z, _j in ZONE.items():
    for _jud in JUDETE_ZONA[_z]:
        JUDET_IMPLICIT.setdefault(_jud, _z)
    for _loc in _j.get("localitati", []):
        LOC_ZONA.setdefault(_curata(fara_diacritice(_loc)), []).append(_z)
RE_COD_POSTAL = [(z, re.compile(v["cod_postal"])) for z, v in ZONE.items() if v.get("cod_postal")]
RE_REMOTE_LOC = re.compile(r"\bremote\b|de acasa|work from home|telemunca|oriunde|anywhere")


def zone_din_orase(orase, judet_sigur=None):
    """Zonele în care e jobul, în ordinea din anunț. Merge și cu adrese complete
    („Strada Hermann Oberth, Ghimbav, Brașov, România”, „Sector 2, București”). Cu `judet_sigur` (site-ul a filtrat
    deja județul), o localitate necunoscută intră la zona implicită a județului."""
    zone = []
    for o in orase:
        bucati = [b for b in (_curata(p) for p in re.split(r"[,>]", fara_diacritice(o or ""))) if b]
        judete = {b for b in bucati if b in TOATE_JUDETELE}
        if judet_sigur:
            judete.add(_curata(fara_diacritice(judet_sigur)))
        z = None
        for b in bucati:
            # „Vulcan, Hunedoara”, „Măgurele, Prahova”: altă localitate cu același nume
            z = next((x for x in LOC_ZONA.get(b, []) if not (judete - {b}) or JUDETE_ZONA[x] & judete), None)
            if z:
                break
        if not z:
            z = next((JUDET_IMPLICIT[j] for j in judete if j in JUDET_IMPLICIT), None)
        if not z:
            z = next((zz for zz, rx in RE_COD_POSTAL if rx.search(o or "")), None)
        if not z and RE_REMOTE_LOC.search(fara_diacritice(o or "")):
            z = REMOTE  # BestJobs, Hipo: „Remote” în loc de oraș
        if z and z not in zone:
            zone.append(z)
    return zone


def marcheaza_dubluri(joburi):
    """Același anunț postat de mai multe ori (alt oraș / altă sursă): păstrăm unul, restul primesc `dublura_lui`."""
    grupe = {}
    for j in joburi:
        j.pop("dublura_lui", None)
        if not j["activ"]:
            continue
        cheie = re.sub(r"[^a-z0-9]", "", fara_diacritice(j["titlu"]))[:60] + "|" + cheie_firma(j["firma"])[:12]
        grupe.setdefault(cheie, []).append(j)
    for grup in grupe.values():
        grup.sort(key=lambda j: (j["sursa"] not in SURSE_DIRECTE, -j["scor"], j["id"]))
        grup[0]["si_in"] = sorted({o for j in grup[1:] for o in j["orase"]} - set(grup[0]["orase"]))[:10]
        grup[0]["alte_surse"] = sorted({j["sursa"] for j in grup[1:]} - {grup[0]["sursa"]})
        for j in grup[1:]:
            j["dublura_lui"] = grup[0]["id"]


def completeaza_salariu(job):
    """Dacă anunțul nu are salariu în câmpul dedicat, îl căutăm în descriere."""
    job["sal_din_descriere"] = False
    if not job.get("sal_max"):
        lo, hi, txt = salariu_din_descriere(job.get("descriere", ""))
        if hi:
            job.update(sal_min=lo, sal_max=hi, salariu_text=txt, sal_din_descriere=True)
    return job


# ----------------------------------------------------------------- surse

def sursa_ejobs():
    api = "https://api.ejobs.ro"
    statics = cache_get("ejobs_statics", lambda: fetch(f"{api}/all-statics"), max_zile=30)["ro"]
    orase = {c["id"]: c for c in statics["cities"]}
    judete = {c["id"]: c["name"] for c in statics["counties"]}
    nivele = {c["id"]: c["name"] for c in statics["careerLevels"]}
    limbi = {c["id"]: fara_diacritice(c["name"]) for c in statics["languages"]}
    ale_noastre = (9, 4, 10, 17)  # Brașov, Bacău, București, Ilfov
    filtru_judete = "".join(f"&filters.counties={j}" for j in ale_noastre)
    # API-ul dă puține rezultate pe căutare, așa că împărțim pe cuvinte cheie și departamente
    # (57 IT Software, 58 IT Hardware, 38 Telecomunicații, 46 Statistică / Matematică)
    cautari = ["q=" + urllib.parse.quote(k) for k in (
        "developer", "programator", "software", "engineer", "frontend", "backend", "full stack", "java", "python",
        ".net", "php", "javascript", "qa", "tester", "devops", "cloud", "administrator", "retea", "network",
        "support", "suport", "helpdesk", "tehnician it", "it", "data", "security", "informatician")] + \
        [f"filters.departments={d}" for d in (57, 58, 38, 46)]

    vazute, rezultate, erori = set(), [], []
    for extra in cautari:
        page = 1
        while page <= 10:
            try:
                d = fetch(f"{api}/jobs?page={page}&pageSize=50&{extra}{filtru_judete}",
                          retries=0 if page > 1 else 1)
            except Exception as e:  # noqa: BLE001 - API-ul dă 404 după ultima pagină
                if page == 1:
                    # de pe serverele GitHub eJobs refuză uneori câte o căutare (403): trecem la următoarea,
                    # dar dacă primele trei pică toate, e blocat de tot
                    erori.append(str(e))
                    if len(erori) >= 3 and not vazute:
                        raise
                break
            for j in d.get("jobs", []):
                if j["id"] in vazute:
                    continue
                vazute.add(j["id"])
                if not e_job_potrivit(j["title"]):
                    continue
                locs = [orase.get(l["cityId"], {}) for l in j.get("locations", [])]
                zone = []
                for l in locs:
                    if l.get("countyId") in ale_noastre:
                        zone += [z for z in zone_din_orase([l.get("name", "?")], judet_sigur=judete[l["countyId"]])
                                 if z not in zone]
                if not zone and not j.get("allLocations"):
                    continue
                rezultate.append((j, [l.get("name", "?") for l in locs], zone))
            if not d.get("morePagesFollow"):
                break
            page += 1
    if erori:
        print(f"   ! eJobs: {len(erori)} căutări din {len(cautari)} au eșuat ({erori[-1][:70]})")
    print(f"   eJobs: {len(vazute)} anunțuri văzute, {len(rezultate)} potrivite în zonele alese")

    joburi = []
    for j, nume_orase, zone in rezultate:
        det = cache_get(f"ejobs_{j['id']}", lambda: fetch(f"{api}/jobs/{j['id']}?viewedFromMobile=false"))
        if det.get("workModel") == "REMOTE":
            zone = [REMOTE] + zone
        elif not zone:
            continue  # „în toată țara”, dar la birou: nu știm în ce oraș
        dd = det.get("details", {}) or {}
        # descrierea firmei rămâne pe dinafară: e text general despre firmă, nu despre post
        desc = text_din_html("\n".join(v for k, v in dd.items()
                                       if isinstance(v, str) and k != "companyDescription"))
        lo, hi = parse_salariu(j.get("salary"))  # eJobs afișează salariul net
        niv = [nivele[n] for n in j.get("careerLevelsIds") or [] if n in nivele]
        joburi.append({
            "id": f"ejobs:{j['id']}", "sursa": "eJobs", "titlu": j["title"].strip(),
            "firma": (j.get("company") or {}).get("name", ""), "firma_confirmata": True,
            "orase": (nume_orase or ["Remote"])[:8], "zona": zone[0], "zone": zone,
            "url": f"https://www.ejobs.ro/user/locuri-de-munca/{j['slug']}/{j['id']}",
            "salariu_text": j.get("salary") or "", "sal_min": lo, "sal_max": hi,
            "publicat": j.get("creationDate"), "expira": j.get("expirationDate"),
            "nivel_sursa": ", ".join(niv), "hibrid_sursa": det.get("workModel") in ("HYBRID", "REMOTE"),
            "limbi_sursa": [limbi[x["languageId"]] for x in det.get("languages") or [] if x.get("languageId") in limbi],
            "descriere": desc[:4000],
        })
    return joburi


def sursa_bestjobs():
    api = "https://api.bestjobs.eu/v2/jobs"
    gasite = {}
    for loc in CFG["cuvinte_cautare"]["bestjobs_locatii"]:
        for kw in CFG["cuvinte_cautare"]["bestjobs"]:
            cursor, pagini = None, 0
            while pagini < 10:
                q = {"limit": 24, "locale": "ro", "keyword": kw, "location[]": loc}
                if cursor:
                    q["cursor"] = cursor
                d = fetch(api + "?" + urllib.parse.urlencode(q))
                items = d.get("items", [])
                for it in items:
                    if it["id"] not in gasite and e_job_potrivit(it["title"]):
                        gasite[it["id"]] = it
                pagini += 1
                cursor = d.get("nextCursor")
                if not items or not cursor:
                    break
        print(f"   BestJobs {loc}: total {len(gasite)} relevante")

    joburi = []
    for jid, it in gasite.items():
        orase = [l["name"].replace(", România", "") for l in it.get("locations", [])]
        zone = zone_din_orase(orase)
        if not zone:
            continue  # căutarea BestJobs întoarce și joburi din alte județe
        def incarca():
            s = fetch(f"https://www.bestjobs.eu/ro/loc-de-munca/{it['slug']}", as_json=False)
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', s, re.S)
            j = json.loads(m.group(1))["props"]["pageProps"].get("job", {}) if m else {}
            return {"description": j.get("description", ""), "salary": j.get("salary", ""),
                    "remote": bool(j.get("remote") or j.get("partialRemote")), "doar_remote": bool(j.get("remote")),
                    "nivel": ", ".join(str(c.get("name", c) if isinstance(c, dict) else c) for c in j.get("careerLevels") or []),
                    "limbi": [fara_diacritice(x.get("name", "")) for x in j.get("spokenLanguages") or []]}
        try:
            det = cache_get(f"bestjobs_{jid}", incarca)
        except Exception as e:  # noqa: BLE001
            print(f"   ! detalii BestJobs {jid}: {e}")
            det = {"description": "", "salary": ""}
        if det.get("doar_remote") and REMOTE not in zone:
            zone.append(REMOTE)
        sal_text = det.get("salary") or it.get("salary") or ""
        lo, hi = parse_salariu(sal_text)
        joburi.append({
            "id": f"bestjobs:{jid}", "sursa": "BestJobs", "titlu": it["title"].strip(),
            "firma": it.get("companyName", ""), "firma_confirmata": True,
            "orase": orase[:8], "zona": zone[0], "zone": zone,
            "url": f"https://www.bestjobs.eu/ro/loc-de-munca/{it['slug']}",
            "salariu_text": sal_text, "sal_min": lo, "sal_max": hi,
            "publicat": None, "expira": None,
            "nivel_sursa": det.get("nivel", ""), "hibrid_sursa": det.get("remote", False),
            "limbi_sursa": det.get("limbi", []),
            "descriere": text_din_html(det.get("description", ""))[:4000],
        })
    return joburi


RE_FIRMA_IN_NUME = re.compile(r"\b(srl|s\.r\.l|sa|s\.a|srl-d|pfa|ii|company|group|grup|impex|com|consult\w*|"
                              r"soft\w*|tech\w*|it|solutions|systems|digital|data|net|web)\b")


def sursa_olx():
    """OLX: în Brașov și Bacău luăm toate anunțurile de muncă (câteva sute) și le filtrăm după titlu; în București
    sunt mii, așa că acolo căutăm după cuvinte și în categoria „IT / Telecomunicații”."""
    api = "https://www.olx.ro/api/v1/offers/"
    cuvinte = ["it", "programator", "developer", "software", "calculatoare", "suport tehnic", "helpdesk", "retea",
               "web", "tester", "informatician", "sistem", "date"]
    # regiunile OLX: 4 Brașov, 3 Bacău, 46 București - Ilfov; categoria 4 = Locuri de muncă, 3343 / 3335 = IT
    cautari = [(4, "Brașov", 4, q) for q in [None, *cuvinte]] + [(3, "Bacău", 4, q) for q in [None, *cuvinte]] + \
              [(46, "București", 4, q) for q in cuvinte] + [(46, "București", c, None) for c in (3343, 3335)]
    joburi, vazute = [], set()
    for regiune, judet, categorie, query in cautari:
        offset = 0
        while offset < 1000:
            q = {"offset": offset, "limit": 50, "category_id": categorie, "region_id": regiune}
            if query:
                q["query"] = query
            d = fetch(api + "?" + urllib.parse.urlencode(q))
            data = d.get("data", [])
            for o in data:
                if o["id"] in vazute:
                    continue
                vazute.add(o["id"])
                desc = text_din_html(o.get("description", ""))
                if not e_job_potrivit_sau_text(o["title"], desc):
                    continue
                params = {p["key"]: p.get("value") for p in o.get("params", [])}
                sal = params.get("salary") or {}
                lo = hi = None
                sal_text = ""
                if sal and not sal.get("arranged") and sal.get("type") not in ("hourly", "daily"):
                    k = NET_DIN_BRUT if sal.get("gross") else 1
                    lo = round((sal.get("converted_from") or sal.get("from") or 0) * k) or None
                    hi = round((sal.get("converted_to") or sal.get("to") or 0) * k) or lo
                    lo = lo or hi
                    sal_text = f"{sal.get('from')} - {sal.get('to')} {sal.get('currency')}" + \
                               (" brut" if sal.get("gross") else " net")
                    if not hi or hi < 2000:
                        lo = hi = None
                program = (params.get("program_demunca") or {}).get("label") or ""
                city = o["location"].get("city", {}).get("name", "")
                zone = zone_din_orase([city], judet_sigur=judet)
                if program:
                    desc = f"Program: {program}\n" + desc
                user = o.get("user") or {}
                firma = user.get("company_name") or user.get("name") or ""
                confirmata = bool(user.get("company_name")) or bool(RE_FIRMA_IN_NUME.search(fara_diacritice(firma)))
                joburi.append({
                    "id": f"olx:{o['id']}", "sursa": "OLX", "titlu": o["title"].strip(),
                    "firma": firma, "firma_confirmata": confirmata,
                    "orase": [city], "zona": zone[0], "zone": zone, "url": o["url"],
                    "salariu_text": sal_text, "sal_min": lo, "sal_max": hi,
                    "publicat": o.get("created_time"), "reimprospatat": o.get("last_refresh_time"),
                    "expira": o.get("valid_to_time"), "descriere": desc[:4000],
                })
            if len(data) < 50:
                break
            offset += 50
    print(f"   OLX: {len(vazute)} anunțuri văzute, {len(joburi)} relevante")
    return joburi


_POST_GENERAL = (r"(referent|inspector|consilier|expert|specialist)( de specialitate)?"
                 r"( (grad\w*|treapta|clasa)( profesional\w*)? (i{1,3}|i?a|iv|debutant|asistent|principal|superior)\b|"
                 r" (i{1,3}|i?a|iv)\b)?")
_COMP_IT = r"(informatic\w*|\bit\b|tehnologia informatiei|\btic\b|sisteme informatice)"
RE_FUNCTIE_DESC = re.compile(
    r"\bpost(ul|uri|urile|ului)?\s+(\w+\s+){0,3}?(de\s+)?(informatician\w*|programator\w*|analist\w* programator\w*|"
    r"inginer\w* de sistem\w*|operator\w* (pc|calculator\w*)|administrator\w* (de )?(retea|sistem\w*)|"
    + _POST_GENERAL + r"\s+(\w+\s+)?" + _COMP_IT + r")|"
    r"\b" + _POST_GENERAL + r"\s*,?\s*(in cadrul|la nivelul|din cadrul|in|la)\s+(compartiment\w*|serviciu\w*|"
    r"birou\w*|directiei|departament\w*)\s+(\w+[\s-]+){0,2}?" + _COMP_IT)
RE_DATA = re.compile(r"\b(\d{1,2})\s*[./]\s*(\d{1,2})\s*[./]\s*(20\d\d)\b")
RE_ZILE_LUCRATOARE = re.compile(r"(\d+)\s*(\(\w+\)\s*)?zile lucratoare\s+(de la|de la data|de la data de)\s+"
                                r"(publicar|afisar)")


def zile_lucratoare(de_la, n):
    zi = datetime.fromisoformat(de_la).date()
    while n > 0:
        zi += timedelta(days=1)
        n -= zi.weekday() < 5
    return zi.isoformat()


def termen_dosar(text, publicat):
    """Ultima zi pentru dosar, din textul concursului: fraza cu „dosar” + „depun”/„înscriere” (nu cea cu
    contestații sau rezultate) care are o dată de după publicare, sau „în termen de 10 zile lucrătoare de la
    publicare” (atunci numărăm de la data de pe posturi.gov.ro, fără sărbători)."""
    zi_pub = (publicat or "")[:10]
    gasite = []
    for fraza in re.split(r"[\n;]", fara_diacritice(text)):
        if "dosar" not in fraza or not re.search(r"depun|inscrier", fraza) or re.search(r"contestat|selecti|rezultat", fraza):
            continue
        for d in RE_DATA.finditer(fraza):
            try:
                zi = datetime(int(d.group(3)), int(d.group(2)), int(d.group(1))).date().isoformat()
            except ValueError:
                continue
            if zi > zi_pub:
                gasite.append(zi)
        m = RE_ZILE_LUCRATOARE.search(fraza)
        if m and zi_pub and int(m.group(1)) <= 30:
            gasite.append(zile_lucratoare(zi_pub, int(m.group(1))))
    return max(gasite) if gasite else None


def posturi_detalii(url):
    """Angajatorul, termenul și contactul, de pe pagina anunțului (API-ul nu le dă)."""
    s = fetch(url, as_json=False)
    camp = lambda k: next(iter(re.findall(  # noqa: E731
        r'pg-mini-k">' + k + r'</div><div class="pg-mini-v">(.*?)</div>', s, re.S)), "")
    termen = re.search(r'pg-meta-deadline">\s*([\d-]+)', s)
    return {"angajator": text_din_html(camp("Angajator")), "email": text_din_html(camp("Email")),
            "telefon": text_din_html(camp("Telefon")), "termen": termen.group(1) if termen else None,
            "etichete": [text_din_html(x) for x in re.findall(r'<span class="pg-pill">(.*?)</span>', s, re.S)]}


def sursa_posturi():
    """posturi.gov.ro: portalul oficial unde primăriile, spitalele, școlile și instituțiile își publică concursurile."""
    api = "https://posturi.gov.ro/wp-json/wp/v2"
    judete = {442: "Brașov", 181: "Bacău", 483: "București", 1331: "Ilfov"}
    gasite = {}
    for kw in ["informatician", "informatic", "programator", "IT", "calculator", "retea", "sistem", "software",
               "tehnologia informatiei", "analist"]:
        pagina = 1
        while pagina <= 10:
            q = {"search": kw, "per_page": 100, "page": pagina, "pg_job_judet": ",".join(map(str, judete)),
                 "after": (NOW_DT - timedelta(days=120)).strftime("%Y-%m-%dT00:00:00"),
                 "_fields": "id,date,date_gmt,title,link,content,pg_job_judet,pg_job_oras"}
            d = fetch(f"{api}/pg_job?" + urllib.parse.urlencode(q))
            for p in d:
                gasite[p["id"]] = p
            if len(d) < 100:
                break
            pagina += 1
    print(f"   posturi.gov.ro: {len(gasite)} anunțuri găsite la căutare")

    joburi = []
    for pid, p in gasite.items():
        titlu = html.unescape(p["title"]["rendered"]).strip(" -–•")
        desc = text_din_html(p["content"]["rendered"])
        if not (e_job_potrivit(titlu) or RE_FUNCTIE_DESC.search(fara_diacritice(desc))):
            continue
        judet = next((judete[x] for x in p.get("pg_job_judet", []) if x in judete), None)
        if not judet:
            continue
        det = cache_get(f"posturi_{pid}", lambda: posturi_detalii(p["link"]), max_zile=7)
        orase = [cache_get(f"posturi_oras_{o}", lambda: html.unescape(fetch(f"{api}/pg_job_oras/{o}")["name"]))
                 for o in p.get("pg_job_oras", [])]
        orase = [o.title() if o.isupper() else o for o in orase]  # „BRAŞOV” -> „Braşov”
        zone = zone_din_orase(orase, judet_sigur=judet) or zone_din_orase([judet])
        dosar = termen_dosar(desc, p["date"])
        antet = [" · ".join(det["etichete"]),
                 "Contact: " + ", ".join(x for x in (det["email"], det["telefon"]) if x) if det["email"] or det["telefon"] else ""]
        joburi.append({
            "id": f"posturi:{pid}", "sursa": "posturi.gov.ro", "titlu": titlu,
            "firma": det["angajator"], "firma_confirmata": bool(det["angajator"]),
            "orase": orase or [judet], "zona": zone[0], "zone": zone,
            "url": p["link"], "salariu_text": "", "sal_min": None, "sal_max": None,
            "publicat": p["date_gmt"] + "Z", "expira": dosar or det["termen"], "termen_site": det["termen"], "termen_dosar": dosar,
            "descriere": "\n".join(x for x in antet if x) + "\n" + desc[:8000],
        })
    print(f"   posturi.gov.ro: {len(joburi)} posturi IT în zonele alese")
    return joburi


def sursa_anofm():
    """ANOFM (mediere.anofm.ro): locurile de muncă pe care firmele le anunță la AJOFM. Au aproape mereu salariul,
    emailul și telefonul angajatorului."""
    api = "https://mediere.anofm.ro/api/entity/vw_public_job_posting"
    randuri = []
    for judet in (9, 5, 2, 42):  # Brașov, Bacău, București, Ilfov
        pagina = 1
        while pagina <= 30:
            d = fetch(api, data={"current": pagina, "rowCount": 100, "sort": {"id": "desc"}, "county_id": judet})
            randuri += d.get("rows") or []
            if pagina * 100 >= (d.get("total") or 0) or not d.get("rows"):
                break
            pagina += 1

    joburi = []
    for r in randuri:
        titlu = din_majuscule(r.get("occupation") or "")
        if r.get("apprentice_qualification_name"):
            titlu += " - " + din_majuscule(r["apprentice_qualification_name"])
        desc = (r.get("description") or "").strip()
        if not e_job_potrivit_sau_text(titlu, desc):
            continue
        locuri = [x.strip() for x in (r.get("address_locality_name") or "").split(">")]
        judet = locuri[0].replace("Municipiul ", "")
        loc = din_majuscule(re.sub(r"^(MUNICIPIUL|ORAS|ORAȘ|COMUNA)\s+", "", locuri[-1] if len(locuri) > 1 else judet))
        loc = re.sub(r"(?i)^bucuresti sectorul", "București, Sectorul", loc)
        zone = zone_din_orase([" , ".join(locuri[1:])], judet_sigur=judet)
        if not zone:
            continue
        k = NET_DIN_BRUT if r.get("salary_type") == "gross" else 1
        lo = round(float(r["minimum_salary"]) * k) if r.get("minimum_salary") else None
        hi = round(float(r["maximum_salary"]) * k) if r.get("maximum_salary") else lo
        lo = lo or hi
        if not hi or hi < 2000:
            lo = hi = None
        contact = ", ".join(x for x in (r.get("contact_name"), r.get("contact_email"), r.get("contact_phone"))
                            if x and x.strip(" -"))
        antet = [f"Contact: {contact}" if contact else "",
                 f"Experiență cerută: {r['professional_experience_name']}" if r.get("professional_experience_name") else "",
                 f"Studii: {r['education_level_name']}" if r.get("education_level_name") else "",
                 " · ".join(x for x in (r.get("contract_type_name"), r.get("work_type_name"), r.get("work_regime_name")) if x),
                 f"Locuri: {r['open_positions']}" if r.get("open_positions") else "",
                 f"Selecție: {r['job_offer_closing_name']}" if r.get("job_offer_closing_name") else ""]
        if r.get("minimum_salary"):
            antet.append(f"Salariu: {r['minimum_salary']}" + (f" – {r['maximum_salary']}" if r.get("maximum_salary") else "")
                         + (" lei brut" if r.get("salary_type") == "gross" else " lei net"))
        nivel = r.get("professional_experience_name") or ""
        if "absolvent" in fara_diacritice(r.get("job_posting_target_name") or ""):
            nivel = "Absolvenți"
        joburi.append({
            "id": f"anofm:{r['id']}", "sursa": "ANOFM", "titlu": titlu,
            "firma": r.get("employer_name") or "", "firma_confirmata": bool(r.get("employer_name")),
            "orase": [loc], "zona": zone[0], "zone": zone,
            "url": f"https://mediere.anofm.ro/app/module/mediere/job/{r['id']}",
            "salariu_text": antet[-1].removeprefix("Salariu: ") if r.get("minimum_salary") else "",
            "sal_min": lo, "sal_max": hi,
            "publicat": (r.get("created_at") or "")[:10] or None, "expira": r.get("job_expiry_date"),
            "nivel_sursa": nivel, "hibrid_sursa": bool(re.search(r"telemunc|distanta|hibrid", fara_diacritice(r.get("work_regime_name") or ""))),
            "descriere": "\n".join(x for x in antet if x) + "\n" + desc[:4000],
        })
    print(f"   ANOFM: {len(randuri)} anunțuri, {len(joburi)} relevante")
    return joburi


def hipo_detalii(url):
    s = fetch(url, as_json=False)
    ld = next((json.loads(x, strict=False) for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', s, re.S)
               if '"JobPosting"' in x), {})
    desc = text_din_html(repara_codificare(ld.get("description") or ""))
    calif = text_din_html(ld.get("qualifications") or "")
    if calif and calif[:200] not in desc:
        desc += "\n" + calif
    desc = re.sub(r"#anunt-content[^}]*}", "", desc).strip()  # stilul paginii, lipit la finalul textului
    exp = re.match(r"\s*(\d+\s*-\s*\d+ ani|\d+\+? ani|fara experienta)", fara_diacritice(ld.get("experienceRequirements") or ""))
    adr = ((ld.get("jobLocation") or {}).get("address") or {})
    return {"descriere": desc, "experienta": exp.group(1) if exp else "", "publicat": ld.get("datePosted"),
            "localitate": (adr.get("addressLocality") or "").strip(" ,"), "tip": ld.get("employmentType") or ""}


def sursa_hipo():
    """Hipo.ro: site de joburi pentru tineri (multe posturi de junior). În Brașov și Bacău luăm tot, în București
    doar domeniile IT (altfel sunt prea multe pagini)."""
    base = "https://www.hipo.ro"
    carduri = {}
    cautari = [("Toate-Domeniile", "Brasov"), ("Toate-Domeniile", "Bacau"), ("IT-Software", "Bucuresti"),
               ("IT-Hardware", "Bucuresti")]
    continua = True
    for (domeniu, oras), pagina in ((c, p) for c in cautari for p in range(1, 11)):
        if pagina > 1 and not continua:
            continue
        s = fetch(f"{base}/locuri-de-munca/cautajob/{domeniu}/{oras}" + (f"/{pagina}" if pagina > 1 else ""),
                  as_json=False)
        gasite = 0
        for c in re.findall(r'<div class="job-item.*?(?=<div class="job-item|$)', s, re.S):
            m = re.search(r'class="job-title" href="(/locuri-de-munca/locuri_de_munca/(\d+)/[^"]*)">\s*<h5[^>]*>(.*?)</h5>', c, re.S)
            if not m:
                continue
            gasite += 1
            titlu = text_din_html(m.group(3))
            if m.group(2) in carduri or not e_job_potrivit(titlu):
                continue
            firma = re.search(r'company-name">\s*<span>(.*?)</span>', c, re.S)
            data = re.search(r'fa-calendar-alt[^>]*></i>\s*(\d\d)-(\d\d)-(\d{4})', c)
            locuri = [text_din_html(x) for x in re.findall(r'fa-map-marker-alt[^>]*></i>(.*?)</span>', c, re.S)]
            carduri[m.group(2)] = {"url": base + m.group(1), "titlu": titlu,
                                   "firma": text_din_html(firma.group(1)) if firma else "",
                                   "data": f"{data.group(3)}-{data.group(2)}-{data.group(1)}" if data else None,
                                   "locuri": locuri}
        continua = gasite and f"{oras}/{pagina + 1}" in s
    joburi = []
    for jid, c in carduri.items():
        zone = zone_din_orase(c["locuri"])
        if not zone:
            continue  # alt oraș
        try:
            det = cache_get(f"hipo_{jid}", lambda: hipo_detalii(c["url"]), max_zile=14)
        except Exception as e:  # noqa: BLE001
            print(f"   ! detalii Hipo {jid}: {e}")
            det = {"descriere": "", "experienta": ""}
        joburi.append({
            "id": f"hipo:{jid}", "sursa": "Hipo", "titlu": c["titlu"],
            "firma": c["firma"], "firma_confirmata": bool(c["firma"]),
            "orase": c["locuri"], "zona": zone[0], "zone": zone, "url": c["url"],
            "salariu_text": "", "sal_min": None, "sal_max": None,
            "publicat": c["data"] or det.get("publicat"), "expira": None,
            "nivel_sursa": det.get("experienta", ""),
            "descriere": ((f"Experiență: {det['experienta']}\n" if det.get("experienta") else "") + det["descriere"])[:4000],
        })
    print(f"   Hipo: {len(carduri)} anunțuri potrivite, {len(joburi)} în zonele alese")
    return joburi


def sursa_edujobs():
    """EduJobs: puține anunțuri proprii, dar preia și anunțurile de pe publi24.ro și jobradar24.ro."""
    api = "https://back-edujobs.feel-it-services.com/job-postings/query?favoritesFirst=false"
    gasite = {}
    cautari = [(kw, loc) for loc in ("Brasov", "Bacau", "Bucuresti") for kw in (
        "programator", "developer", "software", "it", "calculatoare", "suport tehnic", "helpdesk", "tester",
        "retea", "administrator", "informatician", "web", "data")]
    for kw, loc in cautari:
        for pagina in range(1, 6):
            d = fetch(api, data={"search": kw, "page": pagina, "limit": 100, "location": loc})
            for j in d.get("jobPostings") or []:
                gasite.setdefault(j["id"], (j, False))
            for j in d.get("scrapedJobs") or []:
                gasite.setdefault(j["scrapedJobId"], (j, True))
            if pagina * 100 >= max(d.get("totalJobPosting") or 0, d.get("totalScrapedJobs") or 0):
                break

    joburi = []
    for jid, (j, preluat) in gasite.items():
        titlu = (j.get("title") or "").strip()
        zone = zone_din_orase([j.get("location") or ""])
        desc = text_din_html(j.get("description") or "")
        if not zone or not e_job_potrivit_sau_text(titlu, desc):
            continue
        lo, hi = (int(float(j[k])) if str(j.get(k) or "").replace(".", "").isdigit() else None
                  for k in ("salaryMin", "salaryMax"))
        lo, hi = (lo or hi, hi or lo) if (hi or lo or 0) >= 2000 else (None, None)
        antet = [f"{e}: {j[k]}" for k, e in (("phone", "Telefon"), ("program", "Program"), ("study", "Studii"),
                                              ("experience", "Experiență")) if j.get(k) and j[k] != "None"]
        firma = "" if preluat else ((j.get("company") or {}).get("name") or "")
        url = j.get("originalUrl") if preluat else f"https://edujobs.ro/job-page/{jid}"
        sursa = "EduJobs" if not preluat else "publi24" if "publi24" in (url or "") else \
            "jobradar24" if "jobradar24" in (url or "") else "EduJobs"
        joburi.append({
            "id": f"edujobs:{jid}", "sursa": sursa, "titlu": titlu,
            "firma": firma, "firma_confirmata": bool(firma),
            "orase": [j.get("location") or ""], "zona": zone[0], "zone": zone, "url": url,
            "salariu_text": f"{lo} - {hi} lei" if hi else "", "sal_min": lo, "sal_max": hi,
            "publicat": j.get("date") or j.get("createdAt"), "expira": None,
            "nivel_sursa": j.get("experience") if j.get("experience") not in (None, "None") else "",
            "descriere": ("\n".join(antet) + "\n" + desc)[:4000],
        })
    print(f"   EduJobs / publi24: {len(gasite)} anunțuri găsite la căutare, {len(joburi)} potrivite în zonele alese")
    return joburi


def _camp(rx, s):
    m = re.search(rx, s, re.S)
    return text_din_html(m.group(1)) if m else ""


def linkedin_detalii(jid):
    s = fetch(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}", as_json=False)
    criterii = re.findall(r'job-criteria-subheader">(.*?)</h3>\s*<span class="description__job-criteria-text[^"]*">(.*?)</span>',
                          s, re.S)
    antet = [f"{text_din_html(k)}: {text_din_html(v)}" for k, v in criterii]
    nivel = next((text_din_html(v) for k, v in criterii if re.search(r"vechime|seniority", fara_diacritice(text_din_html(k)))), "")
    return {"descriere": "\n".join(antet) + "\n" + _camp(r'show-more-less-html__markup[^>]*>(.*?)</div>\s*(<button|</section>|$)', s),
            "nivel": nivel}


def sursa_linkedin():
    """LinkedIn, fără cont (căutarea publică). Caută „larg”, așa că filtrăm după titlu și localitate.
    Joburile remote le căutăm în toată țara; căutarea publică ignoră filtrul „Remote”, așa că un job din alt oraș
    rămâne doar dacă titlul sau textul spune clar că e remote („fully remote”, „100% remote”)."""
    api = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    carduri, erori = {}, []
    cc = CFG["cuvinte_cautare"]
    for loc, remote in [(l, False) for l in cc["linkedin_locatii"]] + [(cc["linkedin_remote"], True)]:
        for kw in cc["linkedin"]:
            for start in range(0, 60, 10):
                q = {"keywords": kw, "location": loc, "start": start}
                if remote:
                    q["f_WT"] = 2
                try:
                    s = fetch(api + "?" + urllib.parse.urlencode(q), as_json=False, retries=2 if start == 0 else 0)
                except Exception as e:  # noqa: BLE001 - după ultima pagină LinkedIn poate da eroare
                    if start == 0:
                        # o căutare refuzată (HTTP 429) nu oprește tot; dacă primele cinci pică, e blocat de tot
                        erori.append(str(e))
                        if len(erori) >= 5 and not carduri:
                            raise
                    break
                bucati = s.split('data-entity-urn="urn:li:jobPosting:')[1:]
                for c in bucati:
                    jid = c.split('"', 1)[0]
                    titlu = _camp(r'base-search-card__title">(.*?)</h3>', c)
                    if jid in carduri:
                        carduri[jid]["remote"] |= remote  # găsit întâi în oraș, apoi și la remote
                        continue
                    if not e_job_potrivit(titlu):
                        continue
                    carduri[jid] = {"titlu": titlu, "firma": _camp(r'base-search-card__subtitle">(.*?)</h4>', c),
                                    "loc": _camp(r'job-search-card__location">(.*?)</span>', c),
                                    "salariu": _camp(r'job-search-card__salary-info">(.*?)</span>', c),
                                    "data": (re.search(r'datetime="([\d-]+)"', c) or [None, None])[1],
                                    "remote": remote}
                if len(bucati) < 10:
                    break
        print(f"   LinkedIn {loc}{' (remote)' if remote else ''}: total {len(carduri)} relevante")

    if erori:
        print(f"   ! LinkedIn: {len(erori)} căutări refuzate ({erori[-1][:70]})")
    joburi, esuate_la_rand, amanate = [], 0, 0
    for jid, c in carduri.items():
        zone = zone_din_orase([c["loc"]])
        if not zone and not c["remote"]:
            continue  # alt județ din jur
        # când LinkedIn ne refuză (HTTP 429) multe cereri la rând, textul celor rămase se ia la rularea următoare
        if esuate_la_rand >= 8 and not (CACHE / f"linkedin_{jid}.json").exists():
            det, amanate = {"descriere": ""}, amanate + 1
        else:
            try:
                det = cache_get(f"linkedin_{jid}", lambda: linkedin_detalii(jid))
                esuate_la_rand = 0
            except Exception as e:  # noqa: BLE001
                print(f"   ! detalii LinkedIn {jid}: {e}")
                det, esuate_la_rand = {"descriere": ""}, esuate_la_rand + 1
        doar_remote = bool(RE_DOAR_REMOTE.search(fara_diacritice(c["titlu"])) or
                           RE_DOAR_REMOTE.search(fara_diacritice(det["descriere"])))
        if doar_remote:
            zone = [REMOTE] + zone
        if not zone:
            continue  # alt oraș, la birou
        lo, hi = parse_salariu(c["salariu"])
        joburi.append({
            "id": f"linkedin:{jid}", "sursa": "LinkedIn", "titlu": c["titlu"],
            "firma": c["firma"], "firma_confirmata": bool(c["firma"]),
            "orase": [c["loc"]], "zona": zone[0], "zone": zone, "url": f"https://ro.linkedin.com/jobs/view/{jid}",
            "salariu_text": c["salariu"], "sal_min": lo, "sal_max": hi,
            "publicat": c["data"], "expira": None, "nivel_sursa": det.get("nivel", ""), "hibrid_sursa": doar_remote,
            "descriere": det["descriere"][:4000],
        })
    if amanate:
        print(f"   ! LinkedIn refuză cererile: textul pentru {amanate} anunțuri se ia data viitoare")
    return joburi


def inca_potrivit(j):
    """Aceeași regulă ca la descărcare, ca o schimbare de reguli să scoată și anunțurile deja salvate."""
    if j["sursa"] == "posturi.gov.ro":
        return e_job_potrivit(j["titlu"]) or bool(RE_FUNCTIE_DESC.search(fara_diacritice(j.get("descriere", ""))))
    return e_job_potrivit_sau_text(j["titlu"], j.get("descriere", ""))


SURSE = {"ejobs": sursa_ejobs, "bestjobs": sursa_bestjobs, "olx": sursa_olx, "linkedin": sursa_linkedin,
         "edujobs": sursa_edujobs, "posturi": sursa_posturi, "anofm": sursa_anofm, "hipo": sursa_hipo}
# surse unde se aplică direct la angajator, cu emailul / telefonul scris; la dubluri, ele câștigă
SURSE_DIRECTE = {"posturi.gov.ro", "ANOFM"}


# --------------------------------------------------------------- recenzii

CUVINTE_JURIDICE = {"sc", "srl", "sa", "srld", "pfa", "com", "impex", "group", "grup", "romania",
                    "holding", "the", "si", "and", "co", "company", "international", "distribution",
                    "distributie", "rom", "prod", "ro", "ltd", "gmbh"}
# cuvinte care pot lipsi dintr-un nume fără să fie altă firmă
CUVINTE_EXTRA_OK = {"romania", "express", "expres", "trading", "retail", "logistic", "logistics", "services",
                    "service", "prodcom", "2", "exclusive", "global", "europe", "eu", "import", "export",
                    "corporation", "corp", "systems", "solutions", "industries", "industrial"}

def cheie_firma(nume):
    t = re.sub(r"\(.*?\)", " ", fara_diacritice(nume))
    for _ in range(3):  # „L.E.D”, „S.R.L.” -> „led”, „srl”
        t = re.sub(r"\b([a-z])\.(?=[a-z]\b)", r"\1", t)
    cuv = [w for w in re.findall(r"[a-z0-9]+", t) if w not in CUVINTE_JURIDICE]
    return " ".join(cuv)


class UndeLucram:
    BASE = "https://www.undelucram.ro/ro"

    def __init__(self):
        self.cookies = CACHE / "undelucram_cookies.txt"
        self.token = None

    def _token(self):
        if not self.token:
            s = fetch(self.BASE, as_json=False, cookies=self.cookies)
            m = re.search(r'name="csrf-token" content="([^"]+)"', s)
            if not m:
                raise RuntimeError("UndeLucram: nu găsesc tokenul de sesiune")
            self.token = m.group(1)
        return self.token

    def cauta(self, text):
        return fetch(f"{self.BASE}/autocomplete/organisations",
                     data={"value": text, "with_link": True, "with_id": True},
                     headers=[f"X-CSRF-TOKEN: {self._token()}", "X-Requested-With: XMLHttpRequest"],
                     cookies=self.cookies) or []

    def pagina(self, url, nume):
        """Nota, numărul de evaluări și % recomandări de pe pagina publică a firmei."""
        s = fetch(url, as_json=False)
        t = re.sub(r"<script.*?</script>|<style.*?</style>", "", s, flags=re.S)
        t = re.sub(r"\s*\n\s*", "\n", html.unescape(re.sub(r"<[^>]+>", "\n", t)))
        # pagina are și o listă laterală „Rating mai bun în industrie” cu notele ALTOR firme:
        # tăiem tot ce e după ea și cerem ca nota să vină imediat după numele firmei
        t = t.split("Rating mai bun")[0]
        # două formate: „Nume\n4,06\n786 evaluări” sau „Nume\n4,06\n80% recomandă…\n786\nEvaluări”
        m = re.search(r"\n" + re.escape(nume.strip()) + r"\n(\d,\d{1,2})\n(?:(\d+)% recomand[^\n]*\n)?(\d+)(?: evalu|\nEvalu)", t)
        return {"nota": float(m.group(1).replace(",", ".")) if m else None,
                "evaluari": int(m.group(3)) if m else 0,
                "recomanda_pct": int(m.group(2)) if m and m.group(2) else None,
                "url": re.sub(r"/prezentare-", "/evaluari-", url)}

    def potriveste(self, nume_firma, id_manual=None):
        cheie = cheie_firma(nume_firma)
        cuv = cheie.split()
        if not cuv:
            return None
        rezultate = self.cauta(" ".join(cuv[:2]))
        if len(cuv) > 1 and not rezultate:
            rezultate = self.cauta(cuv[0])
        candidati = []
        for r in rezultate:
            if id_manual and r.get("id") != id_manual:
                continue
            ck = cheie_firma(r["name"]).split()
            if not ck:
                continue
            comune = set(cuv) & set(ck)
            jac = len(comune) / len(set(cuv) | set(ck))
            # cuvintele în plus (de o parte sau alta) trebuie să fie generice: „Altex” ~ „Altex Romania”,
            # dar nu „Continental Fast Line” ~ „Continental Romania” sau „Profit Impex” ~ „Profit Point”
            extra_generice = (set(cuv) ^ set(ck)) <= CUVINTE_EXTRA_OK
            ok = bool(id_manual) or (len(cheie) >= 4 and (
                cheie == " ".join(ck) or jac >= 0.75 or (comune and extra_generice)))
            if ok:
                candidati.append((jac, r))
        if not candidati:
            return None
        # între candidații cu același prim cuvânt (ex. „Aquila Part Prod Com” vs „Aquila Spa”)
        # alegem pe cel mai asemănător, apoi pe cel cu cele mai multe păreri
        candidati.sort(key=lambda x: -x[0])
        detalii = []
        for jac, r in candidati[:3]:
            info = self.pagina(r["link"], r["name"])
            detalii.append((jac, info["evaluari"], r, info))
        detalii.sort(key=lambda x: (-round(x[0], 1), -x[1]))
        jac, _, r, info = detalii[0]
        return {"id": r["id"], "nume": r["name"], **info, "sigur": True}


def google_places(nume, oras):
    """Opțional: nota și ultimele recenzii de pe Google Maps, prin API-ul oficial Places (cheie în config)."""
    cheie = CFG.get("google_places_api_key")
    if not cheie:
        return None
    d = fetch("https://places.googleapis.com/v1/places:searchText",
              data={"textQuery": f"{nume} {oras}", "languageCode": "ro", "regionCode": "RO", "pageSize": 1},
              headers=[f"X-Goog-Api-Key: {cheie}",
                       "X-Goog-FieldMask: places.displayName,places.formattedAddress,places.rating,"
                       "places.userRatingCount,places.googleMapsUri,places.reviews"])
    p = (d.get("places") or [None])[0]
    if not p or not p.get("rating"):
        return None
    return {
        "nume": p.get("displayName", {}).get("text"), "adresa": p.get("formattedAddress"),
        "nota": p["rating"], "evaluari": p.get("userRatingCount", 0), "url": p.get("googleMapsUri"),
        "comentarii": [{"nota": r.get("rating"), "text": (r.get("text") or {}).get("text", "")[:600],
                        "cand": r.get("relativePublishTimeDescription", ""),
                        "autor": (r.get("authorAttribution") or {}).get("displayName", "")}
                       for r in p.get("reviews", [])[:5] if (r.get("text") or {}).get("text")],
    }


def actualizeaza_recenzii(db, fortat=False):
    """Caută reputația fiecărei firme cu anunțuri active. Rezultatele se păstrează 30 de zile."""
    firme = db.setdefault("firme", {})
    manual = {cheie_firma(k): v for k, v in CFG.get("recenzii_potrivire_manuala", {}).items()}
    de_cautat = {}
    for j in db["joburi"].values():
        if j["activ"] and j.get("firma_confirmata") and j.get("firma"):
            de_cautat.setdefault(cheie_firma(j["firma"]), j)
    ul = UndeLucram()
    noi = 0
    for cheie, j in de_cautat.items():
        f = firme.get(cheie) or {}
        vechime = zile_de_la(f.get("verificat_la", "2000-01-01T00:00:00+00:00"))
        if f and vechime < 30 and not fortat:
            continue
        m = manual.get(cheie)
        f = {"nume": j["firma"], "verificat_la": NOW, "undelucram": None, "google": None}
        try:
            if m != "nu":
                f["undelucram"] = ul.potriveste(j["firma"], id_manual=m if isinstance(m, int) else None)
        except Exception as e:  # noqa: BLE001
            print(f"   ! UndeLucram {j['firma']}: {e}")
            f["verificat_la"] = "2000-01-01T00:00:00+00:00"  # reîncercăm data viitoare
        try:
            f["google"] = google_places(j["firma"], (j.get("orase") or [""])[0])
        except Exception as e:  # noqa: BLE001
            print(f"   ! Google {j['firma']}: {e}")
        firme[cheie] = f
        noi += 1
        if noi % 20 == 0:
            print(f"   recenzii: {noi} firme verificate…")
    cu_nota = sum(1 for k in de_cautat if (firme.get(k) or {}).get("undelucram"))
    print(f"   Recenzii: {len(de_cautat)} firme, {cu_nota} găsite pe UndeLucram ({noi} verificate acum)")
    return len(de_cautat)


# ------------------------------------------------------------------ main

def main():
    DATA.mkdir(exist_ok=True)
    CACHE.mkdir(exist_ok=True)
    f_db = DATA / "joburi.json"
    db = json.loads(f_db.read_text(encoding="utf-8")) if f_db.exists() else {"joburi": {}, "rulari": []}

    # „reclasifica” = doar recalculează scorurile pe datele existente, fără descărcări
    alese = [a.lower() for a in sys.argv[1:] if not a.startswith("--")] or list(SURSE) + ["recenzii"]
    stare_surse = {}
    for nume in [a for a in alese if a in SURSE]:
        print(f"→ {nume}")
        try:
            gasite = SURSE[nume]()
        except Exception as e:  # noqa: BLE001
            print(f"   ✗ {nume} a eșuat: {e}")
            stare_surse[nume] = f"eroare: {e}"
            continue
        ids_acum = set()
        gasite = [j for j in gasite if inca_potrivit(j)]  # „QA Engineer” la o fabrică: se vede abia din text
        stare_surse[nume] = len(gasite)
        for j in gasite:
            vechi = db["joburi"].get(j["id"])
            j["prima_data"] = vechi["prima_data"] if vechi else NOW
            j["ultima_data"] = NOW
            j["activ"] = (j.get("expira") or "9999")[:10] >= NOW[:10]  # concursurile au termen, deși rămân pe site
            db["joburi"][j["id"]] = completeaza_salariu(j)
            ids_acum.add(j["id"])
        # ce nu mai apare la o sursă care a mers: expirat dacă i-a trecut data sau nu l-am mai văzut de 14 zile
        # (site-urile nu dau mereu toate rezultatele, deci o singură lipsă nu înseamnă că s-a închis)
        for jid, j in db["joburi"].items():
            if jid.startswith(nume + ":") and jid not in ids_acum:
                expira = (j.get("expira") or "9999")[:10]
                j["activ"] = expira >= NOW[:10] and (zile_de_la(j["ultima_data"]) or 0) < 14

    # anunțurile expirate de mult nu mai apar nicăieri; le scoatem ca pagina să se încarce repede
    # (la fel cu cele care nu mai trec de reguli după o schimbare în colector)
    for jid in [k for k, j in db["joburi"].items()
                if not inca_potrivit(j) or (not j["activ"] and (zile_de_la(j["ultima_data"]) or 0) > ZILE_PASTRARE_EXPIRATE)]:
        del db["joburi"][jid]

    if "recenzii" in alese:
        print("→ recenzii firme")
        try:
            stare_surse["recenzii"] = actualizeaza_recenzii(db, fortat="--fortat" in sys.argv)
        except Exception as e:  # noqa: BLE001
            print(f"   ✗ recenzii a eșuat: {e}")
            stare_surse["recenzii"] = f"eroare: {e}"

    firme = db.get("firme", {})
    for j in db["joburi"].values():  # reclasificăm tot, ca schimbările de reguli să se aplice și la cele vechi
        clasifica(j, firme)
        j["firma_cheie"] = cheie_firma(j.get("firma", "")) if j.get("firma_confirmata") else None
    marcheaza_dubluri(list(db["joburi"].values()))
    db["rulari"] = (db.get("rulari", []) + [{"data": NOW, "surse": stare_surse}])[-60:]
    db["actualizat"] = NOW
    db["zone"] = {z: v["eticheta"] for z, v in ZONE.items()}
    f_db.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")
    # pagina încarcă întâi lista (fără textele anunțurilor, care sunt cea mai mare parte), apoi textele separat
    fara_text = {**db, "joburi": {k: {c: v for c, v in j.items() if c != "descriere"} for k, j in db["joburi"].items()}}
    (DATA / "joburi.js").write_text("window.JOBURI = " + json.dumps(fara_text, ensure_ascii=False) + ";\n",
                                    encoding="utf-8")
    texte = {k: j.get("descriere", "") for k, j in db["joburi"].items()}
    (DATA / "descrieri.js").write_text("window.DESCRIERI = " + json.dumps(texte, ensure_ascii=False) + ";\n",
                                       encoding="utf-8")
    active = [j for j in db["joburi"].values() if j["activ"] and not j.get("dublura_lui") and not j["exclus"]]
    bune = [j for j in active if j["verdict"] == "Foarte potrivit"]
    print(f"\n✓ Gata. {len(active)} anunțuri potrivite, {len(bune)} „foarte potrivite”. Deschide index.html.")


if __name__ == "__main__":
    main()
