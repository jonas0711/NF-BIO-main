# Sweetspot Data Håndtering
*Nordisk Film Biografer - Aalborg City Syd*

## Indholdsfortegnelse
- [Overblik](#overblik)
- [Funktioner](#funktioner)
- [Systemkrav](#systemkrav)
- [Installation](#installation)
- [Brug af programmet](#brug-af-programmet)
- [Database struktur](#database-struktur)
- [Sikkerhed](#sikkerhed)
- [Fejlfinding](#fejlfinding)
- [Udvikling](#udvikling)
- [Licens](#licens)

## Overblik
Sweetspot Data Håndtering er et specialudviklet program til Nordisk Film Biografer, designet til at håndtere og spore produktdata med særligt fokus på udløbsdatoer. Programmet muliggør nem import af data fra PDF-filer og billeder, lokal databasehåndtering og automatisk synkronisering med Dropbox.

## Funktioner
- **Data Import**: 
  - Automatisk udtrækning af produktdata fra PDF-filer
  - Vision AI scanning af håndskrevne udløbsdatolister
- **Databaser**: Lokal SQLite database med automatisk backup
- **Dropbox Integration**: Automatisk synkronisering med cloud storage
- **Brugervenlig GUI**: Intuitiv grafisk brugerflade med:
  - Filtreringsmuligheder
  - Sortering af data
  - Farvekodning af udløbsdatoer
  - Kontekstmenuer til hurtig redigering
  - Progress bar for alle operationer
- **Data Administration**:
  - Tilføj nye produkter manuelt
  - Rediger eksisterende produkter
  - Slet produkter
  - Fortryd-funktion for alle handlinger
  - Ryd eller nulstil database med automatisk backup
- **Vision AI Integration**:
  - Scan håndskrevne udløbsdatolister
  - Automatisk genkendelse af produktnavne og datoer
  - Intelligent datoformatering
  - Høj præcision billedanalyse
- **Sikkerhedskopiering**: Automatisk backup før kritiske operationer

## Systemkrav
- Windows 10 eller nyere
- Minimum 4 GB RAM
- 500 MB ledig diskplads
- Internetforbindelse (for Dropbox-synkronisering)
- Skærmopløsning minimum 1280x720

## Installation

### Slutbruger Installation
1. Download `SweetspotSetup_v1.0.exe` fra den officielle distributions-kanal
2. Dobbeltklik på installationsfilen
3. Følg installationsguiden
4. Programmet installeres som standard i `%localappdata%\Sweetspot Data Håndtering`
5. En genvej oprettes på skrivebordet (valgfrit)

4. Konfigurer OpenAI API nøgle:
   - Opret `.env` fil i installationsmappen
   - Tilføj `OPENAI_API_KEY=din-api-nøgle`
   - Eller brug den indbyggede API nøgle dialog

### Udviklingsinstallation
1. Klon repository:
```bash
git clone [repository-url]
```

2. Opret virtuelt miljø:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Installer afhængigheder:
```bash
pip install -r requirements.txt
```

## Brug af programmet

### Første gang
1. Start programmet via genvejen eller den installerede .exe fil
2. Programmet opretter automatisk nødvendige mapper i Documents
3. Der oprettes en tom database hvis ingen eksisterende findes

### Vision AI Scanning
1. Klik på "Upload Udløbsdatoliste (Billede)" i Fil-menuen
2. Vælg et billede af en håndskrevet udløbsdatoliste
3. Vent mens Vision AI analyserer billedet:
   - Progress bar viser fremskridt
   - Statuslinje viser aktuel handling
4. Kontroller de scannede data i tabellen
5. Brug Fortryd hvis nødvendigt

### PDF Import
1. Klik på "Upload PDF-fil"
2. Vælg PDF-fil med produktdata
3. Vent på behandling (fremskridtsindikator vises)
4. Kontroller de importerede data i tabellen

### Dropbox Synkronisering
1. Klik på "Synkroniser med Dropbox" for at uploade
2. Klik på "Hent database fra Dropbox" for at downloade
3. Bekræft handlingen i dialogboksen

### Produkthåndtering
- **Tilføj produkt**: Klik på "Tilføj række" og udfyld formularen
- **Rediger produkt**: Højreklik på produkt og vælg "Rediger"
- **Slet produkt**: Højreklik på produkt og vælg "Slet"
- **Fortryd handling**: Klik på "Fortryd" knappen

### Filtrering og søgning
1. Vælg kolonne i dropdown-menuen
2. Indtast søgeord i søgefeltet
3. Tabellen opdateres automatisk med filtrerede resultater

## Database struktur

### Tabel: products
| Kolonne | Type | Beskrivelse |
|---------|------|-------------|
| UniqueID | INTEGER | Primær nøgle, auto-increment |
| ProductID | TEXT | Produkt identifikation |
| SKU | TEXT | Stock Keeping Unit |
| Article Description Batch | TEXT | Produktbeskrivelse |
| Expiry Date | TEXT | Udløbsdato (DD.MM.YYYY) |
| EAN Serial No | TEXT | EAN/stregkode |
| Remark | TEXT | Bemærkninger |
| Order QTY | TEXT | Ordreantal |
| Ship QTY | TEXT | Leveringsantal |
| UOM | TEXT | Unit of Measure |
| PDF Source | TEXT | Kilde PDF-fil |

## Sikkerhed
- Krypterede Dropbox credentials
- Sikker håndtering af OpenAI API nøgle
- Automatisk backup før kritiske operationer
- Sikker SSL/TLS kommunikation
- Lokal database med begrænset adgang

## Fejlfinding

### Almindelige problemer

#### Vision AI scanning fejler
- Kontroller OpenAI API nøgle i .env fil
- Verificer at billedet er læsbart og under 20MB
- Check internetforbindelse
- Se logfil for detaljerede fejlbeskeder

#### PDF Import fejler
- Kontroller at PDF'en ikke er beskyttet
- Verificer PDF-format
- Check diskplads

#### Dropbox synkronisering fejler
- Kontroller internetforbindelse
- Verificer Dropbox credentials
- Check firewall-indstillinger

#### Database fejl
- Check skriverettigheder i Documents-mappen
- Verificer databasens integritet
- Gendan fra backup hvis nødvendigt

### Logfiler
- Placering: `Documents\Sweetspot Data Håndtering\sweetspot.log`
- Indeholder detaljerede fejlbeskrivelser
- Bør vedlægges ved support-henvendelser

## Udvikling

### Bygning af executable
1. Installer PyInstaller:
```bash
pip install pyinstaller
```

2. Byg executable:
```bash
pyinstaller sweetspot_app.spec
```

### Kodestruktur
- `app.py`: Hovedapplikation og GUI
- `config.py`: Konfiguration og konstanter
- `crypt.py`: Krypteringsfunktioner
- `secure_dropbox_auth.py`: Dropbox authentication
- `.env`: Miljøvariabler og API nøgler

## Licens
© 2024 Nordisk Film Biografer. Alle rettigheder forbeholdes.

---
*Dette dokument blev sidst opdateret: Oktober 2024*
