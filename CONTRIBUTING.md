# Contributing

感谢你改进这个模板。提交改动前，请先确认它服务于当前模板能力，而不是为尚未出现的
业务需求预建抽象或依赖。

## 开发环境

```shell
cp .env.example .env
uv sync
```

运行质量检查：

```shell
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest -q
```

## 提交改动

- 修复行为问题时，优先增加能复现问题的最小测试。
- 不顺手重构无关代码，也不引入只有一个实现的 Repository、BaseService 或工厂。
- 修改配置、外部接口、依赖或部署行为时，同步更新 README 和相关测试。
- 涉及认证、数据库结构、事务语义或其他高风险边界时，先创建 Issue 说明失败语义和兼容性影响。
- Pull Request 应说明动机、改动范围、实际执行的检查和仍未验证的内容。

提交信息使用 Conventional Commits，例如 `fix(config): reject invalid origin`。
