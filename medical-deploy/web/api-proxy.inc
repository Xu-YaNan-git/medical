# 共享的 API 反代（两个 server 都 include）。变量 + resolver：API 容器未就绪时 nginx 仍可启动。
location /patient-api/ {
    set $patient_upstream http://patient-api:8001;
    rewrite ^/patient-api/(.*)$ /$1 break;
    proxy_pass $patient_upstream;
    # 上游 3xx（如 FastAPI 尾斜杠 307）的 Location 改写为同源相对路径，避免 http://127.0.0.1/... 丢端口/前缀
    proxy_redirect ~^https?://[^/]+/(.*)$ /patient-api/$1;
    include /etc/nginx/conf.d/proxy-common.inc;
}

location /doctor-api/ {
    set $doctor_upstream http://doctor-api:8000;
    rewrite ^/doctor-api/(.*)$ /$1 break;
    proxy_pass $doctor_upstream;
    proxy_redirect ~^https?://[^/]+/(.*)$ /doctor-api/$1;
    include /etc/nginx/conf.d/proxy-common.inc;
}
