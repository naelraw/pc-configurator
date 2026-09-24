# Mise en cache nginx d'une réponse publique (inclus après pcradar-proxy.inc)
proxy_cache pcradar;
proxy_cache_key "$scheme$host$request_uri|$pcradar_gzip";
proxy_set_header Accept-Encoding $pcradar_gzip;
proxy_ignore_headers Vary;
proxy_cache_lock on;
proxy_cache_lock_timeout 10s;
proxy_cache_background_update on;
proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
proxy_cache_revalidate on;
add_header X-Cache $upstream_cache_status always;
