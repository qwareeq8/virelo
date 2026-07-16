"""Tests for the Explorer default-view plan builders (pure logic, no registry)."""

from datetime import datetime

from virelo.services.explorer_views import (
    BAGMRU_KEY,
    BAGS_KEY,
    FOLDER_TYPES_KEY,
    ICON_SIZE_DETAILS,
    LOGICAL_VIEW_MODE_DETAILS,
    MODE_DETAILS,
    STREAMS_DEFAULTS_KEY,
    THIS_PC_GUID,
    VIEW_CACHE_KEYS,
    backup_dir_name,
    this_pc_bag_values,
    top_view_values,
)


def test_details_constants_match_winsetview():
    """Details view is LogicalViewMode=1, Mode=4, IconSize=16 (WinSetView index 1)."""
    assert LOGICAL_VIEW_MODE_DETAILS == 1
    assert MODE_DETAILS == 4
    assert ICON_SIZE_DETAILS == 16


def test_view_cache_keys_cover_both_hive_locations():
    """The cache wipe must clear Bags/BagMRU in both registry locations plus Streams."""
    assert BAGS_KEY in VIEW_CACHE_KEYS
    assert BAGMRU_KEY in VIEW_CACHE_KEYS
    assert STREAMS_DEFAULTS_KEY in VIEW_CACHE_KEYS
    assert FOLDER_TYPES_KEY in VIEW_CACHE_KEYS
    legacy = [k for k in VIEW_CACHE_KEYS if k.startswith("Software\\Microsoft\\Windows\\Shell")]
    assert len(legacy) == 2


def test_top_view_values_force_details():
    """Each TopViews entry gets LogicalViewMode=Details and the Details icon size."""
    values = top_view_values(r"FolderTypes\{guid}\TopViews\{view}")
    by_name = {v.name: v for v in values}
    assert by_name["LogicalViewMode"].data == LOGICAL_VIEW_MODE_DETAILS
    assert by_name["LogicalViewMode"].kind == "dword"
    assert by_name["IconSize"].data == ICON_SIZE_DETAILS
    assert all(v.key == r"FolderTypes\{guid}\TopViews\{view}" for v in values)


def test_this_pc_bag_values_target_bag_one():
    """This PC gets NodeSlot 1 and Details bags under Bags\\1\\Shell and Bags\\1\\ComDlg."""
    values = this_pc_bag_values()
    keys = {v.key for v in values}
    assert rf"{BAGS_KEY}\1\Shell\{THIS_PC_GUID}" in keys
    assert rf"{BAGS_KEY}\1\ComDlg\{THIS_PC_GUID}" in keys
    node_slot = [v for v in values if v.name == "NodeSlot"]
    assert len(node_slot) == 1
    assert node_slot[0].data == 1
    assert node_slot[0].key == BAGMRU_KEY + r"\0"
    shell_bag = [
        v for v in values if v.key == rf"{BAGS_KEY}\1\Shell\{THIS_PC_GUID}" and v.name == "Mode"
    ]
    assert shell_bag[0].data == MODE_DETAILS


def test_this_pc_pidl_is_binary():
    """The BagMRU slot value 0 holds the This PC PIDL as raw bytes."""
    values = this_pc_bag_values()
    pidl = [v for v in values if v.key == BAGMRU_KEY and v.name == "0"]
    assert len(pidl) == 1
    assert pidl[0].kind == "binary"
    assert isinstance(pidl[0].data, bytes)
    assert pidl[0].data.startswith(bytes.fromhex("14001F50"))


def test_backup_dir_name_is_timestamped():
    """Backup directories sort chronologically and are unique per second."""
    name = backup_dir_name(datetime(2026, 7, 16, 13, 5, 9))
    assert name == "view-backup-20260716-130509"
