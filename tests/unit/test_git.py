from __future__ import annotations

from server.utils.git import normalize_git_remote_url


class TestNormalizeGitRemoteUrl:
    def test_ssh_format(self):
        result = normalize_git_remote_url("git@github.com:owner/repo.git")
        assert result == "github.com/owner/repo"

    def test_https_format(self):
        result = normalize_git_remote_url("https://github.com/owner/repo.git")
        assert result == "github.com/owner/repo"

    def test_http_format(self):
        result = normalize_git_remote_url("http://github.com/owner/repo")
        assert result == "github.com/owner/repo"

    def test_ssh_long_url(self):
        result = normalize_git_remote_url("ssh://git@github.com/owner/repo")
        assert result == "github.com/owner/repo"

    def test_empty_string(self):
        result = normalize_git_remote_url("")
        assert result is None

    def test_whitespace_only(self):
        result = normalize_git_remote_url("   ")
        assert result is None

    def test_localhost_legacy(self):
        result = normalize_git_remote_url("http://local_proxy@127.0.0.1:16583/git/owner/repo")
        assert result == "github.com/owner/repo"

    def test_localhost_ghe(self):
        result = normalize_git_remote_url("http://token@127.0.0.1:16583/git/ghe.example.com/owner/repo")
        assert result == "ghe.example.com/owner/repo"


class TestGitUtils:
    def test_normalize_preserves_lowercase(self):
        """Normalized URLs should be lowercase"""
        result = normalize_git_remote_url("git@GitHub.com:Owner/Repo.git")
        assert result == "github.com/owner/repo"
