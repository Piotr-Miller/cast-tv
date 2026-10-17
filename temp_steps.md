# Kroki tymczasowe (2026-10-18)

Stałe miejsce na kroki przy przerwie w pracy (restart, zmiana maszyny): zostaje w repo i jest
nadpisywany przy następnej takiej sytuacji.

## S-12: stan

Pomiar na Windows 11 zrobiony 2026-10-18 (`context/changes/s12-desktop-window/research.md`,
ostatnia sekcja; `frame.md`, Discriminator Check). Edge `--app`, pywebview/WebView2 (exe 12,8 MB)
i pywebview + PySide6 (exe 227 MB) przeszły. Wszystkie wiersze Discriminator Check są zamknięte.

## S-12: następne kroki

1. **Ty, w `/rune-plan s12-desktop-window`:** rozstrzygnij trzy decyzje PRD z `frame.md` (sekcja
   Confidence):
   - instalatory i ikona (`prd.md:175`);
   - „nic nie instalujesz” na Linuksie i lista zależności (`prd.md:59`, `prd.md:156`);
   - lista platform i macOS (`prd.md:154`, `prd.md:175`).
2. **Ty, na Fedorze:** zdecyduj, czy usuwam pozostałości:
   - dysk VM w `~/.cache/cast-tv-s12-spike` (7,1 GB, VM zatrzymana);
   - 20 obrazów podman `localhost/spike-*`.
3. **Ty, na Windows:** zdecyduj, czy usuwam `.venv-spike`, `build` i `dist` w
   `context\changes\s12-desktop-window\spike-kit` (ignorowane przez git, 1,2 GB).

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

Napisz „co dalej” w checkoucie `cast-tv`, na gałęzi `s12-desktop-window`.
