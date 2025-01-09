import subprocess
import sys


def main():
    # シェルスクリプトのパス
    script_path = './scripts/pr_status_checker.sh'

    # シェルスクリプトを実行
    subprocess.run(['bash', script_path] + sys.argv[1:], check=True)


if __name__ == '__main__':
    main()
