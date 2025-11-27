def test_config_export_write_retries_default():
    from src.lib.config import Config

    # Should reflect the code-level default (2)
    assert Config.get_export_write_retries() == 2
