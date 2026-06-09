import os
import sys
import pytest
from unittest.mock import MagicMock, patch, mock_open
import yaml

# Add services/gateway to path so we can import sync_registry
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import sync_registry

@pytest.fixture
def mock_redis_client():
    client = MagicMock()
    # Mock exists to return True for nodes
    client.exists.return_value = True
    return client

def test_sync_cycle_no_changes(mock_redis_client):
    # Setup mock redis set data
    mock_redis_client.smembers.return_value = {"172.20.0.5:8000"}
    
    # Mock yml config content
    mock_yaml_data = """
upstreams:
  - name: ai-core-upstream
    targets:
      - target: 172.20.0.5:8000
        weight: 100
"""
    
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=mock_yaml_data)) as mock_file, \
         patch("requests.post") as mock_post:
         
        sync_registry.sync_cycle(mock_redis_client, "registry:service:ai-core")
        
        # Verify no write occurred because targets matched
        mock_file().write.assert_not_called()
        mock_post.assert_not_called()

def test_sync_cycle_add_target(mock_redis_client):
    # Setup mock redis: one target already there, one new target
    mock_redis_client.smembers.return_value = {"172.20.0.5:8000", "172.20.0.6:8000"}
    
    # Mock yml config content (only has 172.20.0.5)
    mock_yaml_data = """
upstreams:
  - name: ai-core-upstream
    targets:
      - target: 172.20.0.5:8000
        weight: 100
"""
    
    # Mock response from Kong Admin API
    mock_response = MagicMock()
    mock_response.status_code = 200
    
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=mock_yaml_data)) as mock_file, \
         patch("requests.post", return_value=mock_response) as mock_post:
         
        sync_registry.sync_cycle(mock_redis_client, "registry:service:ai-core")
        
        # Open was called at least once for writing
        # Let's verify YAML write contains both targets
        written_data = "".join([call[0][0] for call in mock_file().write.call_args_list])
        parsed_written = yaml.safe_load(written_data)
        targets = [t["target"] for t in parsed_written["upstreams"][0]["targets"]]
        assert "172.20.0.5:8000" in targets
        assert "172.20.0.6:8000" in targets
        
        # Verify Kong configuration reload POST was called
        mock_post.assert_called_once()

def test_sync_cycle_expired_node_cleanup(mock_redis_client):
    # Setup mock redis: 2 members in set, but one lacks TTL key (exists=False)
    mock_redis_client.smembers.return_value = {"172.20.0.5:8000", "172.20.0.6:8000"}
    
    # 172.20.0.6:8000 is expired
    def exists_side_effect(key):
        if "172.20.0.6:8000" in key:
            return False
        return True
    mock_redis_client.exists.side_effect = exists_side_effect
    
    # Mock yml config matches only the alive one (172.20.0.5)
    mock_yaml_data = """
upstreams:
  - name: ai-core-upstream
    targets:
      - target: 172.20.0.5:8000
        weight: 100
"""
    
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=mock_yaml_data)) as mock_file, \
         patch("requests.post") as mock_post:
         
        sync_registry.sync_cycle(mock_redis_client, "registry:service:ai-core")
        
        # Verify srem was called for the expired node
        mock_redis_client.srem.assert_called_once_with("registry:service:ai-core", "172.20.0.6:8000")
        
        # Since active target list matches YAML targets (172.20.0.5), no config reload should happen
        mock_file().write.assert_not_called()
        mock_post.assert_not_called()
