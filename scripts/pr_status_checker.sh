#!/bin/bash

# キャッシュディレクトリとファイルの設定
CACHE_DIR="/tmp/gh_pr_check_cache"
mkdir -p "$CACHE_DIR"

# 現在のリポジトリの一意性情報を取得
REPO_ID=$(git rev-parse --show-toplevel | md5sum | cut -d' ' -f1)

# マージ元のブランチ名を取得する関数
get_source_branch() {
    local merge_msg="$1"
    local branch_name=""

    if [[ "$merge_msg" =~ Merge[[:space:]]branch[[:space:]]\'([^\']+)\' ]]; then
        branch_name="${BASH_REMATCH[1]}"
        echo "$branch_name"
        return 0
    fi

    return 1
}

# PRのステータスをチェックする関数
check_pr_status() {
    local branch_name="$1"
    local cache_file="$CACHE_DIR/${REPO_ID}_${branch_name}.cache"

    # キャッシュが存在する場合は再利用
    if [ -f "$cache_file" ]; then
        echo "キャッシュ: ブランチ '$branch_name' の結果を再利用しています"
        cached_result=$(cat "$cache_file")
        return "$cached_result"
    fi

    # GitHub CLIがインストールされているか確認
    if ! command -v gh &> /dev/null; then
        echo "エラー: GitHub CLI (gh) がインストールされていません"
        return 1
    fi

    # 認証状態を確認
    if ! gh auth status &> /dev/null; then
        echo "エラー: GitHub CLIが認証されていません"
        echo "gh auth login を実行してログインしてください"
        return 1
    fi

    echo "ブランチ '$branch_name' のPRをチェックしています..."

    # PRの検索
    pr_number=$(gh pr list --head "$branch_name" --json number --jq '.[0].number')

    if [ -z "$pr_number" ]; then
        echo "警告: ブランチ $branch_name のPRが見つかりません"
        echo "0" > "$cache_file"  # キャッシュに成功を記録
        return 0
    fi

    echo "PR #$pr_number のステータスチェックを確認しています..."

    # ステータスチェックの状態を取得
    failed_checks=$(gh pr view "$pr_number" --json statusCheckRollup --jq '.statusCheckRollup[] | select(.state == "FAILURE")')

    if [ ! -z "$failed_checks" ]; then
        echo "エラー: PR #$pr_number のステータスチェックが失敗しています"
        echo "失敗したチェック:"
        gh pr view "$pr_number" --json statusCheckRollup --jq '.statusCheckRollup[] | select(.state == "FAILURE") | "- " + .context + ": " + .description'

        echo "1" > "$cache_file"  # キャッシュに失敗を記録
        return 1
    fi

    echo "すべてのステータスチェックがパスしています"
    echo "0" > "$cache_file"  # キャッシュに成功を記録
    return 0
}

# メイン処理
main() {
    MERGE_MSG_PATH="$GIT_DIR/MERGE_MSG"

    echo "pr_status_checkerを起動します。"

    if [ ! -f "$MERGE_MSG_PATH" ]; then
        exit 0
    fi

    MERGE_MSG=$(cat "$MERGE_MSG_PATH")

    if [[ "$MERGE_MSG" =~ Merge[[:space:]]branch[[:space:]]\'(hotfix/|release/|feature/) ]]; then
        source_branch=$(get_source_branch "$MERGE_MSG")

        if [ $? -eq 0 ]; then
            echo "Git Flow マージ操作を検出しました"
            echo "マージ元ブランチ: $source_branch"

            if ! check_pr_status "$source_branch"; then
                echo "Git Flow操作を中断します"
                exit 1
            fi
        fi
    fi

    exit 0
}

# スクリプトのエントリーポイント
GIT_DIR=$(git rev-parse --git-dir)
main