/* 运行时 API 地址配置（本地默认直连；部署时由 nginx 镜像覆盖为同源 /patient-api、/doctor-api） */
window.APP_CONFIG = Object.assign({ patientApiBase: 'http://127.0.0.1:8001', doctorApiBase: 'http://127.0.0.1:8000' }, window.APP_CONFIG || {});
