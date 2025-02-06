import os
import re
import subprocess
import json
import time
from datetime import datetime
from pathlib import Path


class PRStatusChecker:
    @classmethod
    def check_pr_status(cls) -> int:
        print("GitHub PR Checker を開始します...")
        try:
            # ブランチ名の抽出
            feature_branch_name = cls._get_feature_branch()
            if not feature_branch_name:
                print("マージ中ではありません。スキップします。")
                return 0

            base_branch_name = cls._get_base_branch()
            if (
                feature_branch_name
                and base_branch_name
                and not cls.is_fms_member(feature_branch=feature_branch_name, base_branch=base_branch_name)
            ):
                print("FMsメンバーではありません。スキップします。")
                return 0

            # PRのステータスチェック
            if not cls._check_pr_status(branch_name=feature_branch_name):
                print("\nPRの概要欄を確認後チェックをつけてください。")
                cls.reset_to_before_merge()
                return 1

            print("\nPRのステータスはSUCCESSです。Pushします。")
            return 0

        except Exception as e:
            print(f"予期せぬエラーが発生しました: {e}")
            cls.reset_to_before_merge()
            return 1

    @classmethod
    def _run_command(cls, command: list) -> str:
        """コマンドを実行して結果を返す"""
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout.strip()

    @classmethod
    def _get_feature_branch(cls) -> str | None:
        """マージ元のブランチ名取得"""
        git_dir = cls._run_command(["git", "rev-parse", "--git-dir"])
        merge_msg_file = os.getcwd() / Path(git_dir) / "MERGE_MSG"

        if not merge_msg_file.exists():
            return None

        merge_msg = merge_msg_file.read_text()

        match = re.search(r"Merge\s+branch\s+'([^']+)'", merge_msg)
        if match:
            return match.group(1)
        return None

    @classmethod
    def _get_base_branch(cls) -> str | None:
        """マージ先のブランチ名取得"""
        return cls._run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])

    @classmethod
    def _check_github_cli_availability(cls) -> bool:
        """GitHub CLIが利用可能か確認"""
        # GitHub CLIの存在確認
        if os.name == "posix":
            exist_check_command = "which"
        else:
            exist_check_command = "where.exe"

        if subprocess.run([exist_check_command, "gh"], capture_output=True).returncode != 0:
            print("エラー: GitHub CLI (gh) がインストールされていません")
            cls.reset_to_before_merge()
            return False

        # 認証状態の確認
        if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode != 0:
            print("エラー: GitHub CLIが認証されていません")
            print("gh auth login を実行してログインしてください")
            cls.reset_to_before_merge()
            return False

        return True

    @classmethod
    def _check_pr_status(cls, branch_name: str) -> bool:
        """PRのステータスをチェック"""
        # GitHub CLIのチェック
        if not cls._check_github_cli_availability():
            return False

        print(f"\nブランチ '{branch_name}' のPRを検索しています...")

        try:
            # PRの検索
            pr_list = cls._run_command(["gh", "pr", "list", "--head", branch_name, "--json", "number"])
            prs = json.loads(pr_list)

            if not prs:
                print(f"警告: ブランチ {branch_name} のPRが見つかりません")
                return True

            # 通常の開発フローでは1つのブランチに1つしかPRを立てないため、先頭のPRを取得
            pr_number = prs[0]["number"]

            print(f"PR #{pr_number} のステータスチェックを確認しています...")

            # ステータスチェックの取得
            status_json = cls._run_command(["gh", "pr", "view", str(pr_number), "--json", "statusCheckRollup"])
            status_logs = json.loads(status_json).get("statusCheckRollup", None)

            if not status_logs:
                return True

            latest_conclusion = max(status_logs, key=lambda status_log: status_log["completedAt"]).get(
                "conclusion", "FAILURE"
            )

            # FAILURE以外（SKIPも）はSUCCESSとみなす
            return not latest_conclusion == "FAILURE"

        except subprocess.CalledProcessError as e:
            print(f"GitHub CLIコマンドの実行中にエラーが発生: {e}")
            return False

    @classmethod
    def reset_to_before_merge(cls):
        """差分を破棄して前の作業ブランチに戻る"""
        print("git reset --mergeを実行してgit statusリセット後に再試行してください。")

        cls._run_command(["git", "reset", "--merge"])

        cls._run_command(["git", "checkout", "-"])

    @classmethod
    def is_fms_member(cls, feature_branch: str, base_branch: str) -> bool:
        """PRのマージコミット以外の初めのコミットがFMs社員のコミットか確認"""
        try:
            commit_hashes = cls._run_command(
                [
                    "git",
                    "log",
                    "--reverse",
                    "--format=%H",
                    f"origin/{base_branch}..origin/{feature_branch}",
                ]
            )
        except Exception as e:
            print("コミット履歴取得時に問題が発生しました。", e)
            return False

        if commit_hashes.startswith("fatal"):
            print("PRのコミットを取得できませんでした。")
            return False

        for commit_hash in commit_hashes.splitlines():
            commit_hash = commit_hash.strip("'")
            result = cls._run_command(["git", "show", "-s", "--format=%P#%ae", commit_hash])

            parent_commits, commiter_email = result.split("#")
            if len(parent_commits.split()) > 1:  # マージコミットはスキップ
                continue

            return "@fullmarks.co.jp" in commiter_email
