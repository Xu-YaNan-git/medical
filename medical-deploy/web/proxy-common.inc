proxy_http_version 1.1;
proxy_set_header Host $http_host;   # 保留端口（$host 会丢掉 :8765/:36967）
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header Connection "";
# 流式 / SSE 友好
proxy_buffering off;
proxy_cache off;
proxy_request_buffering off;
proxy_connect_timeout 10s;
proxy_send_timeout 300s;
proxy_read_timeout 300s;
