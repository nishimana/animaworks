from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""i18n strings for the ``animaworks migrate`` command."""

STRINGS: dict[str, dict[str, str]] = {
    "migrate.help": {
        "ja": "ランタイムデータのマイグレーションを実行",
        "en": "Run runtime data migrations",
    },
    "migrate.no_runtime": {
        "ja": "ランタイムディレクトリが初期化されていません: {data_dir}\n'animaworks init' を実行してください。",
        "en": "Runtime directory not initialized: {data_dir}\nRun 'animaworks init' first.",
    },
    "migrate.dry_run_header": {
        "ja": "=== ドライラン — 変更は行いません ===",
        "en": "=== Dry run — no changes will be made ===",
    },
    "migrate.step_result": {
        "ja": "[{name}] changed: {changed}, skipped: {skipped}",
        "en": "[{name}] changed: {changed}, skipped: {skipped}",
    },
    "migrate.complete": {
        "ja": "マイグレーション完了: {changed}件変更, {skipped}件スキップ",
        "en": "Migration complete: {changed} changed, {skipped} skipped",
    },
    "migrate.error_summary": {
        "ja": "エラー: {count}件のステップで失敗",
        "en": "Errors: {count} step(s) failed",
    },
    "migrate.server_warning": {
        "ja": "⚠ サーバーが実行中です。SQLite WALモードで安全ですが、プロンプト変更は次回ロード時に反映されます。",
        "en": "⚠ Server is running. SQLite WAL mode is safe, but prompt changes take effect on next load.",
    },
    "migrate.list_header": {
        "ja": "マイグレーションステップ一覧:",
        "en": "Migration steps:",
    },
}
