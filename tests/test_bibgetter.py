import pytest
from bibgetter import main, is_arxiv_id, is_doi, is_mathscinet_id, guess_arxiv_id, guess_doi, guess_mathscinet_id

def test_help(capsys):
    """Test that help message is displayed correctly"""
    with pytest.raises(SystemExit):
        main(["-h"])
    output = capsys.readouterr().out
    assert "bibgetter" in output
    assert "Operation to perform" in output

def test_no_args(capsys):
    """Test behavior with no arguments"""
    main([])
    output = capsys.readouterr().out
    assert "No arguments provided to bibgetter" in output
    assert "Allowed operations:" in output
    assert "add" in output
    assert "sync" in output
    assert "pull" in output
    assert "get" in output

@pytest.mark.parametrize("id,expected", [
    ("2101.12345", True),
    ("2101.12345v1", True),
    ("arXiv:math/0309136", True),
    ("not-an-arxiv-id", False),
    ("", False),
])
def test_is_arxiv_id(id, expected):
    """Test arXiv ID validation"""
    assert is_arxiv_id(id) == expected

@pytest.mark.parametrize("id,expected", [
    ("10.1007/s00222-021-01074-w", True),
    ("10.4007/annals.2013.178.1.3", True),
    ("not-a-doi", False),
    ("", False),
])
def test_is_doi(id, expected):
    """Test DOI validation"""
    assert is_doi(id) == expected

@pytest.mark.parametrize("id,expected", [
    ("MR3874219", True),
    ("mr:MR3874219", True),
    ("not-a-mr-id", False),
    ("", False),
])
def test_is_mathscinet_id(id, expected):
    """Test MathSciNet ID validation"""
    assert is_mathscinet_id(id) == expected

@pytest.mark.parametrize("input,expected", [
    ("2502.20094", "2502.20094"),
    ("https://arxiv.org/abs/2502.20094", "2502.20094"),
    ("https://arxiv.org/html/2502.19988v1", "2502.19988v1"),
    ("https://arxiv.org/pdf/2502.20094", "2502.20094"),
    ("https://arxiv.org/pdf/2502.20094.pdf", "2502.20094"),
    ("not-an-arxiv-id", None),
])
def test_guess_arxiv_id(input, expected):
    """Test arXiv ID guessing from various formats"""
    assert guess_arxiv_id(input) == expected

@pytest.mark.parametrize("input,expected", [
    ("10.1007/s00222-021-01074-w", "10.1007/s00222-021-01074-w"),
    ("https://doi.org/10.1007/s00222-021-01074-w", "10.1007/s00222-021-01074-w"),
    ("https://dx.doi.org/10.1007/s00222-021-01074-w", "10.1007/s00222-021-01074-w"),
    ("not-a-doi", None),
])
def test_guess_doi(input, expected):
    """Test DOI guessing from various formats"""
    assert guess_doi(input) == expected

@pytest.mark.parametrize("input,expected", [
    ("MR3874219", "MR3874219"),
    ("https://mathscinet.ams.org/mathscinet/relay-station?mr=3874219", "MR3874219"),
    ("not-a-mr-id", None),
])
def test_guess_mathscinet_id(input, expected):
    """Test MathSciNet ID guessing from various formats"""
    assert guess_mathscinet_id(input) == expected 