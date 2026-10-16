# Joburi IT: Brașov, Bacău, Moinești, București, Prahova și remote

Strânge zilnic anunțurile IT din Brașov și împrejurimi, Bacău, Moinești (cu Comănești, Dărmănești, Onești, Târgu Ocna),
București + Ilfov, Ploiești + județul Prahova și joburile remote din România:
- **programator / developer**: frontend, backend, full stack, mobile, Java, .NET, Python, PHP, JavaScript, embedded,
  ABAP, analist programator, inginer software;
- **IT support / helpdesk**: IT support, service desk, desktop support, tehnician IT / calculatoare, informatician,
  specialist IT, operator calculator (la stat);
- **sisteme, rețele, cloud, securitate**: system / network administrator, DevOps, cloud, inginer de sistem,
  securitate cibernetică, SOC;
- **QA / testare**: tester manual / automation, QA engineer;
- **date / BI**: data analyst / engineer, BI developer, DBA, business analyst IT.

Sursele sunt **eJobs, BestJobs, LinkedIn, OLX, EduJobs (+ publi24, jobradar24), posturi.gov.ro, ANOFM și Hipo**.
Fiecare anunț primește un scor și apare într-o pagină cu filtre (post, zonă, junior, salariu, anunțuri noi).

- `./actualizeaza.sh` descarcă anunțurile noi (prima dată durează mult; descrierile se țin apoi în cache).
- `index.html` se deschide în browser. Din Windows: `\\wsl$\Ubuntu\home\vladb\apps\it-joburi\index.html`,
  sau din WSL cu `explorer.exe index.html`.
- `config.json` conține zonele (localitățile, județele și bonusul fiecăreia), limbile străine pe care le știi,
  firmele preferate, cuvintele de căutare și cursul EUR.

## Surse
| Sursă | Ce are | Cum se aplică |
|---|---|---|
| eJobs, BestJobs | cele mai multe anunțuri: firme de software, centre de servicii, firme mici | cont gratuit pe site |
| LinkedIn | multinaționale și firme de software; plus căutarea „Remote” pentru toată țara (fără cont) | cont LinkedIn sau site-ul firmei |
| OLX | anunțuri mici (tehnician IT, helpdesk, programator la firme mici) | de obicei se sună direct |
| EduJobs | anunțurile preluate de pe publi24.ro și jobradar24.ro | publi24: de obicei telefon |
| posturi.gov.ro | concursuri la stat: primării, spitale, școli, ministere (informatician, administrator rețea) | dosar la instituție, până la data limită |
| ANOFM | locurile de muncă anunțate la AJOFM, aproape mereu cu salariu, email și telefon | CV pe email sau telefon |
| Hipo | joburi pentru tineri și absolvenți | cont gratuit pe site |

Un job intră doar dacă titlul cere unul dintre posturile de mai sus. Nu intră: programator CNC / PLC / producție,
recrutori IT, vânzări de IT, marketing, designeri, profesori de informatică, consultanți SAP funcționali,
„joburile” de antrenat AI (contributor, annotator). Titlurile care pot fi și altă meserie („QA Engineer” la o fabrică,
„System Engineer”, „Business Analyst”) intră doar dacă textul anunțului vorbește de IT (server, Windows, SQL, Jira…).
La anunțurile mici cu titlu general („Ofertă loc de muncă”) se citește meseria din prima frază („Angajăm programator…”).
La concursurile de la stat se citește din text data limită pentru dosar, iar după ea anunțul apare ca expirat.

## Cum se calculează scorul (pornește de la 50, limitat la 0–100)
| Criteriu | Puncte |
|---|---|
| În una din zonele alese (bonusul fiecărei zone se schimbă în `config.json`) | +10 |
| Potrivit pentru junior (titlu, „fără experiență”, ≤1 an cerut, nivelul bifat pe site) | +6 |
| Cere 2–4 ani de experiență / post de senior (≥5 ani, „senior”, „lead”, „architect” în titlu) | −3 / −8 |
| Cere o limbă străină pe care nu o știi (în titlu / în text) | −10 / −6 |
| Program de zi, L–V / ture, noapte, weekend | +8 / −12 |
| Se poate lucra și de acasă (hibrid / remote) | +4 |
| Contract pe perioadă determinată | −6 |
| Abonament medical / tichete de masă / firma plătește cursuri și certificări (AWS, Azure, ISTQB, CCNA…) | +4 / +2 / +3 |
| Salariu net ≥15000 / ≥11000 / ≥8000 / ≥5500 / <3500 lei | +12 / +9 / +6 / +2 / −6 |
| Firmă preferată / agenție de recrutare | +8 / −6 |
| Nota angajaților pe UndeLucram ≥4 / ≥3,5 / ≥3 / ≥2,5 / mai mică (jumătate dacă are sub 5 păreri) | +8 / +4 / 0 / −6 / −10 |
| Nota clienților pe Google (doar cu cheie API) | ±2 |
| Anunț mai vechi de 45 de zile | −4 |

Verdict: **Foarte potrivit** ≥80, **Potrivit** ≥65, **Merită verificat** ≥50, **Slab** sub 50 (ascuns).
Ascunse automat (se văd din „Setări avansate” → „Arată și”): posturi de conducere (șef, manager, director, team
leader), internship-uri și joburi în străinătate. „Tech lead” nu e considerat conducere, ci post de senior.

Nivelul se ia întâi din titlu („Junior”, „Mid”, „Senior”, „Lead”), apoi din text („fără experiență”,
„minimum 3 years of experience”), apoi din ce a bifat firma pe site (eJobs, LinkedIn, ANOFM, Hipo).
Limbile: în `config.json` → `limbi_straine_cunoscute` (implicit doar engleza). Dacă știi germană, adaug-o acolo și
joburile „with German” nu mai pierd puncte. „Cunoașterea limbii germane constituie un avantaj” nu scade nimic.

Zona **Remote** are joburile marcate „de acasă” de site (eJobs, BestJobs, Hipo) și căutarea LinkedIn cu filtrul
„Remote” în toată România; un job din București care se poate face și remote apare la ambele zone.

## Recenzii firme
- **UndeLucram.ro**: nota angajaților, numărul de păreri. Se caută automat după numele firmei și se reîmprospătează la 30 de zile.
  Comentariile de acolo se văd doar cu cont, așa că pagina dă link spre ele.
  Dacă o firmă e legată greșit, se corectează în `config.json` → `recenzii_potrivire_manuala` (id UndeLucram sau `"nu"`).
- **Google Maps** (opțional): nota clienților și ultimele 5 comentarii prin API-ul oficial Google Places.
  Pune cheia în `config.json` → `google_places_api_key`, apoi rulează `python3 colector.py recenzii --fortat`.

## Comenzi
- `python3 colector.py`: totul (anunțuri + recenzii)
- `python3 colector.py anofm hipo`: doar unele surse (`ejobs`, `bestjobs`, `olx`, `linkedin`, `edujobs`, `posturi`, `anofm`, `hipo`)
- `python3 colector.py recenzii --fortat`: reface recenziile
- `python3 colector.py reclasifica`: recalculează scorurile după o schimbare de reguli, fără descărcări

Salvatele, aplicările și notițele stau în browser (localStorage); „Setări avansate” → „Salvează notițele” face o copie.
Anunțurile expirate se șterg după 30 de zile, ca pagina să se încarce repede.
Indeed, Jooble, Glassdoor și Careerjet blochează accesul automat („Security Check”), așa că nu sunt incluse.
MyJob are acum aproape numai joburi în străinătate, iar Talent.com nu avea nimic pentru Brașov. No Fluff Jobs nu mai are anunțuri pentru România.

## Online
- Site: https://vladbranoiu.github.io/joburi-it/ (GitHub Pages, din branch-ul `main`).
- **GitHub Actions** (`.github/workflows/actualizare.yml`) rulează zilnic la 04:20 UTC: eJobs, BestJobs, LinkedIn, EduJobs,
  posturi.gov.ro, ANOFM, Hipo și recenziile. Se poate porni și manual din tabul Actions → „Actualizare anunțuri” → Run workflow.
- **OLX blochează serverele GitHub, iar eJobs le refuză des** (HTTP 403), așa că amândouă se iau și de pe PC: sarcina Windows
  „Joburi IT - OLX” (zilnic la 10:15 și la logare) rulează `sincronizare-olx.sh` într-o copie separată
  (`~/.local/share/joburi-it-sync`). Jurnal: `~/.local/share/joburi-it-sync.log`.
  Dacă PC-ul stă oprit, anunțurile OLX (și cele eJobs, când pică și pe GitHub) dispar treptat în 14 zile
  (sau la data lor de expirare), iar restul merge normal.
- Înainte să modifici ceva local: `git pull` (datele se schimbă zilnic pe GitHub).
