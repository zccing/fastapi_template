import gzip
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
BACKUP_SCRIPT = PROJECT_ROOT / "scripts/postgres/backup"
RESTORE_SCRIPT = PROJECT_ROOT / "scripts/postgres/restore"


def _write_command(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(f"#!/bin/sh\nset -eu\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _script_env(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    bin_directory = tmp_path / "bin"
    backup_directory = tmp_path / "backups"
    call_log = tmp_path / "calls.log"
    bin_directory.mkdir()
    backup_directory.mkdir()

    env = os.environ | {
        "PATH": f"{bin_directory}:{os.environ['PATH']}",
        "POSTGRES_USER": "app_user",
        "POSTGRES_DB": "expected_database",
        "BACKUP_DIRECTORY": str(backup_directory),
        "CALL_LOG": str(call_log),
        "TMPDIR": str(tmp_path),
    }
    return env, bin_directory, call_log


def _run_script(
    script: Path,
    *arguments: str,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - 测试仅执行仓库内固定脚本。
        [script, *arguments],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_successful_restore_commands(bin_directory: Path) -> None:
    _write_command(
        bin_directory,
        "pg_restore",
        'printf \'pg_restore %s\n\' "$*" >> "$CALL_LOG"',
    )
    _write_command(bin_directory, "dropdb", 'printf \'dropdb %s\n\' "$*" >> "$CALL_LOG"')
    _write_command(
        bin_directory,
        "createdb",
        'printf \'createdb %s\n\' "$*" >> "$CALL_LOG"',
    )


def test_backup_uses_configured_database_and_creates_a_valid_archive(tmp_path: Path) -> None:
    env, bin_directory, call_log = _script_env(tmp_path)
    _write_command(
        bin_directory,
        "pg_dump",
        """
for argument in "$@"; do
  case "$argument" in
    --file=*) output_file=${argument#--file=} ;;
  esac
done
printf 'archive' > "$output_file"
printf 'pg_dump %s\n' "$*" >> "$CALL_LOG"
""".strip(),
    )
    _write_command(
        bin_directory,
        "pg_restore",
        'printf \'pg_restore %s\n\' "$*" >> "$CALL_LOG"',
    )

    result = _run_script(BACKUP_SCRIPT, env=env)

    assert result.returncode == 0, result.stderr
    assert "--dbname=expected_database" in call_log.read_text(encoding="utf-8")
    assert len(list((tmp_path / "backups").glob("backup-*.dump"))) == 1


def test_backup_propagates_pg_dump_failure(tmp_path: Path) -> None:
    env, bin_directory, call_log = _script_env(tmp_path)
    _write_command(
        bin_directory,
        "pg_dump",
        "printf 'pg_dump failed\n' >> \"$CALL_LOG\"; exit 7",
    )
    _write_command(
        bin_directory,
        "pg_restore",
        "printf 'unexpected pg_restore\n' >> \"$CALL_LOG\"",
    )

    result = _run_script(BACKUP_SCRIPT, env=env)

    assert result.returncode == 7
    assert "created and validated" not in result.stdout
    assert "unexpected pg_restore" not in call_log.read_text(encoding="utf-8")
    assert list((tmp_path / "backups").iterdir()) == []


def test_restore_validates_archive_before_dropping_database(tmp_path: Path) -> None:
    env, bin_directory, call_log = _script_env(tmp_path)
    (tmp_path / "backups" / "invalid.dump").write_text("invalid", encoding="utf-8")
    _write_command(
        bin_directory,
        "pg_restore",
        'printf \'pg_restore %s\n\' "$*" >> "$CALL_LOG"; exit 9',
    )
    _write_command(bin_directory, "dropdb", "printf 'dropdb\n' >> \"$CALL_LOG\"")
    _write_command(bin_directory, "createdb", "printf 'createdb\n' >> \"$CALL_LOG\"")

    result = _run_script(RESTORE_SCRIPT, "invalid.dump", "--confirm-drop", env=env)

    calls = call_log.read_text(encoding="utf-8")
    assert result.returncode != 0
    assert "pg_restore --list" in calls
    assert "dropdb" not in calls
    assert "createdb" not in calls


def test_restore_recreates_database_only_after_validation(tmp_path: Path) -> None:
    env, bin_directory, call_log = _script_env(tmp_path)
    (tmp_path / "backups" / "valid.dump").write_text("archive", encoding="utf-8")
    _write_successful_restore_commands(bin_directory)

    result = _run_script(RESTORE_SCRIPT, "valid.dump", "--confirm-drop", env=env)

    calls = call_log.read_text(encoding="utf-8").splitlines()
    assert result.returncode == 0, result.stderr
    assert calls[0].startswith("pg_restore --list")
    assert calls[1].startswith("dropdb ")
    assert calls[2].startswith("createdb ")
    assert "--single-transaction" in calls[3]


def test_restore_supports_legacy_gzip_archive(tmp_path: Path) -> None:
    env, bin_directory, _call_log = _script_env(tmp_path)
    backup_file = tmp_path / "backups" / "legacy.dump.gz"
    with gzip.open(backup_file, "wb") as archive:
        archive.write(b"archive")
    _write_successful_restore_commands(bin_directory)

    result = _run_script(RESTORE_SCRIPT, backup_file.name, "--confirm-drop", env=env)

    assert result.returncode == 0, result.stderr
    assert list(tmp_path.glob("postgres-restore.*")) == []


def test_restore_requires_explicit_confirmation_and_a_plain_file_name(tmp_path: Path) -> None:
    env, _bin_directory, _call_log = _script_env(tmp_path)

    for arguments, message in (
        (["backup.dump"], "--confirm-drop"),
        (["../backup.dump", "--confirm-drop"], "plain file name"),
    ):
        result = _run_script(RESTORE_SCRIPT, *arguments, env=env)

        assert result.returncode == 2
        assert message in result.stderr
