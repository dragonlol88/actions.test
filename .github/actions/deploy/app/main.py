import os
import re
import logging
import typing as t
from github import Github
from pydantic import BaseModel, BaseSettings, SecretStr

REGISTER_TMPL = ".github/ISSUE_TEMPLATE/register.md"
UPDATE_TMPL   = ".github/ISSUE_TEMPLATE/update.md"
DELETE_TMPL   = ".github/ISSUE_TEMPLATE/delete.md"

TEMPLETE_REGEX_PATTERN = {
    "created":{
        "title..package_name"   : rb'title: "(.*:)',
        "labels.."               : rb'labels: (.*)',
        "body.header."                 : rb'(## \xf0\x9f\x9f\xa2 .*\n|\xf0\x9f\x94\xb5 .*\n| \xf0\x9f\x94\xb4 .* )',
        "body..package_name"   : rb'(- \*\*Package name :\*\* )',
        "body.release.tag_name": rb'(- \*\*Version :\*\* )',
        "body.release.author"  : rb'(- \*\*Author :\*\* )',
        "body.release.name"    : rb'(- \*\*Short description :\*\* )',
        "body.release.body"    : rb'(- \*\*Long description :\*\* )',
        "body..homepage"       : rb'(- \*\*Homepage :\*\* )',
        "body..link"           : rb'(- \*\*Link :\*\* )',
    },
    "updated": {
        "title..package_name"   : rb'title: "(.*:)',
        "labels.."               : rb'labels: (.*)',
        "body.header."                 : rb'(## \xf0\x9f\x9f\xa2 .*\n|## \xf0\x9f\x94\xb5 .*\n|## \xf0\x9f\x94\xb4 .*\n)',
        "body..package_name"   : rb'(- \*\*Package name :\*\* )',
        "body.release.tag_name": rb'(- \*\*New version :\*\* )',
        "body..link"           : rb'(- \*\*Link for the new version :\*\* )',
    },
    "deleted": {
        "title..package_name"   : rb'title: "(.*:)',
        "labels.."               : rb'labels: (.*)',
        "body.header."                 : rb'(## \xf0\x9f\x9f\xa2 .*\n|## \xf0\x9f\x94\xb5 .*\n|## \xf0\x9f\x94\xb4 .*\n)',
        "body..package_name"   : rb'(- \*\*Package name :\*\* )',

    }
}


class Release(BaseModel):
    id: int
    name: str
    tag_name: t.Optional[str] = None
    author: t.Dict[str, str]
    body: str
    created_at: str
    draft: bool


class EventModel(BaseModel):
    action: str
    changes: t.Optional[t.Dict[str, t.Any]] = None
    release: Release


class GithubContext(BaseModel):

    event: EventModel
    repository: str


class Settings(BaseSettings):
    input_token: SecretStr
    input_pypi_repo   : t.Optional[str] = "42maru-ai/pypi"
    input_package_name: t.Optional[str] = None
    github_context    : GithubContext
    github_server_url : str


def _check_if_exist(contents, package):

    return any([content.name == package for content in contents])


def _make_homepage(server, repo):
    return os.path.join(server, repo)


def _make_link(homepage, tag):
    return f"git+{homepage}@{tag}"


def _get_version(tag: str):
    if tag.startswith("v"):
        return tag.lstrip("v")
    return


class Parser:

    def __init__(self, contents: bytes, release, package_name, homepage, link, action):

        self.action = action
        self.contents = contents
        self.release = release
        self.package_name = package_name
        self.homepage = homepage
        self.link = link

        self.title = None
        self.labels = []
        self.body = ""

    def parse(self):
        items = self.__dict__.copy()

        for action, regex_pattern in TEMPLETE_REGEX_PATTERN.items():
            if action != self.action:
                continue
            for key, regex in regex_pattern.items():
                iss_att, att1, att2 = key.split(".")
                try:
                    sub_obj = items[att1]
                except KeyError:
                    try:
                        value = items[att2]
                    except KeyError:
                        pass

                else:
                    value = getattr(sub_obj, att2)
                subject: bytes = re.search(regex, self.contents).group(1)

                if iss_att == "title":
                    self.title = subject.decode("utf-8") + value
                elif iss_att == "labels":
                    self.labels.append(subject.decode("utf-8"))
                elif iss_att == "body":
                    if att1 == "header":
                        self.body += subject.decode("utf-8") + "\n"
                    elif att2 == "tag_name":
                        version = _get_version(value)
                        self.body += subject.decode("utf-8") + version + "\n"
                    elif att2 == "author":
                        author = value["login"]
                        self.body += subject.decode("utf-8") + author + "\n"
                    elif att2 == "body":
                        long_desc = f"\n```html\n{value}\n```"
                        self.body += subject.decode("utf-8") + long_desc + "\n"
                    else:
                        self.body += subject.decode("utf-8") + value + "\n"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    _token = settings.input_token.get_secret_value()
    _pypi_repo_name = settings.input_pypi_repo
    _github_ctx = settings.github_context
    server_url = settings.github_server_url

    github = Github(_token)

    if settings.input_package_name is None:
        package_name = _github_ctx.repository.split("/")[-1]
    else:
        package_name = settings.input_package_name

    action = _github_ctx.event.action
    pypi_repo = github.get_repo(_pypi_repo_name)
    contents = pypi_repo.get_contents("./")
    release = _github_ctx.event.release

    homepage = _make_homepage(server_url, _github_ctx.repository)
    link = _make_link(homepage, release.tag_name)

    if action == "created":
        if _check_if_exist(contents, package_name):
            content = pypi_repo.get_contents(UPDATE_TMPL).decoded_content
            action = "updated"
        else:
            content = pypi_repo.get_contents(REGISTER_TMPL).decoded_content
    elif action == "deleted":
        content = pypi_repo.get_contents(DELETE_TMPL).decoded_content
    logging.info(f"package {action} from {_github_ctx.repository}")
    parser = Parser(
        contents=content, release=release, package_name=package_name,
        homepage=homepage, link=link, action=action
    )
    parser.parse()
    pypi_repo.create_issue(
        title=parser.title, labels=parser.labels, body=parser.body
    )
