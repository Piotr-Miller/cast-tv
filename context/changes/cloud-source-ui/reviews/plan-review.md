<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Cloud Source UI

- **Plan**: context/changes/cloud-source-ui/plan.md
- **Mode**: Deep
- **Date**: 2026-09-09
- **Verdict**: RETHINK → SOUND after triage (all 8 findings fixed in plan, 2026-09-09)
- **Findings**: 3 critical, 5 warnings, 0 observations

Przed implementacją trzeba rozstrzygnąć tożsamość ponownie wybieranych zdjęć oraz sterowanie pokazem przy zastępowaniu odtwarzania. Triage 2026-09-09: wszystkie osiem ustaleń naniesione do planu (F2 i F5 w wersji doprecyzowanej przez autora). Odwołania do numerów linii dotyczą wersji przejrzanej 2026-09-09.

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Requirement Definition | FAIL |
| End-State Alignment | FAIL |
| Lean Execution | PASS |
| Architectural Fitness | FAIL |
| Blind Spots | FAIL |
| Plan Completeness | WARNING |

## Grounding

5/5 istniejących ścieżek ✓ (`cast-tv`, `cast-gopro`, `cast-photos`, `castcloud.py`, `README.md`), 5/5 symboli ✓, brief↔plan ✓. Nowe pliki `castlib/` są świadomie planowane. `Progress`: zgodne nazwy wszystkich 7 faz, 38 odpowiadających kryteriów, brak checkboxów poza sekcją. Definitions: 15 wierszy; nierozstrzygnięte przypadki opisują F1–F2. Sprawdzono cztery skrypty, wywołania zmienianych funkcji i niezależny przegląd przypadków brzegowych przez jednego subagenta. Nie uruchamiano testów implementacji ani prób sprzętowych.

## Findings

### F1 — Ponowny wybór zdjęcia nie ma reguły scalania

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — istotna decyzja; wymaga namysłu
- **Dimension**: Requirement Definition
- **Location**: Definitions (`plan.md:74`, `:82`), MediaItem (`:263`), Phase 6 (`:852–863`)
- **Detail**: Plan deklaruje unikalność `(source, source_id)`, ale kolejne sesje Pickera dopisują wpisy. Google zachowuje ID tego samego materiału między sesjami. Po wyborze zdjęcia w S1 i S2, a następnie wygaśnięciu S1, plan nie rozstrzyga, czy zdjęcie pozostaje dostępne przez S2, czy dostaje „re-pick”. Trwałość ID potwierdza [dokumentacja PickedMediaItem](https://developers.google.com/photos/picker/reference/rest/v1/mediaItems).
- **Fix**: Ustalić jeden wpis na ID, zachowanie kolejności zaznaczenia i odświeżanie przez aktualną, ważną sesję.
  - Strength: Usuwa duplikaty i niepotrzebne ponowne wybieranie zdjęć.
  - Tradeoff: Wymaga jawnego zarządzania powiązaniami z sesjami.
  - Confidence: HIGH — dokumentacja potwierdza trwałość ID.
  - Blind spot: Preferencja użytkownika dotycząca powtórzeń w kolejce.
- **Decision**: FIXED — jeden wpis na ID, odświeżanie przez ważną sesję, re-pick gdy żadna nie jest ważna (Definitions `pick`, Phase 6 §2, `test_repick_merges_by_media_id`)

### F2 — Stary pokaz może zawisnąć lub przejąć nowe odtwarzanie

- **Severity**: ❌ CRITICAL
- **Impact**: 🔬 HIGH — decyzja architektoniczna; wymaga dokładnego rozważenia
- **Dimension**: Architectural Fitness
- **Location**: Phase 3 — Cast i Show (`plan.md:530–541`, `:558`), Definitions (`:75`, `:85`)
- **Detail**: Zastąpiony `Cast` otrzymuje `replaced`, ale pokaz czeka wyłącznie na `stopped` albo `failed`. Podczas filmu może więc czekać bez końca. Podczas zdjęcia stary pokaz może obudzić się po interwale i zastąpić materiał uruchomiony ręcznie. Nie ma również reguły zatrzymywania poprzedniego `Show`. „Last SOAP wins” opisuje efekt wyścigu, a nie jednoznaczną kolejność poleceń. Dodatkowo pojedyncze zdjęcie ma według Definitions trwać do Stop, podczas gdy opis pętli kończy się po interwale. Obecny kod ma jednego synchronicznego właściciela odtwarzania (`cast-tv:473–510`); nie dostarcza wzorca rozstrzygającego te przypadki. Uwaga obejmuje także brakujące decyzje w Requirement Definition.
- **Fix**: Zdefiniować jednego właściciela odtwarzania; ręczny cast i nowy pokaz anulują poprzedni pokaz. Serializować `SetURI + Play`, kończyć oczekiwanie również przy anulowaniu i osobno opisać pojedyncze zdjęcie.
  - Strength: Jednoznaczny stan TV i UI przy równoczesnym sterowaniu.
  - Tradeoff: Potrzebne testy współbieżności i anulowania.
  - Confidence: HIGH — sprzeczność wynika bezpośrednio z kontraktu stanów.
  - Blind spot: Moment rozpoczęcia odliczania interwału podczas wolnej konwersji.
- **Decision**: FIXED — inaczej niż w propozycji: jeden właściciel plus `generation` sprawdzana po przygotowaniu materiału i przed komendami, jednowątkowy executor porządkujący żądania (zamiast samego locka), przerywalne oczekiwanie Show na `replaced`/`cancelled` (250 ms to reakcja pętli, sieć ma własne timeouty), interwał liczony od udanego `Play`; jedno zdjęcie w pokazie trzyma do Stop (Critical Implementation Details, Phase 3 §2 i §6, Definitions `slideshow` i `cast (while playing)`)

### F3 — Eviction może usunąć aktualnie odtwarzany materiał

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — istotna decyzja; wymaga namysłu
- **Dimension**: Blind Spots
- **Location**: Phase 1 — Registry (`plan.md:268–275`), Phase 5 manual verification (`:804–806`)
- **Detail**: `evict(idle_seconds)` bazuje na czasie ostatniego żądania. Brakuje ochrony aktualnego castu, trwających transferów i napisów. Po 60 sekundach pauzy wpis może zniknąć, więc wymagane w fazie 5 wznowienie po godzinie zakończy się lokalnym 404, zanim resolver odświeży URL. Decyzja w Definitions dotyczy poprzedniego castu, ale kontrakt Registry opisuje ogólne usuwanie po bezczynności. Obecny kod utrzymuje trasy plików przez życie procesu (`cast-tv:108–112`, `:451–460`).
- **Fix**: Chronić aktywny cast, jego napisy i otwarte transfery; usuwać po okresie bezczynności dopiero wpisy wycofane z odtwarzania.
  - Strength: Zachowuje możliwość wznowienia i późnego pobrania napisów.
  - Tradeoff: Registry potrzebuje informacji o właścicielach i aktywnych żądaniach.
  - Confidence: HIGH — obecny kontrakt nie rozróżnia aktywnych i wycofanych wpisów.
  - Blind spot: Zachowanie Samsungowego bufora wymaga testu sprzętowego.
- **Decision**: FIXED — `retire(id)` od supervisora, `evict()` tylko dla wycofanych wpisów bez transferów w toku, napisy dzielą los wideo (Phase 1 §3 i §10, Definitions `cast (while playing)`)

### F4 — Lista nie dostarcza adresu miniaturek

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — istotna decyzja; wymaga namysłu
- **Dimension**: Plan Completeness
- **Location**: Routing (`plan.md:299–301`), API (`:557`), Source (`:650–661`)
- **Detail**: Jedyna trasa miniaturek wymaga ID z Registry: `/m/<token>/<id>/thumb`. `Entry` zwraca ID źródła i `thumb: bool`, a rejestracja następuje dopiero przy castowaniu. Siatka nie otrzymuje więc adresowalnej miniaturki przed uruchomieniem materiału.
- **Fix**: Dodać chronioną trasę miniaturek po `(source, source_id)` i zwracać jej URL w `Entry`.
  - Strength: Korzysta z istniejącego `Source.thumb()` bez rejestrowania całej biblioteki.
  - Tradeoff: Trzeba dopisać kontrakt odpowiedzi i błędów trasy.
  - Confidence: HIGH — luka między listowaniem i routingiem.
  - Blind spot: Odświeżanie wygasłych URL-i miniaturek.
- **Decision**: FIXED — trasa `GET /api/sources/<name>/thumb/<source_id>` za Origin/Host, `Entry.thumb: str | None`, `/m/.../thumb` usunięta (Phase 1 §5, Phase 3 §3 i §6, Phase 4 §1)

### F5 — Konwersja zdjęcia następuje za późno dla DIDL

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — istotna decyzja; wymaga namysłu
- **Dimension**: End-State Alignment
- **Location**: Phase 2 — Serving photos (`plan.md:449–455`), profile i konwersja (`:423–447`)
- **Detail**: Plan wywołuje `prepare()` przy żądaniu HTTP od TV. Tymczasem DIDL trafia do TV wcześniej, w `SetAVTransportURI` — tak działa obecny kod (`cast-tv:473–475`). HEIC może zostać zapowiedziany jako HEIC, a dostarczony jako JPEG. Zachowany PNG również otrzymuje wspólny profil `JPEG_LRG`. Brakuje przygotowania i publikacji wynikowych MIME, rozmiaru i wymiarów przed SOAP.
- **Fix**: Przygotować zdjęcie przed SOAP i budować DIDL oraz odpowiedź HTTP z tych samych danych `Prepared`; profil dobierać do wynikowego MIME.
  - Strength: Zgodne MIME, rozmiar i wymiary na całej ścieżce.
  - Tradeoff: Uruchomienie zdjęcia czeka na konwersję.
  - Confidence: HIGH — kolejność operacji jest widoczna w kodzie.
  - Blind spot: Akceptowane profile obrazu nadal wymagają Samsunga.
- **Decision**: FIXED — inaczej niż w propozycji: `Prepared` jako osobny obiekt (źródłowe pola `MediaItem` zostają), profil z wynikowego MIME i wymiarów (`photo_profile`), trasa publikowana dopiero po udanym przygotowaniu i kontroli generacji, HTTP nie konwertuje, błąd konwersji kończy zadanie przed SOAP (Phase 1 §3, Phase 2 §2–§4 i §6, Definitions `kind → wire`)

### F6 — Mapowanie źródeł nie realizuje zasad dotyczących zdjęć

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — istotna decyzja; wymaga namysłu
- **Dimension**: End-State Alignment
- **Location**: Phase 4 (`plan.md:674–681`), Phase 5 (`:770–772`)
- **Detail**: GoPro ma obsługiwać zdjęcia przez istniejące `library_url()`, które odrzuca warianty obrazów (`cast-gopro:119–122`) i sprawdza je przez `is_video()` (`:137`; `castcloud.py:75–80`). Brakuje ścieżki pobierania zdjęć opartej na zweryfikowanej odpowiedzi API; fallback `files` nie gwarantuje obsługi wariantu zawierającego wyłącznie obraz. OneDrive natomiast akceptuje każde `image/*`, więc przepuszcza również `image/gif`, mimo jawnego wykluczenia GIF-ów.
- **Fix**: Dopisać rozwiązywanie zdjęć GoPro na podstawie rzeczywistych fixture’ów oraz wspólny filtr dozwolonych formatów przed tworzeniem `Entry`.
  - Strength: Lista odpowiada zadeklarowanemu zakresowi obsługiwanych mediów.
  - Tradeoff: Potrzebny probe zdjęcia GoPro, nie tylko jego miniaturki.
  - Confidence: HIGH — oba problemy wynikają z konkretnych warunków.
  - Blind spot: Rzeczywisty format pobierania burst/livephoto pozostaje niezweryfikowany.
- **Decision**: FIXED — drugi probe GoPro (download zdjęcia/burst/livephoto) i `photo_url()` z rankingiem wariantów obrazu; wspólny `is_allowed_photo()` w `media.py` stosowany przez GoPro, OneDrive i Picker; przypadek `image/gif` w `test_kind_from_facets` (Phase 2 §2 i §6, Phase 4 §2 i §5, Phase 5 §2, Phase 6 §2, Definitions `media`)

### F7 — Cache zdjęć przeczy obietnicy tymczasowego przechowywania

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — szybka decyzja; poprawka oczywista i lokalna
- **Dimension**: Blind Spots
- **Location**: Phase 2 — Photo pipeline (`plan.md:440–443`), scope (`:132–133`), Phase 7 paths (`:934–936`)
- **Detail**: Plan obiecuje cache w katalogu tymczasowym, ale wskazuje `cache_dir()/photos`. `cache_dir()` oznacza obecnie `~/.cache/cast-tv` (`castcloud.py:18`), a w fazie 7 `user_cache_dir()`. Nie opisano usuwania zdjęć przy zakończeniu procesu.
- **Fix**: Użyć osobnego katalogu tymczasowego procesu z cleanupem; trwały cache metadanych pozostawić oddzielnie.
- **Decision**: FIXED — `tempfile.mkdtemp` per proces usuwany w `atexit` i na Ctrl+C, `cache_dir()` tylko dla metadanych, `photo_tmp_dir()` w `config.py`, `test_tmp_dir_removed_at_exit` (Phase 1 §8, Phase 2 §3 i §6)

### F8 — Test ręcznego zastąpienia wyprzedza potrzebną funkcjonalność

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — szybka decyzja; poprawka oczywista i lokalna
- **Dimension**: Plan Completeness
- **Location**: Phase 1 — Manual Verification (`plan.md:389–390`)
- **Detail**: Faza 1 wymaga uruchomienia drugiego castu przy działającym pierwszym. Drugie wywołanie CLI na tym samym porcie kończy się obecnie błędem bind (`cast-tv:462–466`). Registry wewnątrz procesu tego nie zmienia, a sterowanie wieloma castami pojawia się dopiero w fazie 3.
- **Fix**: W fazie 1 sprawdzać dwa wpisy w jednym serwerze testem integracyjnym; ręczne zastępowanie odtwarzania pozostawić w fazie 3.
- **Decision**: FIXED — punkt 1.5 zastąpiony automatycznym 1.4 (`test_second_item_does_not_replace_first` na dwóch wpisach w jednym serwerze); ręczne zastępowanie zostaje w 3.5 (Phase 1 Success Criteria, Progress)
