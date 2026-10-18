# Kroki tymczasowe (2026-10-18, po scaleniu PR #61)

Stałe miejsce na kroki przy przerwie w pracy (restart, zmiana maszyny): zostaje w repo i jest
nadpisywany przy następnej takiej sytuacji.

## S-12: stan

- Phase 1 („The window owns the session”) jest na `main` jako `1083431` (PR #61, rebase). Kod
  identyczny z `a33a8a0` z gałęzi.
- Księgowość, która nie trafiła do PR #61 (SHA w Progress przepisane na `1083431`, zadeklarowane
  pliki ręcznych wierszy, notatka i pełny log 1.8), jest w małym PR z gałęzi
  `s12-desktop-window` - czeka na scalenie.
- Ręczne wiersze: 1.8 był zaakceptowany przy `d2dd0ca`, ale rebase usunął ten commit z historii,
  więc jest „unverifiable” i wymaga ponownego potwierdzenia; 1.9-1.16 czekają.

## S-12: następne kroki

1. **Ty:** scal mały PR z księgowością (rebase).
2. **Claude, potem:** nowa gałąź od świeżego `main`. Potwierdzenia (1.8 ponownie i 1.9-1.16)
   zapisuję przy SHA z `main` i wszystkie naraz jednym commitem - wtedy kolejny rebase merge ich
   nie unieważni (zapisany SHA zostaje w historii `main`).
3. **Ty, na laptopie z Windows** - ręczne wiersze. W PowerShell:
   ```powershell
   cd C:\Source\cast-tv
   & $env:TEMP\ctv-win\Scripts\Activate.ps1
   cast-tv
   ```
   Jeśli venv zniknął po restarcie:
   ```powershell
   cd C:\Source\cast-tv
   python -m venv $env:TEMP\ctv-win
   & $env:TEMP\ctv-win\Scripts\Activate.ps1
   pip install -e ".[window]"
   cast-tv
   ```
   - **1.16 (telefon):** na telefonie otwórz **http://192.168.50.213:8895/ui/** (karta Wi-Fi 2
     laptopa; jeśli nie działa, użyj adresu `192.168.50.…`, który wypisał PowerShell - nie
     `http://192.168.16.1:8895/ui/`, to wirtualna karta vEthernet). Oczekiwane: UI działa jak
     dotąd (wybierz film i odtwórz), w nagłówku po prawej **nie ma** przycisku „Quit cast-tv”.
   - **1.13:** film gra na TV. Zamknij **okno cast-tv** przyciskiem X. Oczekiwane: TV przestaje
     grać w ciągu 5 s, PowerShell wypisuje `Stopped.` i wraca prompt.
   - **1.15:** w tym samym PowerShell znowu `cast-tv`. Kliknij okno PowerShell, żeby zasłoniło
     okno cast-tv. Otwórz **drugi** PowerShell i wpisz:
     ```powershell
     cd C:\Source\cast-tv
     & $env:TEMP\ctv-win\Scripts\Activate.ps1
     cast-tv
     ```
     Oczekiwane: okno cast-tv wychodzi na wierzch, drugi PowerShell wypisuje
     „Its window is in front.” i od razu oddaje prompt. Potem zamknij okno cast-tv X.
   - **1.11:** w pierwszym PowerShell `cast-tv --no-window`. Oczekiwane: karta przeglądarki
     **http://127.0.0.1:8895/ui/** zamiast okna, w nagłówku karty jest „Quit cast-tv”. Zakończ
     Ctrl+C w oknie PowerShell.
   - **1.14 (Ctrl+C):** `cast-tv`, zacznij film z okna cast-tv, potem Ctrl+C **w oknie
     PowerShell**. Oczekiwane: TV staje, okno cast-tv się zamyka.
   - **1.14 (wylogowanie) - na samym końcu:** zapisz pracę. `cast-tv`, zacznij film z okna
     cast-tv. Start → ikona konta → **Wyloguj**, bez zamykania cast-tv. Po ponownym zalogowaniu:
     czy TV przestał grać? W PowerShell:
     ```powershell
     Get-Process cast-tv -ErrorAction SilentlyContinue
     ```
     Oczekiwane: nic nie zwraca. Wylogowanie zamyka też sesję Claude Code - wróć przez
     `claude --resume`.
4. **Ty, na Fedorze** - w terminalu, w checkoucie cast-tv:
   ```bash
   git switch main && git pull
   ```
   - **1.10 (bez extra):**
     ```bash
     pipx install --force "$PWD"
     cast-tv
     ```
     Oczekiwane: karta przeglądarki **http://127.0.0.1:8895/ui/** z przyciskiem „Quit cast-tv”
     w nagłówku po prawej. Zacznij film i kliknij „Quit cast-tv”: TV staje, karta pokazuje
     „cast-tv has ended; you can close this tab.”, w terminalu wraca prompt.
   - **1.9 (z extra):**
     ```bash
     pipx install --force "$PWD[window]"
     cast-tv
     ```
     Oczekiwane: okno Qt zatytułowane cast-tv z UI (nie karta przeglądarki).
   - **1.14 (kill):** w oknie cast-tv zacznij film. W **drugim** terminalu:
     ```bash
     pgrep -af cast-tv
     kill <pid z pierwszej kolumny>
     ```
     Oczekiwane: TV staje, okno cast-tv się zamyka, w pierwszym terminalu wraca prompt.
   - **1.12:**
     ```bash
     CAST_TV_WINDOW_FAIL=1 cast-tv
     ```
     Oczekiwane: karta przeglądarki zamiast okna; terminal wypisuje
     „No cast-tv window (unavailable: CAST_TV_WINDOW_FAIL); the UI opens in the browser…”;
     w karcie **Diagnostics** (prawy górny róg) jest `window_unavailable`.
5. Przy każdym wierszu napisz Claude, co zobaczyłeś (także gdy wyszło inaczej). Claude zapisuje
   obserwację w `research.md`, sprawdza `--check-recordable` i dopiero wtedy odhacza.
6. Potem: `/rune-impl-review s12-desktop-window phase 1` (osobna sesja), następnie
   `/rune-implement s12-desktop-window phase 2`.

## Do decyzji, bez pośpiechu

- **Fedora:** czy usuwam dysk VM w `~/.cache/cast-tv-s12-spike` (7,1 GB, VM zatrzymana) i
  20 obrazów podman `localhost/spike-*`.
- **Windows:** czy usuwam `.venv-spike`, `build` i `dist` w
  `C:\Source\cast-tv\context\changes\s12-desktop-window\spike-kit` (ignorowane przez git, 1,2 GB).
- Czy usuwam `C:\Source\cast-tv\temp_steps-2026-10-13.md` (stara notatka, nieśledzona).

## S-13: wiersze 5.11 i 5.12, gdy GoPro pierwszy raz odrzuci sesję (Windows)

Sesja z okna Edge jest z 2026-10-12 22:55, a cookie wygasa **2026-10-19 około 22:55**. Do
2026-10-18 GoPro nie odrzuciło jej ani razu (`first_401_at` puste).

1. W PowerShellu:
   ```powershell
   cd $HOME\Downloads\s13-row-5.10
   $env:CAST_TV_BROWSER='C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
   .\cast-tv-windows-x64.exe
   ```
2. W karcie cast-tv kliknij zakładkę **GoPro**:
   - jeśli jest lista, sesja jeszcze działa. Ctrl+C w oknie PowerShell i spróbuj później;
   - jeśli jest baner **„cast-tv couldn't access your GoPro media with this session”**, zanotuj
     datę i godzinę i przejdź do punktu 3.
3. **Zanim cokolwiek klikniesz**, otwórz **Diagnostics** (prawy górny róg) i skopiuj cały tekst
   karty GoPro. To jest wiersz 5.12.
4. Kliknij **Open gopro.com again** i zanotuj, czy okno Edge zamknęło się samo, czy prosiło o
   zalogowanie. To jest wiersz 5.11.
5. Ctrl+C w oknie PowerShell i przekaż Claude datę, tekst z Diagnostics i wynik z punktu 4.

## Jak wrócić do pracy z Claude

Napisz „co dalej” w `C:\Source\cast-tv`, na gałęzi `s12-desktop-window`.
