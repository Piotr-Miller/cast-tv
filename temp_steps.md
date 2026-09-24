# Wiersz 5.10 (s13-gopro-auth) na laptopie z Windows 11 — kroki

Plik tymczasowy na gałęzi (żeby dało się go odczytać na laptopie); do usunięcia przed merge PR #40.

## Gałąź

- **`s13-gopro-auth-spike`** (PR #40), głowa `a411c6e`. Tylko na tej gałęzi jest skrypt `phase5-windows.ps1`,
  plan i research tej zmiany; `main` jest chroniony i nic z S-13 na nim nie ma.
- **Laptop (Windows):** checkout nie jest potrzebny. Testowany jest artefakt `cast-tv-windows-x64.exe` z release run
  36049997670 (zbudowany z commitu `d14deaa` tej gałęzi; kod jest ten sam co w `2bce9dc` i `a411c6e`, które dodały
  tylko pliki w `context/`), a skrypt pobiera się z raw URL tej gałęzi (polecenie niżej).
- **Fedora (sesja Claude, po powrocie):** w `~/Source/cast-tv` musi być ta gałąź:
  ```bash
  git checkout s13-gopro-auth-spike && git pull --ff-only && git log --oneline -1   # a411c6e
  ```

## Na laptopie

1. W przeglądarce zalogowanej na GitHub otwórz:
   https://github.com/Piotr-Miller/cast-tv/actions/runs/36049997670
   Sekcja **Artifacts** → kliknij `cast-tv-windows-x64.exe` (pobiera się zip).

2. Otwórz PowerShell w folderze z tym zipem (np. Pobrane) i wklej po kolei:

   ```powershell
   Expand-Archive .\cast-tv-windows-x64.exe.zip -DestinationPath . -Force
   curl.exe -sLO https://raw.githubusercontent.com/Piotr-Miller/cast-tv/s13-gopro-auth-spike/context/changes/s13-gopro-auth/phase5-windows.ps1
   powershell -ExecutionPolicy Bypass -File .\phase5-windows.ps1
   ```

3. Skrypt prowadzi żółtymi komunikatami. Kolejność, którą wymusza: 5.4 (Cancel), 5.5 (zamknij okno gopro.com jego X),
   5.7 (zamknij czarne okno konsoli cast-tv jego X, gdy okno gopro.com jest otwarte), 5.3 + 5.9 (zaloguj się w oknie;
   pytanie o dymek „Save password?”), 5.6 (skrypt sam ustawia `CAST_TV_BROWSER=C:\nonexistent.exe`; wklej token
   z własnej przeglądarki: F12 → Application → Storage → Cookies → https://gopro.com → `gp_access_token`).
   Na pytania odpowiadaj `y`/`n` lub słowem. Okno PowerShella ze skryptem ma zostać otwarte cały czas.
   Skrypt sam sprawdza hash exe (ma być `0d22f1d7…`), drukuje `--version`, liczy procesy przeglądarki z profilem
   `gopro-browser` (zamiast Menedżera zadań) i mierzy czasy. Tokena nie czyta ani nie zapisuje.

4. Na końcu wklej do sesji Claude zawartość pliku `phase5-windows.log` (leży obok exe). Jeśli coś poszło inaczej niż
   skrypt zapowiadał (np. okno gopro.com nie zamknęło się razem z konsolą w 5.7), dopisz, co widziałeś.

## Po powrocie na Fedorę

- Sesja Claude: `/10x-implement s13-gopro-auth phase 5` (jeśli po `/clear`) i wklej log.
- cast-tv z żywą sesją z okna (pid 1281835, port 8895) został uruchomiony w tle; zatrzymanie:
  `pkill -INT -f "castlib --no-browser"`.
- Otwarte wiersze po 5.10: 5.11 i 5.12 (przy pierwszym banerze „cast-tv couldn't access your GoPro media with this
  session”: naciśnij **Open gopro.com again** i zapisz, czy okno zamknęło się bez pisania, czy prosiło o logowanie;
  skopiuj tekst karty Diagnostics).
