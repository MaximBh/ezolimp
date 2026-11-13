# Развёртывание EzOlimp на Ubuntu

Шаблоны рассчитаны на один публичный Ubuntu-сервер: Nginx принимает HTTPS и WebSocket, FastAPI слушает только `127.0.0.1:8001`, SQLite и кэш находятся вне каталога кода. Для PvP нужен один worker и один экземпляр приложения, пока состояние матчей хранится в памяти процесса. Nginx ограничивает число WebSocket-соединений с одного IP до 20; если пользователи часто выходят через школьный NAT, скорректируйте этот лимит с учётом ожидаемого числа одновременных игроков.

## 1. DNS, пакеты и пользователь службы

Направьте DNS `A` записи домена на публичный IPv4 сервера. Добавляйте `AAAA` запись только если IPv6 на сервере и в firewall действительно настроен. Подключитесь по SSH и установите нужные пакеты:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx certbot sqlite3
```

Создайте непривилегированную учётную запись и каталоги. Приложение не должно запускаться от `root` и не должно иметь права записи в каталог кода:

```bash
sudo adduser --system --group --no-create-home --home /var/lib/ezolimp ezolimp
sudo install -d -o root -g root -m 0755 /opt/ezolimp
sudo install -d -o ezolimp -g ezolimp -m 0750 /var/lib/ezolimp /var/cache/ezolimp
sudo install -d -o root -g ezolimp -m 0750 /etc/ezolimp
sudo install -d -o www-data -g www-data -m 0755 /var/www/letsencrypt
```

Поместите release проекта в `/opt/ezolimp`, включая `backend/`, `frontend/`, `requirements.lock` и `deploy/`. Владельцем кода оставьте `root` или отдельную учётную запись деплоя. Создайте окружение и установите закреплённые версии:

```bash
sudo python3 -m venv /opt/ezolimp/.venv
sudo /opt/ezolimp/.venv/bin/pip install --no-cache-dir -r /opt/ezolimp/requirements.lock
```

Если переносите SQLite из существующей установки, остановите старое приложение, сохраните резервную копию и переместите базу в `/var/lib/ezolimp/olimpiada.db`. Не переносите активный SQLite-файл обычным копированием, пока приложение работает: данные WAL могут ещё не попасть в основной файл.

## 2. Переменные и секрет

Создайте закрытый env-файл службы:

```bash
sudo install -o root -g ezolimp -m 0640 /opt/ezolimp/deploy/ubuntu/ezolimp.env.example /etc/ezolimp/ezolimp.env
sudoedit /etc/ezolimp/ezolimp.env
```

Замените `example.com` реальным доменом в `PUBLIC_ORIGIN` и `CORS_ALLOWED_ORIGINS`. Запишите в `JWT_SECRET` вывод `openssl rand -base64 48`. Не используйте один секрет для разных окружений и не помещайте env-файл в репозиторий. В production приложение отклонит запуск с HTTP origin, wildcard CORS или отсутствующим/коротким JWT secret.

## 3. Сертификат и Nginx

Сначала включите временный HTTP-only сайт для ACME challenge. В конфиге замените `example.com` на свой домен:

```bash
sudo install -m 0644 /opt/ezolimp/deploy/ubuntu/ezolimp.acme.nginx.conf /etc/nginx/sites-available/ezolimp
sudo ln -s /etc/nginx/sites-available/ezolimp /etc/nginx/sites-enabled/ezolimp
sudo nginx -t
sudo systemctl reload nginx
```

Выпустите сертификат через webroot challenge:

```bash
sudo certbot certonly --webroot -w /var/www/letsencrypt -d example.com
```

Установите production-конфиг `ezolimp.nginx.conf` поверх временного. Замените `example.com` и пути сертификата, если Certbot использовал другое имя. Конфиг оставляет HTTP challenge доступным для продления, перенаправляет остальной HTTP на HTTPS и проксирует WebSocket:

```bash
sudo install -m 0644 /opt/ezolimp/deploy/ubuntu/ezolimp.nginx.conf /etc/nginx/sites-available/ezolimp
sudoedit /etc/nginx/sites-available/ezolimp
sudo nginx -t
sudo systemctl reload nginx
```

Создайте deploy hook, чтобы Nginx перечитывал обновлённый сертификат:

```bash
sudo install -d -m 0755 /etc/letsencrypt/renewal-hooks/deploy
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx >/dev/null <<'EOF'
#!/bin/sh
systemctl reload nginx
EOF
sudo chmod 0755 /etc/letsencrypt/renewal-hooks/deploy/reload-nginx
sudo certbot renew --dry-run
```

## 4. Служба и firewall

Установите unit-файл и запустите приложение:

```bash
sudo install -m 0644 /opt/ezolimp/deploy/ubuntu/ezolimp.service /etc/systemd/system/ezolimp.service
sudo systemd-analyze verify /etc/systemd/system/ezolimp.service
sudo systemctl daemon-reload
sudo systemctl enable --now ezolimp nginx
sudo systemctl status ezolimp --no-pager
curl -fsS https://example.com/healthz
```

Служба ограничена systemd sandbox и ресурсами; доступ на запись есть только к `/var/lib/ezolimp` и `/var/cache/ezolimp`. Проверьте, что Uvicorn слушает только loopback:

```bash
ss -lntp | grep ':8001'
```

Откройте публично только SSH, TCP 80 и TCP 443. Не открывайте 8001, 3000 или 11434. Если включаете UFW, сначала разрешите SSH, чтобы не потерять удалённый доступ:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Проверяйте логи командой `sudo journalctl -u ezolimp -f`. Делайте регулярную резервную копию SQLite через SQLite backup API, например `sqlite3 /var/lib/ezolimp/olimpiada.db ".backup '/путь-к-защищённой-копии/olimpiada.db'"`; храните её вне публичной web-root и не копируйте `/etc/ezolimp/ezolimp.env` в общедоступные резервные копии.

После перехода браузерной авторизации на HttpOnly cookie пользователям потребуется войти снова. Текущая конфигурация предназначена для одного хоста и одного worker: для горизонтального масштабирования PvP-состояние и rate-limit storage нужно перенести в общее хранилище.
