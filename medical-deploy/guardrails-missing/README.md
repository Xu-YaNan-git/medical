空占位构建上下文：仅当 ../medical-guardrails 不存在时由 deploy.sh 通过 GUARDRAILS_SRC 指向这里，
使 `COPY --from=guardrails` 不失败；Dockerfile 检测到无 pyproject.toml 即跳过安装，API 护栏 fail-open。
