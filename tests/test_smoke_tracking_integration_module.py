from src.cli.tracking_integration import TrackingIntegration, create_tracking_integrated_check_exists


def test_import_tracking_integration():
    assert TrackingIntegration is not None
    assert create_tracking_integrated_check_exists is not None
