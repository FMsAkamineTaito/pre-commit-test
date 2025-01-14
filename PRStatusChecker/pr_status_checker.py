import os
import hashlib
import subprocess
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


class PRStatusChecker:
    LOG_FILE="/tmp/pre_commit_result.txt"

    @classmethod
    def check_status(cls) -> int:
        """スクリプトのメインエントリーポイント"""
        
        cls._run_command(["ls", ".gjt/"])

        # マージ操作中かどうかを確認
        if not cls._is_merging():

            return 0

        try:
            # Gitディレクトリの確認
            git_dir = cls._run_command(["git", "rev-parse", "--git-dir"])

            # マージメッセージの読み込みと確認
            merge_msg_file = os.getcwd() / Path(git_dir) / "MERGE_MSG"

            if not merge_msg_file.exists():
    

                cls.reset_to_before_merge()
                return 1

            merge_msg = merge_msg_file.read_text()

            # ブランチ名の抽出
            branch_name = cls._extract_branch_name(merge_msg)
            if not branch_name:
    
                cls.reset_to_before_merge()
                return 1

            # PRのステータスチェック
            success = cls._check_pr_status(branch_name)
            if not success:
    
    
                cls.reset_to_before_merge()
                return 1


            return 0

        except Exception as e:

            cls.reset_to_before_merge()
            return 1

    @classmethod
    def _run_command(cls, command: list) -> str:
        """コマンドを実行して結果を返す"""
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout.strip()

    @classmethod
    def _get_repo_id(cls) -> str:
        """リポジトリの一意のIDを生成"""
        repo_path = cls._run_command(["git", "rev-parse", "--show-toplevel"])
        return hashlib.md5(repo_path.encode()).hexdigest()

    @classmethod
    def _extract_branch_name(cls, merge_msg: str) -> Optional[str]:
        """マージメッセージからブランチ名を抽出"""
        pattern = r"Merge\s+branch\s+'([^']+)'"
        match = re.search(pattern, merge_msg)
        if match:
            return match.group(1)
        return None

    @classmethod
    def _check_gh_cli(cls) -> bool:
        """GitHub CLIが利用可能か確認"""
        # GitHub CLIの存在確認
        if subprocess.run(["which", "gh"], capture_output=True).returncode != 0:

            cls.reset_to_before_merge()
            return False

        # 認証状態の確認
        if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode != 0:


            cls.reset_to_before_merge()
            return False

        return True

    @classmethod
    def _is_merging(cls) -> bool:
        """マージ操作中かどうかを確認"""
        try:
            git_dir = cls._run_command(["git", "rev-parse", "--git-dir"])
            merge_head_file = Path(git_dir) / "MERGE_HEAD"
            return merge_head_file.exists()
        except subprocess.CalledProcessError:
            return False

    @classmethod
    def _check_pr_status(cls, branch_name: str) -> bool:
        """PRのステータスをチェック"""
        # GitHub CLIのチェック
        if not cls._check_gh_cli():
            return False


        try:
            # PRの検索
            pr_list = cls._run_command(["gh", "pr", "list", "--head", branch_name, "--json", "number"])
            prs = json.loads(pr_list)

            if not prs:
    
                return True

            pr_number = prs[0]["number"]

            is_fms_member = cls.is_fms_member(str(pr_number))
            if not is_fms_member:
                return True



            # ステータスチェックの取得
            status_json = cls._run_command(["gh", "pr", "view", str(pr_number), "--json", "statusCheckRollup"])
            status_data = json.loads(status_json).get("statusCheckRollup", None)

            if not status_data:
                return True

            latest_conclusion = max(status_data, key=lambda x: datetime.fromisoformat(x["completedAt"].replace("Z", ""))).get("conclusion", False)

            return latest_conclusion == "SUCCESS"

        except subprocess.CalledProcessError as e:

            return False

    @classmethod
    def reset_to_before_merge(cls):
        with open(cls.LOG_FILE, "w") as log_file:
                log_file.write("failed")

    @classmethod
    def is_fms_member(cls, pr_number: str):
        """PR作成者がFMs社員か判定"""
        results = cls._run_command(["gh", "pr", "view", pr_number, "--json", "commits"])        
        commits = json.loads(results)["commits"]

        commit_author_emails = []
        for commit in commits:
            for author in commit["authors"]:
                commit_author_emails.append(author["email"])

        return all([email for email in commit_author_emails if email.find("@fullmarks.co.jp")])
