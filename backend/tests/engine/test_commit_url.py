from app.services.git_service import commit_web_url


def test_public_commit_links_strip_credentials_and_reject_local_urls():
    sha = "a" * 40
    assert (
        commit_web_url("git@github.com:owner/repo.git", sha) == f"https://github.com/owner/repo/commit/{sha}"
    )
    assert commit_web_url("https://user:secret@gitlab.com/group/sub/repo.git", sha) == (
        f"https://gitlab.com/group/sub/repo/-/commit/{sha}"
    )
    assert commit_web_url(r"D:\remote.git", sha) is None
    assert commit_web_url("https://github.com/owner/repo?token=secret", sha) is None
    assert commit_web_url("https://evil.example/owner/repo", sha) is None
