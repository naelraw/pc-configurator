# Paramètres communs d'envoi vers l'application (inclus dans chaque location)
proxy_pass http://pcradar_app;
proxy_http_version 1.1;
proxy_set_header Connection "";
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_read_timeout 150s;
proxy_send_timeout 150s;
proxy_buffer_size 16k;
proxy_buffers 64 16k;
