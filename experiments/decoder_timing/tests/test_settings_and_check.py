"""Settings and the anchor table as the modules see them, and the comparison of the syndrome index."""
from qecdec import parameters as P
from qecdec.__main__ import setting
from qecdec.check import compare_index
from qecdec.grid import all_jobs


def test_settings_keep_their_types():
    assert P.ERROR_RATES == [1e-3, 3e-3, 5e-3] and P.BB_INSTANCE == {6: "bb_72_12_6", 12: "bb_144_12_12"}
    assert P.NATIVE_DECODERS == {"pymatching", "fusionblossom", "chromobius"}
    assert isinstance(P.SKIP_BPOSD_ABOVE_NS, float) and P.MAX_SECONDS_PER_REP_BB == 12 * 3600
    assert sum(1 for _ in all_jobs()) == 135


def test_anchor_and_checks():
    assert P.ANCHOR == dict(decoder="pymatching", code="surface", d=17, p=1e-3) and P.ANCHOR_PER_ROUND_NS == 1000.0
    assert P.STABILITY_POINTS == [("pymatching", "surface", 5, 1e-3), ("pymatching", "surface", 17, 1e-3)]
    assert P.SEED_CHECK_POINT == ("pymatching", "surface", 13, 3e-3) and P.SEED_CHECK_OFFSET == 7919


def test_setting_command():
    assert setting("campaign.core") == "96" and setting("campaign.set_cpufreq") == "true"
    assert setting("paths.output") == str(P.OUTPUT)


def test_compare_index(tmp_path):
    recorded, new = tmp_path / "rec.csv", tmp_path / "new.csv"
    recorded.write_text("code,d\nsurface,3\nsurface,5\n")
    assert compare_index(new, recorded) == (None, "not built (make syndromes)")
    new.write_text("code,d\nsurface,3\n")
    assert compare_index(new, recorded) == (True, "1 of 2 grid points, all as recorded")
    new.write_text("code,d\nsurface,7\n")
    assert compare_index(new, recorded) == (False, "1 of 1 rows not in the record")
