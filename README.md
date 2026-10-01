# FastAPI Template

[![CI](https://github.com/zccing/fastapi_template/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/zccing/fastapi_template/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.14-3776AB.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](./LICENSE)

一个精简的 FastAPI 后端模板，提供配置校验、异步 PostgreSQL/SQLite、Alembic 迁移、
CORS、可选 Sentry，以及 Ruff、Pyright strict 和 pytest。适合从真实业务需求开始构建
领域模型，不预装认证、任务队列、缓存、前端或管理后台。

**[Use this template](https://github.com/zccing/fastapi_template/generate)**

## 快速开始

需要 Python 3.14+ 和 [uv](https://docs.astral.sh/uv/)。所有命令均在仓库根目录执行。

```shell
gh repo create my-api --template zccing/fastapi_template --private --clone
cd my-api
cp .env.example .env
uv sync
```

启动前，在 `.env` 中选择数据库地址：

| 后端 | `DATABASE_ASYNC_URL` 示例 | 准备工作 |
|---|---|---|
| PostgreSQL（示例默认值） | `postgresql+asyncpg://app:app@localhost:5432/app` | 创建匹配的本地用户和数据库 |
| SQLite | `sqlite+aiosqlite:///./db.sqlite3` | 确保父目录可写；文件会自动创建 |

示例凭据仅用于可丢弃的本地环境。确认目标数据库后执行：

```shell
uv run alembic upgrade head
uv run uvicorn src.main:app --reload
```

访问 `http://127.0.0.1:8000/docs` 查看 API 文档。
`GET http://127.0.0.1:8000/healthcheck` 返回 `{"status":"ok"}`，只检测进程是否响应，
不访问数据库或外部服务，不能替代数据库 readiness 检查。当前没有业务表和 revision，
`upgrade head` 不会替你创建业务表。

## 配置

配置入口是 [`src/config.py`](src/config.py)，完整示例见 [`.env.example`](.env.example)。
加载优先级为构造参数、环境变量、当前工作目录的 `.env`、默认值。必填字段没有隐式
环境默认值；错误信息隐藏原始输入，数据库和 Sentry 地址不参与 Settings 的 repr。
不要把 `model_dump()` 或 `ValidationError.errors()` 直接写进日志，它们仍可能含原始值。

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_ASYNC_URL` | 必填 | 只接受 `postgresql+asyncpg` 或文件型 `sqlite+aiosqlite` |
| `ENVIRONMENT` | 必填 | `LOCAL`、`TESTING`、`STAGING`、`PRODUCTION` |
| `DATABASE_POOL_SIZE` | `16` | 每个进程的常驻池容量上限；另有 10 个临时溢出连接 |
| `DATABASE_POOL_TTL` | `1200` | 正整数秒数，下次取连接时检查并回收 |
| `DATABASE_POOL_PRE_PING` | `true` | 取连接前检查可用性 |
| `APP_VERSION` | `0.1.0` | OpenAPI 展示版本 |
| `ROOT_PATH` | 空字符串 | 反向代理剥离的挂载前缀，如 `/gateway` |
| `SENTRY_DSN` | 未设置 | 设置后启用 Sentry，空字符串显式关闭 |
| `CORS_ORIGINS` | `[]` | HTTP(S) Origin 的 JSON 数组 |
| `CORS_ORIGINS_REGEX` | 未设置 | 仅 LOCAL/TESTING 可用，空字符串显式关闭 |
| `CORS_HEADERS` | `["Content-Type","Authorization","X-API-Key"]` | 允许跨域请求头 |
| `CORS_ALLOW_CREDENTIALS` | `false` | 是否允许浏览器凭据 |

空环境变量会覆盖 `.env`，不会回退到其中的旧值。`ROOT_PATH=` 清除代理前缀；必填字段、
数值和布尔字段不接受空字符串，数组清空使用 `[]`。`.env.example` 中的本地示例值可能
与表中的程序默认值不同。

### 数据库地址

SQLite 路径按原文交给 SQLAlchemy，保留 `..`、空格和中文，不做 HTTP URL 编码。
相对路径基于进程工作目录；绝对路径使用四个斜杠，例如
`sqlite+aiosqlite:////srv/app/data/app.db`。父目录需要提前创建，不支持内存数据库、
authority、查询参数或片段。

从旧模板更新已有项目时，先核实 SQLite 文件的位置：旧版 URL 规范化可能已改写含 `..`、
空格或中文的路径，修复后会使用配置中原本指定的文件。PostgreSQL 用户名和密码中的
特殊字符仍需按连接地址规则编码。

### CORS 与文档

- Origin 只允许协议、主机和可选端口；会规范化大小写、默认端口和尾部 `/`，拒绝凭据、
  路径、查询和片段。STAGING/PRODUCTION 禁止 wildcard 与 Origin 正则；启用凭据时
  所有环境均禁止 wildcard。
- LOCAL、TESTING、STAGING 保留 `/docs`、`/redoc` 和 `/openapi.json`，PRODUCTION 关闭。
  关闭文档不等于认证；公开的 STAGING 应在反向代理层设置访问控制。
- `ROOT_PATH` 是代理剥离的前缀，不是 API 版本。API 版本在领域 `APIRouter` 上定义。

## 数据库与迁移

应用使用惰性连接的 Engine；lifespan 退出时释放连接池。`create_database_engine()`
统一应用和测试的池配置，SQLite 的每个应用连接都启用外键约束。

路由通过 `DBSession` 获取 Session，响应发送前关闭。一个 Session 只属于一个请求或
独立任务；并发和后台任务各自创建 Session。只读 Service 不提交，顶层写 Service
在全部操作成功后提交一次，helper 只做 `flush()`；关闭 Session 会回滚未提交事务。
响应需要的关系和延迟字段必须显式加载完成，避免序列化时触发隐式 I/O。

领域模型继承 `src.models.Base`，沿用共享命名约定，并在 `alembic/env.py` 显式导入
领域 `models` 模块。Alembic 不自动扫描目录，已有迁移环境不需要重新初始化。

连接前确认环境、主机和数据库，不输出凭据。默认只用可丢弃的本地或测试库；共享、
STAGING、PRODUCTION 目标需要对精确目标的明确授权。

```shell
uv run alembic revision --autogenerate -m "create item table"
uv run alembic upgrade head
uv run alembic check
```

自动生成只是草稿：检查 upgrade/downgrade、可空性、外键、索引、默认值和重命名。
文件名含日期、revision ID 和描述，避免同日同名覆盖；生成后先 Ruff 修复，再格式化。
保留 batch migration 以支持 SQLite 的表结构变更，但仍需在两个后端实际验证。

不要修改已执行的 revision。结构变更安全可行时提供 downgrade；不可逆数据迁移应说明
前置条件、影响及备份恢复方案。需要验证回退时，只在可丢弃数据库运行
`uv run alembic downgrade -1`，随后再次 `upgrade head` 和 `alembic check`。

## 测试与质量检查

```shell
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -q
```

测试为每个 Config 字段注入隔离值，禁用 Sentry，SQLite 使用临时文件；运行测试无需
修改本机 `.env`。配置、API、数据库、迁移和共享类型的测试分别放在对应 `test_*.py`。

PostgreSQL 行为测试需要显式指定**可丢弃测试库**，会创建并删除 `template_test_*` 表。
以下是本地示例地址，不要替换成共享或生产库：

```shell
TEST_POSTGRES_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest -q
```

未设置 `TEST_POSTGRES_URL` 时，pytest 会明确跳过 PostgreSQL 用例；不会自动连接应用的
`DATABASE_ASYNC_URL`。CI 在 PostgreSQL 18 上运行数据库行为测试，并在 PostgreSQL 与
SQLite 上执行 `upgrade head` 和 `alembic check`。Pyright 同时检查应用、测试和迁移代码。
当前无业务模型，迁移检查验证的是迁移环境，新增模型后仍需验证实际 schema 变更。

## 部署与锁文件

本模板不提交 `uv.lock`；Push、Pull Request 和每周 CI 从干净检出解析依赖范围，以发现
上游兼容性问题。已有本地锁文件时，`uv sync` 会复用兼容版本；主动验证新版本使用
`uv lock --upgrade`，然后完整运行检查。

生成业务项目后，从 `.gitignore` 移除 `uv.lock`，生成并提交自己的锁文件，并把业务 CI
的同步命令改为 `uv sync --locked`：

```shell
uv lock
git add uv.lock .gitignore
uv sync --locked --no-dev
uv run --locked --no-dev uvicorn src.main:app --host 0.0.0.0 --port 8000
```

部署前通过受控环境变量或 Secret Manager 设置 `ENVIRONMENT=PRODUCTION`、数据库地址、
CORS 白名单及可选 Sentry。迁移由部署流程单独执行，应用启动不自动迁移；生产命令不使用
`--reload`。STAGING/PRODUCTION 的凭据不进入 `.env` 镜像、源码、日志或测试快照。

每个 worker/副本有自己的池，数据库连接预算至少考虑
`实例数 * worker 数 * (DATABASE_POOL_SIZE + 10)`。SQLite 使用持久化可写卷，优先单实例、
低写并发；需要多副本或高写并发时选 PostgreSQL，增加连接池并不能提高 SQLite 写并发。

## 项目定制与扩展

生成业务项目后至少完成：

1. 修改 `pyproject.toml` 中的项目名、描述、版本，以及 `src/main.py` 的 OpenAPI 标题。
2. 更新本 README 的仓库链接、徽章、贡献和安全报告入口。
3. 设置目标环境的数据库、CORS 与外部集成，提交锁文件并调整业务 CI。
4. 按真实用例创建 `src/{domain}/`，挂载 Router，并在 Alembic 注册模型。
5. 统一 UTC 输出的业务字段使用 `src.schemas.UTCDateTime`；它要求时区并保留微秒，
   不会隐式转换普通 datetime。

日常代码约定见 [AGENTS.md](AGENTS.md)。认证、后台任务、缓存、前端和流式端点的选型
条件见 [按需扩展](docs/extensions.md)。贡献流程见 [CONTRIBUTING.md](CONTRIBUTING.md)，
安全问题通过 [SECURITY.md](SECURITY.md) 的私密入口报告。

本项目采用 [MIT License](LICENSE)。
