# FastAPI Template

[![CI](https://github.com/zccing/fastapi_template/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/zccing/fastapi_template/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.14-3776AB.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)

> Minimal, production-minded, agent-ready FastAPI backend template with async PostgreSQL,
> Alembic, strict typing, safe configuration, and no speculative business stack.

一个面向生产约束、保持最小结构、适合开发者与代码 Agent 共同维护的 FastAPI 后端模板。
它提供安全配置边界、SQLAlchemy 异步连接、Alembic、CORS、Sentry、健康检查、严格类型
检查，以及真实 PostgreSQL CI 验证。

**[Use this template](https://github.com/zccing/fastapi_template/generate)**

## 核心特性

- Pydantic Settings 配置与部署边界校验，错误信息隐藏原始敏感输入。
- SQLAlchemy 异步 Engine、路径操作级 `AsyncSession` 和显式事务约定。
- Alembic 异步迁移环境和共享数据库命名约定。
- 显式 `UTCDateTime` 类型，不猜测 naive datetime 的时区。
- CORS、Sentry、FastAPI lifespan，以及不访问数据库的存活检查。
- Ruff、Pyright strict、pytest，以及 Python 3.14 和 PostgreSQL 18 CI。

模板当前没有业务领域、认证授权、任务队列、定时任务、缓存、前端或管理后台，也不会为
这些能力预装依赖或创建空目录。代码修改和条件性扩展规则见 [AGENTS.md](./AGENTS.md)。

适合需要自建领域模型、重视异步 PostgreSQL、类型检查和安全默认值的后端项目；不适合
单文件原型或希望直接获得完整 SaaS 业务栈的场景。

## 快速开始

环境要求：Python 3.14 或更高版本、[uv](https://docs.astral.sh/uv/) 和 PostgreSQL。

可以点击上方 **Use this template**，或使用 GitHub CLI 创建新仓库：

```shell
gh repo create my-api --template zccing/fastapi_template --private --clone
cd my-api
```

在项目根目录创建与 `.env` 连接地址匹配的 PostgreSQL 用户和数据库，然后执行：

```shell
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn src.main:app --reload
```

存活检查位于 `http://127.0.0.1:8000/healthcheck`。它只判断应用进程是否可响应，不访问
数据库，因此不能作为数据库 readiness 检查。

常用质量检查：

```shell
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -q
```

## 锁文件策略

本模板仓库不提交 `uv.lock`。Push、Pull Request 和每周定时 CI 使用 `uv sync` 重新解析
声明的依赖范围，以尽早发现上游兼容性问题。

通过模板生成业务项目后，应从 `.gitignore` 移除 `uv.lock`，生成并提交自己的锁文件：

```shell
uv lock
git add uv.lock .gitignore
uv sync --locked --no-dev
```

只有明确接受每次部署重新解析依赖时，才继续使用无锁的 `uv sync --no-dev`。

## 生成业务项目后

至少完成以下定制：

1. 修改 `pyproject.toml` 中的项目名、描述和版本。
2. 修改 `src.config.app_configs` 中的 OpenAPI 标题。
3. 为目标环境设置数据库地址、CORS 白名单和 Sentry 配置。
4. 生成并提交业务项目自己的 `uv.lock`。
5. 出现第一个业务用例后再创建领域包，并在 `alembic/env.py` 显式导入领域模型。

## 配置

应用从系统环境变量和当前工作目录的 `.env` 读取配置；因此命令默认在仓库根目录执行。
完整示例见 [`.env.example`](./.env.example)。本地开发可以使用已被 Git 忽略的 `.env`；
STAGING 和 PRODUCTION 的密钥应通过受控环境变量或 Secret Manager 注入，不进入源码、
日志或测试快照。

| 变量 | 必填 | 说明 |
|---|---|---|
| `DATABASE_ASYNC_URL` | 是 | `postgresql+asyncpg` 异步连接地址 |
| `ENVIRONMENT` | 是 | `LOCAL`、`TESTING`、`STAGING` 或 `PRODUCTION` |
| `DATABASE_POOL_SIZE` | 否 | 常驻连接池大小，默认 `16`；另有 10 个临时溢出连接 |
| `DATABASE_POOL_TTL` | 否 | 正整数，默认 `1200` 秒；下次取连接时检查并回收 |
| `DATABASE_POOL_PRE_PING` | 否 | 取连接前是否检查可用性，默认 `true` |
| `APP_VERSION` | 否 | OpenAPI 展示的应用版本，默认 `0.1.0` |
| `ROOT_PATH` | 否 | 反向代理剥离的挂载前缀，默认空字符串 |
| `SENTRY_DSN` | 否 | 设置后启用 Sentry |
| `CORS_ORIGINS` | 否 | 明确 Origin 的 JSON 数组 |
| `CORS_ORIGINS_REGEX` | 否 | 仅允许在 LOCAL 或 TESTING 使用的 Origin 正则 |
| `CORS_HEADERS` | 否 | 允许请求头的 JSON 数组 |
| `CORS_ALLOW_CREDENTIALS` | 否 | 是否允许 Cookie 等浏览器凭据 |

- CORS Origin 只允许 HTTP(S) 协议、主机和可选端口；配置会规范化大小写、默认端口和
  尾部 `/`，并拒绝凭据、路径、查询与片段。部署环境禁止 wildcard 和 Origin 正则；
  启用凭据时任何环境都禁止 wildcard。
- LOCAL、TESTING 和 STAGING 保留 OpenAPI；PRODUCTION 隐藏 `/docs`、`/redoc` 和
  `/openapi.json`。若 STAGING 对公网开放，应在反向代理层增加访问控制。
- `ROOT_PATH` 只表示代理剥离的挂载前缀，不是 API 版本前缀；版本路由应放在领域
  `APIRouter` 上。
- 需要统一 UTC 输出的业务时间字段使用 `src.schemas.UTCDateTime`。它拒绝无时区输入，
  并在 JSON 中输出 UTC `Z`；普通 `datetime` 不会被隐式归一化。

## 数据库与迁移

### Session 与事务

- 路由通过 `DBSession` 获取路径操作级 `AsyncSession`，依赖在响应发送前关闭它。
- 一个 Session 只属于一个请求或独立任务，不在并发任务间共享，也不传给
  `BackgroundTasks` 或独立 Worker。
- 只读 Service 不提交；顶层写 Service 在全部操作成功后提交一次，helper 不提交。
- 需要数据库生成值时使用 `flush()`；提交前异常由 Session 关闭回滚未提交事务。
- 响应所需关系和延迟字段在 Session 有效期内显式加载，不在序列化时触发隐式 I/O。

详细事务、查询和异步边界见 [AGENTS.md](./AGENTS.md)。

### 模型与迁移

领域模型继承 `src.models.Base`，使用单数 `snake_case` 表名，并沿用共享命名约定。新增
领域模型后，在 `alembic/env.py` 显式导入其 `models` 模块；Alembic 不会自动扫描
`src/`。

运行任何连接数据库的 Alembic 命令前，先确认目标环境、主机和数据库且不要输出凭据。
默认只连接可丢弃的本地或测试数据库；共享、STAGING 或 PRODUCTION 目标需要用户对精确
目标的明确授权。

```shell
uv run alembic revision --autogenerate -m "create item table"
uv run alembic upgrade head
uv run alembic check
```

`--autogenerate` 只生成草稿。提交前检查 upgrade、downgrade、可空性、外键、索引、默认值
和重命名；不要修改已执行的 revision。需要验证回退时，只在可丢弃数据库执行：

```shell
uv run alembic downgrade -1
uv run alembic upgrade head
```

迁移必须静态、确定、可审查。结构迁移在安全可行时提供有意义的 downgrade；不可逆数据
迁移不得伪造可恢复性，必须说明范围、前置条件及备份恢复方案。

## 目录与扩展

当前 `src/` 只包含应用级基础设施。出现真实业务后，在 `src/{domain}/` 中按需创建
`router.py`、`schemas.py`、`models.py`、`service.py` 等实际使用的模块，并在
`src.main` 挂载领域路由。认证授权、后台任务、缓存、领域配置、前端和流式响应的触发
条件与实现边界见 [AGENTS.md](./AGENTS.md)，不要提前搭建空结构。

## 贡献与安全

提交改动前请阅读 [CONTRIBUTING.md](./CONTRIBUTING.md)。安全漏洞不要通过公开 Issue
披露，请按照 [SECURITY.md](./SECURITY.md) 使用私密报告入口。

本项目采用 [MIT License](./LICENSE)。
