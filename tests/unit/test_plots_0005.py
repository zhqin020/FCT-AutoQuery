import pytest

pd = pytest.importorskip("pandas")

from fct_analysis.parser import parse_cases
from fct_analysis import plots
from pathlib import Path


def test_plots_create_pngs(tmp_path: Path):
    fixture = Path("tests/fixtures/0005_cases.json")
    df = parse_cases(str(fixture))

    out = tmp_path / "plots"
    out.mkdir()

    # Ensure functions run without raising when data present or absent
    plots.volume_trend(df, out / "volume.png")
    plots.duration_boxplot(df, out / "box.png")
    plots.outcome_donut(df, out / "donut.png")
    plots.visa_office_heatmap(df, out / "heatmap.png")

    assert (out / "volume.png").exists()
    assert (out / "box.png").exists()
    assert (out / "donut.png").exists()
    assert (out / "heatmap.png").exists()
