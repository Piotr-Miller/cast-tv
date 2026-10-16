# S-12: kroki tymczasowe (2026-10-16)

Stałe miejsce na kroki przy przerwie w pracy (restart, zmiana maszyny): zostaje w repo i jest nadpisywany przy następnej takiej sytuacji. Stan: frame gotowy (`context/changes/s12-desktop-window/frame.md`),
pomiary na Linuksie zrobione (`research.md`, trzecia sekcja). Otwarta zostaje tylko weryfikacja na
Windows 11.

## Przed restartem

Nic więcej. Logi pomiarów są skopiowane do
`~/.cache/cast-tv-s12-spike/logs/spike-logs-2026-10-16.tar.gz`, bo scratchpad sesji (`/tmp`) znika
przy restarcie. Zestaw na Windows jest na gałęzi `origin/s12-desktop-window` (commit `be4885b`).

## Na Windows 11 (Ty)

W PowerShellu, w checkoutcie `cast-tv`:

```powershell
git fetch origin
git switch --track origin/s12-desktop-window
cd context\changes\s12-desktop-window\spike-kit
py -3 run_spike.py
```

- Potrzebny internet (pip). Kilka okien otworzy się i zamknie samo.
- Kolejność: Edge `--app` → venv i pip (pywebview, PySide6, PyInstaller) → pywebview bez budowania →
  pywebview jako onefile → pywebview + PySide6 jako onefile.
- Wynik: `context\changes\s12-desktop-window\spike-kit\results.txt`. Zachowaj jego zawartość, np.
  wklej do notatki albo wyślij sobie.
- Jeśli pip lub pythonnet padnie na Pythonie 3.14, to też jest wynik, który trafi do `results.txt`.

## Po powrocie na Fedorę

1. **Ty:** otwórz sesję w `~/Source/cast-tv` (`claude --continue` albo nowa sesja; stan S-12 jest w
   pamięci) i wklej zawartość `results.txt`.
2. **Ja:** zapiszę wynik Windows w `research.md` i w Discriminator Check w `frame.md`, potem zadam
   pytanie z kroku 7 frame'a (przekazanie do `/rune-plan s12-desktop-window`).
3. **Zrobione:** `change.md`, `research.md` i `frame.md` zcommitowane i wypchnięte (`1bb3849`); wynik
   z Windows pójdzie osobnym commitem.
4. **Ty:** zdecyduj, czy usuwam pozostałości:
   - dysk VM w `~/.cache/cast-tv-s12-spike` (7,1 GB, VM zatrzymana);
   - 20 obrazów podman `localhost/spike-*`.
5. **Ty, w `/rune-plan`:** rozstrzygnij trzy decyzje PRD z `frame.md` (sekcja Confidence):
   - instalatory i ikona (`prd.md:175`);
   - „nic nie instalujesz” na Linuksie i lista zależności (`prd.md:59`, `prd.md:156`);
   - lista platform i macOS (`prd.md:154`, `prd.md:175`).
