import io

import pytest

from search import Shell, main


@pytest.fixture
def saved_index(index, tmp_path):
    path = tmp_path / "index.json"
    index.save(path)
    return path


def make_shell(path):
    out = io.StringIO()
    return Shell(path, out=out), out


def test_shell_survives_bad_input_without_an_index(tmp_path):
    shell, out = make_shell(tmp_path / "missing.json")
    for line in ["", "   ", "find love", "print love", "stats", "frobnicate", "print", "build abc"]:
        assert shell.handle(line) is True
    text = out.getvalue()
    assert "No index loaded" in text
    assert "Unknown command 'frobnicate'" in text
    assert "Usage: build" in text


def test_exit_and_quit(tmp_path):
    shell, _ = make_shell(tmp_path / "x.json")
    assert shell.handle("exit") is False
    assert shell.handle("QUIT") is False


def test_load_find_print(saved_index):
    shell, out = make_shell(saved_index)
    shell.handle("load")
    shell.handle("find")
    shell.handle('find einstein xyzzy')
    shell.handle("print the")
    shell.handle("print Einstein")
    shell.handle("print xyzzy")
    text = out.getvalue()
    assert "loaded successfully" in text
    assert "Usage: find <query>" in text
    assert "Not in the index: xyzzy" in text
    assert "Results for word(s): einstein" in text
    assert "*Einstein*" in text
    assert "'the' is a stopword" in text
    assert "'einstein' appears on 2 page(s)" in text
    assert "'xyzzy' is not in the inverted index!" in text


def test_load_reports_bad_files(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    shell, out = make_shell(bad)
    assert shell.load() is False
    assert "Could not load" in out.getvalue()


def test_one_shot_commands(saved_index, capsys):
    assert main(["--index", str(saved_index), "find", "love", "life"]) == 0
    assert "Results for word(s): love, life" in capsys.readouterr().out
    assert main(["--index", str(saved_index), "stats"]) == 0
    assert "Pages: 5" in capsys.readouterr().out
    assert main(["--index", str(saved_index.with_name("nope.json")), "find", "x"]) == 1


def test_stopword_query_message(saved_index, capsys):
    main(["--index", str(saved_index), "find", "the"])
    assert "only contains stopwords" in capsys.readouterr().out
