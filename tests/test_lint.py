"""Preflight lint: hard limits kill the command, style findings only warn."""
from __future__ import annotations

import pytest

from gads import lint


def test_rsa_counts_are_hard_limits(capsys):
    with pytest.raises(SystemExit):
        lint.lint_rsa(["a", "b"], ["x", "y"])
    assert "3–15 headlines" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        lint.lint_rsa(["a", "b", "c"], ["x"])
    assert "2–4 descriptions" in capsys.readouterr().err


def test_rsa_lengths_are_hard_limits(capsys):
    with pytest.raises(SystemExit):
        lint.lint_rsa(["x" * 31, "b", "c"], ["x", "y"])
    assert "max 30" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        lint.lint_rsa(["a", "b", "c"], ["y" * 91, "y"])
    assert "max 90" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        lint.lint_rsa(["a", "b", "c"], ["x", "y"], path1="p" * 16)
    assert "path1" in capsys.readouterr().err


def test_rsa_style_findings_only_warn(capsys):
    lint.lint_rsa(["Kurz AI!", "SUPER NABÍDKA", "Kurz AI!"], ["Popis!! Hned", "Druhý popis"])
    err = capsys.readouterr().err
    assert "LINT" in err
    assert "vykřičník v headline" in err
    assert "CAPS" in err and "SUPER" in err
    assert "duplicitní headline" in err
    assert "opakovaná interpunkce" in err


def test_caps_whitelist_for_abbreviations(capsys):
    lint.lint_rsa(["Kurz AI a SEO", "Vibe coding", "Začni dnes"], ["Popis jedna", "Popis dva"])
    assert capsys.readouterr().err == ""  # AI/SEO are not shouting


def test_generic_text_lint(capsys):
    with pytest.raises(SystemExit):
        lint.lint_texts(["a" * 26], max_len=25, label="callout")
    assert "max 25" in capsys.readouterr().err
    lint.lint_texts(["Emoji 🚀"], max_len=25, label="callout")
    assert "emoji" in capsys.readouterr().err
