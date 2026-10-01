from pathlib import Path
from shutil import copyfile

from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command


def test_revisions_with_the_same_message_have_unique_filenames(tmp_path: Path) -> None:
    """生成不访问数据库的空 revision，避免同日同名迁移互相覆盖。"""

    migrations = tmp_path / "alembic"
    (migrations / "versions").mkdir(parents=True)
    copyfile("alembic/script.py.mako", migrations / "script.py.mako")
    config = Config("alembic.ini")
    config.set_main_option("script_location", str(migrations))

    first = command.revision(config, message="update item", rev_id="first")
    second = command.revision(config, message="update item", rev_id="second")

    assert first is not None and not isinstance(first, list)
    assert second is not None and not isinstance(second, list)
    assert first.path != second.path
    assert "first" in Path(first.path).stem
    assert "second" in Path(second.path).stem
    revisions = ScriptDirectory.from_config(config)
    assert [revision.revision for revision in revisions.walk_revisions()] == ["second", "first"]
