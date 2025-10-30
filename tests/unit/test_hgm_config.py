# tests/unit/test_hgm_config.py
import pytest
import tempfile
import json
import os
from python.helpers.hgm_config import HGMConfig, get_default_config, load_config_from_env


def test_default_config_creation():
    """Test creating default configuration"""
    config = HGMConfig.create_default()

    assert config.max_task_evals == 1000
    assert config.max_workers == 4
    assert config.alpha == 0.5
    assert config.beta == 1.0
    assert config.cool_down == 5


def test_config_validation_positive():
    """Test that valid configuration passes validation"""
    config = HGMConfig(
        max_task_evals=100,
        max_workers=2,
        alpha=0.5,
        beta=1.0
    )
    # Should not raise
    config.validate()


def test_config_validation_invalid_max_evals():
    """Test that invalid max_task_evals raises error"""
    with pytest.raises(ValueError, match="max_task_evals must be positive"):
        HGMConfig(max_task_evals=-1)


def test_config_validation_invalid_alpha():
    """Test that invalid alpha raises error"""
    with pytest.raises(ValueError, match="alpha must be between 0 and 2"):
        HGMConfig(alpha=3.0)


def test_config_validation_invalid_strategy_weights():
    """Test that strategy weights must sum to 1.0"""
    with pytest.raises(ValueError, match="strategy_weights must sum to 1.0"):
        HGMConfig(strategy_weights={
            'solve_empty_patches': 0.5,
            'solve_stochasticity': 0.3
            # Only sums to 0.8
        })


def test_config_to_dict():
    """Test converting configuration to dictionary"""
    config = HGMConfig.create_default()
    config_dict = config.to_dict()

    assert isinstance(config_dict, dict)
    assert config_dict['max_task_evals'] == 1000
    assert config_dict['alpha'] == 0.5
    assert 'strategy_weights' in config_dict


def test_config_from_dict():
    """Test creating configuration from dictionary"""
    data = {
        'max_task_evals': 500,
        'max_workers': 2,
        'alpha': 0.7,
        'beta': 1.5
    }

    config = HGMConfig.from_dict(data)

    assert config.max_task_evals == 500
    assert config.max_workers == 2
    assert config.alpha == 0.7
    assert config.beta == 1.5


def test_config_save_and_load():
    """Test saving and loading configuration from file"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        filepath = f.name

    try:
        # Create and save config
        config = HGMConfig(
            max_task_evals=250,
            alpha=0.6,
            max_workers=3
        )
        config.save(filepath)

        # Load config
        loaded_config = HGMConfig.load(filepath)

        assert loaded_config.max_task_evals == 250
        assert loaded_config.alpha == 0.6
        assert loaded_config.max_workers == 3

    finally:
        os.unlink(filepath)


def test_config_update():
    """Test updating configuration"""
    config = HGMConfig.create_default()
    updated = config.update(max_task_evals=500, alpha=0.7)

    # Original unchanged
    assert config.max_task_evals == 1000
    assert config.alpha == 0.5

    # Updated has new values
    assert updated.max_task_evals == 500
    assert updated.alpha == 0.7


def test_config_fast_preset():
    """Test fast configuration preset"""
    config = HGMConfig.create_fast()

    assert config.max_task_evals == 100
    assert config.max_workers == 1
    assert config.alpha == 0.3
    assert config.timeout_seconds == 120


def test_config_thorough_preset():
    """Test thorough configuration preset"""
    config = HGMConfig.create_thorough()

    assert config.max_task_evals == 5000
    assert config.max_workers == 8
    assert config.alpha == 0.7
    assert config.enable_pruning is True


def test_get_default_config():
    """Test get_default_config helper"""
    config = get_default_config()

    assert isinstance(config, HGMConfig)
    assert config.max_task_evals == 1000


def test_config_from_dict_filters_unknown_fields():
    """Test that unknown fields are filtered out"""
    data = {
        'max_task_evals': 500,
        'unknown_field': 'should_be_ignored',
        'another_unknown': 123
    }

    config = HGMConfig.from_dict(data)

    # Should not have unknown fields
    assert config.max_task_evals == 500
    assert not hasattr(config, 'unknown_field')
    assert not hasattr(config, 'another_unknown')


def test_load_config_from_env(monkeypatch):
    """Test loading configuration from environment variables"""
    # Set environment variables
    monkeypatch.setenv('HGM_MAX_TASK_EVALS', '777')
    monkeypatch.setenv('HGM_MAX_WORKERS', '5')
    monkeypatch.setenv('HGM_ALPHA', '0.8')
    monkeypatch.setenv('HGM_LOG_LEVEL', 'DEBUG')

    config = load_config_from_env()

    assert config.max_task_evals == 777
    assert config.max_workers == 5
    assert config.alpha == 0.8
    assert config.log_level == 'DEBUG'


def test_load_config_from_env_invalid_value(monkeypatch, capsys):
    """Test that invalid environment variable values are handled"""
    monkeypatch.setenv('HGM_MAX_TASK_EVALS', 'not_a_number')

    config = load_config_from_env()

    # Should use default value
    assert config.max_task_evals == 1000

    # Should print warning
    captured = capsys.readouterr()
    assert 'Warning' in captured.out or 'Warning' in captured.err


def test_config_str_representation():
    """Test string representation of configuration"""
    config = HGMConfig.create_default()
    config_str = str(config)

    assert 'HGMConfig' in config_str
    assert 'max_evals=1000' in config_str
    assert 'alpha=0.5' in config_str


def test_config_validation_empty_patch_threshold():
    """Test empty patch threshold validation"""
    with pytest.raises(ValueError, match="empty_patch_threshold must be between 0 and 1"):
        HGMConfig(empty_patch_threshold=1.5)


def test_config_validation_timeout():
    """Test timeout validation"""
    with pytest.raises(ValueError, match="timeout_seconds must be positive"):
        HGMConfig(timeout_seconds=0)


def test_config_immutability():
    """Test that update creates new instance"""
    config1 = HGMConfig.create_default()
    config2 = config1.update(max_task_evals=500)

    # Different objects
    assert config1 is not config2

    # Original unchanged
    assert config1.max_task_evals == 1000

    # New has updated value
    assert config2.max_task_evals == 500
