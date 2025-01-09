import os
import hashlib
import subprocess
import json
import re
from pathlib import Path
from typing import Optional, Tuple

class PRStatusChecker:
    def __init__(self):
        self.cache_dir = Path("/tmp/gh_pr_check_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.repo_id = self._get_repo_id()

    def _get_repo_id(self) -> str:
        """リポジトリの一意のIDを生成"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True
            )
            repo_path = result.stdout.strip()
            return hashlib.md5(repo_path.encode()).hexdigest()
        except subprocess.CalledProcessError:
            raise RuntimeError("gitリポジトリが見つかりません")

    def get_source_branch(self, merge_msg: str) -> Optional[str]:
        """マージメッセージからソースブランチ名を抽出"""
        pattern = r"Merge\s+branch\s+'([^']+)'"
        match = re.search(pattern, merge_msg)
        if match:
            return match.group(1)
        return None

    def _check_gh_cli(self) -> bool:
        """GitHub CLIの利用可能性をチェック"""
        # GitHub CLIの存在確認
        if not subprocess.run(["which", "gh"], capture_output=True).returncode == 0:
            print("エラー: GitHub CLI (gh) がインストールされていません")
            return False

        # 認証状態の確認
        if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode != 0:
            print("エラー: GitHub CLIが認証されていません")
            print("gh auth login を実行してログインしてください")
            return False

        return True

    def check_pr_status(self, branch_name: str) -> Tuple[bool, str]:
        """PRのステータスをチェック"""
        cache_file = self.cache_dir / f"{self.repo_id}_{branch_name}.cache"

        # キャッシュチェック
        if cache_file.exists():
            print(f"キャッシュ: ブランチ '{branch_name}' の結果を再利用しています")
            result = cache_file.read_text().strip()
            return result == "0", ""

        # GitHub CLIチェック
        if not self._check_gh_cli():
            return False, "GitHub CLI関連のエラー"

        print(f"ブランチ '{branch_name}' のPRをチェックしています...")

        # PRの検索
        try:
            result = subprocess.run(
                ["gh", "pr", "list", "--head", branch_name, "--json", "number"],
                capture_output=True,
                text=True,
                check=True
            )
            prs = json.loads(result.stdout)
            if not prs:
                print(f"警告: ブランチ {branch_name} のPRが見つかりません")
                cache_file.write_text("0")
                return True, ""

            pr_number = prs[0]["number"]
            print(f"PR #{pr_number} のステータスチェックを確認しています...")

            # ステータスチェックの取得
            result = subprocess.run(
                ["gh", "pr", "view", str(pr_number), "--json", "statusCheckRollup"],
                capture_output=True,
                text=True,
                check=True
            )
            status_data = json.loads(result.stdout)
            failed_checks = [
                check for check in status_data["statusCheckRollup"]
                if check["state"] == "FAILURE"
            ]

            if failed_checks:
                error_msg = "失敗したチェック:\n" + "\n".join(
                    f"- {check['context']}: {check['description']}"
                    for check in failed_checks
                )
                print(f"エラー: PR #{pr_number} のステータスチェックが失敗しています")
                print(error_msg)
                cache_file.write_text("1")
                return False, error_msg

            print("すべてのステータスチェックがパスしています")
            cache_file.write_text("0")
            return True, ""

        except subprocess.CalledProcessError as e:
            error_msg = f"GitHub CLIコマンドの実行中にエラーが発生: {e}"
            return False, error_msg

    def main(self):
        """メイン処理"""
        try:
            git_dir = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                check=True
            ).stdout.strip()

            merge_msg_file = Path(git_dir) / "MERGE_MSG"
            if not merge_msg_file.exists():
                raise RuntimeError(f"Merge message file not found: {merge_msg_file}")

            merge_msg = merge_msg_file.read_text()
            print("Merge Message:")
            print(merge_msg)

            # マージメッセージの検証（必要に応じてカスタマイズ）
            if "expected text" not in merge_msg:
                raise RuntimeError("Merge message does not contain the expected text.")

            branch_name = self.get_source_branch(merge_msg)
            if not branch_name:
                raise RuntimeError("Could not extract source branch name from merge message")

            success, error_msg = self.check_pr_status(branch_name)
            if not success:
                raise RuntimeError(f"PR status check failed: {error_msg}")

            print("PR status check passed.")
            return 0

        except Exception as e:
            print(f"Error: {e}")
            return 1

if __name__ == "__main__":

    print("#### pr_status_checker.pyを実行します。")
    PRStatusChecker().main()
