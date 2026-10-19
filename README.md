# BOTspoti

Własny bot muzyczny Discord uruchamiany na komputerze. Użytkownik dołącza do kanału głosowego i wpisuje:

```text
/play query:https://open.spotify.com/playlist/IDENTYFIKATOR
```

Bot odczytuje pozycje publicznej playlisty, dodaje je w kolejności do kolejki i szuka odpowiadających im nagrań na YouTube. Obsługuje też pojedyncze utwory Spotify, linki do utworów i playlist YouTube oraz wyszukiwanie po nazwie. Nie steruje Flavi ani kontem użytkownika. Działa jako oddzielne konto bota.

**Stan:** implementacja i testy lokalne są dostępne. Odtwarzanie na prawdziwym serwerze Discord oraz dostęp do rzeczywistych playlist Spotify wymagają konfiguracji operatora i nie zostały jeszcze zweryfikowane.

## Ograniczenia, które trzeba znać przed konfiguracją

- Publiczny link Spotify nie gwarantuje, że aplikacja uzyska dostęp do zawartości przez API. Spotify ogranicza dostęp zależnie od trybu i uprawnień aplikacji, a w trybie Development dostęp do cudzych playlist może być niedostępny. Wymagania konta, w tym Premium w niektórych trybach, określa Spotify. Sprawdź aktualne zasady w swoim Dashboard. Bot korzysta z Client Credentials; nie obsługuje logowania użytkownika ani prywatnych playlist. Jeśli Spotify odmawia dostępu, bot zgłasza błąd i nie dodaje częściowej listy. Nie obchodzi ograniczeń przez scraping ani nie odtwarza 30-sekundowych preview.
- Spotify dostarcza metadane, **nie dźwięk**. Audio pochodzi z YouTube przez yt-dlp. Serwis może blokować automatyczny dostęp, zmieniać formaty lub ograniczać niektóre nagrania. Korzystaj zgodnie z uprawnieniami do nagrań i zasadami źródła. Działającego dostępu do YouTube w danej sieci nie można zagwarantować.
- Dopasowanie wykorzystuje wykonawcę i tytuł oraz kontrolę długości; nie gwarantuje identycznej wersji. Nagrania o wyraźnie innej długości i transmisje live są pomijane. Źródło audio jest wyszukiwane dopiero przed odtworzeniem, aby adres strumienia nie wygasł w kolejce.
- Limit wynosi 500 pozycji playlisty i 500 oczekujących utworów na serwer. Większy import zostaje odrzucony, bez cichego obcinania listy. Pliki lokalne, albumy Spotify, podcasty i skrócone linki Spotify nie są obsługiwane.
- Kolejki są w pamięci i znikają po wyłączeniu programu. Komputer musi pozostać włączony. Pusty odtwarzacz rozłącza się po 3 minutach. Kanały Stage nie są obsługiwane.

## 1. Wymagane programy

- Python **3.12 lub nowszy** z pip i venv.
- FFmpeg w `PATH` albo ścieżka w `FFMPEG_PATH` w `.env`.
- Node.js **22 lub nowszy** w `PATH`, używany przez yt-dlp do obsługi odtwarzania YouTube.

Windows: zainstaluj Python ze strony python.org (zaznacz dodanie do PATH), Node.js LTS z nodejs.org oraz FFmpeg, np. `winget install --id Gyan.FFmpeg -e`. Otwórz nowy terminal po instalacji. Sprawdź `python --version`, `node --version` i `ffmpeg -version`.

macOS z Homebrew: `brew install python@3.12 ffmpeg node`.

Linux: zainstaluj Python, moduł venv, FFmpeg oraz Node.js >=22 odpowiednim menedżerem pakietów. Starszy Node.js z dystrybucji może wymagać aktualizacji.

## 2. Konto bota Discord

1. Otwórz https://discord.com/developers/applications i wybierz **New Application**.
2. W sekcji **Bot** utwórz/skonfiguruj konto bota i skopiuj jego token do lokalnego `.env` jako `DISCORD_TOKEN`. Token jest sekretem — nie wklejaj go w czacie ani do repozytorium.
3. W **OAuth2 → URL Generator** zaznacz zakresy `bot` i `applications.commands`. Nadaj uprawnienia **View Channels**, **Send Messages**, **Connect** i **Speak**. Administrator oraz Message Content Intent nie są potrzebne.
4. Otwórz wygenerowany link i dodaj bota do swojego serwera. Musisz mieć uprawnienie do zarządzania serwerem. Sprawdź też nadpisania uprawnień na kanale tekstowym i głosowym.
5. W Discordzie włącz **Ustawienia → Zaawansowane → Tryb dewelopera**, kliknij prawym przyciskiem serwer → **Kopiuj ID serwera**. Zapisz jako `DISCORD_GUILD_ID`. Dzięki temu komendy rejestrują się na tym serwerze bez czekania na propagację komend globalnych. Bez tego pola rejestrowane są globalnie, co może potrwać.

Bot używa discord.py 2.7 z biblioteką DAVE do współczesnych połączeń głosowych Discorda.

## 3. Aplikacja Spotify

1. Otwórz https://developer.spotify.com/dashboard i utwórz aplikację korzystającą z Web API.
2. Zapisz **Client ID** i **Client Secret** w `.env`. To dane aplikacji Spotify, nie login i hasło konta.
3. Sprawdź dostęp swojej aplikacji do endpointu playlist items. Samo utworzenie aplikacji nie usuwa ograniczeń Spotify opisanych powyżej. Nie potrzeba redirect URI do używanego tu przepływu Client Credentials.

Jeżeli nie masz danych Spotify lub API odmawia dostępu do konkretnej playlisty, bezpośrednie linki YouTube i wyszukiwanie pozostają niezależną funkcją. Nie oznacza to, że import Spotify został zweryfikowany.

## 4. Uruchomienie na komputerze

Pobierz pliki repozytorium. W Windows uruchom **`start.bat`**. Przy pierwszym uruchomieniu utworzy `.env` i otworzy Notatnik. Uzupełnij dane, zapisz plik i uruchom ponownie. Skrypt utworzy wirtualne środowisko, zainstaluje przypięte zależności i uruchomi bota. Zamknięcie okna zatrzymuje bota.

Linux/macOS: uruchom `bash start.sh`, uzupełnij utworzony `.env` i ponownie wykonaj `bash start.sh`.

Można też uruchomić ręcznie z katalogu projektu:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
cp .env.example .env
# Uzupełnij .env lokalnie; nie nadpisuj istniejącej konfiguracji.
.venv/bin/python -m botspoti --check
.venv/bin/python -m botspoti
```

W Windows odpowiednikiem `.venv/bin/python` jest `.venv\Scripts\python.exe`, a `python3` zwykle `python`.

`--check` sprawdza obecność konfiguracji oraz FFmpeg, nie wypisuje sekretów i nie loguje się do usług. Brak wymaganych danych daje kod wyjścia 1. Do samego odtwarzania z YouTube wystarczy token Discord; normalny start dopuszcza brak danych Spotify, ale import Spotify wtedy zwróci wyjaśnienie błędu.

Nie publikuj `.env`. Jest ignorowany przez Git. `requirements.lock` przypina pełny sprawdzony zestaw zależności; `requirements.txt` zawiera zależności główne dla świadomych aktualizacji. Po aktualizacji yt-dlp ponownie przetestuj audio i odśwież lockfile.

## Komendy

| Komenda | Działanie |
| --- | --- |
| `/play query:<link lub nazwa>` | Dodaje utwór albo całą dostępną playlistę do kolejki |
| `/queue` | Pokazuje bieżący utwór, następne 10 i liczbę oczekujących |
| `/skip` | Pomija bieżący utwór |
| `/pause` | Wstrzymuje |
| `/resume` | Wznawia |
| `/stop` | Usuwa kolejkę i rozłącza bota |

Dodawać i sterować mogą osoby na tym samym kanale głosowym co bot. Kolejka jest wspólna dla serwera. Równoczesne importy są obsługiwane kolejno. Wybrany kanał tekstowy otrzymuje informacje o odtwarzaniu i pominięciach; bot nie wysyła pingów.

## Sprawdzenie działania

Z katalogu projektu:

```bash
.venv/bin/python -m pip check
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m botspoti --check
```

Testy sprawdzają paginację i kolejność Spotify na kontrolowanych odpowiedziach API, błędy autoryzacji, limity, odrzucanie obcych adresów, dobór źródła audio, przechodzenie do następnego utworu i zatrzymanie. Test FFmpeg uruchamia rzeczywisty proces i sprawdza wygenerowanie ramek Opus z sygnału testowego. To nie są testy sieciowe Spotify ani Discorda.

Po skonfigurowaniu wykonaj test na własnym serwerze: dołącz do kanału głosowego, dodaj dostępny utwór przez `/play`, sprawdź słyszalność, pauzę i wznowienie, następnie dodaj małą publiczną playlistę Spotify z kilkoma znanymi utworami. Sprawdź liczbę pozycji, kolejność, `/skip`, przejście do następnego i `/stop`. Jeśli Spotify odmawia dostępu, zapisz komunikat bez tokenów — trzeba rozwiązać uprawnienia API, a nie uznać import za działający.

## Typowe problemy

- Brak komend: sprawdź ID serwera i zakres `applications.commands` przy zapraszaniu; przy komendach globalnych odczekaj na propagację.
- Brak dźwięku: sprawdź FFmpeg, uprawnienie Speak, wyciszenie serwerowe i dostęp do sieci głosowej Discorda (w tym UDP). Zwykły HTTPS proxy może nie wystarczyć do voice.
- Niedostępne źródło: sprawdź Node.js, dostępność nagrania i aktualność yt-dlp. Nie wyłączaj weryfikacji TLS ani nie umieszczaj prywatnych cookies w repozytorium.
- Spotify 403/404: sprawdź tryb aplikacji i uprawnienia do odczytu danej playlisty. Zmiana playlisty na publiczną może nie wystarczyć.

## Środowisko chmurowe

Do prac programistycznych używaj istniejącego checkoutu `/workspace/BOTspoti`; zadania są izolowane i nie wymagają dodatkowego Git worktree. Testy lokalne nie wymagają tokenów. Bot uruchamiany na komputerze użytkownika nie potrzebuje publikowania portu ani strony WWW. Konfiguracja i udany test lokalnego FFmpeg nie potwierdzają działania usług zewnętrznych. Proces bota trzeba uruchomić ponownie po restarcie komputera lub środowiska.
