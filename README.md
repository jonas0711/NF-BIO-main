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
Sweetspot Data Håndtering er et specialudviklet program til Nordisk Film Biografer, designet til at håndtere og spore produktdata med særligt fokus på udløbsdatoer. Programmet muliggør nem import af data fra PDF-filer, lokal databasehåndtering og automatisk synkronisering med Dropbox.

## Funktioner
- **PDF Import**: Automatisk udtrækning af produktdata fra PDF-filer
- **Databaser**: Lokal SQLite database med automatisk backup
- **Dropbox Integration**: Automatisk synkronisering med cloud storage
- **Brugervenlig GUI**: Intuitiv grafisk brugerflade med:
  - Filtreringsmuligheder
  - Sortering af data
  - Farvekodning af udløbsdatoer
  - Kontekstmenuer til hurtig redigering
- **Data Administration**:
  - Tilføj nye produkter manuelt
  - Rediger eksisterende produkter
  - Slet produkter
  - Fortryd-funktion for alle handlinger
- **Automatisk E-mail Rapport**: Daglig e-mail med udløbende produkter
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
- Automatisk backup før kritiske operationer
- Sikker SSL/TLS kommunikation med Dropbox
- Lokal database med begrænset adgang

## Fejlfinding

### Almindelige problemer

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
- `daily-email-report.py`: E-mail rapport system

## Licens
© 2024 Nordisk Film Biografer. Alle rettigheder forbeholdes.

---
*Dette dokument blev sidst opdateret: Oktober 2024*
