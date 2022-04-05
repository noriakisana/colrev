#! /usr/bin/env python
import logging
from pathlib import Path

import git


class Initializer:
    def __init__(
        self,
        project_name: str,
        SHARE_STAT_REQ: str,
        curated_metadata: bool = False,
        url: str = "NA",
        local_index_repo: bool = False,
    ) -> None:

        saved_args = locals()

        if project_name is not None:
            self.project_name = project_name
        else:
            self.project_name = str(Path.cwd().name)
        assert SHARE_STAT_REQ in ["NONE", "PROCESSED", "SCREENED", "COMPLETED"]
        self.SHARE_STAT_REQ = SHARE_STAT_REQ
        self.curated_metadata = curated_metadata
        self.url = url

        self.__require_empty_directory()
        self.__setup_files()
        self.__setup_git()
        self.__create_commit(saved_args)
        self.__register_repo()
        if local_index_repo:
            self.__create_local_index()

    def __register_repo(self) -> None:
        from colrev_core.environment import EnvironmentManager

        EnvironmentManager.register_repo(Path.cwd())
        return

    def __create_commit(self, saved_args: dict) -> None:
        from colrev_core.review_manager import ReviewManager

        self.REVIEW_MANAGER = ReviewManager()

        self.REVIEW_MANAGER.report_logger.info("Initialize review repository")
        self.REVIEW_MANAGER.report_logger.info(
            "Set project title:".ljust(30, " ") + f"{self.project_name}"
        )
        self.REVIEW_MANAGER.report_logger.info(
            "Set SHARE_STAT_REQ:".ljust(30, " ") + f"{self.SHARE_STAT_REQ}"
        )
        del saved_args["local_index_repo"]
        self.REVIEW_MANAGER.create_commit(
            "Initial commit", manual_author=True, saved_args=saved_args
        )
        return

    def __setup_files(self) -> None:
        import configparser
        from colrev_core.environment import EnvironmentManager

        Path("search").mkdir()

        files_to_retrieve = [
            [Path("template/readme.md"), Path("readme.md")],
            [Path("template/.pre-commit-config.yaml"), Path(".pre-commit-config.yaml")],
            [Path("template/.markdownlint.yaml"), Path(".markdownlint.yaml")],
            [Path("template/.gitattributes"), Path(".gitattributes")],
            [
                Path("template/docker-compose.yml"),
                Path.home() / Path("colrev/docker-compose.yml"),
            ],
        ]
        for rp, p in files_to_retrieve:
            self.__retrieve_package_file(rp, p)

        if self.curated_metadata:
            # replace readme
            self.__retrieve_package_file(
                Path("template/readme_curated_repo.md"), Path("readme.md")
            )
            self.__inplace_change(Path("readme.md"), "{{url}}", self.url)

        self.__inplace_change(
            Path("readme.md"), "{{project_title}}", self.project_name.rstrip(" ")
        )

        global_git_vars = EnvironmentManager.get_name_mail_from_global_git_config()

        if 2 != len(global_git_vars):
            logging.error("Global git variables (user name and email) not available.")
            return
        committer_name, committer_email = global_git_vars
        private_config = configparser.ConfigParser()
        private_config.add_section("general")
        private_config["general"]["EMAIL"] = committer_email
        private_config["general"]["GIT_ACTOR"] = committer_name
        private_config["general"]["CPUS"] = "4"
        private_config["general"]["DEBUG_MODE"] = "no"
        with open("private_config.ini", "w") as configfile:
            private_config.write(configfile)

        shared_config = configparser.ConfigParser()
        shared_config.add_section("general")
        shared_config["general"]["SHARE_STAT_REQ"] = self.SHARE_STAT_REQ
        with open("shared_config.ini", "w") as configfile:
            shared_config.write(configfile)

        # Note: need to write the .gitignore because file would otherwise be
        # ignored in the template directory.
        f = open(".gitignore", "w")
        f.write(
            "*.bib.sav\n"
            + "private_config.ini\n"
            + "missing_pdf_files.csv\n"
            + "manual_cleansing_statistics.csv\n"
            + "data.csv\n"
            + "venv\n"
            + ".references_learned_settings\n"
            + ".corrections\n"
            + ".ipynb_checkpoints/\n"
            + "pdfs"
        )
        f.close()
        return

    def __setup_git(self) -> None:
        from subprocess import check_call
        from subprocess import DEVNULL
        from subprocess import STDOUT

        from colrev_core.environment import EnvironmentManager

        git_repo = git.Repo.init()

        # To check if git actors are set
        EnvironmentManager.get_name_mail_from_global_git_config()

        logging.info("Install latest pre-commmit hooks")
        scripts_to_call = [
            ["pre-commit", "install"],
            ["pre-commit", "install", "--hook-type", "prepare-commit-msg"],
            ["pre-commit", "install", "--hook-type", "pre-push"],
            ["pre-commit", "autoupdate"],
            ["daff", "git", "csv"],
        ]
        for script_to_call in scripts_to_call:
            check_call(script_to_call, stdout=DEVNULL, stderr=STDOUT)
        git_repo.index.add(
            [
                "readme.md",
                ".pre-commit-config.yaml",
                ".gitattributes",
                ".gitignore",
                "shared_config.ini",
                ".markdownlint.yaml",
            ]
        )
        return

    def __require_empty_directory(self):

        cur_content = [str(x) for x in Path.cwd().glob("**/*")]

        if "venv" in cur_content:
            cur_content.remove("venv")
            # Note: we can use paths directly when initiating the project
        if "report.log" in cur_content:
            cur_content.remove("report.log")

        if 0 != len(cur_content):
            raise NonEmptyDirectoryError()

    def __inplace_change(
        self, filename: Path, old_string: str, new_string: str
    ) -> None:
        with open(filename) as f:
            s = f.read()
            if old_string not in s:
                logging.info(f'"{old_string}" not found in {filename}.')
                return
        with open(filename, "w") as f:
            s = s.replace(old_string, new_string)
            f.write(s)
        return

    def __retrieve_package_file(self, template_file: Path, target: Path) -> None:
        import pkgutil

        filedata = pkgutil.get_data(__name__, str(template_file))
        if filedata:
            with open(target, "w") as file:
                file.write(filedata.decode("utf-8"))
        return

    def __create_local_index(self) -> None:
        from colrev_core.environment import LocalIndex
        import os

        self.REVIEW_MANAGER.report_logger.handlers = []

        local_index_path = LocalIndex.local_environment_path / Path("local_index")
        curdir = Path.cwd()
        if not local_index_path.is_dir():
            local_index_path.mkdir(parents=True, exist_ok=True)
            os.chdir(local_index_path)
            Initializer("local_index", "PROCESSED", True)
            print("Created local_index repository")

        os.chdir(curdir)
        return


class NonEmptyDirectoryError(Exception):
    def __init__(self):
        self.message = "please change to an empty directory to initialize a project"
        super().__init__(self.message)


if __name__ == "__main__":
    pass
