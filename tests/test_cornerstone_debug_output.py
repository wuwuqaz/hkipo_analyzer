from ipo_analyzer.cornerstone import CornerstoneAnalyzer


def test_cornerstone_analyze_does_not_emit_debug_stdout(capsys):
    text = """
    The table below sets forth details of the cornerstone investors.
    AMR Action Fund, L.P. 10 20 30 40
    Orient Asset Management (Hong Kong) Limited 1 2 3 4
    June Star Global Limited 5 6 7 8
    Notes:
    """

    CornerstoneAnalyzer().analyze(text)
    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ""
