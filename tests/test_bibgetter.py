import pytest
from bibgetter import main, is_arxiv_id, is_doi, is_mathscinet_id, guess_arxiv_id, guess_doi, guess_mathscinet_id
import os
import time
import tempfile
import bibtexparser

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
    assert "No" in output
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

@pytest.fixture
def temp_bibgetter_dir():
    """Create a temporary directory for bibgetter files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir

def test_get_dois(temp_bibgetter_dir, capsys):
    """Test getting DOI entries and saving to central bibliography"""
    # Run get command with two DOIs and custom directory
    main(['get', 'https://doi.org/10.4171/owr/2024/44', '10.1307/mmj/20216092', 
         '--data-directory', temp_bibgetter_dir])
    
    output = capsys.readouterr().out
    # Check central bibliography exists and contains entries
    central_bib = os.path.join(temp_bibgetter_dir, 'bibliography.bib')
    assert os.path.exists(central_bib)
    
    # Parse bibliography and check entries
    bib_database = bibtexparser.parse_file(central_bib)
    assert len(bib_database.entries) == 2
    
    # Verify DOIs are in the entries
    dois = [entry.key for entry in bib_database.entries]
    assert '10.4171/owr/2024/44' in dois
    assert '10.1307/mmj/20216092' in dois

def test_get_dois_with_parentheses(temp_bibgetter_dir, capsys):
    """Test that DOIs with parentheses in them are handled correctly."""
    main(['get', 'https://doi.org/10.1016/S0022-4049(97)00152-7',
         '--data-directory', temp_bibgetter_dir])
    output = capsys.readouterr().out
    # Previously the parentheses were included in the identifier, which caused
    # biber formatting command to stop. We check that this didn't happen by checking
    # that the bibliography record is properly formatted, in particular laid out over
    # several lines.
    lines = output.splitlines()
    # Find the line containing "Keller"
    keller_line = None
    for i, line in enumerate(lines):
        if "Keller" in line:
            keller_line = i
            break
    # Find the line containing "volume"
    volume_line = None
    for i, line in enumerate(lines):
        if "volume" in line:
            volume_line = i
            break
    assert keller_line is not None
    assert volume_line is not None
    assert keller_line != volume_line

def test_get_is_cached(temp_bibgetter_dir, capsys):
    """Test that second get request is faster due to caching"""
    # Run get command first time and measure duration
    start = time.time()
    main(['get', 'https://doi.org/10.4171/owr/2024/44', '10.1307/mmj/20216092', 
         '--data-directory', temp_bibgetter_dir])
    first_duration = time.time() - start
    
    # Run same command again and measure duration
    start = time.time()
    main(['get', 'https://doi.org/10.4171/owr/2024/44', '10.1307/mmj/20216092',
         '--data-directory', temp_bibgetter_dir])
    second_duration = time.time() - start
    
    # Second run should be significantly faster since entries are cached
    assert second_duration < first_duration / 2
    
def test_add_various_ids(temp_bibgetter_dir, capsys):
    """Test adding various IDs to central bibliography"""
    # Run add command with multiple IDs and custom directory
    main(['add', 'https://doi.org/10.4171/owr/2024/44', '10.1307/mmj/20216092',
         'https://arxiv.org/abs/2502.20094', 'https://mathscinet.ams.org/mathscinet/relay-station?mr=4865600',
         '--data-directory', temp_bibgetter_dir])
    output = capsys.readouterr().out
    assert 'Error' not in output
    
    # Check central bibliography exists and contains entries
    central_bib = os.path.join(temp_bibgetter_dir, 'bibliography.bib')
    assert os.path.exists(central_bib)
    
    # Parse bibliography and check number of entries
    bib_database = bibtexparser.parse_file(central_bib)
    assert len(bib_database.entries) == 4

def test_alias(temp_bibgetter_dir, capsys):
    """Test creating and using bibliography key aliases"""
    # First add some entries to work with
    # TODO: avoid network calls here, just provide a pre-made central bibliography file
    main(['add', 'https://doi.org/10.4171/owr/2024/44', '10.1307/mmj/20216092',
         '--data-directory', temp_bibgetter_dir])
    
    # Create aliases
    main(['alias', 'owrpaper', '10.4171/owr/2024/44',
          '--data-directory', temp_bibgetter_dir])
    main(['alias', 'mmjpaper', '10.1307/mmj/20216092',
          '--data-directory', temp_bibgetter_dir])
    
    # Check aliases are listed correctly
    main(['alias', '--data-directory', temp_bibgetter_dir])
    output = capsys.readouterr().out
    assert 'owrpaper → 10.4171/owr/2024/44' in output
    assert 'mmjpaper → 10.1307/mmj/20216092' in output
    
    # Test getting entries using aliases
    main(['get', 'owrpaper', 'mmjpaper',
          '--data-directory', temp_bibgetter_dir])
    output = capsys.readouterr().out
    assert '@article{owrpaper,' in output
    assert '@article{mmjpaper,' in output

def test_alias_with_guess(temp_bibgetter_dir, capsys):
    """Test that adding an alias to a non-existent bibliography record creates it"""
    main(['alias', 'okawa-irr', 'https://arxiv.org/abs/2304.14048',
          '--data-directory', temp_bibgetter_dir])
    output = capsys.readouterr().out
    assert 'Added alias' in output
    assert '@online{okawa-irr' in output

