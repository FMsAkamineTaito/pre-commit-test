import sys


class PRStatusChecker:

    @classmethod
    def pr_status_check(cls):
        print("#####")

        print("pr status checkerを実行します。")

        sys.exit(1)


if __name__ == "__main__":
    print("maim")

    PRStatusChecker.pr_status_check()