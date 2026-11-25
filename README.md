# ЛР6 — оркестратор и специализированные исполнители

Windows PowerShell, Python 3.12. Для показа готовых результатов модель и GPU не нужны. Откройте PowerShell в папке проекта:

```powershell
git clone https://github.com/isachvl/6_laba_is.git
cd 6_laba_is
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-demo.txt
.\.venv\Scripts\python.exe prepare_laptop.py
Start-Process .\report.pdf
.\.venv\Scripts\mlflow.exe ui --backend-store-uri sqlite:///mlflow.db --host 127.0.0.1 --port 5005
```

Откройте http://127.0.0.1:5005, эксперимент lr6. Сравнение архитектур: single_30 и multi_30. Сравнение контекста исполнителя: multi_selected_10 и full_request_10 — одинаковые 10 задач. Графики и отчёт лежат в multi_30 → Artifacts → analysis и report. Полные трейсы лежат там же в traces. Остановка сервера — Ctrl+C.

Четыре метрики: success — доля успехов; median_model_calls — медиана обращений к модели за эпизод; median_input_tokens — медиана суммы входных токенов; median_peak_input_tokens — медиана наибольшего входа в одном обращении за эпизод. Два изображения: architecture.png и full_request.png. Повторная подготовка обновляет артефакты и не добавляет одинаковые точки метрик.

```powershell
.\.venv\Scripts\python.exe verify_results.py
```

Проверки оркестратора без генерации модели:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest -v test_multi
```

Материалы: report.pdf — отчёт; results.jsonl — 91 запись (30 сохранённых базовых эпизодов ЛР5 и 61 эпизод ЛР6: 20 отладочных, 30 основных, 10 с полным запросом, 1 с расширенными инструментами почты); analysis — таблицы, графики и разборы; traces — новые трейсы; baseline — исходные результаты и трейсы ЛР5; prompts — инструкции ролей; frozen.json — параметры и хеши до основной серии. Один прерванный основной эпизод учтён как неуспех: его полное время неизвестно, записанные затраты являются нижней границей. Он не перезапускался.

Для новых измерений используйте отдельную копию проекта, сохранив готовые результаты. Установите requirements.txt, загрузите модель и llama.cpp командами download_runtime.py и start_server.py. Требуется совместимая NVIDIA GPU. На текущем компьютере используются ранее проверенные бинарники ЛР4 и веса ЛР1; при отсутствии локальных файлов download_runtime.py скачивает зафиксированные версии с проверкой SHA-256. Отладка: run.py dev; после отладки Git-коммит и freeze.py; затем run.py main, analyze.py select, run.py full_request, run.py email_calendar, analyze.py. Для одиночного режима есть config_single.json и run.py main --architecture single. Не изменяйте промпты по итоговым задачам. Готовый отчёт собирает report.py после содержательного разбора в analysis/reviews.json.
