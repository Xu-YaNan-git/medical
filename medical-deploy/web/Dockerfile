# 医疗助手 web（nginx，非 root）。构建上下文 = /workspace（含两个 UI 目录）
#   docker build -f medical-deploy/web/Dockerfile .
FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY medical-patient-triage/ /usr/share/nginx/html/patient/
COPY medical-assistant-prototype/ /usr/share/nginx/html/doctor/

# 覆盖运行时配置为同源反代
COPY medical-deploy/web/config/patient-config.js /usr/share/nginx/html/patient/config.js
COPY medical-deploy/web/config/doctor-config.js  /usr/share/nginx/html/doctor/config.js

# 删除默认站点，放入本项目配置
USER root
RUN rm -f /etc/nginx/conf.d/default.conf \
 && rm -f /usr/share/nginx/html/patient/README.md /usr/share/nginx/html/doctor/README.md
COPY medical-deploy/web/default.conf      /etc/nginx/conf.d/default.conf
COPY medical-deploy/web/api-proxy.inc     /etc/nginx/conf.d/api-proxy.inc
COPY medical-deploy/web/proxy-common.inc  /etc/nginx/conf.d/proxy-common.inc
RUN chown -R 101:101 /usr/share/nginx/html && chmod -R a+rX /usr/share/nginx/html
USER 101

EXPOSE 8765 36967
HEALTHCHECK --interval=15s --timeout=3s --retries=3 CMD wget -qO- http://127.0.0.1:8765/ >/dev/null && wget -qO- http://127.0.0.1:36967/ >/dev/null || exit 1
