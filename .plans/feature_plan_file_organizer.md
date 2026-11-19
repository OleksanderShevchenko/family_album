# План розробки фічі: Організатор медіафайлів за роками і місяцями

---

## 1. Аудит стану розробки: Що зроблено, що переробити, що додати

### 1.1. Що вже зроблено добре — `[ВИКОНАНО ДОБРЕ]`
1. **Розумний парсер дат із пріоритетом назви файлу ([date_extractor.py](file:///C:/Users/Oleksander/Alex/Projects/family_album/src/family_album/utility_functions/date_extractor.py))**:
   - Розпізнає патерни смартфонів, камер, скріншотів, месенджерів (`IMG_...`, `VID_...`, `PXL_...`, `Screenshot_...`, `WhatsApp...`, ISO-дати, Unix timestamps).
   - Валідує календарні межі ($1970 \le \text{year} \le \text{current\_year} + 1$).
   - Дотримується пріоритету: `Назва файлу` $\rightarrow$ `EXIF / Метадані відео` $\rightarrow$ папка `No_Date/`.
2. **Локальний SQLite-каталог у цільовій папці ([organizer_db.py](file:///C:/Users/Oleksander/Alex/Projects/family_album/src/family_album_lib/organizer_db.py))**:
   - Зберігає базу даних у `<target_dir>/.db/album.db` (таблиці `organized_files`, `organizer_sessions`, `organizer_log`).
   - Підтримує перевірку актуальності каталогу (`verify_catalog_actuality`) та пошук за хешем (`find_by_hash`).
3. **Два режими організації та інваріант безпеки ([file_organizer_engine.py](file:///C:/Users/Oleksander/Alex/Projects/family_album/src/family_album_lib/file_organizer_engine.py))**:
   - **Нова організація**: створює поруч `<source>_organized`, перевіряє вільне місце на диску перед `Copy` та пропонує перехід на `Move` при нестачі місця.
   - **Самоорганізація**: автоматично активується при наявності `<source>/.db/album.db` (`Move` всередині папки з пропуском вже організованих `YYYY/MM` та `No_Date`).
   - **Абсолютна безпека даних**: жоден файл ніколи не видаляється і не перезаписується; колізії імен вирішуються суфіксами `_copy1`, `_copy2` тощо.
4. **Базовий графічний інтерфейс ([file_organizer.py](file:///C:/Users/Oleksander/Alex/Projects/family_album/src/family_album/gui/widgets/file_organizer.py))**:
   - Вибір Source/Target директорій, перемикачі режимів та операцій, таблиця попереднього перегляду плану (`tbl_file_data`), індикатор стану БД та прогрес-бар.

---

### 1.2. Що треба переробити / оптимізувати — `[ПОТРЕБУЄ ПЕРЕРОБКИ]`
1. **Критичне гальмування в `is_file_a_video()` ([video_utils.py](file:///C:/Users/Oleksander/Alex/Projects/family_album/src/family_album/utility_functions/video_utils.py#L20-L59))**:
   - Зараз для кожного файлу без відео-розширення (тобто для **кожної фотографії** `.jpg`/`.png`) у гілці `else:` викликається `VideoFileClip(file_name)`, який запускає зовнішній процес ОС `ffmpeg.exe` (~100 мс на кожен файл!).
   - Об'єкти `cv2.VideoCapture` та `VideoFileClip` не закриваються (`cap.release()`, `clip.close()`).
   - **Рішення**: визначати приналежність до відео виключно за відомими розширеннями + `cv2.VideoCapture`, додати швидку функцію `get_video_resolution_fast()` через OpenCV і гарантовано звільняти ресурси у `finally`.
2. **Багаторазове відкриття одного файлу при читанні метаданих ([image_utils.py](file:///C:/Users/Oleksander/Alex/Projects/family_album/src/family_album/utility_functions/image_utils.py), [date_extractor.py](file:///C:/Users/Oleksander/Alex/Projects/family_album/src/family_album/utility_functions/date_extractor.py))**:
   - Зараз під час сканування одне фото відкривається з диска 5–7 разів поспіль (`is_file_a_video`, `is_image_file`, `_get_image_info_pil`, `_get_image_info` без `details=False`, `get_image_size`, `get_image_maker`).
   - **Рішення**: зробити однопрохідну інспекцію заголовка зображення через Pillow (`inspect_image_fast`), читати EXIF Sub-IFD (`0x8769`) напряму через Pillow, а `exifread` викликати лише як резервний варіант із `details=False`.
3. **Однопотоковий аналіз та організація у `FileOrganizerEngine` ([file_organizer_engine.py](file:///C:/Users/Oleksander/Alex/Projects/family_album/src/family_album_lib/file_organizer_engine.py))**:
   - Зараз `scan_and_plan()` та `execute_plan()` обробляють файли послідовно в одному потоці, а при натисканні `Organize Files` сканування запускається вдруге з нуля.
   - **Рішення**: розпаралелити пофайловий аналіз (`scan_and_plan`) та пофайлове копіювання/переміщення (`execute_plan`) через `ThreadPoolExecutor(max_workers=...)`, а також перевикористовувати вже побудований план.
4. **Жорстко фіксована кількість потоків (200) у пошуку дублікатів ([resumable_duplicate_analyser.py](file:///C:/Users/Oleksander/Alex/Projects/family_album/src/family_album_lib/resumable_duplicate_analyser.py#L19))**:
   - Константа `_NUM_OPEN_FILES = 200` перевантажує домашній ноутбук.
   - **Рішення**: передавати кількість потоків із глобальних налаштувань застосунку (`AppSettings.worker_threads`).

---

### 1.3. Що треба розробити — `[НОВИЙ ФУНКЦІОНАЛ]`
1. **Система налаштувань застосунку (`.settings/settings.json`) та діалог `Tools -> Settings...`**:
   - Збереження налаштувань у папці `.settings` поруч із виконуваним файлом / коренем проекту.
   - Автоматичне визначення кількості логічних ядер процесора при першому старті (`cpu_cores * 2`) та створення файлу налаштувань.
   - Збереження та автоматичне відновлення останньої вибраної директорії при запуску програми.
   - Діалогове вікно `Tools -> Settings...` для перегляду та зміни кількості потоків і стартової директорії.
2. **Патерн Memento для Органайзера (Пауза, Збереження стану, Продовження з місця зупинки)**:
   - Підтримка зупинки (`Stop`), збереження стану (`Save State`) та відновлення (`Resume`) як для процесу **аналізу** (`scan_and_plan`), так і для процесу **організації** (`execute_plan`) поточної папки.

---

## 2. Покроковий план виконання (Крок за кроком з перевіркою та комітами)

```mermaid
flowchart TD
    S1["Крок 1: Налаштування застосунку (.settings) + меню Tools -> Settings... + відновлення останньої папки"]
    S2["Крок 2: Оптимізація метаданих фото/відео (усунення ffmpeg на фото, 1-прохідний Pillow, потокобезпечна БД)"]
    S3["Крок 3: Багатопотоковий пайплайн аналізу та організації (ThreadPoolExecutor у scan_and_plan та execute_plan)"]
    S4["Крок 4: Патерн Memento для Органайзера (Пауза / Збереження / Продовження для аналізу та організації)"]

    S1 --> S2 --> S3 --> S4
```

---

### Крок 1: Клас налаштувань застосунку (`.settings`) та діалог `Tools -> Settings...` — `[ВИКОНАНО]`
**Мета**: Створити централізоване сховище налаштувань у `<app_dir>/.settings/settings.json`, автоматично визначати оптимальну кількість потоків при першому запуску, відновлювати останню вибрану директорію та додати вікно налаштувань у меню.
- [x] **1.1. Модуль `src/family_album_lib/app_settings.py` (`AppSettings`)**:
  - Визначення папки застосунку (поруч із `.exe` при PyInstaller-збірці або корінь проекту при запуску з коду).
  - При першому запуску (якщо `.settings/settings.json` ще немає): визначення доступних логічних ядер процесора (`os.cpu_count()`) та розрахунок кількості потоків за замовчуванням: `worker_threads = cpu_cores * 2` (у діапазоні `1..256`), автоматичне створення `.settings/settings.json`.
  - Збереження параметрів: `worker_threads`, `last_selected_directory`.
- [x] **1.2. Діалог `src/family_album/gui/dialogs/settings_dialog.py` (`SettingsDialog`)**:
  - Відображення кількості виявлених ядер CPU та рекомендованої кількості потоків (`cores × 2`).
  - Повзунок (`QSlider`) + числове поле (`QSpinBox`) для зміни кількості потоків + кнопка скидання до рекомендованого значення.
  - Поле перегляду/зміни останньої вибраної директорії та шляху до файлу `.settings/settings.json`.
- [x] **1.3. Інтеграція у `MainWindow`, `DirectoryView`, `DuplicationChecker` та `FileOrganizer`**:
  - Додати меню `Tools -> Settings...` (`Ctrl+,`) у [main_window.py](file:///C:/Users/Oleksander/Alex/Projects/family_album/src/family_album/gui/main_window.py).
  - У [directory_view.py](file:///C:/Users/Oleksander/Alex/Projects/family_album/src/family_album/gui/widgets/directory_view.py) додати метод `select_directory(path)` для програмного розгортання та вибору збереженої папки у дереві при старті.
  - При виборі папки в `MainWindow.evt_dir_selected()` автоматично зберігати її в `AppSettings.last_selected_directory`.
  - Передавати `AppSettings.worker_threads` в обидва інструменти: `ResumableDuplicateAnalyser` / `DuplicationChecker` (замість жорстких `200`) та `FileOrganizer` / `OrganizerWorker`.
- [x] **1.4. Тестування Кроку 1**:
  - Написано модульні тести [tests/test_app_settings.py](file:///C:/Users/Oleksander/Alex/Projects/family_album/tests/test_app_settings.py) (5 тестів, 100% pass).

---

### Крок 2: Оптимізація швидкодії визначення метаданих фото та відео — `[ВИКОНАНО]`
**Мета**: Усунути запуск `ffmpeg` на фотографіях та багаторазове читання файлів з диска.
- [x] **2.1. Оптимізація [video_utils.py](file:///C:/Users/Oleksander/Alex/Projects/family_album/src/family_album/utility_functions/video_utils.py)**:
  - У `is_file_a_video()` перевіряється список відео-розширень (`VIDEO_EXTENSIONS`) і миттєво повертається `False` для не-відео файлів (без виклику `VideoFileClip` / `ffmpeg`), а для анімованих `.gif` використовується швидка перевірка через Pillow (`_is_animated_gif`).
  - Додано `has_video_extension()` та `get_video_resolution_fast()` через `cv2.VideoCapture` (та Pillow для `.gif`) замість важкого `MoviePy`.
  - Гарантовано закриття `cap.release()` та `clip.close()` у блоках `finally`.
- [x] **2.2. Оптимізація [image_utils.py](file:///C:/Users/Oleksander/Alex/Projects/family_album/src/family_album/utility_functions/image_utils.py) та [date_extractor.py](file:///C:/Users/Oleksander/Alex/Projects/family_album/src/family_album/utility_functions/date_extractor.py)**:
  - Додано `IMAGE_EXTENSIONS`, `has_image_extension()` та `inspect_image_fast(file_path)` для отримання `(is_image, resolution, maker)` за одне відкриття заголовка Pillow; виправлено закриття дескриптора у `_is_image_pillow()` та обмежено `cv2.imread()` fallback лише відомими розширеннями зображень.
  - У `extract_date_from_exif()` реалізовано швидкий шлях `extract_date_from_pil_exif()` через Pillow `getexif()` + Exif Sub-IFD (`0x8769`), використовуючи `exifread.process_file(..., details=False)` лише як резервний варіант.
- [x] **2.3. Потокобезпечність [organizer_db.py](file:///C:/Users/Oleksander/Alex/Projects/family_album/src/family_album_lib/organizer_db.py)**:
  - Додано `check_same_thread=False` та `threading.RLock()` для безпечного багатопотокового доступу з пулу потоків.
- [x] **2.4. Тестування Кроку 2**:
  - Розширено та пройдено тести `test_video_utils.py`, `test_image_utils.py`, `test_date_extractor.py`, `test_organizer_db.py` (перевірено відсутність викликів MoviePy на фото, пропуск `exifread` при наявності Pillow EXIF, та паралельний запис у БД із 8 потоків).

---

### Крок 3: Паралелізація пайплайну аналізу та організації (`ThreadPoolExecutor`) — `[ВИКОНАНО]`
**Мета**: Розпаралелити пофайловий аналіз та пофайлове копіювання/переміщення на кількість потоків із `AppSettings.worker_threads`.
- [x] **3.1. Паралельний однопрохідний аналіз у `FileOrganizerEngine.scan_and_plan()`**:
  - Запускається обробка файлів через `ThreadPoolExecutor(max_workers=max_workers)` (`AppSettings.worker_threads`).
  - Реалізовано однопрохідний `_inspect_single_file()`: 1 відкриття заголовка Pillow для фото (розмір, виробник, EXIF Sub-IFD), швидкий OpenCV `get_video_resolution_fast()` для відео без запуску MoviePy при наявності дати в імені файлу.
  - Коректна зупинка за `cancel_event` та тротлінг оновлень прогресу (50 мс) + оптимізація рендеру великих таблиць у `FileOrganizer._populate_plan_table()`.
- [x] **3.2. Паралельна організація у `FileOrganizerEngine.execute_plan()`**:
  - Копіювання/переміщення та розрахунок хешу `Blake2b` кожного файлу виконуються паралельно в потоках `ThreadPoolExecutor(max_workers=max_workers)`.
  - Атомарне резервування унікального імені (`_copyN`) через `_reserve_unique_destination()` + `collision_lock` (виправлено також колізії різних файлів у `safe_move_file`), перевикористання `src_hash` без повторного хешування та потокобезпечний запис у SQLite.
  - Перевикористання готового плану (`existing_plan`) при переході від `Analyze / Preview` до `Organize Files...` без повторного сканування.
  - Усунено дублювання логів і зайвий спам `MainWindow.evt_update_progress` під час роботи органайзера.
- [x] **3.3. Тестування Кроку 3**:
  - Додано 4 нові тести у [test_file_organizer_engine.py](file:///C:/Users/Oleksander/Alex/Projects/family_album/tests/test_file_organizer_engine.py) (60 файлів паралельно, стрес-тест 20 колізій імен при `move` у 8 потоків, перевикористання плану без повторного сканування, відсутність виклику MoviePy на відео з датою в імені) — **54/54 тести проходять**.

---

### Крок 4: Патерн Memento для Органайзера (Пауза / Збереження стану / Відновлення) — `[НАСТУПНИЙ КРОК]`
**Мета**: Дозволити зупиняти, зберігати та продовжувати з місця зупинки як процес аналізу, так і процес організації для поточної папки.
- [ ] **4.1. Модуль `src/family_album_lib/organizer_memento.py`**:
  - Класи `OrganizerStatus`, `OrganizerMemento`, `OrganizerSaveManager` (збереження у `saves/organizer_save_<hash>.json`).
  - Підтримка фаз `phase="analyze"` (зберігає вже проаналізовані елементи плану) та `phase="organize"` (зберігає весь план зі статусами `organized`/`skipped`/`pending` та накопичену статистику `OrganizeStats`).
  - Метод `verify_location(memento)` для перевірки цілісності папки перед відновленням.
- [ ] **4.2. Інтеграція Memento в `FileOrganizerEngine` та GUI віджет `FileOrganizer`**:
  - У `scan_and_plan()` пропускати файли, які вже є у відновленому Memento.
  - У `execute_plan()` пропускати елементи плану зі статусом `organized` або `skipped`, продовжуючи лише `pending`.
  - Додати кнопки **Save State** та **Resume** у віджет `FileOrganizer`, діалог пропозиції відновлення при виявленні збереженого стану та автоматичне видалення сейву після повного завершення організації.
- [ ] **4.3. Тестування Кроку 4**:
  - Написати тести `tests/test_organizer_memento.py` (еквівалентність односесійного та багатосесійного аналізу й організації з паузою та відновленням).

---

## 3. Відкладено на майбутні релізи (Backlog)
- **Undo / Rollback (Відкат останньої організації)** — `[ВІДКЛАДЕНО]` (база даних `.db/album.db` вже зберігає всі пари `original_path` $\rightarrow$ `organized_path` для майбутньої реалізації).
