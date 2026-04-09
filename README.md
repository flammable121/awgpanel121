# AmneziaWG Panel

Панель управления AmneziaWG 2.0 с веб-интерфейсом: управление клиентами, конфигами и базовой статистикой.

## Быстрый старт (установка на VPS)

```bash
bash -c "git clone https://github.com/flammable121/awgpanel121.git awgpanel && cd awgpanel && bash deploy/install.sh"
```

Установка выполняется **одной командой** и проведет вас через несколько вопросов.

Важно: AmneziaWG 2.0 должен быть установлен заранее через официальный desktop‑клиент (AmneziaVPN), так как он поднимает контейнер `amnezia-awg2`.

## Что спрашивает установщик и зачем

1. **`Install Docker automatically? [Y/n]`**  
   Установить Docker (если его нет). Docker нужен для запуска панели.  
   - `Y` — устанавливает Docker автоматически.  
   - `n` — установка прерывается.

2. **`AWG container name [amnezia-awg2]:`**  
   Имя контейнера AmneziaWG (обычно `amnezia-awg2`).  
   Если контейнер называется иначе — укажите свое имя.

3. **`AmneziaWG config path [/opt/amnezia/awg/awg0.conf]:`**  
   Путь к конфигу AWG **внутри контейнера**.  
   Обычно `/opt/amnezia/awg/awg0.conf`.

4. **`AmneziaWG interface [awg0]:`**  
   Имя интерфейса AWG. Обычно `awg0`.

5. **`Press Enter to continue after installation...`**  
   Пауза, если AWG не найден.  
   Установите AWG через AmneziaVPN и нажмите Enter, чтобы проверка повторилась.

6. **`Domain name (leave empty for IP/HTTP):`**  
   Домен для панели.  
   - Если пусто — панель будет доступна по **IP и HTTP (порт 80)**.  
   - Если указан домен — панель будет работать по **HTTPS** (Caddy получит сертификат автоматически).

7. **`Public endpoint for client configs (host:port) [<default>]`**  
   Endpoint, который будет прописан в конфигурациях клиентов.  
   Примеры: `example.com:51820` или `1.2.3.4:51820`.

8. **`Admin username [admin]:`**  
   Логин администратора панели.

9. **`Admin password:`**  
   Пароль администратора (минимум 8 символов).

10. **`Confirm password:`**  
    Повтор пароля для проверки.

11. **`Existing configuration found. Overwrite? [y/N]:`**  
    Если `.env` или `.secrets` уже существуют:  
    - `y` — перезапишет настройки  
    - `N` — отменит установку

12. **`Open ports 80 and 443 in UFW? [Y/n]:`**  
    Если установлен UFW — открыть порты 80/443 для HTTP/HTTPS.

13. **`Open AmneziaWG port <порт>/udp in UFW? [Y/n]:`**  
    Открыть UDP‑порт AWG (если он найден), чтобы клиенты могли подключаться.

## Что происходит после установки

- Создается `.env` с настройками панели и AWG.
- Секреты сохраняются в `.secrets/panel.json` (не в `.env`).
- Генерируется **секретный путь** к панели (например: `/FKnnoR41OKNF23/`).
- В конце установки выводится полный URL панели.
- Генерируется **API токен** для доступа к внешнему API.

## Пример URL доступа

Если есть домен:  
```
https://your-domain.com/<секретный_путь>/
```

Если домена нет:  
```
http://<IP_сервера>/<секретный_путь>/
```

## Примечания

- Секретный путь нужен, чтобы URL панели знали только вы.
- Для домена сертификаты выдаёт Caddy и автоматически продлевает.
- Панель рассчитана на работу с контейнером AmneziaWG, установленным через AmneziaVPN.

## Структура проекта (backend)

Код бэкенда разбит по модулям, чтобы легче было читать и поддерживать:

```text
panel/app/
  main.py                # запуск FastAPI и подключение роутеров
  core.py                # settings, base path, шаблоны
  deps.py                # зависимости (DB, auth, API-key, AwgController)
  routes/
    auth.py              # login/logout/главная
    peers.py             # клиенты + API для клиентов
    awg.py               # параметры AmneziaWG и настройки
    system.py            # метрики, трафик, перезапуски
    api_info.py          # API info + reset token
  services/
    awg_service.py       # бизнес-логика AmneziaWG
    traffic.py           # накопительный трафик и сброс
    secrets.py           # работа с secrets
```

## API (внешний доступ)

API защищён токеном. Токен хранится в `.secrets/panel.json` в поле `API_TOKEN`.

### Авторизация

Используйте один из вариантов:
- `Authorization: Bearer <API_TOKEN>`
- `X-API-Key: <API_TOKEN>`

### Примеры запросов

**Список конфигураций:**
```bash
curl -H "Authorization: Bearer <API_TOKEN>" \
  http://<IP>/<секретный_путь>/api/v1/peers
```

**Создание конфигурации:**
```bash
curl -X POST -H "Authorization: Bearer <API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"name":"iphone","expires_at":"2026-12-31 12:00"}' \
  http://<IP>/<секретный_путь>/api/v1/peers
```

**Включить/выключить:**
```bash
curl -X PATCH -H "Authorization: Bearer <API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"enabled":false}' \
  http://<IP>/<секретный_путь>/api/v1/peers/<ID>
```

**Удалить:**
```bash
curl -X DELETE -H "Authorization: Bearer <API_TOKEN>" \
  http://<IP>/<секретный_путь>/api/v1/peers/<ID>
```

**Скачать конфиг:**
```bash
curl -H "Authorization: Bearer <API_TOKEN>" \
  -o client.conf \
  http://<IP>/<секретный_путь>/api/v1/peers/<ID>/config
```

**QR-код (PNG):**
```bash
curl -H "Authorization: Bearer <API_TOKEN>" \
  -o qr.png \
  http://<IP>/<секретный_путь>/api/v1/peers/<ID>/qr
```
